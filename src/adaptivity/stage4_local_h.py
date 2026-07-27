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
            if degree not in {5, 6}
            or degree < int(trace_degree)
            or degree > int(container_degree)
        }
    )
    if invalid:
        raise ValueError(
            "the first local-h variable-interior cycle permits only "
            "p6->p5 and requires trace_degree <= degree <= p6: "
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
    return payload


def build_stage4_local_h_mesh_data(
    cfg: SimulationConfig3D,
    plan_path: str | Path,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> AirBox3DMesh:
    """Load one plan and build its audited broken-hexa carrier."""

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

    resolved = Path(plan_path).expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("schema_version") != LOCAL_H_PLAN_SCHEMA:
        raise ValueError("Stage-4 local-h plan has an unknown schema")
    if payload.get("status") != "stage4_balanced_local_h_plan":
        raise ValueError("Stage-4 local-h plan has an invalid status")
    if payload.get("periodic_axes") != ["x", "y"]:
        raise ValueError("Stage-4 local-h plan must close x/y periodicity")
    if payload.get("protect_material_interfaces") is not True:
        raise ValueError("Stage-4 local-h plan must protect material interfaces")
    if int(payload.get("maximum_level", -1)) != 1:
        raise ValueError("Stage-4 local-h plan may refine only once")

    rows = payload.get("marked_root_boxes")
    if not isinstance(rows, list):
        raise ValueError("Stage-4 local-h plan has no marked root boxes")
    marked = tuple(
        _normalized_box((*row["lower"], *row["upper"]))
        for row in rows
    )
    base = _base_config_identity(cfg, comm_size=comm.size)
    if payload.get("base_config") != base:
        raise ValueError(
            "Stage-4 local-h plan base geometry differs from the live config"
        )
    forest = _build_forest(
        cfg,
        comm_size=comm.size,
        marked_root_boxes=marked,
        maximum_level=1,
    )
    if payload.get("root_cell_box_catalog_sha256") != (
        cell_box_catalog_sha256(forest.root_boxes)
    ):
        raise ValueError("Stage-4 local-h root-box identity drifted")
    expectation = _forest_expectation(forest)
    if payload.get("expected_forest") != expectation:
        raise ValueError("Stage-4 local-h forest identity drifted")

    markers = base["boundary_tags"]
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=comm,
        boundary_markers=markers,
    )
    trace_degree = int(payload.get("trace_degree", -1))
    cell_interior_degree = int(payload.get("cell_interior_degree", -1))
    if trace_degree not in {4, 5, 6}:
        raise ValueError("Stage-4 local-h plan has an invalid trace degree")
    if cell_interior_degree != int(cfg.nedelec_degree):
        raise ValueError(
            "Stage-4 local-h interior degree differs from the p6 container"
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
    audit = MappingProxyType(
        {
            "schema_version": "task035d.stage4-local-h-mesh.v1",
            "status": "stage4_balanced_local_h_mesh_pass",
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
            "root_cell_count": len(forest.root_boxes),
            "leaf_cell_count": len(forest.leaves),
            "hanging_patch_count": len(forest.hanging_faces),
            "forest": dict(forest.audit),
            "carrier": dict(carrier.audit),
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
        local_refinement_regions={
            "marked_root_boxes": [list(box) for box in marked]
        },
        local_h_context=context,
    )


def _degree_array(mesh: Any, dimension: int, degree: int) -> np.ndarray:
    mesh.topology.create_entities(int(dimension))
    index_map = mesh.topology.index_map(int(dimension))
    return np.full(
        index_map.size_local + index_map.num_ghosts,
        int(degree),
        dtype=np.int32,
    )


def build_stage4_local_h_reduction_authority(
    context: Stage4LocalHContext,
    *,
    phase_x: complex,
    phase_y: complex,
) -> Stage4LocalHReductionAuthority:
    """Bind fixed trace and true variable interiors to physical roots."""

    mesh = context.carrier.mesh
    edge_degrees = _degree_array(mesh, 1, context.trace_degree)
    face_degrees = _degree_array(mesh, 2, context.trace_degree)
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
    physical = build_broken_hexa_trace_constraint_authority(
        context.forest,
        context.carrier,
        degree=context.trace_degree,
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        context.forest,
        context.carrier,
        entity_map,
        physical,
    )
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
    geometry_canonical_entity_degree_sha256 = _json_sha256(
        {
            "edge_degree": int(context.trace_degree),
            "face_degree": int(context.trace_degree),
            "cell_interior_degree_plan_sha256": (
                cell_degree_plan_sha256
            ),
        }
    )
    degree_audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.local-h-fixed-trace-variable-interior-plan.v1"
            ),
            "status": (
                "local_h_fixed_trace_variable_interior_plan_closed"
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
                "uniform fixed trace degree on every physical edge/face; "
                "geometry-bound p5/p6 cell-interior degree with "
                "trace_degree <= cell degree"
            ),
            "adaptation_cycle_scope": (
                "first p6-to-p5 cell-interior-only cycle"
            ),
            "local_variable_trace_implemented": False,
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
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035d.stage4-local-h-reduction-authority.v1"
            ),
            "status": "stage4_local_h_reduction_authority_pass",
            "pass": True,
            "mesh": dict(context.audit),
            "degree_plan": dict(degree_audit),
            "physical_trace": dict(physical.audit),
            "trace_constraints": dict(constraints.audit),
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
            "active_fe_dof_gate_limit": 90_000,
            "active_fe_dof_gate_pass": full3d_equivalent <= 90_000,
            "hanging_or_floquet_slave_rows_globally_numbered": False,
            "ordinary_default_changed": False,
        }
    )
    if full3d_equivalent > 90_000:
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
    "Stage4LocalHContext",
    "Stage4LocalHReductionAuthority",
    "build_stage4_local_h_mesh_data",
    "build_stage4_local_h_reduction_authority",
    "stage4_local_h_refinement_plan_payload",
]
