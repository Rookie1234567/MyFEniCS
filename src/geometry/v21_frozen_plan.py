"""Hash-bound geometry/axis identities for the Review V21 batch.

The large historical canonical cell listing stays in the compact Z0 evidence
record.  Public V21 inputs carry the small explicit axis arrays and this
module verifies that they are the arrays from that record before the mesh
builder is called.  It is deliberately a validator, not a mesh generator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


PLAN_RELATIVE_PATH = Path(
    "docs/task039_extra_physical_multilevel/outcomes/records/"
    "v21_frozen_geometry_mesh_plan.json"
)
PLAN_SHA256 = "b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157"
PLAN_ID = "task039extra.v21.frozen-geometry-mesh-plan.v1"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def geometry_entity_payload(
    geometry: Mapping[str, Any], plan: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return the stage-independent semantic identity of the geometry entity.

    ``geometry_identity`` is a case/stage label (h10 versus h7.5), so it is
    intentionally excluded.  Mesh axes and the frozen plan binding belong to
    the separate discretization/mesh identities.  The frozen-notch geometry
    digest is included as geometric content, not as the plan file digest; this
    keeps A and C equal while keeping the original B entity distinct.
    """

    payload = {
        str(key): value
        for key, value in geometry.items()
        if str(key) != "geometry_identity"
    }
    if payload.get("model_variant") == "frozen_notch":
        if plan is None:
            plan, _ = load_frozen_plan()
        payload["frozen_notch_geometry_semantic_sha256"] = plan[
            "frozen_notch_geometry"
        ]["geometry_semantic_sha256"]
    return payload


def geometry_entity_sha256(
    geometry: Mapping[str, Any], plan: Mapping[str, Any] | None = None
) -> str:
    return hashlib.sha256(_canonical_json_bytes(geometry_entity_payload(geometry, plan))).hexdigest()


def _repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "src").is_dir() and (candidate / "input").is_dir():
            return candidate
    raise RuntimeError("cannot locate repository root for the V21 geometry plan")


