from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows host fallback; Docker/Linux has resource.
    resource = None

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, default_scalar_type, fem, geometry
from dolfinx.fem import petsc as fem_petsc

from ..common.analytic_fields_3d import electric_field_code_values, fresnel_reference
from ..common.config_3d import SimulationConfig3D
from ..common.pml_3d import z_pml_tensors
from ..constraints.floquet_3d import DoubleFloquet3DData, build_double_floquet_mpc
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d
from ..postprocessing.diffraction_3d import compute_diffraction_orders_3d
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


def _max_rss_mb() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Linux reports ru_maxrss in KiB; macOS reports bytes. The Docker runtime
    # used for this project is Linux, but keep the conversion harmless elsewhere.
    if sys.platform == "darwin":
        return float(usage.ru_maxrss) / (1024.0 * 1024.0)
    return float(usage.ru_maxrss) / 1024.0


def _global_max_rss_mb(comm) -> float | None:
    local = _max_rss_mb()
    if local is None:
        return None
    return float(comm.allreduce(local, op=MPI.MAX))


def _direct_lu_petsc_options() -> dict[str, Any]:
    """Return the single supported 3D linear solve setting.

    The project is intentionally back to one direct solve path while Stage 4
    physics and diffraction postprocess are being debugged.  This keeps the
    PETSc setup explicit without exposing a user-facing solver profile.
    """
    return {
        "ksp_type": "preonly",
        "pc_type": "lu",
        "ksp_error_if_not_converged": True,
    }


def _available_parallel_lu_solver_type() -> str | None:
    """Return a PETSc LU package that can factor MPI matrices globally."""

    candidates = (
        ("mumps", "mumps"),
        ("superlu_dist", "superlu_dist"),
        ("strumpack", "strumpack"),
    )
    for package_name, solver_type in candidates:
        try:
            if PETSc.Sys.hasExternalPackage(package_name):
                return solver_type
        except Exception:
            continue
    return None


def _prepare_direct_lu_options_for_comm(comm: MPI.Intracomm) -> tuple[dict[str, Any], str | None, str | None]:
    """Make direct solver options explicit and safe for serial or MPI runs."""

    petsc_options = _direct_lu_petsc_options()
    if comm.size == 1:
        return petsc_options, None, None
    parallel_lu = _available_parallel_lu_solver_type()
    if parallel_lu is None:
        reason = (
            "MPI direct solve requested, but this PETSc build does not report MUMPS, "
            "SuperLU_DIST, or STRUMPACK. Refusing to run preonly+lu because it can "
            "produce partition-dependent local-factorization results."
        )
        return petsc_options, None, reason
    if parallel_lu is not None:
        petsc_options["pc_factor_mat_solver_type"] = parallel_lu
    return petsc_options, parallel_lu, None


def _pc_factor_solver_type(pc) -> str | None:
    try:
        return str(pc.getFactorSolverType())
    except Exception:
        return None


def _ksp_reason_name(reason: int) -> str:
    for name in dir(PETSc.KSP.ConvergedReason):
        if name.startswith("_"):
            continue
        try:
            if int(getattr(PETSc.KSP.ConvergedReason, name)) == reason:
                return name
        except (TypeError, ValueError):
            continue
    return str(reason)


def _petsc_matrix_stats(A) -> dict[str, Any]:
    A.assemble()
    rows, cols = A.getSize()
    info = A.getInfo()
    matrix_norm_frobenius = _petsc_object_norm(A, ("NORM_FROBENIUS", "FROBENIUS"))
    matrix_norm_infinity = _petsc_object_norm(A, ("NORM_INFINITY", "INFINITY"))
    nnz_used = info.get("nz_used")
    average_nnz_per_row = None
    memory_estimate_bytes = None
    if nnz_used is not None and rows > 0:
        average_nnz_per_row = float(nnz_used) / float(rows)
        # Rough AIJ/CSR storage estimate: complex128 value, column index, and
        # row pointer. PETSc's own memory field can be zero for some builds.
        memory_estimate_bytes = float(nnz_used) * (16.0 + 8.0) + float(rows + 1) * 8.0
    return {
        "matrix_rows": int(rows),
        "matrix_cols": int(cols),
        "matrix_nnz_used": float(nnz_used) if nnz_used is not None else None,
        "matrix_average_nnz_per_row": average_nnz_per_row,
        "matrix_memory_bytes": float(info.get("memory")) if info.get("memory") is not None else None,
        "matrix_memory_estimate_bytes": memory_estimate_bytes,
        "matrix_norm_frobenius": matrix_norm_frobenius,
        "matrix_norm_infinity": matrix_norm_infinity,
    }


def _petsc_object_norm(obj, names: tuple[str, ...]) -> float | None:
    for name in names:
        norm_type = getattr(PETSc.NormType, name, None)
        if norm_type is None:
            continue
        try:
            return float(obj.norm(norm_type))
        except Exception:
            continue
    try:
        return float(obj.norm())
    except Exception:
        return None


def _assembled_rhs_norm(L) -> float | None:
    """Assemble the original, unconstrained RHS for serial/MPI comparison."""

    try:
        vec = fem_petsc.assemble_vector(fem.form(L))
        vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
        return _petsc_object_norm(vec, ("NORM_2",))
    except Exception:
        return None


def _linear_system_diagnostics(A, b, x) -> dict[str, float | None]:
    """Measure the actually solved PETSc system after MPC assembly."""

    rhs_norm = _petsc_object_norm(b, ("NORM_2",))
    solution_norm = _petsc_object_norm(x, ("NORM_2",))
    residual_norm = None
    relative_residual = None
    try:
        residual = b.duplicate()
        A.mult(x, residual)
        residual.axpy(PETSc.ScalarType(-1.0), b)
        residual_norm = _petsc_object_norm(residual, ("NORM_2",))
        if residual_norm is not None and rhs_norm is not None:
            relative_residual = float(residual_norm / max(rhs_norm, 1.0e-30))
    except Exception:
        residual_norm = None
        relative_residual = None
    return {
        "linear_system_rhs_norm": rhs_norm,
        "linear_system_solution_norm": solution_norm,
        "linear_system_residual_norm": residual_norm,
        "linear_system_relative_residual": relative_residual,
    }


def _log_matrix_stats(matrix_stats: dict[str, Any], log) -> None:
    log(f"matrix rows = {matrix_stats['matrix_rows']}")
    log(f"matrix cols = {matrix_stats['matrix_cols']}")
    log(f"matrix nnz used = {matrix_stats['matrix_nnz_used']}")
    if matrix_stats["matrix_average_nnz_per_row"] is not None:
        log(f"average nnz per row = {matrix_stats['matrix_average_nnz_per_row']:.2f}")
    log(f"PETSc matrix memory bytes = {matrix_stats['matrix_memory_bytes']}")
    log(f"estimated AIJ matrix memory bytes = {matrix_stats['matrix_memory_estimate_bytes']}")
    log(f"matrix Frobenius norm = {matrix_stats['matrix_norm_frobenius']}")
    log(f"matrix infinity norm = {matrix_stats['matrix_norm_infinity']}")


def _log_solver_summary(summary: dict[str, Any], log) -> None:
    log("Linear solve summary:")
    log(f"  method               = {summary['linear_solve_method']}")
    log(f"  ksp_type             = {summary.get('actual_ksp_type')}")
    log(f"  pc_type              = {summary.get('actual_pc_type')}")
    log(f"  pc factor solver    = {summary.get('actual_pc_factor_solver_type')}")
    log(f"  converged            = {summary['ksp_converged']}")
    log(f"  converged reason     = {summary['ksp_converged_reason']}")
    log(f"  reason name          = {summary['ksp_converged_reason_name']}")
    log(f"  iterations           = {summary['ksp_iterations']}")
    residual = summary["solver_residual_norm"]
    if residual is None:
        log("  residual norm        = None")
    else:
        log(f"  residual norm        = {residual:.6e}")
    max_rss = summary["max_rss_mb"]
    if max_rss is None:
        log("  max RSS across ranks = None")
    else:
        log(f"  max RSS across ranks = {max_rss:.1f} MB")
    log(f"  official result      = {summary['official_result']}")
    log(f"  diagnostic only      = {summary['diagnostic_only']}")
    log(f"  case status          = {summary['case_status']}")


