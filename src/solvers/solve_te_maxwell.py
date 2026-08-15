from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse

from dolfinx import default_scalar_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config import SimulationConfig
from ..common.materials import background_relative_permittivity, relative_permittivity
from ..common.pml import bottom_scalar_pml_coefficients, top_scalar_pml_coefficients
from ..constraints.floquet_constraint import (
    dof_trace_mismatch,
    solve_with_constraints,
    solve_with_constraints_with_stats,
)
from ..constraints.floquet_scalar_constraint import build_scalar_floquet_constraints
from ..geometry.mesh_builder import build_mesh
from ..postprocessing.postprocess import save_scalar_fields_and_plots
from ..postprocessing.power_metrics import (
    compute_power_metrics,
    compute_te_dtn_port_power_metrics,
)
from ..postprocessing.te_reference import write_v3_2d_selected_fields
from .solve_port_maxwell import (
    CompressedTraceBank,
    _add_compressed_trace_to_rhs,
    _compress_trace_vector,
    _compressed_outer_trace_triplets,
)
from .solve_vector_maxwell import _json_default, _petsc_to_csr


def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1e-14 or (abs(root.imag) < 1e-14 and root.real < 0):
        root = -root
    return root


def te_incident_field_function(
    V, cfg: SimulationConfig, amplitude: complex = 1.0 + 0.0j
) -> fem.Function:
    Ez_inc = fem.Function(V, name="Ez_inc")

    def eval_field(x):
        return amplitude * np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))

    Ez_inc.interpolate(eval_field)
    return Ez_inc


def te_layered_background_field_function(V, cfg: SimulationConfig) -> fem.Function:
    Ez_bg = fem.Function(V, name="Ez_background_layered")
    beta_air = _positive_sqrt((cfg.k0 * cfg.n_air) ** 2 - cfg.kx**2)
    beta_sub = _positive_sqrt((cfg.k0 * cfg.n_substrate) ** 2 - cfg.kx**2)

    reflection = (beta_air - beta_sub) / (beta_air + beta_sub)
    transmission = 2.0 * beta_air / (beta_air + beta_sub)

    def eval_field(x):
        air_mask = x[1] >= cfg.substrate_y_max - 1e-12
        values = np.empty(x.shape[1], dtype=np.complex128)
        phase_inc = np.exp(1j * (cfg.kx * x[0] - beta_air * x[1]))
        phase_ref = np.exp(1j * (cfg.kx * x[0] + beta_air * x[1]))
        phase_trn = np.exp(1j * (cfg.kx * x[0] - beta_sub * x[1]))
        values[air_mask] = phase_inc[air_mask] + reflection * phase_ref[air_mask]
        values[~air_mask] = transmission * phase_trn[~air_mask]
        return values

    Ez_bg.interpolate(eval_field)
    return Ez_bg


def te_background_field_function(V, cfg: SimulationConfig) -> fem.Function:
    if cfg.scattering_background == "air":
        return te_incident_field_function(V, cfg)
    if cfg.scattering_background == "layered":
        return te_layered_background_field_function(V, cfg)
    raise ValueError("scattering_background must be 'air' or 'layered'.")


def _subtract_scalar_fields(total, reference):
    diff = fem.Function(total.function_space, name="E_scat")
    diff.x.array[:] = total.x.array[:] - reference.x.array[:]
    diff.x.scatter_forward()
    return diff


def _solve_scalar_mpc_auto(
    a, L, V, mesh_data, cfg: SimulationConfig, log, *, unknown_name: str
):
    try:
        import dolfinx_mpc
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Requested dolfinx_mpc, but dolfinx_mpc is not installed in this Python environment."
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

    solution = fem.Function(mpc.function_space, name=unknown_name)
    problem = dolfinx_mpc.LinearProblem(
        a,
        L,
        mpc,
        bcs=[],
        u=solution,
        petsc_options_prefix=f"te_maxwell_{cfg.case_name}_mpc_",
        petsc_options={
            "ksp_type": "preonly",
            "pc_type": "lu",
            "ksp_error_if_not_converged": True,
        },
    )
    solution = problem.solve()
    reason = int(problem.solver.getConvergedReason())
    iterations = int(problem.solver.getIterationNumber())
    log(f"dolfinx_mpc scalar periodic solver converged reason = {reason}")
    log(f"dolfinx_mpc scalar periodic solver iterations = {iterations}")
    return solution, {
        "solver_backend": "dolfinx_mpc_auto_scalar_periodic_constraint",
        "dolfinx_mpc_num_local_slaves": int(mpc.num_local_slaves),
        "ksp_converged_reason": reason,
        "ksp_iterations": iterations,
        "reduced_linear_residual": None,
        "num_reduced_dofs": None,
    }


