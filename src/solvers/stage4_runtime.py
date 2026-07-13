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
    SimulationConfig3D,
    target_stage4_config,
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


def stage4_physical_model(cfg: SimulationConfig3D) -> dict[str, Any]:
    """Serialize the physical target independently from solver settings."""

    def pair(value: complex) -> list[float]:
        number = complex(value)
        return [float(number.real), float(number.imag)]

    return {
        "geometry_kind": cfg.geometry_kind,
        "period_x_nm": float(cfg.period_x),
        "period_y_nm": float(cfg.period_y),
        "air_height_nm": float(cfg.air_height),
        "substrate_thickness_nm": float(cfg.substrate_thickness),
        "grating_width_x_nm": float(cfg.grating_width_x),
        "grating_width_y_nm": float(cfg.grating_width_y),
        "grating_height_nm": float(cfg.grating_height),
        "n_air": pair(cfg.n_air),
        "n_substrate": pair(cfg.substrate_index),
        "n_grating": pair(cfg.grating_index),
        "wavelength_nm": float(cfg.lambda0),
        "incident_theta_deg": float(cfg.incident_theta_deg),
        "incident_phi_deg": float(cfg.incident_phi_deg),
        "polarization_kind": cfg.polarization_kind,
        "nedelec_degree": int(cfg.nedelec_degree),
        "boundary_model": cfg.stage4_boundary_model,
        "dtn_order_policy": cfg.stage4_dtn_order_policy,
    }


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
