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


def _owned_cell_count(mesh) -> int:
    """Return the number of cells owned by this rank.

    DOLFINx rank-local meshes can also carry ghost cells.  Those ghost cells are
    useful for assembly, but they must not be counted as independent field
    samples when comparing MPI runs against serial runs.
    """
    tdim = mesh.topology.dim
    cell_map = mesh.topology.index_map(tdim)
    return int(cell_map.size_local)


def _owned_point_mask(V_dg, num_points: int) -> np.ndarray:
    """Mask VTK/DG interpolation points belonging to owned cells only."""
    mask = np.zeros(num_points, dtype=bool)
    n_owned_cells = _owned_cell_count(V_dg.mesh)
    for cell in range(n_owned_cells):
        cell_dofs = np.asarray(V_dg.dofmap.cell_dofs(cell), dtype=np.int64)
        valid = (cell_dofs >= 0) & (cell_dofs < num_points)
        mask[cell_dofs[valid]] = True
    if n_owned_cells > 0 and not np.any(mask):
        raise RuntimeError(
            "Could not map owned DG cell dofs to ParaView points. "
            "Parallel 3D postprocessing cannot safely filter ghost cells."
        )
    return mask


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
    """Write one vector real/imag pair plus one magnitude scalar.

    ParaView treats the real/imag arrays as 3-component vectors, so Ex/Ey/Ez
    can be selected from the component menu instead of writing separate scalar
    arrays for every component.
    """
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
    """Write a small PVD collection that points ParaView to rank-local VTUs."""
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


def _global_max_norm(comm, values: np.ndarray, mask: np.ndarray | None = None) -> float:
    if mask is not None:
        values = values[np.asarray(mask, dtype=bool)]
    local = float(np.max(_norm(values))) if values.size else 0.0
    return comm.allreduce(local, op=MPI.MAX)


def _global_max_component_abs(comm, values: np.ndarray, component: int, mask: np.ndarray | None = None) -> float:
    if mask is not None:
        values = values[np.asarray(mask, dtype=bool)]
    local = float(np.max(np.abs(values[:, component]))) if values.size else 0.0
    return comm.allreduce(local, op=MPI.MAX)


