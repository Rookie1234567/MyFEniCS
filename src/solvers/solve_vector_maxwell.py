from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse

from dolfinx import default_real_type, default_scalar_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config import SimulationConfig
from ..common.materials import background_relative_permittivity, relative_permittivity
from ..common.pml import bottom_pml_tensors, curl_3d, field_3d, top_pml_tensors
from ..constraints.floquet_constraint import (
    build_floquet_constraints,
    dof_trace_mismatch,
    solve_with_constraints_with_stats,
)
from ..geometry.mesh_builder import build_mesh
from ..postprocessing.power_metrics import compute_power_metrics
from ..postprocessing.postprocess import save_fields_and_plots


def _petsc_to_csr(A: PETSc.Mat):
    indptr, indices, data = A.getValuesCSR()
    return sparse.csr_matrix(
        (data, indices, indptr), shape=A.getSize(), dtype=np.complex128
    )


def _json_default(value):
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON serialize {type(value)!r}")


def incident_field_function(V, cfg: SimulationConfig) -> fem.Function:
    E_inc = fem.Function(V, name="E_inc")
    px, py = cfg.polarization

    def eval_field(x):
        phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
        values = np.empty((2, x.shape[1]), dtype=np.complex128)
        values[0] = px * phase
        values[1] = py * phase
        return values

    E_inc.interpolate(eval_field)
    return E_inc


def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1e-14 or (abs(root.imag) < 1e-14 and root.real < 0):
        root = -root
    return root


def layered_background_field_function(V, cfg: SimulationConfig) -> fem.Function:
    E_bg = fem.Function(V, name="E_background_layered")
    k_air_y = _positive_sqrt((cfg.k0 * cfg.n_air) ** 2 - cfg.kx**2)
    k_sub_y = _positive_sqrt((cfg.k0 * cfg.n_substrate) ** 2 - cfg.kx**2)

    cos_i = k_air_y / (cfg.k0 * cfg.n_air)
    sin_i = cfg.kx / (cfg.k0 * cfg.n_air)
    cos_t = k_sub_y / (cfg.k0 * cfg.n_substrate)
    sin_t = cfg.kx / (cfg.k0 * cfg.n_substrate)

    reflection = (cfg.n_air * cos_t - cfg.n_substrate * cos_i) / (
        cfg.n_air * cos_t + cfg.n_substrate * cos_i
    )
    transmission = (
        2.0 * cfg.n_air * cos_i / (cfg.n_air * cos_t + cfg.n_substrate * cos_i)
    )

    p_inc = np.asarray((cos_i, sin_i), dtype=np.complex128)
    p_ref = np.asarray((cos_i, -sin_i), dtype=np.complex128)
    p_trn = np.asarray((cos_t, sin_t), dtype=np.complex128)

    def eval_field(x):
        values = np.empty((2, x.shape[1]), dtype=np.complex128)
        air_mask = x[1] >= cfg.substrate_y_max - 1e-12
        phase_inc = np.exp(1j * (cfg.kx * x[0] - k_air_y * x[1]))
        phase_ref = np.exp(1j * (cfg.kx * x[0] + k_air_y * x[1]))
        phase_trn = np.exp(1j * (cfg.kx * x[0] - k_sub_y * x[1]))

        air_values = (
            p_inc[:, None] * phase_inc[None, :]
            + reflection * p_ref[:, None] * phase_ref[None, :]
        )
        substrate_values = transmission * p_trn[:, None] * phase_trn[None, :]
        values[:, air_mask] = air_values[:, air_mask]
        values[:, ~air_mask] = substrate_values[:, ~air_mask]
        return values

    E_bg.interpolate(eval_field)
    return E_bg


def background_field_function(V, cfg: SimulationConfig) -> fem.Function:
    if cfg.scattering_background == "air":
        return incident_field_function(V, cfg)
    if cfg.scattering_background == "layered":
        return layered_background_field_function(V, cfg)
    raise ValueError("scattering_background must be 'air' or 'layered'")