def _solve_scalar_manual(a, L, V, constraints, log):
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(
            "TE manual constraint elimination is serial-only; use mpc_official for MPI."
        )
    log("assembling scalar PETSc matrix/vector")
    A = fem_petsc.assemble_matrix(fem.form(a), bcs=[])
    A.assemble()
    b = fem_petsc.assemble_vector(fem.form(L))
    b.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)

    A_csr = _petsc_to_csr(A)
    b_np = b.array.copy()
    log("solving scalar constrained system with C^H A C reduction + SciPy SuperLU")
    solution, reduced_residual, reduced_size = solve_with_constraints(
        A_csr, b_np, constraints
    )
    Ez = fem.Function(V, name="E_scat")
    Ez.x.array[:] = solution
    Ez.x.scatter_forward()
    return Ez, {
        "solver_backend": "manual_scalar_constraint_elimination",
        "reduced_linear_residual": reduced_residual,
        "num_reduced_dofs": int(reduced_size),
        "ksp_converged_reason": None,
        "ksp_iterations": None,
    }


def _scalar_fourier_trace_vector(V, mesh_data, tag: int, alpha: complex) -> np.ndarray:
    msh = mesh_data.mesh
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    phase = ufl.exp(PETSc.ScalarType(1j * alpha) * x[0])
    form = fem.form(phase * ufl.conj(v) * ds(tag))
    vec = fem_petsc.assemble_vector(form)
    vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    return vec.array.copy()


def _add_scalar_fourier_port_operators(
    A_csr, b_np, V, mesh_data, cfg: SimulationConfig, log
):
    if cfg.use_pml:
        raise RuntimeError(
            "TE Fourier DtN port requires use_pml=False; disable port_use_pml."
        )
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("TE Fourier DtN port is currently a serial manual operator.")
    if cfg.port_dtn_order_count < 0:
        raise RuntimeError("port_dtn_order_count must be non-negative.")

    order_count = cfg.port_dtn_order_count
    log(f"adding TE scalar Fourier DtN port orders m=-{order_count}...{order_count}")
    b_out = np.asarray(b_np, dtype=np.complex128).copy()
    modes: list[dict[str, object]] = []
    trace_vectors: CompressedTraceBank = {"top": {}, "bottom": {}}
    port_rows: list[np.ndarray] = []
    port_cols: list[np.ndarray] = []
    port_data: list[np.ndarray] = []

    for side, tag, refractive_index in (
        ("top", cfg.tags.outer_top, cfg.n_air),
        ("bottom", cfg.tags.outer_bottom, cfg.n_substrate),
    ):
        k_medium = cfg.k0 * refractive_index
        for order in range(-order_count, order_count + 1):
            alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
            beta = _positive_sqrt(k_medium**2 - alpha**2)
            q_mode = -1j * beta
            ell = _scalar_fourier_trace_vector(V, mesh_data, tag, alpha)
            trace = _compress_trace_vector(ell)
            trace_vectors[side][order] = trace
            rows, cols, data = _compressed_outer_trace_triplets(
                trace, q_mode / cfg.period_x
            )
            if len(data):
                port_rows.append(rows)
                port_cols.append(cols)
                port_data.append(data)
            del ell

            if side == "top" and order == 0:
                source_amplitude = (
                    2j
                    * beta
                    * cfg.port_incident_amplitude
                    * np.exp(1j * cfg.ky * cfg.y_max)
                )
                _add_compressed_trace_to_rhs(b_out, trace, -source_amplitude)

            modes.append(
                {
                    "side": side,
                    "order": order,
                    "alpha": alpha,
                    "beta": beta,
                    "q": q_mode,
                    "num_trace_dofs": int(len(trace["indices"])),
                    "port_outer_nnz": int(len(trace["indices"]) ** 2),
                    "trace_vector_storage": "compressed_nonzero_indices_and_values",
                    "dense_trace_size": int(trace["size"]),
                    "trace_compression_ratio": (
                        float(len(trace["indices"]) / trace["size"])
                        if int(trace["size"])
                        else 0.0
                    ),
                    "trace_cutoff": float(trace["cutoff"]),
                }
            )

    if port_data:
        A_port = sparse.coo_matrix(
            (
                np.concatenate(port_data),
                (np.concatenate(port_rows), np.concatenate(port_cols)),
            ),
            shape=A_csr.shape,
            dtype=np.complex128,
        ).tocsr()
    else:
        A_port = sparse.csr_matrix(A_csr.shape, dtype=np.complex128)
    return A_csr + A_port, b_out, modes, trace_vectors


