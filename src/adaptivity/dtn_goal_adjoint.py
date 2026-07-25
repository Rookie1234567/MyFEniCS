"""Actual complex discrete adjoints for Stage-4 DtN power goals.

The Stage-4 auxiliary DtN formulation stores each finite-port modal
projection as an algebraic unknown.  This module differentiates the official
modal ``R00_total``/``R_total``/``T_total`` definitions with respect to those unknowns and
solves ``A^H z = g`` without assembling a second matrix: a complex Hermitian
solve is obtained from the existing direct factorization by conjugating a
``KSPSolveTranspose``.  The ordinary solver path is unchanged; callers reach
this code only through the explicit solution-observer research hook.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..common.modes_3d import incident_power_3d
from ..solvers.dtn_port_3d import (
    _gather_auxiliary_values,
    _mode_boundary_phase,
    _mode_carries_outward_power,
    _mode_power_at_boundary,
)


TINY = np.finfo(float).tiny
SUPPORTED_GOALS = ("R00_total", "R_total", "T_total")
SUPPORTED_CHANNEL_QUANTITIES = (
    "power",
    "amplitude_real",
    "amplitude_imag",
)


@dataclass(frozen=True)
class DtnChannelGoal:
    """One real-valued functional of a single canonical DtN port channel.

    A complex amplitude is deliberately represented by two independent real
    functionals.  This avoids treating a complex quantity as though it had one
    real adjoint and makes the Hermitian-gradient convention explicit.
    """

    side: str
    m: int
    n: int
    polarization: str
    quantity: str

    def __post_init__(self) -> None:
        if self.side not in {"top", "bottom"}:
            raise ValueError("DtN channel side must be 'top' or 'bottom'")
        if self.quantity not in SUPPORTED_CHANNEL_QUANTITIES:
            raise ValueError(
                f"unsupported DtN channel quantity: {self.quantity!r}"
            )
        if not self.polarization:
            raise ValueError("DtN channel polarization must be non-empty")

    @property
    def label(self) -> str:
        prefix = "R" if self.side == "top" else "T"
        order = f"{prefix}_m{int(self.m)}_n{int(self.n)}_{self.polarization}"
        return f"{order}_{self.quantity}"

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "label": self.label}


def task035b_failed_channel_goals() -> tuple[DtnChannelGoal, ...]:
    """Return the independent Review-V1 failed-channel recovery goals."""

    power = tuple(
        DtnChannelGoal(side, m, 0, "s", "power")
        for side in ("top", "bottom")
        for m in (-2, -4, -5)
    )
    complex_amplitudes = (
        ("top", -4),
        ("top", -5),
        ("bottom", -2),
        ("bottom", -4),
        ("bottom", -5),
    )
    components = tuple(
        DtnChannelGoal(side, m, 0, "s", quantity)
        for side, m in complex_amplitudes
        for quantity in ("amplitude_real", "amplitude_imag")
    )
    return power + components


def _relative_difference(left: float, right: float) -> float:
    return float(abs(left - right) / max(abs(left), abs(right), 1.0e-14))


def _owned_adjoint_content_sha256(
    values: np.ndarray,
    *,
    rank: int,
    ownership_start: int,
    ownership_end: int,
) -> str:
    canonical = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    if canonical.shape != (int(ownership_end) - int(ownership_start),):
        raise ValueError("owned adjoint values differ from their PETSc range")
    digest = hashlib.sha256()
    digest.update(b"task035b.petsc-adjoint-owned-content.v1\0")
    digest.update(
        np.asarray(
            [rank, ownership_start, ownership_end],
            dtype=np.dtype("<i8"),
        ).tobytes()
    )
    digest.update(canonical.tobytes())
    return digest.hexdigest()


def _global_adjoint_value_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    if canonical.ndim != 1:
        raise ValueError("global adjoint values must be a vector")
    digest = hashlib.sha256()
    digest.update(b"task035b.global-adjoint-value-content.v1\0")
    digest.update(
        np.asarray([len(canonical)], dtype=np.dtype("<i8")).tobytes()
    )
    digest.update(canonical.tobytes())
    return digest.hexdigest()


def _communicator_content_identity_from_world_ranks(
    world_ranks: Sequence[int],
) -> dict[str, Any]:
    members = [int(rank) for rank in world_ranks]
    if len(set(members)) != len(members):
        raise RuntimeError("MPI communicator world-rank members are duplicated")
    payload = {
        "schema_version": "task035b.mpi-communicator-content.v1",
        "size": len(members),
        "ordered_world_ranks": members,
    }
    return {
        **payload,
        "content_sha256": hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
    }


def mpi_communicator_content_identity(
    communicator: MPI.Intracomm,
) -> dict[str, Any]:
    """Return a deterministic identity for communicator membership/order."""

    return _communicator_content_identity_from_world_ranks(
        communicator.allgather(int(MPI.COMM_WORLD.rank))
    )


def _adjoint_partition_content_identity(
    *,
    global_size: int,
    packets: Sequence[Mapping[str, Any]],
    global_value_sha256: str,
) -> dict[str, Any]:
    ordered = tuple(sorted(packets, key=lambda packet: int(packet["rank"])))
    if tuple(int(packet["rank"]) for packet in ordered) != tuple(
        range(len(ordered))
    ):
        raise RuntimeError("adjoint partition ranks are not contiguous")
    cursor = 0
    normalized: list[dict[str, Any]] = []
    for packet in ordered:
        start = int(packet["ownership_start"])
        end = int(packet["ownership_end"])
        content_hash = str(packet["owned_content_sha256"]).lower()
        if (
            start != cursor
            or end < start
            or len(content_hash) != 64
        ):
            raise RuntimeError("adjoint PETSc ownership partition is invalid")
        try:
            bytes.fromhex(content_hash)
        except ValueError as exc:
            raise RuntimeError(
                "adjoint owned-content hash is not hexadecimal"
            ) from exc
        normalized.append(
            {
                "rank": int(packet["rank"]),
                "world_rank": int(packet["world_rank"]),
                "ownership_start": start,
                "ownership_end": end,
                "owned_value_count": end - start,
                "owned_content_sha256": content_hash,
            }
        )
        cursor = end
    if cursor != int(global_size):
        raise RuntimeError("adjoint ownership does not cover the global vector")
    communicator_identity = _communicator_content_identity_from_world_ranks(
        [packet["world_rank"] for packet in normalized]
    )
    value_hash = str(global_value_sha256).lower()
    try:
        value_hash_valid = (
            len(value_hash) == 64 and len(bytes.fromhex(value_hash)) == 32
        )
    except ValueError:
        value_hash_valid = False
    if not value_hash_valid:
        raise RuntimeError("global adjoint value hash is invalid")
    payload = {
        "schema_version": (
            "task035b.petsc-adjoint-partition-content.v1"
        ),
        "global_size": int(global_size),
        "scalar_dtype": "complex128",
        "mpi_size": len(normalized),
        "communicator_content_sha256": communicator_identity[
            "content_sha256"
        ],
        "communicator_ordered_world_ranks": communicator_identity[
            "ordered_world_ranks"
        ],
        "global_value_sha256": value_hash,
        "partitions": normalized,
    }
    global_hash = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        **payload,
        "global_content_sha256": global_hash,
    }


def petsc_adjoint_partition_content_identity(
    adjoint: PETSc.Vec,
) -> dict[str, Any]:
    """Hash the live adjoint values and the exact PETSc MPI ownership."""

    communicator = adjoint.getComm().tompi4py()
    start, end = map(int, adjoint.getOwnershipRange())
    owned = np.asarray(
        adjoint.getArray(readonly=True),
        dtype=np.complex128,
    )
    packet = {
        "rank": int(communicator.rank),
        "world_rank": int(MPI.COMM_WORLD.rank),
        "ownership_start": start,
        "ownership_end": end,
        "owned_content_sha256": _owned_adjoint_content_sha256(
            owned,
            rank=communicator.rank,
            ownership_start=start,
            ownership_end=end,
        ),
    }
    local_bytes = np.ascontiguousarray(
        owned,
        dtype=np.dtype("<c16"),
    ).tobytes()
    gathered_bytes = communicator.gather(local_bytes, root=0)
    if communicator.rank == 0:
        global_values = np.frombuffer(
            b"".join(gathered_bytes),
            dtype=np.dtype("<c16"),
        )
        global_value_hash = _global_adjoint_value_sha256(global_values)
    else:
        global_value_hash = None
    global_value_hash = communicator.bcast(global_value_hash, root=0)
    return _adjoint_partition_content_identity(
        global_size=int(adjoint.getSize()),
        packets=communicator.allgather(packet),
        global_value_sha256=global_value_hash,
    )


def replicated_adjoint_partition_content_identity(
    values: np.ndarray,
    reported_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Rehash a replicated adjoint with a report's PETSc ownership ranges."""

    replicated = np.asarray(values, dtype=np.complex128)
    if replicated.ndim != 1 or not np.all(np.isfinite(replicated)):
        raise ValueError("replicated retained adjoint must be a finite vector")
    partitions = reported_identity.get("partitions")
    if not isinstance(partitions, Sequence) or isinstance(
        partitions,
        (str, bytes),
    ):
        raise ValueError("adjoint content identity lacks PETSc partitions")
    packets: list[dict[str, Any]] = []
    for raw in partitions:
        if not isinstance(raw, Mapping):
            raise ValueError("adjoint partition record must be a mapping")
        rank = int(raw["rank"])
        world_rank = int(raw["world_rank"])
        start = int(raw["ownership_start"])
        end = int(raw["ownership_end"])
        if start < 0 or end < start or end > len(replicated):
            raise ValueError("adjoint ownership range is out of bounds")
        packets.append(
            {
                "rank": rank,
                "world_rank": world_rank,
                "ownership_start": start,
                "ownership_end": end,
                "owned_content_sha256": _owned_adjoint_content_sha256(
                    replicated[start:end],
                    rank=rank,
                    ownership_start=start,
                    ownership_end=end,
                ),
            }
        )
    return _adjoint_partition_content_identity(
        global_size=len(replicated),
        packets=packets,
        global_value_sha256=_global_adjoint_value_sha256(replicated),
    )