def _solve_mpc(a, L, V, constraints, cfg: SimulationConfig, log):
    try:
        import dolfinx_mpc
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "请求使用 dolfinx_mpc，但当前 Python 环境未安装 dolfinx_mpc。"
        ) from exc

    mpc = dolfinx_mpc.MultiPointConstraint(V)
    slaves = constraints.slave_dofs.astype(np.int32)
    masters = constraints.master_dofs.astype(np.int64)
    coeffs = constraints.coefficients.astype(np.complex128)
    if constraints.master_owners is None:
        owners = np.zeros(len(masters), dtype=np.int32)
    else:
        owners = constraints.master_owners.astype(np.int32)
    offsets = constraints.offsets.astype(np.int32)
    mpc.add_constraint(V, slaves, masters, coeffs, owners, offsets)
    mpc.finalize()

    E_scat = fem.Function(mpc.function_space, name="E_scat")
    problem = dolfinx_mpc.LinearProblem(
        a,
        L,
        mpc,
        bcs=[],
        u=E_scat,
        petsc_options_prefix=f"vector_maxwell_{cfg.case_name}_mpc_",
        petsc_options={
            "ksp_type": "preonly",
            "pc_type": "lu",
            "ksp_error_if_not_converged": True,
        },
    )
    E_scat = problem.solve()
    reason = int(problem.solver.getConvergedReason())
    iterations = int(problem.solver.getIterationNumber())
    log(f"dolfinx_mpc solver converged reason = {reason}")
    log(f"dolfinx_mpc solver iterations = {iterations}")
    return E_scat, {
        "solver_backend": "dolfinx_mpc_lowlevel_add_constraint",
        "dolfinx_mpc_num_local_slaves": int(mpc.num_local_slaves),
        "ksp_converged_reason": reason,
        "ksp_iterations": iterations,
        "reduced_linear_residual": None,
        "num_reduced_dofs": None,
    }


def _solve_mpc_auto(a, L, V, mesh_data, cfg: SimulationConfig, log):
    try:
        import dolfinx_mpc
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "请求使用 dolfinx_mpc，但当前 Python 环境未安装 dolfinx_mpc。"
        ) from exc

    def right_to_left(x):
        y = x.copy()
        y[0] -= cfg.period_x
        return y

    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.create_periodic_constraint_topological(
        V,
        mesh_data.facet_tags,
        cfg.tags.right,
        right_to_left,
        bcs=[],
        scale=np.complex128(cfg.floquet_phase),
    )
    mpc.finalize()

    E_scat = fem.Function(mpc.function_space, name="E_scat")
    problem = dolfinx_mpc.LinearProblem(
        a,
        L,
        mpc,
        bcs=[],
        u=E_scat,
        petsc_options_prefix=f"vector_maxwell_{cfg.case_name}_mpc_auto_",
        petsc_options={
            "ksp_type": "preonly",
            "pc_type": "lu",
            "ksp_error_if_not_converged": True,
        },
    )
    E_scat = problem.solve()
    reason = int(problem.solver.getConvergedReason())
    iterations = int(problem.solver.getIterationNumber())
    log(f"dolfinx_mpc automatic periodic solver converged reason = {reason}")
    log(f"dolfinx_mpc automatic periodic solver iterations = {iterations}")
    return E_scat, {
        "solver_backend": "dolfinx_mpc_auto_periodic_constraint",
        "dolfinx_mpc_num_local_slaves": int(mpc.num_local_slaves),
        "ksp_converged_reason": reason,
        "ksp_iterations": iterations,
        "reduced_linear_residual": None,
        "num_reduced_dofs": None,
    }


def _solve_manual(A_csr, b_np, constraints):
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(
            "manual constraint elimination is serial-only; use constraint_backend='mpc_official' for MPI."
        )
    solution, reduced_residual, reduced_size, reduced_nnz = (
        solve_with_constraints_with_stats(A_csr, b_np, constraints)
    )
    return solution, {
        "solver_backend": "manual_constraint_elimination",
        "reduced_linear_residual": reduced_residual,
        "num_reduced_dofs": int(reduced_size),
        "reduced_matrix_nnz": int(reduced_nnz),
        "ksp_converged_reason": None,
        "ksp_iterations": None,
    }


