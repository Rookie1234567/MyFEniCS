"""End-to-end live p/h-shadow evaluator for Task035e.

The current blind state is read only from its immutable MPI snapshot.  During
the independently solved shadow callback this module transfers the current p6
Nedelec field, reconstructs the current auxiliary coordinates in the shadow
reduced layout, builds all 59 live goal gradients, and evaluates the actual
signed DWR estimates with the borrowed direct factorization.

Only compact audit metadata is exchanged as Python objects.  Distributed
field, matrix, residual, gradient, and adjoint values remain PETSc-owned and
are never gathered into a Python full-vector representation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType, SimpleNamespace
from typing import Any, Callable, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.adaptivity.variable_p_transfer import (
    project_p6_primal_to_active_full,
    recover_active_full_to_p6_field,
)
from src.solvers.common_3d_utils import _trim_process_heap

from .blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from .task035e_actual_dwr import evaluate_task035e_actual_dwr
from .task035e_goal_gradients import (
    build_task035e_formal_secant_goal_gradients,
)
from .task035e_multigoal_snapshot import (
    LoadedTask035eSnapshot,
    _goal_context_identity,
    load_task035e_multigoal_snapshot,
)
from .task035e_shadow_transfer import (
    transfer_task035e_snapshot_to_shadow_p6,
)


SHADOW_EVALUATION_SCHEMA = "task035e.live-shadow-evaluation.v1"
_SOURCE_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ARRAY_DTYPE = np.dtype("<c16")


class Task035eShadowObserverError(RuntimeError):
    """Fail-closed live-shadow pipeline or publication failure."""


def _requires_exact_nested_current_projection(
    shadow_kind: str,
) -> bool:
    """Return the projection contract for one qualified shadow kind."""

    if shadow_kind not in {"p-shadow", "h-shadow"}:
        raise ValueError("shadow kind must be p-shadow or h-shadow")
    return shadow_kind == "p-shadow"


@dataclass(frozen=True, slots=True)
class Task035eShadowEvaluationReceipt:
    """Immutable authority receipt returned on every MPI rank."""

    path: Path
    file_sha256: str
    payload_sha256: str
    source_sha: str
    trial_id: str
    cycle_index: int
    shadow_kind: str
    actual_dwr_report_sha256: str
    formal_mpi8_qualified: bool


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
            raise ValueError("shadow evaluation contains a non-finite float")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(
        "shadow evaluation contains an unsupported object: "
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


def _array_sha256(values: Any, *, namespace: str) -> str:
    array = np.ascontiguousarray(values, dtype=_ARRAY_DTYPE)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError("auxiliary coordinate array is invalid")
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(
        np.asarray(array.shape, dtype=np.dtype("<i8")).tobytes()
    )
    digest.update(array.tobytes())
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


def _require_same_hash(
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
        raise Task035eShadowObserverError(
            f"{label} differs across MPI ranks"
        )


def _public_affine_complement_audit(
    communicator: MPI.Intracomm,
    local_audit: Mapping[str, Any],
    dwr_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the replay-safe aggregate affine-complement identity.

    The owner-local audit intentionally contains rank-dependent row-layout
    and owned-cell fields.  The actual-DWR report represents those fields by
    an ordered catalog of per-rank hashes; only that aggregate identity is
    suitable for the common shadow-evaluation payload.
    """

    raw_public = dwr_report.get(
        "active_interior_affine_complement"
    )
    if not isinstance(raw_public, Mapping):
        raise Task035eShadowObserverError(
            "actual DWR omitted the affine-complement public identity"
        )
    public = _jsonable(raw_public)
    if not isinstance(public, dict) or public.get("present") is not True:
        raise Task035eShadowObserverError(
            "actual DWR affine-complement public identity is invalid"
        )
    audit_identity = public.get("audit_identity")
    if (
        not isinstance(audit_identity, dict)
        or audit_identity.get("pass") is not True
    ):
        raise Task035eShadowObserverError(
            "actual DWR affine-complement aggregate audit is invalid"
        )
    rank_catalog = audit_identity.get("rank_local_audit_sha256")
    if (
        not isinstance(rank_catalog, list)
        or len(rank_catalog) != int(communicator.size)
    ):
        raise Task035eShadowObserverError(
            "actual DWR affine-complement rank catalog is invalid"
        )
    digests = [
        _sha256(value, label="affine-complement rank audit SHA-256")
        for value in rank_catalog
    ]
    expected_local_digest = _json_sha256(
        local_audit,
        namespace=(
            "task035e.actual-dwr.rank-affine-complement-audit.v1"
        ),
    )
    if digests[int(communicator.rank)] != expected_local_digest:
        raise Task035eShadowObserverError(
            "actual DWR affine-complement rank catalog lost the local audit"
        )
    return public


def _collective_local_call(
    communicator: MPI.Intracomm,
    phase: str,
    operation: Callable[[], Any],
) -> Any:
    """Finish one rank-local phase on every rank before any later collective."""

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
        row for row in communicator.allgather(local_error) if row is not None
    ]
    if errors:
        raise Task035eShadowObserverError(
            f"{phase} failed collectively before the next MPI phase: "
            + json.dumps(errors, sort_keys=True)
        )
    return result