def load_frozen_plan(root: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and hash-check the compact frozen Z0 plan."""

    repository_root = _repo_root() if root is None else Path(root).resolve()
    path = repository_root / PLAN_RELATIVE_PATH
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PLAN_SHA256:
        raise ValueError(
            f"V21 frozen geometry plan hash changed: {actual} != {PLAN_SHA256}"
        )
    plan = json.loads(payload.decode("utf-8"))
    if plan.get("schema") != "task039extra.v21.frozen-geometry-mesh-plan.v1":
        raise ValueError("V21 frozen geometry plan schema changed")
    return plan, {"path": str(path), "sha256": actual, "bytes": len(payload)}


def _same_axis(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, (list, tuple)) or not isinstance(expected, (list, tuple)):
        return False
    # Axis coordinates are part of the hash-bound mesh identity.  A caller
    # that changes even one binary64 value must not silently enter the frozen
    # plan; geometric midpoint tests below use a separate coordinate
    # tolerance where that is physically appropriate.
    return len(actual) == len(expected) and all(
        float(left) == float(right)
        for left, right in zip(actual, expected, strict=True)
    )


def _frozen_union(plan: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    geometry = plan["frozen_notch_geometry"]
    boxes = geometry["canonical_cell_boxes"]
    proof = geometry.get("exact_merge_proof", {})
    if float(proof.get("symmetric_difference_volume_nm3", 1.0)) > 1.0e-9:
        raise ValueError("V21 frozen notch canonical boxes are not merge-equivalent")
    if int(proof.get("coverage_multiplicity", 0)) != 1:
        raise ValueError("V21 frozen notch boxes overlap or leave a coverage gap")
    lower = np.asarray(geometry["merged_boxes"][0]["lower"], dtype=np.float64)
    upper = np.asarray(geometry["merged_boxes"][0]["upper"], dtype=np.float64)
    elementary_volume = sum(
        float(np.prod(np.asarray(box["upper"], dtype=np.float64)
                     - np.asarray(box["lower"], dtype=np.float64)))
        for box in boxes
    )
    merged_volume = float(np.prod(upper - lower))
    if not np.isclose(elementary_volume, merged_volume, rtol=0.0, atol=1.0e-9):
        raise ValueError("V21 frozen notch union volume does not match its merged box")
    return lower, upper


def _fully_contained_cells(
    cell_vertices: Any, plan: Mapping[str, Any]
) -> np.ndarray:
    """Classify cells by exact box intersection, rejecting partial overlap."""

    vertices = np.asarray(cell_vertices, dtype=np.float64)
    if vertices.ndim != 3 or vertices.shape[2] != 3:
        raise ValueError("V21 frozen-notch cell vertices must have shape (N, V, 3)")
    if vertices.shape[1] < 4:
        raise ValueError("V21 frozen-notch cells need at least four vertices")
    lower, upper = _frozen_union(plan)
    cell_lower = np.min(vertices, axis=1)
    cell_upper = np.max(vertices, axis=1)
    widths = cell_upper - cell_lower
    if np.any(widths <= 0.0):
        raise ValueError("V21 frozen-notch mesh contains a degenerate cell")
    cell_volume = np.prod(widths, axis=1)
    intersection_width = np.maximum(
        0.0, np.minimum(cell_upper, upper) - np.maximum(cell_lower, lower)
    )
    intersection_volume = np.prod(intersection_width, axis=1)
    volume_tol = np.maximum(cell_volume, 1.0) * 1.0e-12
    partial = (intersection_volume > volume_tol) & (
        np.abs(intersection_volume - cell_volume) > volume_tol
    )
    if np.any(partial):
        first = int(np.flatnonzero(partial)[0])
        raise ValueError(
            "V21 frozen notch partially intersects a cell; "
            f"cell={first}, intersection={intersection_volume[first]}, "
            f"cell_volume={cell_volume[first]}"
        )
    return np.abs(intersection_volume - cell_volume) <= volume_tol


def _validate_union_bounds(plan: Mapping[str, Any], cfg: Any) -> None:
    lower, upper = _frozen_union(plan)
    domain_lower = np.asarray(
        (cfg.grating_x_min, cfg.grating_y_min, cfg.grating_z_min),
        dtype=np.float64,
    )
    domain_upper = np.asarray(
        (cfg.grating_x_max, cfg.grating_y_max, cfg.grating_z_max),
        dtype=np.float64,
    )
    tol = 1.0e-10
    if np.any(lower < domain_lower - tol) or np.any(upper > domain_upper + tol):
        raise ValueError("V21 frozen-notch union lies outside the grating block")
    if np.any(lower < np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min)) - tol):
        raise ValueError("V21 frozen-notch union lies outside the mesh domain")
    if np.any(upper > np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max)) + tol):
        raise ValueError("V21 frozen-notch union lies outside the mesh domain")


def apply_v21_frozen_notch(
    midpoints: Any, tags: Any, cfg: Any, *, cell_vertices: Any
) -> np.ndarray:
    """Apply the hash-bound V21 cell-box edit to already-tagged cells.

    This is intentionally separate from the historical midpoint recipe in
    ``cell_notch.py``.  V21's notch is the frozen union of canonical cell
    boxes, so the actual mesh colouring cannot accidentally fall back to the
    old selector.
    """

    del midpoints
    plan, _binding = load_frozen_plan()
    _validate_union_bounds(plan, cfg)
    result = np.array(tags, copy=True)
    selected = _fully_contained_cells(cell_vertices, plan)
    if np.any(result[selected] != cfg.tags.grating):
        raise ValueError(
            "V21 frozen-notch union contains a cell that is not grating material"
        )
    result[selected] = cfg.tags.air
    return result


def audit_v21_frozen_notch(mesh_data: Any, cfg: Any) -> dict[str, Any]:
    """Audit the actual V21 cell tags against the frozen box union."""

    from dolfinx import mesh

    msh = mesh_data.mesh
    cells = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, msh.topology.dim, cells)
    geometry_dofmap = np.asarray(msh.geometry.dofmap, dtype=np.int64)
    cell_vertices = msh.geometry.x[geometry_dofmap[cells]]
    tags = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    plan, binding = load_frozen_plan()
    _validate_union_bounds(plan, cfg)
    changed = _fully_contained_cells(cell_vertices, plan)
    if np.any(tags[changed] != cfg.tags.air):
        raise ValueError("V21 frozen-notch cells are not tagged as air")
    grating_block = (
        (centers[:, 0] >= cfg.grating_x_min)
        & (centers[:, 0] <= cfg.grating_x_max)
        & (centers[:, 1] >= cfg.grating_y_min)
        & (centers[:, 1] <= cfg.grating_y_max)
        & (centers[:, 2] >= cfg.grating_z_min)
        & (centers[:, 2] <= cfg.grating_z_max)
    )

    def varies(axis: int) -> bool:
        groups: dict[tuple[float, ...], set[int]] = {}
        for point, tag in zip(
            centers[grating_block], tags[grating_block], strict=True
        ):
            key = tuple(np.round(np.delete(point, axis), 10))
            groups.setdefault(key, set()).add(int(tag))
        return any(len(values) > 1 for values in groups.values())

    y_nonseparable = varies(1)
    z_nonseparable = varies(2)
    if not (y_nonseparable and z_nonseparable):
        raise ValueError("V21 frozen notch does not vary in both y and z")
    rows = []
    for cell, center, tag, edited, vertices in zip(
        cells, centers, tags, changed, cell_vertices, strict=True
    ):
        rows.append(
            {
                "cell": int(cell),
                "center": np.asarray(center, dtype=float).tolist(),
                "tag": int(tag),
                "changed": bool(edited),
                "vertices": sorted(
                    np.asarray(vertices, dtype=float).tolist()
                ),
            }
        )
    rows.sort(key=lambda row: row["cell"])
    canonical_rows = sorted(
        [
            {
                "vertices": row["vertices"],
                "center": row["center"],
                "tag": row["tag"],
                "changed": row["changed"],
            }
            for row in rows
        ],
        key=lambda row: row["vertices"],
    )
    canonical_material_sha256 = hashlib.sha256(
        json.dumps(canonical_rows, sort_keys=True).encode()
    ).hexdigest()
    requested_counts = getattr(cfg, "mesh_axis_cell_counts_requested", None)
    a_counts = tuple(int(value) for value in plan["A"]["axis_cells"])
    a_canonical_match = requested_counts is not None and tuple(
        int(value) for value in requested_counts
    ) == a_counts
    if a_canonical_match and canonical_material_sha256 != plan[
        "frozen_notch_geometry"
    ]["canonical_material_sha256"]:
        raise ValueError("V21 h10 notch material layout differs from the frozen A witness")
    return {
        "recipe": "frozen_notch_geometry.canonical_cell_boxes",
        "changed_cells": int(np.count_nonzero(changed)),
        "plan": binding,
        "geometry_semantic_sha256": geometry_entity_sha256(
            {
                "geometry_kind": getattr(
                    cfg, "geometry_kind", "rectangular_block_grating"
                ),
                "model_variant": "frozen_notch",
                "cell_notch": cfg.cell_notch,
                "period_x_nm": cfg.period_x,
                "period_y_nm": cfg.period_y,
                "z_min_nm": cfg.z_min,
                "z_max_nm": cfg.z_max,
                "interface_z_nm": cfg.interface_z,
                "air_height_nm": cfg.air_height,
                "substrate_thickness_nm": cfg.substrate_thickness,
                "grating_width_x_nm": cfg.grating_width_x,
                "grating_width_y_nm": cfg.grating_width_y,
                "grating_height_nm": cfg.grating_height,
            },
            plan,
        ),
        "canonical_cells": rows,
        "canonical_material_sha256": canonical_material_sha256,
        "y_nonseparable": y_nonseparable,
        "z_nonseparable": z_nonseparable,
        "old_cells_match_reference_witness": bool(
            a_canonical_match
            and canonical_material_sha256
            == plan["frozen_notch_geometry"]["canonical_material_sha256"]
        ),
    }


def audit_v21_mesh_identity(
    mesh_data: Any,
    cfg: Any,
    *,
    geometry_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the actual V21 mesh, material tags, entity, and notch branch.

    The notch audit is deliberately called from the formal worker for frozen
    stages.  The original stage uses the same candidate-cell geometry test to
    prove that those cells remained grating material, so the worker cannot
    silently switch between the original and edited colouring recipes.
    """

    from dolfinx import mesh

    msh = mesh_data.mesh
    tdim = int(msh.topology.dim)
    cells = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
    tags = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    if cells.ndim != 1 or tags.shape != cells.shape:
        raise ValueError("V21 mesh audit has inconsistent owned cell tags")
    if len(np.unique(cells)) != len(cells):
        raise ValueError("V21 mesh audit has duplicate owned cell tags")
    geometry_dofmap = np.asarray(msh.geometry.dofmap, dtype=np.int64)
    cell_vertices = msh.geometry.x[geometry_dofmap[cells]]
    centers = mesh.compute_midpoints(msh, tdim, cells)
    plan, binding = load_frozen_plan()
    _validate_union_bounds(plan, cfg)
    notch_candidates = _fully_contained_cells(cell_vertices, plan)
    variant = str(getattr(cfg, "geometry_model_variant", ""))
    if variant == "frozen_notch":
        notch = audit_v21_frozen_notch(mesh_data, cfg)
        if np.any(tags[notch_candidates] != cfg.tags.air):
            raise ValueError("V21 frozen-notch candidate cells are not all air")
    elif variant == "original":
        if getattr(cfg, "cell_notch", None) not in (None, ""):
            raise ValueError("V21 original mesh carries a notch recipe")
        if np.any(tags[notch_candidates] != cfg.tags.grating):
            raise ValueError("V21 original mesh changed a frozen-notch candidate cell")
        notch = {
            "recipe": "frozen_notch_candidate_cells_untouched",
            "changed_cells": 0,
            "candidate_cells": int(np.count_nonzero(notch_candidates)),
            "plan": binding,
        }
    else:
        raise ValueError(f"unsupported V21 mesh geometry variant: {variant}")

    # Reconstruct the pre-notch material rule for every owned cell.  This
    # catches an accidental tag change outside the selected frozen union,
    # which a selected-cell-only check would not see.
    baseline_tags = np.full(len(cells), cfg.tags.air, dtype=np.int32)
    z = centers[:, 2]
    tol = 1.0e-10 * max(abs(cfg.domain_z_max - cfg.domain_z_min), 1.0)
    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        baseline_tags[z < cfg.physical_z_min - tol] = cfg.tags.bottom_pml
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        baseline_tags[z > cfg.physical_z_max + tol] = cfg.tags.top_pml
    if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}:
        physical = (z >= cfg.physical_z_min - tol) & (
            z <= cfg.physical_z_max + tol
        )
        baseline_tags[physical & (z < cfg.interface_z)] = cfg.tags.substrate
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        x = centers[:, 0]
        y = centers[:, 1]
        physical = (z >= cfg.physical_z_min - tol) & (
            z <= cfg.physical_z_max + tol
        )
        in_block = (
            physical
            & (x >= cfg.grating_x_min - tol)
            & (x <= cfg.grating_x_max + tol)
            & (y >= cfg.grating_y_min - tol)
            & (y <= cfg.grating_y_max + tol)
            & (z >= cfg.grating_z_min - tol)
            & (z <= cfg.grating_z_max + tol)
        )
        baseline_tags[in_block] = cfg.tags.grating
    expected_tags = baseline_tags.copy()
    if variant == "frozen_notch":
        expected_tags[notch_candidates] = cfg.tags.air
    tag_mismatch = np.flatnonzero(tags != expected_tags)
    if tag_mismatch.size:
        raise ValueError(
            "V21 mesh material tags differ outside the reviewed geometry rule: "
            f"{tag_mismatch[:8].tolist()}"
        )

    frozen_lower, frozen_upper = _frozen_union(plan)
    selected_vertices = cell_vertices[notch_candidates]
    selected_lower = (
        np.min(selected_vertices, axis=(0, 1))
        if selected_vertices.size
        else np.full(3, np.nan)
    )
    selected_upper = (
        np.max(selected_vertices, axis=(0, 1))
        if selected_vertices.size
        else np.full(3, np.nan)
    )
    selected_lowers = (
        np.min(selected_vertices, axis=1)
        if selected_vertices.size
        else np.empty((0, 3))
    )
    selected_uppers = (
        np.max(selected_vertices, axis=1)
        if selected_vertices.size
        else np.empty((0, 3))
    )
    selected_volumes = (
        np.prod(selected_uppers - selected_lowers, axis=1)
        if selected_vertices.size
        else np.empty(0)
    )
    intersections = np.maximum(
        0.0,
        np.minimum(selected_uppers, frozen_upper)
        - np.maximum(selected_lowers, frozen_lower),
    )
    intersection_volumes = (
        np.prod(intersections, axis=1) if selected_vertices.size else np.empty(0)
    )
    expected_volume = float(np.prod(frozen_upper - frozen_lower))
    selected_volume = float(np.sum(selected_volumes))
    intersection_volume = float(np.sum(intersection_volumes))
    symmetric_difference_volume = float(
        abs(expected_volume + selected_volume - 2.0 * intersection_volume)
    )
    if variant == "frozen_notch" and symmetric_difference_volume > 1.0e-9:
        raise ValueError(
            "V21 frozen-notch selected-cell union differs from the frozen volume: "
            f"{symmetric_difference_volume} nm^3"
        )
    boundary_faces = {
        f"axis_{axis}_{side}": int(
            np.count_nonzero(
                np.isclose(
                    selected_lowers[:, axis] if side == "min" else selected_uppers[:, axis],
                    frozen_lower[axis] if side == "min" else frozen_upper[axis],
                    rtol=0.0,
                    atol=1.0e-10,
                )
            )
        )
        for axis, axis_name in enumerate(("x", "y", "z"))
        for side in ("min", "max")
    }
    boundary_complete = all(value > 0 for value in boundary_faces.values())
    if variant == "frozen_notch" and not boundary_complete:
        raise ValueError("V21 frozen-notch union does not touch every frozen boundary face")

    rows = []
    for cell, center, tag, candidate, vertices in zip(
        cells, centers, tags, notch_candidates, cell_vertices, strict=True
    ):
        rows.append(
            {
                "vertices": sorted(np.asarray(vertices, dtype=float).tolist()),
                "center": np.asarray(center, dtype=float).tolist(),
                "tag": int(tag),
                "notch_candidate": bool(candidate),
            }
        )
    rows.sort(key=lambda row: (row["vertices"], row["center"], row["tag"]))
    material_sha256 = hashlib.sha256(_canonical_json_bytes(rows)).hexdigest()
    coordinate_sha256 = hashlib.sha256(
        np.ascontiguousarray(np.asarray(msh.geometry.x, dtype=np.float64)).tobytes()
    ).hexdigest()
    axis_counts = tuple(
        int(np.unique(np.asarray(msh.geometry.x[:, axis], dtype=np.float64)).size - 1)
        for axis in range(3)
    )
    requested_counts = tuple(
        int(value) for value in getattr(cfg, "mesh_axis_cell_counts_requested", ()) or ()
    )
    if requested_counts and axis_counts != requested_counts:
        raise ValueError(
            f"V21 actual mesh axis counts differ: {axis_counts} != {requested_counts}"
        )
    tag_values, tag_counts = np.unique(tags, return_counts=True)
    payload = dict(geometry_payload or {})
    if not payload:
        payload = {
            "geometry_kind": getattr(cfg, "geometry_kind", None),
            "model_variant": variant,
            "geometry_identity": getattr(cfg, "geometry_identity", None),
            "cell_notch": getattr(cfg, "cell_notch", None),
            "period_x_nm": getattr(cfg, "period_x", None),
            "period_y_nm": getattr(cfg, "period_y", None),
            "z_min_nm": getattr(cfg, "z_min", None),
            "z_max_nm": getattr(cfg, "z_max", None),
            "interface_z_nm": getattr(cfg, "interface_z", None),
            "air_height_nm": getattr(cfg, "air_height", None),
            "substrate_thickness_nm": getattr(cfg, "substrate_thickness", None),
            "grating_width_x_nm": getattr(cfg, "grating_width_x", None),
            "grating_width_y_nm": getattr(cfg, "grating_width_y", None),
            "grating_height_nm": getattr(cfg, "grating_height", None),
        }
    return {
        "schema": "task039extra.v21.actual-mesh-material-entity-audit.v1",
        "variant": variant,
        "geometry_identity": getattr(cfg, "geometry_identity", None),
        "plan": binding,
        "actual_axis_cell_counts": list(axis_counts),
        "requested_axis_cell_counts": list(requested_counts),
        "owned_cell_count": int(len(cells)),
        "geometry_coordinate_sha256": coordinate_sha256,
        "material_layout_sha256": material_sha256,
        "material_tag_counts": {
            str(int(tag)): int(count) for tag, count in zip(tag_values, tag_counts, strict=True)
        },
        "notch_candidate_count": int(np.count_nonzero(notch_candidates)),
        "notch": notch,
        "expected_union_volume_nm3": expected_volume,
        "selected_union_volume_nm3": selected_volume,
        "intersection_volume_nm3": intersection_volume,
        "symmetric_difference_volume_nm3": symmetric_difference_volume,
        "selected_union_lower": selected_lower.tolist(),
        "selected_union_upper": selected_upper.tolist(),
        "frozen_union_lower": frozen_lower.tolist(),
        "frozen_union_upper": frozen_upper.tolist(),
        "boundary_face_counts": boundary_faces,
        "boundary_complete": boundary_complete,
        "material_baseline_consistent": bool(tag_mismatch.size == 0),
        "material_mismatch_cells": [int(value) for value in tag_mismatch[:16]],
        "geometry_entity_sha256": geometry_entity_sha256(payload, plan),
        "geometry_entity_payload": geometry_entity_payload(payload, plan),
        "cell_rows": rows,
    }


