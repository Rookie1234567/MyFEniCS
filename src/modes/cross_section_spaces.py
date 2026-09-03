from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import ufl
from basix.ufl import element, mixed_element
from dolfinx import default_real_type, fem, graph, mesh
from mpi4py import MPI

from ..common.config_3d import SimulationConfig3D
from ..geometry.mesh_builder_3d import (
    HexaAxisPlan,
    _axis_stats,
    _rank_cell_ids,
    stage4_axis_plan,
)


CrossSectionMaterial = Literal["air", "lossy_homogeneous", "stage4_xy"]


@dataclass(frozen=True)
class CrossSectionMesh:
    """A distributed quadrilateral cross-section matching the Stage-4 x-y grid."""

    mesh: mesh.Mesh
    x_values: np.ndarray
    y_values: np.ndarray
    axis_plan: HexaAxisPlan
    material_kind: CrossSectionMaterial
    epsilon_r: fem.Function

    @property
    def mesh_cells(self) -> tuple[int, int]:
        return (len(self.x_values) - 1, len(self.y_values) - 1)


@dataclass(frozen=True)
class CrossSectionSpaces:
    """Mixed H(curl)-H1 mode space and collapse maps into the parent space."""

    mixed: fem.FunctionSpace
    transverse: fem.FunctionSpace
    longitudinal: fem.FunctionSpace
    transverse_to_mixed: np.ndarray
    longitudinal_to_mixed: np.ndarray
    transverse_degree: int
    longitudinal_degree: int


def _required_array_sha256(value: Any, label: str) -> str:
    try:
        array = np.ascontiguousarray(np.asarray(value))
    except (TypeError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"cross-section {label} hash is unavailable") from exc
    if array.dtype.kind == "O":
        raise RuntimeError(f"cross-section {label} hash is non-numeric")
    return hashlib.sha256(array.tobytes()).hexdigest()


def _index_map_layout(index_map: Any) -> dict[str, Any]:
    local_range = getattr(index_map, "local_range", (0, 0))
    if callable(local_range):
        local_range = local_range()
    layout: dict[str, Any] = {
        "size_local": int(index_map.size_local),
        "num_ghosts": int(index_map.num_ghosts),
        "size_global": int(index_map.size_global),
        "local_range": [int(local_range[0]), int(local_range[1])],
    }
    local_ids = np.arange(
        int(index_map.size_local) + int(index_map.num_ghosts), dtype=np.int32
    )
    local_to_global = getattr(index_map, "local_to_global", None)
    if not callable(local_to_global):
        raise TypeError("cross-section IndexMap lacks local_to_global")
    try:
        global_ids = np.asarray(local_to_global(local_ids))
    except (TypeError, ValueError, RuntimeError) as exc:
        raise RuntimeError("cross-section IndexMap local_to_global failed") from exc
    if global_ids.shape != local_ids.shape:
        raise RuntimeError("cross-section IndexMap local_to_global shape mismatch")
    layout["local_to_global_sha256"] = _required_array_sha256(
        global_ids, "local-to-global"
    )
    layout["local_to_global_count"] = int(global_ids.size)
    layout["local_to_global_dtype"] = str(global_ids.dtype)
    owners = getattr(index_map, "owners", None)
    if callable(owners):
        owners = owners()
    if owners is None:
        raise RuntimeError("cross-section IndexMap lacks ghost owners")
    layout["ghost_owners_sha256"] = _required_array_sha256(owners, "ghost-owner")
    owners_array = np.asarray(owners)
    layout["ghost_owners_count"] = int(owners_array.size)
    layout["ghost_owners_dtype"] = str(owners_array.dtype)
    return layout


