"""Exact-sequence current-to-shadow field transfer for Task035e.

The blind controller cannot retain a live DOLFINx object between two watchdog
processes.  A current solve therefore publishes an immutable, rank-partitioned
snapshot.  This module reconstructs that current p6 Nedelec carrier field on
its hash-bound mesh and transfers it to the p6 carrier of one independently
solved p- or h-shadow.

For a true local-h shadow the transfer uses DOLFINx nonmatching Nedelec
interpolation.  It then interpolates the result back to the current carrier
and checks both field and curl round trips.  The returned shadow field is only
an injected current state; it is never substituted for the independently
solved shadow endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from basix.ufl import element
from mpi4py import MPI
import numpy as np
import ufl

from dolfinx import default_real_type, fem

from .stage4_local_h import build_stage4_local_h_mesh_data
from .task035e_multigoal_snapshot import LoadedTask035eSnapshot


TRANSFER_SCHEMA = "task035e.exact-sequence-shadow-field-transfer.v1"


class Task035eShadowTransferError(RuntimeError):
    """Fail-closed current-to-shadow transfer error."""


@dataclass(frozen=True, slots=True)
class Task035eShadowFieldTransfer:
    """Transferred current field and its exact-sequence audit."""

    current_field: fem.Function
    shadow_field: fem.Function
    current_mesh_data: Any
    audit: Mapping[str, Any]


def _identity_sha256(value: Any, *, label: str) -> str:
    digest = str(value)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{label} must be one lowercase SHA-256")
    return digest


def _shadow_transition_identity(
    *,
    current_forest_sha256: str,
    current_hanging_sha256: str,
    current_degree_sha256: str,
    shadow_forest_sha256: str,
    shadow_hanging_sha256: str,
    shadow_degree_sha256: str,
) -> Mapping[str, Any]:
    """Classify a p/h shadow from executed geometry and degree identities."""

    current_forest = _identity_sha256(
        current_forest_sha256,
        label="current forest identity",
    )
    current_hanging = _identity_sha256(
        current_hanging_sha256,
        label="current hanging-face identity",
    )
    current_degree = _identity_sha256(
        current_degree_sha256,
        label="current degree identity",
    )
    shadow_forest = _identity_sha256(
        shadow_forest_sha256,
        label="shadow forest identity",
    )
    shadow_hanging = _identity_sha256(
        shadow_hanging_sha256,
        label="shadow hanging-face identity",
    )
    shadow_degree = _identity_sha256(
        shadow_degree_sha256,
        label="shadow degree identity",
    )
    same_forest_geometry = bool(
        current_forest == shadow_forest
        and current_hanging == shadow_hanging
    )
    same_degree_plan = current_degree == shadow_degree
    if same_forest_geometry and not same_degree_plan:
        observed_kind = "p-shadow"
    elif not same_forest_geometry:
        observed_kind = "h-shadow"
    else:
        observed_kind = "no-op-shadow"
    return MappingProxyType(
        {
            "schema_version": (
                "task035e.executed-shadow-transition-identity.v1"
            ),
            "current_forest_leaf_catalog_sha256": current_forest,
            "current_hanging_face_catalog_sha256": current_hanging,
            "current_cell_degree_plan_sha256": current_degree,
            "shadow_forest_leaf_catalog_sha256": shadow_forest,
            "shadow_hanging_face_catalog_sha256": shadow_hanging,
            "shadow_cell_degree_plan_sha256": shadow_degree,
            "same_forest_geometry": same_forest_geometry,
            "same_degree_plan": same_degree_plan,
            "observed_shadow_kind": observed_kind,
            "whole_plan_file_sha_used_for_shadow_classification": False,
        }
    )


def _json_sha256(value: Any, *, namespace: str) -> str:
    encoded = json.dumps(
        value,
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


def _collective_failure(
    communicator: MPI.Intracomm,
    *,
    phase: str,
    error: Exception | None,
) -> None:
    packet = (
        None
        if error is None
        else {
            "rank": int(communicator.rank),
            "phase": phase,
            "exception_type": type(error).__name__,
            "message": str(error),
        }
    )
    errors = [
        row for row in communicator.allgather(packet) if row is not None
    ]
    if errors:
        raise Task035eShadowTransferError(
            f"{phase} failed collectively: "
            + json.dumps(errors, sort_keys=True)
        )


def _owned_vector_values(function: fem.Function) -> tuple[
    np.ndarray,
    tuple[int, int],
    int,
]:
    vector = function.x.petsc_vec
    start, end = map(int, vector.getOwnershipRange())
    values = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    if values.shape != (end - start,) or not np.all(np.isfinite(values)):
        raise ValueError("Nedelec field owned coefficient array is invalid")
    return values, (start, end), int(vector.getSize())


def _p6_space(mesh: Any) -> Any:
    return fem.functionspace(
        mesh,
        element(
            "N1curl",
            mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )


def reconstruct_task035e_snapshot_p6_field(
    snapshot: LoadedTask035eSnapshot,
    *,
    config: Any,
) -> tuple[fem.Function, Any, Mapping[str, Any]]:
    """Rebuild the current carrier and restore this rank's owned p6 field."""

    manifest = snapshot.manifest
    plan = manifest.get("plan_identity")
    if not isinstance(plan, Mapping):
        raise ValueError("snapshot plan identity is absent")
    plan_path = Path(str(plan.get("path", ""))).expanduser().resolve()
    plan_sha = str(plan.get("file_sha256", ""))
    if (
        not plan_path.is_file()
        or len(plan_sha) != 64
        or snapshot.manifest_path.parent == plan_path
    ):
        raise ValueError("snapshot current plan binding is invalid")

    communicator = config_comm = getattr(config, "_task035e_comm", None)
    if config_comm is not None:
        raise ValueError(
            "Task035e configuration must not carry a hidden communicator"
        )
    del communicator
    # The snapshot loader has already required its communicator to match the
    # rank catalog.  Stage-4 mesh construction must use that same communicator.
    # The local shard rank is a reliable way to recover it without storing an
    # MPI object in immutable JSON.
    comm = MPI.COMM_WORLD
    if int(manifest.get("mpi_size", -1)) != int(comm.size):
        raise ValueError("snapshot and reconstruction communicator differ")
    mesh_data = build_stage4_local_h_mesh_data(
        config,
        plan_path,
        comm=comm,
    )
    context = mesh_data.local_h_context
    forest_audit = (
        None if context is None else getattr(context.forest, "audit", None)
    )
    if (
        context is None
        or context.plan_file_sha256 != plan_sha
        or context.audit.get("pass") is not True
        or not isinstance(forest_audit, Mapping)
        or forest_audit.get("leaf_catalog_sha256")
        != plan.get("forest_leaf_catalog_sha256")
    ):
        raise ValueError("reconstructed current mesh differs from the snapshot")
    current_degree_sha = _identity_sha256(
        plan.get("cell_degree_plan_sha256"),
        label="snapshot current degree identity",
    )
    current_hanging_sha = _identity_sha256(
        forest_audit.get("hanging_face_catalog_sha256"),
        label="snapshot current hanging-face identity",
    )
    space = _p6_space(mesh_data.mesh)
    field = fem.Function(space, name="task035e_snapshot_current_p6")
    owned = np.asarray(
        snapshot.arrays["p6_recovered_field_owned"],
        dtype=np.complex128,
    )
    partition = manifest.get("partitions", {}).get(
        "p6_recovered_field", {}
    )
    expected_range = tuple(
        map(
            int,
            partition.get("ownership_ranges", [])[comm.rank],
        )
    )
    observed_range = tuple(
        map(int, field.x.petsc_vec.getOwnershipRange())
    )
    if (
        expected_range != observed_range
        or owned.shape != (observed_range[1] - observed_range[0],)
        or int(field.x.petsc_vec.getSize())
        != int(partition.get("global_size", -1))
        or not np.all(np.isfinite(owned))
    ):
        raise ValueError(
            "reconstructed p6 carrier ownership differs from the snapshot"
        )
    field.x.petsc_vec.getArray()[:] = owned
    field.x.scatter_forward()
    audit = {
        "schema_version": "task035e.snapshot-p6-reconstruction.v1",
        "status": "snapshot_p6_field_reconstruction_pass",
        "pass": True,
        "plan_file_sha256": plan_sha,
        "forest_leaf_catalog_sha256": plan[
            "forest_leaf_catalog_sha256"
        ],
        "forest_hanging_face_catalog_sha256": current_hanging_sha,
        "cell_degree_plan_sha256": current_degree_sha,
        "p6_global_rows": int(partition["global_size"]),
        "p6_ownership_range": list(observed_range),
        "snapshot_manifest_file_sha256": (
            snapshot.manifest_file_sha256
        ),
        "snapshot_shard_file_sha256": hashlib.sha256(
            snapshot.shard_path.read_bytes()
        ).hexdigest(),
        "coefficient_source": "immutable_rank_owned_snapshot_shard",
        "full_vector_python_allgather_used": False,
        "ordinary_default_changed": False,
    }
    return field, mesh_data, MappingProxyType(audit)


