"""Read-only mesh evidence for the V7 anisotropic N0 full-solve target.

This module inspects an already-created MPI1 mesh and its degree-6/degree-4
spaces.  It does not build meshes, create finite-element objects, or assemble
forms.  The checks are specific to the reviewed 100 x 2 x 234 target.
"""

from __future__ import annotations

import hashlib
from itertools import pairwise
from typing import Any

import numpy as np

V7_MESH_EVIDENCE_SCHEMA = "task39extra.v7-anisotropic-mesh-evidence.v1"
V7_EXPECTED_AXIS_COUNTS = (100, 2, 234)
V7_EXPECTED_GLOBAL_CELLS = 46_800
V7_EXPECTED_SI_INDEX = 0.9998851259969171 + 4.325285938225562e-06j


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _array_sha256(values: Any) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _finite_complex(value: Any, name: str) -> complex:
    result = complex(value)
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise ValueError(f"V7 mesh evidence requires finite {name}")
    return result


def _axis_break_indices(axis: np.ndarray, breaks: tuple[float, ...], name: str) -> list[int]:
    indices = []
    for point in breaks:
        matches = np.flatnonzero(np.isclose(axis, point, rtol=0.0, atol=1.0e-10))
        if len(matches) != 1:
            raise ValueError(f"actual {name} axis does not contain one plane at {point:g} nm")
        indices.append(int(matches[0]))
    if indices[0] != 0 or indices[-1] != len(axis) - 1:
        raise ValueError(f"actual {name} axis endpoints differ from the reviewed domain")
    if any(right <= left for left, right in pairwise(indices)):
        raise ValueError(f"actual {name} material planes are not strictly ordered")
    return indices


def _segment_axis_facts(
    axis: np.ndarray,
    breaks: tuple[float, ...],
    expected_counts: tuple[int, ...],
    name: str,
) -> dict[str, Any]:
    positions = _axis_break_indices(axis, breaks, name)
    counts = tuple(right - left for left, right in pairwise(positions))
    if counts != expected_counts:
        raise ValueError(
            f"actual {name} segment counts {counts} differ from {expected_counts}"
        )
    widths = np.diff(axis)
    segment_facts = []
    for index, (left, right, count) in enumerate(
        zip(positions[:-1], positions[1:], counts, strict=True)
    ):
        segment = widths[left:right]
        expected_width = (breaks[index + 1] - breaks[index]) / count
        if not np.allclose(segment, expected_width, rtol=1.0e-12, atol=1.0e-12):
            raise ValueError(f"actual {name} spacing differs inside segment {index}")
        segment_facts.append(
            {
                "start_nm": float(breaks[index]),
                "stop_nm": float(breaks[index + 1]),
                "cell_count": int(count),
                "min_width_nm": float(np.min(segment)),
                "max_width_nm": float(np.max(segment)),
            }
        )
    return {"segment_counts": list(counts), "segments": segment_facts}


def _lookup_axis_cells(
    lows: np.ndarray,
    highs: np.ndarray,
    axis: np.ndarray,
    name: str,
) -> np.ndarray:
    indices = np.searchsorted(axis, lows, side="left")
    if np.any(indices >= len(axis) - 1):
        raise ValueError(f"actual cell lower coordinates escape the {name} axis")
    tolerance = 1.0e-10
    if (
        np.any(np.abs(axis[indices] - lows) > tolerance)
        or np.any(np.abs(axis[indices + 1] - highs) > tolerance)
    ):
        raise ValueError(f"actual cell vertices do not match adjacent {name} axis planes")
    return indices.astype(np.int64, copy=False)


def _periodic_face_pair(
    coordinates: np.ndarray,
    *,
    axis: int,
    lower: float,
    upper: float,
    expected_points: int,
    name: str,
) -> dict[str, Any]:
    tolerance = 1.0e-10
    lower_points = np.unique(
        coordinates[np.isclose(coordinates[:, axis], lower, rtol=0.0, atol=tolerance)][:,
                    [index for index in range(3) if index != axis]],
        axis=0,
    )
    upper_points = np.unique(
        coordinates[np.isclose(coordinates[:, axis], upper, rtol=0.0, atol=tolerance)][:,
                    [index for index in range(3) if index != axis]],
        axis=0,
    )
    if len(lower_points) != expected_points or len(upper_points) != expected_points:
        raise ValueError(f"actual {name} periodic face node counts differ")
    lower_points = lower_points[np.lexsort(tuple(lower_points[:, i] for i in reversed(range(2))))]
    upper_points = upper_points[np.lexsort(tuple(upper_points[:, i] for i in reversed(range(2))))]
    if not np.array_equal(lower_points, upper_points):
        raise ValueError(f"actual {name} periodic face coordinates do not pair exactly")
    return {
        "lower_coordinate_nm": float(lower),
        "upper_coordinate_nm": float(upper),
        "lower_node_count": len(lower_points),
        "upper_node_count": len(upper_points),
        "paired_transverse_coordinates_exact": True,
        "transverse_coordinate_sha256": _array_sha256(lower_points),
    }


