from __future__ import annotations

from math import ceil
from pathlib import Path

from ..common.config import SimulationConfig


_TOL = 1.0e-10


def _curve_node_count(length: float, target_size: float) -> int:
    return max(2, int(ceil(length / target_size)) + 1)


def _unique_sorted(values: list[float]) -> list[float]:
    ordered = sorted(float(value) for value in values)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > _TOL:
            unique.append(value)
    return unique


def _add_if_inside(values: list[float], value: float, low: float, high: float) -> None:
    if low + _TOL < value < high - _TOL:
        values.append(float(value))


def mesh_axis_coordinates_2d(cfg: SimulationConfig) -> tuple[list[float], list[float]]:
    """Return the structured 2D mesh coordinate axes used by the Gmsh builder."""
    x_coords = [cfg.x_min, cfg.grating_x_min, cfg.grating_x_max, cfg.x_max]
    y_coords = [
        *([cfg.y_min] if cfg.use_pml else []),
        cfg.physical_y_min,
        cfg.substrate_y_max,
        cfg.grating_y_max,
        cfg.physical_y_max,
        *([cfg.y_max] if cfg.use_pml else []),
    ]

    if cfg.mesh_lock_near_field_template:
        near_x_min = max(cfg.x_min, cfg.grating_x_min - cfg.near_field_margin_x)
        near_x_max = min(cfg.x_max, cfg.grating_x_max + cfg.near_field_margin_x)
        _add_if_inside(x_coords, near_x_min, cfg.x_min, cfg.x_max)
        _add_if_inside(x_coords, near_x_max, cfg.x_min, cfg.x_max)

        near_sub_bottom = max(cfg.physical_y_min, cfg.substrate_y_max - cfg.near_field_sub_depth)
        near_air_top = min(cfg.physical_y_max, cfg.near_field_air_top)
        _add_if_inside(y_coords, near_sub_bottom, cfg.y_min, cfg.y_max)
        _add_if_inside(y_coords, near_air_top, cfg.y_min, cfg.y_max)

    return _unique_sorted(x_coords), _unique_sorted(y_coords)


def _interval_inside(low: float, high: float, target_low: float, target_high: float) -> bool:
    return low >= target_low - _TOL and high <= target_high + _TOL


def material_tag_for_rect_2d(cfg: SimulationConfig, x0: float, x1: float, y0: float, y1: float) -> int:
    """Classify one structured rectangle by material tag without midpoint approximation."""
    if cfg.use_pml and y1 <= cfg.physical_y_min + _TOL:
        return cfg.tags.bottom_pml
    if cfg.use_pml and y0 >= cfg.physical_y_max - _TOL:
        return cfg.tags.top_pml
    if _interval_inside(y0, y1, cfg.substrate_y_min, cfg.substrate_y_max):
        return cfg.tags.substrate
    if (
        _interval_inside(x0, x1, cfg.grating_x_min, cfg.grating_x_max)
        and _interval_inside(y0, y1, cfg.grating_y_min, cfg.grating_y_max)
    ):
        return cfg.tags.grating
    return cfg.tags.air


