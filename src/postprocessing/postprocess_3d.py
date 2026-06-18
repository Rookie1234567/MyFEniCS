from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista
import ufl
from mpi4py import MPI

from dolfinx import fem, io, plot

from ..common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values
from ..common.config_3d import SimulationConfig3D


def _field_grid(V_dg):
    cells, cell_types, coords = plot.vtk_mesh(V_dg)
    return pyvista.UnstructuredGrid(cells, cell_types, coords), coords


def _values(field, num_points: int) -> np.ndarray:
    values = field.x.array.reshape(num_points, -1)
    if values.shape[1] < 3:
        raise RuntimeError("Expected a 3D vector field.")
    return values[:, :3]


def _norm(values: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum(np.abs(values) ** 2, axis=1))


def _vec_real(values: np.ndarray) -> np.ndarray:
    return values.real.astype(np.float64)


def _vec_imag(values: np.ndarray) -> np.ndarray:
    return values.imag.astype(np.float64)


def _add_complex_vector(grid, prefix: str, values: np.ndarray) -> None:
    grid.point_data[f"{prefix}_real"] = _vec_real(values)
    grid.point_data[f"{prefix}_imag"] = _vec_imag(values)
    grid.point_data[f"{prefix}_abs"] = _norm(values).astype(np.float64)


def _add_abs_scalar(grid, name: str, values: np.ndarray) -> None:
    grid.point_data[name] = _norm(values).astype(np.float64)


def _plane_wave_values(cfg: SimulationConfig3D, coords: np.ndarray) -> np.ndarray:
    return cfg.electric_field_scale_V_per_m * electric_field_code_values(cfg, coords)


def _exact_h_values(cfg: SimulationConfig3D, coords: np.ndarray) -> np.ndarray:
    return cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(cfg, coords)


def _write_parallel_vtu_collection(out_dir: Path, size: int):
    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for rank in range(size):
        lines.append(
            f'    <DataSet timestep="0" group="" part="{rank}" '
            f'file="fields_3d_for_paraview_rank{rank:04d}.vtu"/>'
        )
    lines.extend(["  </Collection>", "</VTKFile>", ""])
    (out_dir / "fields_3d_for_paraview_parallel.pvd").write_text("\n".join(lines), encoding="utf-8")


def _global_max_norm(comm, values: np.ndarray) -> float:
    local = float(np.max(_norm(values))) if values.size else 0.0
    return comm.allreduce(local, op=MPI.MAX)


def _global_mean_vector(comm, values: np.ndarray) -> np.ndarray:
    local_sum = np.sum(values, axis=0) if len(values) else np.zeros(3, dtype=np.float64)
    total_sum = comm.allreduce(local_sum, op=MPI.SUM)
    total_count = comm.allreduce(len(values), op=MPI.SUM)
    if total_count == 0:
        return np.zeros(3, dtype=np.float64)
    return np.asarray(total_sum, dtype=np.float64) / float(total_count)


def _interpolation_points(V):
    points = V.element.interpolation_points
    return points() if callable(points) else points