def _verify_tagged_face_planes(
    coordinates: np.ndarray,
    facet_indices: np.ndarray,
    facet_values: np.ndarray,
    facet_geometry_dofs: np.ndarray,
    tagged_planes: dict[str, tuple[int, int, float]],
) -> dict[str, bool]:
    """Bind tagged topology facets to coordinate rows through DOLFINx geometry."""

    geometry_dofs = np.asarray(facet_geometry_dofs)
    if (
        geometry_dofs.ndim != 2
        or geometry_dofs.shape[0] != len(facet_indices)
        or geometry_dofs.shape[1] != 4
        or not np.issubdtype(geometry_dofs.dtype, np.integer)
        or (geometry_dofs.size and (np.min(geometry_dofs) < 0
                                    or np.max(geometry_dofs) >= len(coordinates)))
    ):
        raise ValueError("V7 entities_to_geometry returned invalid facet geometry rows")

    verified = {}
    for name, (tag, axis, plane) in tagged_planes.items():
        tagged_rows = np.flatnonzero(facet_values == tag)
        if len(tagged_rows) == 0:
            raise ValueError(f"actual V7 boundary tag {name} is empty")
        for first in range(0, len(tagged_rows), 4096):
            block = tagged_rows[first:first + 4096]
            face_coordinates = coordinates[geometry_dofs[block], axis]
            if not np.allclose(face_coordinates, plane, rtol=0.0, atol=1.0e-10):
                raise ValueError(f"actual V7 {name} tag is not on its coordinate plane")
        verified[name] = True
    return verified


