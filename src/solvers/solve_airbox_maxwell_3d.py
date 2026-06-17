from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, default_scalar_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config_3d import SimulationConfig3D
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
from ..postprocessing.postprocess_3d import save_airbox_3d_fields
from .solve_vector_maxwell import _json_default


def _start_timed_stage(comm) -> float:
    comm.barrier()
    return time.perf_counter()


def _finish_timed_stage(comm, timings: dict[str, float], name: str, started: float, log) -> None:
    local_elapsed = time.perf_counter() - started
    elapsed = float(comm.allreduce(local_elapsed, op=MPI.MAX))
    timings[name] = elapsed
    log(f"{name} seconds = {elapsed:.3f}")


def plane_wave_electric_field(V, cfg: SimulationConfig3D) -> fem.Function:
    field = fem.Function(V, name="E_exact")
    k = cfg.wavevector
    p = cfg.polarization_vector
    amplitude = complex(cfg.incident_amplitude)

    def eval_field(x):
        phase = np.exp(1j * (k[0] * x[0] + k[1] * x[1] + k[2] * x[2]))
        return amplitude * p[:, None] * phase[None, :]

    field.interpolate(eval_field)
    return field


def run_airbox_3d_case(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    log_lines: list[str] = []
    timings: dict[str, float] = {}
    start = _start_timed_stage(comm)

    def log(message: str):
        log_lines.append(message)
        if comm.rank == 0:
            PETSc.Sys.Print(message)

    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError("The 3D Maxwell solver requires complex-mode DOLFINx/PETSc.")

    stage_start = _start_timed_stage(comm)
    # Trigger validation before any expensive setup.
    k = cfg.wavevector
    p = cfg.polarization_vector
    dot_k_p = np.dot(k, p)
    _finish_timed_stage(comm, timings, "config_validation", stage_start, log)

    log(f"case = {cfg.case_name}")
    log("stage = 1, 3D full-vector Maxwell air-box Dirichlet plane-wave test")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"DOLFINx scalar type = {default_scalar_type}")
    log(f"k0 = {cfg.k0:.12g}")
    log(f"k = {k.tolist()}")
    log(f"polarization = {p.tolist()}")
    log(f"dot(k, p) = {dot_k_p:.6e}")
    log(f"mesh target size = {cfg.mesh_target_size}")

    stage_start = _start_timed_stage(comm)
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    _finish_timed_stage(comm, timings, "mesh_build", stage_start, log)

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    num_cells = msh.topology.index_map(tdim).size_global

    stage_start = _start_timed_stage(comm)
    curl_el = element("N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type)
    V = fem.functionspace(msh, curl_el)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    _finish_timed_stage(comm, timings, "function_space_setup", stage_start, log)
    log(f"mesh cells = {num_cells}")
    log(f"3D N1curl dofs = {num_dofs}")

    stage_start = _start_timed_stage(comm)
    E_exact = plane_wave_electric_field(V, cfg)
    boundary_dofs = fem.locate_dofs_topological(V, fdim, mesh_data.boundary_facets)
    bc = fem.dirichletbc(E_exact, boundary_dofs)
    _finish_timed_stage(comm, timings, "boundary_condition_setup", stage_start, log)
    log(f"Dirichlet H(curl) boundary dofs = {len(boundary_dofs)}")

    stage_start = _start_timed_stage(comm)
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh)
    zero = fem.Constant(msh, np.zeros(3, dtype=default_scalar_type))
    mu_inv = PETSc.ScalarType(1.0 / cfg.mu_r)
    eps_r = PETSc.ScalarType(cfg.eps_r)
    a = mu_inv * ufl.inner(ufl.curl(u), ufl.curl(v)) * dx - cfg.k0**2 * eps_r * ufl.inner(u, v) * dx
    L = ufl.inner(zero, v) * dx
    _finish_timed_stage(comm, timings, "variational_form_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    E = fem.Function(V, name="E_numerical")
    problem = fem_petsc.LinearProblem(
        a,
        L,
        bcs=[bc],
        u=E,
        petsc_options_prefix=f"airbox3d_{cfg.case_name}_",
        petsc_options={
            "ksp_type": "preonly",
            "pc_type": "lu",
            "ksp_error_if_not_converged": True,
        },
    )
    _finish_timed_stage(comm, timings, "linear_problem_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    E = problem.solve()
    _finish_timed_stage(comm, timings, "linear_problem_solve", stage_start, log)
    reason = int(problem.solver.getConvergedReason())
    iterations = int(problem.solver.getIterationNumber())
    residual_norm = float(problem.solver.getResidualNorm())
    log(f"solver converged reason = {reason}")
    log(f"solver iterations = {iterations}")
    log(f"solver residual norm = {residual_norm:.6e}")

    stage_start = _start_timed_stage(comm)
    field_metrics = save_airbox_3d_fields(mesh_data, cfg, E, out_dir)
    _finish_timed_stage(comm, timings, "postprocess", stage_start, log)
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))

    summary = {
        "case_name": cfg.case_name,
        "stage": "stage1_3d_airbox",
        "config": cfg.as_jsonable(),
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": "dolfinx.fem.petsc.LinearProblem with strong tangential E plane-wave boundary data",
        "ksp_converged_reason": reason,
        "ksp_iterations": iterations,
        "solver_residual_norm": residual_norm,
        "incident_transversality_dot_k_p": dot_k_p,
        "timings_seconds": timings,
        "elapsed_seconds": elapsed,
        **field_metrics,
    }
    log(f"max |E| = {field_metrics['max_abs_E']:.6e}")
    log(f"max |H| = {field_metrics['max_abs_H']:.6e}")
    log(f"plane-wave relative max error = {field_metrics['relative_max_abs_E_error']:.6e}")
    log(f"H relative max error = {field_metrics['relative_max_abs_H_error']:.6e}")
    log(f"Poynting direction cosine = {field_metrics['poynting_direction_cosine']:.6e}")
    log(f"ParaView file = {field_metrics['paraview_file']}")
    log("timing summary seconds:")
    for name, value in timings.items():
        log(f"  {name}: {value:.3f}")
    log(f"elapsed seconds = {elapsed:.3f}")

    if comm.rank == 0:
        (out_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "solver_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    return summary