def _current_auxiliary_solver_coordinates(
    snapshot: LoadedTask035eSnapshot,
    shadow_view: Any,
) -> tuple[np.ndarray, Mapping[str, Any]]:
    """Recover only the small current auxiliary tail by owner reduction."""

    comm = shadow_view.mesh_data.mesh.comm
    def local_preflight() -> tuple[
        int,
        int,
        int,
        np.ndarray,
        np.ndarray,
        Mapping[str, Any],
        Mapping[str, Any],
        np.ndarray,
    ]:
        manifest = snapshot.manifest
        common = manifest.get("common_identity")
        reduction = (
            None
            if not isinstance(common, Mapping)
            else common.get("reduction")
        )
        current_goal = (
            None
            if not isinstance(common, Mapping)
            else common.get("goal_context")
        )
        partitions = manifest.get("partitions")
        reduced_partition = (
            None
            if not isinstance(partitions, Mapping)
            else partitions.get("reduced")
        )
        if (
            not isinstance(reduction, Mapping)
            or not isinstance(current_goal, Mapping)
            or not isinstance(reduced_partition, Mapping)
        ):
            raise ValueError(
                "current snapshot lacks reduction/goal/partition identity"
            )
        current_trace = int(reduction["independent_trace_rows"])
        appended = int(reduction["appended_auxiliary_rows"])
        reduced_size = int(reduced_partition["global_size"])
        if (
            appended <= 0
            or current_trace + appended != reduced_size
            or appended != int(current_goal["mode_count"])
        ):
            raise ValueError(
                "current snapshot auxiliary layout does not close"
            )
        ranges = reduced_partition.get("ownership_ranges")
        if not isinstance(ranges, list) or len(ranges) != comm.size:
            raise ValueError(
                "current reduced ownership catalog differs from MPI size"
            )
        start, end = map(int, ranges[comm.rank])
        local = np.asarray(
            snapshot.arrays["reduced_x_owned"],
            dtype=np.complex128,
        )
        if (
            local.shape != (end - start,)
            or not np.all(np.isfinite(local))
        ):
            raise ValueError("current owned reduced solution is invalid")

        local_tail = np.zeros(appended, dtype=np.complex128)
        local_coverage = np.zeros(appended, dtype=np.int32)
        lower = max(start, current_trace)
        upper = min(end, reduced_size)
        if upper > lower:
            target = slice(lower - current_trace, upper - current_trace)
            source = slice(lower - start, upper - start)
            local_tail[target] = local[source]
            local_coverage[target] = 1

        shadow_system = shadow_view.reduction.system
        shadow_context = dict(shadow_view.goal_context)
        modes = tuple(shadow_context.get("modes", ()))
        raw_scales = shadow_context.get("auxiliary_coordinate_scales")
        scales = (
            np.ones(len(modes), dtype=np.complex128)
            if raw_scales is None
            else np.asarray(raw_scales, dtype=np.complex128)
        )
        if (
            int(shadow_system.appended_rows) != appended
            or len(modes) != appended
            or scales.shape != (appended,)
            or not np.all(np.isfinite(scales))
            or np.any(np.abs(scales) <= 0.0)
        ):
            raise ValueError(
                "current and shadow auxiliary coordinate layouts differ"
            )
        shadow_goal = _goal_context_identity(shadow_context)
        invariant_fields = (
            "mode_count",
            "ordered_modes_sha256",
            "incident_projections_sha256",
            "coordinate_scales_sha256",
            "coordinate_scale_source",
            "normalization",
            "formal_goal_count",
            "formal_goal_inventory_sha256",
        )
        differing = [
            name
            for name in invariant_fields
            if current_goal.get(name) != shadow_goal.get(name)
        ]
        if differing:
            raise ValueError(
                "current and shadow DtN identities differ: "
                f"{differing}"
            )
        return (
            current_trace,
            appended,
            reduced_size,
            local_tail,
            local_coverage,
            current_goal,
            shadow_goal,
            scales,
        )

    preflight = _collective_local_call(
        comm,
        "current auxiliary rank-local preflight",
        local_preflight,
    )
    if preflight is None:
        raise Task035eShadowObserverError(
            "current auxiliary preflight returned no rank-local state"
        )
    (
        current_trace,
        appended,
        _reduced_size,
        local_tail,
        local_coverage,
        current_goal,
        _shadow_goal,
        scales,
    ) = preflight
    solver_coordinates = np.zeros_like(local_tail)
    coverage = np.zeros_like(local_coverage)
    comm.Allreduce(local_tail, solver_coordinates, op=MPI.SUM)
    comm.Allreduce(local_coverage, coverage, op=MPI.SUM)
    if not np.all(coverage == 1):
        raise RuntimeError(
            "current auxiliary solver coordinates are not owned exactly once"
        )

    def local_postflight() -> tuple[str, dict[str, Any]]:
        physical_auxiliary = solver_coordinates / scales
        physical_hash = _array_sha256(
            physical_auxiliary,
            namespace="task035e.current-physical-auxiliary-values.v1",
        )
        if physical_hash != current_goal["auxiliary_values_sha256"]:
            raise ValueError(
                "current reduced auxiliary tail differs from its physical "
                "goal-context values"
            )
        audit = {
            "schema_version": (
                "task035e.current-auxiliary-tail-reconstruction.v1"
            ),
            "status": "current_auxiliary_tail_reconstruction_pass",
            "pass": True,
            "mpi_size": int(comm.size),
            "current_independent_trace_rows": current_trace,
            "appended_auxiliary_rows": appended,
            "coverage_min": int(coverage.min()),
            "coverage_max": int(coverage.max()),
            "solver_coordinate_sha256": _array_sha256(
                solver_coordinates,
                namespace="task035e.current-solver-auxiliary-values.v1",
            ),
            "physical_auxiliary_sha256": physical_hash,
            "ordered_modes_sha256": current_goal[
                "ordered_modes_sha256"
            ],
            "incident_projections_sha256": current_goal[
                "incident_projections_sha256"
            ],
            "coordinate_scales_sha256": current_goal[
                "coordinate_scales_sha256"
            ],
            "rank_local_validation_rendezvous": True,
            "python_full_reduced_vector_allgather_used": False,
            "native_small_auxiliary_allreduce_used": True,
            "ordinary_default_changed": False,
        }
        return physical_hash, audit

    postflight = _collective_local_call(
        comm,
        "current auxiliary rank-local postflight",
        local_postflight,
    )
    if postflight is None:
        raise Task035eShadowObserverError(
            "current auxiliary postflight returned no audit"
        )
    physical_hash, audit = postflight
    _require_same_hash(
        comm,
        physical_hash,
        label="current physical auxiliary values",
    )
    return solver_coordinates, MappingProxyType(audit)


