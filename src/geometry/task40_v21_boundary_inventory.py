"""Read-only mapping from saved port facets to V20 cell-class identities."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np


def map_boundary_facet_rows(
    facets: Sequence[Mapping[str, Any]],
    *,
    cell_vertices: Mapping[int, np.ndarray],
    cell_permutations: Mapping[int, int],
    cell_material_tags: Mapping[int, int],
    side_boundary_z_nm: Mapping[str, float],
    saved_classes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map saved facets to one adjacent cell and an exact saved class.

    Adjacency, material tags, and facet centers must come from the read-back
    mesh and the project's existing geometry-tagging rules. No carrier support
    or finite-element space is constructed here.
    """

    class_by_key: dict[tuple[int, tuple[str, ...], int], Mapping[str, Any]] = {}
    class_ids: set[str] = set()
    for saved in saved_classes:
        material_tag = int(saved["material_tag"])
        permutation = int(saved["cell_permutation"])
        widths = tuple(float(value) for value in saved["cell_widths_nm"])
        width_hex = tuple(float(value).hex() for value in widths)
        metric = saved["metric_identity"]
        saved_hex = tuple(str(value) for value in metric["cell_widths_float_hex"])
        if width_hex != saved_hex or int(metric["cell_permutation"]) != permutation:
            raise ValueError("saved class metric identity disagrees with its class fields")
        key = (material_tag, saved_hex, permutation)
        class_id = str(saved["class_id"])
        if key in class_by_key or class_id in class_ids:
            raise ValueError("saved class keys and IDs must be unique")
        class_by_key[key] = saved
        class_ids.add(class_id)

    mapped: list[dict[str, Any]] = []
    seen_facets: set[tuple[str, int]] = set()
    facet_counts: Counter[str] = Counter()
    cells_by_side: dict[str, set[int]] = {}
    classes_by_side: dict[str, Counter[str]] = {}
    for facet in facets:
        side = str(facet["side"])
        if side not in {"bottom", "top"}:
            raise ValueError(f"unsupported boundary side: {side!r}")
        facet_id = int(facet["facet_id"])
        facet_key = (side, facet_id)
        if facet_key in seen_facets:
            raise ValueError(f"duplicate saved boundary facet: {facet_key}")
        seen_facets.add(facet_key)

        adjacent = tuple(int(value) for value in facet["adjacent_cell_ids"])
        if len(adjacent) != 1:
            raise ValueError(
                f"{side} facet {facet_id} must have exactly one adjacent cell"
            )
        cell_id = adjacent[0]
        if any(
            cell_id not in mapping
            for mapping in (cell_vertices, cell_permutations, cell_material_tags)
        ):
            raise ValueError(f"missing saved-mesh cell data for cell {cell_id}")

        coordinates = np.asarray(cell_vertices[cell_id], dtype=np.float64)
        if coordinates.shape != (8, 3) or not np.isfinite(coordinates).all():
            raise ValueError(f"cell {cell_id} must have eight finite 3D vertices")
        lower = coordinates.min(axis=0)
        upper = coordinates.max(axis=0)
        widths = tuple(float(value) for value in upper - lower)
        if any(value <= 0.0 for value in widths):
            raise ValueError(f"cell {cell_id} has a nonpositive metric width")
        permutation = int(cell_permutations[cell_id])
        material_tag = int(cell_material_tags[cell_id])

        boundary_z = float(side_boundary_z_nm[side])
        actual_cell_z = float(lower[2] if side == "bottom" else upper[2])
        if actual_cell_z != boundary_z:
            raise ValueError(
                f"{side} facet {facet_id} does not lie on saved boundary z={boundary_z}"
            )
        projected_center = np.asarray(facet["projected_center_nm"], dtype=np.float64)
        actual_center = np.asarray(facet["actual_center_nm"], dtype=np.float64)
        if projected_center.shape != (2,) or actual_center.shape != (3,):
            raise ValueError(f"{side} facet {facet_id} has malformed center coordinates")
        if not np.isfinite(actual_center).all() or not np.array_equal(
            actual_center[:2], projected_center
        ):
            raise ValueError(
                f"{side} facet {facet_id} center differs from its saved pairing center"
            )
        if float(actual_center[2]) != boundary_z:
            raise ValueError(
                f"{side} facet {facet_id} center is not on saved boundary z={boundary_z}"
            )

        key = (material_tag, tuple(value.hex() for value in widths), permutation)
        saved = class_by_key.get(key)
        if saved is None:
            raise ValueError(
                f"no saved class for {side} facet {facet_id}, cell {cell_id}, key={key}"
            )

        class_id = str(saved["class_id"])
        mapped.append(
            {
                "side": side,
                "facet_id": facet_id,
                "cell_id": cell_id,
                "material_tag": material_tag,
                "cell_permutation": permutation,
                "cell_widths_nm": list(widths),
                "cell_widths_float_hex": [value.hex() for value in widths],
                "cell_bounds_nm": [
                    [float(lower[axis]), float(upper[axis])] for axis in range(3)
                ],
                "projected_center_nm": [float(value) for value in projected_center],
                "class_id": class_id,
            }
        )
        facet_counts[side] += 1
        cells_by_side.setdefault(side, set()).add(cell_id)
        classes_by_side.setdefault(side, Counter())[class_id] += 1

    return {
        "facet_mappings": mapped,
        "facet_count_by_side": dict(sorted(facet_counts.items())),
        "unique_cell_count_by_side": {
            side: len(values) for side, values in sorted(cells_by_side.items())
        },
        "class_facet_count_by_side": {
            side: dict(sorted(counts.items()))
            for side, counts in sorted(classes_by_side.items())
        },
    }