def _write_case_outputs(out_dir: Path, summary: dict[str, Any], log_lines: list[str], comm) -> None:
    if comm.rank == 0:
        (out_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "solver_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        if summary.get("diagnostic_only"):
            (out_dir / "NO_OFFICIAL_FIELD_OUTPUT.txt").write_text(
                "This case did not produce official field output because the solver did not produce a valid solution.\n"
                "Read run_summary.json and solver_log.txt for the failure reason.\n",
                encoding="utf-8",
            )
        else:
            (out_dir / "NO_OFFICIAL_FIELD_OUTPUT.txt").unlink(missing_ok=True)


def _clear_official_field_outputs(out_dir: Path, comm) -> None:
    if comm.rank == 0:
        patterns = (
            "fields_3d_for_paraview*.vtu",
            "fields_3d_for_paraview_parallel.pvd",
            "E_3d_numerical.bp",
            "H_3d_A_per_m_from_curl.bp",
            "vtx_3d_warning.txt",
        )
        for pattern in patterns:
            for path in out_dir.glob(pattern):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
    comm.barrier()


def plane_wave_electric_field(V, cfg: SimulationConfig3D) -> fem.Function:
    field = fem.Function(V, name="E_exact")

    def eval_field(x):
        return electric_field_code_values(cfg, x.T).T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field


def stage4_layered_background_field(V, cfg: SimulationConfig3D) -> fem.Function:
    """Stage-4 layered background used only inside the physical domain.

    The 2D scattered solver uses the background to form the grating contrast
    source and to reconstruct the physical total field.  It does not need a
    meaningful background field in the artificial PML.  Keeping the analytic
    Fresnel background in the PML made the ParaView total field look nonzero at
    the outer truncation boundary even when the scattered field was absorbed.
    For Stage 4, zero the background outside the physical z interval and let
    the PML display the solved scattered field only.
    """

    field = fem.Function(V, name="E_background_layered_physical_only")

    def eval_field(x):
        coords = x.T
        values = electric_field_code_values(cfg, coords)
        mask = (coords[:, 2] >= cfg.physical_z_min - 1.0e-12) & (
            coords[:, 2] <= cfg.physical_z_max + 1.0e-12
        )
        values[~mask] = 0.0
        return values.T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field


def _create_nedelec_space(msh, cfg: SimulationConfig3D):
    curl_el = element("N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type)
    return fem.functionspace(msh, curl_el)


def _add_reference_field_to_solution(E: fem.Function, cfg: SimulationConfig3D) -> None:
    """Reconstruct total field from a correction solve on E's own dof layout.

    ``dolfinx_mpc.LinearProblem`` may return a Function whose local vector
    layout differs from the original unconstrained function space used for
    boundary data.  Interpolate the analytic reference field on the solution
    space before adding it, so MPI-local array lengths always match.
    """

    reference = plane_wave_electric_field(E.function_space, cfg)
    if E.x.array.shape != reference.x.array.shape:
        raise RuntimeError(
            "Cannot reconstruct 3D reference-correction total field because the "
            "solution and reference-field local vectors still have different "
            f"shapes: {E.x.array.shape} vs {reference.x.array.shape}."
        )
    E.x.array[:] += reference.x.array
    E.x.scatter_forward()


def _combine_fields(primary: fem.Function, added: fem.Function, name: str) -> fem.Function:
    if primary.x.array.shape != added.x.array.shape:
        raise RuntimeError(
            f"Cannot combine fields {primary.name!r} and {added.name!r}; local vector shapes differ: "
            f"{primary.x.array.shape} vs {added.x.array.shape}."
        )
    total = fem.Function(primary.function_space, name=name)
    total.x.array[:] = primary.x.array
    total.x.array[:] += added.x.array
    total.x.scatter_forward()
    return total


def _function_coefficient_norm(field: fem.Function) -> float:
    index_map = field.function_space.dofmap.index_map
    block_size = field.function_space.dofmap.index_map_bs
    owned_size = index_map.size_local * block_size
    owned = np.asarray(field.x.array[:owned_size], dtype=np.complex128)
    local = float(np.real(np.vdot(owned, owned)))
    return float(np.sqrt(field.function_space.mesh.comm.allreduce(local, op=MPI.SUM)))


def _sample_field_at_points(function, points: np.ndarray) -> np.ndarray:
    msh = function.function_space.mesh
    comm = msh.comm
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    local_indices: list[int] = []
    local_cells: list[int] = []
    for i in range(len(points)):
        links = collisions.links(i)
        if len(links) >= 1:
            local_indices.append(i)
            local_cells.append(int(links[0]))

    if local_indices:
        local_points = points[np.asarray(local_indices, dtype=np.int32)]
        local_values = function.eval(local_points, np.asarray(local_cells, dtype=np.int32))
        local_values = np.asarray(local_values, dtype=np.complex128)
        if local_values.ndim == 1:
            local_values = local_values.reshape((len(local_points), -1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_values))
    width = 0
    for _, values in packets:
        if values.size:
            width = int(values.shape[1])
            break
    if width == 0:
        raise RuntimeError("No rank could evaluate the requested 3D probe points.")

    values = np.zeros((len(points), width), dtype=np.complex128)
    filled = np.zeros(len(points), dtype=bool)
    for indices, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index]:
                values[int(point_index)] = packet_values[row]
                filled[int(point_index)] = True
    if not np.all(filled):
        missing = np.flatnonzero(~filled)[:5]
        examples = ", ".join(str(points[i].tolist()) for i in missing)
        raise RuntimeError(f"No mesh cell found for {np.count_nonzero(~filled)} 3D probe points: {examples}")
    return values[:, :3]


def _relative_norm_error(actual: np.ndarray, expected: np.ndarray) -> float:
    diff = actual - expected
    denom = max(float(np.linalg.norm(actual)), float(np.linalg.norm(expected)), 1.0e-30)
    return float(np.linalg.norm(diff) / denom)


def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1.0e-14 or (abs(root.imag) < 1.0e-14 and root.real < 0.0):
        root = -root
    return complex(root)


def _mode_basis(cfg: SimulationConfig3D, n_medium: complex, vertical_sign: int) -> tuple[np.ndarray, np.ndarray]:
    q = _positive_sqrt((cfg.k0 * complex(n_medium)) ** 2 - cfg.kx**2 - cfg.ky**2)
    kvec = np.asarray((cfg.kx, cfg.ky, vertical_sign * q), dtype=np.complex128)
    kind = cfg.polarization_kind.lower()
    if cfg.geometry_kind == "fresnel_interface" and kind != "p":
        # Fresnel reference fields are defined for s/p polarizations.  Treat a
        # legacy "custom" preset as s so the numerical modal fit uses the same
        # basis as analytic_fields_3d._fresnel_components.
        polarization = cfg.s_polarization_vector
    elif kind == "s":
        polarization = cfg.s_polarization_vector
    elif kind == "p":
        direction = kvec / (cfg.k0 * complex(n_medium))
        polarization = np.cross(direction, cfg.s_polarization_vector)
    else:
        polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
        if abs(kvec[0]) + abs(kvec[1]) > 1.0e-14:
            denom = np.dot(kvec, kvec)
            if abs(denom) > 1.0e-30:
                polarization = polarization - kvec * (np.dot(kvec, polarization) / denom)
    norm = np.sqrt(np.sum(np.abs(polarization) ** 2))
    if norm <= 0.0:
        raise ValueError("Cannot build a nonzero 3D modal polarization vector.")
    return kvec, polarization / norm


def incident_air_plane_wave_field(V, cfg: SimulationConfig3D) -> fem.Function:
    """Incident air-region plane wave used by the Fresnel scattered-field solve.

    This field contains only the known incoming wave in the air background.  It
    deliberately excludes Fresnel reflected and transmitted analytic fields.
    """

    k_inc, p_inc = _mode_basis(cfg, cfg.n_air, vertical_sign=-1)
    amplitude = complex(cfg.incident_amplitude)
    field = fem.Function(V, name="E_incident_air")

    def eval_field(x):
        coords = x.T
        phase = np.exp(1j * (k_inc[0] * coords[:, 0] + k_inc[1] * coords[:, 1] + k_inc[2] * coords[:, 2]))
        return (amplitude * phase[:, None] * p_inc[None, :]).T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field


def _sample_grid_points(cfg: SimulationConfig3D, z_values: np.ndarray, nx: int = 4, ny: int = 4) -> np.ndarray:
    x_values = np.linspace(cfg.x_min + 0.2 * (cfg.x_max - cfg.x_min), cfg.x_min + 0.8 * (cfg.x_max - cfg.x_min), nx)
    y_values = np.linspace(cfg.y_min + 0.2 * (cfg.y_max - cfg.y_min), cfg.y_min + 0.8 * (cfg.y_max - cfg.y_min), ny)
    points = [[x, y, z] for z in z_values for x in x_values for y in y_values]
    return np.asarray(points, dtype=np.float64)


def _cell_tag_volumes(msh, mesh_data, cfg: SimulationConfig3D) -> dict[str, float]:
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    tag_items = {
        "air": cfg.tags.air,
        "substrate": cfg.tags.substrate,
        "grating": cfg.tags.grating,
        "top_pml": cfg.tags.top_pml,
        "bottom_pml": cfg.tags.bottom_pml,
    }
    volumes: dict[str, float] = {}
    for name, tag in tag_items.items():
        local = fem.assemble_scalar(fem.form(ufl.as_ufl(1.0) * dx(tag)))
        global_value = msh.comm.allreduce(local, op=MPI.SUM)
        volumes[name] = float(np.real(global_value))
    return volumes


def _interpolated_mode_field(function_space, mode_k: np.ndarray, mode_polarization: np.ndarray) -> fem.Function:
    field = fem.Function(function_space, name="mode_calibration")

    def eval_field(x):
        coords = x.T
        phase = np.exp(1j * (mode_k[0] * coords[:, 0] + mode_k[1] * coords[:, 1] + mode_k[2] * coords[:, 2]))
        return (phase[:, None] * mode_polarization[None, :]).T

    field.interpolate(eval_field)
    return field


def _fit_plane_wave_modes(
    E,
    cfg: SimulationConfig3D,
    points: np.ndarray,
    modes: list[tuple[str, np.ndarray, np.ndarray]],
    *,
    calibrate_fe_response: bool = True,
):
    values = _sample_field_at_points(E, points)
    rows = []
    rhs = []
    for point, value in zip(points, values):
        phase_xy = cfg.kx * point[0] + cfg.ky * point[1]
        for component in range(3):
            rows.append(
                [
                    mode_polarization[component] * np.exp(1j * (phase_xy + mode_k[2] * point[2]))
                    for _, mode_k, mode_polarization in modes
                ]
            )
            rhs.append(value[component])
    A = np.asarray(rows, dtype=np.complex128)
    b = np.asarray(rhs, dtype=np.complex128)
    amplitudes, *_ = np.linalg.lstsq(A, b, rcond=None)
    residual = float(np.linalg.norm(A @ amplitudes - b) / max(float(np.linalg.norm(b)), 1.0e-30))

    if calibrate_fe_response and modes:
        # Point-sampling a low-order Nedelec interpolation of a plane wave can
        # bias modal amplitudes by several percent even when the field itself is
        # the correct FE representation.  Calibrate the fit by measuring how
        # each unit-amplitude mode is seen after interpolation in this exact
        # function space, then invert that small response matrix.
        response_columns = []
        for _, mode_k, mode_polarization in modes:
            mode_field = _interpolated_mode_field(E.function_space, mode_k, mode_polarization)
            apparent, _ = _fit_plane_wave_modes(
                mode_field,
                cfg,
                points,
                modes,
                calibrate_fe_response=False,
            )
            response_columns.append([apparent[name] for name, _, _ in modes])
        response = np.asarray(response_columns, dtype=np.complex128).T
        if response.size:
            condition = np.linalg.cond(response)
            if np.isfinite(condition) and condition < 1.0e12:
                amplitudes = np.linalg.solve(response, amplitudes)
    return {name: complex(value) for value, (name, _, _) in zip(amplitudes, modes)}, residual


def _floquet_probe_metrics(floquet_data: DoubleFloquet3DData) -> dict[str, float]:
    # Stage 2 now uses explicit edge topology for Floquet constraints, so the
    # old probe-fit mismatch is replaced by the maximum edge midpoint pairing
    # error measured during dof matching.
    x_mismatch = float(floquet_data.max_edge_midpoint_pairing_error)
    y_mismatch = float(floquet_data.max_edge_midpoint_pairing_error)
    return {
        "floquet_x_face_mismatch": x_mismatch,
        "floquet_y_face_mismatch": y_mismatch,
        "floquet_edge_corner_mismatch": floquet_data.edge_corner_phase_mismatch,
    }


def _pml_probe_metrics(E, cfg: SimulationConfig3D) -> dict[str, float | None]:
    if not cfg.use_pml:
        return {
            "pml_reflection_proxy": None,
            "pml_decay_ratio_top": None,
            "pml_decay_ratio_bottom": None,
        }

    center_x = 0.5 * (cfg.x_min + cfg.x_max)
    center_y = 0.5 * (cfg.y_min + cfg.y_max)
    metrics: dict[str, float | None] = {}
    physical_z = np.linspace(cfg.physical_z_min + 0.15 * (cfg.physical_z_max - cfg.physical_z_min),
                             cfg.physical_z_max - 0.15 * (cfg.physical_z_max - cfg.physical_z_min), 6)
    physical_points = np.asarray([[center_x, center_y, z] for z in physical_z], dtype=np.float64)
    numerical = _sample_field_at_points(E, physical_points)
    exact = electric_field_code_values(cfg, physical_points)
    metrics["pml_reference_relative_error"] = _relative_norm_error(numerical, exact)

    # Fit the numerical physical-region field to downward/upward plane waves.
    # The ratio |A_up|/|A_down| is a more meaningful PML reflection proxy than
    # simply comparing against the manufactured field point by point.
    k_down, p_down = _mode_basis(cfg, cfg.n_air, vertical_sign=-1)
    k_up, p_up = _mode_basis(cfg, cfg.n_air, vertical_sign=1)
    fit_z = np.linspace(
        cfg.physical_z_min + 0.2 * (cfg.physical_z_max - cfg.physical_z_min),
        cfg.physical_z_max - 0.2 * (cfg.physical_z_max - cfg.physical_z_min),
        5,
    )
    amplitudes, fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        _sample_grid_points(cfg, fit_z, nx=3, ny=3),
        [("down", k_down, p_down), ("up", k_up, p_up)],
    )
    down_abs = abs(amplitudes["down"])
    up_abs = abs(amplitudes["up"])
    metrics["pml_reflection_proxy"] = float(up_abs / max(down_abs, 1.0e-30))
    metrics["pml_mode_fit_residual"] = fit_residual
    metrics["pml_downward_amplitude_abs"] = float(down_abs)
    metrics["pml_upward_amplitude_abs"] = float(up_abs)

    if cfg.pml_top_thickness > 0.0:
        top_inner = np.asarray([[center_x, center_y, cfg.physical_z_max + 0.05 * cfg.pml_top_thickness]])
        top_outer = np.asarray([[center_x, center_y, cfg.domain_z_max - 0.05 * cfg.pml_top_thickness]])
        metrics["pml_decay_ratio_top"] = float(
            np.linalg.norm(_sample_field_at_points(E, top_outer)) / max(np.linalg.norm(_sample_field_at_points(E, top_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_top"] = None

    if cfg.pml_bottom_thickness > 0.0:
        bottom_inner = np.asarray([[center_x, center_y, cfg.physical_z_min - 0.05 * cfg.pml_bottom_thickness]])
        bottom_outer = np.asarray([[center_x, center_y, cfg.domain_z_min + 0.05 * cfg.pml_bottom_thickness]])
        metrics["pml_decay_ratio_bottom"] = float(
            np.linalg.norm(_sample_field_at_points(E, bottom_outer))
            / max(np.linalg.norm(_sample_field_at_points(E, bottom_inner)), 1.0e-30)
        )
    else:
        metrics["pml_decay_ratio_bottom"] = None
    return metrics


def _stage4_scattered_pml_metrics(E_sca, cfg: SimulationConfig3D) -> dict[str, float | None | str]:
    """Measure PML behavior from the scattered field, not the total field.

    In Stage 4, ``E_total = E_bg + E_scat``.  The PML is meant to absorb the
    outgoing scattered field.  The layered background field is analytically
    continued into the artificial PML and may have nonzero or even large
    magnitude there, so judging the PML from ``E_total`` is misleading.
    """

    metrics: dict[str, float | None | str] = {
        "pml_metric_field": "E_scat",
        "pml_metric_note": "Stage 4 PML diagnostics use E_scat; E_total/E_b in PML are artificial-coordinate fields.",
        "pml_reference_relative_error": None,
        "pml_reflection_proxy": None,
        "pml_decay_ratio_top": None,
        "pml_decay_ratio_bottom": None,
        "pml_scattered_decay_ratio_top": None,
        "pml_scattered_decay_ratio_bottom": None,
    }
    if E_sca is None or not cfg.use_pml:
        return metrics

    center_x = 0.5 * (cfg.x_min + cfg.x_max)
    center_y = 0.5 * (cfg.y_min + cfg.y_max)
    if cfg.pml_top_thickness > 0.0:
        top_inner = np.asarray([[center_x, center_y, cfg.physical_z_max + 0.05 * cfg.pml_top_thickness]])
        top_outer = np.asarray([[center_x, center_y, cfg.domain_z_max - 0.05 * cfg.pml_top_thickness]])
        top_inner_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, top_inner)))
        top_outer_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, top_outer)))
        metrics["pml_scattered_inner_norm_top"] = top_inner_norm
        metrics["pml_scattered_outer_norm_top"] = top_outer_norm
        metrics["pml_scattered_decay_ratio_top"] = top_outer_norm / max(top_inner_norm, 1.0e-30)
        metrics["pml_decay_ratio_top"] = metrics["pml_scattered_decay_ratio_top"]

    if cfg.pml_bottom_thickness > 0.0:
        bottom_inner = np.asarray([[center_x, center_y, cfg.physical_z_min - 0.05 * cfg.pml_bottom_thickness]])
        bottom_outer = np.asarray([[center_x, center_y, cfg.domain_z_min + 0.05 * cfg.pml_bottom_thickness]])
        bottom_inner_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, bottom_inner)))
        bottom_outer_norm = float(np.linalg.norm(_sample_field_at_points(E_sca, bottom_outer)))
        metrics["pml_scattered_inner_norm_bottom"] = bottom_inner_norm
        metrics["pml_scattered_outer_norm_bottom"] = bottom_outer_norm
        metrics["pml_scattered_decay_ratio_bottom"] = bottom_outer_norm / max(bottom_inner_norm, 1.0e-30)
        metrics["pml_decay_ratio_bottom"] = metrics["pml_scattered_decay_ratio_bottom"]
    return metrics