def cross_section_layout_identity(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    comm: MPI.Intracomm | None = None,
    preserve_input_partition: bool = False,
) -> dict[str, Any]:
    """Return a compact owner-aware identity for a cross-section layout."""
    mesh_comm = cross_section.mesh.comm if comm is None else comm
    topology = cross_section.mesh.topology
    tdim = topology.dim
    cell_index_map = topology.index_map(tdim)
    mixed_index_map = spaces.mixed.dofmap.index_map
    geometry_dofmap = cross_section.mesh.geometry.dofmap
    geometry_hash = _required_array_sha256(geometry_dofmap, "geometry connectivity")
    topology.create_entity_permutations()
    permutation_info = topology.get_cell_permutation_info()
    permutation_hash = _required_array_sha256(
        permutation_info, "cell permutation info"
    )
    permutation = {
        "source": "topology.get_cell_permutation_info",
        "sha256": permutation_hash,
    }
    orientation = {
        "source": "topology.get_cell_permutation_info",
        "sha256": permutation_hash,
    }
    total_cells = (len(cross_section.x_values) - 1) * (
        len(cross_section.y_values) - 1
    )
    input_cell_ids = np.fromiter(
        _rank_cell_ids(total_cells, mesh_comm.rank, mesh_comm.size), dtype=np.int64
    )
    local_record = {
        "rank": int(mesh_comm.rank),
        "input_cell_ids_sha256": _required_array_sha256(
            input_cell_ids, "input cell ids"
        ),
        "input_cell_count": int(input_cell_ids.size),
        "cells": {
            "index_map": _index_map_layout(cell_index_map),
            "permutation": permutation,
            "orientation": orientation,
            "connectivity": {"source": "geometry_dofmap", "sha256": geometry_hash},
        },
        "mixed_dofs": _index_map_layout(mixed_index_map),
        "transverse_to_mixed_sha256": _required_array_sha256(
            spaces.transverse_to_mixed, "transverse collapse map"
        ),
        "longitudinal_to_mixed_sha256": _required_array_sha256(
            spaces.longitudinal_to_mixed, "longitudinal collapse map"
        ),
    }
    payload: dict[str, Any] = {
        "schema": "task041.cross_section_layout_identity.v1",
        "partition_policy": (
            "input_contiguous_v1" if preserve_input_partition else "dolfinx_graph_default"
        ),
        "mpi_size": int(mesh_comm.size),
        "global_mixed_size": int(mixed_index_map.size_global),
        "rank_layout": mesh_comm.allgather(local_record),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    payload["canonical_json_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def _structured_quad_mesh(
    comm: MPI.Intracomm,
    x_values: np.ndarray,
    y_values: np.ndarray,
    *,
    preserve_input_partition: bool = False,
) -> mesh.Mesh:
    nx = len(x_values) - 1
    ny = len(y_values) - 1
    if nx < 1 or ny < 1:
        raise ValueError("A cross-section mesh needs at least one cell per axis.")

    points = np.asarray(
        [(x, y) for y in y_values for x in x_values], dtype=default_real_type
    )

    def node(i: int, j: int) -> int:
        return j * len(x_values) + i

    cells: list[list[int]] = []
    for cell_id in _rank_cell_ids(nx * ny, comm.rank, comm.size):
        j = int(cell_id) // nx
        i = int(cell_id) - j * nx
        cells.append(
            [node(i, j), node(i + 1, j), node(i, j + 1), node(i + 1, j + 1)]
        )

    coordinate_element = element(
        "Lagrange", "quadrilateral", 1, shape=(2,), dtype=default_real_type
    )
    domain = ufl.Mesh(coordinate_element)
    if preserve_input_partition:

        def keep_input_cell_owners(
            _comm,
            num_partitions: int,
            adjacency,
            _ghost_mode: bool,
        ):
            if int(num_partitions) != int(comm.size):
                raise RuntimeError(
                    "input-preserving partitioner received an unexpected "
                    "partition count"
                )
            destinations = np.full(
                (int(adjacency.num_nodes), 1),
                int(comm.rank),
                dtype=np.int32,
            )
            return graph.adjacencylist(destinations)._cpp_object

        partitioner = mesh.create_cell_partitioner(
            keep_input_cell_owners,
            mesh.GhostMode.shared_facet,
        )
    else:
        partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    return mesh.create_mesh(
        comm,
        np.asarray(cells, dtype=np.int64),
        domain,
        points,
        partitioner=partitioner,
    )


def _cross_section_epsilon(
    msh: mesh.Mesh,
    cfg: SimulationConfig3D,
    material_kind: CrossSectionMaterial,
) -> fem.Function:
    V_eps = fem.functionspace(msh, ("DG", 0))
    epsilon_r = fem.Function(V_eps, name=f"epsilon_r_{material_kind}")

    if material_kind == "air":
        epsilon_r.x.array[:] = complex(cfg.n_air) ** 2
    elif material_kind == "lossy_homogeneous":
        if cfg.n_grating is None:
            raise ValueError("lossy_homogeneous requires cfg.n_grating.")
        epsilon_r.x.array[:] = complex(cfg.n_grating) ** 2
    elif material_kind == "stage4_xy":
        epsilon_r.x.array[:] = complex(cfg.n_air) ** 2
        tdim = msh.topology.dim
        num_owned = msh.topology.index_map(tdim).size_local
        cells = np.arange(num_owned, dtype=np.int32)
        midpoints = mesh.compute_midpoints(msh, tdim, cells)
        tol = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
        inside = (
            (midpoints[:, 0] >= cfg.grating_x_min - tol)
            & (midpoints[:, 0] <= cfg.grating_x_max + tol)
            & (midpoints[:, 1] >= cfg.grating_y_min - tol)
            & (midpoints[:, 1] <= cfg.grating_y_max + tol)
        )
        if cfg.n_grating is None:
            raise ValueError("stage4_xy requires cfg.n_grating.")
        epsilon_r.x.array[cells[inside]] = complex(cfg.n_grating) ** 2
    else:  # pragma: no cover - protected by Literal and explicit runtime guard
        raise ValueError(f"Unsupported cross-section material kind: {material_kind}")

    epsilon_r.x.scatter_forward()
    return epsilon_r


def build_matching_cross_section(
    cfg: SimulationConfig3D,
    material_kind: CrossSectionMaterial,
    *,
    x_values: np.ndarray | None = None,
    y_values: np.ndarray | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    preserve_input_partition: bool = False,
) -> CrossSectionMesh:
    """Build one x-y slice from the exact Stage-4 hexahedral axis plan."""

    plan = stage4_axis_plan(cfg, comm.size)
    if (x_values is None) != (y_values is None):
        raise ValueError("Explicit matching x/y axes must be supplied together.")
    if x_values is None:
        resolved_x = np.asarray(plan.x_values, dtype=np.float64)
        resolved_y = np.asarray(plan.y_values, dtype=np.float64)
    else:
        resolved_x = np.asarray(x_values, dtype=np.float64)
        resolved_y = np.asarray(y_values, dtype=np.float64)
        if (
            resolved_x.ndim != 1
            or resolved_y.ndim != 1
            or len(resolved_x) < 2
            or len(resolved_y) < 2
            or np.any(np.diff(resolved_x) <= 0.0)
            or np.any(np.diff(resolved_y) <= 0.0)
        ):
            raise ValueError("Explicit matching x/y axes must be strictly increasing.")
        tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
        if not (
            np.isclose(resolved_x[0], cfg.x_min, atol=tolerance, rtol=0.0)
            and np.isclose(resolved_x[-1], cfg.x_max, atol=tolerance, rtol=0.0)
            and np.isclose(resolved_y[0], cfg.y_min, atol=tolerance, rtol=0.0)
            and np.isclose(resolved_y[-1], cfg.y_max, atol=tolerance, rtol=0.0)
        ):
            raise ValueError("Explicit matching x/y axes must span the full period.")
        plan = HexaAxisPlan(
            x_values=resolved_x,
            y_values=resolved_y,
            z_values=plan.z_values,
            mesh_spacing_mode_resolved="task033_explicit_matching_xy_axes",
            axis_cell_stats={
                **plan.axis_cell_stats,
                "x": _axis_stats(resolved_x),
                "y": _axis_stats(resolved_y),
            },
            material_plane_alignment={
                "all_aligned": True,
                "source": "Task033 certified graded matching x/y axes",
            },
            local_refinement_regions=plan.local_refinement_regions,
        )
    msh = _structured_quad_mesh(
        comm,
        resolved_x,
        resolved_y,
        preserve_input_partition=preserve_input_partition,
    )
    msh.name = f"{cfg.case_name}_{material_kind}_cross_section"
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    epsilon_r = _cross_section_epsilon(msh, cfg, material_kind)
    return CrossSectionMesh(
        mesh=msh,
        x_values=resolved_x,
        y_values=resolved_y,
        axis_plan=plan,
        material_kind=material_kind,
        epsilon_r=epsilon_r,
    )


def build_cross_section_spaces(
    cross_section: CrossSectionMesh,
    *,
    transverse_degree: int,
    longitudinal_degree: int | None = None,
) -> CrossSectionSpaces:
    """Create the mixed ``N1curl x Lagrange`` QEP trial/test space."""

    if transverse_degree < 1:
        raise ValueError("transverse_degree must be at least one.")
    scalar_degree = (
        int(transverse_degree)
        if longitudinal_degree is None
        else int(longitudinal_degree)
    )
    if scalar_degree < 1:
        raise ValueError("longitudinal_degree must be at least one.")

    msh = cross_section.mesh
    transverse_element = element(
        "N1curl", msh.basix_cell(), int(transverse_degree), dtype=default_real_type
    )
    longitudinal_element = element(
        "Lagrange", msh.basix_cell(), scalar_degree, dtype=default_real_type
    )
    mixed_space = fem.functionspace(
        msh, mixed_element([transverse_element, longitudinal_element])
    )
    transverse, transverse_to_mixed = mixed_space.sub(0).collapse()
    longitudinal, longitudinal_to_mixed = mixed_space.sub(1).collapse()
    return CrossSectionSpaces(
        mixed=mixed_space,
        transverse=transverse,
        longitudinal=longitudinal,
        transverse_to_mixed=np.asarray(transverse_to_mixed, dtype=np.int32),
        longitudinal_to_mixed=np.asarray(longitudinal_to_mixed, dtype=np.int32),
        transverse_degree=int(transverse_degree),
        longitudinal_degree=scalar_degree,
    )
