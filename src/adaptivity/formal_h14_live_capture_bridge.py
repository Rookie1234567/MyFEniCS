"""Fail-closed aggregation of capability-only h14 numerical snapshots.

This module does not add hooks to the assembly, DtN, or runner paths.  It
turns caller-supplied numerical objects into content-bound capability
snapshots and checks source/mesh/catalog/operator/communicator consistency.

No ``captured=True`` or ``formal=True`` argument exists.  Readiness follows
only from typed numerical payloads, their recomputed hashes, and cross-object
identity checks.  Caller declarations such as ``actual_pde`` or
``physical_condensation_used`` are hashed for diagnostics but never qualify
evidence.  Even a complete capability snapshot leaves the typed formal
contract incomplete: production assembly/run identity, distributed matrix
content identity, and collective live-observer binding do not yet exist.
Consequently this module never constructs a formal runner hook bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
from numbers import Integral, Real
import re
from types import MappingProxyType
from typing import Any, Hashable, Mapping, Sequence

import numpy as np
from mpi4py import MPI

from src.adaptivity.actual_physical_discrete_gradient_authority import (
    ActualPhysicalDiscreteGradientAuthority,
)
from src.adaptivity.complement_schur_channel_dwr import ChannelGoal
from src.adaptivity.dtn_goal_adjoint import (
    mpi_communicator_content_identity,
    replicated_adjoint_partition_content_identity,
)
from src.adaptivity.physical_missing_p6_action_only_complement import (
    ActualFocusChannelGoalBundle,
    FullP6LocalSchurClassCollector,
    PhysicalMissingP6ActionLayout,
    ProjectedCondensedDual,
    ProjectedDtnComplementMode,
)
from src.solvers.dtn_surface_vector_cache import (
    dtn_reduced_operator_identity,
)
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    validate_primal_recovery_mpc_backsubstitution,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_RHS_COMPONENTS = (
    "volume_source",
    "incident_traction",
    "dtn_incident_auxiliary",
)
_PRODUCTION_HOOKS_MISSING = (
    "formal_assembly_run_identity",
    "distributed_reduced_matrix_content_identity",
    "collective_live_observer_binding",
)
_CAPABILITY_EVIDENCE = "capability_only"
_FOCUS: Mapping[str, tuple[str, str, int, str]] = MappingProxyType(
    {
        "T_m-4_n0_s_power": ("real_power", "bottom", -4, "power"),
        "T_m-4_n0_s_amplitude_real": (
            "complex_amplitude_real",
            "bottom",
            -4,
            "amplitude_real",
        ),
        "T_m-4_n0_s_amplitude_imag": (
            "complex_amplitude_imag",
            "bottom",
            -4,
            "amplitude_imag",
        ),
        "R_m-4_n0_s_power": ("real_power", "top", -4, "power"),
        "R_m-4_n0_s_amplitude_real": (
            "complex_amplitude_real",
            "top",
            -4,
            "amplitude_real",
        ),
        "R_m-4_n0_s_amplitude_imag": (
            "complex_amplitude_imag",
            "top",
            -4,
            "amplitude_imag",
        ),
        "R_m-5_n0_s_power": ("real_power", "top", -5, "power"),
        "R_m-5_n0_s_amplitude_real": (
            "complex_amplitude_real",
            "top",
            -5,
            "amplitude_real",
        ),
        "R_m-5_n0_s_amplitude_imag": (
            "complex_amplitude_imag",
            "top",
            -5,
            "amplitude_imag",
        ),
    }
)


def _sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{label} must be a full SHA256")
    return normalized


def _source_sha(value: str) -> str:
    normalized = str(value).lower()
    if _SOURCE_SHA.fullmatch(normalized) is None:
        raise ValueError("source commit must be a full Git SHA")
    return normalized


def _canonical(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {
            "kind": "ndarray",
            "shape": list(array.shape),
            "dtype": array.dtype.str,
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    if isinstance(value, np.generic):
        return _canonical(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_canonical(item) for item in value),
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"live-capture hash cannot canonicalize {type(value).__name__}")


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(payload),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _freeze(value: Any) -> Any:
    """Return a recursively immutable copy of one JSON/numerical payload."""

    if isinstance(value, np.ndarray):
        result = np.array(value, copy=True, order="C")
        if np.issubdtype(result.dtype, np.number) and not np.all(np.isfinite(result)):
            raise FloatingPointError("capture payload contains NaN or Inf")
        result.setflags(write=False)
        return result
    if isinstance(value, np.generic):
        return _freeze(value.item())
    if isinstance(value, complex):
        if not np.isfinite(value):
            raise FloatingPointError("capture payload contains NaN or Inf")
        return complex(value)
    if isinstance(value, Real) and not isinstance(value, bool):
        if not np.isfinite(float(value)):
            raise FloatingPointError("capture payload contains NaN or Inf")
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _assert_finite_tree(value: Any, *, label: str) -> None:
    """Reject every non-finite numerical leaf in a capture payload."""

    if isinstance(value, np.ndarray):
        if np.issubdtype(value.dtype, np.number) and not np.all(np.isfinite(value)):
            raise FloatingPointError(f"{label} contains NaN or Inf")
        return
    if isinstance(value, np.generic):
        _assert_finite_tree(value.item(), label=label)
        return
    if isinstance(value, complex):
        if not np.isfinite(value):
            raise FloatingPointError(f"{label} contains NaN or Inf")
        return
    if isinstance(value, Real) and not isinstance(value, bool):
        if not np.isfinite(float(value)):
            raise FloatingPointError(f"{label} contains NaN or Inf")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite_tree(item, label=f"{label}.{key}")
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_finite_tree(item, label=f"{label}[{index}]")
        return
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            _assert_finite_tree(
                getattr(value, field.name),
                label=f"{label}.{field.name}",
            )


def _collective_snapshot(
    communicator: MPI.Intracomm,
    *,
    namespace: str,
    local_payload_sha256: str,
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...], str]:
    """Bind one rank-local payload to exact communicator membership/order."""

    local_hash = _sha256(
        local_payload_sha256,
        label=f"{namespace} local payload hash",
    )
    communicator_identity = mpi_communicator_content_identity(communicator)
    packet = {
        "rank": int(communicator.rank),
        "world_rank": int(MPI.COMM_WORLD.rank),
        "local_payload_sha256": local_hash,
    }
    packets = tuple(communicator.allgather(packet))
    expected_ranks = tuple(range(int(communicator.size)))
    if tuple(int(item["rank"]) for item in packets) != expected_ranks:
        raise RuntimeError(f"{namespace} communicator ranks are inconsistent")
    if tuple(int(item["world_rank"]) for item in packets) != tuple(
        communicator_identity["ordered_world_ranks"]
    ):
        raise RuntimeError(f"{namespace} communicator world-rank membership drifted")
    collective_hash = _hash(
        {
            "schema": "task035b.capability-collective-content.v1",
            "namespace": namespace,
            "communicator": communicator_identity,
            "packets": packets,
        }
    )
    return (
        _freeze(communicator_identity),
        tuple(_freeze(item) for item in packets),
        collective_hash,
    )


def _validate_stored_collective(
    *,
    namespace: str,
    local_payload_sha256: str,
    communicator_identity: Mapping[str, Any],
    collective_packets: Sequence[Mapping[str, Any]],
    collective_capture_sha256: str,
) -> None:
    """Recompute a stored collective record without trusting its pass flags."""

    local_hash = _sha256(
        local_payload_sha256,
        label=f"{namespace} local payload hash",
    )
    packets = tuple(dict(item) for item in collective_packets)
    size = _exact_integer(communicator_identity.get("size"))
    world_ranks = communicator_identity.get("ordered_world_ranks")
    if (
        size is None
        or size <= 0
        or not isinstance(world_ranks, Sequence)
        or isinstance(world_ranks, (str, bytes))
        or len(world_ranks) != size
        or len(set(map(int, world_ranks))) != size
        or len(packets) != size
    ):
        raise RuntimeError(f"{namespace} communicator identity is invalid")
    if tuple(int(item.get("rank", -1)) for item in packets) != tuple(range(size)):
        raise RuntimeError(f"{namespace} collective ranks are invalid")
    if tuple(int(item.get("world_rank", -1)) for item in packets) != tuple(
        map(int, world_ranks)
    ):
        raise RuntimeError(f"{namespace} collective membership is invalid")
    for item in packets:
        _sha256(
            str(item.get("local_payload_sha256", "")),
            label=f"{namespace} packet payload hash",
        )
    if local_hash not in {str(item["local_payload_sha256"]) for item in packets}:
        raise RuntimeError(
            f"{namespace} local payload is absent from collective packets"
        )
    expected_communicator_hash = _hash(
        {
            "schema_version": "task035b.mpi-communicator-content.v1",
            "size": size,
            "ordered_world_ranks": list(map(int, world_ranks)),
        }
    )
    if communicator_identity.get("content_sha256") != expected_communicator_hash:
        raise RuntimeError(f"{namespace} communicator hash is stale")
    expected_collective = _hash(
        {
            "schema": "task035b.capability-collective-content.v1",
            "namespace": namespace,
            "communicator": communicator_identity,
            "packets": packets,
        }
    )
    if (
        _sha256(
            collective_capture_sha256,
            label=f"{namespace} collective capture hash",
        )
        != expected_collective
    ):
        raise RuntimeError(f"{namespace} collective capture hash is stale")


def _capture_provenance(
    *,
    action_layout: PhysicalMissingP6ActionLayout,
    source_commit: str,
    mesh_sha256: str,
) -> Mapping[str, str]:
    source = _source_sha(source_commit)
    mesh_hash = _sha256(mesh_sha256, label="mesh hash")
    payload = {
        "schema": "task035b.h14-live-capture-provenance.v1",
        "source_commit": source,
        "mesh_sha256": mesh_hash,
        "catalog_sha256": _sha256(
            action_layout.catalog_sha256,
            label="catalog hash",
        ),
        "trace_geometry_sha256": _sha256(
            action_layout.trace_geometry_sha256,
            label="trace geometry hash",
        ),
        "ordered_trace_basis_sha256": _sha256(
            action_layout.ordered_trace_basis_sha256,
            label="ordered trace basis hash",
        ),
        "qualification_sha256": _sha256(
            action_layout.qualification_sha256,
            label="action-layout qualification hash",
        ),
        "complement_layout_sha256": _sha256(
            action_layout.complement_layout_sha256,
            label="complement layout hash",
        ),
    }
    return MappingProxyType(
        {
            **payload,
            "provenance_sha256": _hash(payload),
        }
    )


def _exact_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Integral):
        return None
    return int(value)


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    if not np.isfinite(result) or result < 0.0:
        return None
    return result


def _nested_residual(
    report: Mapping[str, Any],
    name: str,
) -> float | None:
    residual = report.get(name)
    if not isinstance(residual, Mapping):
        return None
    return _finite_nonnegative(residual.get("relative_residual"))


def _goal_report_numerics_pass(
    report: Mapping[str, Any],
    *,
    quantity: str,
) -> bool:
    """Recompute the existing adjoint report gate without its pass flags."""

    gradient_norm = _finite_nonnegative(report.get("gradient_norm"))
    if gradient_norm is None or gradient_norm <= 0.0:
        return False
    scale = max(gradient_norm, 1.0)
    reasons = tuple(
        _exact_integer(report.get(name))
        for name in (
            "transpose_converged_reason",
            "minus_converged_reason",
            "plus_converged_reason",
            "direct_tangent_converged_reason",
        )
    )
    residuals = tuple(
        _nested_residual(report, name)
        for name in (
            "adjoint_residual",
            "minus_primal_residual",
            "plus_primal_residual",
            "direct_tangent_residual",
        )
    )
    direct_relative = _finite_nonnegative(report.get("direct_adjoint_relative_error"))
    direct_absolute = _finite_nonnegative(report.get("direct_adjoint_absolute_error"))
    finite_relative = _finite_nonnegative(
        report.get("finite_difference_relative_error")
    )
    finite_absolute = _finite_nonnegative(
        report.get("finite_difference_absolute_error")
    )
    convention_token = {
        "power": "g_aux=2*w*outgoing_amplitude",
        "amplitude_real": "g_aux=conj(boundary_phase)",
        "amplitude_imag": "g_aux=i*conj(boundary_phase)",
    }[quantity]
    return bool(
        all(reason is not None and reason > 0 for reason in reasons)
        and all(residual is not None and residual <= 1.0e-9 for residual in residuals)
        and direct_relative is not None
        and direct_absolute is not None
        and (direct_relative <= 1.0e-8 or direct_absolute <= 1.0e-12 * scale)
        and finite_relative is not None
        and finite_absolute is not None
        and (finite_relative <= 1.0e-7 or finite_absolute <= 5.0e-11 * scale)
        and convention_token in str(report.get("gradient_convention", ""))
    )


def _vector(
    values: Any,
    *,
    dimension: int,
    label: str,
) -> np.ndarray:
    vector = np.asarray(values, dtype=np.complex128).copy()
    if vector.shape != (int(dimension),):
        raise ValueError(f"{label} has the wrong dimension")
    if not np.all(np.isfinite(vector)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    vector.setflags(write=False)
    return vector


def _matrix(
    values: Any,
    *,
    shape: tuple[int, int],
    label: str,
) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.complex128).copy()
    if matrix.shape != shape:
        raise ValueError(f"{label} has the wrong shape")
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    matrix.setflags(write=False)
    return matrix


def _local_schur_payload_sha256(
    *,
    schur_by_class: Mapping[Hashable, np.ndarray],
    cell_class_keys: Mapping[int, Hashable],
    storage_trace_rows_per_cell: int,
    provenance_sha256: str,
) -> str:
    dimension = int(storage_trace_rows_per_cell)
    classes = {
        key: _matrix(
            values,
            shape=(dimension, dimension),
            label=f"live local Schur class {key!r}",
        )
        for key, values in schur_by_class.items()
    }
    cells = {int(cell): key for cell, key in cell_class_keys.items()}
    if not cells or set(cells.values()) != set(classes):
        raise RuntimeError("local Schur class/cell inventory is not exact")
    return _hash(
        {
            "schema": "task035b.capability-local-schur-payload.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": _sha256(
                provenance_sha256,
                label="local Schur provenance hash",
            ),
            "storage_trace_rows_per_cell": dimension,
            "cell_class_keys": cells,
            "schur_by_class": classes,
        }
    )


def _dtn_content(
    *,
    modes: Sequence[ProjectedDtnComplementMode],
    retained_trace_rows: int,
    low_dimension: int,
    high_dimension: int,
    provenance_sha256: str,
    reduced_operator_sha256: str,
) -> tuple[str, str, np.ndarray]:
    retained = int(retained_trace_rows)
    low = int(low_dimension)
    high = int(high_dimension)
    selected = tuple(modes)
    if retained <= 0 or low <= retained or high <= 0:
        raise ValueError("DtN capability dimensions are invalid")
    indices = tuple(int(mode.auxiliary_global_index) for mode in selected)
    if indices != tuple(range(retained, low)):
        raise RuntimeError(
            "DtN capability modes do not cover every auxiliary row exactly once"
        )
    identities: list[Mapping[str, Any]] = []
    payload: dict[str, Any] = {}
    missing_incident = np.zeros(high, dtype=np.complex128)
    seen_physical_identities: set[tuple[str, int, int, str]] = set()
    for mode in selected:
        identity = dict(mode.mode_identity)
        exact_m = _exact_integer(identity.get("m"))
        exact_n = _exact_integer(identity.get("n"))
        physical_identity = (
            str(identity.get("side", "")),
            -(10**9) if exact_m is None else exact_m,
            -(10**9) if exact_n is None else exact_n,
            str(identity.get("polarization", "")),
        )
        if (
            physical_identity[0] not in {"top", "bottom"}
            or exact_m is None
            or exact_n is None
            or not physical_identity[3]
        ):
            raise RuntimeError("DtN capability mode identity is incomplete")
        if physical_identity in seen_physical_identities:
            raise RuntimeError("DtN physical mode identities are duplicated")
        seen_physical_identities.add(physical_identity)
        traction = _vector(
            mode.traction_high,
            dimension=high,
            label="DtN capability traction projection",
        )
        ell = _vector(
            mode.ell_high,
            dimension=high,
            label="DtN capability electric projection",
        )
        denominator = complex(mode.denominator)
        incident = complex(mode.incident_projection_solver)
        if (
            not np.isfinite(denominator)
            or abs(denominator) <= np.finfo(float).tiny
            or not np.isfinite(incident)
        ):
            raise FloatingPointError("DtN capability scalar is non-finite")
        identities.append(identity)
        missing_incident -= traction * incident
        payload[str(mode.auxiliary_global_index)] = {
            "mode_identity": identity,
            "traction_high": traction,
            "ell_high": ell,
            "denominator": denominator,
            "incident_projection_solver": incident,
            "caller_declared_live_projection": bool(
                mode.full_p6_component_vectors_projected_live
            ),
            "caller_declared_physical_condensation": bool(
                mode.physical_condensation_used
            ),
        }
    provenance_hash = _sha256(
        provenance_sha256,
        label="DtN capability provenance hash",
    )
    reduced_hash = _sha256(
        reduced_operator_sha256,
        label="DtN capability reduced-operator hash",
    )
    inventory_hash = _hash(
        {
            "schema": "task035b.capability-dtn-mode-inventory.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": provenance_hash,
            "mode_identities": identities,
            "auxiliary_indices": indices,
        }
    )
    payload_hash = _hash(
        {
            "schema": "task035b.capability-dtn-projected-payload.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": provenance_hash,
            "reduced_operator_sha256": reduced_hash,
            "payload": payload,
            "missing_incident_rhs": missing_incident,
        }
    )
    missing_incident.setflags(write=False)
    return inventory_hash, payload_hash, missing_incident


def _complete_rhs_content(
    *,
    complete: ProjectedCondensedDual,
    components: Mapping[str, ProjectedCondensedDual],
    low_dimension: int,
    high_dimension: int,
    provenance_sha256: str,
    reduced_operator_sha256: str,
    dtn_projected_payload_sha256: str,
    closure_tolerance: float,
) -> tuple[str, float]:
    if not np.isfinite(closure_tolerance) or float(closure_tolerance) <= 0.0:
        raise ValueError("complete RHS closure tolerance must be finite positive")
    if set(components) != set(_RHS_COMPONENTS):
        raise RuntimeError("complete RHS capability component set is incomplete")
    low = _vector(
        complete.retained,
        dimension=low_dimension,
        label="complete retained RHS",
    )
    high = _vector(
        complete.missing,
        dimension=high_dimension,
        label="complete missing RHS",
    )
    low_sum = np.zeros(low_dimension, dtype=np.complex128)
    high_sum = np.zeros(high_dimension, dtype=np.complex128)
    numerical_components: dict[str, Mapping[str, np.ndarray]] = {}
    for name in _RHS_COMPONENTS:
        retained = _vector(
            components[name].retained,
            dimension=low_dimension,
            label=f"{name} retained RHS",
        )
        missing = _vector(
            components[name].missing,
            dimension=high_dimension,
            label=f"{name} missing RHS",
        )
        low_sum += retained
        high_sum += missing
        numerical_components[name] = {
            "retained": retained,
            "missing": missing,
        }
    denominator = max(
        1.0,
        float(np.linalg.norm(low)),
        float(np.linalg.norm(high)),
    )
    decomposition_error = float(
        np.sqrt(
            np.linalg.norm(low - low_sum) ** 2 + np.linalg.norm(high - high_sum) ** 2
        )
        / denominator
    )
    if not np.isfinite(decomposition_error):
        raise FloatingPointError("complete RHS decomposition is non-finite")
    payload_hash = _hash(
        {
            "schema": "task035b.capability-complete-missing-rhs.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": _sha256(
                provenance_sha256,
                label="complete RHS provenance hash",
            ),
            "reduced_operator_sha256": _sha256(
                reduced_operator_sha256,
                label="complete RHS reduced-operator hash",
            ),
            "dtn_projected_payload_sha256": _sha256(
                dtn_projected_payload_sha256,
                label="complete RHS DtN payload hash",
            ),
            "closure_tolerance": float(closure_tolerance),
            "complete_retained": low,
            "complete_missing": high,
            "components": numerical_components,
        }
    )
    return payload_hash, decomposition_error


def _focus_goal_content(
    *,
    goals: Sequence[ChannelGoal],
    goal_reports: Mapping[str, Mapping[str, Any]],
    low_dimension: int,
    high_dimension: int,
    provenance_sha256: str,
    reduced_operator_sha256: str,
    communicator_identity: Mapping[str, Any],
) -> tuple[str, str]:
    selected = tuple(goals)
    by_label = {goal.label: goal for goal in selected}
    if len(selected) != len(_FOCUS) or set(by_label) != set(_FOCUS):
        raise RuntimeError("focus-goal capability is not exactly nine goals")
    if set(goal_reports) != set(_FOCUS):
        raise RuntimeError("focus-goal report set is not exactly nine reports")
    expected_comm_hash = communicator_identity.get("content_sha256")
    expected_world_ranks = tuple(
        map(int, communicator_identity.get("ordered_world_ranks", ()))
    )
    canonical_reports: dict[str, Any] = {}
    goal_payload: dict[str, Any] = {}
    for label, (component, side, order, quantity) in _FOCUS.items():
        goal = by_label[label]
        if (
            goal.component != component
            or goal.retained_adjoint.shape != (int(low_dimension),)
            or goal.missing_gradient.shape != (int(high_dimension),)
            or not np.all(np.isfinite(goal.retained_adjoint))
            or not np.array_equal(
                goal.missing_gradient,
                np.zeros(int(high_dimension), dtype=np.complex128),
            )
            or not np.isfinite(goal.tolerance)
            or goal.tolerance <= 0.0
            or goal.baseline_signed_error is None
            or not np.isfinite(float(goal.baseline_signed_error))
        ):
            raise RuntimeError(f"{label} capability goal payload is invalid")
        report = goal_reports[label]
        if not isinstance(report, Mapping):
            raise RuntimeError(f"{label} raw adjoint report is not a mapping")
        metadata = report.get("goal")
        auxiliary_index = _exact_integer(report.get("augmented_global_index"))
        matrix_rows = _exact_integer(report.get("matrix_rows"))
        adjoint_identity = report.get("adjoint_content_identity")
        if isinstance(adjoint_identity, Mapping):
            try:
                recomputed_identity = replicated_adjoint_partition_content_identity(
                    goal.retained_adjoint,
                    adjoint_identity,
                )
            except (KeyError, TypeError, ValueError, RuntimeError):
                recomputed_identity = None
        else:
            recomputed_identity = None
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("label") != label
            or metadata.get("side") != side
            or _exact_integer(metadata.get("m")) != order
            or _exact_integer(metadata.get("n")) != 0
            or metadata.get("polarization") != "s"
            or metadata.get("quantity") != quantity
            or auxiliary_index is None
            or matrix_rows != int(low_dimension)
            or not _goal_report_numerics_pass(report, quantity=quantity)
            or recomputed_identity is None
            or _canonical(adjoint_identity) != _canonical(recomputed_identity)
            or recomputed_identity.get("communicator_content_sha256")
            != expected_comm_hash
            or tuple(
                map(
                    int,
                    recomputed_identity.get(
                        "communicator_ordered_world_ranks",
                        (),
                    ),
                )
            )
            != expected_world_ranks
            or report.get("adjoint_content_sha256")
            != recomputed_identity["global_value_sha256"]
            or report.get("adjoint_partition_content_sha256")
            != recomputed_identity["global_content_sha256"]
        ):
            raise RuntimeError(f"{label} adjoint capability report is invalid")
        canonical_reports[label] = report
        goal_payload[label] = {
            "component": goal.component,
            "tolerance": float(goal.tolerance),
            "baseline_signed_error": float(goal.baseline_signed_error),
            "retained_adjoint": goal.retained_adjoint,
            "missing_gradient": goal.missing_gradient,
            "caller_declared_actual_channel_gradient": bool(
                goal.actual_channel_gradient
            ),
            "caller_declared_retained_adjoint_qualified": bool(
                goal.retained_adjoint_qualified
            ),
            "caller_declared_actual_discrete_system": bool(
                report.get("actual_discrete_system") is True
            ),
            "adjoint_content_sha256": (recomputed_identity["global_value_sha256"]),
            "adjoint_partition_content_sha256": (
                recomputed_identity["global_content_sha256"]
            ),
        }
    provenance_hash = _sha256(
        provenance_sha256,
        label="focus-goal provenance hash",
    )
    reduced_hash = _sha256(
        reduced_operator_sha256,
        label="focus-goal reduced-operator hash",
    )
    report_hash = _hash(
        {
            "schema": "task035b.capability-nine-focus-goal-reports.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": provenance_hash,
            "reports": canonical_reports,
        }
    )
    payload_hash = _hash(
        {
            "schema": "task035b.capability-nine-focus-goal-payload.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": provenance_hash,
            "reduced_operator_sha256": reduced_hash,
            "goals": goal_payload,
        }
    )
    return report_hash, payload_hash


def _condensed_recovery_content(
    *,
    condensed_system: AssemblyTimeCondensedSystem,
    provenance_sha256: str,
    catalog_sha256: str,
    trace_geometry_sha256: str,
    ordered_trace_basis_sha256: str,
) -> tuple[str, str, str]:
    numerical_payload = {
        "owned_trace_original_dofs": (condensed_system.owned_trace_original_dofs),
        "original_to_trace": condensed_system.original_to_trace,
        "trace_expansion": (condensed_system.trace_constraints.expansion_by_original),
        "owned_active_rows": (condensed_system.trace_constraints.owned_active_rows),
        "cell_recovery_maps": tuple(
            {
                "interior_original_dofs": cell.interior_original_dofs,
                "trace_original_dofs": cell.trace_original_dofs,
                "cell_local_dofs": cell.cell_local_dofs,
                "raw_key": cell.raw_key,
                "class_key": cell.class_key,
                "cell_permutation": int(cell.cell_permutation),
                "interior_policy": cell.interior_policy,
            }
            for cell in condensed_system.cell_recovery_maps
        ),
        "interior_from_trace_by_class": (condensed_system.interior_from_trace_by_class),
        "interior_lu_by_class": condensed_system.interior_lu_by_class,
        "interior_rhs_projection_by_class": (
            condensed_system.interior_rhs_projection_by_class
        ),
        "interior_solution_embedding_by_class": (
            condensed_system.interior_solution_embedding_by_class
        ),
        "dual_interior_from_trace_by_class": (
            condensed_system.dual_interior_from_trace_by_class
        ),
        "appended_dual_interior_by_cell": (
            condensed_system.appended_dual_interior_by_cell
        ),
        "appended_dual_rows_registered": (
            condensed_system.appended_dual_rows_registered
        ),
        "interior_residual_projection_by_class": (
            condensed_system.interior_residual_projection_by_class
        ),
        "dimensions": {
            "full_rows": int(condensed_system.full_rows),
            "trace_rows": int(condensed_system.trace_rows),
            "active_rows": int(condensed_system.active_rows),
            "appended_rows": int(condensed_system.appended_rows),
            "interior_rows": int(condensed_system.interior_rows),
            "active_interior_rows": int(condensed_system.active_interior_rows),
        },
    }
    _assert_finite_tree(
        numerical_payload,
        label="generalized recovery numerical payload",
    )
    try:
        _row_offsets, _columns, matrix_values = condensed_system.matrix.getValuesCSR()
    except Exception as exc:
        raise RuntimeError(
            "generalized recovery matrix lacks inspectable local CSR content"
        ) from exc
    if not np.all(np.isfinite(np.asarray(matrix_values))):
        raise FloatingPointError("generalized recovery matrix contains NaN or Inf")
    operator_identity = dtn_reduced_operator_identity(condensed_system)
    reduced_hash = _sha256(
        str(operator_identity["content_sha256"]),
        label="reduced-operator content hash",
    )
    expansion_hash = _trace_expansion_sha256(condensed_system)
    recovery_hash = _hash(
        {
            "schema": "task035b.capability-generalized-recovery.v2",
            "evidence_class": _CAPABILITY_EVIDENCE,
            "provenance_sha256": _sha256(
                provenance_sha256,
                label="recovery provenance hash",
            ),
            "catalog_sha256": _sha256(
                catalog_sha256,
                label="recovery catalog hash",
            ),
            "trace_geometry_sha256": _sha256(
                trace_geometry_sha256,
                label="recovery trace geometry hash",
            ),
            "ordered_trace_basis_sha256": _sha256(
                ordered_trace_basis_sha256,
                label="recovery ordered trace basis hash",
            ),
            "reduced_operator_sha256": reduced_hash,
            "trace_expansion_sha256": expansion_hash,
            "operator_identity": operator_identity,
            "numerical_payload": numerical_payload,
        }
    )
    return reduced_hash, expansion_hash, recovery_hash


@dataclass(frozen=True)
class LiveFullP6LocalSchurCapture:
    """Immutable, content-bound snapshot of the live local-Schur observer."""

    schur_by_class: Mapping[Hashable, np.ndarray]
    cell_class_keys: Mapping[int, Hashable]
    storage_trace_rows_per_cell: int
    source_commit: str
    mesh_sha256: str
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    provenance_sha256: str
    local_capture_sha256: str
    collective_capture_sha256: str
    communicator_identity: Mapping[str, Any]
    collective_packets: tuple[Mapping[str, Any], ...]
    global_cell_count: int
    evidence_class: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.evidence_class != _CAPABILITY_EVIDENCE:
            raise ValueError("local-Schur evidence must remain capability-only")
        object.__setattr__(self, "source_commit", _source_sha(self.source_commit))
        for field_name in (
            "mesh_sha256",
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "provenance_sha256",
            "local_capture_sha256",
            "collective_capture_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        dimension = int(self.storage_trace_rows_per_cell)
        classes = {
            key: _matrix(
                values,
                shape=(dimension, dimension),
                label=f"live local Schur class {key!r}",
            )
            for key, values in self.schur_by_class.items()
        }
        cells = {int(cell): key for cell, key in self.cell_class_keys.items()}
        object.__setattr__(self, "schur_by_class", MappingProxyType(classes))
        object.__setattr__(self, "cell_class_keys", MappingProxyType(cells))
        recomputed = _local_schur_payload_sha256(
            schur_by_class=classes,
            cell_class_keys=cells,
            storage_trace_rows_per_cell=dimension,
            provenance_sha256=self.provenance_sha256,
        )
        if recomputed != self.local_capture_sha256:
            raise RuntimeError("local-Schur payload hash is stale")
        _validate_stored_collective(
            namespace="local_schur",
            local_payload_sha256=recomputed,
            communicator_identity=self.communicator_identity,
            collective_packets=self.collective_packets,
            collective_capture_sha256=self.collective_capture_sha256,
        )
        object.__setattr__(
            self,
            "communicator_identity",
            _freeze(self.communicator_identity),
        )
        object.__setattr__(
            self,
            "collective_packets",
            tuple(_freeze(item) for item in self.collective_packets),
        )
        object.__setattr__(self, "audit", _freeze(self.audit))


@dataclass(frozen=True)
class LiveFullP6DtnModeCapture:
    """Complete auxiliary-row inventory with projected full-p6 vectors."""

    modes: tuple[ProjectedDtnComplementMode, ...]
    retained_trace_rows: int
    low_dimension: int
    high_dimension: int
    source_commit: str
    mesh_sha256: str
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    provenance_sha256: str
    reduced_operator_sha256: str
    mode_inventory_sha256: str
    projected_payload_sha256: str
    missing_incident_rhs: np.ndarray
    collective_capture_sha256: str
    communicator_identity: Mapping[str, Any]
    collective_packets: tuple[Mapping[str, Any], ...]
    evidence_class: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.evidence_class != _CAPABILITY_EVIDENCE:
            raise ValueError("DtN evidence must remain capability-only")
        object.__setattr__(self, "source_commit", _source_sha(self.source_commit))
        object.__setattr__(
            self,
            "reduced_operator_sha256",
            _sha256(
                self.reduced_operator_sha256,
                label="DtN reduced-operator hash",
            ),
        )
        for field_name in (
            "mesh_sha256",
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "provenance_sha256",
            "mode_inventory_sha256",
            "projected_payload_sha256",
            "collective_capture_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        inventory_hash, payload_hash, missing_incident = _dtn_content(
            modes=self.modes,
            retained_trace_rows=self.retained_trace_rows,
            low_dimension=self.low_dimension,
            high_dimension=self.high_dimension,
            provenance_sha256=self.provenance_sha256,
            reduced_operator_sha256=self.reduced_operator_sha256,
        )
        supplied_missing = _vector(
            self.missing_incident_rhs,
            dimension=self.high_dimension,
            label="DtN missing incident RHS",
        )
        if (
            inventory_hash != self.mode_inventory_sha256
            or payload_hash != self.projected_payload_sha256
            or not np.array_equal(missing_incident, supplied_missing)
        ):
            raise RuntimeError("DtN capability payload hash/content is stale")
        _validate_stored_collective(
            namespace="dtn_modes",
            local_payload_sha256=payload_hash,
            communicator_identity=self.communicator_identity,
            collective_packets=self.collective_packets,
            collective_capture_sha256=self.collective_capture_sha256,
        )
        object.__setattr__(self, "modes", tuple(self.modes))
        object.__setattr__(self, "missing_incident_rhs", missing_incident)
        object.__setattr__(
            self,
            "communicator_identity",
            _freeze(self.communicator_identity),
        )
        object.__setattr__(
            self,
            "collective_packets",
            tuple(_freeze(item) for item in self.collective_packets),
        )
        object.__setattr__(self, "audit", _freeze(self.audit))


@dataclass(frozen=True)
class LiveCompleteMissingRhsCapture:
    """Numerically closed decomposition of the complete projected ``b_H``."""

    complete: ProjectedCondensedDual
    components: Mapping[str, ProjectedCondensedDual]
    provenance_sha256: str
    reduced_operator_sha256: str
    dtn_projected_payload_sha256: str
    complete_rhs_sha256: str
    decomposition_relative_error: float
    closure_tolerance: float
    low_dimension: int
    high_dimension: int
    collective_capture_sha256: str
    communicator_identity: Mapping[str, Any]
    collective_packets: tuple[Mapping[str, Any], ...]
    evidence_class: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.evidence_class != _CAPABILITY_EVIDENCE:
            raise ValueError("complete-RHS evidence must remain capability-only")
        for field_name in (
            "provenance_sha256",
            "reduced_operator_sha256",
            "dtn_projected_payload_sha256",
            "complete_rhs_sha256",
            "collective_capture_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        complete = ProjectedCondensedDual(
            retained=_vector(
                self.complete.retained,
                dimension=self.low_dimension,
                label="complete retained RHS",
            ),
            missing=_vector(
                self.complete.missing,
                dimension=self.high_dimension,
                label="complete missing RHS",
            ),
            audit=MappingProxyType(
                {
                    "schema_version": (
                        "task035b.capability-projected-dual-snapshot.v1"
                    ),
                    "evidence_class": _CAPABILITY_EVIDENCE,
                    "formal_qualification": False,
                }
            ),
        )
        components = {
            name: ProjectedCondensedDual(
                retained=_vector(
                    component.retained,
                    dimension=self.low_dimension,
                    label=f"{name} retained RHS",
                ),
                missing=_vector(
                    component.missing,
                    dimension=self.high_dimension,
                    label=f"{name} missing RHS",
                ),
                audit=MappingProxyType(
                    {
                        "schema_version": (
                            "task035b.capability-projected-dual-snapshot.v1"
                        ),
                        "evidence_class": _CAPABILITY_EVIDENCE,
                        "formal_qualification": False,
                    }
                ),
            )
            for name, component in self.components.items()
        }
        recomputed_hash, recomputed_error = _complete_rhs_content(
            complete=complete,
            components=components,
            low_dimension=self.low_dimension,
            high_dimension=self.high_dimension,
            provenance_sha256=self.provenance_sha256,
            reduced_operator_sha256=self.reduced_operator_sha256,
            dtn_projected_payload_sha256=(self.dtn_projected_payload_sha256),
            closure_tolerance=self.closure_tolerance,
        )
        if (
            recomputed_hash != self.complete_rhs_sha256
            or not np.isfinite(self.closure_tolerance)
            or float(self.closure_tolerance) <= 0.0
            or not np.isfinite(self.decomposition_relative_error)
            or float(self.decomposition_relative_error) != recomputed_error
            or recomputed_error > float(self.closure_tolerance)
        ):
            raise RuntimeError("complete-RHS capability payload hash is stale")
        _validate_stored_collective(
            namespace="complete_rhs",
            local_payload_sha256=recomputed_hash,
            communicator_identity=self.communicator_identity,
            collective_packets=self.collective_packets,
            collective_capture_sha256=self.collective_capture_sha256,
        )
        object.__setattr__(self, "complete", complete)
        object.__setattr__(self, "components", MappingProxyType(components))
        object.__setattr__(
            self,
            "communicator_identity",
            _freeze(self.communicator_identity),
        )
        object.__setattr__(
            self,
            "collective_packets",
            tuple(_freeze(item) for item in self.collective_packets),
        )
        object.__setattr__(self, "audit", _freeze(self.audit))


@dataclass(frozen=True)
class LiveNineFocusGoalCapture:
    """Nine numerical retained adjoints and their raw report identities."""

    goals: tuple[ChannelGoal, ...]
    low_dimension: int
    high_dimension: int
    retained_trace_rows: int
    evidence_class: str
    goal_reports: Mapping[str, Mapping[str, Any]]
    provenance_sha256: str
    reduced_operator_sha256: str
    goal_report_sha256: str
    goal_payload_sha256: str
    collective_capture_sha256: str
    communicator_identity: Mapping[str, Any]
    collective_packets: tuple[Mapping[str, Any], ...]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.evidence_class != _CAPABILITY_EVIDENCE:
            raise ValueError("focus-goal evidence must remain capability-only")
        for field_name in (
            "provenance_sha256",
            "reduced_operator_sha256",
            "goal_report_sha256",
            "goal_payload_sha256",
            "collective_capture_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        frozen_reports = _freeze(self.goal_reports)
        report_hash, payload_hash = _focus_goal_content(
            goals=self.goals,
            goal_reports=frozen_reports,
            low_dimension=self.low_dimension,
            high_dimension=self.high_dimension,
            provenance_sha256=self.provenance_sha256,
            reduced_operator_sha256=self.reduced_operator_sha256,
            communicator_identity=self.communicator_identity,
        )
        if (
            report_hash != self.goal_report_sha256
            or payload_hash != self.goal_payload_sha256
        ):
            raise RuntimeError("focus-goal capability payload hash is stale")
        _validate_stored_collective(
            namespace="focus_goals",
            local_payload_sha256=payload_hash,
            communicator_identity=self.communicator_identity,
            collective_packets=self.collective_packets,
            collective_capture_sha256=self.collective_capture_sha256,
        )
        object.__setattr__(self, "goals", tuple(self.goals))
        object.__setattr__(self, "goal_reports", frozen_reports)
        object.__setattr__(
            self,
            "communicator_identity",
            _freeze(self.communicator_identity),
        )
        object.__setattr__(
            self,
            "collective_packets",
            tuple(_freeze(item) for item in self.collective_packets),
        )
        object.__setattr__(self, "audit", _freeze(self.audit))


@dataclass(frozen=True)
class LiveGeneralizedRecoveryCapture:
    """Live generalized-recovery object and its content identities."""

    condensed_system: AssemblyTimeCondensedSystem
    source_commit: str
    mesh_sha256: str
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    provenance_sha256: str
    reduced_operator_sha256: str
    trace_expansion_sha256: str
    recovery_capture_sha256: str
    collective_capture_sha256: str
    communicator_identity: Mapping[str, Any]
    collective_packets: tuple[Mapping[str, Any], ...]
    evidence_class: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.evidence_class != _CAPABILITY_EVIDENCE:
            raise ValueError("recovery evidence must remain capability-only")
        object.__setattr__(self, "source_commit", _source_sha(self.source_commit))
        for field_name in (
            "mesh_sha256",
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "provenance_sha256",
            "reduced_operator_sha256",
            "trace_expansion_sha256",
            "recovery_capture_sha256",
            "collective_capture_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        reduced_hash, expansion_hash, recovery_hash = _condensed_recovery_content(
            condensed_system=self.condensed_system,
            provenance_sha256=self.provenance_sha256,
            catalog_sha256=self.catalog_sha256,
            trace_geometry_sha256=self.trace_geometry_sha256,
            ordered_trace_basis_sha256=(self.ordered_trace_basis_sha256),
        )
        if (
            reduced_hash != self.reduced_operator_sha256
            or expansion_hash != self.trace_expansion_sha256
            or recovery_hash != self.recovery_capture_sha256
        ):
            raise RuntimeError("generalized recovery payload hash is stale")
        _validate_stored_collective(
            namespace="generalized_recovery",
            local_payload_sha256=recovery_hash,
            communicator_identity=self.communicator_identity,
            collective_packets=self.collective_packets,
            collective_capture_sha256=self.collective_capture_sha256,
        )
        object.__setattr__(
            self,
            "communicator_identity",
            _freeze(self.communicator_identity),
        )
        object.__setattr__(
            self,
            "collective_packets",
            tuple(_freeze(item) for item in self.collective_packets),
        )
        object.__setattr__(self, "audit", _freeze(self.audit))


@dataclass(frozen=True)
class H14LiveCaptureReadiness:
    """Non-throwing completeness report used before formal hook assembly."""

    formal_actual_pde_ready: bool
    typed_capture_contract_complete: bool
    capability_snapshot_complete: bool
    missing_capabilities: tuple[str, ...]
    identity_mismatches: tuple[str, ...]
    component_hashes: Mapping[str, str]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.formal_actual_pde_ready is not False:
            raise ValueError(
                "typed captures cannot establish formal actual-PDE readiness"
            )
        if self.typed_capture_contract_complete is not False:
            raise ValueError(
                "capability snapshots cannot complete the typed formal contract"
            )
        complete = bool(self.capability_snapshot_complete)
        if complete != (not self.missing_capabilities and not self.identity_mismatches):
            raise ValueError("live-capture readiness is internally inconsistent")
        object.__setattr__(
            self,
            "component_hashes",
            MappingProxyType(dict(self.component_hashes)),
        )


@dataclass(frozen=True)
class FormalH14LiveHookBundle:
    """Reserved formal bundle; construction is disabled until hooks exist."""

    discrete_gradient: ActualPhysicalDiscreteGradientAuthority
    action_layout: PhysicalMissingP6ActionLayout
    local_schur: LiveFullP6LocalSchurCapture
    dtn_modes: LiveFullP6DtnModeCapture
    complete_rhs: LiveCompleteMissingRhsCapture
    focus_goals: LiveNineFocusGoalCapture
    recovery: LiveGeneralizedRecoveryCapture
    evidence_class: str
    hook_bundle_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        raise RuntimeError(
            "formal h14 hook bundle is disabled until production assembly, "
            "distributed-matrix, and collective-observer identities exist"
        )


def snapshot_live_full_p6_local_schur_capture(
    *,
    collector: FullP6LocalSchurClassCollector,
    action_layout: PhysicalMissingP6ActionLayout,
    communicator: MPI.Intracomm,
    source_commit: str,
    mesh_sha256: str,
) -> LiveFullP6LocalSchurCapture:
    """Freeze the observer payload and recompute all class/cell identities."""

    dimension = int(collector.storage_trace_rows_per_cell)
    if dimension != 432 or int(action_layout.storage_trace_rows_per_cell) != 432:
        raise RuntimeError(
            "formal h14 requires the qualified 432-row full-p6 cell trace"
        )
    if dimension != int(action_layout.storage_trace_rows_per_cell):
        raise RuntimeError("collector and action-layout trace dimensions differ")
    provenance = _capture_provenance(
        action_layout=action_layout,
        source_commit=source_commit,
        mesh_sha256=mesh_sha256,
    )
    cells = {int(cell): key for cell, key in collector.cell_class_keys.items()}
    expected_cells = {int(cell.local_cell) for cell in action_layout.owned_cells}
    if set(cells) != expected_cells:
        raise RuntimeError("live local-Schur observer does not cover every action cell")
    if set(cells.values()) != set(collector.schur_by_class):
        raise RuntimeError("live local-Schur class inventory is not exact")
    classes = {
        key: _matrix(
            values,
            shape=(dimension, dimension),
            label=f"live local Schur class {key!r}",
        )
        for key, values in collector.schur_by_class.items()
    }
    local_hash = _local_schur_payload_sha256(
        schur_by_class=classes,
        cell_class_keys=cells,
        storage_trace_rows_per_cell=dimension,
        provenance_sha256=provenance["provenance_sha256"],
    )
    communicator_identity, packets, collective_hash = _collective_snapshot(
        communicator,
        namespace="local_schur",
        local_payload_sha256=local_hash,
    )
    cell_counts = tuple(communicator.allgather(len(cells)))
    class_counts = tuple(communicator.allgather(len(classes)))
    global_cell_count = sum(map(int, cell_counts))
    if global_cell_count <= 0 or sum(map(int, class_counts)) <= 0:
        raise RuntimeError("local-Schur collective capability is empty")
    frozen_classes = MappingProxyType(classes)
    frozen_cells = MappingProxyType(cells)
    return LiveFullP6LocalSchurCapture(
        schur_by_class=frozen_classes,
        cell_class_keys=frozen_cells,
        storage_trace_rows_per_cell=dimension,
        source_commit=provenance["source_commit"],
        mesh_sha256=provenance["mesh_sha256"],
        catalog_sha256=provenance["catalog_sha256"],
        trace_geometry_sha256=provenance["trace_geometry_sha256"],
        ordered_trace_basis_sha256=(provenance["ordered_trace_basis_sha256"]),
        provenance_sha256=provenance["provenance_sha256"],
        local_capture_sha256=local_hash,
        collective_capture_sha256=collective_hash,
        communicator_identity=communicator_identity,
        collective_packets=packets,
        global_cell_count=global_cell_count,
        evidence_class=_CAPABILITY_EVIDENCE,
        audit=MappingProxyType(
            {
                "schema_version": ("task035b.capability-local-schur-capture.v2"),
                "status": "content_bound_capability_local_schur_snapshot",
                "pass": True,
                "evidence_class": _CAPABILITY_EVIDENCE,
                "formal_qualification": False,
                "production_assembly_observer_bound": False,
                "capture_source_type": type(collector).__name__,
                "source_commit": provenance["source_commit"],
                "mesh_sha256": provenance["mesh_sha256"],
                "provenance_sha256": provenance["provenance_sha256"],
                "local_cell_count": len(cells),
                "global_cell_count": global_cell_count,
                "local_class_count": len(classes),
                "collective_communicator_content_sha256": (
                    communicator_identity["content_sha256"]
                ),
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def capture_live_full_p6_dtn_modes(
    *,
    modes: Sequence[ProjectedDtnComplementMode],
    action_layout: PhysicalMissingP6ActionLayout,
    reduced_operator_sha256: str,
    source_commit: str,
    mesh_sha256: str,
    communicator: MPI.Intracomm,
) -> LiveFullP6DtnModeCapture:
    """Snapshot finite DtN vectors without promoting caller physical flags."""

    retained = int(action_layout.retained_trace_rows)
    low = int(action_layout.low_dimension)
    high = int(action_layout.high_dimension)
    provenance = _capture_provenance(
        action_layout=action_layout,
        source_commit=source_commit,
        mesh_sha256=mesh_sha256,
    )
    selected = tuple(modes)
    inventory_hash, payload_hash, missing_incident = _dtn_content(
        modes=selected,
        retained_trace_rows=retained,
        low_dimension=low,
        high_dimension=high,
        provenance_sha256=provenance["provenance_sha256"],
        reduced_operator_sha256=reduced_operator_sha256,
    )
    communicator_identity, packets, collective_hash = _collective_snapshot(
        communicator,
        namespace="dtn_modes",
        local_payload_sha256=payload_hash,
    )
    return LiveFullP6DtnModeCapture(
        modes=selected,
        retained_trace_rows=retained,
        low_dimension=low,
        high_dimension=high,
        source_commit=provenance["source_commit"],
        mesh_sha256=provenance["mesh_sha256"],
        catalog_sha256=provenance["catalog_sha256"],
        trace_geometry_sha256=provenance["trace_geometry_sha256"],
        ordered_trace_basis_sha256=(provenance["ordered_trace_basis_sha256"]),
        provenance_sha256=provenance["provenance_sha256"],
        reduced_operator_sha256=reduced_operator_sha256,
        mode_inventory_sha256=inventory_hash,
        projected_payload_sha256=payload_hash,
        missing_incident_rhs=missing_incident,
        collective_capture_sha256=collective_hash,
        communicator_identity=communicator_identity,
        collective_packets=packets,
        evidence_class=_CAPABILITY_EVIDENCE,
        audit=MappingProxyType(
            {
                "schema_version": ("task035b.capability-dtn-mode-capture.v2"),
                "status": "content_bound_capability_dtn_snapshot",
                "pass": True,
                "evidence_class": _CAPABILITY_EVIDENCE,
                "formal_qualification": False,
                "production_dtn_observer_bound": False,
                "mode_count": len(selected),
                "auxiliary_row_count": low - retained,
                "one_mode_per_auxiliary_row": True,
                "caller_live_projection_declarations": [
                    bool(mode.full_p6_component_vectors_projected_live)
                    for mode in selected
                ],
                "caller_physical_condensation_declarations": [
                    bool(mode.physical_condensation_used) for mode in selected
                ],
                "caller_declarations_used_for_formal_qualification": False,
                "source_commit": provenance["source_commit"],
                "mesh_sha256": provenance["mesh_sha256"],
                "provenance_sha256": provenance["provenance_sha256"],
                "collective_communicator_content_sha256": (
                    communicator_identity["content_sha256"]
                ),
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def capture_complete_missing_rhs(
    *,
    complete: ProjectedCondensedDual,
    components: Mapping[str, ProjectedCondensedDual],
    dtn_modes: LiveFullP6DtnModeCapture,
    reduced_operator_sha256: str,
    communicator: MPI.Intracomm,
    tolerance: float = 2.0e-10,
) -> LiveCompleteMissingRhsCapture:
    """Numerically close ``b_H`` while retaining capability-only semantics."""

    if not np.isfinite(tolerance) or float(tolerance) <= 0.0:
        raise ValueError("complete missing-RHS tolerance must be finite positive")
    communicator_identity = mpi_communicator_content_identity(communicator)
    if (
        dtn_modes.communicator_identity.get("content_sha256")
        != communicator_identity["content_sha256"]
    ):
        raise RuntimeError("complete-RHS and DtN communicators differ")
    low = dtn_modes.low_dimension
    high = dtn_modes.high_dimension
    capability_audit = MappingProxyType(
        {
            "schema_version": ("task035b.capability-projected-dual-snapshot.v1"),
            "evidence_class": _CAPABILITY_EVIDENCE,
            "formal_qualification": False,
        }
    )
    complete_copy = ProjectedCondensedDual(
        retained=_vector(
            complete.retained,
            dimension=low,
            label="complete retained RHS",
        ),
        missing=_vector(
            complete.missing,
            dimension=high,
            label="complete missing RHS",
        ),
        audit=capability_audit,
    )
    frozen = {
        name: ProjectedCondensedDual(
            retained=_vector(
                component.retained,
                dimension=low,
                label=f"{name} retained RHS",
            ),
            missing=_vector(
                component.missing,
                dimension=high,
                label=f"{name} missing RHS",
            ),
            audit=capability_audit,
        )
        for name, component in components.items()
    }
    rhs_hash, decomposition_error = _complete_rhs_content(
        complete=complete_copy,
        components=frozen,
        low_dimension=low,
        high_dimension=high,
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=reduced_operator_sha256,
        dtn_projected_payload_sha256=dtn_modes.projected_payload_sha256,
        closure_tolerance=float(tolerance),
    )
    dtn_error = (
        _vector(
            frozen["dtn_incident_auxiliary"].missing,
            dimension=high,
            label="DtN RHS component",
        )
        - dtn_modes.missing_incident_rhs
    )
    if decomposition_error > float(tolerance) or np.linalg.norm(dtn_error) > float(
        tolerance
    ):
        raise RuntimeError("complete projected b_H decomposition does not close")
    reduced_hash = _sha256(
        reduced_operator_sha256,
        label="complete RHS reduced-operator hash",
    )
    communicator_identity, packets, collective_hash = _collective_snapshot(
        communicator,
        namespace="complete_rhs",
        local_payload_sha256=rhs_hash,
    )
    return LiveCompleteMissingRhsCapture(
        complete=complete_copy,
        components=MappingProxyType(frozen),
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=reduced_hash,
        dtn_projected_payload_sha256=(dtn_modes.projected_payload_sha256),
        complete_rhs_sha256=rhs_hash,
        decomposition_relative_error=decomposition_error,
        closure_tolerance=float(tolerance),
        low_dimension=low,
        high_dimension=high,
        collective_capture_sha256=collective_hash,
        communicator_identity=communicator_identity,
        collective_packets=packets,
        evidence_class=_CAPABILITY_EVIDENCE,
        audit=MappingProxyType(
            {
                "schema_version": (
                    "task035b.capability-complete-missing-rhs-capture.v2"
                ),
                "status": "numerically_closed_capability_b_H_snapshot",
                "pass": True,
                "evidence_class": _CAPABILITY_EVIDENCE,
                "formal_qualification": False,
                "production_projection_observer_bound": False,
                "required_component_count": len(_RHS_COMPONENTS),
                "provenance_sha256": dtn_modes.provenance_sha256,
                "decomposition_relative_error": decomposition_error,
                "dtn_incident_component_recomputed": True,
                "caller_projection_audits_used_for_qualification": False,
                "collective_communicator_content_sha256": (
                    communicator_identity["content_sha256"]
                ),
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def capture_live_nine_focus_goals(
    *,
    bundle: ActualFocusChannelGoalBundle,
    goal_reports: Mapping[str, Mapping[str, Any]],
    dtn_modes: LiveFullP6DtnModeCapture,
    reduced_operator_sha256: str,
    communicator: MPI.Intracomm,
) -> LiveNineFocusGoalCapture:
    """Snapshot nine finite adjoints without promoting caller declarations."""

    goals = tuple(bundle.goals)
    low = dtn_modes.low_dimension
    high = dtn_modes.high_dimension
    retained = dtn_modes.retained_trace_rows
    if set(goal_reports) != set(_FOCUS):
        raise RuntimeError("focus-goal report set is not exactly nine reports")
    communicator_identity = mpi_communicator_content_identity(communicator)
    if (
        dtn_modes.communicator_identity.get("content_sha256")
        != communicator_identity["content_sha256"]
    ):
        raise RuntimeError("focus-goal and DtN communicators differ")
    mode_identity_by_auxiliary = {
        mode.auxiliary_global_index: mode.mode_identity for mode in dtn_modes.modes
    }
    for label, (_component, side, order, _quantity) in _FOCUS.items():
        report = goal_reports[label]
        mode_identity = mode_identity_by_auxiliary.get(
            _exact_integer(report.get("augmented_global_index"))
        )
        if (
            not isinstance(mode_identity, Mapping)
            or mode_identity.get("side") != side
            or _exact_integer(mode_identity.get("m")) != order
            or _exact_integer(mode_identity.get("n")) != 0
            or mode_identity.get("polarization") != "s"
        ):
            raise RuntimeError(f"{label} DtN auxiliary identity differs")
    reduced_hash = _sha256(
        reduced_operator_sha256,
        label="focus-goal reduced-operator hash",
    )
    frozen_reports = _freeze(goal_reports)
    report_hash, payload_hash = _focus_goal_content(
        goals=goals,
        goal_reports=frozen_reports,
        low_dimension=low,
        high_dimension=high,
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=reduced_hash,
        communicator_identity=communicator_identity,
    )
    communicator_identity, packets, collective_hash = _collective_snapshot(
        communicator,
        namespace="focus_goals",
        local_payload_sha256=payload_hash,
    )
    return LiveNineFocusGoalCapture(
        goals=goals,
        low_dimension=low,
        high_dimension=high,
        retained_trace_rows=retained,
        evidence_class=_CAPABILITY_EVIDENCE,
        goal_reports=frozen_reports,
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=reduced_hash,
        goal_report_sha256=report_hash,
        goal_payload_sha256=payload_hash,
        collective_capture_sha256=collective_hash,
        communicator_identity=communicator_identity,
        collective_packets=packets,
        audit=MappingProxyType(
            {
                "schema_version": ("task035b.capability-nine-focus-goal-capture.v2"),
                "status": "nine_content_bound_capability_goals_captured",
                "pass": True,
                "goal_count": len(goals),
                "evidence_class": _CAPABILITY_EVIDENCE,
                "formal_qualification": False,
                "production_live_adjoint_observer_bound": False,
                "provenance_sha256": dtn_modes.provenance_sha256,
                "adjoint_residual_gate": 1.0e-9,
                "raw_report_pass_boolean_used": False,
                "caller_actual_pde_declarations_used_for_qualification": (False),
                "collective_communicator_content_sha256": (
                    communicator_identity["content_sha256"]
                ),
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def _trace_expansion_sha256(
    condensed: AssemblyTimeCondensedSystem,
) -> str:
    constraints = condensed.trace_constraints
    return _hash(
        {
            "schema": "task035b.live-generalized-trace-expansion.v1",
            "full_trace_rows": int(constraints.full_trace_rows),
            "active_rows": int(constraints.active_rows),
            "owned_active_rows": constraints.owned_active_rows,
            "expansion_by_original": {
                str(original): {
                    "rows": rows,
                    "coefficients": coefficients,
                }
                for original, (rows, coefficients) in sorted(
                    constraints.expansion_by_original.items()
                )
            },
        }
    )


def capture_live_generalized_recovery(
    *,
    condensed_system: AssemblyTimeCondensedSystem,
    action_layout: PhysicalMissingP6ActionLayout,
    source_commit: str,
    mesh_sha256: str,
) -> LiveGeneralizedRecoveryCapture:
    """Bind generalized recovery maps to source, mesh, and trace identities."""

    provenance = _capture_provenance(
        action_layout=action_layout,
        source_commit=source_commit,
        mesh_sha256=mesh_sha256,
    )
    constraints = condensed_system.trace_constraints
    qualification = constraints.build_audit.get("caller_qualification")
    if not isinstance(qualification, Mapping):
        raise RuntimeError("generalized recovery lacks caller qualification")
    required_identity = {
        "catalog_sha256": action_layout.catalog_sha256,
        "trace_geometry_sha256": action_layout.trace_geometry_sha256,
        "ordered_trace_basis_sha256": (action_layout.ordered_trace_basis_sha256),
    }
    if any(
        qualification.get(name) != expected
        for name, expected in required_identity.items()
    ):
        raise RuntimeError(
            "generalized recovery identity differs from the action layout"
        )
    if (
        constraints.active_coordinates_are_original_trace_dofs
        or constraints.build_audit.get("complete_storage_trace_pullback") is not True
        or constraints.build_audit.get("post_recovery_mpc_backsubstitution_forbidden")
        is not True
        or constraints.build_audit.get("inactive_mode_rows_allocated") is not False
        or constraints.build_audit.get("full_trace_matrix_allocated") is not False
    ):
        raise RuntimeError("generalized recovery pullback is incomplete")
    if (
        int(condensed_system.active_rows) != int(action_layout.retained_trace_rows)
        or int(condensed_system.appended_rows)
        != int(action_layout.low_dimension - action_layout.retained_trace_rows)
        or tuple(map(int, condensed_system.matrix.getSize()))
        != (action_layout.low_dimension, action_layout.low_dimension)
        or int(constraints.full_trace_rows)
        != len(action_layout.storage_dual_projections)
    ):
        raise RuntimeError(
            "generalized recovery dimensions differ from the live low system"
        )
    policy = validate_primal_recovery_mpc_backsubstitution(
        condensed_system,
        requested=False,
    )
    if (
        policy.get("caller_expansion_already_contains_complete_pullback") is not True
        or policy.get("mpc_backsubstitution_permitted") is not False
    ):
        raise RuntimeError("generalized recovery permits duplicate pullback")
    communicator = condensed_system.matrix.getComm().tompi4py()
    reduced_hash, expansion_hash, recovery_hash = _condensed_recovery_content(
        condensed_system=condensed_system,
        provenance_sha256=provenance["provenance_sha256"],
        catalog_sha256=action_layout.catalog_sha256,
        trace_geometry_sha256=action_layout.trace_geometry_sha256,
        ordered_trace_basis_sha256=(action_layout.ordered_trace_basis_sha256),
    )
    operator_identity = dtn_reduced_operator_identity(condensed_system)
    global_cell_count = int(
        communicator.allreduce(
            int(operator_identity["cell_recovery_map_count"]),
            op=MPI.SUM,
        )
    )
    global_class_array_count = int(
        communicator.allreduce(
            int(operator_identity["class_array_count"]),
            op=MPI.SUM,
        )
    )
    if global_cell_count <= 0 or global_class_array_count <= 0:
        raise RuntimeError(
            "generalized recovery lacks live cell/Aii projection content"
        )
    source = provenance["source_commit"]
    mesh_hash = provenance["mesh_sha256"]
    communicator_identity, packets, collective_hash = _collective_snapshot(
        communicator,
        namespace="generalized_recovery",
        local_payload_sha256=recovery_hash,
    )
    return LiveGeneralizedRecoveryCapture(
        condensed_system=condensed_system,
        source_commit=source,
        mesh_sha256=mesh_hash,
        catalog_sha256=action_layout.catalog_sha256,
        trace_geometry_sha256=action_layout.trace_geometry_sha256,
        ordered_trace_basis_sha256=(action_layout.ordered_trace_basis_sha256),
        provenance_sha256=provenance["provenance_sha256"],
        reduced_operator_sha256=reduced_hash,
        trace_expansion_sha256=expansion_hash,
        recovery_capture_sha256=recovery_hash,
        collective_capture_sha256=collective_hash,
        communicator_identity=communicator_identity,
        collective_packets=packets,
        evidence_class=_CAPABILITY_EVIDENCE,
        audit=MappingProxyType(
            {
                "schema_version": (
                    "task035b.capability-generalized-recovery-capture.v2"
                ),
                "status": "content_bound_capability_recovery_snapshot",
                "pass": True,
                "evidence_class": _CAPABILITY_EVIDENCE,
                "formal_qualification": False,
                "production_assembly_run_identity_bound": False,
                "distributed_reduced_matrix_content_identity_bound": False,
                "source_commit": source,
                "mesh_sha256": mesh_hash,
                "provenance_sha256": provenance["provenance_sha256"],
                "global_cell_recovery_map_count": global_cell_count,
                "global_class_array_count": global_class_array_count,
                "complete_storage_trace_pullback": True,
                "duplicate_mpc_backsubstitution_forbidden": True,
                "all_recovery_operator_arrays_finite": True,
                "collective_communicator_content_sha256": (
                    communicator_identity["content_sha256"]
                ),
                "full_recovered_true_residual_completed": False,
                "candidate_PDE_resolve_required": True,
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def assess_formal_h14_live_capture_readiness(
    *,
    discrete_gradient: ActualPhysicalDiscreteGradientAuthority | None = None,
    action_layout: PhysicalMissingP6ActionLayout | None = None,
    local_schur: LiveFullP6LocalSchurCapture | None = None,
    dtn_modes: LiveFullP6DtnModeCapture | None = None,
    complete_rhs: LiveCompleteMissingRhsCapture | None = None,
    focus_goals: LiveNineFocusGoalCapture | None = None,
    recovery: LiveGeneralizedRecoveryCapture | None = None,
    communicator: MPI.Intracomm | None = None,
) -> H14LiveCaptureReadiness:
    """Validate capability snapshots; never promote them to formal evidence."""

    supplied = {
        "actual_discrete_gradient": (
            discrete_gradient,
            ActualPhysicalDiscreteGradientAuthority,
        ),
        "physical_action_layout": (
            action_layout,
            PhysicalMissingP6ActionLayout,
        ),
        "live_local_schur": (
            local_schur,
            LiveFullP6LocalSchurCapture,
        ),
        "full_p6_dtn_modes": (
            dtn_modes,
            LiveFullP6DtnModeCapture,
        ),
        "complete_b_H": (
            complete_rhs,
            LiveCompleteMissingRhsCapture,
        ),
        "nine_focus_goals": (
            focus_goals,
            LiveNineFocusGoalCapture,
        ),
        "generalized_recovery": (
            recovery,
            LiveGeneralizedRecoveryCapture,
        ),
    }
    wrong_types = tuple(
        name
        for name, (value, expected) in supplied.items()
        if value is not None and not isinstance(value, expected)
    )
    if "actual_discrete_gradient" in wrong_types:
        discrete_gradient = None
    if "physical_action_layout" in wrong_types:
        action_layout = None
    if "live_local_schur" in wrong_types:
        local_schur = None
    if "full_p6_dtn_modes" in wrong_types:
        dtn_modes = None
    if "complete_b_H" in wrong_types:
        complete_rhs = None
    if "nine_focus_goals" in wrong_types:
        focus_goals = None
    if "generalized_recovery" in wrong_types:
        recovery = None
    components = {
        "actual_discrete_gradient": discrete_gradient,
        "physical_action_layout": action_layout,
        "live_local_schur": local_schur,
        "full_p6_dtn_modes": dtn_modes,
        "complete_b_H": complete_rhs,
        "nine_focus_goals": focus_goals,
        "generalized_recovery": recovery,
    }
    missing_list = [name for name, value in components.items() if value is None]
    if communicator is None:
        missing_list.append("collective_validation_communicator")
    missing = tuple(missing_list)
    mismatches: list[str] = [f"{name}_wrong_type" for name in wrong_types]
    hashes: dict[str, str] = {}
    if discrete_gradient is not None:
        try:
            _assert_finite_tree(
                discrete_gradient,
                label="discrete-gradient capability",
            )
            hashes["actual_discrete_gradient"] = _hash(
                {
                    "schema": ("task035b.capability-discrete-gradient-snapshot.v1"),
                    "payload": discrete_gradient,
                }
            )
        except (TypeError, ValueError, FloatingPointError):
            hashes["actual_discrete_gradient"] = ""
            mismatches.append("discrete_gradient_payload_invalid")
        if (
            discrete_gradient.audit.get("pass") is not True
            or discrete_gradient.audit.get("authority_sha256")
            != discrete_gradient.authority_sha256
            or discrete_gradient.audit.get("interpolation_matrix_sha256")
            != discrete_gradient.interpolation_matrix_sha256
            or discrete_gradient.audit.get("discrete_gradient_matrix_sha256")
            != discrete_gradient.discrete_gradient_matrix_sha256
        ):
            mismatches.append("discrete_gradient_capability_identity_mismatch")
    if action_layout is not None:
        try:
            _assert_finite_tree(
                action_layout,
                label="physical-action capability",
            )
            hashes["physical_action_layout"] = _hash(
                {
                    "schema": ("task035b.capability-action-layout-snapshot.v1"),
                    "payload": action_layout,
                }
            )
        except (TypeError, ValueError, FloatingPointError):
            hashes["physical_action_layout"] = ""
            mismatches.append("physical_action_layout_payload_invalid")
        if (
            action_layout.audit.get("pass") is not True
            or action_layout.audit.get("full_p6_trace_matrix_materialized") is not False
            or action_layout.audit.get("inactive_missing_p6_rows_allocated") != 0
            or action_layout.storage_trace_rows_per_cell != 432
            or action_layout.retained_trace_rows <= 0
            or action_layout.low_dimension <= action_layout.retained_trace_rows
            or action_layout.high_dimension <= 0
            or any(
                len(cell.storage_original_dofs) != 432
                for cell in action_layout.owned_cells
            )
        ):
            mismatches.append("physical_action_layout_capability_invalid")
    if local_schur is not None:
        try:
            local_hash = _local_schur_payload_sha256(
                schur_by_class=local_schur.schur_by_class,
                cell_class_keys=local_schur.cell_class_keys,
                storage_trace_rows_per_cell=(local_schur.storage_trace_rows_per_cell),
                provenance_sha256=local_schur.provenance_sha256,
            )
        except (TypeError, ValueError, RuntimeError, FloatingPointError):
            local_hash = ""
        hashes["live_local_schur"] = local_hash
        if (
            local_hash != local_schur.local_capture_sha256
            or local_schur.storage_trace_rows_per_cell != 432
            or local_schur.global_cell_count <= 0
            or local_schur.audit.get("full_p6_trace_matrix_materialized") is not False
            or local_schur.audit.get("inactive_missing_p6_rows_allocated") != 0
        ):
            mismatches.append("local_schur_capability_payload_invalid")
    if dtn_modes is not None:
        try:
            _inventory_hash, dtn_hash, recomputed_incident = _dtn_content(
                modes=dtn_modes.modes,
                retained_trace_rows=dtn_modes.retained_trace_rows,
                low_dimension=dtn_modes.low_dimension,
                high_dimension=dtn_modes.high_dimension,
                provenance_sha256=dtn_modes.provenance_sha256,
                reduced_operator_sha256=dtn_modes.reduced_operator_sha256,
            )
        except (TypeError, ValueError, RuntimeError, FloatingPointError):
            dtn_hash = ""
            recomputed_incident = np.empty(0, dtype=np.complex128)
        hashes["full_p6_dtn_modes"] = dtn_hash
        if dtn_hash != dtn_modes.projected_payload_sha256 or not np.array_equal(
            recomputed_incident,
            dtn_modes.missing_incident_rhs,
        ):
            mismatches.append("dtn_capability_payload_invalid")
    if complete_rhs is not None:
        try:
            rhs_hash, rhs_error = _complete_rhs_content(
                complete=complete_rhs.complete,
                components=complete_rhs.components,
                low_dimension=complete_rhs.low_dimension,
                high_dimension=complete_rhs.high_dimension,
                provenance_sha256=complete_rhs.provenance_sha256,
                reduced_operator_sha256=(complete_rhs.reduced_operator_sha256),
                dtn_projected_payload_sha256=(
                    complete_rhs.dtn_projected_payload_sha256
                ),
                closure_tolerance=complete_rhs.closure_tolerance,
            )
        except (TypeError, ValueError, RuntimeError, FloatingPointError):
            rhs_hash = ""
            rhs_error = float("inf")
        hashes["complete_b_H"] = rhs_hash
        if (
            rhs_hash != complete_rhs.complete_rhs_sha256
            or rhs_error != complete_rhs.decomposition_relative_error
        ):
            mismatches.append("complete_rhs_capability_payload_invalid")
    if focus_goals is not None:
        try:
            report_hash, goal_hash = _focus_goal_content(
                goals=focus_goals.goals,
                goal_reports=focus_goals.goal_reports,
                low_dimension=focus_goals.low_dimension,
                high_dimension=focus_goals.high_dimension,
                provenance_sha256=focus_goals.provenance_sha256,
                reduced_operator_sha256=(focus_goals.reduced_operator_sha256),
                communicator_identity=(focus_goals.communicator_identity),
            )
        except (TypeError, ValueError, RuntimeError, FloatingPointError):
            report_hash = ""
            goal_hash = ""
        hashes["nine_focus_goals"] = goal_hash
        if (
            report_hash != focus_goals.goal_report_sha256
            or goal_hash != focus_goals.goal_payload_sha256
        ):
            mismatches.append("focus_goal_capability_payload_invalid")
    if recovery is not None:
        try:
            (
                current_operator_hash,
                current_expansion_hash,
                current_recovery_hash,
            ) = _condensed_recovery_content(
                condensed_system=recovery.condensed_system,
                provenance_sha256=recovery.provenance_sha256,
                catalog_sha256=recovery.catalog_sha256,
                trace_geometry_sha256=recovery.trace_geometry_sha256,
                ordered_trace_basis_sha256=(recovery.ordered_trace_basis_sha256),
            )
        except Exception:
            current_operator_hash = ""
            current_expansion_hash = ""
            current_recovery_hash = ""
        hashes["generalized_recovery"] = current_recovery_hash
        if (
            recovery.audit.get("complete_storage_trace_pullback") is not True
            or recovery.audit.get("duplicate_mpc_backsubstitution_forbidden")
            is not True
            or recovery.audit.get(
                "global_cell_recovery_map_count",
                0,
            )
            <= 0
            or recovery.audit.get("global_class_array_count", 0) <= 0
            or recovery.audit.get("full_p6_trace_matrix_materialized") is not False
            or recovery.audit.get("inactive_missing_p6_rows_allocated") != 0
            or current_operator_hash != recovery.reduced_operator_sha256
            or current_expansion_hash != recovery.trace_expansion_sha256
            or current_recovery_hash != recovery.recovery_capture_sha256
        ):
            mismatches.append("generalized_recovery_capability_payload_invalid")

    if communicator is not None:
        ordered_presence = tuple(
            name for name, value in components.items() if value is not None
        )
        presence_packets = tuple(communicator.allgather(ordered_presence))
        collective_presence_consistent = len(set(presence_packets)) == 1
        if not collective_presence_consistent:
            mismatches.append("rank_component_presence_mismatch")
        else:
            collective_components = (
                (
                    "local_schur",
                    local_schur,
                    hashes.get("live_local_schur", ""),
                ),
                (
                    "dtn_modes",
                    dtn_modes,
                    hashes.get("full_p6_dtn_modes", ""),
                ),
                (
                    "complete_rhs",
                    complete_rhs,
                    hashes.get("complete_b_H", ""),
                ),
                (
                    "focus_goals",
                    focus_goals,
                    hashes.get("nine_focus_goals", ""),
                ),
                (
                    "generalized_recovery",
                    recovery,
                    hashes.get("generalized_recovery", ""),
                ),
            )
            for name, capture, local_hash in collective_components:
                if capture is None:
                    continue
                local_hash_valid = bool(_SHA256.fullmatch(local_hash))
                validity = tuple(communicator.allgather(local_hash_valid))
                if not all(validity):
                    mismatches.append(f"{name}_rank_payload_invalid")
                    continue
                (
                    current_communicator,
                    current_packets,
                    current_collective_hash,
                ) = _collective_snapshot(
                    communicator,
                    namespace=name,
                    local_payload_sha256=local_hash,
                )
                if (
                    dict(capture.communicator_identity) != dict(current_communicator)
                    or tuple(dict(packet) for packet in capture.collective_packets)
                    != tuple(dict(packet) for packet in current_packets)
                    or capture.collective_capture_sha256 != current_collective_hash
                ):
                    mismatches.append(f"{name}_communicator_or_collective_mismatch")
                if (
                    capture.evidence_class != _CAPABILITY_EVIDENCE
                    or capture.audit.get("formal_qualification") is not False
                ):
                    mismatches.append(f"{name}_evidence_not_capability_only")

    if discrete_gradient is not None and action_layout is not None:
        for name in (
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
        ):
            if getattr(discrete_gradient, name) != getattr(
                action_layout,
                name,
            ):
                mismatches.append(f"gradient_action_{name}_mismatch")
        expected_high = sum(
            1 if orbit.entity_kind == "edge" else 20
            for orbit in discrete_gradient.orbit_evidence
        )
        if expected_high != action_layout.high_dimension:
            mismatches.append("gradient_action_high_dimension_mismatch")
    if action_layout is not None and local_schur is not None:
        if (
            local_schur.storage_trace_rows_per_cell
            != action_layout.storage_trace_rows_per_cell
        ):
            mismatches.append("local_schur_trace_dimension_mismatch")
    if action_layout is not None and dtn_modes is not None:
        if (
            dtn_modes.retained_trace_rows != action_layout.retained_trace_rows
            or dtn_modes.low_dimension != action_layout.low_dimension
            or dtn_modes.high_dimension != action_layout.high_dimension
        ):
            mismatches.append("dtn_action_dimensions_mismatch")
    if dtn_modes is not None and complete_rhs is not None:
        if (
            complete_rhs.dtn_projected_payload_sha256
            != dtn_modes.projected_payload_sha256
            or complete_rhs.reduced_operator_sha256 != dtn_modes.reduced_operator_sha256
        ):
            mismatches.append("complete_rhs_dtn_identity_mismatch")
    if dtn_modes is not None and focus_goals is not None:
        if (
            focus_goals.low_dimension != dtn_modes.low_dimension
            or focus_goals.high_dimension != dtn_modes.high_dimension
            or focus_goals.retained_trace_rows != dtn_modes.retained_trace_rows
            or focus_goals.reduced_operator_sha256 != dtn_modes.reduced_operator_sha256
        ):
            mismatches.append("focus_goal_dtn_identity_mismatch")
    provenance_captures = {
        name: capture.provenance_sha256
        for name, capture in (
            ("local_schur", local_schur),
            ("dtn", dtn_modes),
            ("rhs", complete_rhs),
            ("goals", focus_goals),
            ("recovery", recovery),
        )
        if capture is not None
    }
    if len(set(provenance_captures.values())) > 1:
        mismatches.append("live_capture_provenance_mismatch")
    if recovery is not None:
        for capture_name, capture in (
            ("dtn", dtn_modes),
            ("rhs", complete_rhs),
            ("goals", focus_goals),
        ):
            if (
                capture is not None
                and capture.reduced_operator_sha256 != recovery.reduced_operator_sha256
            ):
                mismatches.append(f"{capture_name}_recovery_operator_mismatch")
        if action_layout is not None:
            expected_provenance = _capture_provenance(
                action_layout=action_layout,
                source_commit=recovery.source_commit,
                mesh_sha256=recovery.mesh_sha256,
            )
            if recovery.provenance_sha256 != expected_provenance["provenance_sha256"]:
                mismatches.append("recovery_provenance_content_mismatch")
            for name in (
                "catalog_sha256",
                "trace_geometry_sha256",
                "ordered_trace_basis_sha256",
            ):
                if getattr(recovery, name) != getattr(action_layout, name):
                    mismatches.append(f"recovery_action_{name}_mismatch")
    if recovery is not None and local_schur is not None:
        if (
            local_schur.source_commit != recovery.source_commit
            or local_schur.mesh_sha256 != recovery.mesh_sha256
            or local_schur.catalog_sha256 != recovery.catalog_sha256
            or local_schur.trace_geometry_sha256 != recovery.trace_geometry_sha256
            or local_schur.ordered_trace_basis_sha256
            != recovery.ordered_trace_basis_sha256
        ):
            mismatches.append("local_schur_recovery_provenance_mismatch")
    if recovery is not None and dtn_modes is not None:
        if (
            dtn_modes.source_commit != recovery.source_commit
            or dtn_modes.mesh_sha256 != recovery.mesh_sha256
            or dtn_modes.catalog_sha256 != recovery.catalog_sha256
            or dtn_modes.trace_geometry_sha256 != recovery.trace_geometry_sha256
            or dtn_modes.ordered_trace_basis_sha256
            != recovery.ordered_trace_basis_sha256
        ):
            mismatches.append("dtn_recovery_provenance_mismatch")

    unique_mismatches = tuple(dict.fromkeys(mismatches))
    capability_complete = not missing and not unique_mismatches
    ready = False
    return H14LiveCaptureReadiness(
        formal_actual_pde_ready=ready,
        typed_capture_contract_complete=False,
        capability_snapshot_complete=capability_complete,
        missing_capabilities=missing,
        identity_mismatches=unique_mismatches,
        component_hashes=hashes,
        audit=MappingProxyType(
            {
                "schema_version": ("task035b.formal-h14-capability-readiness.v2"),
                "status": (
                    "capability_snapshot_complete_formal_hooks_missing"
                    if capability_complete
                    else "capability_snapshot_incomplete"
                ),
                "formal_actual_pde_ready": ready,
                "typed_capture_contract_complete": False,
                "capability_snapshot_complete": capability_complete,
                "evidence_class": _CAPABILITY_EVIDENCE,
                "production_hooks_missing": list(_PRODUCTION_HOOKS_MISSING),
                "missing_capabilities": list(missing),
                "identity_mismatches": list(unique_mismatches),
                "caller_readiness_booleans_used_for_formal_qualification": (False),
                "formal_candidate_passed": False,
                "candidate_PDE_resolve_required": True,
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def build_formal_h14_live_hook_bundle(
    *,
    discrete_gradient: ActualPhysicalDiscreteGradientAuthority | None = None,
    action_layout: PhysicalMissingP6ActionLayout | None = None,
    local_schur: LiveFullP6LocalSchurCapture | None = None,
    dtn_modes: LiveFullP6DtnModeCapture | None = None,
    complete_rhs: LiveCompleteMissingRhsCapture | None = None,
    focus_goals: LiveNineFocusGoalCapture | None = None,
    recovery: LiveGeneralizedRecoveryCapture | None = None,
    communicator: MPI.Intracomm | None = None,
) -> FormalH14LiveHookBundle:
    """Fail closed until the missing production identities are implemented."""

    readiness = assess_formal_h14_live_capture_readiness(
        discrete_gradient=discrete_gradient,
        action_layout=action_layout,
        local_schur=local_schur,
        dtn_modes=dtn_modes,
        complete_rhs=complete_rhs,
        focus_goals=focus_goals,
        recovery=recovery,
        communicator=communicator,
    )
    raise RuntimeError(
        "formal h14 bundle remains fail-closed: "
        f"typed_capture_contract_complete="
        f"{readiness.typed_capture_contract_complete}, "
        f"missing={readiness.missing_capabilities}, "
        f"mismatches={readiness.identity_mismatches}, "
        f"production_hooks_missing={_PRODUCTION_HOOKS_MISSING}"
    )


__all__ = [
    "FormalH14LiveHookBundle",
    "H14LiveCaptureReadiness",
    "LiveCompleteMissingRhsCapture",
    "LiveFullP6DtnModeCapture",
    "LiveFullP6LocalSchurCapture",
    "LiveGeneralizedRecoveryCapture",
    "LiveNineFocusGoalCapture",
    "assess_formal_h14_live_capture_readiness",
    "build_formal_h14_live_hook_bundle",
    "capture_complete_missing_rhs",
    "capture_live_full_p6_dtn_modes",
    "capture_live_generalized_recovery",
    "capture_live_nine_focus_goals",
    "snapshot_live_full_p6_local_schur_capture",
]