def _all_cells(space: Any) -> np.ndarray:
    topology = space.mesh.topology
    dimension = topology.dim
    index_map = topology.index_map(dimension)
    return np.arange(
        index_map.size_local + index_map.num_ghosts,
        dtype=np.int32,
    )


def _interpolate_nonmatching(
    source: fem.Function,
    target_space: Any,
    *,
    name: str,
    padding: float,
) -> fem.Function:
    cells = _all_cells(target_space)
    interpolation_data = fem.create_interpolation_data(
        target_space,
        source.function_space,
        cells,
        padding=float(padding),
    )
    target = fem.Function(target_space, name=name)
    target.interpolate_nonmatching(source, cells, interpolation_data)
    target.x.scatter_forward()
    return target


def _relative_coefficient_error(
    expected: fem.Function,
    observed: fem.Function,
) -> tuple[float, float, float]:
    expected_values, expected_range, expected_size = _owned_vector_values(
        expected
    )
    observed_values, observed_range, observed_size = _owned_vector_values(
        observed
    )
    if (
        expected_range != observed_range
        or expected_size != observed_size
        or expected_values.shape != observed_values.shape
    ):
        raise ValueError("round-trip coefficient layouts differ")
    difference = observed_values - expected_values
    local = np.asarray(
        [
            float(np.vdot(difference, difference).real),
            float(np.vdot(expected_values, expected_values).real),
            float(np.max(np.abs(difference), initial=0.0)),
        ],
        dtype=np.float64,
    )
    total = np.zeros(3, dtype=np.float64)
    expected.function_space.mesh.comm.Allreduce(
        local[:2],
        total[:2],
        op=MPI.SUM,
    )
    total[2] = expected.function_space.mesh.comm.allreduce(
        float(local[2]),
        op=MPI.MAX,
    )
    error = float(math.sqrt(total[0]))
    norm = float(math.sqrt(total[1]))
    return error / max(norm, np.finfo(float).tiny), error, float(total[2])


