"""Matrix-free one-sided Hybrid local DtN carrier for Task037b H2b.

The fine local Schur action and the external C/D blocks are action-only from
construction.  The small H block is assembled, while the test-only direct
path remains responsible for extracting an explicit condensed reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
    qualify_stage4_full3d_assembly_backend,
    resolve_stage4_full3d_assembly_backend,
)
from ..common.modes_3d import PortMode3D, outgoing_port_modes_3d
from ..constraints.floquet_3d import build_double_floquet_mpc
from ..geometry.hybrid_local_mesh import (
    HybridLocalMesh,
    HybridLocalSide,
    build_hybrid_local_mesh,
)
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import _create_nedelec_space
from .condensed_dtn import (
    DtnBlockAssembler,
    PetscCondensedBlocks,
    condensed_rhs,
    create_matrix_free_condensed_operator,
)
from .dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assemble_unconstrained_vector,
    _combine_owned_entries,
    _dtn_n0_trace_alias_preflight,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _incident_top_traction_form,
    _mode_projection_denominator,
    _traction_vector,
    _vec_nonzero_owned_entries,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    build_unconstrained_assembly_time_condensation,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
)
from .hybrid_local_static_condensation import (
    HybridLocalStaticCondensation,
    bind_hybrid_local_static_condensation,
)
from .static_local_schur_action import create_static_local_schur_action

__all__ = (
    "HybridLocalDtnActionSystem",
    "assemble_hybrid_local_dtn_action_system",
)


class _HybridActionStaticCondensation:
    """Narrow coupling adapter over the retained action-only condensation."""

    def __init__(
        self,
        condensed: AssemblyTimeCondensedSystem,
        bilinear_form: Any,
        floquet_data: Any,
        reduced_operator: PETSc.Mat,
    ) -> None:
        self.condensed = condensed
        self._adapter: HybridLocalStaticCondensation = (
            bind_hybrid_local_static_condensation(
                condensed=condensed,
                bilinear_form=bilinear_form,
                floquet_data=floquet_data,
                assembly_backend_requested=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
                assembly_backend_actual=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
                external_auxiliary_rows=0,
                reduced_operator=reduced_operator,
            )
        )

    @property
    def metadata(self):
        return self._adapter.metadata

    def reduce_tangential_surface_mpc_vector(
        self,
        full_mpc_vector: PETSc.Vec,
        *,
        eliminated_tolerance: float = 1.0e-12,
        eliminated_relative_tolerance: float = (1024.0 * np.finfo(np.float64).eps),
        audit: dict[str, object] | None = None,
    ) -> PETSc.Vec:
        return self._adapter.reduce_tangential_surface_mpc_vector(
            full_mpc_vector,
            eliminated_tolerance=eliminated_tolerance,
            eliminated_relative_tolerance=eliminated_relative_tolerance,
            audit=audit,
        )

    def interior_cross_bilinear(
        self,
        left_full_vector: PETSc.Vec,
        right_full_vector: PETSc.Vec,
    ) -> complex:
        return self._adapter.interior_cross_bilinear(
            left_full_vector,
            right_full_vector,
        )

    def recover_and_audit(
        self,
        reduced_solution: PETSc.Vec,
        reduced_effective_rhs: PETSc.Vec,
        full_effective_rhs: PETSc.Vec,
    ):
        return self._adapter.recover_and_audit(
            reduced_solution,
            reduced_effective_rhs,
            full_effective_rhs,
        )

    def destroy(self) -> None:
        self.condensed.destroy()


@dataclass
class HybridLocalDtnActionSystem:
    """One-sided H2b carrier with no external rows in the Krylov layout."""

    side: HybridLocalSide
    cfg: SimulationConfig3D
    local_mesh: HybridLocalMesh
    V: Any
    floquet_data: Any
    bilinear_form: Any
    linear_form: Any
    A: PETSc.Mat
    b: PETSc.Vec
    blocks: PetscCondensedBlocks
    fine_action: PETSc.Mat
    static_condensation: _HybridActionStaticCondensation
    full_fe_rhs: PETSc.Vec
    n_fe: int
    external_modes: list[PortMode3D]
    incident_projections: np.ndarray
    base_matrix_stats: dict[str, Any]
    augmented_matrix_stats: dict[str, Any]
    coupling_stats: dict[str, Any]
    dtn_quadrature_degree: int
    assembly_backend_requested: str
    assembly_backend_actual: str
    assembly_backend_qualification: dict[str, Any]
    inventory: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def global_size(self) -> int:
        return int(self.n_fe)

    @property
    def n_external_aux(self) -> int:
        return 0

    @property
    def physical_full_size(self) -> int:
        return int(
            self.static_condensation.condensed.full_rows + len(self.external_modes)
        )

    @property
    def external_blocks(self) -> PetscCondensedBlocks:
        return self.blocks

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        self.fine_action.destroy()
        self.blocks.destroy()
        self.full_fe_rhs.destroy()
        self.static_condensation.destroy()
        self._destroyed = True


def _empty_action_stats(n_rows: int) -> dict[str, Any]:
    return {
        "matrix_type": "not_materialized_action_only",
        "matrix_rows": int(n_rows),
        "matrix_cols": int(n_rows),
        "matrix_nnz_used": None,
        "matrix_nnz_allocated": None,
        "matrix_memory_bytes": None,
        "matrix_memory_mb": None,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "matrix_stats_measurement_status": "not_applicable_action_only",
    }


def assemble_hybrid_local_dtn_action_system(
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    *,
    bottom_interface_z_nm: float = 10.0,
    top_interface_z_nm: float = 110.0,
    local_mesh_override: HybridLocalMesh | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    log=None,
) -> HybridLocalDtnActionSystem:
    """Build one static-condensed one-sided action-only DtN system.

    No augmented local matrix is allocated.  The production sequence is
    retained local Schur, matrix-free fine action, matrix-free C/D blocks, and
    the condensed action/RHS; direct assembled systems are test-only oracles.
    """

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError(
            "Task037b H2b requires the auxiliary external DtN path."
        )
    if cfg.use_pml:
        raise ValueError("Task037b H2b local action requires use_pml=False.")
    assembly_backend_audit = resolve_stage4_full3d_assembly_backend(cfg, apply=True)
    assembly_backend_qualification = qualify_stage4_full3d_assembly_backend(
        cfg,
        assembly_backend_audit,
    )
    if assembly_backend_audit["actual"] != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND:
        raise ValueError(
            "Task037b H2b requires assembly_time_static_condensed; "
            f"got {assembly_backend_audit['actual']}"
        )
    if local_mesh_override is not None:
        if local_mesh_override.side != side:
            raise ValueError("The local mesh override side does not match the request.")
        local_mesh = local_mesh_override
    else:
        local_mesh = build_hybrid_local_mesh(
            cfg,
            side,
            bottom_interface_z_nm=bottom_interface_z_nm,
            top_interface_z_nm=top_interface_z_nm,
            comm=comm,
        )
    V = _create_nedelec_space(local_mesh.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, local_mesh.mesh_data, cfg, log)
    bilinear_form, linear_form = _build_variational_forms(
        local_mesh.mesh,
        local_mesh.mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == side]
    if not modes:
        raise RuntimeError(f"Task037b {side} action selected zero external modes.")
    n_aux = len(modes)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    condensed = build_unconstrained_assembly_time_condensation(
        fem.form(bilinear_form),
        V,
        local_mesh.mesh_data.cell_tags,
        mpc=floquet_data.mpc,
        defer_final_assembly=True,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    if condensed.matrix is not None or condensed.appended_rows != 0:
        condensed.destroy()
        raise RuntimeError("H2b action carrier allocated non-active condensed rows.")

    full_fe_rhs = _assemble_unconstrained_vector(linear_form)
    if side == "top":
        incident_vec = _assemble_unconstrained_vector(
            _incident_top_traction_form(V, local_mesh.mesh_data, cfg)
        )
        full_fe_rhs.axpy(PETSc.ScalarType(1.0), incident_vec)
        incident_vec.destroy()

    surface_assemblers = (
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            0,
            quadrature_degree=quadrature_degree,
        ),
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            1,
            quadrature_degree=quadrature_degree,
        ),
    )
    trace_alias_preflight = _dtn_n0_trace_alias_preflight(
        modes,
        {
            (side, 0): surface_assemblers[0],
            (side, 1): surface_assemblers[1],
        },
        floquet_data.mpc,
        enabled=bool(cfg.dtn_y_invariant_n0_alias_preflight),
        overlap_tolerance=float(cfg.dtn_trace_alias_overlap_tolerance),
    )
    component_key: tuple[int, int, complex] | None = None
    component_right_entries = None
    component_left_entries = None
    component_full_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_interior_bilinear: np.ndarray | None = None
    mode_entries: list[dict[str, Any]] = []
    incident_projections: list[complex] = []
    for aux_index, mode in enumerate(modes):
        key = (int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if key != component_key or component_right_entries is None:
            if component_full_vectors is not None:
                for vector in component_full_vectors:
                    vector.destroy()
            component_full_vectors = tuple(
                assembler.assemble_unconstrained_vector(mode)
                for assembler in surface_assemblers
            )
            right_vectors = tuple(
                condense_unconstrained_vector_to_active_trace(
                    condensed,
                    vector,
                    side="right",
                )
                for vector in component_full_vectors
            )
            left_vectors = tuple(
                condense_unconstrained_vector_to_active_trace(
                    condensed,
                    vector,
                    side="left",
                )
                for vector in component_full_vectors
            )
            component_right_entries = tuple(
                _vec_nonzero_owned_entries(vector) for vector in right_vectors
            )
            component_left_entries = tuple(
                _vec_nonzero_owned_entries(vector) for vector in left_vectors
            )
            for vector in (*right_vectors, *left_vectors):
                vector.destroy()
            component_interior_bilinear = np.asarray(
                [
                    [
                        cell_interior_schur_bilinear(condensed, left, right)
                        for right in component_full_vectors
                    ]
                    for left in component_full_vectors
                ],
                dtype=np.complex128,
            )
            component_key = key
        if component_left_entries is None:
            raise RuntimeError("H2b left component cache is missing.")
        traction = _traction_vector(mode, cfg)
        projection_cols, projection_values = _combine_owned_entries(
            component_left_entries,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_right_entries,
            (traction[0], traction[1]),
            comm=comm,
        )
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)
        if incident_projection != 0.0 and component_full_vectors is not None:
            for coefficient, vector in zip(
                traction[:2],
                component_full_vectors,
                strict=True,
            ):
                full_fe_rhs.axpy(
                    PETSc.ScalarType(-incident_projection * coefficient),
                    vector,
                )
        auxiliary_diagonal = 1.0 + 0.0j
        if component_interior_bilinear is not None:
            auxiliary_diagonal -= complex(
                np.vdot(
                    np.asarray(mode.e_vector[:2], dtype=np.complex128),
                    component_interior_bilinear
                    @ np.asarray(traction[:2], dtype=np.complex128),
                )
                / _mode_projection_denominator(mode, cfg)
            )
        mode_entries.append(
            {
                "aux_index": int(aux_index),
                "traction_rows": traction_rows,
                "traction_values": -traction_values,
                "ell_cols": projection_cols,
                "ell_values": -np.conj(projection_values)
                / _mode_projection_denominator(mode, cfg),
                "auxiliary_diagonal": auxiliary_diagonal,
            }
        )
    if component_full_vectors is not None:
        for vector in component_full_vectors:
            vector.destroy()

    base_active_rhs = condense_unconstrained_vector_to_active_trace(
        condensed,
        full_fe_rhs,
        side="right",
    )
    assembler = DtnBlockAssembler(
        base_active_rhs,
        n_aux,
        traction_supports=tuple(entry["traction_rows"] for entry in mode_entries),
        ell_supports=tuple(entry["ell_cols"] for entry in mode_entries),
        matrix_free_dtn=True,
    )
    for entry in mode_entries:
        assembler.add_mode(**entry)
    base_active_rhs.destroy()
    blocks = assembler.finish()
    fine_action, _fine_context = create_static_local_schur_action(condensed)
    A, _condensed_context = create_matrix_free_condensed_operator(
        blocks,
        fine_operator=fine_action,
    )
    b = condensed_rhs(blocks)
    static_adapter = _HybridActionStaticCondensation(
        condensed,
        bilinear_form,
        floquet_data,
        A,
    )
    comm4 = local_mesh.mesh.comm
    traction_rows_total = int(
        comm4.allreduce(
            sum(len(entry["traction_rows"]) for entry in mode_entries),
            op=MPI.SUM,
        )
    )
    ell_cols_total = int(
        comm4.allreduce(
            sum(len(entry["ell_cols"]) for entry in mode_entries),
            op=MPI.SUM,
        )
    )
    coupling_stats = {
        "external_side": side,
        "external_traction_rows_total": traction_rows_total,
        "external_projection_cols_total": ell_cols_total,
        "external_mode_count": n_aux,
        "external_auxiliary_rows_in_krylov": 0,
        "external_auxiliary_rows": 0,
        "explicit_external_c_matrix_count": 0,
        "explicit_external_d_matrix_count": 0,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "matrix_free_dtn": True,
        "dtn_trace_alias_preflight": trace_alias_preflight,
        "preallocation": dict(assembler.preallocation_audit),
    }
    inventory = {
        "matrix_type": "python",
        "matrix_free": True,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "fine_action_matrix_type": "python",
        "fine_global_A_materialized": False,
        "bottom_global_F_materialized": False,
        "top_global_F_materialized": False,
        "explicit_external_c_matrix_count": 0,
        "explicit_external_d_matrix_count": 0,
        "direct_factor_count": 0,
        "global_size": int(condensed.active_rows),
        "active_rows": int(condensed.active_rows),
        "external_mode_count": n_aux,
        "external_auxiliary_rows_in_krylov": 0,
        "external_auxiliary_rows": 0,
        "external_blocks_matrix_free": True,
        "ordinary_default_changed": False,
    }
    stats = _empty_action_stats(condensed.active_rows)
    if log is not None:
        log(
            f"Task037b H2b {side} action-only rows={condensed.active_rows} "
            f"external_aux={n_aux} C/D=0/0"
        )
    return HybridLocalDtnActionSystem(
        side=side,
        cfg=cfg,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=bilinear_form,
        linear_form=linear_form,
        A=A,
        b=b,
        blocks=blocks,
        fine_action=fine_action,
        static_condensation=static_adapter,
        full_fe_rhs=full_fe_rhs,
        n_fe=int(condensed.active_rows),
        external_modes=modes,
        incident_projections=np.asarray(incident_projections, dtype=np.complex128),
        base_matrix_stats=stats,
        augmented_matrix_stats=stats.copy(),
        coupling_stats=coupling_stats,
        dtn_quadrature_degree=quadrature_degree,
        assembly_backend_requested=str(assembly_backend_audit["requested"]),
        assembly_backend_actual=str(assembly_backend_audit["actual"]),
        assembly_backend_qualification=assembly_backend_qualification,
        inventory=inventory,
    )