def _fresnel_numerical_metrics(E, cfg: SimulationConfig3D) -> dict[str, Any]:
    """Extract Fresnel R/T from the solved 3D field by modal fitting."""
    ref = fresnel_reference(cfg)
    n1 = complex(cfg.n_air)
    n2 = complex(cfg.substrate_index)
    k_inc, p_inc = _mode_basis(cfg, n1, vertical_sign=-1)
    k_ref, p_ref = _mode_basis(cfg, n1, vertical_sign=1)
    k_trn, p_trn = _mode_basis(cfg, n2, vertical_sign=-1)

    top_height = cfg.physical_z_max - cfg.interface_z
    bottom_height = cfg.interface_z - cfg.physical_z_min
    top_z = np.linspace(cfg.interface_z + 0.25 * top_height, cfg.interface_z + 0.75 * top_height, 4)
    bottom_z = np.linspace(cfg.interface_z - 0.75 * bottom_height, cfg.interface_z - 0.25 * bottom_height, 4)
    top_points = _sample_grid_points(cfg, top_z, nx=4, ny=4)
    bottom_points = _sample_grid_points(cfg, bottom_z, nx=4, ny=4)
    top_amplitudes, top_fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        top_points,
        [("incident", k_inc, p_inc), ("reflected", k_ref, p_ref)],
    )
    bottom_amplitudes, bottom_fit_residual = _fit_plane_wave_modes(
        E,
        cfg,
        bottom_points,
        [("transmitted", k_trn, p_trn)],
    )

    incident = top_amplitudes["incident"]
    reflected = top_amplitudes["reflected"]
    transmitted = bottom_amplitudes["transmitted"]
    cos_i = max(float(np.cos(cfg.theta_rad)), 1.0e-30)
    sin_t = n1 / n2 * np.sin(cfg.theta_rad)
    cos_t = _positive_sqrt(1.0 - sin_t**2)
    admittance_ratio = float(np.real((n2 * cos_t) / (n1 * cos_i)))
    # These are numerical postprocess values.  The analytic Fresnel values are
    # only used below as the reference to compute errors.
    R_total = float(abs(reflected / incident) ** 2)
    T_total = float(admittance_ratio * abs(transmitted / incident) ** 2)
    return {
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "fresnel_R": ref["R"],
        "fresnel_T": ref["T"],
        "fresnel_R_error": abs(R_total - float(ref["R"])),
        "fresnel_T_error": abs(T_total - float(ref["T"])),
        "fresnel_R_plus_T_error": abs(R_total + T_total - float(ref["R_plus_T"])),
        "fresnel_reference": ref,
        "fresnel_incident_amplitude_abs": float(abs(incident)),
        "fresnel_reflected_amplitude_abs": float(abs(reflected)),
        "fresnel_transmitted_amplitude_abs": float(abs(transmitted)),
        "fresnel_top_mode_fit_residual": top_fit_residual,
        "fresnel_bottom_mode_fit_residual": bottom_fit_residual,
        "fresnel_top_sampling_z_min": float(np.min(top_z)),
        "fresnel_top_sampling_z_max": float(np.max(top_z)),
        "fresnel_bottom_sampling_z_min": float(np.min(bottom_z)),
        "fresnel_bottom_sampling_z_max": float(np.max(bottom_z)),
        "fresnel_top_sampling_point_count": int(len(top_points)),
        "fresnel_bottom_sampling_point_count": int(len(bottom_points)),
        "fresnel_top_sampling_margin_to_interface": float(np.min(top_z) - cfg.interface_z),
        "fresnel_top_sampling_margin_to_top_pml": float(cfg.physical_z_max - np.max(top_z)),
        "fresnel_bottom_sampling_margin_to_interface": float(cfg.interface_z - np.max(bottom_z)),
        "fresnel_bottom_sampling_margin_to_bottom_pml": float(np.min(bottom_z) - cfg.physical_z_min),
        "rt_metric_note": "R/T are fitted from the numerical 3D field in uniform layers and compared with Fresnel theory.",
    }


