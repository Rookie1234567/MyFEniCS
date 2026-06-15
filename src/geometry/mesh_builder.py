from __future__ import annotations

from math import ceil
from pathlib import Path

import gmsh
from mpi4py import MPI

from dolfinx import io
from dolfinx.io import gmsh as gmshio

from ..common.config import SimulationConfig


def _curve_node_count(length: float, target_size: float) -> int:
    return max(2, int(ceil(length / target_size)) + 1)


def build_mesh(cfg: SimulationConfig, out_dir: Path):
    """Build one structured Gmsh unit-cell mesh with matching left/right facets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    gmsh.initialize()
    gmsh.model.add(f"{cfg.case_name}_unit_cell")

    try:
        if comm.rank == 0:
            x_coords = [cfg.x_min, cfg.grating_x_min, cfg.grating_x_max, cfg.x_max]
            y_coords = [
                *( [cfg.y_min] if cfg.use_pml else [] ),
                cfg.physical_y_min,
                cfg.substrate_y_max,
                cfg.grating_y_max,
                cfg.physical_y_max,
                *( [cfg.y_max] if cfg.use_pml else [] ),
            ]

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

                    if cfg.use_pml and j == 0:
                        physical_tag = cfg.tags.bottom_pml
                    elif cfg.use_pml and j == len(y_coords) - 2:
                        physical_tag = cfg.tags.top_pml
                    elif y_coords[j] >= cfg.substrate_y_min - 1e-12 and y_coords[j + 1] <= cfg.substrate_y_max + 1e-12:
                        physical_tag = cfg.tags.substrate
                    elif (
                        i == 1
                        and abs(y_coords[j] - cfg.grating_y_min) < 1e-12
                        and abs(y_coords[j + 1] - cfg.grating_y_max) < 1e-12
                    ):
                        physical_tag = cfg.tags.grating
                    else:
                        physical_tag = cfg.tags.air
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