def _relative_form_error(
    expected: fem.Function,
    observed: fem.Function,
    *,
    curl: bool,
) -> tuple[float, float, float]:
    difference = observed - expected
    expected_expression = ufl.curl(expected) if curl else expected
    difference_expression = ufl.curl(difference) if curl else difference
    error_form = fem.form(
        ufl.inner(difference_expression, difference_expression) * ufl.dx
    )
    reference_form = fem.form(
        ufl.inner(expected_expression, expected_expression) * ufl.dx
    )
    communicator = expected.function_space.mesh.comm
    local = np.asarray(
        [
            float(np.real(fem.assemble_scalar(error_form))),
            float(np.real(fem.assemble_scalar(reference_form))),
        ],
        dtype=np.float64,
    )
    global_values = np.zeros(2, dtype=np.float64)
    communicator.Allreduce(local, global_values, op=MPI.SUM)
    if (
        np.any(global_values < -1.0e-18)
        or not np.all(np.isfinite(global_values))
    ):
        raise RuntimeError("field/curl round-trip form norm is invalid")
    error = math.sqrt(max(float(global_values[0]), 0.0))
    reference = math.sqrt(max(float(global_values[1]), 0.0))
    return error / max(reference, np.finfo(float).tiny), error, reference


def _require_world_communicator(
    communicator: MPI.Intracomm,
) -> int:
    """Accept MPI_COMM_WORLD itself or one congruent duplicate.

    DOLFINx owns a duplicated communicator for each mesh.  mpi4py object
    equality therefore rejects ``mesh.comm`` even though MPI formally
    classifies it as congruent to ``MPI_COMM_WORLD``.  A communicator with a
    different group or rank ordering remains out of scope for the formal
    Task035e transfer.
    """

    try:
        relation = int(
            MPI.Comm.Compare(communicator, MPI.COMM_WORLD)
        )
    except Exception as exc:
        raise ValueError(
            "Task035e formal shadow transfer requires a valid MPI "
            "communicator"
        ) from exc
    if relation not in {int(MPI.IDENT), int(MPI.CONGRUENT)}:
        raise ValueError(
            "Task035e formal shadow transfer requires the world communicator "
            "or one congruent duplicate"
        )
    return relation