def _rank_pipeline_catalog(
    communicator: MPI.Intracomm,
    *,
    transfer: Mapping[str, Any],
    projection: Mapping[str, Any],
    extraction: Mapping[str, Any],
    trace_conformance: Mapping[str, Any],
) -> list[dict[str, Any]]:
    local = {
        "rank": int(communicator.rank),
        "transfer": _jsonable(transfer),
        "projection": _jsonable(projection),
        "primal_extraction": _jsonable(extraction),
        "trace_conformance": _jsonable(trace_conformance),
    }
    rows = communicator.allgather(local)
    if [int(row["rank"]) for row in rows] != list(
        range(communicator.size)
    ):
        raise RuntimeError("shadow pipeline rank audit is incomplete")
    return rows


def _public_trace_conformance_audit(
    communicator: MPI.Intracomm,
    local_audit: Mapping[str, Any],
    *,
    rank_pipeline_catalog_sha256: str,
) -> Mapping[str, Any]:
    """Return the collective trace summary used by the replayed payload.

    Extraction and recovery retain owner-local selected-row counts.  Their full
    audits belong in ``rank_pipeline_audits``; copying one rank's nested audit
    into the common payload makes a valid MPI execution non-replayable.
    """

    catalog_sha = _sha256(
        rank_pipeline_catalog_sha256,
        label="rank pipeline catalog SHA-256",
    )
    root_fields = (
        "schema_version",
        "status",
        "pass",
        "shadow_kind",
        "exact_nested_projection_retained",
        "physical_root_projection_applied",
        "ordinary_default_changed",
    )
    if any(field not in local_audit for field in root_fields):
        raise Task035eShadowObserverError(
            "trace-conformance audit lacks its public root fields"
        )
    public = {
        field: _jsonable(local_audit[field])
        for field in root_fields
    }
    if public["pass"] is not True:
        raise Task035eShadowObserverError(
            "trace-conformance public audit is not passing"
        )
    public.update(
        {
            "rank_pipeline_catalog_sha256": catalog_sha,
            "rank_local_detail_location": "rank_pipeline_audits",
            "rank_local_selected_row_fields_omitted_from_public_payload": True,
        }
    )

    if public["physical_root_projection_applied"] is True:
        nested = {
            name: local_audit.get(name)
            for name in (
                "pre_recovery_temporary_release",
                "projection_pipeline",
                "conforming_p6_recovery",
                "coefficient_projection",
            )
        }
        if not all(
            isinstance(value, Mapping) and value.get("pass") is True
            for value in nested.values()
        ):
            raise Task035eShadowObserverError(
                "physical-root trace audit lacks one passing component"
            )
        pipeline_fields = (
            "schema_version",
            "status",
            "pass",
            "input_receives_exact_nested_transfer_credit",
            "active_interior_rows_bitwise_unchanged",
            "strict_reextraction_closure_l2_norm",
            "strict_reextraction_closure_linf_norm",
            "strict_reextraction_reference_l2_norm",
            "strict_reextraction_reference_linf_norm",
            "strict_reextraction_relative_l2",
            "strict_reextraction_relative_linf",
            "strict_reextraction_tolerance",
            "full_vector_allgather_used",
            "ordinary_default_changed",
        )
        recovery_fields = (
            "schema_version",
            "status",
            "pass",
            "absolute_shared_coefficient_error_max",
            "relative_shared_coefficient_error_max",
            "conformity_tolerance",
            "target_field_reused",
            "new_p6_function_allocated",
            "replaced_field_coefficients_audited_before_overwrite",
            "replaced_coefficient_delta_l2_norm",
            "replaced_coefficient_reference_l2_norm",
            "replaced_coefficient_delta_relative_l2",
            "replaced_coefficient_delta_linf_norm",
            "replaced_coefficient_reference_linf_norm",
            "replaced_coefficient_delta_relative_linf",
            "replaced_coefficient_rows_designated_exactly_once",
            "selected_values_reused_for_recovery_and_conformity_audit",
            "full_active_vector_replicated_bytes_per_rank",
            "global_embedding_matrix_allocated",
            "ordinary_default_changed",
        )
        pipeline = nested["projection_pipeline"]
        recovery = nested["conforming_p6_recovery"]
        if (
            any(field not in pipeline for field in pipeline_fields)
            or any(field not in recovery for field in recovery_fields)
        ):
            raise Task035eShadowObserverError(
                "physical-root trace audit lacks one public metric"
            )
        public.update(
            {
                "pre_recovery_temporary_release": _jsonable(
                    nested["pre_recovery_temporary_release"]
                ),
                "projection_pipeline": {
                    field: _jsonable(pipeline[field])
                    for field in pipeline_fields
                },
                "conforming_p6_recovery": {
                    field: _jsonable(recovery[field])
                    for field in recovery_fields
                },
                "coefficient_projection": _jsonable(
                    nested["coefficient_projection"]
                ),
            }
        )
    elif public["shadow_kind"] != "p-shadow":
        raise Task035eShadowObserverError(
            "non-p-shadow trace audit omitted physical-root projection"
        )

    public_sha = _json_sha256(
        public,
        namespace="task035e.trace-conformance-public-audit.v1",
    )
    _require_same_hash(
        communicator,
        public_sha,
        label="trace-conformance public audit",
    )
    return MappingProxyType(
        {
            **public,
            "public_audit_sha256": public_sha,
        }
    )


