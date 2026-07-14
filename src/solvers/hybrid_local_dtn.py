from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dolfinx_mpc
import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..common.modes_3d import PortMode3D, outgoing_port_modes_3d
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.hybrid_local_mesh import HybridLocalMesh, HybridLocalSide, build_hybrid_local_mesh
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import _create_nedelec_space, _petsc_matrix_stats
from .dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assemble_mpc_vector,
    _augmented_vec_from_base,
    _combine_owned_entries,
    _copy_base_matrix_to_augmented,
    _dtn_surface_quadrature_degree,
    _incident_projection_onto_top_mode,
    _incident_top_traction_form,
    _local_augmented_dtn_coupling_stats,
    _mode_projection_denominator,
    _traction_vector,
    _vec_nonzero_owned_entries,
)


@dataclass
class HybridLocalDtnSystem:
    """One terminal FEM block including only its external Fourier-DtN port."""

    side: HybridLocalSide
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

    @property
    def global_size(self) -> int:
        return int(self.n_fe + self.n_external_aux)


def _assemble_one_sided_external_dtn(
    *,
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    local_mesh: HybridLocalMesh,
    V,
    floquet_data: DoubleFloquet3DData,
    bilinear_form,
    linear_form,
) -> tuple[
    PETSc.Mat,
    PETSc.Vec,
    list[PortMode3D],
    np.ndarray,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    int,
]:
    """Assemble the existing Stage-4 auxiliary DtN algebra on one outer face."""

    comm = local_mesh.mesh.comm
    A_base = dolfinx_mpc.assemble_matrix(fem.form(bilinear_form), floquet_data.mpc, bcs=None)
    A_base.assemble()
    b_base = _assemble_mpc_vector(linear_form, floquet_data.mpc)
    n_fe = int(A_base.getSize()[0])
    base_stats = _petsc_matrix_stats(A_base)

    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == side]
    if not modes:
        raise RuntimeError(f"Task32 {side} local block selected zero external DtN modes.")
    n_aux = len(modes)
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    A_aug = _copy_base_matrix_to_augmented(A_base, n_aux, comm)
    b_aug = _augmented_vec_from_base(b_base, n_aux, comm)

    if side == "top":
        incident_vec = _assemble_mpc_vector(
            _incident_top_traction_form(V, local_mesh.mesh_data, cfg),
            floquet_data.mpc,
        )
        try:
            incident_rows, incident_values = _vec_nonzero_owned_entries(incident_vec)
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
    component_entries = None
    traction_rows_local = 0
    projection_cols_local = 0
    incident_projections: list[complex] = []
    for aux_index, mode in enumerate(modes):
        key = (int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if key != component_key or component_entries is None:
            component_entries = tuple(
                assembler.assemble_entries(mode, floquet_data.mpc)
                for assembler in surface_assemblers
            )
            component_key = key
        traction = _traction_vector(mode, cfg)
        projection_cols, projection_values = _combine_owned_entries(
            component_entries,
            (mode.e_vector[0], mode.e_vector[1]),
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_entries,
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
            )
            if incident_projection != 0.0:
                b_aug.setValues(
                    traction_rows,
                    -traction_values * incident_projection,
                    addv=PETSc.InsertMode.ADD_VALUES,
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
            )
        A_aug.setValue(aux_global, aux_global, PETSc.ScalarType(1.0))

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
        }
    )
    augmented_stats = _petsc_matrix_stats(A_aug)
    A_base.destroy()
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
    )


def assemble_hybrid_local_dtn_system(
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    log=None,
) -> HybridLocalDtnSystem:
    """Build one Task32 terminal FEM matrix with one external DtN port."""

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Task32 direct baseline requires auxiliary external DtN.")
    if cfg.use_pml:
        raise ValueError("Task32 external DtN local blocks require use_pml=False.")
    local_mesh = build_hybrid_local_mesh(cfg, side, comm=comm)
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
    ) = _assemble_one_sided_external_dtn(
        cfg=cfg,
        side=side,
        local_mesh=local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=a,
        linear_form=L,
    )
    return HybridLocalDtnSystem(
        side=side,
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
    )