def run_case(
    cfg: SimulationConfig, out_dir: Path, constraint_backend: str = "manual"
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    start = time.perf_counter()

    def log(message: str):
        log_lines.append(message)
        if MPI.COMM_WORLD.rank == 0:
            PETSc.Sys.Print(message)

    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError(
            "当前 DOLFINx/PETSc 不是 complex 模式，不能求解复数频域 Maxwell 方程。"
        )
    if cfg.polarization_type.upper() != "TM":
        raise RuntimeError(
            "solve_vector_maxwell.run_case() only supports TM Ex/Ey; use solve_te_maxwell for TE."
        )

    log(f"case = {cfg.case_name}")
    log(f"constraint_backend = {constraint_backend}")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"DOLFINx scalar type = {default_scalar_type}")
    log(f"k0 = {cfg.k0:.12g}, kx = {cfg.kx}, ky = {cfg.ky}")
    log(f"omega = {cfg.omega:.12g}")
    log(f"polarization = {cfg.polarization}")
    log(f"scattering_background = {cfg.scattering_background}")
    log(
        f"dot(k, p) = {cfg.kx * cfg.polarization[0] + cfg.ky * cfg.polarization[1]:.6e}"
    )
    log(
        f"Floquet phase = {cfg.floquet_phase.real:.12g} + {cfg.floquet_phase.imag:.12g}j"
    )

    mesh_data = build_mesh(cfg, out_dir)
    msh = mesh_data.mesh
    tdim = msh.topology.dim
    num_cells = msh.topology.index_map(tdim).size_global

    curl_el = element(
        "N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type
    )
    V = fem.functionspace(msh, curl_el)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    log(f"mesh cells = {num_cells}")
    log(f"N1curl dofs = {num_dofs}")

    eps = relative_permittivity(mesh_data, cfg)
    eps_bg = background_relative_permittivity(mesh_data, cfg)
    E_background = background_field_function(V, cfg)
    constraints = build_floquet_constraints(V, mesh_data, cfg)
    log(f"Floquet constrained boundary dofs = {len(constraints.slave_dofs)}")
    log(f"max left/right y-pairing error = {constraints.max_pair_y_error:.3e}")
    log(f"max Floquet probe reconstruction error = {constraints.max_probe_error:.3e}")
    orientation_unique = np.unique(np.round(constraints.orientation_factors.real, 6))
    log(
        f"Nedelec orientation factors, rounded real parts = {orientation_unique.tolist()}"
    )

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
    d_top_pml = dx(cfg.tags.top_pml)
    d_bottom_pml = dx(cfg.tags.bottom_pml)

    eps_top_pml, mu_top_pml = top_pml_tensors(x, cfg)
    eps_bottom_pml, mu_bottom_pml = bottom_pml_tensors(x, cfg)
    a = (
        ufl.inner(curl_3d(u), curl_3d(v)) * d_physical
        - cfg.k0**2 * eps * ufl.inner(u, v) * d_physical
        + ufl.inner(ufl.inv(mu_top_pml) * curl_3d(u), curl_3d(v)) * d_top_pml
        - cfg.k0**2 * ufl.inner(eps_top_pml * field_3d(u), field_3d(v)) * d_top_pml
        + ufl.inner(ufl.inv(mu_bottom_pml) * curl_3d(u), curl_3d(v)) * d_bottom_pml
        - cfg.k0**2
        * ufl.inner(eps_bottom_pml * field_3d(u), field_3d(v))
        * d_bottom_pml
    )
    L = cfg.k0**2 * (eps - eps_bg) * ufl.inner(E_background, v) * d_physical

    if constraint_backend == "mpc_auto":
        log("solving constrained system with dolfinx_mpc automatic periodic constraint")
        E_scat, solver_info = _solve_mpc_auto(a, L, V, mesh_data, cfg, log)
        E_inc_output = background_field_function(E_scat.function_space, cfg)
    elif constraint_backend in ("mpc_official", "mpc_lowlevel"):
        log(
            "solving constrained system with dolfinx_mpc.MultiPointConstraint low-level data"
        )
        E_scat, solver_info = _solve_mpc(a, L, V, constraints, cfg, log)
        E_inc_output = background_field_function(E_scat.function_space, cfg)
    elif constraint_backend == "manual":
        log("assembling PETSc matrix/vector")
        A = fem_petsc.assemble_matrix(fem.form(a), bcs=[])
        A.assemble()
        b = fem_petsc.assemble_vector(fem.form(L))
        b.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)

        A_csr = _petsc_to_csr(A)
        b_np = b.array.copy()
        log("solving constrained system with C^H A C reduction + SciPy SuperLU")
        solution, solver_info = _solve_manual(A_csr, b_np, constraints)
        E_scat = fem.Function(V, name="E_scat")
        E_scat.x.array[:] = solution
        E_scat.x.scatter_forward()
        E_inc_output = E_background
    else:
        raise ValueError(
            "constraint_backend 必须是 'mpc_auto'、'mpc_official'、'mpc_lowlevel' 或 'manual'。"
        )

    E_total = fem.Function(E_scat.function_space, name="E_total")
    E_total.x.array[:] = E_inc_output.x.array[:] + E_scat.x.array[:]
    E_total.x.scatter_forward()

    field_metrics = save_fields_and_plots(
        mesh_data, cfg, E_inc_output, E_scat, E_total, out_dir
    )
    power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
    scatter_ratio = field_metrics["max_abs_E_scat"] / max(
        field_metrics["max_abs_E_inc"], 1e-30
    )
    floquet_mismatch_scat = dof_trace_mismatch(E_scat.x.array, constraints)
    floquet_mismatch_total = dof_trace_mismatch(E_total.x.array, constraints)
    elapsed = time.perf_counter() - start

    summary = {
        "case_name": cfg.case_name,
        "config": cfg.as_jsonable(),
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "num_reduced_dofs": solver_info["num_reduced_dofs"],
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver": solver_info["solver_backend"],
        "scattering_background": cfg.scattering_background,
        "reduced_linear_residual": solver_info["reduced_linear_residual"],
        "ksp_converged_reason": solver_info["ksp_converged_reason"],
        "ksp_iterations": solver_info["ksp_iterations"],
        "dolfinx_mpc_num_local_slaves": solver_info.get("dolfinx_mpc_num_local_slaves"),
        "elapsed_seconds": elapsed,
        "max_abs_E_inc": field_metrics["max_abs_E_inc"],
        "max_abs_E_scat": field_metrics["max_abs_E_scat"],
        "max_abs_E_total": field_metrics["max_abs_E_total"],
        "max_abs_E_scat_over_max_abs_E_inc": scatter_ratio,
        "power_metrics": power_metrics,
        "near_field_integrals": power_metrics.get("near_field_integrals", {}),
        "floquet_phase": cfg.floquet_phase,
        "floquet_max_probe_error": constraints.max_probe_error,
        "floquet_mismatch_scat_dof": floquet_mismatch_scat,
        "floquet_mismatch_total_dof": floquet_mismatch_total,
        "incident_transversality_dot_k_p": cfg.kx * cfg.polarization[0]
        + cfg.ky * cfg.polarization[1],
        "pml_type": (
            "top air PML and bottom substrate PML using the official DOLFINx-style complex coordinate "
            "map y' = y + i * alpha/k0 * y * (|y|-l_dom/2)/(l_pml/2-l_dom/2)^2, shifted to the physical "
            "domain center"
        ),
        "floquet_method": (
            "right boundary Nedelec edge dofs constrained to left dofs with complex phase "
            "by dolfinx_mpc.create_periodic_constraint_topological"
            if constraint_backend == "mpc_auto"
            else "right boundary Nedelec edge dofs constrained to left boundary H(curl) dofs "
            "with probe-reconstructed complex Floquet transformations; constraints assembled by dolfinx_mpc"
            if constraint_backend in ("mpc_official", "mpc_lowlevel")
            else "right boundary Nedelec edge dofs constrained to left boundary H(curl) dofs "
            "with probe-reconstructed complex Floquet transformations"
        ),
    }
    if solver_info["reduced_linear_residual"] is not None:
        log(f"reduced residual = {solver_info['reduced_linear_residual']:.3e}")
    log(f"max |E_inc| = {field_metrics['max_abs_E_inc']:.6e}")
    log(f"max |E_scat| = {field_metrics['max_abs_E_scat']:.6e}")
    log(f"max |E_total| = {field_metrics['max_abs_E_total']:.6e}")
    log(f"max |E_scat| / max |E_inc| = {scatter_ratio:.6e}")
    if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics):
        log(
            "power metrics: "
            f"R={power_metrics['R_total']:.6e}, "
            f"T={power_metrics['T_total']:.6e}, "
            f"R+T={power_metrics['R_plus_T']:.6e}"
        )
    elif power_metrics.get("skipped"):
        log(f"power metrics skipped: {power_metrics['reason']}")
    log(f"Floquet mismatch scat dof = {floquet_mismatch_scat:.3e}")
    log(f"Floquet mismatch total dof = {floquet_mismatch_total:.3e}")
    log(f"elapsed seconds = {elapsed:.3f}")

    if MPI.COMM_WORLD.rank == 0:
        (out_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "solver_log.txt").write_text(
            "\n".join(log_lines) + "\n", encoding="utf-8"
        )

    return summary
