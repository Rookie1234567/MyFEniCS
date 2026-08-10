"""Streaming full-field recovery for a condensed Hybrid local block."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import (
    HybridInternalModeCoupling,
    _ReusableInterfaceSurfaceLoad,
    _ReusableModeTractionEvaluator,
)
from .dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _gather_auxiliary_values,
    _traction_vector,
)
from .hybrid_local_dtn import HybridLocalDtnSystem


@dataclass(frozen=True)
class HybridStaticRecoveredLocalField:
    """Physical local field plus full residual and streaming provenance."""

    electric_field: Any
    recovery_audit: dict[str, Any]
    full_operator_residual: dict[str, Any]
    streaming_audit: dict[str, Any]


def _modal_vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    vector.set(PETSc.ScalarType(0.0))
    first, last = vector.getOwnershipRange()
    if last > first:
        vector.setValues(
            np.arange(first, last, dtype=PETSc.IntType),
            np.asarray(values[first:last], dtype=PETSc.ScalarType),
        )
    vector.assemble()
    return vector


def _reduced_internal_action(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    modal: np.ndarray,
) -> PETSc.Vec:
    count = coupling.mode_count_per_direction
    block = coupling.bottom if system.side == "bottom" else coupling.top
    if system.side == "bottom":
        positive_values = modal[:count]
        negative_values = (
            np.asarray(coupling.propagation.backward.factors)
            * modal[count:]
        )
    else:
        positive_values = (
            np.asarray(coupling.propagation.forward.factors)
            * modal[:count]
        )
        negative_values = modal[count:]
    positive_source = _modal_vector(
        block.positive_traction,
        positive_values,
    )
    negative_source = _modal_vector(
        block.negative_traction,
        negative_values,
    )
    result = block.positive_traction.createVecLeft()
    temporary = block.negative_traction.createVecLeft()
    try:
        block.positive_traction.mult(positive_source, result)
        block.negative_traction.mult(negative_source, temporary)
        result.axpy(PETSc.ScalarType(1.0), temporary)
    finally:
        positive_source.destroy()
        negative_source.destroy()
        temporary.destroy()
    return result


def _add_external_tractions(
    system: HybridLocalDtnSystem,
    full_rhs: PETSc.Vec,
    reduced_solution: PETSc.Vec,
    auxiliary_override: np.ndarray | None = None,
) -> dict[str, Any]:
    if auxiliary_override is None:
        auxiliary = _gather_auxiliary_values(
            reduced_solution,
            system.n_fe,
            system.n_external_aux,
            system.local_mesh.mesh.comm,
        )
    else:
        auxiliary = np.asarray(auxiliary_override, dtype=np.complex128)
        if auxiliary.shape != (len(system.external_modes),):
            raise ValueError("External auxiliary override has the wrong shape.")
    assemblers = (
        _ReusableSurfaceComponentAssembler(
            system.V,
            system.local_mesh.mesh_data,
            system.local_mesh.external_facet_tag,
            0,
            quadrature_degree=system.dtn_quadrature_degree,
        ),
        _ReusableSurfaceComponentAssembler(
            system.V,
            system.local_mesh.mesh_data,
            system.local_mesh.external_facet_tag,
            1,
            quadrature_degree=system.dtn_quadrature_degree,
        ),
    )
    key = None
    component_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    assembled_orders = 0
    try:
        for amplitude, mode in zip(
            auxiliary,
            system.external_modes,
            strict=True,
        ):
            mode_key = (
                int(mode.m),
                int(mode.n),
                complex(mode.k_vector[2]),
            )
            if mode_key != key:
                if component_vectors is not None:
                    for vector in component_vectors:
                        vector.destroy()
                component_vectors = tuple(
                    assembler.assemble_unconstrained_vector(mode)
                    for assembler in assemblers
                )
                key = mode_key
                assembled_orders += 1
            traction = _traction_vector(mode, system.cfg)
            for coefficient, vector in zip(
                amplitude * traction[:2],
                component_vectors,
                strict=True,
            ):
                if coefficient != 0.0:
                    full_rhs.axpy(PETSc.ScalarType(coefficient), vector)
    finally:
        if component_vectors is not None:
            for vector in component_vectors:
                vector.destroy()
    return {
        "external_auxiliary_count": int(len(auxiliary)),
        "external_unique_surface_orders_reassembled": assembled_orders,
    }


def _add_internal_tractions(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    modal: np.ndarray,
    full_rhs: PETSc.Vec,
) -> dict[str, Any]:
    count = coupling.mode_count_per_direction
    if system.side == "bottom":
        positive_values = modal[:count]
        negative_values = (
            np.asarray(coupling.propagation.backward.factors)
            * modal[count:]
        )
    else:
        positive_values = (
            np.asarray(coupling.propagation.forward.factors)
            * modal[:count]
        )
        negative_values = modal[count:]
    evaluator = _ReusableModeTractionEvaluator(coupling.spaces)
    surface = _ReusableInterfaceSurfaceLoad(system)
    queries = 0
    assemblies = 0
    sign = system.local_mesh.local_interface_outward_normal_sign
    for basis, values, traction_betas in (
        (
            coupling.positive_basis,
            positive_values,
            coupling.positive_traction_beta_per_nm,
        ),
        (
            coupling.negative_basis,
            negative_values,
            coupling.negative_traction_beta_per_nm,
        ),
    ):
        for mode, coefficient, traction_beta in zip(
            basis.modes,
            values,
            traction_betas,
            strict=True,
        ):
            traction = evaluator.evaluate(
                mode,
                local_outward_normal_sign=sign,
                beta_override=complex(traction_beta),
            )
            vector, mode_queries = surface.assemble_full_vector(traction)
            try:
                if coefficient != 0.0:
                    full_rhs.axpy(PETSc.ScalarType(coefficient), vector)
            finally:
                vector.destroy()
            queries += mode_queries
            assemblies += 1
    return {
        "internal_mode_surface_vectors_reassembled": assemblies,
        "internal_mode_lifted_query_points": queries,
        "traction_beta_source": "coupling_selected_traction_beta_per_nm",
    }


def recover_hybrid_static_local_field(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    reduced_solution: PETSc.Vec,
    modal_amplitudes: np.ndarray,
    *,
    auxiliary_override: np.ndarray | None = None,
) -> HybridStaticRecoveredLocalField:
    """Recover one local field without retaining any full ``N_FE x M`` block."""

    if system.static_condensation is None or system.full_fe_rhs is None:
        raise ValueError(
            "Hybrid static field recovery requires a condensed local system."
        )
    modal = np.asarray(modal_amplitudes, dtype=np.complex128)
    if modal.shape != (coupling.internal_unknown_count,):
        raise ValueError("Hybrid modal amplitudes have the wrong shape.")
    if reduced_solution.getSize() != system.global_size:
        raise ValueError("Hybrid reduced local solution has the wrong size.")

    comm = system.local_mesh.mesh.comm
    started = perf_counter()
    full_effective_rhs = system.full_fe_rhs.duplicate()
    system.full_fe_rhs.copy(full_effective_rhs)
    reduced_effective_rhs = system.b.duplicate()
    system.b.copy(reduced_effective_rhs)
    internal_action = _reduced_internal_action(
        system,
        coupling,
        modal,
    )
    try:
        reduced_effective_rhs.axpy(
            PETSc.ScalarType(-1.0),
            internal_action,
        )
        external_audit = _add_external_tractions(
            system,
            full_effective_rhs,
            reduced_solution,
            auxiliary_override=auxiliary_override,
        )
        internal_audit = _add_internal_tractions(
            system,
            coupling,
            modal,
            full_effective_rhs,
        )
        recovered = system.static_condensation.recover_and_audit(
            reduced_solution,
            reduced_effective_rhs,
            full_effective_rhs,
        )
    finally:
        internal_action.destroy()
        reduced_effective_rhs.destroy()
        full_effective_rhs.destroy()
    return HybridStaticRecoveredLocalField(
        electric_field=recovered.electric_field,
        recovery_audit=recovered.recovery_audit,
        full_operator_residual=recovered.full_operator_residual,
        streaming_audit={
            "schema_version": "task035b.hybrid-static-streaming-recovery.v1",
            "side": system.side,
            "full_surface_mode_matrix_retained": False,
            "full_global_matrix_allocated": False,
            "full_effective_rhs_reassembled_once": True,
            **external_audit,
            **internal_audit,
            "total_seconds_max": float(
                comm.allreduce(perf_counter() - started, op=MPI.MAX)
            ),
        },
    )


__all__ = [
    "HybridStaticRecoveredLocalField",
    "recover_hybrid_static_local_field",
]
