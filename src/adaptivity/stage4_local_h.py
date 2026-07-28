"""Explicit Stage-4 adapter for balanced dyadic local-hexa refinement.

The ordinary Stage-4 mesh builder remains unchanged.  This module is entered
only when a hash-bound local-h plan is supplied.  It builds the physical
dyadic forest, the deliberately broken DOLFINx carrier, and the combined
hanging/Floquet trace authority used by assembly-time cell condensation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np

from src.common.config_3d import SimulationConfig3D
from src.geometry.mesh_builder_3d import AirBox3DMesh, stage4_axis_plan

from .dyadic_hexa_broken_mesh import (
    BrokenDyadicHexCarrier,
    build_broken_dyadic_hexa_carrier,
)
from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    Box,
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from .hcurl_broken_cell_trace import (
    BrokenHexCellTraceConstraintMap,
    build_broken_hexa_cell_trace_constraint_map,
)
from .hcurl_broken_trace_graph import (
    build_broken_hexa_entity_degree_arrays,
    build_broken_hexa_trace_constraint_authority,
)
from .variable_p_degree_plan import (
    CellBoxKey,
    VariablePCellDegreePlan,
    cell_box_catalog,
    cell_box_catalog_sha256,
)
from .variable_p_entity_map import build_variable_p_global_entity_map


LOCAL_H_PLAN_SCHEMA = "task035d.stage4-local-h-refinement-plan.v1"
MULTILEVEL_LOCAL_H_PLAN_SCHEMA = (
    "task035e.stage4-multilevel-local-h-refinement-plan.v1"
)


@dataclass(frozen=True)
class Stage4LocalHContext:
    """Audited mesh-side state retained for the condensed solver."""

    forest: BalancedDyadicHexForest
    carrier: BrokenDyadicHexCarrier
    plan_path: str
    plan_file_sha256: str
    trace_degree: int
    cell_interior_degree: int
    cell_interior_degree_by_box: Mapping[CellBoxKey, int]
    variable_trace_from_cell_degrees: bool
    selected_p6_face_geometry_keys: tuple[tuple[int, ...], ...]
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class Stage4LocalHReductionAuthority:
    """Exact-sequence active space and physical trace constraints."""

    degree_plan: VariablePCellDegreePlan
    trace_constraints: BrokenHexCellTraceConstraintMap
    audit: Mapping[str, Any]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _collective_phase_timings(
    comm: MPI.Intracomm,
    local_seconds: Mapping[str, float],
) -> dict[str, Any]:
    """Publish diagnostic-only phase wall times with MPI fail-closed keys."""

    normalized = {
        str(key): float(value) for key, value in local_seconds.items()
    }
    if any(
        not np.isfinite(value) or value < 0.0
        for value in normalized.values()
    ):
        raise RuntimeError("Stage-4 setup timing contains an invalid value")
    packets = comm.allgather(normalized)
    keys = tuple(normalized)
    if any(tuple(packet) != keys for packet in packets):
        raise RuntimeError("MPI Stage-4 timing phase catalogs differ")
    by_rank = {
        key: [float(packet[key]) for packet in packets]
        for key in keys
    }
    return {
        "semantics": (
            "perf_counter wall seconds; by-rank values plus MPI maximum; "
            "diagnostic only and excluded from geometry/numerical hashes"
        ),
        "seconds_by_rank": by_rank,
        "seconds_max": {
            key: max(values) for key, values in by_rank.items()
        },
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_box(values: Sequence[float]) -> Box:
    if len(values) != 6:
        raise ValueError("one local-h box requires six coordinates")
    box = tuple(round(float(value), 12) for value in values)
    if any(box[axis] >= box[axis + 3] for axis in range(3)):
        raise ValueError("one local-h box has non-positive extent")
    return box  # type: ignore[return-value]


def _cell_interior_degree_catalog(
    forest: BalancedDyadicHexForest,
    *,
    trace_degree: int,
    container_degree: int,
    overrides: Mapping[CellBoxKey, int] | None = None,
) -> dict[CellBoxKey, int]:
    """Close sparse leaf overrides into one complete geometry-bound catalog."""

    boxes = tuple(cell.box for cell in forest.leaves)
    result: dict[CellBoxKey, int] = {
        box: int(container_degree) for box in boxes
    }
    normalized_overrides: dict[CellBoxKey, int] = {}
    for raw_box, raw_degree in (overrides or {}).items():
        box = _normalized_box(raw_box)
        if box in normalized_overrides:
            raise ValueError("local-h cell-interior box is duplicated")
        normalized_overrides[box] = int(raw_degree)
    missing = sorted(set(normalized_overrides) - set(boxes))
    if missing:
        raise ValueError(
            "local-h cell-interior override is not one forest leaf: "
            f"{missing[:2]}"
        )
    result.update(normalized_overrides)
    invalid = sorted(
        {
            degree
            for degree in result.values()
            if degree not in {4, 5, 6}
            or degree < int(trace_degree)
            or degree > int(container_degree)
        }
    )
    if invalid:
        raise ValueError(
            "local-h variable interiors require p4/p5/p6 and "
            "trace_degree <= degree <= p6: "
            f"{invalid}"
        )
    return result


def _cell_interior_degree_sha256(
    degree_by_box: Mapping[CellBoxKey, int],
) -> str:
    return _json_sha256(
        [
            {"box": list(box), "degree": int(degree_by_box[box])}
            for box in sorted(degree_by_box)
        ]
    )


def _cell_interior_degree_rows(
    degree_by_box: Mapping[CellBoxKey, int],
) -> list[dict[str, Any]]:
    return [
        {
            "lower": list(box[:3]),
            "upper": list(box[3:]),
            "degree": int(degree_by_box[box]),
        }
        for box in sorted(degree_by_box)
    ]


def _load_cell_interior_degree_catalog(
    payload: Mapping[str, Any],
    forest: BalancedDyadicHexForest,
    *,
    trace_degree: int,
    container_degree: int,
) -> dict[CellBoxKey, int]:
    rows = payload.get("cell_interior_degrees")
    if rows is None:
        # Backwards compatibility for the already frozen h-only p6 plans.
        return _cell_interior_degree_catalog(
            forest,
            trace_degree=trace_degree,
            container_degree=container_degree,
        )
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            "local-h variable cell-interior catalog must be nonempty"
        )
    catalog: dict[CellBoxKey, int] = {}
    for row in rows:
        box = _normalized_box((*row["lower"], *row["upper"]))
        if box in catalog:
            raise ValueError("local-h cell-interior box is duplicated")
        catalog[box] = int(row["degree"])
    closed = _cell_interior_degree_catalog(
        forest,
        trace_degree=trace_degree,
        container_degree=container_degree,
        overrides=catalog,
    )
    if set(catalog) != set(closed):
        raise ValueError(
            "local-h variable cell-interior catalog must list every leaf"
        )
    expected_sha = payload.get("cell_interior_degree_plan_sha256")
    actual_sha = _cell_interior_degree_sha256(closed)
    if expected_sha != actual_sha:
        raise ValueError(
            "local-h cell-interior degree-plan content SHA is invalid"
        )
    return closed


def _stage4_root_boxes(
    cfg: SimulationConfig3D,
    *,
    comm_size: int,
) -> tuple[Box, ...]:
    plan = stage4_axis_plan(cfg, int(comm_size))
    return tuple(
        _normalized_box(
            (
                plan.x_values[ix],
                plan.y_values[iy],
                plan.z_values[iz],
                plan.x_values[ix + 1],
                plan.y_values[iy + 1],
                plan.z_values[iz + 1],
            )
        )
        for iz in range(len(plan.z_values) - 1)
        for iy in range(len(plan.y_values) - 1)
        for ix in range(len(plan.x_values) - 1)
    )


def _base_config_identity(
    cfg: SimulationConfig3D,
    *,
    comm_size: int,
) -> dict[str, Any]:
    plan = stage4_axis_plan(cfg, int(comm_size))
    payload = {
        "stage_case": cfg.stage_case,
        "geometry_kind": cfg.geometry_kind,
        "period_x": float(cfg.period_x),
        "period_y": float(cfg.period_y),
        "domain_z_min": float(cfg.domain_z_min),
        "domain_z_max": float(cfg.domain_z_max),
        "interface_z": float(cfg.interface_z),
        "grating_bounds": [
            float(cfg.grating_x_min),
            float(cfg.grating_y_min),
            float(cfg.grating_z_min),
            float(cfg.grating_x_max),
            float(cfg.grating_y_max),
            float(cfg.grating_z_max),
        ],
        "mesh_target_size": float(cfg.mesh_target_size),
        "mesh_spacing_mode_resolved": plan.mesh_spacing_mode_resolved,
        "axis_values": {
            "x": list(map(float, plan.x_values)),
            "y": list(map(float, plan.y_values)),
            "z": list(map(float, plan.z_values)),
        },
        "mesh_cells_resolved": list(plan.mesh_cells_resolved),
        "material_tags": {
            "air": int(cfg.tags.air),
            "substrate": int(cfg.tags.substrate),
            "grating": int(cfg.tags.grating),
        },
        "boundary_tags": {
            "x_lower": int(cfg.tags.x_min),
            "x_upper": int(cfg.tags.x_max),
            "y_lower": int(cfg.tags.y_min),
            "y_upper": int(cfg.tags.y_max),
            "z_lower": int(cfg.tags.z_min),
            "z_upper": int(cfg.tags.z_max),
        },
    }
    payload["identity_sha256"] = _json_sha256(payload)
    return payload


def _root_material_tags(
    cfg: SimulationConfig3D,
    root_boxes: tuple[Box, ...],
) -> tuple[int, ...]:
    extent = max(
        cfg.x_max - cfg.x_min,
        cfg.y_max - cfg.y_min,
        cfg.domain_z_max - cfg.domain_z_min,
        1.0,
    )
    tolerance = 1.0e-11 * extent
    material_planes = (
        (0, cfg.grating_x_min, "grating_x_min"),
        (0, cfg.grating_x_max, "grating_x_max"),
        (1, cfg.grating_y_min, "grating_y_min"),
        (1, cfg.grating_y_max, "grating_y_max"),
        (2, cfg.interface_z, "interface_z"),
        (2, cfg.grating_z_max, "grating_z_max"),
    )
    tags: list[int] = []
    for box in root_boxes:
        for axis, plane, label in material_planes:
            if box[axis] + tolerance < plane < box[axis + 3] - tolerance:
                raise RuntimeError(
                    f"Stage-4 local-h root straddles {label}: {box}"
                )
        midpoint = tuple(
            0.5 * (box[axis] + box[axis + 3])
            for axis in range(3)
        )
        in_grating = bool(
            cfg.has_grating_block
            and cfg.grating_x_min - tolerance
            <= midpoint[0]
            <= cfg.grating_x_max + tolerance
            and cfg.grating_y_min - tolerance
            <= midpoint[1]
            <= cfg.grating_y_max + tolerance
            and cfg.grating_z_min - tolerance
            <= midpoint[2]
            <= cfg.grating_z_max + tolerance
        )
        if in_grating:
            tags.append(int(cfg.tags.grating))
        elif midpoint[2] < cfg.interface_z - tolerance:
            tags.append(int(cfg.tags.substrate))
        else:
            tags.append(int(cfg.tags.air))
    return tuple(tags)


def stage4_local_h_root_forest_catalog(
    cfg: SimulationConfig3D,
    *,
    comm_size: int,
) -> BalancedDyadicHexForest:
    """Return the immutable geometry-only root catalog for plan builders."""

    roots = _stage4_root_boxes(cfg, comm_size=int(comm_size))
    return build_root_dyadic_hexa_forest(
        roots,
        _root_material_tags(cfg, roots),
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )


def _build_forest(
    cfg: SimulationConfig3D,
    *,
    comm_size: int,
    marked_root_boxes: Sequence[Sequence[float]],
    maximum_level: int,
) -> BalancedDyadicHexForest:
    if int(maximum_level) != 1:
        raise ValueError("the qualified Stage-4 local-h plan allows one split")
    roots = _stage4_root_boxes(cfg, comm_size=int(comm_size))
    root_by_box = {box: index for index, box in enumerate(roots)}
    marked = tuple(_normalized_box(box) for box in marked_root_boxes)
    if not marked or len(set(marked)) != len(marked):
        raise ValueError("local-h marked root boxes must be nonempty and unique")
    missing = sorted(set(marked) - set(root_by_box))
    if missing:
        raise ValueError(
            f"local-h plan marks boxes outside the root mesh: {missing[:2]}"
        )
    forest = build_root_dyadic_hexa_forest(
        roots,
        _root_material_tags(cfg, roots),
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    return refine_balanced_dyadic_hexa_forest(
        forest,
        (
            DyadicHexKey(root_by_box[box], 0, 0, 0, 0)
            for box in marked
        ),
        maximum_level=1,
    )


def _box_row(box: Box) -> dict[str, list[float]]:
    return {
        "lower": list(box[:3]),
        "upper": list(box[3:]),
    }


def _build_multilevel_forest(
    cfg: SimulationConfig3D,
    *,
    comm_size: int,
    refinement_stages: Sequence[Sequence[Sequence[float]]],
    maximum_level: int,
) -> tuple[
    BalancedDyadicHexForest,
    tuple[tuple[Box, ...], ...],
    tuple[dict[str, Any], ...],
]:
    """Apply geometry-bound leaf marks in deterministic refinement stages."""

    maximum_level = int(maximum_level)
    if maximum_level != 2:
        raise ValueError(
            "the qualified Task035e multilevel plan requires maximum_level=2"
        )
    if not 1 <= len(refinement_stages) <= 6:
        raise ValueError(
            "Task035e multilevel plans require one to six action stages"
        )
    roots = _stage4_root_boxes(cfg, comm_size=int(comm_size))
    forest = build_root_dyadic_hexa_forest(
        roots,
        _root_material_tags(cfg, roots),
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    normalized_stages: list[tuple[Box, ...]] = []
    stage_audits: list[dict[str, Any]] = []
    for stage_index, raw_stage in enumerate(refinement_stages, start=1):
        marked = tuple(_normalized_box(box) for box in raw_stage)
        if not marked or len(set(marked)) != len(marked):
            raise ValueError(
                "multilevel local-h stage marks must be nonempty and unique"
            )
        key_by_box = {cell.box: cell.key for cell in forest.leaves}
        missing = sorted(set(marked) - set(key_by_box))
        if missing:
            raise ValueError(
                "multilevel local-h stage marks boxes that are not current "
                f"leaves: stage={stage_index}, missing={missing[:2]}"
            )
        marked_keys = tuple(key_by_box[box] for box in marked)
        pre_leaf_by_key = dict(forest.leaf_by_key)
        pre_leaf_count = len(pre_leaf_by_key)
        forest = refine_balanced_dyadic_hexa_forest(
            forest,
            marked_keys,
            maximum_level=maximum_level,
        )
        split_keys = set(pre_leaf_by_key) - set(forest.leaf_by_key)
        closure_added = tuple(sorted(split_keys - set(marked_keys)))
        normalized_stages.append(marked)
        stage_audits.append(
            {
                "stage_index": stage_index,
                "marked_leaves": [
                    {
                        **_box_row(box),
                        "dyadic_key": key.to_dict(),
                    }
                    for box, key in sorted(
                        zip(marked, marked_keys, strict=True),
                        key=lambda row: row[0],
                    )
                ],
                "pre_leaf_count": pre_leaf_count,
                "post_leaf_count": len(forest.leaves),
                "closure_added_leaves": [
                    {
                        **_box_row(pre_leaf_by_key[key].box),
                        "dyadic_key": key.to_dict(),
                    }
                    for key in closure_added
                ],
                "post_leaf_level_counts": dict(
                    forest.audit["leaf_level_counts"]
                ),
                "closure_counts": dict(
                    forest.audit["closure_split_counts"]
                ),
                "post_leaf_catalog_sha256": forest.audit[
                    "leaf_catalog_sha256"
                ],
                "post_hanging_face_catalog_sha256": forest.audit[
                    "hanging_face_catalog_sha256"
                ],
            }
        )
    return (
        forest,
        tuple(normalized_stages),
        tuple(stage_audits),
    )


def stage4_multilevel_local_h_forest_catalog(
    cfg: SimulationConfig3D,
    refinement_stages: Sequence[Sequence[Sequence[float]]],
    *,
    comm_size: int,
) -> BalancedDyadicHexForest:
    """Return the immutable closed leaf catalog for one incremental plan."""

    forest, _normalized_stages, _stage_audits = _build_multilevel_forest(
        cfg,
        comm_size=int(comm_size),
        refinement_stages=refinement_stages,
        maximum_level=2,
    )
    return forest


def _forest_expectation(
    forest: BalancedDyadicHexForest,
) -> dict[str, Any]:
    return {
        "root_cell_count": len(forest.root_boxes),
        "leaf_cell_count": len(forest.leaves),
        "hanging_patch_count": len(forest.hanging_faces),
        "closure_counts": dict(forest.audit["closure_split_counts"]),
        "root_catalog_sha256": _json_sha256(
            [
                {"box": list(box), "material_tag": int(tag)}
                for box, tag in zip(
                    forest.root_boxes,
                    forest.root_material_tags,
                    strict=True,
                )
            ]
        ),
        "leaf_catalog_sha256": forest.audit["leaf_catalog_sha256"],
        "hanging_face_catalog_sha256": forest.audit[
            "hanging_face_catalog_sha256"
        ],
    }


def _multilevel_leaf_inventory(
    forest: BalancedDyadicHexForest,
) -> dict[str, Any]:
    """Return geometry-only leaf sizes and material/level populations."""

    size_counts: dict[tuple[float, float, float], int] = {}
    material_level_counts: dict[tuple[int, int], int] = {}
    material_size_counts: dict[
        tuple[int, float, float, float],
        int,
    ] = {}
    for cell in forest.leaves:
        size = tuple(
            round(cell.box[axis + 3] - cell.box[axis], 12)
            for axis in range(3)
        )
        size_counts[size] = size_counts.get(size, 0) + 1
        material_level = (int(cell.material_tag), int(cell.key.level))
        material_level_counts[material_level] = (
            material_level_counts.get(material_level, 0) + 1
        )
        material_size = (int(cell.material_tag), *size)
        material_size_counts[material_size] = (
            material_size_counts.get(material_size, 0) + 1
        )
    return {
        "leaf_size_histogram": [
            {
                "size": list(size),
                "count": count,
            }
            for size, count in sorted(size_counts.items())
        ],
        "material_level_histogram": [
            {
                "material_tag": material_tag,
                "level": level,
                "count": count,
            }
            for (material_tag, level), count in sorted(
                material_level_counts.items()
            )
        ],
        "material_size_histogram": [
            {
                "material_tag": row[0],
                "size": list(row[1:]),
                "count": count,
            }
            for row, count in sorted(material_size_counts.items())
        ],
    }


def _user_mark_component_count(
    refinement_stages: Sequence[Sequence[Box]],
) -> int:
    """Count connected components of requested boxes, excluding closure."""

    boxes = tuple(
        box
        for stage in refinement_stages
        for box in stage
    )
    if not boxes:
        return 0
    extent = max(
        max(box[axis + 3] - box[axis] for axis in range(3))
        for box in boxes
    )
    tolerance = max(extent, 1.0) * 1.0e-11

    def connected(left: Box, right: Box) -> bool:
        return all(
            max(left[axis], right[axis])
            <= min(left[axis + 3], right[axis + 3]) + tolerance
            for axis in range(3)
        )

    parent = list(range(len(boxes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(boxes)):
        for right in range(left + 1, len(boxes)):
            if connected(boxes[left], boxes[right]):
                union(left, right)
    return len({find(index) for index in range(len(boxes))})


def _multilevel_audit(
    forest: BalancedDyadicHexForest,
    *,
    refinement_stage_count: int,
    refinement_stages: Sequence[Sequence[Box]],
) -> dict[str, Any]:
    actual_maximum_level = max(
        cell.key.level for cell in forest.leaves
    )
    level_counts = dict(forest.audit["leaf_level_counts"])
    all_local_levels_present = all(
        int(level_counts.get(str(level), 0)) > 0
        for level in range(3)
    )
    user_mark_component_count = _user_mark_component_count(
        refinement_stages
    )
    return {
        "true_multilevel": (
            actual_maximum_level >= 2
            and all_local_levels_present
        ),
        "actual_maximum_level": actual_maximum_level,
        "all_local_levels_present": all_local_levels_present,
        "user_mark_component_count": user_mark_component_count,
        "spatially_separated_user_patches": (
            user_mark_component_count >= 2
        ),
        "leaf_level_counts": level_counts,
        "maximum_adjacent_level_jump": int(
            forest.audit["maximum_adjacent_level_jump"]
        ),
        "strong_2_to_1_balance": bool(
            forest.audit["strong_2_to_1_balance"]
        ),
        "periodic_boundary_audit": dict(
            forest.audit["periodic_boundary_audit"]
        ),
        "material_interface_hanging_face_count": int(
            forest.audit[
                "material_interface_hanging_face_count"
            ]
        ),
        "leaf_inventory": _multilevel_leaf_inventory(forest),
    }


def stage4_local_h_refinement_plan_payload(
    cfg: SimulationConfig3D,
    marked_root_boxes: Sequence[Sequence[float]],
    *,
    comm_size: int,
    trace_degree: int,
    cell_interior_degree: int,
    provenance: Mapping[str, Any],
    cell_interior_degree_overrides: (
        Mapping[CellBoxKey, int] | None
    ) = None,
    selected_p6_face_geometry_keys: Sequence[Sequence[int]] = (),
) -> dict[str, Any]:
    """Return a JSON-ready, geometry-bound one-cycle local h/p plan."""

    trace_degree = int(trace_degree)
    cell_interior_degree = int(cell_interior_degree)
    if trace_degree not in {4, 5, 6}:
        raise ValueError("local-h trace degree must be p4, p5, or p6")
    if cell_interior_degree != 6 or trace_degree > cell_interior_degree:
        raise ValueError(
            "current local-h production adapter requires a p6 container"
        )
    marked = tuple(_normalized_box(box) for box in marked_root_boxes)
    selected_faces = tuple(
        tuple(map(int, geometry_key))
        for geometry_key in selected_p6_face_geometry_keys
    )
    if len(set(selected_faces)) != len(selected_faces):
        raise ValueError("selected p6 physical face key is duplicated")
    if any(len(geometry_key) != 6 for geometry_key in selected_faces):
        raise ValueError(
            "selected p6 physical face key must have six integers"
        )
    if selected_faces and trace_degree != 5:
        raise ValueError(
            "selective p6 physical faces require a p5 trace base"
        )
    forest = _build_forest(
        cfg,
        comm_size=int(comm_size),
        marked_root_boxes=marked,
        maximum_level=1,
    )
    base = _base_config_identity(cfg, comm_size=int(comm_size))
    degree_catalog = _cell_interior_degree_catalog(
        forest,
        trace_degree=trace_degree,
        container_degree=cell_interior_degree,
        overrides=cell_interior_degree_overrides,
    )
    payload = {
        "schema_version": LOCAL_H_PLAN_SCHEMA,
        "status": "stage4_balanced_local_h_plan",
        "base_config": base,
        "root_cell_box_catalog_sha256": cell_box_catalog_sha256(
            forest.root_boxes
        ),
        "marked_root_boxes": [
            {"lower": list(box[:3]), "upper": list(box[3:])}
            for box in marked
        ],
        "periodic_axes": ["x", "y"],
        "protect_material_interfaces": True,
        "maximum_level": 1,
        "trace_degree": trace_degree,
        "cell_interior_degree": cell_interior_degree,
        "expected_forest": _forest_expectation(forest),
        "provenance": dict(provenance),
        "ordinary_default_changed": False,
    }
    if cell_interior_degree_overrides is not None:
        payload["cell_interior_degrees"] = (
            _cell_interior_degree_rows(degree_catalog)
        )
        payload["cell_interior_degree_plan_sha256"] = (
            _cell_interior_degree_sha256(degree_catalog)
        )
    if selected_faces:
        payload["selected_p6_face_geometry_keys"] = [
            list(key) for key in sorted(selected_faces)
        ]
    return payload


def stage4_multilevel_local_h_refinement_plan_payload(
    cfg: SimulationConfig3D,
    refinement_stages: Sequence[Sequence[Sequence[float]]],
    *,
    comm_size: int,
    trace_degree: int,
    cell_interior_degree: int,
    provenance: Mapping[str, Any],
    cell_interior_degree_overrides: (
        Mapping[CellBoxKey, int] | None
    ) = None,
    selected_p6_face_geometry_keys: Sequence[Sequence[int]] = (),
    variable_trace_from_cell_degrees: bool = False,
) -> dict[str, Any]:
    """Return a hash-ready incremental multilevel local-h/p plan."""

    trace_degree = int(trace_degree)
    cell_interior_degree = int(cell_interior_degree)
    if trace_degree not in {4, 5, 6}:
        raise ValueError("multilevel local-h trace must be p4, p5, or p6")
    if cell_interior_degree != 6 or trace_degree > cell_interior_degree:
        raise ValueError(
            "Task035e multilevel local-h requires a p6 container"
        )
    selected_faces = tuple(
        tuple(map(int, geometry_key))
        for geometry_key in selected_p6_face_geometry_keys
    )
    if len(set(selected_faces)) != len(selected_faces):
        raise ValueError("selected p6 physical face key is duplicated")
    if any(len(geometry_key) != 6 for geometry_key in selected_faces):
        raise ValueError(
            "selected p6 physical face key must have six integers"
        )
    if selected_faces and trace_degree != 5:
        raise ValueError(
            "selective p6 physical faces require a p5 trace base"
        )
    variable_trace_from_cell_degrees = bool(
        variable_trace_from_cell_degrees
    )
    if variable_trace_from_cell_degrees and selected_faces:
        raise ValueError(
            "cell-driven variable trace and legacy selected-p6 faces are "
            "mutually exclusive"
        )
    if (
        variable_trace_from_cell_degrees
        and cell_interior_degree_overrides is None
    ):
        raise ValueError(
            "cell-driven variable trace requires an explicit complete "
            "cell-degree plan"
        )
    forest, normalized_stages, stage_audits = _build_multilevel_forest(
        cfg,
        comm_size=int(comm_size),
        refinement_stages=refinement_stages,
        maximum_level=2,
    )
    base = _base_config_identity(cfg, comm_size=int(comm_size))
    degree_catalog = _cell_interior_degree_catalog(
        forest,
        trace_degree=trace_degree,
        container_degree=cell_interior_degree,
        overrides=cell_interior_degree_overrides,
    )
    payload: dict[str, Any] = {
        "schema_version": MULTILEVEL_LOCAL_H_PLAN_SCHEMA,
        "status": "stage4_balanced_multilevel_local_h_plan",
        "base_config": base,
        "root_cell_box_catalog_sha256": cell_box_catalog_sha256(
            forest.root_boxes
        ),
        "refinement_stages": list(stage_audits),
        "periodic_axes": ["x", "y"],
        "protect_material_interfaces": True,
        "maximum_level": 2,
        "refinement_stage_count": len(normalized_stages),
        "trace_degree": trace_degree,
        "cell_interior_degree": cell_interior_degree,
        "variable_trace_from_cell_degrees": (
            variable_trace_from_cell_degrees
        ),
        "expected_forest": _forest_expectation(forest),
        "multilevel_audit": _multilevel_audit(
            forest,
            refinement_stage_count=len(normalized_stages),
            refinement_stages=normalized_stages,
        ),
        "provenance": dict(provenance),
        "ordinary_default_changed": False,
    }
    if cell_interior_degree_overrides is not None:
        payload["cell_interior_degrees"] = (
            _cell_interior_degree_rows(degree_catalog)
        )
        payload["cell_interior_degree_plan_sha256"] = (
            _cell_interior_degree_sha256(degree_catalog)
        )
    if selected_faces:
        payload["selected_p6_face_geometry_keys"] = [
            list(key) for key in sorted(selected_faces)
        ]
    return payload


def build_stage4_local_h_mesh_data(
    cfg: SimulationConfig3D,
    plan_path: str | Path,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> AirBox3DMesh:
    """Load one plan and build its audited broken-hexa carrier."""

    mesh_setup_started = perf_counter()
    config_validation_started = perf_counter()
    if (
        cfg.stage_case != "stage4_block_grating"
        or cfg.geometry_kind != "rectangular_block_grating"
        or not cfg.has_grating_block
    ):
        raise ValueError(
            "Stage-4 local-h is restricted to the fixed rectangular grating"
        )
    if cfg.mesh_cell_type_resolved != "hexahedron":
        raise ValueError("Stage-4 local-h requires affine hexahedra")
    if not cfg.use_floquet_xy or cfg.use_pml:
        raise ValueError("Stage-4 local-h requires x/y Floquet and no PML")
    config_validation_seconds = perf_counter() - config_validation_started

    plan_read_started = perf_counter()
    resolved = Path(plan_path).expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    plan_read_seconds = perf_counter() - plan_read_started
    forest_rebuild_started = perf_counter()
    schema = payload.get("schema_version")
    if schema not in {
        LOCAL_H_PLAN_SCHEMA,
        MULTILEVEL_LOCAL_H_PLAN_SCHEMA,
    }:
        raise ValueError("Stage-4 local-h plan has an unknown schema")
    if payload.get("periodic_axes") != ["x", "y"]:
        raise ValueError("Stage-4 local-h plan must close x/y periodicity")
    if payload.get("protect_material_interfaces") is not True:
        raise ValueError("Stage-4 local-h plan must protect material interfaces")
    base = _base_config_identity(cfg, comm_size=comm.size)
    if payload.get("base_config") != base:
        raise ValueError(
            "Stage-4 local-h plan base geometry differs from the live config"
        )
    if schema == LOCAL_H_PLAN_SCHEMA:
        if payload.get("status") != "stage4_balanced_local_h_plan":
            raise ValueError("Stage-4 local-h plan has an invalid status")
        if int(payload.get("maximum_level", -1)) != 1:
            raise ValueError("Stage-4 local-h plan may refine only once")
        rows = payload.get("marked_root_boxes")
        if not isinstance(rows, list):
            raise ValueError(
                "Stage-4 local-h plan has no marked root boxes"
            )
        marked = tuple(
            _normalized_box((*row["lower"], *row["upper"]))
            for row in rows
        )
        forest = _build_forest(
            cfg,
            comm_size=comm.size,
            marked_root_boxes=marked,
            maximum_level=1,
        )
        refinement_region_payload: dict[str, Any] = {
            "marked_root_boxes": [list(box) for box in marked]
        }
        refinement_stage_count = 1
        maximum_level = 1
    else:
        if payload.get("status") != (
            "stage4_balanced_multilevel_local_h_plan"
        ):
            raise ValueError(
                "Stage-4 multilevel local-h plan has an invalid status"
            )
        if int(payload.get("maximum_level", -1)) != 2:
            raise ValueError(
                "Stage-4 multilevel local-h plan requires two levels"
            )
        stage_rows = payload.get("refinement_stages")
        if (
            not isinstance(stage_rows, list)
            or not 1 <= len(stage_rows) <= 6
        ):
            raise ValueError(
                "Stage-4 multilevel local-h plan requires one to six stages"
            )
        stages: list[tuple[Box, ...]] = []
        for stage_index, stage_row in enumerate(stage_rows, start=1):
            if int(stage_row.get("stage_index", -1)) != stage_index:
                raise ValueError(
                    "Stage-4 multilevel stage indices are not contiguous"
                )
            marked_rows = stage_row.get("marked_leaves")
            if not isinstance(marked_rows, list):
                raise ValueError(
                    "Stage-4 multilevel stage has no marked leaves"
                )
            stages.append(
                tuple(
                    _normalized_box(
                        (*row["lower"], *row["upper"])
                    )
                    for row in marked_rows
                )
            )
        forest, normalized_stages, rebuilt_stage_rows = (
            _build_multilevel_forest(
                cfg,
                comm_size=comm.size,
                refinement_stages=stages,
                maximum_level=2,
            )
        )
        if list(rebuilt_stage_rows) != stage_rows:
            raise ValueError(
                "Stage-4 multilevel refinement-stage identity drifted"
            )
        refinement_stage_count = len(normalized_stages)
        if (
            int(payload.get("refinement_stage_count", -1))
            != refinement_stage_count
        ):
            raise ValueError(
                "Stage-4 multilevel refinement-stage count drifted"
            )
        expected_multilevel_audit = _multilevel_audit(
            forest,
            refinement_stage_count=refinement_stage_count,
            refinement_stages=normalized_stages,
        )
        if payload.get("multilevel_audit") != expected_multilevel_audit:
            raise ValueError(
                "Stage-4 multilevel mesh audit identity drifted"
            )
        refinement_region_payload = {
            "refinement_stages": [
                [list(box) for box in stage]
                for stage in normalized_stages
            ]
        }
        maximum_level = int(
            expected_multilevel_audit["actual_maximum_level"]
        )
    if payload.get("root_cell_box_catalog_sha256") != (
        cell_box_catalog_sha256(forest.root_boxes)
    ):
        raise ValueError("Stage-4 local-h root-box identity drifted")
    expectation = _forest_expectation(forest)
    if payload.get("expected_forest") != expectation:
        raise ValueError("Stage-4 local-h forest identity drifted")
    forest_rebuild_seconds = perf_counter() - forest_rebuild_started

    markers = base["boundary_tags"]
    carrier_started = perf_counter()
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=comm,
        boundary_markers=markers,
    )
    carrier_seconds = perf_counter() - carrier_started
    degree_catalog_started = perf_counter()
    trace_degree = int(payload.get("trace_degree", -1))
    cell_interior_degree = int(payload.get("cell_interior_degree", -1))
    if trace_degree not in {4, 5, 6}:
        raise ValueError("Stage-4 local-h plan has an invalid trace degree")
    if cell_interior_degree != int(cfg.nedelec_degree):
        raise ValueError(
            "Stage-4 local-h interior degree differs from the p6 container"
        )
    selected_face_rows = payload.get(
        "selected_p6_face_geometry_keys",
        [],
    )
    if not isinstance(selected_face_rows, list):
        raise ValueError("selected p6 physical face catalog is invalid")
    selected_p6_face_geometry_keys = tuple(
        tuple(map(int, geometry_key))
        for geometry_key in selected_face_rows
    )
    if (
        len(set(selected_p6_face_geometry_keys))
        != len(selected_p6_face_geometry_keys)
        or any(
            len(geometry_key) != 6
            for geometry_key in selected_p6_face_geometry_keys
        )
    ):
        raise ValueError(
            "selected p6 physical face catalog is duplicated or malformed"
        )
    if selected_p6_face_geometry_keys and trace_degree != 5:
        raise ValueError(
            "selected p6 physical faces require a p5 trace base"
        )
    variable_trace_from_cell_degrees = payload.get(
        "variable_trace_from_cell_degrees",
        False,
    )
    if not isinstance(variable_trace_from_cell_degrees, bool):
        raise ValueError(
            "cell-driven variable-trace opt-in must be a boolean"
        )
    if (
        schema != MULTILEVEL_LOCAL_H_PLAN_SCHEMA
        and variable_trace_from_cell_degrees
    ):
        raise ValueError(
            "cell-driven variable trace requires the Task035e "
            "multilevel schema"
        )
    if (
        variable_trace_from_cell_degrees
        and selected_p6_face_geometry_keys
    ):
        raise ValueError(
            "cell-driven variable trace and legacy selected-p6 faces are "
            "mutually exclusive"
        )
    cell_interior_degree_by_box = _load_cell_interior_degree_catalog(
        payload,
        forest,
        trace_degree=trace_degree,
        container_degree=cell_interior_degree,
    )
    degree_counts = {
        f"p{degree}": sum(
            value == degree
            for value in cell_interior_degree_by_box.values()
        )
        for degree in (4, 5, 6)
    }
    plan_file_sha256 = _file_sha256(resolved)
    degree_catalog_seconds = perf_counter() - degree_catalog_started
    timing = _collective_phase_timings(
        comm,
        {
            "config_validation": config_validation_seconds,
            "plan_file_read": plan_read_seconds,
            "forest_rebuild_and_identity": forest_rebuild_seconds,
            "broken_carrier_build": carrier_seconds,
            "degree_catalog_and_plan_hash": degree_catalog_seconds,
            "local_h_mesh_setup_total_before_audit_publish": (
                perf_counter() - mesh_setup_started
            ),
        },
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035e.stage4-multilevel-local-h-mesh.v1"
                if schema == MULTILEVEL_LOCAL_H_PLAN_SCHEMA
                else "task035d.stage4-local-h-mesh.v1"
            ),
            "status": (
                "stage4_balanced_multilevel_local_h_mesh_pass"
                if schema == MULTILEVEL_LOCAL_H_PLAN_SCHEMA
                else "stage4_balanced_local_h_mesh_pass"
            ),
            "pass": True,
            "plan_path": str(resolved),
            "plan_file_sha256": plan_file_sha256,
            "base_config_identity_sha256": base["identity_sha256"],
            "trace_degree": trace_degree,
            "cell_interior_degree": cell_interior_degree,
            "cell_interior_degree_counts": degree_counts,
            "cell_interior_degree_plan_sha256": (
                _cell_interior_degree_sha256(
                    cell_interior_degree_by_box
                )
            ),
            "variable_cell_interior_degree": (
                len(
                    set(cell_interior_degree_by_box.values())
                )
                > 1
            ),
            "variable_trace_from_cell_degrees": (
                variable_trace_from_cell_degrees
            ),
            "selected_p6_face_count": len(
                selected_p6_face_geometry_keys
            ),
            "selected_p6_face_geometry_keys": [
                list(key)
                for key in selected_p6_face_geometry_keys
            ],
            "root_cell_count": len(forest.root_boxes),
            "leaf_cell_count": len(forest.leaves),
            "hanging_patch_count": len(forest.hanging_faces),
            "maximum_level": maximum_level,
            "refinement_stage_count": refinement_stage_count,
            "true_multilevel": (
                schema == MULTILEVEL_LOCAL_H_PLAN_SCHEMA
                and maximum_level == 2
            ),
            "user_mark_component_count": (
                None
                if schema == LOCAL_H_PLAN_SCHEMA
                else expected_multilevel_audit[
                    "user_mark_component_count"
                ]
            ),
            "spatially_separated_user_patches": (
                False
                if schema == LOCAL_H_PLAN_SCHEMA
                else expected_multilevel_audit[
                    "spatially_separated_user_patches"
                ]
            ),
            "forest": dict(forest.audit),
            "carrier": dict(carrier.audit),
            "phase_timing_semantics": timing["semantics"],
            "phase_timings_seconds_by_rank": timing[
                "seconds_by_rank"
            ],
            "phase_timings_seconds_max": timing["seconds_max"],
            "full3d_equivalent_dof_gate_limit": 90_000,
            "ordinary_default_changed": False,
            "pde_accuracy_credit": False,
        }
    )
    context = Stage4LocalHContext(
        forest=forest,
        carrier=carrier,
        plan_path=str(resolved),
        plan_file_sha256=plan_file_sha256,
        trace_degree=trace_degree,
        cell_interior_degree=cell_interior_degree,
        cell_interior_degree_by_box=MappingProxyType(
            cell_interior_degree_by_box
        ),
        variable_trace_from_cell_degrees=(
            variable_trace_from_cell_degrees
        ),
        selected_p6_face_geometry_keys=(
            selected_p6_face_geometry_keys
        ),
        audit=audit,
    )
    axis_plan = stage4_axis_plan(cfg, comm.size)
    return AirBox3DMesh(
        mesh=carrier.mesh,
        cell_tags=carrier.cell_tags,
        facet_tags=carrier.physical_boundary_tags,
        boundary_facets=np.unique(
            np.asarray(
                carrier.physical_boundary_tags.indices,
                dtype=np.int32,
            )
        ),
        mesh_cell_type_resolved="hexahedron",
        mesh_cells_resolved=axis_plan.mesh_cells_resolved,
        z_alignment_warnings=[],
        mesh_spacing_mode_resolved="balanced_dyadic_local_h",
        mesh_axis_cell_stats=axis_plan.axis_cell_stats,
        material_plane_alignment=axis_plan.material_plane_alignment,
        local_refinement_regions=refinement_region_payload,
        local_h_context=context,
    )


def build_stage4_local_h_reduction_authority(
    context: Stage4LocalHContext,
    *,
    phase_x: complex,
    phase_y: complex,
) -> Stage4LocalHReductionAuthority:
    """Bind fixed trace and true variable interiors to physical roots."""

    reduction_started = perf_counter()
    mesh = context.carrier.mesh
    variable_trace = bool(context.variable_trace_from_cell_degrees)
    physical_started = perf_counter()
    physical = build_broken_hexa_trace_constraint_authority(
        context.forest,
        context.carrier,
        degree=(
            context.cell_interior_degree
            if variable_trace
            else context.trace_degree
        ),
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
        selected_p6_face_geometry_keys=(
            context.selected_p6_face_geometry_keys
        ),
        cell_degree_by_box=(
            context.cell_interior_degree_by_box
            if variable_trace
            else None
        ),
    )
    physical_seconds = perf_counter() - physical_started
    entity_degree_arrays_started = perf_counter()
    edge_degrees, face_degrees = (
        build_broken_hexa_entity_degree_arrays(
            context.forest,
            context.carrier,
            physical,
        )
    )
    entity_degree_arrays_seconds = (
        perf_counter() - entity_degree_arrays_started
    )
    entity_map_started = perf_counter()
    canonical_leaf = np.asarray(
        context.carrier.canonical_leaf_by_local_cell,
        dtype=np.int64,
    )
    cell_degrees = np.asarray(
        [
            context.cell_interior_degree_by_box[
                context.forest.leaves[int(leaf)].box
            ]
            for leaf in canonical_leaf
        ],
        dtype=np.int32,
    )
    entity_map = build_variable_p_global_entity_map(
        mesh,
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=cell_degrees,
    )
    entity_map_seconds = perf_counter() - entity_map_started
    cell_trace_started = perf_counter()
    constraints = build_broken_hexa_cell_trace_constraint_map(
        context.forest,
        context.carrier,
        entity_map,
        physical,
    )
    cell_trace_seconds = perf_counter() - cell_trace_started
    reduction_audit_started = perf_counter()
    boxes = cell_box_catalog(mesh)
    if set(boxes) != set(context.cell_interior_degree_by_box):
        raise RuntimeError(
            "local-h cell-interior plan differs from carrier geometry"
        )
    degree_counts = {
        f"p{degree}": sum(
            value == degree
            for value in context.cell_interior_degree_by_box.values()
        )
        for degree in (4, 5, 6)
    }
    variable_interior = len(
        set(context.cell_interior_degree_by_box.values())
    ) > 1
    cell_degree_plan_sha256 = _cell_interior_degree_sha256(
        context.cell_interior_degree_by_box
    )
    entity_degree_identity: dict[str, Any] = {
        "cell_interior_degree_plan_sha256": cell_degree_plan_sha256,
        "variable_trace_from_cell_degrees": variable_trace,
    }
    if variable_trace:
        entity_degree_identity[
            "geometry_canonical_trace_degree_sha256"
        ] = physical.audit[
            "geometry_canonical_entity_degree_sha256"
        ]
    else:
        entity_degree_identity.update(
            {
                "edge_degree": int(context.trace_degree),
                "face_degree": int(context.trace_degree),
            }
        )
    if context.selected_p6_face_geometry_keys:
        entity_degree_identity["selected_p6_face_geometry_keys"] = [
            list(key)
            for key in context.selected_p6_face_geometry_keys
        ]
    geometry_canonical_entity_degree_sha256 = _json_sha256(
        entity_degree_identity
    )
    degree_audit = MappingProxyType(
        {
            "schema_version": (
                "task035e.local-h-variable-exact-sequence-plan.v1"
                if variable_trace
                else "task035d.local-h-fixed-trace-variable-interior-plan.v1"
            ),
            "status": (
                "local_h_variable_exact_sequence_plan_closed"
                if variable_trace
                else "local_h_fixed_trace_variable_interior_plan_closed"
                if variable_interior
                else "local_h_fixed_trace_uniform_interior_plan_closed"
            ),
            "pass": True,
            "mpi_size": int(mesh.comm.size),
            "mesh_cell_box_catalog_sha256": (
                cell_box_catalog_sha256(boxes)
            ),
            "cell_count": len(boxes),
            "cell_degree_counts": degree_counts,
            "cell_degree_plan_sha256": cell_degree_plan_sha256,
            "geometry_canonical_entity_degree_sha256": (
                geometry_canonical_entity_degree_sha256
            ),
            "runtime_global_entity_degree_sha256": (
                entity_map.audit["canonical_degree_map_sha256"]
            ),
            "runtime_global_entity_id_order_partition_independent": (
                False
            ),
            "trace_degree": context.trace_degree,
            "minimum_trace_degree": context.trace_degree,
            "trace_degree_values": list(
                physical.audit["trace_degree_values"]
            ),
            "selected_p6_face_count": int(
                physical.audit["selected_p6_face_count"]
            ),
            "cell_interior_container_degree": (
                context.cell_interior_degree
            ),
            "cell_interior_degree": context.cell_interior_degree,
            "variable_cell_interior_degree": variable_interior,
            "active_rows": entity_map.active_rows,
            "active_trace_rows": entity_map.active_trace_rows,
            "inactive_p6_rows": int(
                entity_map.uniform_p6_rows - entity_map.active_rows
            ),
            "inactive_p6_trace_rows": int(
                entity_map.uniform_p6_trace_rows
                - entity_map.active_trace_rows
            ),
            "entity_degree_closure": (
                (
                    "cell-driven p4/p5/p6 edge, face, and cell-interior "
                    "degrees; incident-cell minimum followed by complete "
                    "periodic-orbit and hanging-patch fixed-point closure"
                )
                if variable_trace
                else
                (
                    "p5 edge and base face degree with whole, non-hanging "
                    "periodic-orbit p6 physical faces; geometry-bound "
                    "p5/p6 cell-interior degree with "
                    "trace_degree <= cell degree"
                )
                if context.selected_p6_face_geometry_keys
                else (
                    "uniform fixed trace degree on every physical "
                    "edge/face; geometry-bound p5/p6 cell-interior degree "
                    "with trace_degree <= cell degree"
                )
            ),
            "adaptation_cycle_scope": (
                "Task035e bidirectional p4/p5/p6 local-hp cycle"
                if variable_trace
                else "first p6-to-p5 cell-interior-only cycle"
            ),
            "local_variable_trace_implemented": bool(
                variable_trace
                or physical.audit["selected_p6_face_count"]
            ),
            "variable_trace_from_cell_degrees": variable_trace,
            "inactive_high_order_trace_rows_globally_numbered": False,
            "cell_driven_variable_trace_component_complete": (
                variable_trace and variable_interior
            ),
            "combined_hp_space_construction_complete": False,
            "compiled_cell_tensor_binding_complete": False,
            "mpi8_pde_qualification_complete": False,
            "complete_combined_hp_credit": False,
            "cell_interior_p6_modes_globally_numbered_when_inactive": (
                False
            ),
            "geometry_bound_not_global_entity_id_bound": True,
            "ordinary_default_changed": False,
        }
    )
    degree_plan = VariablePCellDegreePlan(
        cell_degree_by_box=MappingProxyType(
            dict(context.cell_interior_degree_by_box)
        ),
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=cell_degrees,
        entity_map=entity_map,
        audit=degree_audit,
    )
    hanging_slave_rows = int(
        constraints.audit.get("hanging_slave_rows", 0)
    )
    full3d_equivalent = int(
        entity_map.active_rows - hanging_slave_rows
    )
    task035e_scope = (
        context.audit["schema_version"]
        == "task035e.stage4-multilevel-local-h-mesh.v1"
    )
    advisory_dof_target = 90_000
    reduction_audit_seconds = perf_counter() - reduction_audit_started
    timing = _collective_phase_timings(
        mesh.comm,
        {
            "physical_trace_authority": physical_seconds,
            "entity_degree_array_binding": entity_degree_arrays_seconds,
            "variable_p_global_entity_map": entity_map_seconds,
            "cell_trace_expansion_authority": cell_trace_seconds,
            "degree_plan_and_resource_audit": reduction_audit_seconds,
            "local_h_reduction_total_before_audit_publish": (
                perf_counter() - reduction_started
            ),
        },
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035e.stage4-multilevel-local-hp-reduction-authority.v1"
                if variable_trace
                else "task035d.stage4-local-h-reduction-authority.v1"
            ),
            "status": "stage4_local_h_reduction_authority_pass",
            "pass": True,
            "mesh": dict(context.audit),
            "degree_plan": dict(degree_audit),
            "physical_trace": dict(physical.audit),
            "trace_constraints": dict(constraints.audit),
            "trace_constraint_setup_timing": dict(
                constraints.setup_timing
            ),
            "raw_broken_active_fe_dofs": entity_map.active_rows,
            "raw_broken_trace_rows": entity_map.active_trace_rows,
            "hanging_slave_rows": hanging_slave_rows,
            "periodic_slave_rows": int(
                constraints.audit.get("periodic_slave_rows", 0)
            ),
            "actual_full3d_equivalent_active_fe_dofs": (
                full3d_equivalent
            ),
            "independent_trace_rows": (
                constraints.independent_trace_rows
            ),
            "phase_timing_semantics": timing["semantics"],
            "phase_timings_seconds_by_rank": timing[
                "seconds_by_rank"
            ],
            "phase_timings_seconds_max": timing["seconds_max"],
            "active_fe_dof_hard_gate_active": not task035e_scope,
            "active_fe_dof_gate_limit": (
                None if task035e_scope else advisory_dof_target
            ),
            "active_fe_dof_gate_pass": (
                True
                if task035e_scope
                else full3d_equivalent <= advisory_dof_target
            ),
            "active_fe_dof_advisory_target": advisory_dof_target,
            "active_fe_dof_advisory_target_met": (
                full3d_equivalent <= advisory_dof_target
            ),
            "variable_trace_from_cell_degrees": variable_trace,
            "hanging_or_floquet_slave_rows_globally_numbered": False,
            "ordinary_default_changed": False,
        }
    )
    if not task035e_scope and full3d_equivalent > advisory_dof_target:
        raise RuntimeError(
            "Task035d local-h candidate exceeds 90,000 "
            "Full3D-equivalent DoF"
        )
    return Stage4LocalHReductionAuthority(
        degree_plan=degree_plan,
        trace_constraints=constraints,
        audit=audit,
    )


__all__ = [
    "LOCAL_H_PLAN_SCHEMA",
    "MULTILEVEL_LOCAL_H_PLAN_SCHEMA",
    "Stage4LocalHContext",
    "Stage4LocalHReductionAuthority",
    "build_stage4_local_h_mesh_data",
    "build_stage4_local_h_reduction_authority",
    "stage4_local_h_root_forest_catalog",
    "stage4_local_h_refinement_plan_payload",
    "stage4_multilevel_local_h_forest_catalog",
    "stage4_multilevel_local_h_refinement_plan_payload",
]