def _global_mean_vector(comm, values: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    if mask is not None:
        values = values[np.asarray(mask, dtype=bool)]
    local_sum = np.sum(values, axis=0) if len(values) else np.zeros(3, dtype=np.float64)
    total_sum = comm.allreduce(local_sum, op=MPI.SUM)
    total_count = comm.allreduce(len(values), op=MPI.SUM)
    if total_count == 0:
        return np.zeros(3, dtype=np.float64)
    return np.asarray(total_sum, dtype=np.float64) / float(total_count)


def _field_component_l2_metrics(mesh_data, cfg: SimulationConfig3D, field) -> dict[str, object]:
    """Assemble component L2 diagnostics on the original H(curl) field.

    These metrics bypass DG/ParaView interpolation.  They are useful for
    separating a real MPI solve inconsistency from a visualization-only issue.
    The length unit is still nm, so the L2 values are mainly diagnostic; the
    component ratios are the robust comparison quantities.
    """
    dx = ufl.Measure("dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
    comm = mesh_data.mesh.comm
    integrals: list[float] = []
    for component in range(3):
        local = fem.assemble_scalar(fem.form(ufl.inner(field[component], field[component]) * d_physical))
        total = comm.allreduce(local, op=MPI.SUM)
        integrals.append(max(float(np.real(total)), 0.0) * cfg.electric_field_scale_V_per_m**2)
    total_integral = max(float(sum(integrals)), 0.0)
    l2_values = [float(np.sqrt(value)) for value in integrals]
    total_l2 = float(np.sqrt(total_integral))
    ratios = [float(value / total_integral) if total_integral > 0.0 else 0.0 for value in integrals]
    return {
        "component_l2_integral_E_V2_per_m2_nm3": integrals,
        "component_l2_norm_E_V_per_m_sqrt_nm3": l2_values,
        "component_l2_total_E_V_per_m_sqrt_nm3": total_l2,
        "component_l2_energy_fraction_Ex_Ey_Ez": ratios,
    }


def _interpolation_points(V):
    points = V.element.interpolation_points
    return points() if callable(points) else points


def save_airbox_3d_fields(
    mesh_data,
    cfg: SimulationConfig3D,
    E_numerical,
    out_dir: Path,
    *,
    E_scattered=None,
    E_background=None,
    E_incident_port=None,
) -> dict[str, object]:
    """Save compact 3D E/H fields and return reconstruction metrics.

    The solve uses normalized field amplitudes internally.  ParaView output uses
    E in V/m and H in A/m, with incident_e0_v_per_m as the physical scale.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    V_dg = fem.functionspace(mesh_data.mesh, ("DG", cfg.visualization_degree, (3,)))
    has_exact_reference = not cfg.stage_case.startswith("stage4_")

    E_code_dg = fem.Function(V_dg, name="E_code")
    E_code_dg.interpolate(E_numerical)

    E_num_dg = fem.Function(V_dg, name="E_tot_V_per_m")
    E_num_dg.x.array[:] = cfg.electric_field_scale_V_per_m * E_code_dg.x.array[:]
    E_num_dg.x.scatter_forward()

    E_sca_dg = None
    if E_scattered is not None:
        E_sca_code_dg = fem.Function(V_dg, name="E_sca_code")
        E_sca_code_dg.interpolate(E_scattered)
        E_sca_dg = fem.Function(V_dg, name="E_sca_V_per_m")
        E_sca_dg.x.array[:] = cfg.electric_field_scale_V_per_m * E_sca_code_dg.x.array[:]
        E_sca_dg.x.scatter_forward()

    E_bg_dg = None
    if E_background is not None:
        E_bg_code_dg = fem.Function(V_dg, name="E_b_code")
        E_bg_code_dg.interpolate(E_background)
        E_bg_dg = fem.Function(V_dg, name="E_b_V_per_m")
        E_bg_dg.x.array[:] = cfg.electric_field_scale_V_per_m * E_bg_code_dg.x.array[:]
        E_bg_dg.x.scatter_forward()

    E_port_dg = None
    if E_incident_port is not None:
        E_port_code_dg = fem.Function(V_dg, name="E_incident_port_code")
        E_port_code_dg.interpolate(E_incident_port)
        E_port_dg = fem.Function(V_dg, name="E_incident_port_V_per_m")
        E_port_dg.x.array[:] = cfg.electric_field_scale_V_per_m * E_port_code_dg.x.array[:]
        E_port_dg.x.scatter_forward()

    E_exact_dg = None
    if has_exact_reference:
        E_exact_dg = fem.Function(V_dg, name="E_exact_V_per_m")
        E_exact_dg.interpolate(lambda x: _plane_wave_values(cfg, x.T).T)

    h_expr = (cfg.magnetic_field_scale_A_per_m / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(E_numerical)
    H_dg = fem.Function(V_dg, name="H_A_per_m_from_curl")
    H_dg.interpolate(fem.Expression(h_expr, _interpolation_points(V_dg)))

    H_exact_dg = None
    if has_exact_reference:
        H_exact_dg = fem.Function(V_dg, name="H_exact_A_per_m")
        H_exact_dg.interpolate(lambda x: _exact_h_values(cfg, x.T).T)

    vtx_output_status = "skipped_mpi"
    vtx_output_files: list[str] = []
    if comm.size == 1:
        try:
            with io.VTXWriter(comm, out_dir / "E_3d_numerical.bp", E_num_dg) as writer:
                writer.write(0.0)
            with io.VTXWriter(comm, out_dir / "H_3d_A_per_m_from_curl.bp", H_dg) as writer:
                writer.write(0.0)
            vtx_output_status = "written_serial"
            vtx_output_files = ["E_3d_numerical.bp", "H_3d_A_per_m_from_curl.bp"]
        except Exception as exc:  # pragma: no cover - best-effort artifact
            vtx_output_status = "failed_serial"
            if comm.rank == 0:
                (out_dir / "vtx_3d_warning.txt").write_text(str(exc), encoding="utf-8")
    elif comm.rank == 0:
        (out_dir / "vtx_3d_skipped_mpi.txt").write_text(
            "MPI 3D VTX .bp output is skipped because ADIOS2/VTXWriter can raise "
            "unrecoverable BUS errors for large parallel vector fields in the current container. "
            "Use fields_3d_for_paraview_parallel.pvd instead.\n",
            encoding="utf-8",
        )

    grid, coords = _field_grid(V_dg)
    e_num = _values(E_num_dg, grid.n_points)
    e_sca = _values(E_sca_dg, grid.n_points) if E_sca_dg is not None else None
    e_bg = _values(E_bg_dg, grid.n_points) if E_bg_dg is not None else None
    e_port = _values(E_port_dg, grid.n_points) if E_port_dg is not None else None
    e_exact = _values(E_exact_dg, grid.n_points) if E_exact_dg is not None else None
    e_error = e_num - e_exact if e_exact is not None else None
    h_num = _values(H_dg, grid.n_points)
    h_exact = _values(H_exact_dg, grid.n_points) if H_exact_dg is not None else None
    h_error = h_num - h_exact if h_exact is not None else None

    paraview_grid = grid.copy()
    owned_cell_count = _owned_cell_count(mesh_data.mesh)
    owned_point_mask = _owned_point_mask(V_dg, grid.n_points)
    postprocess_point_scope = "owned_cells_only" if comm.size > 1 else "serial_all_cells"
    local_owned_point_count = int(np.count_nonzero(owned_point_mask))
    local_total_point_count = int(grid.n_points)
    global_owned_point_count = int(comm.allreduce(local_owned_point_count, op=MPI.SUM))
    global_total_point_count = int(comm.allreduce(local_total_point_count, op=MPI.SUM))
    z_values = np.asarray(paraview_grid.points[:, 2], dtype=np.float64)
    z_tol = 1.0e-8 * max(cfg.domain_z_max - cfg.domain_z_min, 1.0)
    physical_point_mask_all = (z_values >= cfg.physical_z_min - z_tol) & (z_values <= cfg.physical_z_max + z_tol)
    pml_point_mask_all = ~physical_point_mask_all
    physical_point_mask = owned_point_mask & physical_point_mask_all
    pml_point_mask = owned_point_mask & pml_point_mask_all
    # ParaView arrays use physical display units.  The solve itself is still
    # normalized to E0=1, and cfg supplies the V/m and A/m scaling factors.
    # E_numerical is already the total field for this writer, so the older
    # E_V_per_m alias is not written anymore.
    _add_complex_vector(paraview_grid, "E_tot_V_per_m", e_num)
    if e_sca is not None:
        _add_complex_vector(paraview_grid, "E_sca_V_per_m", e_sca)
    if e_bg is not None:
        _add_complex_vector(paraview_grid, "E_b_V_per_m", e_bg)
    if e_port is not None:
        _add_complex_vector(paraview_grid, "E_incident_port_V_per_m", e_port)
    if e_exact is not None:
        _add_abs_scalar(paraview_grid, "E_exact_abs_V_per_m", e_exact)
        _add_abs_scalar(paraview_grid, "E_error_abs_V_per_m", e_error)
    _add_complex_vector(paraview_grid, "H_A_per_m", h_num)
    if h_exact is not None:
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

    paraview_cells_before_owned_filter = int(paraview_grid.n_cells)
    paraview_owned_cell_filter_applied = False
    if comm.size > 1 and owned_cell_count < paraview_grid.n_cells:
        owned_cells = np.arange(owned_cell_count, dtype=np.int64)
        paraview_grid = paraview_grid.extract_cells(owned_cells)
        paraview_owned_cell_filter_applied = True
    paraview_cells_written = int(paraview_grid.n_cells)

    if comm.size > 1:
        # PyVista writes one local VTU per rank.  Rank0 writes the collection
        # file after a barrier so ParaView can open the distributed result.
        paraview_path = out_dir / "fields_3d_for_paraview_parallel.pvd"
        paraview_grid.save(out_dir / f"fields_3d_for_paraview_rank{comm.rank:04d}.vtu")
        comm.barrier()
        if comm.rank == 0:
            _write_parallel_vtu_collection(out_dir, comm.size)
    else:
        paraview_grid.save(out_dir / "fields_3d_for_paraview.vtu")
        paraview_path = out_dir / "fields_3d_for_paraview.vtu"

    max_e_exact = _global_max_norm(comm, e_exact, owned_point_mask) if e_exact is not None else None
    max_e_num = _global_max_norm(comm, e_num, owned_point_mask)
    max_e_num_physical = _global_max_norm(comm, e_num, physical_point_mask)
    max_e_num_pml = _global_max_norm(comm, e_num, pml_point_mask)
    max_e_error = _global_max_norm(comm, e_error, owned_point_mask) if e_error is not None else None
    max_h = _global_max_norm(comm, h_num, owned_point_mask)
    max_h_exact = _global_max_norm(comm, h_exact, owned_point_mask) if h_exact is not None else None
    max_h_error = _global_max_norm(comm, h_error, owned_point_mask) if h_error is not None else None

    poynting = 0.5 * np.real(np.cross(e_num, np.conj(h_num)))
    mean_poynting = _global_mean_vector(comm, poynting, owned_point_mask)
    direction = cfg.direction_vector
    mean_norm = float(np.linalg.norm(mean_poynting))
    poynting_cosine = float(np.dot(mean_poynting, direction) / mean_norm) if mean_norm > 0.0 else float("nan")

    result = {
        "max_abs_E_exact": max_e_exact,
        "max_abs_E": max_e_num,
        "max_abs_Ex": _global_max_component_abs(comm, e_num, 0, owned_point_mask),
        "max_abs_Ey": _global_max_component_abs(comm, e_num, 1, owned_point_mask),
        "max_abs_Ez": _global_max_component_abs(comm, e_num, 2, owned_point_mask),
        "max_abs_E_physical_z_region": max_e_num_physical,
        "max_abs_E_pml_z_region": max_e_num_pml,
        "max_abs_E_error": max_e_error,
        "relative_max_abs_E_error": None
        if max_e_error is None or max_e_exact is None
        else max_e_error / max(max_e_exact, 1.0e-30),
        "max_abs_H": max_h,
        "max_abs_H_exact": max_h_exact,
        "max_abs_H_error": max_h_error,
        "relative_max_abs_H_error": None
        if max_h_error is None or max_h_exact is None
        else max_h_error / max(max_h_exact, 1.0e-30),
        "mean_poynting_W_per_m2": mean_poynting.tolist(),
        "poynting_direction_cosine": poynting_cosine,
        "curl_postprocess_success": True,
        "paraview_file": str(paraview_path),
        "postprocess_point_scope": postprocess_point_scope,
        "postprocess_local_owned_points": local_owned_point_count,
        "postprocess_local_total_points_before_owned_filter": local_total_point_count,
        "postprocess_global_owned_points": global_owned_point_count,
        "postprocess_global_total_points_before_owned_filter": global_total_point_count,
        "paraview_owned_cell_filter_applied": paraview_owned_cell_filter_applied,
        "paraview_local_owned_cells": owned_cell_count,
        "paraview_local_cells_before_owned_filter": paraview_cells_before_owned_filter,
        "paraview_local_cells_written": paraview_cells_written,
        "vtx_3d_output_status": vtx_output_status,
        "vtx_3d_output_files": vtx_output_files,
        "exact_reference_available": has_exact_reference,
        "exact_reference_note": None
        if has_exact_reference
        else "Stage 4 grating has no analytic exact solution; E_b is the layered background field, so E_exact is not written.",
        "paraview_e_field_arrays": [
            "E_tot_V_per_m_real",
            "E_tot_V_per_m_imag",
            "E_tot_V_per_m_abs",
            *([] if e_sca is None else ["E_sca_V_per_m_real", "E_sca_V_per_m_imag", "E_sca_V_per_m_abs"]),
            *([] if e_bg is None else ["E_b_V_per_m_real", "E_b_V_per_m_imag", "E_b_V_per_m_abs"]),
            *(
                []
                if e_port is None
                else [
                    "E_incident_port_V_per_m_real",
                    "E_incident_port_V_per_m_imag",
                    "E_incident_port_V_per_m_abs",
                ]
            ),
        ],
    }
    result.update(_field_component_l2_metrics(mesh_data, cfg, E_numerical))
    if e_sca is not None:
        result["max_abs_E_sca"] = _global_max_norm(comm, e_sca, owned_point_mask)
        result["max_abs_E_sca_Ex"] = _global_max_component_abs(comm, e_sca, 0, owned_point_mask)
        result["max_abs_E_sca_Ey"] = _global_max_component_abs(comm, e_sca, 1, owned_point_mask)
        result["max_abs_E_sca_Ez"] = _global_max_component_abs(comm, e_sca, 2, owned_point_mask)
        result["max_abs_E_sca_physical_z_region"] = _global_max_norm(comm, e_sca, physical_point_mask)
        result["max_abs_E_sca_pml_z_region"] = _global_max_norm(comm, e_sca, pml_point_mask)
    if e_bg is not None:
        result["max_abs_E_b"] = _global_max_norm(comm, e_bg, owned_point_mask)
        result["max_abs_E_b_Ex"] = _global_max_component_abs(comm, e_bg, 0, owned_point_mask)
        result["max_abs_E_b_Ey"] = _global_max_component_abs(comm, e_bg, 1, owned_point_mask)
        result["max_abs_E_b_Ez"] = _global_max_component_abs(comm, e_bg, 2, owned_point_mask)
        result["max_abs_E_b_physical_z_region"] = _global_max_norm(comm, e_bg, physical_point_mask)
        result["max_abs_E_b_pml_z_region"] = _global_max_norm(comm, e_bg, pml_point_mask)
    if e_port is not None:
        result["max_abs_E_incident_port"] = _global_max_norm(comm, e_port, owned_point_mask)
        result["max_abs_E_incident_port_Ex"] = _global_max_component_abs(comm, e_port, 0, owned_point_mask)
        result["max_abs_E_incident_port_Ey"] = _global_max_component_abs(comm, e_port, 1, owned_point_mask)
        result["max_abs_E_incident_port_Ez"] = _global_max_component_abs(comm, e_port, 2, owned_point_mask)
        result["max_abs_E_incident_port_physical_z_region"] = _global_max_norm(
            comm,
            e_port,
            physical_point_mask,
        )
    return result
