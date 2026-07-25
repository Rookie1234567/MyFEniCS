from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import dolfinx_mpc
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
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.hybrid_local_mesh import HybridLocalMesh, HybridLocalSide, build_hybrid_local_mesh
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import _create_nedelec_space, _petsc_matrix_stats
from .dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assemble_mpc_vector,
    _assemble_unconstrained_vector,
    _augmented_vec_from_base,
    _combine_owned_entries,
    _copy_base_matrix_to_augmented,
    _deferred_preallocation_matrix_stats,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _incident_top_traction_form,
    _local_augmented_dtn_coupling_stats,
    _mode_projection_denominator,
    _owned_cells_adjacent_to_facet_tag,
    _traction_vector,
    _vec_nonzero_owned_entries,
)
from .hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from .hybrid_local_static_condensation import (
    HybridLocalStaticCondensation,
    bind_hybrid_local_static_condensation,
)


@dataclass
class HybridLocalDtnSystem:
    """One terminal FEM block including only its external Fourier-DtN port."""

    side: HybridLocalSide
    cfg: SimulationConfig3D
    local_mesh: HybridLocalMesh
    V: Any
    floquet_data: DoubleFloquet3DData
    bilinear_form: Any
    linear_form: Any
    A: PETSc.Mat
    b: PETSc.Vec
    n_fe: int
    n_external_aux: int
    external_modes: list[PortMode3D]
    incident_projections: np.ndarray
    base_matrix_stats: dict[str, Any]
    augmented_matrix_stats: dict[str, Any]
    coupling_stats: dict[str, Any]
    dtn_quadrature_degree: int
    assembly_backend_requested: str = "standard_full"
    assembly_backend_actual: str = "standard_full"
    assembly_backend_qualification: dict[str, Any] | None = None
    static_condensation: HybridLocalStaticCondensation | None = None
    full_fe_rhs: PETSc.Vec | None = None
    full_fe_rows: int | None = None
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def global_size(self) -> int:
        return int(self.n_fe + self.n_external_aux)

    @property
    def physical_full_size(self) -> int:
        return int(
            (self.full_fe_rows if self.full_fe_rows is not None else self.n_fe)
            + self.n_external_aux
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        if self.full_fe_rhs is not None:
            self.full_fe_rhs.destroy()
        self._destroyed = True


def _assemble_one_sided_external_dtn(
    *,
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    local_mesh: HybridLocalMesh,
    V,
    floquet_data: DoubleFloquet3DData,
    bilinear_form,
    linear_form,
    assembly_backend_audit: dict[str, Any],
    assembly_backend_qualification: dict[str, Any],
) -> tuple[
    PETSc.Mat,
    PETSc.Vec,
    list[PortMode3D],
    np.ndarray,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    int,
    HybridLocalStaticCondensation | None,
    PETSc.Vec | None,
    int,
]:
    """Assemble the existing Stage-4 auxiliary DtN algebra on one outer face."""

    comm = local_mesh.mesh.comm
    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == side]
    if not modes:
        raise RuntimeError(f"Task32 {side} local block selected zero external DtN modes.")
    n_aux = len(modes)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    static_requested = (
        assembly_backend_audit["actual"]
        == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    )
    static_condensation = None
    full_fe_rhs = None
    A_base = None
    b_base = None
    if static_requested:
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear_form),
            V,
            local_mesh.mesh_data.cell_tags,
            mpc=floquet_data.mpc,
            appended_global_rows=n_aux,
            appended_support_owned_cell_groups=(
                _owned_cells_adjacent_to_facet_tag(
                    local_mesh.mesh_data,
                    local_mesh.external_facet_tag,
                ),
            ),
            appended_support_group_by_row=tuple(0 for _mode in modes),
            defer_final_assembly=True,
        )
        static_condensation = bind_hybrid_local_static_condensation(
            condensed=condensed,
            bilinear_form=bilinear_form,
            floquet_data=floquet_data,
            assembly_backend_requested=str(
                assembly_backend_audit["requested"]
            ),
            assembly_backend_actual=str(assembly_backend_audit["actual"]),
            external_auxiliary_rows=n_aux,
        )
        A_aug = condensed.matrix
        n_fe = int(condensed.active_rows)
        base_stats = _deferred_preallocation_matrix_stats(
            A_aug,
            condensed.build_audit["trace_preallocation"],
        )
        full_fe_rhs = _assemble_unconstrained_vector(linear_form)
        b_aug = static_condensation.reduce_surface_vector(
            full_fe_rhs,
            role="load_column",
        )
        full_fe_rows = int(condensed.full_rows)
    else:
        A_base = dolfinx_mpc.assemble_matrix(
            fem.form(bilinear_form),
            floquet_data.mpc,
            bcs=None,
        )
        A_base.assemble()
        b_base = _assemble_mpc_vector(linear_form, floquet_data.mpc)
        n_fe = int(A_base.getSize()[0])
        base_stats = _petsc_matrix_stats(A_base)
        A_aug = _copy_base_matrix_to_augmented(A_base, n_aux, comm)
        b_aug = _augmented_vec_from_base(b_base, n_aux, comm)
        full_fe_rows = n_fe

    if side == "top":
        incident_form = _incident_top_traction_form(
            V,
            local_mesh.mesh_data,
            cfg,
        )
        incident_vec = (
            _assemble_unconstrained_vector(incident_form)
            if static_condensation is not None
            else _assemble_mpc_vector(incident_form, floquet_data.mpc)
        )
        try:
            if static_condensation is not None:
                reduced_incident = static_condensation.reduce_surface_vector(
                    incident_vec,
                    role="load_column",
                )
                incident_rows, incident_values = _vec_nonzero_owned_entries(
                    reduced_incident
                )
                reduced_incident.destroy()
                if full_fe_rhs is None:
                    raise RuntimeError(
                        "Hybrid static condensation lost its full FE RHS."
                    )
                full_fe_rhs.axpy(PETSc.ScalarType(1.0), incident_vec)
            else:
                incident_rows, incident_values = _vec_nonzero_owned_entries(
                    incident_vec
                )
            if len(incident_rows):
                b_aug.setValues(
                    incident_rows,
                    incident_values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        finally:
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
    component_key: tuple[int, int, complex] | None = None
    component_right_entries = None
    component_left_entries = None
    component_full_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_interior_bilinear: np.ndarray | None = None
    traction_rows_local = 0
    projection_cols_local = 0
    incident_projections: list[complex] = []
    matrix_insert_mode = (
        PETSc.InsertMode.ADD_VALUES
        if static_condensation is not None
        else PETSc.InsertMode.INSERT_VALUES
    )
    matrix_row_start, matrix_row_end = A_aug.getOwnershipRange()
    for aux_index, mode in enumerate(modes):
        key = (int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if key != component_key or component_right_entries is None:
            if component_full_vectors is not None:
                for vector in component_full_vectors:
                    vector.destroy()
                component_full_vectors = None
            if static_condensation is not None:
                component_full_vectors = tuple(
                    assembler.assemble_unconstrained_vector(mode)
                    for assembler in surface_assemblers
                )
                right_vectors = tuple(
                    static_condensation.reduce_surface_vector(
                        vector,
                        role="load_column",
                    )
                    for vector in component_full_vectors
                )
                left_vectors = tuple(
                    static_condensation.reduce_surface_vector(
                        vector,
                        role="row_functional",
                    )
                    for vector in component_full_vectors
                )
                component_right_entries = tuple(
                    _vec_nonzero_owned_entries(vector)
                    for vector in right_vectors
                )
                component_left_entries = tuple(
                    _vec_nonzero_owned_entries(vector)
                    for vector in left_vectors
                )
                for vector in (*right_vectors, *left_vectors):
                    vector.destroy()
                component_interior_bilinear = (
                    static_condensation.interior_cross_block(
                        component_full_vectors,
                        component_full_vectors,
                    )
                )
            else:
                component_right_entries = tuple(
                    assembler.assemble_entries(mode, floquet_data.mpc)
                    for assembler in surface_assemblers
                )
                component_left_entries = component_right_entries
                component_interior_bilinear = None
            component_key = key
        if component_left_entries is None:
            raise RuntimeError("Hybrid external DtN left component cache is missing.")
        traction = _traction_vector(mode, cfg)
        projection_cols, projection_values = _combine_owned_entries(
            component_left_entries,
            (mode.e_vector[0], mode.e_vector[1]),
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_right_entries,
            (traction[0], traction[1]),
        )
        aux_global = n_fe + aux_index
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)

        if len(traction_rows):
            traction_rows_local += int(len(traction_rows))
            A_aug.setValues(
                traction_rows,
                np.asarray([aux_global], dtype=PETSc.IntType),
                (-traction_values).reshape((len(traction_rows), 1)),
                addv=matrix_insert_mode,
            )
            if incident_projection != 0.0:
                b_aug.setValues(
                    traction_rows,
                    -traction_values * incident_projection,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        if (
            incident_projection != 0.0
            and full_fe_rhs is not None
            and component_full_vectors is not None
        ):
            for coefficient, vector in zip(
                traction[:2],
                component_full_vectors,
                strict=True,
            ):
                full_fe_rhs.axpy(
                    PETSc.ScalarType(
                        -incident_projection * coefficient
                    ),
                    vector,
                )
        if len(projection_cols):
            projection_cols_local += int(len(projection_cols))
            denominator = _mode_projection_denominator(mode, cfg)
            A_aug.setValues(
                np.asarray([aux_global], dtype=PETSc.IntType),
                projection_cols,
                (-np.conj(projection_values) / denominator).reshape(
                    (1, len(projection_cols))
                ),
                addv=matrix_insert_mode,
            )
        auxiliary_diagonal = 1.0 + 0.0j
        if component_interior_bilinear is not None:
            electric = np.asarray(mode.e_vector[:2], dtype=np.complex128)
            traction_xy = np.asarray(traction[:2], dtype=np.complex128)
            auxiliary_diagonal -= complex(
                np.vdot(
                    electric,
                    component_interior_bilinear @ traction_xy,
                )
                / _mode_projection_denominator(mode, cfg)
            )
        if matrix_row_start <= aux_global < matrix_row_end:
            A_aug.setValue(
                aux_global,
                aux_global,
                PETSc.ScalarType(auxiliary_diagonal),
                addv=matrix_insert_mode,
            )

    if component_full_vectors is not None:
        for vector in component_full_vectors:
            vector.destroy()
    A_aug.assemble()
    b_aug.assemble()
    traction_rows = int(comm.allreduce(traction_rows_local, op=MPI.SUM))
    projection_cols = int(comm.allreduce(projection_cols_local, op=MPI.SUM))
    coupling_stats = _local_augmented_dtn_coupling_stats(
        n_fe=n_fe,
        n_aux=n_aux,
        traction_rows_total=traction_rows,
        ell_cols_total=projection_cols,
    )
    coupling_stats.update(
        {
            "external_side": side,
            "external_facet_tag": int(local_mesh.external_facet_tag),
            "internal_interface_facet_tag": int(local_mesh.interface_facet_tag),
            "external_traction_rows_total": traction_rows,
            "external_projection_cols_total": projection_cols,
            "internal_interface_dtn_coupling_inserted": False,
            "assembly_backend_requested": assembly_backend_audit[
                "requested"
            ],
            "assembly_backend_actual": assembly_backend_audit["actual"],
            "assembly_backend_qualification": (
                assembly_backend_qualification
            ),
            "static_condensation": (
                static_condensation.metadata.to_dict()
                if static_condensation is not None
                else None
            ),
        }
    )
    augmented_stats = _petsc_matrix_stats(A_aug)
    if A_base is not None:
        A_base.destroy()
    if b_base is not None:
        b_base.destroy()
    return (
        A_aug,
        b_aug,
        modes,
        np.asarray(incident_projections, dtype=np.complex128),
        base_stats,
        augmented_stats,
        coupling_stats,
        quadrature_degree,
        static_condensation,
        full_fe_rhs,
        full_fe_rows,
    )


def assemble_hybrid_local_dtn_system(
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    *,
    bottom_interface_z_nm: float = 10.0,
    top_interface_z_nm: float = 110.0,
    local_mesh_override: HybridLocalMesh | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    log=None,
) -> HybridLocalDtnSystem:
    """Build one terminal FEM matrix with one external DtN port.

    The reviewed Task32 decomposition remains the default.  Task33 may pass a
    symmetric alternative pair explicitly when measuring the local-FEM versus
    modal-buffer trade-off.
    """

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Task32 direct baseline requires auxiliary external DtN.")
    if cfg.use_pml:
        raise ValueError("Task32 external DtN local blocks require use_pml=False.")
    assembly_backend_audit = resolve_stage4_full3d_assembly_backend(
        cfg,
        apply=True,
    )
    assembly_backend_qualification = (
        qualify_stage4_full3d_assembly_backend(
            cfg,
            assembly_backend_audit,
        )
    )
    if log is not None:
        log(
            "Hybrid local assembly backend "
            f"requested={assembly_backend_audit['requested']} "
            f"actual={assembly_backend_audit['actual']} "
            "qualification="
            f"{assembly_backend_qualification['status']}"
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
    a, L = _build_variational_forms(
        local_mesh.mesh,
        local_mesh.mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    (
        A,
        b,
        modes,
        incident_projections,
        base_stats,
        augmented_stats,
        coupling_stats,
        quadrature_degree,
        static_condensation,
        full_fe_rhs,
        full_fe_rows,
    ) = _assemble_one_sided_external_dtn(
        cfg=cfg,
        side=side,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=a,
        linear_form=L,
        assembly_backend_audit=assembly_backend_audit,
        assembly_backend_qualification=assembly_backend_qualification,
    )
    return HybridLocalDtnSystem(
        side=side,
        cfg=cfg,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=a,
        linear_form=L,
        A=A,
        b=b,
        n_fe=int(A.getSize()[0] - len(modes)),
        n_external_aux=len(modes),
        external_modes=modes,
        incident_projections=incident_projections,
        base_matrix_stats=base_stats,
        augmented_matrix_stats=augmented_stats,
        coupling_stats=coupling_stats,
        dtn_quadrature_degree=quadrature_degree,
        assembly_backend_requested=str(assembly_backend_audit["requested"]),
        assembly_backend_actual=str(assembly_backend_audit["actual"]),
        assembly_backend_qualification=assembly_backend_qualification,
        static_condensation=static_condensation,
        full_fe_rhs=full_fe_rhs,
        full_fe_rows=full_fe_rows,
    )