def _linear_residual(
    matrix: PETSc.Mat,
    right_hand_side: PETSc.Vec,
    solution: PETSc.Vec,
    *,
    hermitian: bool = False,
) -> dict[str, float]:
    residual = right_hand_side.duplicate()
    if hermitian:
        matrix.multHermitian(solution, residual)
    else:
        matrix.mult(solution, residual)
    residual.axpy(PETSc.ScalarType(-1.0), right_hand_side)
    rhs_norm = float(right_hand_side.norm())
    residual_norm = float(residual.norm())
    residual.destroy()
    return {
        "rhs_norm": rhs_norm,
        "residual_norm": residual_norm,
        "relative_residual": residual_norm / max(rhs_norm, TINY),
    }


def _normalized_goal_weights(config, modes, goal: str) -> np.ndarray:
    if goal not in SUPPORTED_GOALS:
        raise ValueError(f"unsupported DtN power goal: {goal!r}")
    side = "bottom" if goal == "T_total" else "top"
    incident_power = float(incident_power_3d(config))
    weights = np.zeros(len(modes), dtype=np.float64)
    for index, mode in enumerate(modes):
        if (
            mode.side != side
            or not _mode_carries_outward_power(mode)
            or (
                goal == "R00_total"
                and (int(mode.m) != 0 or int(mode.n) != 0)
            )
        ):
            continue
        weights[index] = float(
            _mode_power_at_boundary(mode, config, 1.0 + 0.0j)
            / incident_power
        )
    if np.any(weights < -1.0e-14) or not np.all(np.isfinite(weights)):
        raise RuntimeError("DtN power goal produced invalid modal weights.")
    return np.maximum(weights, 0.0)