def _maybe_serial_scalar_constraints(V, mesh_data, cfg: SimulationConfig):
    if mesh_data.mesh.comm.size == 1:
        return build_scalar_floquet_constraints(V, mesh_data, cfg)
    return None


def run_te_case(
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
        raise RuntimeError("Current DOLFINx/PETSc is not in complex mode.")
    if cfg.polarization_type.upper() != "TE":
        raise RuntimeError("run_te_case() only supports cfg.polarization_type='TE'.")

    log(f"case = {cfg.case_name}")
    log("formulation = TE scattered scalar Ez")
    log(f"constraint_backend = {constraint_backend}")
    log(f"k0 = {cfg.k0:.12g}, kx = {cfg.kx}, ky = {cfg.ky}")
    log(f"scattering_background = {cfg.scattering_background}")
    log(
        f"Floquet phase = {cfg.floquet_phase.real:.12g} + {cfg.floquet_phase.imag:.12g}j"
    )

    mesh_data = build_mesh(cfg, out_dir)
    msh = mesh_data.mesh
    tdim = msh.topology.dim
    num_cells = msh.topology.index_map(tdim).size_global

    scalar_degree = max(int(cfg.nedelec_degree), 1)
    V = fem.functionspace(msh, ("Lagrange", scalar_degree))
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    log(f"mesh cells = {num_cells}")
    log(f"scalar Lagrange dofs = {num_dofs}")

    eps = relative_permittivity(mesh_data, cfg)
    eps_bg = background_relative_permittivity(mesh_data, cfg)
    E_background = te_background_field_function(V, cfg)

    constraints = _maybe_serial_scalar_constraints(V, mesh_data, cfg)
    if constraints is not None:
        log(f"scalar Floquet constrained boundary dofs = {len(constraints.slave_dofs)}")
        log(
            f"max scalar left/right y-pairing error = {constraints.max_pair_y_error:.3e}"
        )

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
    d_top_pml = dx(cfg.tags.top_pml)
    d_bottom_pml = dx(cfg.tags.bottom_pml)

    C_top, eps_top_scaled = top_scalar_pml_coefficients(x, cfg)
    C_bottom, eps_bottom_scaled = bottom_scalar_pml_coefficients(x, cfg)
    a = (
        ufl.inner(ufl.grad(u), ufl.grad(v)) * d_physical
        - cfg.k0**2 * eps * ufl.inner(u, v) * d_physical
        + ufl.inner(C_top * ufl.grad(u), ufl.grad(v)) * d_top_pml
        - cfg.k0**2 * eps_top_scaled * ufl.inner(u, v) * d_top_pml
        + ufl.inner(C_bottom * ufl.grad(u), ufl.grad(v)) * d_bottom_pml
        - cfg.k0**2 * eps_bottom_scaled * ufl.inner(u, v) * d_bottom_pml
    )
    L = cfg.k0**2 * (eps - eps_bg) * ufl.inner(E_background, v) * d_physical

    if constraint_backend in ("mpc_official", "mpc_lowlevel", "mpc_auto"):
        log(
            "solving TE scalar scattered-field system with dolfinx_mpc automatic periodic constraint"
        )
        E_scat, solver_info = _solve_scalar_mpc_auto(
            a, L, V, mesh_data, cfg, log, unknown_name="E_scat"
        )
        E_inc_output = te_background_field_function(E_scat.function_space, cfg)
    elif constraint_backend == "manual":
        if constraints is None:
            constraints = build_scalar_floquet_constraints(V, mesh_data, cfg)
        E_scat, solver_info = _solve_scalar_manual(a, L, V, constraints, log)
        E_inc_output = E_background
    else:
        raise ValueError(
            "TE solver supports 'mpc_official', 'mpc_lowlevel', 'mpc_auto', or 'manual'."
        )

    E_total = fem.Function(E_scat.function_space, name="E_total")
    E_total.x.array[:] = E_inc_output.x.array[:] + E_scat.x.array[:]
    E_total.x.scatter_forward()

    field_metrics = save_scalar_fields_and_plots(
        mesh_data, cfg, E_inc_output, E_scat, E_total, out_dir
    )
    power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
    floquet_mismatch_scat = (
        dof_trace_mismatch(E_scat.x.array, constraints)
        if constraints is not None
        else float("nan")
    )
    floquet_mismatch_total = (
        dof_trace_mismatch(E_total.x.array, constraints)
        if constraints is not None
        else float("nan")
    )
    elapsed = time.perf_counter() - start
    scatter_ratio = field_metrics["max_abs_E_scat"] / max(
        field_metrics["max_abs_E_inc"], 1e-30
    )

    summary = {
        "case_name": cfg.case_name,
        "formulation": "te_scattered_field",
        "config": cfg.as_jsonable(),
        "num_mesh_cells": int(num_cells),
        "num_scalar_dofs": int(num_dofs),
        "num_reduced_dofs": solver_info["num_reduced_dofs"],
        "petsc_scalar_type": str(PETSc.ScalarType),
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
        "floquet_phase": cfg.floquet_phase,
        "floquet_mismatch_scat_dof": floquet_mismatch_scat,
        "floquet_mismatch_total_dof": floquet_mismatch_total,
        "te_field_model": "scalar Ez; physical electric field E=(0,0,Ez)",
        "te_pml_type": "scalar complex-coordinate PML with det(J)J^{-1}J^{-T} gradient tensor",
    }
    if solver_info["reduced_linear_residual"] is not None:
        log(f"reduced residual = {solver_info['reduced_linear_residual']:.3e}")
    log(f"max |E_inc| = {field_metrics['max_abs_E_inc']:.6e}")
    log(f"max |E_scat| = {field_metrics['max_abs_E_scat']:.6e}")
    log(f"max |E_total| = {field_metrics['max_abs_E_total']:.6e}")
    if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics):
        log(
            "power metrics: "
            f"R={power_metrics['R_total']:.6e}, "
            f"T={power_metrics['T_total']:.6e}, "
            f"R+T={power_metrics['R_plus_T']:.6e}"
        )
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


