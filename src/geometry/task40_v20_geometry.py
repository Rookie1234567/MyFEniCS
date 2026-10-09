"""Geometry-only inventory for the reviewed original-size Task40 V20 mesh."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np


def _cell_permutation_info(msh: Any) -> np.ndarray:
    create_permutations = getattr(msh.topology, "create_entity_permutations", None)
    if not callable(create_permutations):
        raise RuntimeError("V20 geometry inventory requires topology entity permutations")
    create_permutations()
    return np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)


def _mesh_cell_classes(
    mesh_data: Any, cfg: Any, *, cell_permutations: np.ndarray | None = None
) -> list[dict[str, Any]]:
    msh = mesh_data.mesh
    cells = int(msh.topology.index_map(3).size_local)
    dofmap = np.asarray(msh.geometry.dofmap, dtype=np.int64)
    vertices = np.asarray(msh.geometry.x, dtype=np.float64)[dofmap]
    if cell_permutations is None:
        cell_permutations = _cell_permutation_info(msh)
    if cell_permutations.shape != (cells,):
        raise RuntimeError("V20 geometry inventory has an incomplete cell-permutation array")
    tag_by_cell = {
        int(cell): int(tag)
        for cell, tag in zip(mesh_data.cell_tags.indices, mesh_data.cell_tags.values, strict=True)
    }
    if len(tag_by_cell) != cells or vertices.shape != (cells, 8, 3):
        raise RuntimeError("V20 geometry-only mesh lacks a complete serial cell/tag inventory")

    reference_tag_by_cell = dict(tag_by_cell)
    notch_cell_ids: set[int] = set()
    if cfg.air_void_box_nm is not None:
        x0, x1, y0, y1, z0, z1 = map(float, cfg.air_void_box_nm)
        centers = 0.5 * (vertices.min(axis=1) + vertices.max(axis=1))
        in_box = (
            (centers[:, 0] >= x0)
            & (centers[:, 0] <= x1)
            & (centers[:, 1] >= y0)
            & (centers[:, 1] <= y1)
            & (centers[:, 2] >= z0)
            & (centers[:, 2] <= z1)
        )
        notch_cell_ids = {
            int(cell)
            for cell in np.flatnonzero(in_box)
            if tag_by_cell[int(cell)] == int(cfg.tags.air)
        }
        expected_void_count = int(
            (mesh_data.rectangular_air_void_audit or {}).get(
                "owned_void_box_cell_count", len(notch_cell_ids)
            )
        )
        if len(notch_cell_ids) != expected_void_count:
            raise RuntimeError(
                "V20 target/reference material variants disagree with the audited air-void cell count"
            )
        for cell in notch_cell_ids:
            reference_tag_by_cell[cell] = int(cfg.tags.grating)

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for cell in range(cells):
        coords = vertices[cell]
        lo = coords.min(axis=0)
        hi = coords.max(axis=0)
        widths = tuple(float(value) for value in hi - lo)
        if not np.isfinite(widths).all() or any(value <= 0.0 for value in widths):
            raise RuntimeError(f"V20 cell {cell} has an invalid exact metric")
        # Exact float tuples intentionally preserve distinct geometry metrics.
        permutation = int(cell_permutations[cell])
        target_key = (tag_by_cell[cell], widths, permutation)
        reference_key = (reference_tag_by_cell[cell], widths, permutation)
        for model, key in (("target", target_key), ("filled_reference", reference_key)):
            group = groups.get(key)
            if group is None:
                group = {
                    "material_tag": int(key[0]),
                    "cell_widths_nm": list(widths),
                    "metric_identity": {
                        "cell_widths_float_hex": [float(value).hex() for value in widths],
                        "cell_permutation": permutation,
                    },
                    "cell_permutation": permutation,
                    "target_cell_count": 0,
                    "filled_reference_cell_count": 0,
                    "target_representative_cell": None,
                    "target_representative_cell_coordinates_nm": None,
                    "target_representative_cell_permutation": None,
                    "filled_reference_representative_cell": None,
                    "representative_bounds_nm": [
                        [float(lo[axis]), float(hi[axis])] for axis in range(3)
                    ],
                }
                groups[key] = group
            count_key = (
                "target_cell_count" if model == "target" else "filled_reference_cell_count"
            )
            representative_key = (
                "target_representative_cell"
                if model == "target"
                else "filled_reference_representative_cell"
            )
            group[count_key] += 1
            if model == "target" and group["target_representative_cell"] is None:
                group["target_representative_cell"] = int(cell)
                group["target_representative_cell_coordinates_nm"] = vertices[cell].tolist()
                group["target_representative_cell_permutation"] = permutation
            elif group[representative_key] is None:
                group[representative_key] = int(cell)

    tags = {
        int(cfg.tags.air): "air",
        int(cfg.tags.substrate): "substrate",
        int(cfg.tags.grating): "grating",
    }
    result = list(groups.values())
    for index, item in enumerate(result):
        item["class_id"] = f"c{index:02d}"
        item["material"] = tags.get(item["material_tag"], "other")
        item["representative_cell"] = (
            item["target_representative_cell"]
            if item["target_representative_cell"] is not None
            else item["filled_reference_representative_cell"]
        )
        item["cell_count"] = max(
            int(item["target_cell_count"]),
            int(item["filled_reference_cell_count"]),
        )
        item["models_present"] = [
            model
            for model, count_key in (
                ("target", "target_cell_count"),
                ("filled_reference", "filled_reference_cell_count"),
            )
            if int(item[count_key]) > 0
        ]
    return result


def _facet_pair_inventory(
    mesh_data: Any, cfg: Any, *, cell_permutations: np.ndarray | None = None
) -> dict[str, Any]:
    from dolfinx import mesh

    msh = mesh_data.mesh
    if cell_permutations is None:
        cell_permutations = _cell_permutation_info(msh)
    fdim = msh.topology.dim - 1
    facets = np.asarray(mesh_data.facet_tags.indices, dtype=np.int32)
    values = np.asarray(mesh_data.facet_tags.values, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, fdim, facets)
    records_by_tag: dict[int, list[tuple[int, np.ndarray]]] = {}
    for facet, tag, center in zip(facets, values, centers, strict=True):
        tag_value = int(tag)
        records_by_tag.setdefault(tag_value, []).append((int(facet), center))

    def surface_key(
        tags: tuple[int, int], transverse: tuple[int, int]
    ) -> tuple[bool, int, list[dict[str, Any]]]:
        sides: list[dict[tuple[float, float], list[int]]] = []
        for tag in tags:
            projected: dict[tuple[float, float], list[int]] = {}
            for facet, center in records_by_tag.get(tag, ()):
                key = tuple(float(center[axis]) for axis in transverse)
                projected.setdefault(key, []).append(int(facet))
            for facet_ids in projected.values():
                facet_ids.sort()
            sides.append(projected)
        left, right = sides
        pairing_pass = Counter({key: len(ids) for key, ids in left.items()}) == Counter(
            {key: len(ids) for key, ids in right.items()}
        )
        pairs = []
        if pairing_pass:
            for key in sorted(left):
                for left_id, right_id in zip(left[key], right[key], strict=True):
                    pairs.append(
                        {
                            "projected_center_nm": [float(value) for value in key],
                            "minus_or_bottom_facet_id": int(left_id),
                            "plus_or_top_facet_id": int(right_id),
                        }
                    )
        return pairing_pass, sum(len(ids) for ids in left.values()), pairs

    x_pass, x_count, x_pairs = surface_key(
        (int(cfg.tags.x_min), int(cfg.tags.x_max)), (1, 2)
    )
    y_pass, y_count, y_pairs = surface_key(
        (int(cfg.tags.y_min), int(cfg.tags.y_max)), (0, 2)
    )
    z_pass, z_count, z_pairs = surface_key(
        (int(cfg.tags.z_min), int(cfg.tags.z_max)), (0, 1)
    )
    facet_counts = Counter(map(int, values))

    msh.topology.create_connectivity(fdim, msh.topology.dim)
    facet_to_cell = msh.topology.connectivity(fdim, msh.topology.dim)
    cell_tag_by_id = {
        int(cell): int(tag)
        for cell, tag in zip(mesh_data.cell_tags.indices, mesh_data.cell_tags.values, strict=True)
    }
    geometry_dofmap = np.asarray(msh.geometry.dofmap, dtype=np.int64)
    geometry = np.asarray(msh.geometry.x, dtype=np.float64)
    axes = tuple(
        np.unique(geometry[:, axis]) for axis in range(3)
    )

    def axis_interval(axis: int, lower: float) -> int:
        matches = np.flatnonzero(axes[axis][:-1] == lower)
        if len(matches) != 1:
            raise RuntimeError("boundary face cell lower coordinate is absent from exact mesh axes")
        return int(matches[0])

    boundary_cells: list[dict[str, Any]] = []
    for side, facet_tag, transverse in (
        ("bottom", int(cfg.tags.z_min), (0, 1)),
        ("top", int(cfg.tags.z_max), (0, 1)),
    ):
        tagged = records_by_tag.get(facet_tag, ())
        if not tagged:
            raise RuntimeError(f"V20 {side} boundary has no tagged facets")
        facet, center = min(
            tagged,
            key=lambda row: (
                float(row[1][transverse[0]]),
                float(row[1][transverse[1]]),
                int(row[0]),
            ),
        )
        adjacent = np.asarray(facet_to_cell.links(facet), dtype=np.int32)
        if adjacent.shape != (1,):
            raise RuntimeError(f"V20 {side} boundary facet does not have exactly one adjacent cell")
        cell = int(adjacent[0])
        coords = geometry[geometry_dofmap[cell]]
        lo, hi = coords.min(axis=0), coords.max(axis=0)
        boundary_cells.append(
            {
                "side": side,
                "facet_id": int(facet),
                "cell_id": cell,
                "material_tag": cell_tag_by_id[cell],
                "cell_permutation": int(cell_permutations[cell]),
                "bounds_nm": [[float(value) for value in (lo[axis], hi[axis])] for axis in range(3)],
                "face_i": axis_interval(0, float(lo[0])),
                "face_j": axis_interval(1, float(lo[1])),
                "facet_center_nm": [float(value) for value in center],
            }
        )

    return {
        "x_periodic_face_pair_count_per_side": x_count,
        "y_periodic_face_pair_count_per_side": y_count,
        "z_port_face_count_per_side": z_count,
        "x_periodic_coordinate_pairing_pass": x_pass,
        "y_periodic_coordinate_pairing_pass": y_pass,
        "top_bottom_port_coordinate_pairing_pass": z_pass,
        "facet_id_pairings": {
            "x_periodic": x_pairs,
            "y_periodic": y_pairs,
            "top_bottom_port": z_pairs,
        },
        "facet_tag_counts": {str(key): int(value) for key, value in facet_counts.items()},
        "boundary_face_cells": boundary_cells,
        "pairing_scope": (
            "actual facet ID/tag records paired by exact projected center coordinates; "
            "duplicate coordinates retain one row per facet ID; boundary cells selected "
            "by tagged-facet adjacency, not cell numbering"
        ),
    }


def build_v20_geometry_inventory(
    resolved: Mapping[str, Any], output_directory: str | Path
) -> tuple[dict[str, Any], Any, Any, list[dict[str, Any]]]:
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.io.input_validation import simulation_config_3d_from_normalized

    output_directory = Path(output_directory)
    cfg = simulation_config_3d_from_normalized(resolved)
    started = perf_counter()
    mesh_data = build_airbox_mesh_3d(cfg, output_directory / "target_geometry")
    msh = mesh_data.mesh
    axis_coordinates = [
        np.unique(np.asarray(msh.geometry.x[:, axis], dtype=np.float64))
        for axis in range(3)
    ]
    cells = int(msh.topology.index_map(3).size_local)
    tags = Counter(map(int, mesh_data.cell_tags.values))
    cell_permutations = _cell_permutation_info(msh)
    permutations = Counter(map(int, cell_permutations))
    classes = _mesh_cell_classes(
        mesh_data, cfg, cell_permutations=cell_permutations
    )
    pairing = _facet_pair_inventory(
        mesh_data, cfg, cell_permutations=cell_permutations
    )
    expected_axes = tuple(
        int(value) for value in resolved["discretization"]["mesh_axis_cell_counts"]
    )
    actual_axes = tuple(len(values) - 1 for values in axis_coordinates)
    if actual_axes != expected_axes or cells != int(np.prod(expected_axes)):
        raise RuntimeError(f"V20 actual geometry axes/cells differ: {actual_axes}/{cells}")
    if not all(
        pairing[key]
        for key in (
            "x_periodic_coordinate_pairing_pass",
            "y_periodic_coordinate_pairing_pass",
            "top_bottom_port_coordinate_pairing_pass",
        )
    ):
        raise RuntimeError("V20 geometric opposite-face pairing failed")
    facts = {
        "schema": "task40extra.review_v20_original_geometry_inventory.v1",
        "status": "PASS",
        "mesh_id": "TARGET_ORIGINAL_NY8",
        "mesh_cell_type": mesh_data.mesh_cell_type_resolved,
        "actual_axes": list(actual_axes),
        "actual_cell_count": cells,
        "vertex_axis_coordinate_counts": [len(values) for values in axis_coordinates],
        "axis_coordinate_sha256": [
            hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
            for values in axis_coordinates
        ],
        "material_tag_counts": {str(key): int(value) for key, value in tags.items()},
        "material_tag_names": {
            str(cfg.tags.air): "air",
            str(cfg.tags.substrate): "substrate",
            str(cfg.tags.grating): "grating",
        },
        "cell_permutation_histogram": {str(key): int(value) for key, value in permutations.items()},
        "material_plane_alignment": mesh_data.material_plane_alignment,
        "rectangular_air_void_audit": mesh_data.rectangular_air_void_audit,
        "periodic_face_inventory": pairing,
        "cell_class_count": len(classes),
        "target_cell_class_count": sum(
            int(item["target_cell_count"]) > 0 for item in classes
        ),
        "filled_reference_cell_class_count": sum(
            int(item["filled_reference_cell_count"]) > 0 for item in classes
        ),
        "target_cell_class_ids": [
            item["class_id"] for item in classes if int(item["target_cell_count"]) > 0
        ],
        "filled_reference_cell_class_ids": [
            item["class_id"]
            for item in classes
            if int(item["filled_reference_cell_count"]) > 0
        ],
        "shared_cell_class_ids": [
            item["class_id"]
            for item in classes
            if int(item["target_cell_count"]) > 0
            and int(item["filled_reference_cell_count"]) > 0
        ],
        "target_only_cell_class_ids": [
            item["class_id"]
            for item in classes
            if int(item["target_cell_count"]) > 0
            and int(item["filled_reference_cell_count"]) == 0
        ],
        "filled_reference_only_cell_class_ids": [
            item["class_id"]
            for item in classes
            if int(item["target_cell_count"]) == 0
            and int(item["filled_reference_cell_count"]) > 0
        ],
        "model_class_identity_scope": (
            "one target-tagged geometry is reused; the filled-notch reference changes "
            "only audited air-void cells from air to grating, then groups by exact material, "
            "cell widths, and prepared cell permutation"
        ),
        "maximum_exact_metric_class_cell_count": max(
            (
                max(
                    int(item["target_cell_count"]),
                    int(item["filled_reference_cell_count"]),
                )
                for item in classes
            ),
            default=0,
        ),
        "cell_classes": classes,
        "global_p6_space_created": False,
        "global_mpc_created": False,
        "global_C_D_created": False,
        "q_csr_created": False,
        "factor_created": False,
        "elapsed_seconds": perf_counter() - started,
        "artifact_directory": str(output_directory / "target_geometry"),
    }
    return facts, mesh_data, cfg, classes


__all__ = ["build_v20_geometry_inventory"]