def _p6_coefficient_projection_audit(
    *,
    delta_l2: float,
    delta_linf: float,
    reference_l2: float,
    reference_linf: float,
    source_projection_relative_scale: float,
) -> Mapping[str, Any]:
    """Bound the conforming correction by the preceding local projection."""

    scale = float(source_projection_relative_scale)
    values = tuple(
        float(value)
        for value in (
            delta_l2,
            delta_linf,
            reference_l2,
            reference_linf,
        )
    )
    if not math.isfinite(scale) or scale < 0.0 or not all(
        math.isfinite(value) and value >= 0.0 for value in values
    ):
        raise ValueError(
            "conforming p6 coefficient audit inputs are inconsistent"
        )
    relative_l2 = delta_l2 / max(
        reference_l2,
        np.finfo(np.float64).tiny,
    )
    relative_linf = delta_linf / max(
        reference_linf,
        np.finfo(np.float64).tiny,
    )
    relative_l2_limit = max(5.0e-10, 2.0 * scale)
    passed = bool(
        all(
            math.isfinite(value)
            for value in (
                delta_l2,
                delta_linf,
                reference_l2,
                reference_linf,
                relative_l2,
                relative_linf,
            )
        )
        and relative_l2 <= relative_l2_limit
    )
    audit = {
        "schema_version": (
            "task035e.h-shadow-conforming-p6-coefficient-audit.v1"
        ),
        "status": (
            "h_shadow_conforming_p6_coefficient_projection_pass"
            if passed
            else "h_shadow_conforming_p6_coefficient_projection_fail"
        ),
        "pass": passed,
        "coefficient_delta_l2_norm": delta_l2,
        "coefficient_delta_linf_norm": delta_linf,
        "coefficient_reference_l2_norm": reference_l2,
        "coefficient_reference_linf_norm": reference_linf,
        "coefficient_delta_relative_l2": relative_l2,
        "coefficient_delta_relative_linf": relative_linf,
        "source_local_projection_relative_scale": scale,
        "relative_l2_acceptance_limit": relative_l2_limit,
        "acceptance_rule": (
            "conforming correction relative L2 <= max(5e-10, "
            "2*max(local p6 round-trip, shared-active prediction))"
        ),
        "exact_nested_transfer_credit": False,
        "ordinary_default_changed": False,
    }
    if not passed:
        raise RuntimeError(
            "h-shadow conforming p6 coefficient correction exceeds its "
            "source projection scale: "
            f"relative_l2={relative_l2:.6e}, "
            f"limit={relative_l2_limit:.6e}"
        )
    return MappingProxyType(audit)