def run_te_port_case(
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
        raise RuntimeError("Current DOLFINx/PETSc is not in complex mode.")
    if cfg.polarization_type.upper() != "TE":
        raise RuntimeError(
            "run_te_port_case() only supports cfg.polarization_type='TE'."
        )
    if cfg.use_pml:
        raise RuntimeError(
            "port_use_pml=True is disabled for the TE port total-field solver. "
            "The port weak form places Robin/DtN conditions directly on the outer top/bottom boundaries."
        )
    if cfg.port_boundary_model not in ("robin", "dtn"):
        raise ValueError(
            "A concrete TE port case must use port_boundary_model='robin' or 'dtn'."
        )
    if cfg.port_boundary_model == "dtn" and constraint_backend in (
        "mpc_official",
        "mpc_lowlevel",
        "mpc_auto",
    ):
        raise RuntimeError(
            "TE Fourier DtN port currently supports the serial manual backend only."
        )

    log(f"case = {cfg.case_name}")
    log("formulation = TE port total field")
    log(f"constraint_backend = {constraint_backend}")
    log(f"use_pml = {cfg.use_pml}")
    log(f"k0 = {cfg.k0:.12g}, kx = {cfg.kx}, ky = {cfg.ky}")
    log(f"port_boundary_model = {cfg.port_boundary_model}")
    log(f"port_dtn_order_count = {cfg.port_dtn_order_count}")
    log(
        f"Floquet phase = {cfg.floquet_phase.real:.12g} + {cfg.floquet_phase.imag:.12g}j"
    )

    mesh_data = build_mesh(cfg, out_dir)
    msh = mesh_data.mesh
    tdim = msh.topology.dim
    num_cells = msh.topology.index_map(tdim).size_global

    scalar_degree = max(int(cfg.nedelec_degree), 1)
    V = fem.functionspace(msh, ("Lagrange", scalar_degree))
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    log(f"mesh cells = {num_cells}")
    log(f"scalar Lagrange dofs = {num_dofs}")

    eps = relative_permittivity(mesh_data, cfg)
    E_inc = te_incident_field_function(V, cfg, amplitude=cfg.port_incident_amplitude)
    constraints = _maybe_serial_scalar_constraints(V, mesh_data, cfg)
    if constraints is not None:
        log(f"scalar Floquet constrained boundary dofs = {len(constraints.slave_dofs)}")
        log(
            f"max scalar left/right y-pairing error = {constraints.max_pair_y_error:.3e}"
        )

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))

    k_air = cfg.k0 * cfg.n_air
    k_sub = cfg.k0 * cfg.n_substrate
    beta_air = _positive_sqrt(k_air**2 - cfg.kx**2)
    beta_sub = _positive_sqrt(k_sub**2 - cfg.kx**2)
    q_top = -1j * beta_air
    q_bottom = -1j * beta_sub

    a = (
        ufl.inner(ufl.grad(u), ufl.grad(v)) * d_physical
        - cfg.k0**2 * eps * ufl.inner(u, v) * d_physical
    )
    if cfg.port_boundary_model == "robin":
        incident = cfg.port_incident_amplitude * ufl.exp(
            1j * (cfg.kx * x[0] + cfg.ky * x[1])
        )
        top_source = 2j * beta_air * incident
        a = (
            a
            + ufl.inner(q_top * u, v) * ds(cfg.tags.outer_top)
            + ufl.inner(q_bottom * u, v) * ds(cfg.tags.outer_bottom)
        )
        L = -ufl.inner(top_source, v) * ds(cfg.tags.outer_top)
    else:
        L = PETSc.ScalarType(0.0) * ufl.conj(v) * ds(cfg.tags.outer_top)

    port_modes = []
    port_trace_vectors: CompressedTraceBank = {"top": {}, "bottom": {}}
    if constraint_backend in ("mpc_official", "mpc_lowlevel", "mpc_auto"):
        log(
            "solving TE scalar port system with dolfinx_mpc automatic periodic constraint"
        )
        E_total, solver_info = _solve_scalar_mpc_auto(
            a, L, V, mesh_data, cfg, log, unknown_name="E_total"
        )
        E_inc_output = te_incident_field_function(
            E_total.function_space, cfg, amplitude=cfg.port_incident_amplitude
        )
    elif constraint_backend == "manual":
        if constraints is None:
            constraints = build_scalar_floquet_constraints(V, mesh_data, cfg)
        log("assembling scalar port PETSc matrix/vector")
        A = fem_petsc.assemble_matrix(fem.form(a), bcs=[])
        A.assemble()
        A_csr = _petsc_to_csr(A)
        if cfg.port_boundary_model == "robin":
            b = fem_petsc.assemble_vector(fem.form(L))
            b.ghostUpdate(
                addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
            )
            b_np = b.array.copy()
        else:
            b_np = np.zeros(A_csr.shape[0], dtype=np.complex128)
        if cfg.port_boundary_model == "dtn":
            A_csr, b_np, port_modes, port_trace_vectors = (
                _add_scalar_fourier_port_operators(A_csr, b_np, V, mesh_data, cfg, log)
            )
        log(
            "solving TE scalar constrained port system with C^H A C reduction + SciPy SuperLU"
        )
        solution, reduced_residual, reduced_size, reduced_nnz = (
            solve_with_constraints_with_stats(A_csr, b_np, constraints)
        )
        solver_info = {
            "solver_backend": "manual_scalar_constraint_elimination",
            "reduced_linear_residual": reduced_residual,
            "num_reduced_dofs": int(reduced_size),
            "reduced_matrix_nnz": int(reduced_nnz),
            "ksp_converged_reason": None,
            "ksp_iterations": None,
        }
        E_total = fem.Function(V, name="E_total")
        E_total.x.array[:] = solution
        E_total.x.scatter_forward()
        E_inc_output = E_inc
    else:
        raise ValueError(
            "TE port solver supports 'mpc_official', 'mpc_lowlevel', 'mpc_auto', or 'manual'."
        )

    E_scat_output = _subtract_scalar_fields(E_total, E_inc_output)
    field_metrics = save_scalar_fields_and_plots(
        mesh_data, cfg, E_inc_output, E_scat_output, E_total, out_dir
    )
    power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
    dtn_port_power_metrics = {}
    dtn_port_vs_probe_power_difference = {}
    if cfg.port_boundary_model == "dtn":
        dtn_port_power_metrics = compute_te_dtn_port_power_metrics(
            mesh_data, cfg, E_total, out_dir, port_trace_vectors
        )
        if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics) and {
            "R_total",
            "T_total",
            "R_plus_T",
        }.issubset(dtn_port_power_metrics):
            dtn_port_vs_probe_power_difference = {
                "R_total_port_minus_probe": dtn_port_power_metrics["R_total"]
                - power_metrics["R_total"],
                "T_total_port_minus_probe": dtn_port_power_metrics["T_total"]
                - power_metrics["T_total"],
                "R_plus_T_port_minus_probe": dtn_port_power_metrics["R_plus_T"]
                - power_metrics["R_plus_T"],
            }
    v3_selected_fields = None
    if cfg.case_name == "task039_5nm_v3_1deg_s5":
        v3_selected_fields = write_v3_2d_selected_fields(cfg, E_total, out_dir)

    floquet_mismatch_total = (
        dof_trace_mismatch(E_total.x.array, constraints)
        if constraints is not None
        else float("nan")
    )
    elapsed = time.perf_counter() - start
    summary = {
        "case_name": cfg.case_name,
        "formulation": "te_port_total_field",
        "port_model": (
            "single Floquet fundamental mode scalar Robin port"
            if cfg.port_boundary_model == "robin"
            else "multi-order scalar Fourier Floquet DtN port"
        ),
        "config": cfg.as_jsonable(),
        "num_mesh_cells": int(num_cells),
        "num_scalar_dofs": int(num_dofs),
        "num_reduced_dofs": solver_info["num_reduced_dofs"],
        "linear_matrix_rows": (
            int(A_csr.shape[0]) if constraint_backend == "manual" else None
        ),
        "linear_matrix_nnz": (
            int(A_csr.nnz) if constraint_backend == "manual" else None
        ),
        "reduced_matrix_nnz": solver_info.get("reduced_matrix_nnz"),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "solver": solver_info["solver_backend"],
        "reduced_linear_residual": solver_info["reduced_linear_residual"],
        "ksp_converged_reason": solver_info["ksp_converged_reason"],
        "ksp_iterations": solver_info["ksp_iterations"],
        "dolfinx_mpc_num_local_slaves": solver_info.get("dolfinx_mpc_num_local_slaves"),
        "elapsed_seconds": elapsed,
        "max_abs_E_inc": field_metrics["max_abs_E_inc"],
        "max_abs_E_scat_reference": field_metrics["max_abs_E_scat"],
        "max_abs_E_total": field_metrics["max_abs_E_total"],
        "power_metrics": power_metrics,
        "dtn_port_power_metrics": dtn_port_power_metrics,
        "dtn_port_vs_probe_power_difference": dtn_port_vs_probe_power_difference,
        "floquet_phase": cfg.floquet_phase,
        "floquet_mismatch_total_dof": floquet_mismatch_total,
        "top_port_q": q_top,
        "bottom_port_q": q_bottom,
        "port_boundary_model": cfg.port_boundary_model,
        "port_dtn_order_count": cfg.port_dtn_order_count,
        "port_modes": port_modes,
        "te_field_model": "scalar Ez; physical electric field E=(0,0,Ez)",
    }
    if v3_selected_fields is not None:
        summary["v3_selected_fields"] = v3_selected_fields
    if solver_info["reduced_linear_residual"] is not None:
        log(f"reduced residual = {solver_info['reduced_linear_residual']:.3e}")
    log(f"max |E_inc| = {field_metrics['max_abs_E_inc']:.6e}")
    log(f"max |E_total| = {field_metrics['max_abs_E_total']:.6e}")
    if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics):
        log(
            "power metrics: "
            f"R={power_metrics['R_total']:.6e}, "
            f"T={power_metrics['T_total']:.6e}, "
            f"R+T={power_metrics['R_plus_T']:.6e}"
        )
    if {"R_total", "T_total", "R_plus_T"}.issubset(dtn_port_power_metrics):
        log(
            "TE DtN boundary-integral port power metrics: "
            f"R={dtn_port_power_metrics['R_total']:.6e}, "
            f"T={dtn_port_power_metrics['T_total']:.6e}, "
            f"R+T={dtn_port_power_metrics['R_plus_T']:.6e}"
        )
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