def save_airbox_3d_fields(mesh_data, cfg: SimulationConfig3D, E_numerical, out_dir: Path) -> dict[str, object]:
    """Save compact 3D E/H fields and return reconstruction metrics.

    The solve uses normalized field amplitudes internally.  ParaView output uses
    E in V/m and H in A/m, with incident_e0_v_per_m as the physical scale.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    V_dg = fem.functionspace(mesh_data.mesh, ("DG", cfg.visualization_degree, (3,)))

    E_code_dg = fem.Function(V_dg, name="E_code")
    E_code_dg.interpolate(E_numerical)

    E_num_dg = fem.Function(V_dg, name="E_V_per_m")
    E_num_dg.x.array[:] = cfg.electric_field_scale_V_per_m * E_code_dg.x.array[:]
    E_num_dg.x.scatter_forward()

    E_exact_dg = fem.Function(V_dg, name="E_exact_V_per_m")
    E_exact_dg.interpolate(lambda x: _plane_wave_values(cfg, x.T).T)

    h_expr = (cfg.magnetic_field_scale_A_per_m / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(E_numerical)
    H_dg = fem.Function(V_dg, name="H_A_per_m_from_curl")
    H_dg.interpolate(fem.Expression(h_expr, _interpolation_points(V_dg)))

    H_exact_dg = fem.Function(V_dg, name="H_exact_A_per_m")
    H_exact_dg.interpolate(lambda x: _exact_h_values(cfg, x.T).T)

    try:
        with io.VTXWriter(comm, out_dir / "E_3d_numerical.bp", E_num_dg) as writer:
            writer.write(0.0)
        with io.VTXWriter(comm, out_dir / "H_3d_A_per_m_from_curl.bp", H_dg) as writer:
            writer.write(0.0)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "vtx_3d_warning.txt").write_text(str(exc), encoding="utf-8")

    grid, coords = _field_grid(V_dg)
    e_num = _values(E_num_dg, grid.n_points)
    e_exact = _values(E_exact_dg, grid.n_points)
    e_error = e_num - e_exact
    h_num = _values(H_dg, grid.n_points)
    h_exact = _values(H_exact_dg, grid.n_points)
    h_error = h_num - h_exact

    paraview_grid = grid.copy()
    _add_complex_vector(paraview_grid, "E_V_per_m", e_num)
    _add_abs_scalar(paraview_grid, "E_exact_abs_V_per_m", e_exact)
    _add_abs_scalar(paraview_grid, "E_error_abs_V_per_m", e_error)
    _add_complex_vector(paraview_grid, "H_A_per_m", h_num)
    _add_abs_scalar(paraview_grid, "H_exact_abs_A_per_m", h_exact)
    _add_abs_scalar(paraview_grid, "H_error_abs_A_per_m", h_error)
    domain_tags = np.full(paraview_grid.n_cells, cfg.tags.air, dtype=np.int32)
    if hasattr(mesh_data, "cell_tags"):
        indices = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
        values = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
        valid = indices < paraview_grid.n_cells
        domain_tags[indices[valid]] = values[valid]
    paraview_grid.cell_data["domain_tag"] = domain_tags
    paraview_grid.field_data["length_unit_nm"] = np.array([1.0], dtype=np.float64)
    paraview_grid.field_data["electric_field_unit_V_per_m"] = np.array([1.0], dtype=np.float64)
    paraview_grid.field_data["incident_e0_V_per_m"] = np.array([cfg.electric_field_scale_V_per_m], dtype=np.float64)
    paraview_grid.field_data["magnetic_field_unit_A_per_m"] = np.array([1.0], dtype=np.float64)
    paraview_grid.field_data["magnetic_field_scale_A_per_m"] = np.array(
        [cfg.magnetic_field_scale_A_per_m],
        dtype=np.float64,
    )

    if comm.size > 1:
        paraview_path = out_dir / "fields_3d_for_paraview_parallel.pvd"
        paraview_grid.save(out_dir / f"fields_3d_for_paraview_rank{comm.rank:04d}.vtu")
        comm.barrier()
        if comm.rank == 0:
            _write_parallel_vtu_collection(out_dir, comm.size)
    else:
        paraview_grid.save(out_dir / "fields_3d_for_paraview.vtu")
        paraview_path = out_dir / "fields_3d_for_paraview.vtu"

    max_e_exact = _global_max_norm(comm, e_exact)
    max_e_num = _global_max_norm(comm, e_num)
    max_e_error = _global_max_norm(comm, e_error)
    max_h = _global_max_norm(comm, h_num)
    max_h_exact = _global_max_norm(comm, h_exact)
    max_h_error = _global_max_norm(comm, h_error)

    poynting = 0.5 * np.real(np.cross(e_num, np.conj(h_num)))
    mean_poynting = _global_mean_vector(comm, poynting)
    direction = cfg.direction_vector
    mean_norm = float(np.linalg.norm(mean_poynting))
    poynting_cosine = float(np.dot(mean_poynting, direction) / mean_norm) if mean_norm > 0.0 else float("nan")

    return {
        "max_abs_E_exact": max_e_exact,
        "max_abs_E": max_e_num,
        "max_abs_E_error": max_e_error,
        "relative_max_abs_E_error": max_e_error / max(max_e_exact, 1.0e-30),
        "max_abs_H": max_h,
        "max_abs_H_exact": max_h_exact,
        "max_abs_H_error": max_h_error,
        "relative_max_abs_H_error": max_h_error / max(max_h_exact, 1.0e-30),
        "mean_poynting_W_per_m2": mean_poynting.tolist(),
        "poynting_direction_cosine": poynting_cosine,
        "curl_postprocess_success": True,
        "paraview_file": str(paraview_path),
    }