def _release_h_shadow_projection_temporaries(
    communicator: MPI.Intracomm,
    *,
    phase: str,
) -> Mapping[str, Any]:
    """Release one h-shadow projection phase's native temporaries."""

    if phase not in {
        "before_in_place_p6_recovery",
        "before_goal_gradients",
    }:
        raise ValueError("h-shadow projection cleanup phase is invalid")
    gc.collect()
    PETSc.garbage_cleanup(communicator)
    gc.collect()
    local = _trim_process_heap()
    rows = communicator.allgather(
        {
            "rank": int(communicator.rank),
            **local,
        }
    )
    if [int(row["rank"]) for row in rows] != list(
        range(communicator.size)
    ):
        raise RuntimeError(
            "h-shadow projection cleanup lost one MPI rank"
        )
    supported = all(row["supported"] is True for row in rows)
    succeeded = all(row["succeeded"] is True for row in rows)
    before = [
        float(row["rss_before_mb"])
        for row in rows
        if row["rss_before_mb"] is not None
    ]
    after = [
        float(row["rss_after_mb"])
        for row in rows
        if row["rss_after_mb"] is not None
    ]
    released = [
        float(row["rss_released_mb"])
        for row in rows
        if row["rss_released_mb"] is not None
    ]
    passed = bool(supported and succeeded)
    audit = {
        "schema_version": (
            "task035e.h-shadow-projection-temporary-release.v1"
        ),
        "status": (
            "h_shadow_projection_temporaries_released"
            if passed
            else "h_shadow_projection_temporary_release_failed"
        ),
        "pass": passed,
        "phase": phase,
        "python_gc_called_twice": True,
        "petsc_garbage_cleanup_called": True,
        "glibc_malloc_trim_called": True,
        "supported_on_all_ranks": supported,
        "succeeded_on_all_ranks": succeeded,
        "return_codes_by_rank": [
            row["return_code"] for row in rows
        ],
        "sum_rss_before_mb": (
            None
            if len(before) != communicator.size
            else float(sum(before))
        ),
        "sum_rss_after_mb": (
            None
            if len(after) != communicator.size
            else float(sum(after))
        ),
        "sum_rss_released_mb": (
            None
            if len(released) != communicator.size
            else float(sum(released))
        ),
        "release_occurs_before_in_place_p6_recovery": (
            phase == "before_in_place_p6_recovery"
        ),
        "release_occurs_before_formal_goal_gradients": (
            phase == "before_goal_gradients"
        ),
        "live_reduced_primal_retained": True,
        "live_p6_storage_retained": True,
        "live_conforming_p6_field_retained": (
            phase == "before_goal_gradients"
        ),
        "live_preconformance_p6_coefficients_retained": (
            phase == "before_in_place_p6_recovery"
        ),
        "live_conforming_active_primal_retained": (
            phase == "before_in_place_p6_recovery"
        ),
        "live_affine_complement_retained": (
            phase == "before_goal_gradients"
        ),
        "ordinary_default_changed": False,
    }
    if not passed:
        raise RuntimeError(
            "h-shadow projection temporary release is unavailable on one "
            "or more ranks"
        )
    return MappingProxyType(audit)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"shadow evaluation parent directory is absent: {path.parent}"
        )
    if path.exists():
        raise FileExistsError(
            f"shadow evaluation is immutable and already exists: {path}"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                _jsonable(payload),
                stream,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _validate_observed_shadow_kind(
    transfer_audit: Mapping[str, Any],
    *,
    expected_shadow_kind: str,
) -> Mapping[str, Any]:
    """Require the requested role to match executed forest/degree changes."""

    if expected_shadow_kind not in {"p-shadow", "h-shadow"}:
        raise ValueError("expected shadow kind must be p-shadow or h-shadow")
    transition = transfer_audit.get("transition_identity")
    if not isinstance(transition, Mapping):
        raise ValueError("shadow transfer has no transition identity")
    observed = transition.get("observed_shadow_kind")
    if observed != expected_shadow_kind:
        raise ValueError(
            "requested shadow kind differs from executed forest/degree "
            f"transition: requested={expected_shadow_kind}, "
            f"observed={observed}"
        )
    same_forest = transition.get("same_forest_geometry")
    same_degree = transition.get("same_degree_plan")
    expected_structure = (
        same_forest is True and same_degree is False
        if expected_shadow_kind == "p-shadow"
        else same_forest is False
    )
    if not expected_structure:
        raise ValueError(
            "executed forest/degree transition is inconsistent with its "
            "classified shadow kind"
        )
    return MappingProxyType(
        {
            "schema_version": (
                "task035e.requested-observed-shadow-kind-closure.v1"
            ),
            "pass": True,
            "requested_shadow_kind": expected_shadow_kind,
            "observed_shadow_kind": observed,
            "same_forest_geometry": bool(same_forest),
            "same_degree_plan": bool(same_degree),
            "whole_plan_file_sha_used_for_classification": False,
        }
    )


def evaluate_and_write_task035e_shadow(
    shadow_view: Any,
    *,
    current_snapshot_manifest: str | Path,
    current_snapshot_manifest_sha256: str,
    artifact_path: str | Path,
    source_sha: str,
    trial_id: str,
    cycle_index: int,
    expected_shadow_plan_sha256: str,
    shadow_kind: str,
    allow_serial_test_fixture: bool = False,
) -> Task035eShadowEvaluationReceipt:
    """Execute and persist the complete current-to-shadow DWR pipeline."""

    comm = shadow_view.mesh_data.mesh.comm
    source = _source_sha(source_sha)
    snapshot_sha = _sha256(
        current_snapshot_manifest_sha256,
        label="current snapshot manifest SHA-256",
    )
    shadow_plan_sha = _sha256(
        expected_shadow_plan_sha256,
        label="shadow plan SHA-256",
    )
    if shadow_kind not in {"p-shadow", "h-shadow"}:
        raise ValueError("shadow_kind must be p-shadow or h-shadow")
    if (
        not isinstance(trial_id, str)
        or not trial_id.strip()
        or type(cycle_index) is not int
        or not 0 <= cycle_index <= 5
    ):
        raise ValueError("shadow trial/cycle identity is invalid")
    formal_mpi8 = int(comm.size) == 8
    if not formal_mpi8 and not (
        int(comm.size) == 1 and allow_serial_test_fixture is True
    ):
        raise Task035eShadowObserverError(
            "formal Task035e shadow evaluation requires MPI8"
        )

    request_identity = {
        "source_sha": source,
        "trial_id": trial_id,
        "cycle_index": cycle_index,
        "shadow_kind": shadow_kind,
        "current_snapshot_manifest": str(
            Path(current_snapshot_manifest).expanduser().resolve()
        ),
        "current_snapshot_manifest_sha256": snapshot_sha,
        "artifact_path": str(Path(artifact_path).expanduser().resolve()),
        "expected_shadow_plan_sha256": shadow_plan_sha,
        "mpi_size": int(comm.size),
        "formal_mpi8_qualified": formal_mpi8,
    }
    request_sha = _json_sha256(
        request_identity,
        namespace="task035e.live-shadow-observer-request.v1",
    )
    _require_same_hash(
        comm,
        request_sha,
        label="live shadow observer request",
    )

    def load_and_validate_snapshot() -> LoadedTask035eSnapshot:
        loaded = load_task035e_multigoal_snapshot(
            current_snapshot_manifest,
            expected_manifest_file_sha256=snapshot_sha,
            communicator=comm,
        )
        if (
            loaded.manifest.get("source_sha") != source
            or loaded.manifest.get("trial_id") != trial_id
            or loaded.manifest.get("cycle_index") != cycle_index
        ):
            raise ValueError(
                "current snapshot source/trial/cycle differs from shadow "
                "request"
            )
        return loaded

    snapshot = _collective_local_call(
        comm,
        "rank-local current snapshot load and replay",
        load_and_validate_snapshot,
    )
    if not isinstance(snapshot, LoadedTask035eSnapshot):
        raise Task035eShadowObserverError(
            "collective current snapshot load returned no snapshot"
        )
    snapshot_identity = {
        "manifest_path": str(snapshot.manifest_path),
        "manifest_file_sha256": snapshot.manifest_file_sha256,
        "manifest_payload_sha256": snapshot.manifest[
            "manifest_payload_sha256"
        ],
        "current_plan_file_sha256": snapshot.manifest["plan_identity"][
            "file_sha256"
        ],
    }
    current_plan_path = str(
        snapshot.manifest["plan_identity"]["path"]
    )
    current_plan_file_sha256 = str(
        snapshot.manifest["plan_identity"]["file_sha256"]
    )

    active_current = None
    reduced_current = None
    affine_complement = None
    heavy_state_release_audit = None
    recovered_state_release_audit: Mapping[str, Any] | None = None
    trace_conformance_audit: Mapping[str, Any] | None = None
    pre_recovery_temporary_release_audit: Mapping[str, Any] | None = None
    pre_gradient_temporary_release_audit: Mapping[str, Any] | None = None
    try:
        transfer = transfer_task035e_snapshot_to_shadow_p6(
            snapshot,
            shadow_view,
        )
        transfer_audit = dict(transfer.audit)
        shadow_kind_audit = _collective_local_call(
            comm,
            "requested versus observed shadow-kind closure",
            lambda: _validate_observed_shadow_kind(
                transfer_audit,
                expected_shadow_kind=shadow_kind,
            ),
        )
        if not isinstance(shadow_kind_audit, Mapping):
            raise Task035eShadowObserverError(
                "collective shadow-kind closure returned no audit"
            )
        active_current, projection_audit = (
            project_p6_primal_to_active_full(
                shadow_view.reduction.transfer,
                transfer.shadow_field.x.petsc_vec,
                require_exact_nested=(
                    _requires_exact_nested_current_projection(
                        shadow_kind
                    )
                ),
            )
        )
        auxiliary, auxiliary_audit = (
            _current_auxiliary_solver_coordinates(
                snapshot,
                shadow_view,
            )
        )
        if shadow_kind == "p-shadow":
            reduced_current, extraction_audit = (
                shadow_view.reduction.extract_primal_to_reduced(
                    active_current,
                    auxiliary_reduced_values=auxiliary,
                )
            )
            current_endpoint_field = transfer.shadow_field
            trace_conformance_audit = MappingProxyType(
                {
                    "schema_version": (
                        "task035e.h-shadow-trace-conformance.v1"
                    ),
                    "status": (
                        "physical_root_trace_projection_not_required"
                    ),
                    "pass": True,
                    "shadow_kind": shadow_kind,
                    "exact_nested_projection_retained": True,
                    "physical_root_projection_applied": False,
                    "ordinary_default_changed": False,
                }
            )
        else:
            (
                reduced_current,
                conformed_active,
                extraction_audit,
            ) = shadow_view.reduction.project_primal_trace_to_reduced(
                active_current,
                auxiliary_reduced_values=auxiliary,
            )
            active_current.destroy()
            active_current = conformed_active
            pre_recovery_temporary_release_audit = (
                _release_h_shadow_projection_temporaries(
                    comm,
                    phase="before_in_place_p6_recovery",
                )
            )
            current_endpoint_field, recovery_audit = (
                recover_active_full_to_p6_field(
                    shadow_view.reduction.transfer,
                    active_current,
                    target_field=transfer.shadow_field,
                )
            )
            projection_scale = max(
                float(
                    projection_audit[
                        "p6_round_trip_relative_error_l2"
                    ]
                ),
                float(
                    projection_audit[
                        "shared_active_prediction_relative_error_max"
                    ]
                ),
            )
            coefficient_audit = _p6_coefficient_projection_audit(
                delta_l2=float(
                    recovery_audit[
                        "replaced_coefficient_delta_l2_norm"
                    ]
                ),
                delta_linf=float(
                    recovery_audit[
                        "replaced_coefficient_delta_linf_norm"
                    ]
                ),
                reference_l2=float(
                    recovery_audit[
                        "replaced_coefficient_reference_l2_norm"
                    ]
                ),
                reference_linf=float(
                    recovery_audit[
                        "replaced_coefficient_reference_linf_norm"
                    ]
                ),
                source_projection_relative_scale=projection_scale,
            )
            trace_conformance_audit = MappingProxyType(
                {
                    "schema_version": (
                        "task035e.h-shadow-trace-conformance.v1"
                    ),
                    "status": (
                        "physical_root_conforming_h_shadow_projection_pass"
                    ),
                    "pass": True,
                    "shadow_kind": shadow_kind,
                    "exact_nested_projection_retained": False,
                    "physical_root_projection_applied": True,
                    "pre_recovery_temporary_release": dict(
                        pre_recovery_temporary_release_audit
                    ),
                    "projection_pipeline": extraction_audit,
                    "conforming_p6_recovery": recovery_audit,
                    "coefficient_projection": dict(coefficient_audit),
                    "ordinary_default_changed": False,
                }
            )
        if shadow_kind == "p-shadow":
            pre_recovery_temporary_release_audit = MappingProxyType(
                {
                    "schema_version": (
                        "task035e.h-shadow-projection-"
                        "temporary-release.v1"
                    ),
                    "status": (
                        "h_shadow_projection_temporary_release_not_required"
                    ),
                    "pass": True,
                    "phase": "before_in_place_p6_recovery",
                    "shadow_kind": shadow_kind,
                    "release_occurs_before_in_place_p6_recovery": False,
                    "release_occurs_before_formal_goal_gradients": False,
                    "ordinary_default_changed": False,
                }
            )
        del transfer
        if shadow_view.recovered.active_full_rhs is None:
            raise Task035eShadowObserverError(
                "shadow recovery lost the active full RHS"
            )
        if (
            shadow_view.recovered.active_auxiliary_interior_action
            is not None
        ):
            raise Task035eShadowObserverError(
                "formal Task035e trace-only port unexpectedly retained an "
                "auxiliary-to-cell-interior action"
            )
        affine_complement = (
            shadow_view.reduction.primal_affine_complement(
                active_current,
                shadow_view.recovered.active_full_rhs,
            )
        )
        if affine_complement.active_full_complement is None:
            raise Task035eShadowObserverError(
                "affine-interior complement construction returned no vector"
            )
        recovered_state_rows = {
            name: (
                None
                if vector is None
                else int(vector.getSize())
            )
            for name, vector in (
                (
                    "active_full_solution",
                    shadow_view.recovered.active_full_solution,
                ),
                (
                    "active_full_rhs",
                    shadow_view.recovered.active_full_rhs,
                ),
                (
                    "active_auxiliary_interior_action",
                    shadow_view.recovered.active_auxiliary_interior_action,
                ),
            )
        }
        shadow_view.recovered.destroy()
        recovered_state_release_audit = MappingProxyType(
            {
                "schema_version": (
                    "task035e.pre-gradient-recovered-state-release.v1"
                ),
                "status": "recovered_active_vectors_released",
                "pass": True,
                "released_global_rows": recovered_state_rows,
                "recovered_p6_field_retained": True,
                "active_full_solution_released": (
                    recovered_state_rows["active_full_solution"] is not None
                ),
                "active_full_rhs_released": (
                    recovered_state_rows["active_full_rhs"] is not None
                ),
                "active_auxiliary_interior_action_was_absent": (
                    recovered_state_rows[
                        "active_auxiliary_interior_action"
                    ]
                    is None
                ),
                "ordinary_default_changed": False,
            }
        )

        current_goal_context = dict(shadow_view.goal_context)
        raw_scales = current_goal_context.get(
            "auxiliary_coordinate_scales"
        )
        scales = (
            np.ones(len(auxiliary), dtype=np.complex128)
            if raw_scales is None
            else np.asarray(raw_scales, dtype=np.complex128)
        )
        if (
            scales.shape != auxiliary.shape
            or not np.all(np.isfinite(scales))
            or np.any(np.abs(scales) <= 0.0)
        ):
            raise Task035eShadowObserverError(
                "current endpoint auxiliary scales are invalid"
            )
        current_physical_auxiliary = np.asarray(
            auxiliary / scales,
            dtype=np.complex128,
        )
        current_physical_auxiliary.setflags(write=False)
        current_goal_context["auxiliary_values"] = (
            current_physical_auxiliary
        )
        current_endpoint_view = SimpleNamespace(
            field=current_endpoint_field,
            mesh_data=shadow_view.mesh_data,
            config=shadow_view.config,
            x=reduced_current,
            reduction=shadow_view.reduction,
            goal_context=MappingProxyType(current_goal_context),
            port_metrics=shadow_view.port_metrics,
        )
        active_current.destroy()
        active_current = None
        del auxiliary
        del snapshot
        pre_gradient_temporary_release_audit = (
            _release_h_shadow_projection_temporaries(
                comm,
                phase="before_goal_gradients",
            )
            if shadow_kind == "h-shadow"
            else MappingProxyType(
                {
                    "schema_version": (
                        "task035e.h-shadow-projection-"
                        "temporary-release.v1"
                    ),
                    "status": (
                        "h_shadow_projection_temporary_release_not_required"
                    ),
                    "pass": True,
                    "phase": "before_goal_gradients",
                    "shadow_kind": shadow_kind,
                    "release_occurs_before_in_place_p6_recovery": False,
                    "release_occurs_before_formal_goal_gradients": False,
                    "ordinary_default_changed": False,
                }
            )
        )
        heavy_state_release_audit = {
            "schema_version": (
                "task035e.pre-adjoint-heavy-state-release.v3"
            ),
            "pass": True,
            "active_current_vector_destroyed_before_gradients": True,
            "snapshot_python_reference_released_before_gradients": True,
            "recovered_active_vector_release": dict(
                recovered_state_release_audit
            ),
            "current_transferred_p6_field_retained_for_exact_secant_gradient": (
                shadow_kind == "p-shadow"
            ),
            "current_conforming_p6_field_retained_for_secant_gradient": (
                True
            ),
            "original_nonconforming_h_shadow_coefficients_overwritten_before_gradients": (
                shadow_kind == "h-shadow"
            ),
            "h_shadow_p6_storage_reused_in_place": (
                shadow_kind == "h-shadow"
            ),
            "current_endpoint_p6_field_released_after_gradient_and_dwr": True,
            "active_affine_complement_retained_through_dwr_only": True,
            "pre_recovery_temporary_release": dict(
                pre_recovery_temporary_release_audit
            ),
            "pre_gradient_temporary_release": dict(
                pre_gradient_temporary_release_audit
            ),
            "native_allocator_release_timing_claimed": False,
        }
        with build_task035e_formal_secant_goal_gradients(
            current_endpoint_view,
            shadow_view,
        ) as goal_gradients:
            dwr = evaluate_task035e_actual_dwr(
                shadow_view,
                reduced_current,
                goal_gradients.gradients,
                source_sha=source,
                expected_shadow_plan_sha256=shadow_plan_sha,
                shadow_kind=shadow_kind,
                current_plan_path=current_plan_path,
                expected_current_plan_sha256=(
                    current_plan_file_sha256
                ),
                require_cellwise_partition=True,
                active_full_affine_complement=(
                    affine_complement.active_full_complement
                ),
                active_full_goal_gradients=(
                    goal_gradients.active_full_gradients
                ),
                affine_complement_audit=affine_complement.audit,
                require_affine_complement=True,
            )
            gradient_audit = dict(goal_gradients.audit)
        affine_complement_audit = dict(affine_complement.audit)
        affine_complement_public_audit = (
            _public_affine_complement_audit(
                comm,
                affine_complement_audit,
                dwr.report,
            )
        )
        del current_endpoint_view
        del current_endpoint_field
    finally:
        if affine_complement is not None:
            affine_complement.destroy()
        if reduced_current is not None:
            reduced_current.destroy()
        if active_current is not None:
            active_current.destroy()

    if (
        transfer_audit.get("pass") is not True
        or shadow_kind_audit.get("pass") is not True
        or projection_audit.get("pass") is not True
        or extraction_audit.get("pass") is not True
        or trace_conformance_audit is None
        or trace_conformance_audit.get("pass") is not True
        or pre_recovery_temporary_release_audit is None
        or pre_recovery_temporary_release_audit.get("pass") is not True
        or pre_gradient_temporary_release_audit is None
        or pre_gradient_temporary_release_audit.get("pass") is not True
        or recovered_state_release_audit is None
        or recovered_state_release_audit.get("pass") is not True
        or auxiliary_audit.get("pass") is not True
        or affine_complement_audit.get("pass") is not True
        or gradient_audit.get("pass") is not True
        or dwr.report.get("pass") is not True
        or tuple(dwr.signed_eta) != FORMAL_GOAL_IDS
        or not isinstance(dwr.cellwise_partition, Mapping)
        or dwr.cellwise_partition.get("pass") is not True
    ):
        raise Task035eShadowObserverError(
            "one live-shadow component did not pass exactly"
        )

    gradient_sha = _sha256(
        gradient_audit["gradient_inventory_sha256"],
        label="gradient inventory SHA-256",
    )
    _require_same_hash(
        comm,
        gradient_sha,
        label="gradient inventory",
    )
    _require_same_hash(
        comm,
        dwr.report_sha256,
        label="actual DWR report",
    )
    _require_same_hash(
        comm,
        _json_sha256(
            affine_complement_public_audit,
            namespace=(
                "task035e.shadow-evaluation."
                "affine-complement-public-audit.v1"
            ),
        ),
        label="affine-complement public audit",
    )
    rank_catalog = _rank_pipeline_catalog(
        comm,
        transfer=transfer_audit,
        projection=projection_audit,
        extraction=extraction_audit,
        trace_conformance=trace_conformance_audit,
    )
    rank_catalog_sha = _json_sha256(
        rank_catalog,
        namespace="task035e.shadow-pipeline-rank-catalog.v1",
    )
    trace_conformance_public_audit = (
        _public_trace_conformance_audit(
            comm,
            trace_conformance_audit,
            rank_pipeline_catalog_sha256=rank_catalog_sha,
        )
    )
    unsigned = {
        "schema_version": SHADOW_EVALUATION_SCHEMA,
        "status": "live_shadow_59_goal_actual_dwr_pass",
        "pass": True,
        "source_sha": source,
        "trial_id": trial_id,
        "cycle_index": cycle_index,
        "shadow_kind": shadow_kind,
        "mpi_size": int(comm.size),
        "formal_mpi8_qualified": formal_mpi8,
        "diagnostic_serial_fixture": not formal_mpi8,
        "current_snapshot": {
            **snapshot_identity,
        },
        "shadow_plan_file_sha256": shadow_plan_sha,
        "shadow_kind_closure": dict(shadow_kind_audit),
        "current_auxiliary_reconstruction": dict(auxiliary_audit),
        "physical_root_trace_conformance": dict(
            trace_conformance_public_audit
        ),
        "active_interior_affine_complement": (
            affine_complement_public_audit
        ),
        "pre_adjoint_heavy_state_release": dict(
            heavy_state_release_audit
        ),
        "rank_pipeline_audits": rank_catalog,
        "rank_pipeline_catalog_sha256": rank_catalog_sha,
        "goal_gradient_inventory": gradient_audit,
        "actual_dwr": dict(dwr.report),
        "cellwise_dwr_partition": dict(dwr.cellwise_partition),
        "signed_dwr_delta": {
            goal_id: float(dwr.signed_eta[goal_id])
            for goal_id in FORMAL_GOAL_IDS
        },
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": (
            FORMAL_GOAL_INVENTORY_SHA256
        ),
        "algebra": {
            "current_field_source": "immutable current MPI snapshot",
            "current_to_shadow_transfer": transfer_audit["interpolation"],
            "current_reduced_injection": (
                (
                    "exact nested active primal projection plus "
                    "constraint left inverse"
                )
                if shadow_kind == "p-shadow"
                else (
                    "audited nonmatching coefficient-L2 projection into "
                    "the exact-sequence active space, physical-root "
                    "trace reconstruction, and strict constraint "
                    "re-extraction; no exact-transfer credit"
                )
            ),
            "shadow_residual": "b_shadow-A_shadow*x_current_in_shadow",
            "adjoint": "A_shadow^H*z_J=g_J",
            "goal_derivative": (
                "analytic current-to-shadow averaged derivative"
            ),
            "signed_estimator": (
                "Re(z_reduced,J^H*r_reduced)"
                "+Re(g_active-interior,J^H*c_affine)"
            ),
            "python_full_vector_allgather": False,
        },
        "capability_credit": {
            "current_primal_snapshot_complete": True,
            "current_to_shadow_injection_complete": True,
            "local_h_transfer_complete": shadow_kind == "h-shadow",
            "physical_root_trace_conformance_complete": (
                shadow_kind == "h-shadow"
            ),
            "formal_59_goal_gradient_construction_complete": True,
            "actual_enriched_residual_complete": True,
            "actual_59_goal_adjoint_complete": True,
            "actual_signed_dwr_complete": True,
            "static_condensation_affine_complement_complete": True,
            "analytic_secant_goal_derivative_complete": True,
            "shadow_endpoint_effectivity_complete": False,
            "accuracy_credit": False,
        },
        "hidden_reference_consumed": False,
        "endpoint_delta_used_as_dwr": False,
        "ordinary_default_changed": False,
    }
    payload_sha = _json_sha256(
        unsigned,
        namespace="task035e.live-shadow-evaluation-payload.v1",
    )
    payload = {**unsigned, "payload_sha256": payload_sha}
    output = Path(artifact_path).expanduser().resolve()
    write_error = None
    if comm.rank == 0:
        try:
            _atomic_json(output, payload)
        except Exception as exc:
            write_error = {
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
    write_error = comm.bcast(write_error, root=0)
    if write_error is not None:
        raise Task035eShadowObserverError(
            f"shadow evaluation publication failed: {write_error}"
        )
    comm.Barrier()
    replay_error = None
    file_sha = None
    try:
        if not output.is_file() or (output.stat().st_mode & 0o777) != 0o600:
            raise ValueError(
                "shadow evaluation is absent or not mode 0600"
            )
        replay = json.loads(output.read_text(encoding="utf-8"))
        if replay != _jsonable(payload):
            raise ValueError(
                "shadow evaluation replay differs from live payload"
            )
        replay_unsigned = dict(replay)
        stored_payload_sha = replay_unsigned.pop("payload_sha256")
        if (
            stored_payload_sha != payload_sha
            or _json_sha256(
                replay_unsigned,
                namespace="task035e.live-shadow-evaluation-payload.v1",
            )
            != payload_sha
        ):
            raise ValueError("shadow evaluation self-hash differs")
        file_sha = _file_sha256(output)
    except Exception as exc:
        replay_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    errors = [
        row for row in comm.allgather(replay_error) if row is not None
    ]
    if errors or file_sha is None:
        raise Task035eShadowObserverError(
            "shadow evaluation replay failed: "
            + json.dumps(errors, sort_keys=True)
        )
    _require_same_hash(comm, file_sha, label="shadow evaluation file")
    return Task035eShadowEvaluationReceipt(
        path=output,
        file_sha256=file_sha,
        payload_sha256=payload_sha,
        source_sha=source,
        trial_id=trial_id,
        cycle_index=cycle_index,
        shadow_kind=shadow_kind,
        actual_dwr_report_sha256=dwr.report_sha256,
        formal_mpi8_qualified=formal_mpi8,
    )


def build_task035e_shadow_evaluation_observer(
    **kwargs: Any,
) -> Callable[[Any], None]:
    """Return the explicit opt-in live callback used by the watchdog."""

    def observer(view: Any) -> None:
        evaluate_and_write_task035e_shadow(view, **kwargs)

    return observer


__all__ = [
    "SHADOW_EVALUATION_SCHEMA",
    "Task035eShadowEvaluationReceipt",
    "Task035eShadowObserverError",
    "build_task035e_shadow_evaluation_observer",
    "evaluate_and_write_task035e_shadow",
]
