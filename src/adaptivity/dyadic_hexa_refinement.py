"""Geometry authority for balanced local refinement of affine hexahedra.

Task035d needs a real local-h topology before any numerical kernel is allowed
to claim local refinement.  DOLFINx does not currently provide the required
hexahedral refinement path, so this module owns a small, deterministic dyadic
forest:

* every marked hexahedron is split isotropically into eight affine children;
* neighbouring leaves are closed to a strong 2:1 level balance;
* x/y periodic boundary refinements are mirrored;
* material interfaces can be kept free of hanging faces; and
* coarse faces adjacent to four fine faces are catalogued explicitly.

The forest is geometry-only.  It deliberately grants no PDE or accuracy
credit.  H(curl) trace constraints for the catalogued hanging faces live in
``hcurl_hanging_trace.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


Box = tuple[float, float, float, float, float, float]
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
_ROUND_DIGITS = 12


def _round(value: float) -> float:
    return round(float(value), _ROUND_DIGITS)


def _box(values: Sequence[float]) -> Box:
    if len(values) != 6:
        raise ValueError("a hexahedron box requires six coordinates")
    result = tuple(_round(value) for value in values)
    if any(result[axis] >= result[axis + 3] for axis in range(3)):
        raise ValueError(f"hexahedron box has non-positive extent: {result}")
    return result  # type: ignore[return-value]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _touches(left: float, right: float, tolerance: float) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def _positive_overlap(
    left: tuple[float, float],
    right: tuple[float, float],
    tolerance: float,
) -> tuple[float, float] | None:
    lower = max(left[0], right[0])
    upper = min(left[1], right[1])
    if upper - lower <= tolerance:
        return None
    return _round(lower), _round(upper)


@dataclass(frozen=True, order=True)
class DyadicHexKey:
    """Stable identity of one dyadic descendant of a root hexahedron."""

    root: int
    level: int
    i: int
    j: int
    k: int

    def __post_init__(self) -> None:
        root = int(self.root)
        level = int(self.level)
        indices = (int(self.i), int(self.j), int(self.k))
        if root < 0 or level < 0:
            raise ValueError("dyadic root and level must be non-negative")
        limit = 1 << level
        if any(index < 0 or index >= limit for index in indices):
            raise ValueError(
                f"dyadic child index is outside level {level}: {indices}"
            )
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "i", indices[0])
        object.__setattr__(self, "j", indices[1])
        object.__setattr__(self, "k", indices[2])

    def children(self) -> tuple[DyadicHexKey, ...]:
        """Return the eight isotropic children in canonical order."""

        return tuple(
            DyadicHexKey(
                self.root,
                self.level + 1,
                2 * self.i + di,
                2 * self.j + dj,
                2 * self.k + dk,
            )
            for dk in (0, 1)
            for dj in (0, 1)
            for di in (0, 1)
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "root": self.root,
            "level": self.level,
            "i": self.i,
            "j": self.j,
            "k": self.k,
        }


@dataclass(frozen=True)
class DyadicHexCell:
    """One leaf hexahedron with inherited material identity."""

    key: DyadicHexKey
    box: Box
    material_tag: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.to_dict(),
            "box": list(self.box),
            "material_tag": int(self.material_tag),
        }


@dataclass(frozen=True)
class FaceAdjacency:
    """Positive-area contact between two leaf faces."""

    left: DyadicHexKey
    right: DyadicHexKey
    axis: int
    left_side: int
    right_side: int
    overlap_u: tuple[float, float]
    overlap_v: tuple[float, float]


@dataclass(frozen=True)
class HangingFacePatch:
    """One coarse face covered by four one-level-finer faces."""

    coarse: DyadicHexKey
    axis: int
    side: int
    fine: tuple[DyadicHexKey, ...]
    child_offsets: tuple[tuple[int, int], ...]
    material_tag: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "coarse": self.coarse.to_dict(),
            "axis": self.axis,
            "side": self.side,
            "fine": [key.to_dict() for key in self.fine],
            "child_offsets": [list(offset) for offset in self.child_offsets],
            "material_tag": self.material_tag,
        }


@dataclass(frozen=True)
class BalancedDyadicHexForest:
    """Immutable, hash-bound local-hexa refinement authority."""

    root_boxes: tuple[Box, ...]
    root_material_tags: tuple[int, ...]
    leaves: tuple[DyadicHexCell, ...]
    periodic_axes: tuple[str, ...]
    protect_material_interfaces: bool
    domain_bounds: Box
    hanging_faces: tuple[HangingFacePatch, ...]
    audit: Mapping[str, Any]

    @property
    def leaf_by_key(self) -> Mapping[DyadicHexKey, DyadicHexCell]:
        return MappingProxyType({cell.key: cell for cell in self.leaves})


def _cell_box(root_box: Box, key: DyadicHexKey) -> Box:
    denominator = float(1 << key.level)
    indices = (key.i, key.j, key.k)
    lower = tuple(
        root_box[axis]
        + (root_box[axis + 3] - root_box[axis])
        * indices[axis]
        / denominator
        for axis in range(3)
    )
    upper = tuple(
        root_box[axis]
        + (root_box[axis + 3] - root_box[axis])
        * (indices[axis] + 1)
        / denominator
        for axis in range(3)
    )
    return _box((*lower, *upper))


def _domain_bounds(root_boxes: Sequence[Box]) -> Box:
    return _box(
        (
            *(min(box[axis] for box in root_boxes) for axis in range(3)),
            *(max(box[axis + 3] for box in root_boxes) for axis in range(3)),
        )
    )


def _geometry_tolerance(bounds: Box) -> float:
    extent = max(
        bounds[axis + 3] - bounds[axis] for axis in range(3)
    )
    return max(float(extent), 1.0) * 1.0e-11


def _face_adjacencies(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    *,
    tolerance: float,
) -> tuple[FaceAdjacency, ...]:
    cells = tuple(leaves.values())
    result: list[FaceAdjacency] = []
    for left_index, left in enumerate(cells):
        for right in cells[left_index + 1 :]:
            for axis in range(3):
                left_side: int | None = None
                right_side: int | None = None
                if _touches(
                    left.box[axis + 3],
                    right.box[axis],
                    tolerance,
                ):
                    left_side, right_side = 1, 0
                elif _touches(
                    right.box[axis + 3],
                    left.box[axis],
                    tolerance,
                ):
                    left_side, right_side = 0, 1
                if left_side is None or right_side is None:
                    continue
                tangential = tuple(
                    candidate for candidate in range(3) if candidate != axis
                )
                overlap_u = _positive_overlap(
                    (
                        left.box[tangential[0]],
                        left.box[tangential[0] + 3],
                    ),
                    (
                        right.box[tangential[0]],
                        right.box[tangential[0] + 3],
                    ),
                    tolerance,
                )
                overlap_v = _positive_overlap(
                    (
                        left.box[tangential[1]],
                        left.box[tangential[1] + 3],
                    ),
                    (
                        right.box[tangential[1]],
                        right.box[tangential[1] + 3],
                    ),
                    tolerance,
                )
                if overlap_u is not None and overlap_v is not None:
                    result.append(
                        FaceAdjacency(
                            left=left.key,
                            right=right.key,
                            axis=axis,
                            left_side=left_side,
                            right_side=right_side,
                            overlap_u=overlap_u,
                            overlap_v=overlap_v,
                        )
                    )
                    break
    return tuple(result)


def _touching_pairs(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    *,
    tolerance: float,
) -> tuple[tuple[DyadicHexKey, DyadicHexKey], ...]:
    """Return every face/edge/vertex touching pair.

    Strong octree balance is enforced on all closures, not only on faces.
    This prevents a level-two child from meeting a level-zero leaf at a
    coarse edge or corner and creating a chained hanging constraint in a
    later trace implementation.
    """

    cells = tuple(leaves.values())
    result: list[tuple[DyadicHexKey, DyadicHexKey]] = []
    for left_index, left in enumerate(cells):
        for right in cells[left_index + 1 :]:
            separated = any(
                left.box[axis + 3] < right.box[axis] - tolerance
                or right.box[axis + 3] < left.box[axis] - tolerance
                for axis in range(3)
            )
            if separated:
                continue
            positive_axes = sum(
                _positive_overlap(
                    (left.box[axis], left.box[axis + 3]),
                    (right.box[axis], right.box[axis + 3]),
                    tolerance,
                )
                is not None
                for axis in range(3)
            )
            if positive_axes == 3:
                raise RuntimeError("dyadic leaf interiors overlap")
            result.append((left.key, right.key))
    return tuple(result)


def _boundary_patch_rows(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    *,
    bounds: Box,
    axis: int,
    side: int,
    tolerance: float,
) -> tuple[tuple[float, float, float, float, int], ...]:
    plane = bounds[axis + 3] if side else bounds[axis]
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    rows = []
    for cell in leaves.values():
        coordinate = cell.box[axis + 3] if side else cell.box[axis]
        if not _touches(coordinate, plane, tolerance):
            continue
        rows.append(
            (
                cell.box[tangential[0]],
                cell.box[tangential[0] + 3],
                cell.box[tangential[1]],
                cell.box[tangential[1] + 3],
                cell.key.level,
            )
        )
    return tuple(sorted(rows))


def _periodic_boundary_audit(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    *,
    bounds: Box,
    periodic_axes: tuple[str, ...],
    tolerance: float,
) -> tuple[dict[str, Any], list[DyadicHexKey]]:
    rows: dict[str, Any] = {}
    split: set[DyadicHexKey] = set()
    for axis_name in periodic_axes:
        axis = _AXIS_INDEX[axis_name]
        lower = _boundary_patch_rows(
            leaves,
            bounds=bounds,
            axis=axis,
            side=0,
            tolerance=tolerance,
        )
        upper = _boundary_patch_rows(
            leaves,
            bounds=bounds,
            axis=axis,
            side=1,
            tolerance=tolerance,
        )
        rows[axis_name] = {
            "lower_patch_count": len(lower),
            "upper_patch_count": len(upper),
            "lower_sha256": _json_sha256(lower),
            "upper_sha256": _json_sha256(upper),
            "matching": lower == upper,
        }
        if lower == upper:
            continue
        lower_cells = [
            cell
            for cell in leaves.values()
            if _touches(cell.box[axis], bounds[axis], tolerance)
        ]
        upper_cells = [
            cell
            for cell in leaves.values()
            if _touches(
                cell.box[axis + 3],
                bounds[axis + 3],
                tolerance,
            )
        ]
        tangential = tuple(
            candidate for candidate in range(3) if candidate != axis
        )
        for lower_cell in lower_cells:
            for upper_cell in upper_cells:
                overlap_u = _positive_overlap(
                    (
                        lower_cell.box[tangential[0]],
                        lower_cell.box[tangential[0] + 3],
                    ),
                    (
                        upper_cell.box[tangential[0]],
                        upper_cell.box[tangential[0] + 3],
                    ),
                    tolerance,
                )
                overlap_v = _positive_overlap(
                    (
                        lower_cell.box[tangential[1]],
                        lower_cell.box[tangential[1] + 3],
                    ),
                    (
                        upper_cell.box[tangential[1]],
                        upper_cell.box[tangential[1] + 3],
                    ),
                    tolerance,
                )
                if overlap_u is None or overlap_v is None:
                    continue
                if lower_cell.key.level < upper_cell.key.level:
                    split.add(lower_cell.key)
                elif upper_cell.key.level < lower_cell.key.level:
                    split.add(upper_cell.key)
    return rows, sorted(split)


def _split(
    leaves: dict[DyadicHexKey, DyadicHexCell],
    targets: Iterable[DyadicHexKey],
    *,
    root_boxes: tuple[Box, ...],
    maximum_level: int,
) -> int:
    count = 0
    for key in sorted(set(targets)):
        cell = leaves.get(key)
        if cell is None:
            raise ValueError(f"marked dyadic leaf does not exist: {key}")
        if key.level >= maximum_level:
            raise ValueError(
                f"marked leaf {key} reaches maximum level {maximum_level}"
            )
        del leaves[key]
        for child_key in key.children():
            leaves[child_key] = DyadicHexCell(
                key=child_key,
                box=_cell_box(root_boxes[key.root], child_key),
                material_tag=cell.material_tag,
            )
        count += 1
    return count


def _pre_split_closure(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    targets: set[DyadicHexKey],
    *,
    bounds: Box,
    periodic_axes: tuple[str, ...],
    protect_material_interfaces: bool,
    tolerance: float,
) -> tuple[set[DyadicHexKey], int, int]:
    result = set(targets)
    periodic_added: set[DyadicHexKey] = set()
    material_added: set[DyadicHexKey] = set()
    changed = True
    while changed:
        changed = False
        snapshot = tuple(result)
        for key in snapshot:
            cell = leaves[key]
            for axis_name in periodic_axes:
                axis = _AXIS_INDEX[axis_name]
                side: int | None = None
                if _touches(cell.box[axis], bounds[axis], tolerance):
                    side = 0
                elif _touches(
                    cell.box[axis + 3],
                    bounds[axis + 3],
                    tolerance,
                ):
                    side = 1
                if side is None:
                    continue
                tangential = tuple(
                    candidate
                    for candidate in range(3)
                    if candidate != axis
                )
                opposite_plane = (
                    bounds[axis + 3] if side == 0 else bounds[axis]
                )
                for partner in leaves.values():
                    partner_plane = (
                        partner.box[axis + 3]
                        if side == 0
                        else partner.box[axis]
                    )
                    if not _touches(
                        partner_plane,
                        opposite_plane,
                        tolerance,
                    ):
                        continue
                    overlap_u = _positive_overlap(
                        (
                            cell.box[tangential[0]],
                            cell.box[tangential[0] + 3],
                        ),
                        (
                            partner.box[tangential[0]],
                            partner.box[tangential[0] + 3],
                        ),
                        tolerance,
                    )
                    overlap_v = _positive_overlap(
                        (
                            cell.box[tangential[1]],
                            cell.box[tangential[1] + 3],
                        ),
                        (
                            partner.box[tangential[1]],
                            partner.box[tangential[1] + 3],
                        ),
                        tolerance,
                    )
                    if (
                        overlap_u is not None
                        and overlap_v is not None
                        and partner.key.level <= key.level
                        and partner.key not in result
                    ):
                        result.add(partner.key)
                        periodic_added.add(partner.key)
                        changed = True
        if protect_material_interfaces:
            for adjacency in _face_adjacencies(
                leaves,
                tolerance=tolerance,
            ):
                left = leaves[adjacency.left]
                right = leaves[adjacency.right]
                if left.material_tag == right.material_tag:
                    continue
                if (
                    left.key in result
                    and right.key.level <= left.key.level
                    and right.key not in result
                ):
                    result.add(right.key)
                    material_added.add(right.key)
                    changed = True
                if (
                    right.key in result
                    and left.key.level <= right.key.level
                    and left.key not in result
                ):
                    result.add(left.key)
                    material_added.add(left.key)
                    changed = True
    return result, len(periodic_added), len(material_added)


def _hanging_face_catalog(
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    *,
    tolerance: float,
) -> tuple[HangingFacePatch, ...]:
    groups: dict[
        tuple[DyadicHexKey, int, int],
        list[tuple[DyadicHexKey, tuple[int, int]]],
    ] = {}
    for adjacency in _face_adjacencies(leaves, tolerance=tolerance):
        left = leaves[adjacency.left]
        right = leaves[adjacency.right]
        if left.key.level == right.key.level:
            continue
        if abs(left.key.level - right.key.level) != 1:
            raise RuntimeError("hanging face violates strong 2:1 balance")
        if left.key.level < right.key.level:
            coarse, fine = left, right
            side = adjacency.left_side
        else:
            coarse, fine = right, left
            side = adjacency.right_side
        tangential = tuple(
            candidate
            for candidate in range(3)
            if candidate != adjacency.axis
        )
        fine_box = fine.box
        offsets: list[int] = []
        for axis in tangential:
            span = coarse.box[axis + 3] - coarse.box[axis]
            relative = (
                fine_box[axis] - coarse.box[axis]
            ) / span
            offset = int(round(2.0 * relative))
            if offset not in {0, 1}:
                raise RuntimeError(
                    "fine face is not a dyadic child of its coarse face"
                )
            expected_span = 0.5 * span
            if not math.isclose(
                fine_box[axis + 3] - fine_box[axis],
                expected_span,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise RuntimeError(
                    "fine hanging face does not have half tangential extent"
                )
            offsets.append(offset)
        groups.setdefault(
            (coarse.key, adjacency.axis, side),
            [],
        ).append((fine.key, (offsets[0], offsets[1])))
    result: list[HangingFacePatch] = []
    for (coarse_key, axis, side), values in sorted(groups.items()):
        ordered = sorted(values, key=lambda row: row[1])
        offsets = tuple(offset for _key, offset in ordered)
        if offsets != ((0, 0), (0, 1), (1, 0), (1, 1)):
            raise RuntimeError(
                "one coarse hanging face is not covered by four children: "
                f"{coarse_key}, offsets={offsets}"
            )
        fine_keys = tuple(key for key, _offset in ordered)
        coarse = leaves[coarse_key]
        result.append(
            HangingFacePatch(
                coarse=coarse_key,
                axis=axis,
                side=side,
                fine=fine_keys,
                child_offsets=offsets,
                material_tag=coarse.material_tag,
            )
        )
    return tuple(result)


def _forest(
    *,
    root_boxes: tuple[Box, ...],
    root_material_tags: tuple[int, ...],
    leaves: Mapping[DyadicHexKey, DyadicHexCell],
    periodic_axes: tuple[str, ...],
    protect_material_interfaces: bool,
    closure_counts: Mapping[str, int],
) -> BalancedDyadicHexForest:
    bounds = _domain_bounds(root_boxes)
    tolerance = _geometry_tolerance(bounds)
    adjacencies = _face_adjacencies(leaves, tolerance=tolerance)
    touching = _touching_pairs(leaves, tolerance=tolerance)
    maximum_jump = max(
        (
            abs(
                leaves[left].key.level
                - leaves[right].key.level
            )
            for left, right in touching
        ),
        default=0,
    )
    if maximum_jump > 1:
        raise RuntimeError("dyadic forest is not strongly 2:1 balanced")
    hanging = _hanging_face_catalog(leaves, tolerance=tolerance)
    material_hanging = [
        patch
        for patch in hanging
        if any(
            leaves[key].material_tag != patch.material_tag
            for key in patch.fine
        )
    ]
    if protect_material_interfaces and material_hanging:
        raise RuntimeError("material interface contains a hanging face")
    periodic, periodic_split = _periodic_boundary_audit(
        leaves,
        bounds=bounds,
        periodic_axes=periodic_axes,
        tolerance=tolerance,
    )
    if periodic_split or any(
        not row["matching"] for row in periodic.values()
    ):
        raise RuntimeError("periodic boundary refinement patterns do not match")
    ordered_leaves = tuple(
        sorted(leaves.values(), key=lambda cell: cell.key)
    )
    leaf_payload = [cell.to_dict() for cell in ordered_leaves]
    audit = {
        "schema_version": "task035d.dyadic-hexa-forest.v1",
        "status": "balanced_periodic_dyadic_hexa_forest_pass",
        "pass": True,
        "root_cell_count": len(root_boxes),
        "leaf_cell_count": len(ordered_leaves),
        "refined_root_count": len(
            {cell.key.root for cell in ordered_leaves if cell.key.level > 0}
        ),
        "leaf_level_counts": {
            str(level): sum(
                cell.key.level == level for cell in ordered_leaves
            )
            for level in sorted({cell.key.level for cell in ordered_leaves})
        },
        "maximum_adjacent_level_jump": maximum_jump,
        "balance_touch_class": "face_edge_vertex",
        "touching_pair_count": len(touching),
        "face_adjacency_count": len(adjacencies),
        "strong_2_to_1_balance": maximum_jump <= 1,
        "hanging_face_count": len(hanging),
        "hanging_fine_face_count": 4 * len(hanging),
        "material_interface_hanging_face_count": len(material_hanging),
        "material_interface_protection": protect_material_interfaces,
        "periodic_axes": list(periodic_axes),
        "periodic_boundary_audit": periodic,
        "closure_split_counts": dict(closure_counts),
        "leaf_catalog_sha256": _json_sha256(leaf_payload),
        "hanging_face_catalog_sha256": _json_sha256(
            [patch.to_dict() for patch in hanging]
        ),
        "axis_aligned_affine_hexahedra": True,
        "local_h_is_real_cell_split": True,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    return BalancedDyadicHexForest(
        root_boxes=root_boxes,
        root_material_tags=root_material_tags,
        leaves=ordered_leaves,
        periodic_axes=periodic_axes,
        protect_material_interfaces=protect_material_interfaces,
        domain_bounds=bounds,
        hanging_faces=hanging,
        audit=MappingProxyType(audit),
    )


def build_root_dyadic_hexa_forest(
    root_boxes: Sequence[Sequence[float]],
    material_tags: Sequence[int],
    *,
    periodic_axes: Sequence[str] = ("x", "y"),
    protect_material_interfaces: bool = True,
) -> BalancedDyadicHexForest:
    """Create the unrefined level-zero forest from a conforming box catalog."""

    boxes = tuple(_box(values) for values in root_boxes)
    tags = tuple(map(int, material_tags))
    if not boxes or len(boxes) != len(tags):
        raise ValueError("root boxes and material tags must be nonempty peers")
    if len(set(boxes)) != len(boxes):
        raise ValueError("root hexahedron boxes must be unique")
    axes = tuple(
        dict.fromkeys(str(axis).lower() for axis in periodic_axes)
    )
    if any(axis not in _AXIS_INDEX for axis in axes):
        raise ValueError("periodic axes must be drawn from x/y/z")
    leaves = {
        DyadicHexKey(root, 0, 0, 0, 0): DyadicHexCell(
            key=DyadicHexKey(root, 0, 0, 0, 0),
            box=box,
            material_tag=tags[root],
        )
        for root, box in enumerate(boxes)
    }
    return _forest(
        root_boxes=boxes,
        root_material_tags=tags,
        leaves=leaves,
        periodic_axes=axes,
        protect_material_interfaces=bool(protect_material_interfaces),
        closure_counts={
            "user": 0,
            "periodic": 0,
            "material": 0,
            "balance": 0,
        },
    )


def refine_balanced_dyadic_hexa_forest(
    forest: BalancedDyadicHexForest,
    marked_leaves: Iterable[DyadicHexKey],
    *,
    maximum_level: int = 2,
) -> BalancedDyadicHexForest:
    """Split marked leaves and apply periodic, material, and 2:1 closure."""

    maximum_level = int(maximum_level)
    if maximum_level < 1:
        raise ValueError("maximum dyadic level must be at least one")
    leaves = dict(forest.leaf_by_key)
    requested = set(marked_leaves)
    if not requested:
        raise ValueError("local-h refinement requires at least one marked leaf")
    missing = sorted(requested - set(leaves))
    if missing:
        raise ValueError(f"marked leaves are not current leaves: {missing}")
    bounds = forest.domain_bounds
    tolerance = _geometry_tolerance(bounds)
    closure_counts = {
        "user": len(requested),
        "periodic": 0,
        "material": 0,
        "balance": 0,
    }
    targets, periodic_added, material_added = _pre_split_closure(
        leaves,
        requested,
        bounds=bounds,
        periodic_axes=forest.periodic_axes,
        protect_material_interfaces=forest.protect_material_interfaces,
        tolerance=tolerance,
    )
    closure_counts["periodic"] += periodic_added
    closure_counts["material"] += material_added
    _split(
        leaves,
        targets,
        root_boxes=forest.root_boxes,
        maximum_level=maximum_level,
    )

    while True:
        balance_targets: set[DyadicHexKey] = set()
        material_targets: set[DyadicHexKey] = set()
        for left_key, right_key in _touching_pairs(
            leaves,
            tolerance=tolerance,
        ):
            left = leaves[left_key]
            right = leaves[right_key]
            difference = left.key.level - right.key.level
            if abs(difference) > 1:
                balance_targets.add(
                    right.key if difference > 0 else left.key
                )
        for adjacency in _face_adjacencies(leaves, tolerance=tolerance):
            left = leaves[adjacency.left]
            right = leaves[adjacency.right]
            difference = left.key.level - right.key.level
            if (
                forest.protect_material_interfaces
                and left.material_tag != right.material_tag
                and difference != 0
            ):
                material_targets.add(
                    right.key if difference > 0 else left.key
                )
        _periodic_rows, periodic_targets = _periodic_boundary_audit(
            leaves,
            bounds=bounds,
            periodic_axes=forest.periodic_axes,
            tolerance=tolerance,
        )
        targets = (
            balance_targets
            | material_targets
            | set(periodic_targets)
        )
        if not targets:
            break
        closure_counts["balance"] += len(balance_targets)
        closure_counts["material"] += len(material_targets)
        closure_counts["periodic"] += len(periodic_targets)
        targets, periodic_added, material_added = _pre_split_closure(
            leaves,
            targets,
            bounds=bounds,
            periodic_axes=forest.periodic_axes,
            protect_material_interfaces=(
                forest.protect_material_interfaces
            ),
            tolerance=tolerance,
        )
        closure_counts["periodic"] += periodic_added
        closure_counts["material"] += material_added
        _split(
            leaves,
            targets,
            root_boxes=forest.root_boxes,
            maximum_level=maximum_level,
        )

    return _forest(
        root_boxes=forest.root_boxes,
        root_material_tags=forest.root_material_tags,
        leaves=leaves,
        periodic_axes=forest.periodic_axes,
        protect_material_interfaces=forest.protect_material_interfaces,
        closure_counts=closure_counts,
    )


__all__ = [
    "BalancedDyadicHexForest",
    "Box",
    "DyadicHexCell",
    "DyadicHexKey",
    "FaceAdjacency",
    "HangingFacePatch",
    "build_root_dyadic_hexa_forest",
    "refine_balanced_dyadic_hexa_forest",
]