def dtn_power_goal_value(
    config,
    modes,
    auxiliary_values: np.ndarray,
    incident_projections,
    *,
    goal: str,
) -> float:
    selected_modes = list(modes)
    auxiliary = np.asarray(auxiliary_values, dtype=np.complex128)
    incident = np.asarray(incident_projections, dtype=np.complex128)
    if len(selected_modes) != len(auxiliary) or auxiliary.shape != incident.shape:
        raise ValueError("DtN goal arrays are not shape-compatible")
    outgoing = auxiliary.copy()
    for index, mode in enumerate(selected_modes):
        if mode.side == "top":
            outgoing[index] -= incident[index]
    weights = _normalized_goal_weights(config, selected_modes, goal)
    return float(np.sum(weights * np.abs(outgoing) ** 2))


def _channel_mode_index(modes, goal: DtnChannelGoal) -> int:
    matches = [
        index
        for index, mode in enumerate(modes)
        if (
            mode.side == goal.side
            and int(mode.m) == int(goal.m)
            and int(mode.n) == int(goal.n)
            and mode.polarization == goal.polarization
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            "DtN channel goal must resolve to exactly one auxiliary mode: "
            f"{goal.as_dict()}, matches={matches}"
        )
    return int(matches[0])


def _outgoing_channel_amplitude(
    mode,
    auxiliary_value: complex,
    incident_projection: complex,
) -> complex:
    return complex(
        auxiliary_value - incident_projection
        if mode.side == "top"
        else auxiliary_value
    )


def _goal_context_auxiliary_coordinate_scales(
    goal_context: dict[str, Any],
) -> np.ndarray:
    """Map global-z modal coefficients into the solved auxiliary coordinates."""

    modes = list(goal_context["modes"])
    raw = goal_context.get("auxiliary_coordinate_scales")
    if raw is None:
        return np.ones(len(modes), dtype=np.complex128)
    scales = np.asarray(raw, dtype=np.complex128)
    if scales.shape != (len(modes),):
        raise ValueError(
            "DtN auxiliary-coordinate scales do not match the mode count"
        )
    if not np.all(np.isfinite(scales)) or np.any(np.abs(scales) <= 0.0):
        raise ValueError("DtN auxiliary-coordinate scales are invalid")
    return scales


def _global_auxiliary_from_solver_coordinates(
    solver_values: np.ndarray,
    goal_context: dict[str, Any],
) -> np.ndarray:
    values = np.asarray(solver_values, dtype=np.complex128)
    scales = _goal_context_auxiliary_coordinate_scales(goal_context)
    if values.shape != scales.shape:
        raise ValueError(
            "DtN solver-coordinate values do not match the mode count"
        )
    return values / scales


def dtn_channel_goal_value(
    config,
    modes,
    auxiliary_values: np.ndarray,
    incident_projections,
    *,
    goal: DtnChannelGoal,
) -> float:
    """Evaluate one Review-V1 single-channel real functional."""

    selected_modes = list(modes)
    auxiliary = np.asarray(auxiliary_values, dtype=np.complex128)
    incident = np.asarray(incident_projections, dtype=np.complex128)
    if (
        len(selected_modes) != len(auxiliary)
        or auxiliary.shape != incident.shape
    ):
        raise ValueError("DtN channel goal arrays are not shape-compatible")
    index = _channel_mode_index(selected_modes, goal)
    mode = selected_modes[index]
    outgoing = _outgoing_channel_amplitude(
        mode,
        auxiliary[index],
        incident[index],
    )
    if goal.quantity == "power":
        incident_power = float(incident_power_3d(config))
        return float(
            _mode_power_at_boundary(mode, config, outgoing)
            / incident_power
        )
    boundary_amplitude = outgoing * _mode_boundary_phase(mode, config)
    if goal.quantity == "amplitude_real":
        return float(boundary_amplitude.real)
    if goal.quantity == "amplitude_imag":
        return float(boundary_amplitude.imag)
    raise AssertionError("validated DtN channel goal became unsupported")


def build_dtn_channel_goal_gradient(
    state: PETSc.Vec,
    config,
    goal_context: dict[str, Any],
    *,
    goal: DtnChannelGoal,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Build ``g`` for one channel with ``dJ(x)[dx] = Re(g^H dx)``."""

    modes = list(goal_context["modes"])
    auxiliary = np.asarray(
        goal_context["auxiliary_values"], dtype=np.complex128
    )
    incident = np.asarray(
        goal_context["incident_projections"], dtype=np.complex128
    )
    coordinate_scales = _goal_context_auxiliary_coordinate_scales(
        goal_context
    )
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    if auxiliary.shape != incident.shape or len(modes) != len(auxiliary):
        raise ValueError("DtN channel goal context arrays are not compatible")
    if state.getSize() != n_fe + len(auxiliary):
        raise ValueError(
            "DtN channel goal context does not match the augmented system"
        )
    mode_index = _channel_mode_index(modes, goal)
    mode = modes[mode_index]
    outgoing = _outgoing_channel_amplitude(
        mode,
        auxiliary[mode_index],
        incident[mode_index],
    )
    boundary_phase = _mode_boundary_phase(mode, config)
    if goal.quantity == "power":
        weight = float(
            _mode_power_at_boundary(mode, config, 1.0 + 0.0j)
            / incident_power_3d(config)
        )
        derivative = 2.0 * weight * outgoing
        convention = "g_aux=2*w*outgoing_amplitude"
    elif goal.quantity == "amplitude_real":
        weight = None
        derivative = np.conj(boundary_phase)
        convention = "g_aux=conj(boundary_phase)"
    elif goal.quantity == "amplitude_imag":
        weight = None
        derivative = 1j * np.conj(boundary_phase)
        convention = "g_aux=i*conj(boundary_phase)"
    else:  # pragma: no cover - protected by DtnChannelGoal validation.
        raise AssertionError("validated DtN channel goal became unsupported")
    derivative /= np.conj(coordinate_scales[mode_index])

    gradient = state.duplicate()
    gradient.set(PETSc.ScalarType(0.0))
    global_index = int(n_fe + mode_index)
    row_start, row_end = gradient.getOwnershipRange()
    if row_start <= global_index < row_end:
        gradient.setValue(
            global_index,
            PETSc.ScalarType(derivative),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    gradient.assemble()
    functional_value = dtn_channel_goal_value(
        config,
        modes,
        auxiliary,
        incident,
        goal=goal,
    )
    return gradient, {
        "goal": goal.as_dict(),
        "goal_value": functional_value,
        "auxiliary_mode_index": mode_index,
        "augmented_global_index": global_index,
        "outgoing_amplitude": [
            float(outgoing.real),
            float(outgoing.imag),
        ],
        "boundary_phase": [
            float(boundary_phase.real),
            float(boundary_phase.imag),
        ],
        "power_weight": weight,
        "gradient_norm": float(gradient.norm()),
        "gradient_convention": f"dJ=Re(g^H dx), {convention}",
        "auxiliary_coordinate_scale": [
            float(coordinate_scales[mode_index].real),
            float(coordinate_scales[mode_index].imag),
        ],
        "canonical_channel_identity": {
            "side": mode.side,
            "m": int(mode.m),
            "n": int(mode.n),
            "polarization": mode.polarization,
        },
    }


def build_dtn_power_goal_gradient(
    state: PETSc.Vec,
    config,
    goal_context: dict[str, Any],
    *,
    goal: str,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Build ``g`` such that ``dJ(x)[dx] = Re(g^H dx)``."""

    modes = list(goal_context["modes"])
    auxiliary = np.asarray(
        goal_context["auxiliary_values"], dtype=np.complex128
    )
    incident = np.asarray(
        goal_context["incident_projections"], dtype=np.complex128
    )
    coordinate_scales = _goal_context_auxiliary_coordinate_scales(
        goal_context
    )
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    if auxiliary.shape != incident.shape or len(modes) != len(auxiliary):
        raise ValueError("DtN goal context arrays are not shape-compatible.")
    if state.getSize() != n_fe + len(auxiliary):
        raise ValueError("DtN goal context does not match the augmented system.")

    weights = _normalized_goal_weights(config, modes, goal)
    outgoing = auxiliary.copy()
    for index, mode in enumerate(modes):
        if mode.side == "top":
            outgoing[index] -= incident[index]
    auxiliary_gradient = (
        2.0 * weights * outgoing / np.conj(coordinate_scales)
    )

    gradient = state.duplicate()
    gradient.set(PETSc.ScalarType(0.0))
    row_start, row_end = gradient.getOwnershipRange()
    indices = np.arange(n_fe, n_fe + len(auxiliary), dtype=np.int64)
    owned = (indices >= row_start) & (indices < row_end)
    if np.any(owned):
        gradient.setValues(
            np.asarray(indices[owned], dtype=PETSc.IntType),
            np.asarray(auxiliary_gradient[owned], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    gradient.assemble()
    goal_value = float(np.sum(weights * np.abs(outgoing) ** 2))
    return gradient, {
        "goal": goal,
        "goal_value_from_quadratic_form": goal_value,
        "active_modal_count": int(np.count_nonzero(weights > 0.0)),
        "modal_weight_sum": float(np.sum(weights)),
        "gradient_norm": float(gradient.norm()),
        "gradient_convention": "dJ=Re(g^H dx), g_aux=2*w*outgoing_amplitude",
    }


def _normalized_rhs_direction(
    right_hand_side: PETSc.Vec,
) -> PETSc.Vec:
    direction = right_hand_side.copy()
    rhs_norm = float(direction.norm())
    if rhs_norm <= TINY:
        raise ValueError("cannot verify an adjoint with a zero right-hand side")
    direction.scale(PETSc.ScalarType(1.0 / rhs_norm))
    values = direction.getArray()
    row_start, row_end = direction.getOwnershipRange()
    indices = np.arange(row_start, row_end, dtype=np.float64)
    probe = (
        np.cos(0.173 * (indices + 1.0))
        + 1j * np.sin(0.311 * (indices + 1.0))
    ) / math.sqrt(max(direction.getSize(), 1))
    values[:] += PETSc.ScalarType(0.05) * probe
    direction_norm = float(direction.norm())
    direction.scale(PETSc.ScalarType(1.0 / max(direction_norm, TINY)))
    return direction


def solve_hermitian_discrete_adjoint(
    matrix: PETSc.Mat,
    solver: PETSc.KSP,
    goal_gradient: PETSc.Vec,
    *,
    template: PETSc.Vec,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Reuse a complex direct factor to solve ``A^H z = g``."""

    if not np.issubdtype(PETSc.ScalarType, np.complexfloating):
        raise RuntimeError("the discrete adjoint requires complex PETSc scalars")
    if matrix.getSize()[0] != template.getSize():
        raise ValueError("matrix and adjoint template sizes do not match")
    conjugated_gradient = goal_gradient.copy()
    conjugated_gradient.getArray()[:] = np.conj(
        goal_gradient.getArray(readonly=True)
    )
    transpose_solution = template.duplicate()
    solver.solveTranspose(conjugated_gradient, transpose_solution)
    transpose_reason = int(solver.getConvergedReason())
    adjoint = transpose_solution.copy()
    adjoint.getArray()[:] = np.conj(
        transpose_solution.getArray(readonly=True)
    )
    residual = _linear_residual(
        matrix, goal_gradient, adjoint, hermitian=True
    )
    conjugated_gradient.destroy()
    transpose_solution.destroy()
    return adjoint, {
        "transpose_converged_reason": transpose_reason,
        "adjoint_residual": residual,
        "complex_adjoint_equation": "A^H z = g",
        "adjoint_solve_method": (
            "z=conj(KSPSolveTranspose(conj(g))); reuse_forward_direct_factor"
        ),
        "forward_factor_reused": True,
    }


def verify_hermitian_discrete_adjoint(
    matrix: PETSc.Mat,
    right_hand_side: PETSc.Vec,
    state: PETSc.Vec,
    solver: PETSc.KSP,
    goal_gradient: PETSc.Vec,
    goal_evaluator: Callable[[PETSc.Vec], float],
    *,
    finite_difference_relative_step: float = 1.0e-5,
    adjoint_observer: Callable[[PETSc.Vec], None] | None = None,
) -> dict[str, Any]:
    """Solve and independently verify a real functional's complex adjoint."""

    if matrix.getSize()[0] != state.getSize():
        raise ValueError("matrix and state sizes do not match")
    adjoint, solve_report = solve_hermitian_discrete_adjoint(
        matrix, solver, goal_gradient, template=state
    )
    direction = _normalized_rhs_direction(right_hand_side)
    rhs_norm = float(right_hand_side.norm())
    step = float(finite_difference_relative_step) * rhs_norm
    rhs_minus = right_hand_side.copy()
    rhs_plus = right_hand_side.copy()
    rhs_minus.axpy(PETSc.ScalarType(-step), direction)
    rhs_plus.axpy(PETSc.ScalarType(step), direction)
    state_minus = state.duplicate()
    state_plus = state.duplicate()
    solver.solve(rhs_minus, state_minus)
    minus_reason = int(solver.getConvergedReason())
    solver.solve(rhs_plus, state_plus)
    plus_reason = int(solver.getConvergedReason())
    minus_residual = _linear_residual(matrix, rhs_minus, state_minus)
    plus_residual = _linear_residual(matrix, rhs_plus, state_plus)

    goal_minus = float(goal_evaluator(state_minus))
    goal_plus = float(goal_evaluator(state_plus))
    finite_difference = (goal_plus - goal_minus) / (2.0 * step)
    central_difference_tangent = state_plus.copy()
    central_difference_tangent.axpy(
        PETSc.ScalarType(-1.0),
        state_minus,
    )
    central_difference_tangent.scale(
        PETSc.ScalarType(1.0 / (2.0 * step))
    )
    direct_tangent = state.duplicate()
    solver.solve(direction, direct_tangent)
    direct_tangent_reason = int(solver.getConvergedReason())
    direct_tangent_residual = _linear_residual(
        matrix,
        direction,
        direct_tangent,
    )
    central_difference_tangent_derivative = float(
        np.real(goal_gradient.dot(central_difference_tangent))
    )
    direct_derivative = float(
        np.real(goal_gradient.dot(direct_tangent))
    )
    adjoint_derivative = float(np.real(adjoint.dot(direction)))
    direct_adjoint_relative_error = _relative_difference(
        direct_derivative, adjoint_derivative
    )
    finite_difference_relative_error = _relative_difference(
        finite_difference, adjoint_derivative
    )
    direct_adjoint_absolute_error = abs(
        direct_derivative - adjoint_derivative
    )
    finite_difference_absolute_error = abs(
        finite_difference - adjoint_derivative
    )
    gradient_scale = max(float(goal_gradient.norm()), 1.0)
    direct_adjoint_absolute_tolerance = 1.0e-12 * gradient_scale
    finite_difference_absolute_tolerance = 5.0e-11 * gradient_scale
    direct_adjoint_closure_pass = bool(
        direct_adjoint_relative_error <= 1.0e-8
        or direct_adjoint_absolute_error
        <= direct_adjoint_absolute_tolerance
    )
    finite_difference_closure_pass = bool(
        finite_difference_relative_error <= 1.0e-7
        or finite_difference_absolute_error
        <= finite_difference_absolute_tolerance
    )

    passed = bool(
        solve_report["transpose_converged_reason"] > 0
        and minus_reason > 0
        and plus_reason > 0
        and solve_report["adjoint_residual"]["relative_residual"]
        <= 1.0e-9
        and minus_residual["relative_residual"] <= 1.0e-9
        and plus_residual["relative_residual"] <= 1.0e-9
        and direct_tangent_reason > 0
        and direct_tangent_residual["relative_residual"] <= 1.0e-9
        and direct_adjoint_closure_pass
        and finite_difference_closure_pass
    )
    report = {
        "pass": passed,
        "actual_discrete_system": True,
        **solve_report,
        "matrix_rows": int(matrix.getSize()[0]),
        "mpi_size": int(matrix.getComm().getSize()),
        "minus_converged_reason": minus_reason,
        "plus_converged_reason": plus_reason,
        "minus_primal_residual": minus_residual,
        "plus_primal_residual": plus_residual,
        "direct_tangent_converged_reason": direct_tangent_reason,
        "direct_tangent_residual": direct_tangent_residual,
        "finite_difference_relative_step": float(
            finite_difference_relative_step
        ),
        "finite_difference_absolute_step": step,
        "goal_minus": goal_minus,
        "goal_plus": goal_plus,
        "derivative_direct_tangent": direct_derivative,
        "derivative_central_difference_tangent": (
            central_difference_tangent_derivative
        ),
        "derivative_adjoint": adjoint_derivative,
        "derivative_finite_difference": finite_difference,
        "direct_adjoint_relative_error": direct_adjoint_relative_error,
        "direct_adjoint_absolute_error": (
            direct_adjoint_absolute_error
        ),
        "direct_adjoint_absolute_tolerance": (
            direct_adjoint_absolute_tolerance
        ),
        "direct_adjoint_closure_pass": direct_adjoint_closure_pass,
        "finite_difference_relative_error": finite_difference_relative_error,
        "finite_difference_absolute_error": (
            finite_difference_absolute_error
        ),
        "finite_difference_absolute_tolerance": (
            finite_difference_absolute_tolerance
        ),
        "finite_difference_closure_pass": (
            finite_difference_closure_pass
        ),
    }
    adjoint_content = petsc_adjoint_partition_content_identity(adjoint)
    report["adjoint_content_identity"] = adjoint_content
    report["adjoint_content_sha256"] = adjoint_content[
        "global_value_sha256"
    ]
    report["adjoint_partition_content_sha256"] = adjoint_content[
        "global_content_sha256"
    ]
    if adjoint_observer is not None:
        adjoint_observer(adjoint)
    for vector in (
        adjoint,
        direction,
        rhs_minus,
        rhs_plus,
        state_minus,
        state_plus,
        central_difference_tangent,
        direct_tangent,
    ):
        vector.destroy()
    return report


def evaluate_actual_dtn_power_adjoints(
    *,
    linear_system: dict[str, Any],
    dtn_result: dict[str, Any],
    config,
    communicator: MPI.Intracomm,
    official_summary: dict[str, Any],
    goals: tuple[str, ...] = SUPPORTED_GOALS,
    adjoint_observer: Callable[[str, PETSc.Vec], None] | None = None,
) -> dict[str, Any]:
    """Evaluate actual discrete adjoints while forward objects are alive."""

    goal_context = dtn_result.get("goal_context")
    if not isinstance(goal_context, dict):
        raise RuntimeError("the solved DtN system did not retain goal context")
    matrix = linear_system["A"]
    right_hand_side = linear_system["b"]
    state = linear_system["x"]
    solver = linear_system["ksp"]
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    n_aux = len(goal_context["modes"])

    goal_reports: dict[str, Any] = {}
    for goal in goals:
        gradient, metadata = build_dtn_power_goal_gradient(
            state, config, goal_context, goal=goal
        )

        def evaluate(candidate: PETSc.Vec, selected_goal: str = goal) -> float:
            auxiliary = _global_auxiliary_from_solver_coordinates(
                _gather_auxiliary_values(
                    candidate,
                    n_fe,
                    n_aux,
                    communicator,
                ),
                goal_context,
            )
            return dtn_power_goal_value(
                config,
                goal_context["modes"],
                auxiliary,
                goal_context["incident_projections"],
                goal=selected_goal,
            )

        verification = verify_hermitian_discrete_adjoint(
            matrix,
            right_hand_side,
            state,
            solver,
            gradient,
            evaluate,
            adjoint_observer=(
                None
                if adjoint_observer is None
                else lambda vector, selected_goal=goal: adjoint_observer(
                    selected_goal, vector
                )
            ),
        )
        official_value = float(official_summary[goal])
        functional_value = float(metadata["goal_value_from_quadratic_form"])
        official_closure = abs(functional_value - official_value)
        goal_reports[goal] = {
            **metadata,
            **verification,
            "official_summary_value": official_value,
            "official_functional_absolute_closure": official_closure,
            "pass": bool(
                verification["pass"]
                and official_closure
                <= 1.0e-11 * max(abs(official_value), 1.0)
            ),
        }
        gradient.destroy()

    passed = all(report["pass"] for report in goal_reports.values())
    return {
        "schema_version": "task035.actual-dtn-discrete-adjoint.v1",
        "status": (
            "actual_discrete_dtn_adjoint_pass"
            if passed
            else "actual_discrete_dtn_adjoint_fail"
        ),
        "pass": passed,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "official_goals": list(goals),
        "complex_conjugation": "Hermitian A^H, never plain transpose",
        "normalization": goal_context["normalization"],
        "field_gather": False,
        "auxiliary_scalar_gather_only": True,
        "goals": goal_reports,
    }


def evaluate_actual_dtn_channel_adjoints(
    *,
    linear_system: dict[str, Any],
    dtn_result: dict[str, Any],
    config,
    communicator: MPI.Intracomm,
    goals: tuple[DtnChannelGoal, ...] | None = None,
    adjoint_observer: (
        Callable[[DtnChannelGoal, PETSc.Vec], None] | None
    ) = None,
) -> dict[str, Any]:
    """Solve and verify independent Review-V1 diffraction-channel adjoints."""

    selected_goals = (
        task035b_failed_channel_goals() if goals is None else tuple(goals)
    )
    if not selected_goals:
        raise ValueError("at least one DtN channel goal is required")
    if len({goal.label for goal in selected_goals}) != len(selected_goals):
        raise ValueError("DtN channel adjoint labels must be unique")
    goal_context = dtn_result.get("goal_context")
    if not isinstance(goal_context, dict):
        raise RuntimeError("the solved DtN system did not retain goal context")
    matrix = linear_system.get("A")
    right_hand_side = linear_system.get("b")
    state = linear_system.get("x")
    solver = linear_system.get("ksp")
    if any(
        value is None
        for value in (matrix, right_hand_side, state, solver)
    ):
        raise RuntimeError(
            "channel adjoints require live matrix/vector/direct-factor objects"
        )
    n_fe = int(goal_context["num_fem_dofs_after_mpc"])
    n_aux = len(goal_context["modes"])

    reports: dict[str, Any] = {}
    for goal in selected_goals:
        gradient, metadata = build_dtn_channel_goal_gradient(
            state,
            config,
            goal_context,
            goal=goal,
        )

        def evaluate(
            candidate: PETSc.Vec,
            selected_goal: DtnChannelGoal = goal,
        ) -> float:
            auxiliary = _global_auxiliary_from_solver_coordinates(
                _gather_auxiliary_values(
                    candidate,
                    n_fe,
                    n_aux,
                    communicator,
                ),
                goal_context,
            )
            return dtn_channel_goal_value(
                config,
                goal_context["modes"],
                auxiliary,
                goal_context["incident_projections"],
                goal=selected_goal,
            )

        verification = verify_hermitian_discrete_adjoint(
            matrix,
            right_hand_side,
            state,
            solver,
            gradient,
            evaluate,
            adjoint_observer=(
                None
                if adjoint_observer is None
                else lambda vector, selected_goal=goal: adjoint_observer(
                    selected_goal,
                    vector,
                )
            ),
        )
        reports[goal.label] = {
            **metadata,
            **verification,
            "pass": bool(verification["pass"]),
        }
        gradient.destroy()

    passed = all(report["pass"] for report in reports.values())
    power_count = sum(
        goal.quantity == "power" for goal in selected_goals
    )
    component_count = len(selected_goals) - power_count
    return {
        "schema_version": "task035b.actual-dtn-channel-adjoint.v1",
        "status": (
            "actual_dtn_channel_adjoint_pass"
            if passed
            else "actual_dtn_channel_adjoint_fail"
        ),
        "pass": passed,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "goal_count": len(selected_goals),
        "independent_power_goal_count": int(power_count),
        "independent_complex_amplitude_component_goal_count": int(
            component_count
        ),
        "complex_amplitude_semantics": (
            "each complex channel uses independent real and imaginary "
            "real-valued Hermitian adjoints"
        ),
        "complex_conjugation": "Hermitian A^H, never plain transpose",
        "normalization": goal_context["normalization"],
        "field_gather": False,
        "auxiliary_scalar_gather_only": True,
        "goals": reports,
    }


def run_target_actual_dtn_adjoint(
    out_dir: Path,
    *,
    degree: int = 2,
    h_nm: float = 50.0,
    polarization_kind: str = "s",
    mesh_cell_type: str = "tetrahedron",
    progress_observer=None,
    mesh_data_override=None,
) -> dict[str, Any]:
    """Run one low-cost Task034 target solve and its actual R/T adjoints."""

    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, Any] = {}

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    def observer(**state) -> None:
        progress("actual_dtn_discrete_adjoint", "begin")
        captured["adjoint"] = evaluate_actual_dtn_power_adjoints(
            linear_system=state["linear_system"],
            dtn_result=state["dtn_result"],
            config=state["config"],
            communicator=state["field"].function_space.mesh.comm,
            official_summary=state["summary"],
        )
        progress("actual_dtn_discrete_adjoint", "end")

    base = target_stage4_config(degree=int(degree), h_nm=float(h_nm))
    config = replace(
        base,
        case_name=f"task035_actual_dtn_adjoint_p{degree}_h{h_nm:g}".replace(
            ".", "p"
        ),
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type=mesh_cell_type,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        unique_output=False,
    )
    progress("actual_dtn_primal_solve", "begin")
    summary = run_stage4b_block_grating_3d_case(
        config,
        out_dir / "primal",
        solution_observer=observer,
        mesh_data_override=mesh_data_override,
    )
    progress("actual_dtn_primal_solve", "end")
    residual = summary.get("linear_system_relative_residual")
    prerequisites = bool(
        summary.get("official_result") is True
        and summary.get("case_status") == "completed"
        and isinstance(residual, (int, float))
        and float(residual) <= 1.0e-9
        and "adjoint" in captured
    )
    adjoint = captured.get("adjoint") or {
        "status": "actual_discrete_dtn_adjoint_not_run",
        "pass": False,
    }
    passed = prerequisites and adjoint["pass"]
    return {
        "schema_version": "task035.target-actual-dtn-adjoint.v1",
        "status": (
            "target_actual_dtn_adjoint_pass"
            if passed
            else "target_actual_dtn_adjoint_fail"
        ),
        "pass": passed,
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": f"boundary-fitted conforming {mesh_cell_type}",
            "degree": int(degree),
            "h_nm": float(h_nm),
        },
        "primal_prerequisites_pass": prerequisites,
        "primal_summary": summary,
        "adjoint": adjoint,
    }


__all__ = [
    "DtnChannelGoal",
    "SUPPORTED_GOALS",
    "SUPPORTED_CHANNEL_QUANTITIES",
    "build_dtn_channel_goal_gradient",
    "build_dtn_power_goal_gradient",
    "dtn_channel_goal_value",
    "dtn_power_goal_value",
    "evaluate_actual_dtn_channel_adjoints",
    "evaluate_actual_dtn_power_adjoints",
    "mpi_communicator_content_identity",
    "petsc_adjoint_partition_content_identity",
    "replicated_adjoint_partition_content_identity",
    "run_target_actual_dtn_adjoint",
    "solve_hermitian_discrete_adjoint",
    "task035b_failed_channel_goals",
    "verify_hermitian_discrete_adjoint",
]
