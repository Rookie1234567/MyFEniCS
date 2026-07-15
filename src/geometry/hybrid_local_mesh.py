from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from dolfinx import mesh
from mpi4py import MPI

from ..common.config_3d import SimulationConfig3D
from .mesh_builder_3d import (
    AirBox3DMesh,
    _axis_stats,
    _mark_cells,
    _structured_hexa_mesh,
    stage4_axis_plan,
)


HybridLocalSide = Literal["bottom", "top"]


@dataclass(frozen=True)
class HybridLocalMesh:
    """One Task32 terminal FEM mesh with an explicit internal interface."""

    side: HybridLocalSide
    mesh_data: AirBox3DMesh
    z_values: np.ndarray
    interface_z_nm: float
    external_z_nm: float
    interface_facet_tag: int
    external_facet_tag: int
    local_interface_outward_normal_sign: int
    modal_interface_outward_normal_sign: int
    global_interface_facet_count: int
    global_external_facet_count: int
    full_mesh_or_field_gathered: bool = False

    @property
    def mesh(self) -> mesh.Mesh:
        return self.mesh_data.mesh

    @property
    def mesh_cells(self) -> tuple[int, int, int]:
        return self.mesh_data.mesh_cells_resolved


def _local_boundary_tags(
    msh: mesh.Mesh,
    cfg: SimulationConfig3D,
    *,
    z_min: float,
    z_max: float,
) -> tuple[mesh.MeshTags, np.ndarray]:
    fdim = msh.topology.dim - 1
    tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, z_max - z_min, 1.0)
    markers = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min, atol=tolerance, rtol=0.0)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max, atol=tolerance, rtol=0.0)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min, atol=tolerance, rtol=0.0)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max, atol=tolerance, rtol=0.0)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], z_min, atol=tolerance, rtol=0.0)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], z_max, atol=tolerance, rtol=0.0)),
    )
    indices = []
    values = []
    for tag, marker in markers:
        facets = mesh.locate_entities_boundary(msh, fdim, marker)
        indices.append(facets)
        values.append(np.full(len(facets), tag, dtype=np.int32))
    facet_indices = np.concatenate(indices).astype(np.int32)
    facet_values = np.concatenate(values).astype(np.int32)
    order = np.argsort(facet_indices)
    facet_indices = facet_indices[order]
    facet_values = facet_values[order]
    return (
        mesh.meshtags(msh, fdim, facet_indices, facet_values),
        np.unique(facet_indices),
    )


def build_hybrid_local_mesh(
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    *,
    bottom_interface_z_nm: float = 10.0,
    top_interface_z_nm: float = 110.0,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> HybridLocalMesh:
    """Slice the reviewed Stage-4 tensor grid into one terminal 3D FEM block."""

    if cfg.geometry_kind != "rectangular_block_grating":
        raise ValueError("Task32 local meshes require the Stage-4 block geometry.")
    if cfg.mesh_cell_type_resolved != "hexahedron":
        raise ValueError("Task32 matching interfaces require a hexahedral mesh.")
    if side not in {"bottom", "top"}:
        raise ValueError(f"Unsupported local side: {side}")

    plan = stage4_axis_plan(cfg, comm.size)
    tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
    interface_z = float(
        bottom_interface_z_nm if side == "bottom" else top_interface_z_nm
    )
    if not float(cfg.domain_z_min) < interface_z < float(cfg.domain_z_max):
        raise ValueError(f"Interface z={interface_z:g} nm lies outside the 3D domain.")
    # Task32 freezes the physical matching planes at z=10/110 nm.  They are
    # already present for h5/h2, but h3's target-spacing Stage-4 axis contains
    # multiples of 3 nm and therefore omits them.  Insert the exact interface
    # into the local z axis instead of moving the physical decomposition.  The
    # transverse x/y grid remains exactly the reviewed Stage-4 grid and hence
    # still matches the independent 2D cross-section mesh.
    global_z_values = np.asarray(plan.z_values, dtype=np.float64)
    if not np.any(
        np.isclose(global_z_values, interface_z, atol=tolerance, rtol=0.0)
    ):
        global_z_values = np.sort(
            np.concatenate((global_z_values, np.asarray([interface_z])))
        )
    if side == "bottom":
        z_values = global_z_values[global_z_values <= interface_z + tolerance]
        external_z = float(cfg.domain_z_min)
        expected_first = external_z
        expected_last = interface_z
        interface_tag = cfg.tags.z_max
        external_tag = cfg.tags.z_min
        local_normal_sign = +1
    else:
        z_values = global_z_values[global_z_values >= interface_z - tolerance]
        external_z = float(cfg.domain_z_max)
        expected_first = interface_z
        expected_last = external_z
        interface_tag = cfg.tags.z_min
        external_tag = cfg.tags.z_max
        local_normal_sign = -1
    z_values = np.asarray(z_values, dtype=np.float64)
    if len(z_values) < 2:
        raise RuntimeError(f"The {side} local block contains no volume cell.")
    if not np.isclose(z_values[0], expected_first, atol=tolerance, rtol=0.0):
        raise RuntimeError(f"The {side} local block has the wrong lower z bound.")
    if not np.isclose(z_values[-1], expected_last, atol=tolerance, rtol=0.0):
        raise RuntimeError(f"The {side} local block has the wrong upper z bound.")

    msh = _structured_hexa_mesh(comm, plan.x_values, plan.y_values, z_values)
    msh.name = f"{cfg.case_name}_{side}_local"
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _local_boundary_tags(
        msh, cfg, z_min=float(z_values[0]), z_max=float(z_values[-1])
    )
    mesh_cells = (
        len(plan.x_values) - 1,
        len(plan.y_values) - 1,
        len(z_values) - 1,
    )
    local_axis_stats = {
        "x": _axis_stats(plan.x_values),
        "y": _axis_stats(plan.y_values),
        "z": _axis_stats(z_values),
    }
    mesh_data = AirBox3DMesh(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved="hexahedron",
        mesh_cells_resolved=mesh_cells,
        z_alignment_warnings=[],
        mesh_spacing_mode_resolved=plan.mesh_spacing_mode_resolved,
        mesh_axis_cell_stats=local_axis_stats,
        material_plane_alignment=plan.material_plane_alignment,
        local_refinement_regions=plan.local_refinement_regions,
    )
    interface_facets = facet_tags.find(interface_tag)
    external_facets = facet_tags.find(external_tag)
    fdim = msh.topology.dim - 1
    num_owned_facets = msh.topology.index_map(fdim).size_local
    interface_owned = interface_facets[interface_facets < num_owned_facets]
    external_owned = external_facets[external_facets < num_owned_facets]
    global_interface = int(comm.allreduce(len(interface_owned), op=MPI.SUM))
    global_external = int(comm.allreduce(len(external_owned), op=MPI.SUM))
    expected_facets = int(mesh_cells[0] * mesh_cells[1])
    if global_interface != expected_facets or global_external != expected_facets:
        raise RuntimeError(
            f"{side} interface/external facet counts {global_interface}/{global_external} "
            f"do not match {expected_facets}."
        )
    return HybridLocalMesh(
        side=side,
        mesh_data=mesh_data,
        z_values=z_values,
        interface_z_nm=interface_z,
        external_z_nm=external_z,
        interface_facet_tag=interface_tag,
        external_facet_tag=external_tag,
        local_interface_outward_normal_sign=local_normal_sign,
        modal_interface_outward_normal_sign=-local_normal_sign,
        global_interface_facet_count=global_interface,
        global_external_facet_count=global_external,
    )