def _stage2_reference_metrics(E, cfg: SimulationConfig3D, field_metrics: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if cfg.geometry_kind == "fresnel_interface":
        metrics.update(_fresnel_numerical_metrics(E, cfg))
    elif cfg.use_pml:
        metrics.update(
            {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "fresnel_R": None,
                "fresnel_T": None,
                "fresnel_R_error": None,
                "fresnel_T_error": None,
            }
        )
    metrics["fresnel_field_relative_max_error"] = field_metrics.get("relative_max_abs_E_error")
    return metrics


def run_fresnel_analytic_postprocess_sanity(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, Any]:
    """Check Fresnel R/T fitting by interpolating the analytic total field only.

    This diagnostic intentionally does not assemble or solve Maxwell.  It uses
    the same mesh, Nedelec function space, and ``_fresnel_numerical_metrics``
    modal fitting path as the real 2C solve.  If this sanity check fails, the
    issue is in postprocessing, polarization basis, sampling, or T
    normalization rather than in the PDE solve.
    """

    if cfg.geometry_kind != "fresnel_interface":
        raise ValueError("Fresnel analytic postprocess sanity requires geometry_kind='fresnel_interface'.")
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    start = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    msh = mesh_data.mesh
    V = _create_nedelec_space(msh, cfg)
    E_analytic = plane_wave_electric_field(V, cfg)
    metrics = _fresnel_numerical_metrics(E_analytic, cfg)
    field_norm = _function_coefficient_norm(E_analytic)
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    summary: dict[str, Any] = {
        "case_name": cfg.case_name,
        "stage": "stage2_3d_fresnel_analytic_postprocess_sanity",
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "completed",
        "official_result": False,
        "diagnostic_only": True,
        "postprocess_only": True,
        "postprocess_sanity_kind": "fresnel_analytic_total_field_interpolation",
        "num_mesh_cells": msh.topology.index_map(msh.topology.dim).size_global,
        "num_nedelec_dofs": V.dofmap.index_map.size_global * V.dofmap.index_map_bs,
        "mesh_cell_type_actual": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": mesh_data.mesh_cells_resolved,
        "z_alignment_warnings": mesh_data.z_alignment_warnings,
        "domain_tag_volumes": _cell_tag_volumes(msh, mesh_data, cfg),
        "E_analytic_norm": field_norm,
        "elapsed_seconds": elapsed,
        "max_rss_mb": _global_max_rss_mb(comm),
        **metrics,
    }
    summary["fresnel_postprocess_sanity_thresholds"] = {
        "fresnel_R_error": 1.0e-8,
        "fresnel_T_error": 1.0e-8,
        "fresnel_top_mode_fit_residual": 1.0e-1,
        "fresnel_bottom_mode_fit_residual": 1.0e-1,
    }
    summary["fresnel_postprocess_sanity_pass"] = bool(
        summary["fresnel_R_error"] < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_R_error"]
        and summary["fresnel_T_error"] < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_T_error"]
        and summary["fresnel_top_mode_fit_residual"]
        < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_top_mode_fit_residual"]
        and summary["fresnel_bottom_mode_fit_residual"]
        < summary["fresnel_postprocess_sanity_thresholds"]["fresnel_bottom_mode_fit_residual"]
    )
    if comm.rank == 0:
        (out_dir / "fresnel_analytic_postprocess_sanity.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    return summary


def _stage_label(cfg: SimulationConfig3D) -> str:
    if cfg.stage_case == "stage1_airbox":
        return "stage1_3d_airbox"
    if cfg.stage_case.startswith("stage4_"):
        return f"stage4_3d_{cfg.stage_case.removeprefix('stage4_')}"
    return f"stage2_3d_{cfg.stage_case}"


def _summary_base_fields(cfg: SimulationConfig3D, comm: MPI.Intracomm) -> dict[str, Any]:
    """Small duplicated-at-top fields used by test scripts and reports.

    The complete configuration remains under ``summary["config"]``.  These
    top-level copies keep validation scripts simple and avoid fragile lookups
    through the nested JSON structure.
    """
    return {
        "stage_case": cfg.stage_case,
        "geometry_kind": cfg.geometry_kind,
        "mpi_size": comm.size,
        "mpi_rank": comm.rank,
        "mesh_target_size": cfg.mesh_target_size,
        "mesh_cell_type": cfg.mesh_cell_type,
        "mesh_cell_type_resolved": cfg.mesh_cell_type_resolved,
        "floquet_constraint_mode_requested": cfg.floquet_constraint_mode_requested,
        "nedelec_degree": cfg.nedelec_degree,
        "visualization_degree": cfg.visualization_degree,
        "incident_theta_deg": cfg.incident_theta_deg,
        "incident_phi_deg": cfg.incident_phi_deg,
        "polarization_kind": cfg.polarization_kind,
        "length_unit": "nm",
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
    }


def _build_variational_forms(
    msh,
    mesh_data,
    cfg: SimulationConfig3D,
    V,
    *,
    field_formulation: str = "total_field",
    incident_field: fem.Function | None = None,
):
    """Assemble the shared Stage-1/Stage-2 curl-curl Maxwell weak form.

    Cell tags decide which material tensor is used.  The x/y periodicity is not
    part of this form; it is imposed later through ``dolfinx_mpc`` constraints.
    """
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    zero = fem.Constant(msh, np.zeros(3, dtype=default_scalar_type))
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    a = PETSc.ScalarType(0.0) * ufl.inner(u, v) * dx

    def add_isotropic(tag: int, eps_r: complex):
        return (
            PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(curl_u, curl_v) * dx(tag)
            - cfg.k0**2 * PETSc.ScalarType(eps_r) * ufl.inner(u, v) * dx(tag)
        )

    a += add_isotropic(cfg.tags.air, cfg.eps_r)
    a += add_isotropic(cfg.tags.substrate, cfg.substrate_index**2)
    a += add_isotropic(cfg.tags.grating, cfg.grating_index**2)
    if float(cfg.divergence_penalty) > 0.0:
        d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
        a += PETSc.ScalarType(cfg.divergence_penalty) * ufl.inner(ufl.div(u), ufl.div(v)) * d_physical

    # PML cells use the same unknown E, but with the z-stretched material
    # tensors.  Top and bottom are tagged separately so the sign convention is
    # testable and visible in ParaView through domain_tag.
    x = ufl.SpatialCoordinate(msh)
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        eps_top, mu_top = z_pml_tensors(x, cfg, "top", cfg.eps_r)
        a += ufl.inner(ufl.inv(mu_top) * curl_u, curl_v) * dx(cfg.tags.top_pml)
        a += -cfg.k0**2 * ufl.inner(eps_top * u, v) * dx(cfg.tags.top_pml)
    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        eps_bottom_background = (
            cfg.substrate_index**2
            if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}
            else cfg.eps_r
        )
        eps_bottom, mu_bottom = z_pml_tensors(x, cfg, "bottom", eps_bottom_background)
        a += ufl.inner(ufl.inv(mu_bottom) * curl_u, curl_v) * dx(cfg.tags.bottom_pml)
        a += -cfg.k0**2 * ufl.inner(eps_bottom * u, v) * dx(cfg.tags.bottom_pml)
    if (
        field_formulation == "layered_scattered"
        and cfg.stage4_boundary_model.lower() == "robin0"
    ):
        # Diagnostic truncation for Stage 4 only: no PML cells are present, so
        # a zero-order impedance term approximates outgoing waves at the top
        # and bottom planes.  The official Stage-4 path remains the 2D-like PML
        # weak form without this surface term.
        u_t = ufl.as_vector((u[0], u[1], 0.0))
        v_t = ufl.as_vector((v[0], v[1], 0.0))
        a += PETSc.ScalarType(1j * cfg.k0 * complex(cfg.n_air)) * ufl.inner(u_t, v_t) * ds(cfg.tags.z_max)
        a += PETSc.ScalarType(1j * cfg.k0 * complex(cfg.substrate_index)) * ufl.inner(u_t, v_t) * ds(cfg.tags.z_min)
    L = ufl.inner(zero, v) * dx
    if field_formulation == "incident_scattered":
        if incident_field is None:
            raise ValueError("incident_scattered formulation requires an incident_field.")
        contrast = PETSc.ScalarType(cfg.substrate_index**2 - cfg.eps_r)
        L += cfg.k0**2 * contrast * ufl.inner(incident_field, v) * dx(cfg.tags.substrate)
    elif field_formulation == "layered_scattered":
        if incident_field is None:
            raise ValueError("layered_scattered formulation requires a layered background field.")
        contrast = PETSc.ScalarType(cfg.eps_grating - cfg.grating_background_eps)
        L += cfg.k0**2 * contrast * ufl.inner(incident_field, v) * dx(cfg.tags.grating)
    return a, L


def _rhs_source_norm_for_tag(
    msh,
    mesh_data,
    cfg: SimulationConfig3D,
    source_field: fem.Function | None,
    tag: int,
    contrast: complex,
) -> float | None:
    if source_field is None:
        return None
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    energy_form = fem.form(ufl.inner(source_field, source_field) * dx(tag))
    local_energy = fem.assemble_scalar(energy_form)
    energy = msh.comm.allreduce(local_energy, op=MPI.SUM)
    scaled_contrast = cfg.k0**2 * complex(contrast)
    return float(abs(scaled_contrast) * np.sqrt(max(float(np.real(energy)), 0.0)))


def _incident_scattered_rhs_source_norm(
    msh, mesh_data, cfg: SimulationConfig3D, incident_field: fem.Function | None
) -> float | None:
    return _rhs_source_norm_for_tag(
        msh,
        mesh_data,
        cfg,
        incident_field,
        cfg.tags.substrate,
        cfg.substrate_index**2 - cfg.eps_r,
    )


def _layered_scattered_rhs_source_norm(
    msh, mesh_data, cfg: SimulationConfig3D, background_field: fem.Function | None
) -> float | None:
    return _rhs_source_norm_for_tag(
        msh,
        mesh_data,
        cfg,
        background_field,
        cfg.tags.grating,
        cfg.eps_grating - cfg.grating_background_eps,
    )


def _use_reference_correction_formulation(cfg: SimulationConfig3D) -> bool:
    """Use a correction unknown for analytic Stage-2 reference sanity cases.

    Solving homogeneous total-field problems with z-face Dirichlet data and
    x/y Floquet constraints creates a closed periodic cavity.  Near discrete
    cavity modes the total field can be badly amplified even when the boundary
    constraints are correct.  Keep this sanity path for 2A and 2B, but not for
    the 2C Fresnel physical benchmark.
    """

    return cfg.stage_case in {"floquet_airbox", "pml_airbox"}


def _use_incident_scattered_formulation(cfg: SimulationConfig3D) -> bool:
    return cfg.stage_case == "fresnel_interface" and cfg.geometry_kind == "fresnel_interface"


def _use_layered_scattered_formulation(cfg: SimulationConfig3D) -> bool:
    return cfg.stage_case in {"stage4_block_grating", "stage4_flat_layer_sanity"} and cfg.geometry_kind == "rectangular_block_grating"


def _stage4_lossless_energy_balance_check(cfg: SimulationConfig3D, summary: dict[str, Any]) -> dict[str, Any]:
    """Return an explicit pass/fail flag for lossless Stage-4 R/T metrics."""

    if cfg.geometry_kind != "rectangular_block_grating" or summary.get("R_plus_T") is None:
        return {}
    lossless = all(
        abs(complex(index).imag) < 1.0e-12
        for index in (cfg.n_air, cfg.substrate_index, cfg.grating_index)
    )
    tolerance = 1.0e-8
    r_plus_t = float(summary["R_plus_T"])
    passed = (not lossless) or r_plus_t <= 1.0 + tolerance
    return {
        "stage4_lossless_energy_balance_checked": bool(lossless),
        "stage4_energy_balance_tolerance": tolerance,
        "stage4_energy_balance_pass": bool(passed),
        "stage4_energy_balance_excess": float(r_plus_t - 1.0) if lossless else None,
    }


def _field_formulation_label(
    cfg: SimulationConfig3D,
    use_reference_correction: bool,
    use_incident_scattered: bool,
) -> str:
    if use_incident_scattered:
        return "incident_scattered"
    if _use_layered_scattered_formulation(cfg):
        return "layered_scattered"
    if not use_reference_correction:
        return "total_field"
    if cfg.stage_case == "floquet_airbox":
        return "incident_correction"
    return "reference_correction"


def _z_boundary_facets(mesh_data, cfg: SimulationConfig3D) -> np.ndarray:
    return np.unique(
        np.concatenate(
            [
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_min), dtype=np.int32),
                np.asarray(mesh_data.facet_tags.find(cfg.tags.z_max), dtype=np.int32),
            ]
        )
    )


