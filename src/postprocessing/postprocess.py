from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista

from dolfinx import fem, io, plot
from mpi4py import MPI

from ..common.config import SimulationConfig


def _plotter(window_size=(1200, 900)):
    pyvista.OFF_SCREEN = True
    return pyvista.Plotter(off_screen=True, window_size=window_size)


def save_mesh_plots(mesh_data, cfg: SimulationConfig, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    msh = mesh_data.mesh
    tdim = msh.topology.dim
    topology, cell_types, geometry = plot.vtk_mesh(msh, tdim)
    grid = pyvista.UnstructuredGrid(topology, cell_types, geometry)
    num_local_cells = msh.topology.index_map(tdim).size_local
    markers = mesh_data.cell_tags.values[mesh_data.cell_tags.indices < num_local_cells]
    grid.cell_data["domain_tag"] = markers

    plotter = _plotter()
    plotter.add_mesh(grid, color="white", show_edges=True, line_width=1)
    plotter.view_xy()
    plotter.screenshot(str(out_dir / "mesh.png"))
    plotter.close()

    plotter = _plotter()
    plotter.add_mesh(
        grid,
        scalars="domain_tag",
        categories=True,
        cmap=["#d8dee9", "#f2cc8f", "#81b29a", "#8ecae6"],
        show_edges=True,
        show_scalar_bar=False,
    )
    plotter.add_scalar_bar(title="domain tag")
    plotter.view_xy()
    plotter.screenshot(str(out_dir / "material_domains.png"))
    plotter.close()


def _field_grid(V_dg):
    cells, cell_types, coords = plot.vtk_mesh(V_dg)
    grid = pyvista.UnstructuredGrid(cells, cell_types, coords)
    return grid, coords


def _field_values(field, num_points: int) -> np.ndarray:
    values = field.x.array.reshape(num_points, -1)
    if values.shape[1] < 2:
        raise RuntimeError("Expected a vector field with at least two components for Ex/Ey output.")
    return values[:, :2]


def _scalar_field_values(field, num_points: int) -> np.ndarray:
    values = field.x.array.reshape(num_points, -1)
    if values.shape[1] < 1:
        raise RuntimeError("Expected a scalar field for Ez output.")
    return values[:, 0]


def _save_scalar(grid, name: str, data: np.ndarray, path: Path, cmap: str = "RdBu_r"):
    g = grid.copy()
    g.point_data[name] = np.asarray(data, dtype=np.float64)
    plotter = _plotter()
    plotter.add_mesh(g, scalars=name, cmap=cmap, show_edges=False, show_scalar_bar=False)
    plotter.add_scalar_bar(title=name)
    plotter.view_xy()
    plotter.screenshot(str(path))
    plotter.close()


def _save_quiver(grid, coords, vectors, scalar, path: Path):
    background = grid.copy()
    background.point_data["|E_total|"] = scalar
    stride = max(1, coords.shape[0] // 260)
    points = coords[::stride]
    vec2 = vectors[::stride]
    vec3 = np.zeros((len(points), 3), dtype=np.float64)
    vec3[:, :2] = vec2.real
    pdata = pyvista.PolyData(points)
    pdata["E_real"] = vec3
    glyphs = pdata.glyph(orient="E_real", scale="E_real", factor=0.10)

    plotter = _plotter()
    plotter.add_mesh(background, scalars="|E_total|", cmap="viridis", opacity=0.82, show_scalar_bar=False)
    plotter.add_mesh(glyphs, color="black")
    plotter.add_scalar_bar(title="|E_total|")
    plotter.view_xy()
    plotter.screenshot(str(path))
    plotter.close()


def _vec3(values: np.ndarray, part: str) -> np.ndarray:
    vectors = np.zeros((values.shape[0], 3), dtype=np.float64)
    if part == "real":
        vectors[:, :2] = values.real
    elif part == "imag":
        vectors[:, :2] = values.imag
    else:
        raise ValueError("part must be 'real' or 'imag'")
    return vectors


def _add_complex_field_arrays(grid, prefix: str, values: np.ndarray, norm: np.ndarray):
    grid.point_data[f"{prefix}_real"] = _vec3(values, "real")
    grid.point_data[f"{prefix}_imag"] = _vec3(values, "imag")
    grid.point_data[f"{prefix}_real_vector"] = _vec3(values, "real")
    grid.point_data[f"{prefix}_imag_vector"] = _vec3(values, "imag")
    grid.point_data[f"{prefix}_abs"] = norm.astype(np.float64)
    grid.point_data[f"{prefix}_Ex_real"] = values[:, 0].real.astype(np.float64)
    grid.point_data[f"{prefix}_Ex_imag"] = values[:, 0].imag.astype(np.float64)
    grid.point_data[f"{prefix}_Ey_real"] = values[:, 1].real.astype(np.float64)
    grid.point_data[f"{prefix}_Ey_imag"] = values[:, 1].imag.astype(np.float64)
    grid.point_data[f"{prefix}_Ex_abs"] = np.abs(values[:, 0]).astype(np.float64)
    grid.point_data[f"{prefix}_Ey_abs"] = np.abs(values[:, 1]).astype(np.float64)
    grid.point_data[f"{prefix}_Ex_phase"] = np.angle(values[:, 0]).astype(np.float64)
    grid.point_data[f"{prefix}_Ey_phase"] = np.angle(values[:, 1]).astype(np.float64)


def _add_complex_scalar_field_arrays(grid, prefix: str, values: np.ndarray):
    abs_values = np.abs(values).astype(np.float64)
    grid.point_data[f"{prefix}_real"] = values.real.astype(np.float64)
    grid.point_data[f"{prefix}_imag"] = values.imag.astype(np.float64)
    grid.point_data[f"{prefix}_abs"] = abs_values
    grid.point_data[f"{prefix}_phase"] = np.angle(values).astype(np.float64)
    grid.point_data[f"{prefix}_Ez_real"] = values.real.astype(np.float64)
    grid.point_data[f"{prefix}_Ez_imag"] = values.imag.astype(np.float64)
    grid.point_data[f"{prefix}_Ez_abs"] = abs_values
    grid.point_data[f"{prefix}_Ez_phase"] = np.angle(values).astype(np.float64)


def _domain_cell_arrays(mesh_data, cfg: SimulationConfig, n_cells: int) -> dict[str, np.ndarray]:
    tdim = mesh_data.mesh.topology.dim
    cell_map = mesh_data.mesh.topology.index_map(tdim)
    num_cells_on_rank = cell_map.size_local + cell_map.num_ghosts
    tags = np.zeros(num_cells_on_rank, dtype=np.int32)
    valid = mesh_data.cell_tags.indices < num_cells_on_rank
    tags[mesh_data.cell_tags.indices[valid]] = mesh_data.cell_tags.values[valid].astype(np.int32)

    if n_cells < num_cells_on_rank:
        tags = tags[:n_cells]
    elif n_cells > num_cells_on_rank:
        tags = np.pad(tags, (0, n_cells - num_cells_on_rank), mode="constant")

    arrays = {
        "domain_tag": tags,
        "material_id": tags.copy(),
    }
    return arrays


def _add_domain_cell_arrays(grid, mesh_data, cfg: SimulationConfig):
    for name, values in _domain_cell_arrays(mesh_data, cfg, grid.n_cells).items():
        grid.cell_data[name] = values


def _add_numeric_metadata(grid):
    grid.field_data["length_unit_nm"] = np.array([1.0], dtype=np.float64)
    grid.field_data["electric_field_normalization_E0"] = np.array([1.0], dtype=np.float64)


def _save_paraview_fields(
    grid,
    mesh_data,
    cfg: SimulationConfig,
    inc_values,
    scat_values,
    total_values,
    inc_norm,
    scat_norm,
    total_norm,
    out_dir: Path,
):
    paraview_grid = grid.copy()
    _add_complex_field_arrays(paraview_grid, "E_inc", inc_values, inc_norm)
    _add_complex_field_arrays(paraview_grid, "E_scat", scat_values, scat_norm)
    _add_complex_field_arrays(paraview_grid, "E_total", total_values, total_norm)
    _add_domain_cell_arrays(paraview_grid, mesh_data, cfg)
    _add_numeric_metadata(paraview_grid)
    paraview_grid.save(out_dir / "fields_for_paraview.vtu")


def _write_parallel_vtu_collection(out_dir: Path, size: int):
    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for rank in range(size):
        lines.append(
            f'    <DataSet timestep="0" group="" part="{rank}" '
            f'file="fields_for_paraview_rank{rank:04d}.vtu"/>'
        )
    lines.extend(["  </Collection>", "</VTKFile>", ""])
    (out_dir / "fields_for_paraview_parallel.pvd").write_text("\n".join(lines), encoding="utf-8")


def _save_parallel_paraview_fields(
    V_dg,
    mesh_data,
    cfg: SimulationConfig,
    E_inc_dg,
    E_scat_dg,
    E_total_dg,
    out_dir: Path,
):
    comm = mesh_data.mesh.comm
    grid, _ = _field_grid(V_dg)
    total_values = _field_values(E_total_dg, grid.n_points)
    scat_values = _field_values(E_scat_dg, grid.n_points)
    inc_values = _field_values(E_inc_dg, grid.n_points)

    total_norm = np.sqrt(np.abs(total_values[:, 0]) ** 2 + np.abs(total_values[:, 1]) ** 2)
    scat_norm = np.sqrt(np.abs(scat_values[:, 0]) ** 2 + np.abs(scat_values[:, 1]) ** 2)
    inc_norm = np.sqrt(np.abs(inc_values[:, 0]) ** 2 + np.abs(inc_values[:, 1]) ** 2)

    paraview_grid = grid.copy()
    _add_complex_field_arrays(paraview_grid, "E_inc", inc_values, inc_norm)
    _add_complex_field_arrays(paraview_grid, "E_scat", scat_values, scat_norm)
    _add_complex_field_arrays(paraview_grid, "E_total", total_values, total_norm)
    _add_domain_cell_arrays(paraview_grid, mesh_data, cfg)
    _add_numeric_metadata(paraview_grid)
    paraview_grid.save(out_dir / f"fields_for_paraview_rank{comm.rank:04d}.vtu")
    comm.barrier()
    if comm.rank == 0:
        _write_parallel_vtu_collection(out_dir, comm.size)


def _save_parallel_scalar_paraview_fields(
    V_dg,
    mesh_data,
    cfg: SimulationConfig,
    E_inc_dg,
    E_scat_dg,
    E_total_dg,
    out_dir: Path,
):
    comm = mesh_data.mesh.comm
    grid, _ = _field_grid(V_dg)
    total_values = _scalar_field_values(E_total_dg, grid.n_points)
    scat_values = _scalar_field_values(E_scat_dg, grid.n_points)
    inc_values = _scalar_field_values(E_inc_dg, grid.n_points)

    paraview_grid = grid.copy()
    _add_complex_scalar_field_arrays(paraview_grid, "E_inc", inc_values)
    _add_complex_scalar_field_arrays(paraview_grid, "E_scat", scat_values)
    _add_complex_scalar_field_arrays(paraview_grid, "E_total", total_values)
    _add_domain_cell_arrays(paraview_grid, mesh_data, cfg)
    _add_numeric_metadata(paraview_grid)
    paraview_grid.save(out_dir / f"fields_for_paraview_rank{comm.rank:04d}.vtu")
    comm.barrier()
    if comm.rank == 0:
        _write_parallel_vtu_collection(out_dir, comm.size)


def save_fields_and_plots(mesh_data, cfg: SimulationConfig, E_inc, E_scat, E_total, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    gdim = mesh_data.mesh.geometry.dim
    V_dg = fem.functionspace(mesh_data.mesh, ("DG", cfg.visualization_degree, (gdim,)))

    E_inc_dg = fem.Function(V_dg, name="E_inc")
    E_scat_dg = fem.Function(V_dg, name="E_scat")
    E_total_dg = fem.Function(V_dg, name="E_total")
    E_inc_dg.interpolate(E_inc)
    E_scat_dg.interpolate(E_scat)
    E_total_dg.interpolate(E_total)

    try:
        with io.VTXWriter(comm, out_dir / "E_inc.bp", E_inc_dg) as writer:
            writer.write(0.0)
        with io.VTXWriter(comm, out_dir / "E_scat.bp", E_scat_dg) as writer:
            writer.write(0.0)
        with io.VTXWriter(comm, out_dir / "E_total.bp", E_total_dg) as writer:
            writer.write(0.0)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "vtx_warning.txt").write_text(str(exc), encoding="utf-8")

    def local_max_norm(field):
        values = field.x.array.reshape(-1, gdim)
        if values.size == 0:
            return 0.0
        return float(np.max(np.sqrt(np.sum(np.abs(values) ** 2, axis=1))))

    max_abs_E_inc = comm.allreduce(local_max_norm(E_inc_dg), op=MPI.MAX)
    max_abs_E_scat = comm.allreduce(local_max_norm(E_scat_dg), op=MPI.MAX)
    max_abs_E_total = comm.allreduce(local_max_norm(E_total_dg), op=MPI.MAX)

    if comm.size > 1:
        _save_parallel_paraview_fields(V_dg, mesh_data, cfg, E_inc_dg, E_scat_dg, E_total_dg, out_dir)
        if comm.rank == 0:
            (out_dir / "postprocess_parallel_note.txt").write_text(
                "MPI run: VTX .bp field files were written collectively. "
                "Rank-local VTU files and fields_for_paraview_parallel.pvd were also written for ParaView. "
                "Open fields_for_paraview_parallel.pvd to see the full distributed result.\n",
                encoding="utf-8",
            )
        return {
            "max_abs_E_inc": max_abs_E_inc,
            "max_abs_E_scat": max_abs_E_scat,
            "max_abs_E_total": max_abs_E_total,
            "parallel_visualization_note": "VTX .bp and rank-local VTU/PVD collection written.",
        }

    save_mesh_plots(mesh_data, cfg, out_dir)
    grid, coords = _field_grid(V_dg)
    total_values = _field_values(E_total_dg, grid.n_points)
    scat_values = _field_values(E_scat_dg, grid.n_points)
    inc_values = _field_values(E_inc_dg, grid.n_points)

    total_norm = np.sqrt(np.abs(total_values[:, 0]) ** 2 + np.abs(total_values[:, 1]) ** 2)
    scat_norm = np.sqrt(np.abs(scat_values[:, 0]) ** 2 + np.abs(scat_values[:, 1]) ** 2)
    inc_norm = np.sqrt(np.abs(inc_values[:, 0]) ** 2 + np.abs(inc_values[:, 1]) ** 2)

    _save_paraview_fields(
        grid, mesh_data, cfg, inc_values, scat_values, total_values, inc_norm, scat_norm, total_norm, out_dir
    )

    _save_scalar(grid, "Re Ex", total_values[:, 0].real, out_dir / "Ex_real.png")
    _save_scalar(grid, "Im Ex", total_values[:, 0].imag, out_dir / "Ex_imag.png")
    _save_scalar(grid, "Re Ey", total_values[:, 1].real, out_dir / "Ey_real.png")
    _save_scalar(grid, "Im Ey", total_values[:, 1].imag, out_dir / "Ey_imag.png")
    _save_scalar(grid, "|E_total|", total_norm, out_dir / "E_total_norm.png", cmap="viridis")
    _save_scalar(grid, "|E_scat|", scat_norm, out_dir / "E_scat_norm.png", cmap="magma")
    _save_scalar(
        grid,
        "arg Ex_total",
        np.angle(total_values[:, 0]),
        out_dir / "E_total_phase_or_component_phase.png",
        cmap="twilight",
    )
    _save_quiver(grid, coords, total_values, total_norm, out_dir / "E_vector_quiver_real.png")

    return {
        "max_abs_E_inc": max_abs_E_inc,
        "max_abs_E_scat": max_abs_E_scat,
        "max_abs_E_total": max_abs_E_total,
    }


def save_scalar_fields_and_plots(mesh_data, cfg: SimulationConfig, E_inc, E_scat, E_total, out_dir: Path):
    """Save TE scalar Ez fields using the same artifact names as the TM path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    V_dg = fem.functionspace(mesh_data.mesh, ("DG", cfg.visualization_degree))

    E_inc_dg = fem.Function(V_dg, name="E_inc")
    E_scat_dg = fem.Function(V_dg, name="E_scat")
    E_total_dg = fem.Function(V_dg, name="E_total")
    E_inc_dg.interpolate(E_inc)
    E_scat_dg.interpolate(E_scat)
    E_total_dg.interpolate(E_total)

    try:
        with io.VTXWriter(comm, out_dir / "E_inc.bp", E_inc_dg) as writer:
            writer.write(0.0)
        with io.VTXWriter(comm, out_dir / "E_scat.bp", E_scat_dg) as writer:
            writer.write(0.0)
        with io.VTXWriter(comm, out_dir / "E_total.bp", E_total_dg) as writer:
            writer.write(0.0)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "vtx_warning.txt").write_text(str(exc), encoding="utf-8")

    def local_max_abs(field):
        values = field.x.array
        if values.size == 0:
            return 0.0
        return float(np.max(np.abs(values)))

    max_abs_E_inc = comm.allreduce(local_max_abs(E_inc_dg), op=MPI.MAX)
    max_abs_E_scat = comm.allreduce(local_max_abs(E_scat_dg), op=MPI.MAX)
    max_abs_E_total = comm.allreduce(local_max_abs(E_total_dg), op=MPI.MAX)

    if comm.size > 1:
        _save_parallel_scalar_paraview_fields(V_dg, mesh_data, cfg, E_inc_dg, E_scat_dg, E_total_dg, out_dir)
        if comm.rank == 0:
            (out_dir / "postprocess_parallel_note.txt").write_text(
                "MPI run: scalar TE VTX .bp field files were written collectively. "
                "Rank-local VTU files and fields_for_paraview_parallel.pvd were also written for ParaView.\n",
                encoding="utf-8",
            )
        return {
            "max_abs_E_inc": max_abs_E_inc,
            "max_abs_E_scat": max_abs_E_scat,
            "max_abs_E_total": max_abs_E_total,
            "parallel_visualization_note": "VTX .bp and rank-local scalar VTU/PVD collection written.",
        }

    save_mesh_plots(mesh_data, cfg, out_dir)
    grid, _ = _field_grid(V_dg)
    total_values = _scalar_field_values(E_total_dg, grid.n_points)
    scat_values = _scalar_field_values(E_scat_dg, grid.n_points)
    inc_values = _scalar_field_values(E_inc_dg, grid.n_points)

    _add_complex_scalar_field_arrays(grid, "E_inc", inc_values)
    _add_complex_scalar_field_arrays(grid, "E_scat", scat_values)
    _add_complex_scalar_field_arrays(grid, "E_total", total_values)
    _add_domain_cell_arrays(grid, mesh_data, cfg)
    _add_numeric_metadata(grid)
    grid.save(out_dir / "fields_for_paraview.vtu")

    _save_scalar(grid, "Re Ez", total_values.real, out_dir / "Ez_real.png")
    _save_scalar(grid, "Im Ez", total_values.imag, out_dir / "Ez_imag.png")
    _save_scalar(grid, "|E_total|", np.abs(total_values), out_dir / "E_total_norm.png", cmap="viridis")
    _save_scalar(grid, "|E_scat|", np.abs(scat_values), out_dir / "E_scat_norm.png", cmap="magma")
    _save_scalar(
        grid,
        "arg Ez_total",
        np.angle(total_values),
        out_dir / "E_total_phase_or_component_phase.png",
        cmap="twilight",
    )

    return {
        "max_abs_E_inc": max_abs_E_inc,
        "max_abs_E_scat": max_abs_E_scat,
        "max_abs_E_total": max_abs_E_total,
    }
