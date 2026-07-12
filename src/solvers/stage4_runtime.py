from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

import numpy as np
from dolfinx import default_scalar_type
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import (
    EUV_REFERENCE_WAVELENGTH_NM,
    NUMERICAL_SANITY_ONLY,
    SI_GRATING_INDEX_EUV_13P5_NM,
    SI_GRATING_MATERIAL_LABEL,
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    SI_SUBSTRATE_MATERIAL_LABEL,
    SimulationConfig3D,
    oblique_incidence_airbox_config,
)
from ..common.modes_3d import PortMode3D, outgoing_port_modes_3d
from ..constraints.floquet_3d import build_double_floquet_mpc
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import (
    _create_nedelec_space,
    _petsc_matrix_stats,
    _prepare_direct_lu_options_for_comm,
)
from .dtn_port_3d import solve_stage4_dtn_port_total_field


@dataclass
class RuntimeStage4System:
    cfg: SimulationConfig3D
    A_petsc: PETSc.Mat
    b_petsc: PETSc.Vec
    x_petsc: PETSc.Vec
    V: Any
    mesh_data: Any
    floquet_data: Any
    n_fe: int
    n_aux: int
    solver_info: dict[str, Any]
    matrix_stats: dict[str, Any]
    timings: dict[str, float]
    log_lines: list[str]
    out_dir: Path
    modes: list[PortMode3D]


def target_stage4_config(*, degree: int, h_nm: float) -> SimulationConfig3D:
    """Return the reviewed 50 x 25 x 140 nm target grating configuration."""

    cfg = oblique_incidence_airbox_config(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        scattering_background="layered",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="auto_propagating",
        stage4_dtn_assembly="auxiliary",
        stage4_pml_outer_bc="natural",
        lambda0=EUV_REFERENCE_WAVELENGTH_NM,
        period_x=50.0,
        period_y=25.0,
        air_height=130.0,
        substrate_thickness=10.0,
        z_min=-10.0,
        z_max=130.0,
        interface_z=0.0,
        use_floquet_xy=True,
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
        pml_alpha=5.0,
        n_substrate=SI_SUBSTRATE_INDEX_EUV_13P5_NM,
        n_grating=SI_GRATING_INDEX_EUV_13P5_NM,
        substrate_material_label=SI_SUBSTRATE_MATERIAL_LABEL,
        grating_material_label=SI_GRATING_MATERIAL_LABEL,
        validation_role=NUMERICAL_SANITY_ONLY,
        grating_width_x=17.0,
        grating_width_y=25.0,
        grating_height=120.0,
        incident_theta_deg=80.0,
        incident_phi_deg=0.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=int(degree),
        visualization_degree=int(degree),
        mesh_target_size=float(h_nm),
        mesh_spacing_mode="auto",
        mesh_refined_size=None,
        mesh_refinement_radius=None,
        mesh_cell_type="auto",
        floquet_constraint_mode="auto",
        diffraction_zero_order_only=False,
        diffraction_sample_count_x=32,
        diffraction_sample_count_y=32,
        diffraction_probe_fraction=0.75,
        diffraction_compute_modal_diagnostic=False,
        matrix_diagnostics_assemble_only=True,
        unique_output=True,
    )
    cfg.case_name = f"target_stage4_block_grating_p{degree}_h{h_nm:g}".replace(".", "p")
    return cfg


def assemble_target_stage4_system(
    *,
    h_nm: float,
    output_dir: Path,
    degree: int = 2,
    config_overrides: dict[str, Any] | None = None,
) -> RuntimeStage4System:
    """Assemble, but do not solve, the reviewed target Stage4 augmented system."""

    comm = MPI.COMM_WORLD
    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError("Stage4 runtime assembly requires complex DOLFINx/PETSc")
    cfg = target_stage4_config(degree=degree, h_nm=h_nm)
    for key, value in (config_overrides or {}).items():
        if not hasattr(cfg, key):
            raise ValueError(f"unknown Stage4 configuration override: {key}")
        setattr(cfg, key, value)
    modes = list(outgoing_port_modes_3d(cfg))
    if not modes:
        raise RuntimeError("Stage4 runtime system selected zero DtN modes")
    if comm.rank == 0:
        output_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    log_lines: list[str] = []

    def log(message: str) -> None:
        log_lines.append(str(message))
        if comm.rank == 0:
            PETSc.Sys.Print(message)

    timings: dict[str, float] = {}
    started = time.perf_counter()
    petsc_options, _solver, disabled = _prepare_direct_lu_options_for_comm(comm, cfg)
    if disabled is not None:
        raise RuntimeError(disabled)
    t0 = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(cfg, output_dir)
    timings["mesh_build_s"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    t0 = time.perf_counter()
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    timings["function_space_s"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    t0 = time.perf_counter()
    floquet_data = build_double_floquet_mpc(V, mesh_data, cfg, log)
    timings.update(floquet_data.timings_seconds)
    timings["floquet_s"] = float(comm.allreduce(time.perf_counter() - t0, op=MPI.MAX))
    a, L = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    t0 = time.perf_counter()
    dtn = solve_stage4_dtn_port_total_field(
        a=a,
        L=L,
        V=V,
        mesh_data=mesh_data,
        cfg=cfg,
        floquet_data=floquet_data,
        petsc_options=petsc_options,
        out_dir=output_dir,
        log=log,
        started=started,
    )
    timings["dtn_assembly_s"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    solver_info = dtn["solver_info"]
    return RuntimeStage4System(
        cfg=cfg,
        A_petsc=dtn["A"],
        b_petsc=dtn["b"],
        x_petsc=dtn["x"],
        V=V,
        mesh_data=mesh_data,
        floquet_data=floquet_data,
        n_fe=int(solver_info["num_fem_dofs_after_mpc"]),
        n_aux=int(solver_info["num_auxiliary_dofs"]),
        solver_info=solver_info,
        matrix_stats=_petsc_matrix_stats(dtn["A"]),
        timings=timings,
        log_lines=log_lines,
        out_dir=output_dir,
        modes=modes,
    )