def _run_maxwell_3d_case_core(cfg: SimulationConfig3D, out_dir: Path) -> dict[str, object]:
    """Shared 3D Maxwell execution engine used by the stage-specific modules.

    This file intentionally keeps the low-level finite-element assembly,
    PETSc/MPC setup, diagnostics, and common postprocessing in one place.  The
    public reading/dispatch entry points live in:

    - solve_maxwell_3d_stage_1_airbox.py
    - solve_maxwell_3d_stage_2_no_grating.py
    - solve_maxwell_3d_stage_4_grating.py

    That split lets each stage document its own physical formulation without
    duplicating this long, shared assembly path.
    """
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
    if cfg.stage_case not in {
        "stage1_airbox",
        "floquet_airbox",
        "pml_airbox",
        "fresnel_interface",
        "stage4_block_grating",
        "stage4_flat_layer_sanity",
    }:
        raise ValueError(
            "3D stage_case must be 'stage1_airbox', 'floquet_airbox', 'pml_airbox', "
            "'fresnel_interface', 'stage4_block_grating', or 'stage4_flat_layer_sanity'."
        )
    if cfg.use_pml and (cfg.pml_top_thickness <= 0.0 or cfg.pml_bottom_thickness <= 0.0):
        raise ValueError("3D PML cases require positive pml_top_thickness and pml_bottom_thickness.")
    k = cfg.wavevector
    p = cfg.polarization_vector
    mesh_cell_type_resolved = cfg.mesh_cell_type_resolved
    floquet_constraint_mode_requested = cfg.floquet_constraint_mode_requested
    dot_k_p = np.dot(k, p)
    _finish_timed_stage(comm, timings, "config_validation", stage_start, log)

    log(f"case = {cfg.case_name}")
    log(f"stage = {_stage_label(cfg)}")
    log(f"geometry kind = {cfg.geometry_kind}")
    log(f"use Floquet xy = {cfg.use_floquet_xy}")
    log(f"use PML = {cfg.use_pml}")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"DOLFINx scalar type = {default_scalar_type}")
    log(f"k0 = {cfg.k0:.12g}")
    log(f"k = {k.tolist()}")
    log(f"polarization = {p.tolist()}")
    log(f"dot(k, p) = {dot_k_p:.6e}")
    log(f"mesh target size = {cfg.mesh_target_size}")
    log(f"mesh cell type requested = {cfg.mesh_cell_type}")
    log(f"mesh cell type resolved = {mesh_cell_type_resolved}")
    log(f"Floquet constraint mode requested = {floquet_constraint_mode_requested}")
    petsc_options, selected_parallel_lu, parallel_direct_disabled_reason = _prepare_direct_lu_options_for_comm(comm)
    log("linear solve method = direct_lu")
    log(f"divergence penalty = {cfg.divergence_penalty}")
    if selected_parallel_lu is not None:
        log(f"MPI direct factor solver selected = {selected_parallel_lu}")
    if parallel_direct_disabled_reason is not None:
        log(f"WARNING: {parallel_direct_disabled_reason}")
    log(f"PETSc direct LU options = {petsc_options}")

    if parallel_direct_disabled_reason is not None:
        _clear_official_field_outputs(out_dir, comm)
        elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
        max_rss_mb = _global_max_rss_mb(comm)
        summary = {
            "case_name": cfg.case_name,
            "stage": _stage_label(cfg),
            **_summary_base_fields(cfg, comm),
            "config": cfg.as_jsonable(),
            "case_status": "failed_parallel_direct_lu_unavailable",
            "official_result": False,
            "diagnostic_only": True,
            "postprocess_skipped": True,
            "postprocess_skip_reason": parallel_direct_disabled_reason,
            "num_mesh_cells": None,
            "num_nedelec_dofs": None,
            "matrix_stats": None,
            "petsc_scalar_type": str(PETSc.ScalarType),
            "dolfinx_default_scalar_type": str(default_scalar_type),
            "solver_backend": "3D Maxwell direct LU path",
            "linear_solve_method": "direct_lu",
            "linear_solve_petsc_options": petsc_options,
            "linear_solve_disabled_reason": parallel_direct_disabled_reason,
            "actual_ksp_type": None,
            "actual_pc_type": None,
            "actual_pc_factor_solver_type": None,
            "selected_parallel_lu_solver_type": selected_parallel_lu,
            "ksp_converged": False,
            "ksp_converged_reason": None,
            "ksp_converged_reason_name": "PARALLEL_DIRECT_LU_UNAVAILABLE",
            "ksp_iterations": 0,
            "solver_residual_norm": None,
            "incident_transversality_dot_k_p": dot_k_p,
            "timings_seconds": timings,
            "elapsed_seconds": elapsed,
            "max_rss_mb": max_rss_mb,
        }
        _log_solver_summary(summary, log)
        log(f"elapsed seconds = {elapsed:.3f}")
        _write_case_outputs(out_dir, summary, log_lines, comm)
        return summary

    stage_start = _start_timed_stage(comm)
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    _finish_timed_stage(comm, timings, "mesh_build", stage_start, log)
    log(f"mesh cell type actual = {mesh_data.mesh_cell_type_resolved}")
    log(f"mesh cells requested = {cfg.mesh_cells}")
    log(f"mesh cells resolved = {mesh_data.mesh_cells_resolved}")
    for warning in mesh_data.z_alignment_warnings:
        log(f"WARNING: {warning}")

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    num_cells = msh.topology.index_map(tdim).size_global
    domain_tag_volumes = _cell_tag_volumes(msh, mesh_data, cfg)

    stage_start = _start_timed_stage(comm)
    V = _create_nedelec_space(msh, cfg)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    _finish_timed_stage(comm, timings, "function_space_setup", stage_start, log)
    log(f"mesh cells = {num_cells}")
    log(f"3D N1curl dofs = {num_dofs}")

    stage_start = _start_timed_stage(comm)
    solve_reference_correction = _use_reference_correction_formulation(cfg)
    solve_incident_scattered = _use_incident_scattered_formulation(cfg)
    solve_layered_scattered = _use_layered_scattered_formulation(cfg)
    field_formulation = _field_formulation_label(cfg, solve_reference_correction, solve_incident_scattered)
    solve_with_zero_bc = solve_reference_correction or solve_incident_scattered or solve_layered_scattered
    stage4_boundary_model = cfg.stage4_boundary_model.lower()
    if solve_layered_scattered and stage4_boundary_model not in {"pml", "robin0"}:
        raise ValueError("stage4_boundary_model must be 'pml' or 'robin0' for Stage-4 layered scattering.")
    stage4_pml_outer_bc = cfg.stage4_pml_outer_bc.lower()
    if solve_layered_scattered and stage4_pml_outer_bc not in {"natural", "zero_tangential"}:
        raise ValueError("stage4_pml_outer_bc must be 'natural' or 'zero_tangential'.")
    if solve_layered_scattered and stage4_boundary_model == "robin0" and cfg.use_pml:
        raise ValueError("stage4_boundary_model='robin0' requires use_pml=False.")
    # The unknown is a correction/scattered field in all non-total-field paths.
    # Stage 4 solves the scattered field.  The default PML truncation is now a
    # natural outer boundary so a too-thin PML remains visible in diagnostics
    # instead of being hidden by an imposed zero tangential field.  The old zero
    # outer boundary is still available as an explicit diagnostic switch.
    stage4_pml_zero_outer_boundary = (
        solve_layered_scattered
        and stage4_boundary_model == "pml"
        and stage4_pml_outer_bc == "zero_tangential"
    )
    stage4_robin_boundary = solve_layered_scattered and stage4_boundary_model == "robin0"
    apply_strong_boundary_bc = not (stage4_robin_boundary or (solve_layered_scattered and not stage4_pml_zero_outer_boundary))
    E_source_for_rhs = None
    if solve_incident_scattered:
        E_source_for_rhs = incident_air_plane_wave_field(V, cfg)
        rhs_source_norm = _incident_scattered_rhs_source_norm(msh, mesh_data, cfg, E_source_for_rhs)
    elif solve_layered_scattered:
        E_source_for_rhs = stage4_layered_background_field(V, cfg)
        rhs_source_norm = _layered_scattered_rhs_source_norm(msh, mesh_data, cfg, E_source_for_rhs)
    else:
        rhs_source_norm = None
    E_exact = None if solve_with_zero_bc else plane_wave_electric_field(V, cfg)
    E_bc = fem.Function(V, name="E_zero_bc") if solve_with_zero_bc else E_exact
    floquet_data: DoubleFloquet3DData | None = None
    boundary_dofs = np.asarray([], dtype=np.int32)
    raw_boundary_dofs_global = 0
    boundary_dofs_global = 0
    if cfg.use_floquet_xy:
        # Floquet constraints own the x/y side walls.  Strong H(curl)
        # Dirichlet data is therefore only applied on z faces, with slave dofs
        # removed to avoid prescribing the same unknown twice.
        floquet_data = build_double_floquet_mpc(V, mesh_data, cfg, log)
        timings.update(floquet_data.timings_seconds)
        if apply_strong_boundary_bc:
            boundary_facets = _z_boundary_facets(mesh_data, cfg)
            raw_boundary_dofs = fem.locate_dofs_topological(V, fdim, boundary_facets)
            boundary_dofs = np.setdiff1d(
                raw_boundary_dofs, floquet_data.local_slave_dofs, assume_unique=False
            ).astype(np.int32)
            raw_boundary_dofs_global = int(comm.allreduce(len(raw_boundary_dofs), op=MPI.SUM))
            boundary_dofs_global = int(comm.allreduce(len(boundary_dofs), op=MPI.SUM))
            log(
                "Dirichlet H(curl) z-boundary dofs before slave removal "
                f"local/global = {len(raw_boundary_dofs)} / {raw_boundary_dofs_global}"
            )
        else:
            log("No z-boundary Dirichlet dofs were located for this Floquet run.")
    elif apply_strong_boundary_bc:
        boundary_dofs = fem.locate_dofs_topological(V, fdim, mesh_data.boundary_facets)
        raw_boundary_dofs_global = int(comm.allreduce(len(boundary_dofs), op=MPI.SUM))
        boundary_dofs_global = raw_boundary_dofs_global
    bcs = [fem.dirichletbc(E_bc, boundary_dofs)] if apply_strong_boundary_bc else []
    problem_bcs = bcs if bcs else None
    _finish_timed_stage(comm, timings, "boundary_condition_setup", stage_start, log)
    log(f"strong Dirichlet H(curl) boundary enabled = {apply_strong_boundary_bc}")
    log(f"Dirichlet H(curl) boundary dofs local/global = {len(boundary_dofs)} / {boundary_dofs_global}")
    log(f"field formulation = {field_formulation}")
    if solve_layered_scattered:
        log(f"stage4 boundary model = {stage4_boundary_model}")
        log(f"stage4 PML outer boundary condition = {stage4_pml_outer_bc}")
        if stage4_pml_zero_outer_boundary:
            log("stage4 PML boundary flow = zero tangential scattered E on outer z PML faces")
        elif stage4_boundary_model == "pml":
            log("stage4 PML boundary flow = natural outer z boundary")
        if stage4_robin_boundary:
            log("stage4 diagnostic robin0 boundary = zero-order impedance term without PML")
    if solve_incident_scattered:
        log("incident-scattered RHS sign = +k0^2*(eps_sub - eps_air)*inner(E_inc, v)")
        log(f"incident-scattered RHS source region = physical_substrate")
        log(f"incident-scattered RHS source tag volumes = {{'substrate': {domain_tag_volumes['substrate']:.6e}}}")
        log(f"incident-scattered RHS source norm = {rhs_source_norm:.6e}")
    if solve_layered_scattered:
        log("layered-scattered RHS sign = +k0^2*(eps_true - eps_bg)*inner(E_bg, v)")
        log("layered-scattered RHS source region = physical_grating")
        log(f"layered-scattered RHS source tag volumes = {{'grating': {domain_tag_volumes['grating']:.6e}}}")
        log(f"layered-scattered RHS source contrast = {cfg.eps_grating - cfg.grating_background_eps!r}")
        log(f"layered-scattered RHS source norm = {rhs_source_norm:.6e}")

    stage_start = _start_timed_stage(comm)
    a, L = _build_variational_forms(
        msh,
        mesh_data,
        cfg,
        V,
        field_formulation=field_formulation,
        incident_field=E_source_for_rhs,
    )
    unconstrained_rhs_norm = _assembled_rhs_norm(L)
    _finish_timed_stage(comm, timings, "variational_form_setup", stage_start, log)
    log(f"unconstrained RHS norm = {unconstrained_rhs_norm}")

    stage_start = _start_timed_stage(comm)
    if floquet_data is None:
        E = fem.Function(V, name="E_numerical")
        problem = fem_petsc.LinearProblem(
            a,
            L,
            bcs=problem_bcs,
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_direct_lu_",
            petsc_options=petsc_options,
        )
        solver_backend = (
            "dolfinx.fem.petsc.LinearProblem with strong tangential E boundary data"
            if apply_strong_boundary_bc
            else "dolfinx.fem.petsc.LinearProblem without strong tangential E boundary data"
        )
    else:
        import dolfinx_mpc

        E = fem.Function(floquet_data.mpc.function_space, name="E_numerical")
        problem = dolfinx_mpc.LinearProblem(
            a,
            L,
            floquet_data.mpc,
            bcs=problem_bcs,
            u=E,
            petsc_options_prefix=f"airbox3d_{cfg.case_name}_direct_lu_mpc_",
            petsc_options=petsc_options,
        )
        solver_backend = (
            "dolfinx_mpc.LinearProblem with x/y double Floquet and z boundary data"
            if apply_strong_boundary_bc
            else "dolfinx_mpc.LinearProblem with x/y double Floquet and no strong tangential E boundary data"
        )
    _finish_timed_stage(comm, timings, "linear_problem_setup", stage_start, log)

    stage_start = _start_timed_stage(comm)
    E = problem.solve()
    E.x.scatter_forward()
    E_sca = E if (solve_incident_scattered or solve_layered_scattered) else None
    E_incident_solution = None
    E_background_solution = None
    E_total = E
    if solve_reference_correction:
        _add_reference_field_to_solution(E, cfg)
    elif solve_incident_scattered:
        E_incident_solution = incident_air_plane_wave_field(E.function_space, cfg)
        E_total = _combine_fields(E_sca, E_incident_solution, "E_total")
    elif solve_layered_scattered:
        E_background_solution = stage4_layered_background_field(E.function_space, cfg)
        E_total = _combine_fields(E_sca, E_background_solution, "E_total")
    _finish_timed_stage(comm, timings, "linear_problem_solve", stage_start, log)

    stage_start = _start_timed_stage(comm)
    matrix_stats = _petsc_matrix_stats(problem.A)
    _finish_timed_stage(comm, timings, "matrix_stats", stage_start, log)
    _log_matrix_stats(matrix_stats, log)

    reason = int(problem.solver.getConvergedReason())
    reason_name = _ksp_reason_name(reason)
    iterations = int(problem.solver.getIterationNumber())
    residual_norm = float(problem.solver.getResidualNorm())
    ksp_type = problem.solver.getType()
    pc = problem.solver.getPC()
    pc_type = pc.getType()
    pc_factor_solver_type = _pc_factor_solver_type(pc)
    linear_system_diagnostics = _linear_system_diagnostics(problem.A, problem.b, problem.x)
    log(f"solver converged reason = {reason}")
    log(f"solver converged reason name = {reason_name}")
    log(f"solver iterations = {iterations}")
    log(f"solver residual norm = {residual_norm:.6e}")
    log(f"actual KSP type = {ksp_type}")
    log(f"actual PC type = {pc_type}")
    log(f"actual PC factor solver type = {pc_factor_solver_type}")
    log(f"linear system RHS norm = {linear_system_diagnostics['linear_system_rhs_norm']}")
    log(f"linear system solution norm = {linear_system_diagnostics['linear_system_solution_norm']}")
    log(f"linear system true relative residual = {linear_system_diagnostics['linear_system_relative_residual']}")
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    max_rss_mb = _global_max_rss_mb(comm)
    converged = reason > 0

    summary = {
        "case_name": cfg.case_name,
        "stage": _stage_label(cfg),
        **_summary_base_fields(cfg, comm),
        "config": cfg.as_jsonable(),
        "case_status": "completed" if converged else "failed_not_converged",
        "official_result": converged,
        "diagnostic_only": not converged,
        "postprocess_skipped": not converged,
        "postprocess_skip_reason": None if converged else "PETSc KSP did not converge.",
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "matrix_stats": matrix_stats,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "dolfinx_default_scalar_type": str(default_scalar_type),
        "solver_backend": solver_backend,
        "field_formulation": field_formulation,
        "stage4_boundary_model": stage4_boundary_model if solve_layered_scattered else None,
        "stage4_pml_outer_bc": stage4_pml_outer_bc if solve_layered_scattered else None,
        "strong_z_boundary_dirichlet_enabled": bool(apply_strong_boundary_bc),
        "strong_z_boundary_dirichlet_dofs": int(boundary_dofs_global),
        "stage4_matches_2d_scattered_pml_boundary_flow": False,
        "stage4_outer_pml_zero_tangential_e_bc": bool(
            solve_layered_scattered and cfg.use_pml and stage4_pml_zero_outer_boundary
        ),
        "stage4_outer_pml_natural_bc": bool(
            solve_layered_scattered and cfg.use_pml and stage4_boundary_model == "pml" and not stage4_pml_zero_outer_boundary
        ),
        "stage4_robin0_zero_order_boundary_enabled": bool(stage4_robin_boundary),
        "strong_z_boundary_dirichlet_raw_dofs_global": int(raw_boundary_dofs_global),
        "strong_z_boundary_dirichlet_dofs_global": int(boundary_dofs_global),
        "incident_added_to_solution": field_formulation in {"incident_correction", "incident_scattered"},
        "background_added_to_solution": field_formulation == "layered_scattered",
        "background_zeroed_in_pml_for_stage4_output": bool(solve_layered_scattered),
        "reference_added_to_solution": field_formulation == "reference_correction",
        "fresnel_reference_used_for_solution": False,
        "fresnel_reference_used_for_comparison_only": cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"},
        "rhs_source_region": (
            "physical_substrate"
            if solve_incident_scattered
            else "physical_grating"
            if solve_layered_scattered
            else None
        ),
        "rhs_source_sign": (
            "+k0^2*(eps_sub-eps_air)*inner(E_inc,v)"
            if solve_incident_scattered
            else "+k0^2*(eps_true-eps_bg)*inner(E_bg,v)"
            if solve_layered_scattered
            else None
        ),
        "rhs_source_contrast": (
            complex(cfg.substrate_index**2 - cfg.eps_r)
            if solve_incident_scattered
            else complex(cfg.eps_grating - cfg.grating_background_eps)
            if solve_layered_scattered
            else None
        ),
        "rhs_source_tag_ids": (
            {"substrate": cfg.tags.substrate}
            if solve_incident_scattered
            else {"grating": cfg.tags.grating}
            if solve_layered_scattered
            else {}
        ),
        "rhs_source_tag_volumes": (
            {"substrate": domain_tag_volumes["substrate"]}
            if solve_incident_scattered
            else {"grating": domain_tag_volumes["grating"]}
            if solve_layered_scattered
            else {}
        ),
        "rhs_source_excludes_air_and_pml": bool(solve_incident_scattered or solve_layered_scattered),
        "rhs_source_norm": rhs_source_norm,
        "unconstrained_rhs_norm": unconstrained_rhs_norm,
        "domain_tag_volumes": domain_tag_volumes,
        "linear_solve_method": "direct_lu",
        "linear_solve_petsc_options": petsc_options,
        "linear_solve_disabled_reason": None,
        "actual_ksp_type": ksp_type,
        "actual_pc_type": pc_type,
        "actual_pc_factor_solver_type": pc_factor_solver_type,
        "selected_parallel_lu_solver_type": selected_parallel_lu,
        "ksp_converged": converged,
        "ksp_converged_reason": reason,
        "ksp_converged_reason_name": reason_name,
        "ksp_iterations": iterations,
        "solver_residual_norm": residual_norm,
        **linear_system_diagnostics,
        "use_floquet_xy": cfg.use_floquet_xy,
        "use_pml": cfg.use_pml,
        "floquet_num_local_slaves": None if floquet_data is None else floquet_data.num_local_slaves,
        "floquet_num_local_slave_records_seen": None
        if floquet_data is None
        else floquet_data.num_local_slave_records_seen,
        "floquet_num_local_ghost_slave_constraints": None
        if floquet_data is None
        else floquet_data.num_local_ghost_slave_constraints,
        "floquet_num_global_ghost_slave_constraints": None
        if floquet_data is None
        else floquet_data.num_global_ghost_slave_constraints,
        "floquet_num_local_ghost_slave_records_skipped": None
        if floquet_data is None
        else floquet_data.num_local_ghost_slave_records_skipped,
        "floquet_num_global_ghost_slave_records_skipped": None
        if floquet_data is None
        else floquet_data.num_global_ghost_slave_records_skipped,
        "floquet_constraint_mode_resolved": None if floquet_data is None else floquet_data.constraint_mode_resolved,
        "floquet_raw_map_nnz": None if floquet_data is None else floquet_data.raw_map_nnz,
        "floquet_max_masters_per_slave": None if floquet_data is None else floquet_data.max_masters_per_slave,
        "floquet_estimated_constraint_memory_mb": None
        if floquet_data is None
        else floquet_data.estimated_constraint_memory_mb,
        "floquet_num_slave_edges": None if floquet_data is None else floquet_data.num_slave_edges,
        "floquet_num_matched_master_edges": None
        if floquet_data is None
        else floquet_data.num_matched_master_edges,
        "floquet_num_constraints": None if floquet_data is None else floquet_data.num_constraints,
        "floquet_max_edge_midpoint_pairing_error": None
        if floquet_data is None
        else floquet_data.max_edge_midpoint_pairing_error,
        "floquet_num_x_constraints": None if floquet_data is None else floquet_data.num_x_constraints,
        "floquet_num_y_constraints": None if floquet_data is None else floquet_data.num_y_constraints,
        "floquet_num_corner_constraints": None
        if floquet_data is None
        else floquet_data.num_corner_constraints,
        "mesh_cell_type_actual": mesh_data.mesh_cell_type_resolved,
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "mesh_z_alignment_warnings": mesh_data.z_alignment_warnings,
        "max_face_pairing_coordinate_error": None
        if floquet_data is None
        else floquet_data.max_face_pairing_coordinate_error,
        "nedelec_orientation_factor_stats": None if floquet_data is None else floquet_data.orientation_factor_stats,
        "floquet_constraint_phase_x": None if floquet_data is None else floquet_data.phase_x,
        "floquet_constraint_phase_y": None if floquet_data is None else floquet_data.phase_y,
        "floquet_constraint_phase_corner": None if floquet_data is None else floquet_data.phase_corner,
        "floquet_edge_corner_constraint_phase_mismatch": None
        if floquet_data is None
        else floquet_data.edge_corner_phase_mismatch,
        "floquet_constraint_timings_seconds": None if floquet_data is None else floquet_data.timings_seconds,
        "pml_parameters": {
            "pml_alpha": cfg.pml_alpha,
            "pml_top_thickness": cfg.pml_top_thickness,
            "pml_bottom_thickness": cfg.pml_bottom_thickness,
            "physical_z_min": cfg.physical_z_min,
            "physical_z_max": cfg.physical_z_max,
            "domain_z_min": cfg.domain_z_min,
            "domain_z_max": cfg.domain_z_max,
        },
        "incident_transversality_dot_k_p": dot_k_p,
        "timings_seconds": timings,
        "elapsed_seconds": elapsed,
        "max_rss_mb": max_rss_mb,
    }

    if not converged:
        _clear_official_field_outputs(out_dir, comm)
        log("WARNING: PETSc KSP did not converge.")
        log("WARNING: This field is only a diagnostic iterate and must not be used as a valid solution.")
        log("WARNING: Official postprocess and ParaView output are skipped for this failed case.")
        _log_solver_summary(summary, log)
        log("timing summary seconds:")
        for name, value in timings.items():
            log(f"  {name}: {value:.3f}")
        log(f"elapsed seconds = {elapsed:.3f}")
        _write_case_outputs(out_dir, summary, log_lines, comm)
        return summary

    stage_start = _start_timed_stage(comm)
    field_metrics = save_airbox_3d_fields(
        mesh_data,
        cfg,
        E_total,
        out_dir,
        E_scattered=E_sca if solve_layered_scattered else None,
        E_background=E_background_solution if solve_layered_scattered else None,
    )
    _finish_timed_stage(comm, timings, "postprocess", stage_start, log)
    elapsed = float(comm.allreduce(time.perf_counter() - start, op=MPI.MAX))
    max_rss_mb = _global_max_rss_mb(comm)
    summary["timings_seconds"] = timings
    summary["elapsed_seconds"] = elapsed
    summary["max_rss_mb"] = max_rss_mb
    summary.update(field_metrics)
    if solve_incident_scattered:
        summary["E_sca_norm"] = _function_coefficient_norm(E_sca)
        summary["E_inc_norm"] = _function_coefficient_norm(E_incident_solution)
        summary["E_bg_norm"] = None
        summary["E_total_norm"] = _function_coefficient_norm(E_total)
    elif solve_layered_scattered:
        summary["E_sca_norm"] = _function_coefficient_norm(E_sca)
        summary["E_inc_norm"] = None
        summary["E_bg_norm"] = _function_coefficient_norm(E_background_solution)
        summary["E_total_norm"] = _function_coefficient_norm(E_total)
    else:
        summary["E_sca_norm"] = None
        summary["E_inc_norm"] = None
        summary["E_bg_norm"] = None
        summary["E_total_norm"] = _function_coefficient_norm(E)
    stage2_metrics: dict[str, Any] = {}
    if floquet_data is not None:
        stage2_metrics.update(_floquet_probe_metrics(floquet_data))
    if cfg.use_pml and solve_layered_scattered:
        stage2_metrics.update(_stage4_scattered_pml_metrics(E_sca, cfg))
    elif cfg.use_pml:
        stage2_metrics.update(_pml_probe_metrics(E_total, cfg))
    stage2_metrics.update(_stage2_reference_metrics(E_total, cfg, field_metrics))
    summary.update(stage2_metrics)
    diffraction_metrics: dict[str, Any] = {}
    if cfg.geometry_kind == "rectangular_block_grating":
        stage_start = _start_timed_stage(comm)
        diffraction_metrics = compute_diffraction_orders_3d(
            mesh_data,
            cfg,
            E_total,
            out_dir,
            E_scattered=E_sca if solve_layered_scattered else None,
        )
        _finish_timed_stage(comm, timings, "diffraction_postprocess", stage_start, log)
        summary.update(diffraction_metrics)
        summary.update(_stage4_lossless_energy_balance_check(cfg, summary))
        if summary.get("stage4_energy_balance_pass") is False:
            summary["official_result"] = False
            summary["diagnostic_only"] = True
            summary["case_status"] = "failed_stage4_energy_balance"
            summary["postprocess_skipped"] = False
            summary["postprocess_skip_reason"] = None
        summary["timings_seconds"] = timings
    has_power_metrics = (
        {"R_total", "T_total", "R_plus_T"}.issubset(summary)
        and summary.get("R_total") is not None
        and summary.get("T_total") is not None
        and summary.get("R_plus_T") is not None
    )
    if comm.rank == 0 and has_power_metrics and cfg.geometry_kind != "rectangular_block_grating":
        (out_dir / "power_metrics_3d.json").write_text(
            json.dumps(
                {key: summary[key] for key in ("R_total", "T_total", "R_plus_T", "fresnel_R", "fresnel_T", "fresnel_R_error", "fresnel_T_error") if key in summary},
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            ),
            encoding="utf-8",
        )
    log(f"max |E| = {field_metrics['max_abs_E']:.6e}")
    log(
        "max component |Ex|/|Ey|/|Ez| = "
        f"{field_metrics['max_abs_Ex']:.6e} / {field_metrics['max_abs_Ey']:.6e} / {field_metrics['max_abs_Ez']:.6e}"
    )
    if field_metrics.get("max_abs_E_physical_z_region") is not None:
        log(f"max |E| in physical z-region = {field_metrics['max_abs_E_physical_z_region']:.6e}")
    if field_metrics.get("max_abs_E_pml_z_region") is not None:
        log(f"max |E| in PML z-region = {field_metrics['max_abs_E_pml_z_region']:.6e}")
    log(f"max |H| = {field_metrics['max_abs_H']:.6e}")
    if field_metrics.get("exact_reference_available"):
        log(f"plane-wave relative max error = {field_metrics['relative_max_abs_E_error']:.6e}")
        log(f"H relative max error = {field_metrics['relative_max_abs_H_error']:.6e}")
    else:
        log("exact reference unavailable for this case; E_exact/H_exact error fields are not written.")
        if field_metrics.get("max_abs_E_sca") is not None:
            log(f"max |E_scat| = {field_metrics['max_abs_E_sca']:.6e}")
            log(
                "max E_scat component |Ex|/|Ey|/|Ez| = "
                f"{field_metrics['max_abs_E_sca_Ex']:.6e} / "
                f"{field_metrics['max_abs_E_sca_Ey']:.6e} / "
                f"{field_metrics['max_abs_E_sca_Ez']:.6e}"
            )
        if field_metrics.get("max_abs_E_sca_physical_z_region") is not None:
            log(f"max |E_scat| in physical z-region = {field_metrics['max_abs_E_sca_physical_z_region']:.6e}")
        if field_metrics.get("max_abs_E_sca_pml_z_region") is not None:
            log(f"max |E_scat| in PML z-region = {field_metrics['max_abs_E_sca_pml_z_region']:.6e}")
        if field_metrics.get("max_abs_E_b") is not None:
            log(f"max |E_bg| = {field_metrics['max_abs_E_b']:.6e}")
        if field_metrics.get("max_abs_E_b_physical_z_region") is not None:
            log(f"max |E_bg| in physical z-region = {field_metrics['max_abs_E_b_physical_z_region']:.6e}")
        if field_metrics.get("max_abs_E_b_pml_z_region") is not None:
            log(f"max |E_bg| in PML z-region = {field_metrics['max_abs_E_b_pml_z_region']:.6e}")
    log(f"Poynting direction cosine = {field_metrics['poynting_direction_cosine']:.6e}")
    if floquet_data is not None:
        log(f"Floquet x-face mismatch = {summary['floquet_x_face_mismatch']:.6e}")
        log(f"Floquet y-face mismatch = {summary['floquet_y_face_mismatch']:.6e}")
        log(f"Floquet edge/corner mismatch = {summary['floquet_edge_corner_mismatch']:.6e}")
    if cfg.use_pml:
        if summary.get("pml_reflection_proxy") is not None:
            log(f"PML reflection proxy = {summary['pml_reflection_proxy']:.6e}")
        if summary.get("pml_metric_field"):
            log(f"PML metric field = {summary['pml_metric_field']}")
        log(f"PML top decay ratio = {summary['pml_decay_ratio_top']}")
        log(f"PML bottom decay ratio = {summary['pml_decay_ratio_bottom']}")
    if cfg.geometry_kind == "fresnel_interface":
        log(f"Numerical R/T = {summary['R_total']:.6e} / {summary['T_total']:.6e}")
        log(f"Fresnel R/T = {summary['fresnel_R']:.6e} / {summary['fresnel_T']:.6e}")
        log(f"R+T = {summary['R_plus_T']:.6e}")
        log(f"Fresnel top mode fit residual = {summary['fresnel_top_mode_fit_residual']:.6e}")
        log(f"Fresnel bottom mode fit residual = {summary['fresnel_bottom_mode_fit_residual']:.6e}")
        log(f"Fresnel incident amplitude abs = {summary['fresnel_incident_amplitude_abs']:.6e}")
        log(f"Fresnel reflected amplitude abs = {summary['fresnel_reflected_amplitude_abs']:.6e}")
        log(f"Fresnel transmitted amplitude abs = {summary['fresnel_transmitted_amplitude_abs']:.6e}")
        log(
            "Fresnel sampling z ranges = "
            f"top [{summary['fresnel_top_sampling_z_min']:.6g}, {summary['fresnel_top_sampling_z_max']:.6g}] nm, "
            f"bottom [{summary['fresnel_bottom_sampling_z_min']:.6g}, {summary['fresnel_bottom_sampling_z_max']:.6g}] nm"
        )
    if cfg.geometry_kind == "rectangular_block_grating":
        log(f"3D diffraction total power source = {summary.get('diffraction_total_power_source')}")
        log(f"3D diffraction R/T = {summary['R_total']:.6e} / {summary['T_total']:.6e}")
        log(f"3D diffraction R+T = {summary['R_plus_T']:.6e}")
        log(f"3D diffraction A_balance = {summary['A_balance']:.6e}")
        if summary.get("stage4_lossless_energy_balance_checked"):
            log(f"Stage 4 lossless energy-balance pass = {summary['stage4_energy_balance_pass']}")
            log(f"Stage 4 R+T excess over 1 = {summary['stage4_energy_balance_excess']:.6e}")
        if summary.get("R_total_from_modal_orders") is not None:
            log(
                "3D modal-order diagnostic R/T = "
                f"{summary['R_total_from_modal_orders']:.6e} / {summary['T_total_from_modal_orders']:.6e}"
            )
            log(f"3D modal-order diagnostic R+T = {summary['R_plus_T_from_modal_orders']:.6e}")
        else:
            log("3D modal-order diagnostic skipped")
        if summary.get("R_total_from_net_flux") is not None:
            log(
                "3D sampled net-flux R/T = "
                f"{summary['R_total_from_net_flux']:.6e} / {summary['T_total_from_net_flux']:.6e}"
            )
            log(f"3D sampled net-flux R+T = {summary['R_plus_T_from_net_flux']:.6e}")
        if summary.get("diffraction_top_fit_residual") is not None:
            log(f"3D diffraction top fit residual = {summary['diffraction_top_fit_residual']:.6e}")
            log(f"3D diffraction bottom fit residual = {summary['diffraction_bottom_fit_residual']:.6e}")
        else:
            log("3D diffraction modal fit residual skipped")
    log(f"ParaView file = {field_metrics['paraview_file']}")
    log("timing summary seconds:")
    for name, value in timings.items():
        log(f"  {name}: {value:.3f}")
    _log_solver_summary(summary, log)
    log(f"elapsed seconds = {elapsed:.3f}")

    _write_case_outputs(out_dir, summary, log_lines, comm)
    return summary