def build_mesh(cfg: SimulationConfig, out_dir: Path):
    """Build one structured Gmsh unit-cell mesh with matching left/right facets."""
    import gmsh
    from dolfinx import io
    from dolfinx.io import gmsh as gmshio
    from mpi4py import MPI

    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    gmsh.initialize()
    gmsh.model.add(f"{cfg.case_name}_unit_cell")

    try:
        if comm.rank == 0:
            if cfg.mesh_cell_shape not in ("triangle", "quadrilateral"):
                raise ValueError("mesh_cell_shape must be 'triangle' or 'quadrilateral'.")
            x_coords, y_coords = mesh_axis_coordinates_2d(cfg)

            points: dict[tuple[int, int], int] = {}
            for j, y in enumerate(y_coords):
                for i, x in enumerate(x_coords):
                    points[(i, j)] = gmsh.model.geo.addPoint(x, y, 0.0, cfg.mesh_target_size)

            horizontal: dict[tuple[int, int], int] = {}
            for j in range(len(y_coords)):
                for i in range(len(x_coords) - 1):
                    tag = gmsh.model.geo.addLine(points[(i, j)], points[(i + 1, j)])
                    horizontal[(i, j)] = tag
                    gmsh.model.geo.mesh.setTransfiniteCurve(
                        tag, _curve_node_count(x_coords[i + 1] - x_coords[i], cfg.mesh_target_size)
                    )

            vertical: dict[tuple[int, int], int] = {}
            for i in range(len(x_coords)):
                for j in range(len(y_coords) - 1):
                    tag = gmsh.model.geo.addLine(points[(i, j)], points[(i, j + 1)])
                    vertical[(i, j)] = tag
                    gmsh.model.geo.mesh.setTransfiniteCurve(
                        tag, _curve_node_count(y_coords[j + 1] - y_coords[j], cfg.mesh_target_size)
                    )

            surfaces_by_tag = {
                cfg.tags.air: [],
                cfg.tags.substrate: [],
                cfg.tags.grating: [],
                cfg.tags.top_pml: [],
                cfg.tags.bottom_pml: [],
            }
            for j in range(len(y_coords) - 1):
                for i in range(len(x_coords) - 1):
                    loop = gmsh.model.geo.addCurveLoop(
                        [
                            horizontal[(i, j)],
                            vertical[(i + 1, j)],
                            -horizontal[(i, j + 1)],
                            -vertical[(i, j)],
                        ]
                    )
                    surf = gmsh.model.geo.addPlaneSurface([loop])
                    gmsh.model.geo.mesh.setTransfiniteSurface(surf)
                    if cfg.mesh_cell_shape == "quadrilateral":
                        gmsh.model.geo.mesh.setRecombine(2, surf)

                    physical_tag = material_tag_for_rect_2d(
                        cfg,
                        x_coords[i],
                        x_coords[i + 1],
                        y_coords[j],
                        y_coords[j + 1],
                    )
                    surfaces_by_tag[physical_tag].append(surf)

            gmsh.model.geo.synchronize()
            names = {
                cfg.tags.air: "air",
                cfg.tags.substrate: "substrate",
                cfg.tags.grating: "rectangular_grating",
                cfg.tags.top_pml: "top_pml",
                cfg.tags.bottom_pml: "bottom_pml",
            }
            for tag, surfaces in surfaces_by_tag.items():
                if surfaces:
                    gmsh.model.addPhysicalGroup(2, surfaces, tag=tag, name=names[tag])

            gmsh.model.addPhysicalGroup(
                1,
                [vertical[(0, j)] for j in range(len(y_coords) - 1)],
                tag=cfg.tags.left,
                name="left_floquet",
            )
            gmsh.model.addPhysicalGroup(
                1,
                [vertical[(len(x_coords) - 1, j)] for j in range(len(y_coords) - 1)],
                tag=cfg.tags.right,
                name="right_floquet",
            )
            gmsh.model.addPhysicalGroup(
                1,
                [horizontal[(i, len(y_coords) - 1)] for i in range(len(x_coords) - 1)],
                tag=cfg.tags.outer_top,
                name="outer_top",
            )
            gmsh.model.addPhysicalGroup(
                1,
                [horizontal[(i, 0)] for i in range(len(x_coords) - 1)],
                tag=cfg.tags.outer_bottom,
                name="outer_bottom",
            )

            gmsh.model.mesh.generate(2)
            gmsh.write(str(out_dir / "mesh.msh"))

        mesh_data = gmshio.model_to_mesh(gmsh.model, comm, 0, gdim=2)
    finally:
        gmsh.finalize()

    try:
        with io.XDMFFile(comm, out_dir / "mesh.xdmf", "w") as xdmf:
            xdmf.write_mesh(mesh_data.mesh)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "mesh_xdmf_warning.txt").write_text(str(exc), encoding="utf-8")

    return mesh_data