def transfer_task035e_snapshot_to_shadow_p6(
    snapshot: LoadedTask035eSnapshot,
    shadow_view: Any,
    *,
    padding: float = 1.0e-10,
    relative_tolerance: float = 5.0e-9,
) -> Task035eShadowFieldTransfer:
    """Inject one current snapshot into the solved shadow p6 carrier.

    The shadow endpoint in ``shadow_view.field`` remains untouched.  The
    returned ``shadow_field`` is a distinct function containing only the
    transferred current state.
    """

    comm = shadow_view.mesh_data.mesh.comm
    _require_world_communicator(comm)
    tolerance = float(relative_tolerance)
    if (
        not math.isfinite(tolerance)
        or tolerance <= 0.0
        or not math.isfinite(float(padding))
        or float(padding) <= 0.0
    ):
        raise ValueError("shadow transfer tolerances must be positive")

    current_field = None
    current_mesh_data = None
    reconstruction: Mapping[str, Any] | None = None
    error = None
    try:
        current_field, current_mesh_data, reconstruction = (
            reconstruct_task035e_snapshot_p6_field(
                snapshot,
                config=shadow_view.config,
            )
        )
    except Exception as exc:
        error = exc
    _collective_failure(
        comm,
        phase="current p6 reconstruction",
        error=error,
    )
    if (
        current_field is None
        or current_mesh_data is None
        or reconstruction is None
    ):
        raise Task035eShadowTransferError(
            "collective current p6 reconstruction lost its result"
        )

    shadow_space = shadow_view.field.function_space
    shadow_field = None
    round_trip = None
    error = None
    try:
        shadow_field = _interpolate_nonmatching(
            current_field,
            shadow_space,
            name="task035e_current_injected_to_shadow_p6",
            padding=float(padding),
        )
        round_trip = _interpolate_nonmatching(
            shadow_field,
            current_field.function_space,
            name="task035e_shadow_injection_roundtrip_current_p6",
            padding=float(padding),
        )
    except Exception as exc:
        error = exc
    _collective_failure(
        comm,
        phase="nonmatching Nedelec shadow interpolation",
        error=error,
    )
    if shadow_field is None or round_trip is None:
        raise Task035eShadowTransferError(
            "collective nonmatching interpolation lost its result"
        )

    metrics = None
    error = None
    try:
        coefficient = _relative_coefficient_error(
            current_field,
            round_trip,
        )
        field = _relative_form_error(
            current_field,
            round_trip,
            curl=False,
        )
        curl = _relative_form_error(
            current_field,
            round_trip,
            curl=True,
        )
        metrics = {
            "coefficient_relative_l2": coefficient[0],
            "coefficient_error_l2": coefficient[1],
            "coefficient_max_abs_error": coefficient[2],
            "field_relative_l2": field[0],
            "field_error_l2": field[1],
            "field_reference_l2": field[2],
            "curl_relative_l2": curl[0],
            "curl_error_l2": curl[1],
            "curl_reference_l2": curl[2],
        }
        if not all(
            math.isfinite(float(value)) for value in metrics.values()
        ):
            raise RuntimeError("shadow transfer metrics are non-finite")
    except Exception as exc:
        error = exc
    _collective_failure(
        comm,
        phase="exact-sequence shadow round-trip audit",
        error=error,
    )
    if metrics is None:
        raise Task035eShadowTransferError(
            "collective shadow transfer audit lost its metrics"
        )
    shadow_context = shadow_view.mesh_data.local_h_context
    shadow_forest_audit = (
        None
        if shadow_context is None
        else getattr(shadow_context.forest, "audit", None)
    )
    shadow_degree_audit = getattr(
        shadow_view.reduction.degree_plan,
        "audit",
        None,
    )
    identity_error = None
    transition_identity: Mapping[str, Any] | None = None
    try:
        if not isinstance(shadow_forest_audit, Mapping) or not isinstance(
            shadow_degree_audit,
            Mapping,
        ):
            raise ValueError(
                "shadow forest or degree execution identity is absent"
            )
        transition_identity = _shadow_transition_identity(
            current_forest_sha256=reconstruction[
                "forest_leaf_catalog_sha256"
            ],
            current_hanging_sha256=reconstruction[
                "forest_hanging_face_catalog_sha256"
            ],
            current_degree_sha256=reconstruction[
                "cell_degree_plan_sha256"
            ],
            shadow_forest_sha256=shadow_forest_audit[
                "leaf_catalog_sha256"
            ],
            shadow_hanging_sha256=shadow_forest_audit[
                "hanging_face_catalog_sha256"
            ],
            shadow_degree_sha256=shadow_degree_audit[
                "cell_degree_plan_sha256"
            ],
        )
    except Exception as exc:
        identity_error = exc
    _collective_failure(
        comm,
        phase="executed p/h shadow identity classification",
        error=identity_error,
    )
    if transition_identity is None:
        raise Task035eShadowTransferError(
            "collective p/h shadow identity classification lost its result"
        )
    checks = {
        "coefficient_roundtrip": (
            metrics["coefficient_relative_l2"] <= tolerance
        ),
        "field_roundtrip": metrics["field_relative_l2"] <= tolerance,
        "curl_roundtrip": metrics["curl_relative_l2"] <= tolerance,
        "current_mesh_qualified": (
            current_mesh_data.local_h_context.audit.get("pass") is True
        ),
        "shadow_mesh_qualified": (
            shadow_context is not None
            and shadow_context.audit.get("pass") is True
        ),
        "executed_shadow_transition_is_not_noop": (
            transition_identity["observed_shadow_kind"]
            in {"p-shadow", "h-shadow"}
        ),
    }
    passed = all(checks.values())
    current_plan_sha = reconstruction["plan_file_sha256"]
    shadow_plan_sha = (
        shadow_view.mesh_data.local_h_context.plan_file_sha256
    )
    unsigned = {
        "schema_version": TRANSFER_SCHEMA,
        "status": (
            "exact_sequence_shadow_field_transfer_pass"
            if passed
            else "exact_sequence_shadow_field_transfer_fail"
        ),
        "pass": passed,
        "snapshot_manifest_file_sha256": (
            snapshot.manifest_file_sha256
        ),
        "current_plan_file_sha256": current_plan_sha,
        "shadow_plan_file_sha256": shadow_plan_sha,
        "transition_identity": dict(transition_identity),
        "observed_shadow_kind": transition_identity[
            "observed_shadow_kind"
        ],
        "same_mesh_p_shadow": (
            transition_identity["observed_shadow_kind"] == "p-shadow"
        ),
        "true_nonmatching_h_shadow": (
            transition_identity["observed_shadow_kind"] == "h-shadow"
        ),
        "interpolation": (
            "DOLFINx N1curl p6 nonmatching interpolation followed by "
            "shadow-to-current round-trip"
        ),
        "relative_tolerance": tolerance,
        "padding": float(padding),
        "metrics": metrics,
        "checks": checks,
        "reconstruction": dict(reconstruction),
        "commuting_credit": (
            "field_and_curl_roundtrip_verified"
            if passed
            else "none"
        ),
        "shadow_endpoint_reused_as_injected_current": False,
        "hidden_reference_consumed": False,
        "full_vector_python_allgather_used": False,
        "ordinary_default_changed": False,
    }
    audit = {
        **unsigned,
        "transfer_sha256": _json_sha256(
            unsigned,
            namespace="task035e.shadow-field-transfer-audit.v1",
        ),
    }
    if not passed:
        raise Task035eShadowTransferError(
            "Task035e exact-sequence field transfer failed: "
            + json.dumps(checks, sort_keys=True)
        )
    return Task035eShadowFieldTransfer(
        current_field=current_field,
        shadow_field=shadow_field,
        current_mesh_data=current_mesh_data,
        audit=MappingProxyType(audit),
    )


__all__ = [
    "TRANSFER_SCHEMA",
    "Task035eShadowFieldTransfer",
    "Task035eShadowTransferError",
    "reconstruct_task035e_snapshot_p6_field",
    "transfer_task035e_snapshot_to_shadow_p6",
]