def actual_v7_anisotropic_mesh_evidence(
    levels: Any,
    cfg: Any,
    *,
    entities_to_geometry_fn: Any = None,
    required_space_degrees: tuple[int, ...] = (6, 4),
    axis_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check an already-built V7 tensor mesh and its explicitly built spaces.

    ``axis_contract`` is for a separately named, frozen diagnostic grid.
    Omitting it preserves the original 46800-cell V7 contract.
    """

    if axis_contract is None:
        axis_contract = {
            "name": "V7 original 100x2x234 grid",
            "schema": V7_MESH_EVIDENCE_SCHEMA,
            "global_cells": V7_EXPECTED_GLOBAL_CELLS,
            "axis_counts": V7_EXPECTED_AXIS_COUNTS,
            "segment_counts": {
                "x": (33, 34, 33),
                "y": (2,),
                "z": (17, 200, 17),
            },
            "axes_nm": None,
        }
    required_global_cells = int(axis_contract["global_cells"])
    expected_axis_counts = tuple(int(value) for value in axis_contract["axis_counts"])
    segment_counts = axis_contract["segment_counts"]

    required_space_degrees = tuple(int(degree) for degree in required_space_degrees)
    if required_space_degrees not in ((6, 4), (6,)):
        raise ValueError("V7 mesh evidence supports only the reviewed (p6,p4) or p6-only space set")

    mesh = levels["mesh"]
    mesh_data = levels["mesh_data"]
    topology = mesh.topology
    cell_map = topology.index_map(topology.dim)
    local_cells = int(cell_map.size_local)
    global_cells = int(cell_map.size_global)
    comm_size = int(mesh.comm.size)
    _require(comm_size == 1, "V7 mesh evidence requires MPI1")
    _require(topology.cell_name() == "hexahedron", "V7 target must use hexahedra")
    _require(
        local_cells == global_cells == required_global_cells,
        f"actual global cell count is not {axis_contract['name']}",
    )
    _require(
        tuple(int(value) for value in getattr(cfg, "mesh_axis_cell_counts_requested", ()))
        == expected_axis_counts,
        f"runtime config does not request {axis_contract['name']} axis counts",
    )
    _require(
        cfg.geometry_kind == "rectangular_block_grating"
        and cfg.cell_notch is None
        and not bool(cfg.use_pml)
        and bool(cfg.use_floquet_xy)
        and int(cfg.nedelec_degree) == 6
        and cfg.stage4_boundary_model == "dtn_port"
        and cfg.scattering_background == "layered"
        and cfg.stage4_dtn_order_policy == "auto_propagating"
        and cfg.stage4_dtn_assembly == "auxiliary",
        "runtime geometry/FE/periodic boundary differs from the V7 contract",
    )
    _require(
        bool(getattr(cfg, "full3d_reference_export", False))
        and int(getattr(cfg, "full3d_reference_sample_count_y", 0)) >= 4,
        "V7 requires full-3D reference export with at least four y samples",
    )

    expected_geometry = {
        "x_min": 0.0,
        "x_max": 50.0,
        "y_min": 0.0,
        "y_max": 25.0,
        "domain_z_min": -10.0,
        "domain_z_max": 130.0,
        "interface_z": 0.0,
        "grating_width_x": 17.0,
        "grating_width_y": 25.0,
        "grating_height": 120.0,
    }
    for key, expected in expected_geometry.items():
        actual = float(getattr(cfg, key))
        _require(np.isclose(actual, expected, rtol=0.0, atol=1.0e-12),
                 f"V7 actual geometry {key} differs from {expected:g} nm")
    _require(
        np.isclose(float(cfg.grating_y_min), float(cfg.y_min), rtol=0.0, atol=1.0e-12)
        and np.isclose(float(cfg.grating_y_max), float(cfg.y_max), rtol=0.0, atol=1.0e-12)
        and complex(cfg.ky) == 0j,
        "V7 grating/incident field is not invariant over the full y period",
    )
    _require(
        np.isclose(complex(cfg.n_air), 1.0 + 0.0j, rtol=0.0, atol=1.0e-15)
        and np.isclose(complex(cfg.n_substrate), V7_EXPECTED_SI_INDEX, rtol=0.0, atol=1.0e-15)
        and np.isclose(complex(cfg.n_grating), V7_EXPECTED_SI_INDEX, rtol=0.0, atol=1.0e-15)
        and np.isclose(complex(cfg.mu_r), 1.0 + 0.0j, rtol=0.0, atol=1.0e-15),
        "V7 actual Si/air material identity differs from the reviewed input",
    )

    coordinates = np.asarray(mesh.geometry.x)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    _require(
        coordinates.ndim == 2 and coordinates.shape[1] == 3
        and coordinates.dtype == np.dtype(np.float64)
        and np.isfinite(coordinates).all(),
        "V7 geometry coordinates must be finite float64 three-vectors",
    )
    _require(
        geometry_dofmap.ndim == 2
        and geometry_dofmap.shape[0] >= local_cells
        and geometry_dofmap.shape[1] == 8
        and np.issubdtype(geometry_dofmap.dtype, np.integer),
        "V7 mesh must provide eight Q1 coordinate dofs per cell",
    )
    if geometry_dofmap[:local_cells].size:
        _require(
            int(np.min(geometry_dofmap[:local_cells])) >= 0
            and int(np.max(geometry_dofmap[:local_cells])) < len(coordinates),
            "V7 coordinate dofmap references an unavailable geometry point",
        )

    axes = tuple(np.unique(coordinates[:, axis]) for axis in range(3))
    x_axis, y_axis, z_axis = axes
    axis_counts = tuple(len(axis) - 1 for axis in axes)
    _require(
        axis_counts == expected_axis_counts,
        f"actual axis cell counts {axis_counts} differ from {expected_axis_counts}",
    )
    expected_axes = axis_contract.get("axes_nm")
    if expected_axes is not None:
        for axis_name, actual_axis in zip(("x", "y", "z"), axes, strict=True):
            if not np.array_equal(
                actual_axis, np.asarray(expected_axes[axis_name], dtype=np.float64)
            ):
                raise ValueError(
                    f"actual {axis_name} coordinates differ from the frozen mesh plan"
                )
    if any(np.any(np.diff(axis) <= 0.0) for axis in axes):
        raise ValueError("actual V7 axes must be strictly increasing")
    x_breaks = (float(cfg.x_min), float(cfg.grating_x_min),
                float(cfg.grating_x_max), float(cfg.x_max))
    z_breaks = (float(cfg.domain_z_min), float(cfg.interface_z),
                float(cfg.grating_z_max), float(cfg.domain_z_max))
    x_segments = _segment_axis_facts(x_axis, x_breaks, segment_counts["x"], "x")
    y_segments = _segment_axis_facts(y_axis, (float(cfg.y_min), float(cfg.y_max)),
                                     segment_counts["y"], "y")
    z_segments = _segment_axis_facts(z_axis, z_breaks, segment_counts["z"], "z")

    cell_tags = mesh_data.cell_tags
    tag_indices = np.asarray(cell_tags.indices)
    tag_values = np.asarray(cell_tags.values)
    _require(
        tag_indices.shape == (local_cells,)
        and np.issubdtype(tag_indices.dtype, np.integer)
        and np.array_equal(tag_indices, np.arange(local_cells, dtype=tag_indices.dtype))
        and tag_values.shape == (local_cells,)
        and np.issubdtype(tag_values.dtype, np.integer),
        "V7 actual cell tags must cover every owned cell exactly once",
    )
    material_tags = {
        "air": int(cfg.tags.air),
        "substrate": int(cfg.tags.substrate),
        "grating": int(cfg.tags.grating),
    }
    _require(len(set(material_tags.values())) == 3,
             "V7 air/substrate/grating tag identities must be distinct")
    expected_tag_set = set(material_tags.values())
    _require(set(map(int, np.unique(tag_values))) == expected_tag_set,
             "V7 actual cells contain missing or unauthorized material/PML tags")
    material_values = {
        "air": _finite_complex(cfg.eps_air, "air permittivity"),
        "substrate": _finite_complex(cfg.eps_substrate, "substrate permittivity"),
        "grating": _finite_complex(cfg.eps_grating, "grating permittivity"),
    }
    _require(material_values["substrate"] == material_values["grating"],
             "V7 Si grating and substrate must share the same material value")
    _require(
        material_values["air"] == 1.0 + 0.0j
        and material_values["substrate"] == V7_EXPECTED_SI_INDEX**2
        and material_values["grating"] == V7_EXPECTED_SI_INDEX**2,
        "V7 actual relative permittivities must be air=1 and Si=n*n",
    )

    nx, ny, nz = axis_counts
    tag_grid = np.full((nx, ny, nz), -1, dtype=np.int32)
    seen_cells = np.zeros(required_global_cells, dtype=np.bool_)
    bounds_hash = hashlib.sha256()
    jacobian_min = float("inf")
    jacobian_max = 0.0
    maximum_corner_error = 0.0
    for first in range(0, local_cells, 4096):
        last = min(first + 4096, local_cells)
        vertices = coordinates[geometry_dofmap[first:last]]
        lows = np.min(vertices, axis=1)
        highs = np.max(vertices, axis=1)
        edge_x = vertices[:, 1] - vertices[:, 0]
        edge_y = vertices[:, 2] - vertices[:, 0]
        edge_z = vertices[:, 4] - vertices[:, 0]
        x_width = highs[:, 0] - lows[:, 0]
        y_width = highs[:, 1] - lows[:, 1]
        z_width = highs[:, 2] - lows[:, 2]
        offsets = np.stack(
            [
                np.zeros_like(edge_x), edge_x, edge_y, edge_x + edge_y,
                edge_z, edge_x + edge_z, edge_y + edge_z,
                edge_x + edge_y + edge_z,
            ],
            axis=1,
        )
        expected_vertices = vertices[:, :1, :] + offsets
        corner_error = float(np.max(np.abs(vertices - expected_vertices)))
        maximum_corner_error = max(maximum_corner_error, corner_error)
        if corner_error > 1.0e-10:
            raise ValueError("actual Q1 hex vertex order/geometry is not axis-aligned affine")
        jacobian = np.einsum("ij,ij->i", np.cross(edge_x, edge_y), edge_z)
        expected_jacobian = x_width * y_width * z_width
        if (
            not np.isfinite(jacobian).all()
            or np.any(jacobian <= 0.0)
            or not np.allclose(jacobian, expected_jacobian, rtol=1.0e-12, atol=1.0e-14)
        ):
            raise ValueError("actual V7 hexahedra have nonpositive or inconsistent Jacobians")
        jacobian_min = min(jacobian_min, float(np.min(jacobian)))
        jacobian_max = max(jacobian_max, float(np.max(jacobian)))

        ix = _lookup_axis_cells(lows[:, 0], highs[:, 0], x_axis, "x")
        iy = _lookup_axis_cells(lows[:, 1], highs[:, 1], y_axis, "y")
        iz = _lookup_axis_cells(lows[:, 2], highs[:, 2], z_axis, "z")
        linear = (ix * ny + iy) * nz + iz
        if len(np.unique(linear)) != len(linear) or np.any(seen_cells[linear]):
            raise ValueError("actual V7 mesh has duplicate tensor-product cell locations")
        seen_cells[linear] = True
        tag_grid[ix, iy, iz] = tag_values[first:last].astype(np.int32, copy=False)
        bounds = np.column_stack((lows, highs)).astype("<f8", copy=False)
        bounds_hash.update(memoryview(np.ascontiguousarray(bounds)).cast("B"))

    if not bool(np.all(seen_cells)) or np.any(tag_grid < 0):
        raise ValueError("actual V7 mesh does not cover every tensor-product cell exactly once")
    if not np.array_equal(tag_grid, np.broadcast_to(tag_grid[:, :1, :], tag_grid.shape)):
        raise ValueError("actual cell material tags vary between the two y layers")

    x_mid = 0.5 * (x_axis[:-1] + x_axis[1:])
    z_mid = 0.5 * (z_axis[:-1] + z_axis[1:])
    expected_xz_tags = np.full((nx, nz), material_tags["air"], dtype=np.int32)
    expected_xz_tags[:, z_mid < float(cfg.interface_z)] = material_tags["substrate"]
    in_grating_x = (x_mid >= float(cfg.grating_x_min)) & (
        x_mid <= float(cfg.grating_x_max)
    )
    in_grating_z = (z_mid >= float(cfg.grating_z_min)) & (
        z_mid <= float(cfg.grating_z_max)
    )
    expected_xz_tags[in_grating_x[:, None] & in_grating_z[None, :]] = (
        material_tags["grating"]
    )
    expected_tags = np.broadcast_to(expected_xz_tags[:, None, :], tag_grid.shape)
    if not np.array_equal(tag_grid, expected_tags):
        raise ValueError("actual V7 material tags do not match the full-y Si block geometry")

    tag_counts = {
        name: int(np.count_nonzero(tag_values == tag))
        for name, tag in material_tags.items()
    }
    expected_counts = {
        name: int(np.count_nonzero(expected_xz_tags == tag) * ny)
        for name, tag in material_tags.items()
    }
    if tag_counts != expected_counts:
        raise ValueError("actual V7 material tag counts differ from the geometry-derived counts")

    boundary_facts = mesh_data.facet_tags
    facet_indices = np.asarray(boundary_facts.indices)
    facet_values = np.asarray(boundary_facts.values)
    _require(
        facet_indices.ndim == 1
        and facet_values.shape == facet_indices.shape
        and np.issubdtype(facet_indices.dtype, np.integer)
        and np.issubdtype(facet_values.dtype, np.integer)
        and len(np.unique(facet_indices)) == len(facet_indices),
        "V7 boundary facet tags must be unique integer mesh identities",
    )
    expected_facet_counts = {
        "x_min": (int(cfg.tags.x_min), ny * nz),
        "x_max": (int(cfg.tags.x_max), ny * nz),
        "y_min": (int(cfg.tags.y_min), nx * nz),
        "y_max": (int(cfg.tags.y_max), nx * nz),
        "z_min": (int(cfg.tags.z_min), nx * ny),
        "z_max": (int(cfg.tags.z_max), nx * ny),
    }
    actual_facet_counts = {
        name: int(np.count_nonzero(facet_values == tag))
        for name, (tag, _) in expected_facet_counts.items()
    }
    for name, (tag, expected_count) in expected_facet_counts.items():
        if actual_facet_counts[name] != expected_count:
            raise ValueError(f"actual V7 {name} boundary facet count differs")
        if tag not in set(map(int, np.unique(facet_values))):
            raise ValueError(f"actual V7 {name} boundary tag is missing")
    if set(map(int, np.unique(facet_values))) != {
        tag for tag, _ in expected_facet_counts.values()
    }:
        raise ValueError("actual V7 boundary facets contain an unknown tag")
    tagged_planes = {
        "x_min": (int(cfg.tags.x_min), 0, float(cfg.x_min)),
        "x_max": (int(cfg.tags.x_max), 0, float(cfg.x_max)),
        "y_min": (int(cfg.tags.y_min), 1, float(cfg.y_min)),
        "y_max": (int(cfg.tags.y_max), 1, float(cfg.y_max)),
        "z_min": (int(cfg.tags.z_min), 2, float(cfg.domain_z_min)),
        "z_max": (int(cfg.tags.z_max), 2, float(cfg.domain_z_max)),
    }
    if entities_to_geometry_fn is None:
        from dolfinx import mesh as dmesh

        entities_to_geometry_fn = dmesh.entities_to_geometry
    facet_geometry_dofs = np.asarray(
        entities_to_geometry_fn(mesh, topology.dim - 1, facet_indices, False)
    )
    tagged_face_planes = _verify_tagged_face_planes(
        coordinates, facet_indices, facet_values, facet_geometry_dofs, tagged_planes
    )

    periodic_x = _periodic_face_pair(
        coordinates,
        axis=0,
        lower=float(cfg.x_min),
        upper=float(cfg.x_max),
        expected_points=(ny + 1) * (nz + 1),
        name="x",
    )
    periodic_y = _periodic_face_pair(
        coordinates,
        axis=1,
        lower=float(cfg.y_min),
        upper=float(cfg.y_max),
        expected_points=(nx + 1) * (nz + 1),
        name="y",
    )
    phase_x = _finite_complex(cfg.floquet_phase_x, "x Floquet phase")
    phase_y = _finite_complex(cfg.floquet_phase_y, "y Floquet phase")
    if not np.isclose(abs(phase_x), 1.0, rtol=0.0, atol=1.0e-12):
        raise ValueError("actual V7 x Floquet phase is not unit magnitude")
    if not np.isclose(phase_y, 1.0 + 0.0j, rtol=0.0, atol=1.0e-12):
        raise ValueError("actual V7 y Floquet phase is not unity for ky=0")

    spaces = levels["spaces"]
    rows = {}
    for degree in required_space_degrees:
        if degree not in spaces:
            raise ValueError(f"V7 actual levels do not contain the p{degree} space")
        space = spaces[degree]
        index_map = space.dofmap.index_map
        block_size = int(space.dofmap.index_map_bs)
        _require(block_size > 0, f"V7 p{degree} space has invalid dof block size")
        global_rows = int(index_map.size_global) * block_size
        local_rows = int(index_map.size_local) * block_size
        ghost_rows = int(index_map.num_ghosts) * block_size
        _require(global_rows > 0, f"V7 p{degree} space has no global rows")
        rows[f"p{degree}"] = {
            "global_unconstrained_space_rows": global_rows,
            "local_owned_space_rows": local_rows,
            "local_ghost_space_rows": ghost_rows,
            "block_size": block_size,
        }

    axes_facts = {}
    for name, axis in zip(("x", "y", "z"), axes, strict=True):
        axes_facts[name] = {
            "coordinates_nm": [float(value) for value in axis],
            "coordinate_count": len(axis),
            "cell_count": len(axis) - 1,
            "sha256_raw_float64": _array_sha256(axis),
            "min_width_nm": float(np.min(np.diff(axis))),
            "max_width_nm": float(np.max(np.diff(axis))),
        }

    return {
        "schema": str(axis_contract["schema"]),
        "status": "PASS",
        "actual_global_cell_count": global_cells,
        "actual_local_owned_cell_count": local_cells,
        "actual_axis_cell_counts": list(axis_counts),
        "axis_segments": {"x": x_segments, "y": y_segments, "z": z_segments},
        "axes": axes_facts,
        "raw_geometry_sha256": _array_sha256(coordinates),
        "geometry_dofmap_sha256": _array_sha256(geometry_dofmap),
        "raw_cell_bounds_sha256": bounds_hash.hexdigest(),
        "cell_tag_indices_sha256": _array_sha256(tag_indices),
        "cell_tag_values_sha256": _array_sha256(tag_values),
        "cell_tag_counts": tag_counts,
        "cell_tag_y_invariance": {
            "y_slab_count": int(ny),
            "grating_covers_full_period": True,
            "tags_constant_for_each_xz_column": True,
            "tag_geometry_matches_config": True,
        },
        "material_relative_permittivity_by_name": {
            name: {"real": value.real, "imag": value.imag}
            for name, value in material_values.items()
        },
        "material_index_identity": {
            "substrate_and_grating": {
                "real": float(complex(cfg.n_substrate).real),
                "imag": float(complex(cfg.n_substrate).imag),
            },
            "label": "Si / silicon",
            "tags_by_name": material_tags,
        },
        "jacobian": {
            "all_positive": True,
            "minimum": jacobian_min,
            "maximum": jacobian_max,
            "maximum_hex_corner_mapping_error_nm": maximum_corner_error,
            "sampled_or_all_cells": f"all_{global_cells}_owned_cells",
        },
        "periodic_faces": {
            "x": periodic_x,
            "y": periodic_y,
            "x_boundary_facet_tag_count": actual_facet_counts["x_min"]
            + actual_facet_counts["x_max"],
            "y_boundary_facet_tag_count": actual_facet_counts["y_min"]
            + actual_facet_counts["y_max"],
            "floquet_x_enabled": True,
            "floquet_y_enabled": True,
            "kx": {"real": float(complex(cfg.kx).real), "imag": float(complex(cfg.kx).imag)},
            "ky": {"real": float(complex(cfg.ky).real), "imag": float(complex(cfg.ky).imag)},
            "phase_x": {"real": phase_x.real, "imag": phase_x.imag},
            "phase_y": {"real": phase_y.real, "imag": phase_y.imag},
            "meaning": "actual periodic geometry/tag evidence; not an MPC residual test",
        },
        "boundary_facet_tag_counts": actual_facet_counts,
        "boundary_tags_match_actual_face_planes": tagged_face_planes,
        "actual_unconstrained_space_rows": rows,
        "space_evidence_scope": {
            "required_space_degrees": list(required_space_degrees),
            "not_built_space_degrees": [degree for degree in (6, 4) if degree not in required_space_degrees],
        },
        "full3d_reference_export": True,
        "full3d_reference_sample_count_y": int(cfg.full3d_reference_sample_count_y),
        "full3d_reference_plane_z_nm": [
            float(value) for value in cfg.full3d_reference_plane_z
        ],
        "scope": "actual target mesh/material/spaces only; not a solver or convergence result",
        "mesh_or_fe_data_modified": False,
    }


def actual_v7_candidate_d_mesh_evidence(
    levels: Any,
    cfg: Any,
    *,
    entities_to_geometry_fn: Any = None,
) -> dict[str, Any]:
    """Validate candidate D's actual 47,200-cell x+z changed grid."""

    from src.geometry.v7_d_aniso_n0_p6_axis_plan import (
        D_AXIS_COUNTS,
        D_AXIS_PLAN_ID,
        D_X_SEGMENT_COUNTS,
        D_Y_SEGMENT_COUNTS,
        D_Z_SEGMENT_COUNTS,
        d_axis_plan,
        validate_frozen_d_axes,
    )

    axis_values = validate_frozen_d_axes(
        {
            "mesh_plan_id": cfg.mesh_plan_id,
            "mesh_plan_sha256": cfg.mesh_plan_sha256,
            "mesh_axis_cell_counts": cfg.mesh_axis_cell_counts_requested,
            "mesh_axis_x_values": cfg.mesh_axis_x_values_requested,
            "mesh_axis_y_values": cfg.mesh_axis_y_values_requested,
            "mesh_axis_z_values": cfg.mesh_axis_z_values_requested,
            "mesh_axis_z_profile": cfg.mesh_axis_z_profile,
        }
    )
    plan = d_axis_plan()
    evidence = actual_v7_anisotropic_mesh_evidence(
        levels,
        cfg,
        entities_to_geometry_fn=entities_to_geometry_fn,
        required_space_degrees=(6,),
        axis_contract={
            "name": "V7 candidate D 200x2x118 grid",
            "schema": "task39extra.v7.candidate-d-mesh-evidence.v1",
            "global_cells": int(np.prod(D_AXIS_COUNTS)),
            "axis_counts": D_AXIS_COUNTS,
            "segment_counts": {
                "x": D_X_SEGMENT_COUNTS,
                "y": D_Y_SEGMENT_COUNTS,
                "z": D_Z_SEGMENT_COUNTS,
            },
            "axes_nm": axis_values,
        },
    )
    evidence["diagnostic_scope"] = "CROSS_CHANGED_GRID_DIAGNOSTIC"
    evidence["mesh_plan_id"] = D_AXIS_PLAN_ID
    evidence["mesh_plan_sha256"] = plan["plan_sha256"]
    evidence["mesh_plan_axis_sha256_le_f64"] = plan["axis_sha256_le_f64"]
    return evidence