def validate_v21_input(
    stage: str,
    geometry: Mapping[str, Any],
    discretization: Mapping[str, Any],
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one V21 input against the frozen A or B/C plan entry."""

    stage = str(stage)
    plan, binding = load_frozen_plan(root)
    if stage == "Z2_NOTCH_H10":
        entry = plan["A"]
        expected_variant = "frozen_notch"
        expected_identity = "v21_frozen_notch_h10"
        expected_notch = "positive_x_middle_y_z40_80"
    elif stage == "Z3_ORIGINAL_H7P5":
        entry = plan["BC"]
        expected_variant = "original"
        expected_identity = "v21_original_h7p5"
        expected_notch = None
    elif stage == "Z4_NOTCH_H7P5":
        entry = plan["BC"]
        expected_variant = "frozen_notch"
        expected_identity = "v21_frozen_notch_h7p5"
        expected_notch = "positive_x_middle_y_z40_80"
    else:
        raise ValueError(f"unsupported V21 geometry stage: {stage}")

    if discretization.get("mesh_plan_id") != PLAN_ID:
        raise ValueError("V21 input mesh_plan_id does not identify the frozen plan")
    if discretization.get("mesh_plan_sha256") != PLAN_SHA256:
        raise ValueError("V21 input mesh_plan_sha256 does not bind the frozen plan")
    if geometry.get("model_variant") != expected_variant:
        raise ValueError(
            f"{stage} requires geometry.model_variant={expected_variant!r}"
        )
    if geometry.get("geometry_identity") != expected_identity:
        raise ValueError(
            f"{stage} requires geometry.geometry_identity={expected_identity!r}"
        )
    if geometry.get("cell_notch") != expected_notch:
        raise ValueError(
            f"{stage} has an inconsistent explicit cell_notch/model_variant pair"
        )

    axes = entry["axes_nm"]
    actual_axes = {
        "x": discretization.get("mesh_axis_x_values"),
        "y": discretization.get("mesh_axis_y_values"),
        "z": discretization.get("mesh_axis_z_values"),
    }
    for axis_name, expected in axes.items():
        if not _same_axis(actual_axes[axis_name], expected):
            raise ValueError(f"{stage} explicit {axis_name} axis differs from frozen plan")
    expected_counts = tuple(int(value) for value in entry["axis_cells"])
    actual_counts = discretization.get("mesh_axis_cell_counts")
    if tuple(actual_counts or ()) != expected_counts:
        raise ValueError(f"{stage} explicit axis cell counts differ from frozen plan")
    for axis_name, values in actual_axes.items():
        if len(values) != expected_counts["xyz".index(axis_name)] + 1:
            raise ValueError(f"{stage} {axis_name} axis length disagrees with its cell count")

    return {
        "stage": stage,
        "plan": binding,
        "plan_id": PLAN_ID,
        "plan_sha256": PLAN_SHA256,
        "model_variant": expected_variant,
        "geometry_identity": expected_identity,
        "axis_cell_counts": list(expected_counts),
        "authority": entry.get("authority"),
        "reference_root": entry.get("reference_root"),
        "geometry_semantic_sha256": geometry_entity_sha256(geometry, plan),
        "frozen_notch_geometry_semantic_sha256": plan["frozen_notch_geometry"][
            "geometry_semantic_sha256"
        ],
        "axis_plan_sha256": entry.get("axis_plan_sha256"),
    }


__all__ = [
    "PLAN_ID",
    "PLAN_RELATIVE_PATH",
    "PLAN_SHA256",
    "apply_v21_frozen_notch",
    "audit_v21_frozen_notch",
    "audit_v21_mesh_identity",
    "geometry_entity_payload",
    "geometry_entity_sha256",
    "load_frozen_plan",
    "validate_v21_input",
]
