"""Deterministic geometry-only initial spaces for the two Task035e paths.

The planner consumes only the fixed grating configuration, wavelength,
material tags, port locations, MPI width, and clean source identity.  It
selects two separated corner/port patches, performs one real balanced dyadic
stage, and closes a complete p4/p5 cell map.  No solved field, goal value, DWR
value, or externally supplied error map is accepted by this API.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import string
from types import MappingProxyType
from typing import Any, Mapping

from src.common.config_3d import (
    EUV_REFERENCE_WAVELENGTH_NM,
    SimulationConfig3D,
)

from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    Box,
    DyadicHexKey,
)
from .stage4_local_h import (
    stage4_local_h_root_forest_catalog,
    stage4_multilevel_local_h_forest_catalog,
    stage4_multilevel_local_h_refinement_plan_payload,
)
from .task035e_hp_transition import build_initial_hp_transition_state


INITIAL_SPACE_SCHEMA = "task035e.blind-initial-space-plan.v1"
INITIAL_SPACE_ALGORITHM_ID = (
    "task035e.geometry-wave-stability-initial-space.v1"
)
_PATH_H_NM = MappingProxyType({"A": 20.0, "B": 15.0})
_STABILITY_AXIS_WAVELENGTH_LIMIT = 1.5
_ALGORITHM_CONTRACT = {
    "algorithm_id": INITIAL_SPACE_ALGORITHM_ID,
    "paths": {"A": 20.0, "B": 15.0},
    "wavelength_nm": EUV_REFERENCE_WAVELENGTH_NM,
    "mpi_size": 8,
    "patch_rules": [
        "top-port cell outside and adjacent to the left grating side",
        "bottom-port cell outside and adjacent to the right grating side",
    ],
    "patch_y_sides": ["lower", "upper"],
    "refinement_stage_count": 1,
    "maximum_available_dyadic_level": 2,
    "default_degree": 4,
    "guard_degree": 5,
    "container_degree": 6,
    "guard_rules": [
        "cell touches either physical z port",
        "cell shares a positive-area face with a different material tag",
        "maximum optical axis span exceeds 1.5 wavelengths",
    ],
    "variable_trace_from_cell_degrees": True,
    "ordinary_default_changed": False,
}


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


INITIAL_SPACE_ALGORITHM_SHA256 = _json_sha256(_ALGORITHM_CONTRACT)


def _require_source_sha(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in {40, 64}
        or any(character not in string.hexdigits for character in value)
    ):
        raise ValueError("source_sha must be a 40/64-character hex digest")
    return value.lower()


def _same(left: float, right: float, *, scale: float) -> bool:
    return math.isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=max(float(scale), 1.0) * 1.0e-11,
    )


def _positive_overlap(
    left: tuple[float, float],
    right: tuple[float, float],
    *,
    tolerance: float,
) -> bool:
    return (
        min(left[1], right[1]) - max(left[0], right[0])
        > tolerance
    )


def _share_positive_area_face(
    left: Box,
    right: Box,
    *,
    tolerance: float,
) -> bool:
    for axis in range(3):
        if not (
            _same(
                left[axis + 3],
                right[axis],
                scale=tolerance / 1.0e-11,
            )
            or _same(
                right[axis + 3],
                left[axis],
                scale=tolerance / 1.0e-11,
            )
        ):
            continue
        tangential = tuple(index for index in range(3) if index != axis)
        if all(
            _positive_overlap(
                (
                    left[candidate],
                    left[candidate + 3],
                ),
                (
                    right[candidate],
                    right[candidate + 3],
                ),
                tolerance=tolerance,
            )
            for candidate in tangential
        ):
            return True
    return False


def _validate_scope(
    cfg: SimulationConfig3D,
    *,
    path_id: str,
    comm_size: int,
) -> float:
    if path_id not in _PATH_H_NM:
        raise ValueError("path_id must be A or B")
    nominal_h_nm = float(_PATH_H_NM[path_id])
    if int(comm_size) != 8:
        raise ValueError("formal Task035e initial spaces are MPI8-bound")
    if (
        cfg.stage_case != "stage4_block_grating"
        or cfg.geometry_kind != "rectangular_block_grating"
        or not cfg.has_grating_block
    ):
        raise ValueError("initial planner requires the fixed block grating")
    if (
        not cfg.use_floquet_xy
        or cfg.stage4_boundary_model != "dtn_port"
        or cfg.use_pml
    ):
        raise ValueError("initial planner requires Floquet x/y and DtN ports")
    if int(cfg.nedelec_degree) != 6:
        raise ValueError("initial planner requires the p6 container")
    if not _same(
        cfg.mesh_target_size,
        nominal_h_nm,
        scale=nominal_h_nm,
    ):
        raise ValueError(
            f"Path {path_id} requires nominal h={nominal_h_nm:g} nm"
        )
    if not _same(
        cfg.lambda0,
        EUV_REFERENCE_WAVELENGTH_NM,
        scale=EUV_REFERENCE_WAVELENGTH_NM,
    ):
        raise ValueError("initial planner requires the fixed 13.5 nm wave")
    return nominal_h_nm


def _unique_root(
    forest: BalancedDyadicHexForest,
    predicate,
    *,
    label: str,
) -> Box:
    matches = tuple(cell.box for cell in forest.leaves if predicate(cell.box))
    if len(matches) != 1:
        raise RuntimeError(
            f"{label} patch rule selected {len(matches)} root cells"
        )
    return matches[0]


def _initial_patch_boxes(
    cfg: SimulationConfig3D,
    root_forest: BalancedDyadicHexForest,
) -> tuple[Box, Box]:
    bounds = root_forest.domain_bounds
    extent = max(
        bounds[axis + 3] - bounds[axis] for axis in range(3)
    )

    left_top = _unique_root(
        root_forest,
        lambda box: (
            _same(box[3], cfg.grating_x_min, scale=extent)
            and _same(box[1], bounds[1], scale=extent)
            and _same(box[2], cfg.grating_z_max, scale=extent)
            and _same(box[5], bounds[5], scale=extent)
        ),
        label="left-top",
    )
    right_bottom = _unique_root(
        root_forest,
        lambda box: (
            _same(box[0], cfg.grating_x_max, scale=extent)
            and _same(box[4], bounds[4], scale=extent)
            and _same(box[2], bounds[2], scale=extent)
            and _same(box[5], cfg.interface_z, scale=extent)
        ),
        label="right-bottom",
    )
    return left_top, right_bottom


def _material_index_abs(
    cfg: SimulationConfig3D,
    material_tag: int,
) -> float:
    if int(material_tag) == int(cfg.tags.air):
        value = cfg.n_air
    elif int(material_tag) == int(cfg.tags.substrate):
        value = cfg.n_substrate
    elif int(material_tag) == int(cfg.tags.grating):
        value = cfg.n_grating
    else:
        raise RuntimeError(f"unexpected material tag: {material_tag}")
    if value is None:
        raise RuntimeError("active material has no refractive index")
    return float(abs(complex(value)))


def _cell_guard_reasons(
    cfg: SimulationConfig3D,
    forest: BalancedDyadicHexForest,
) -> dict[DyadicHexKey, set[str]]:
    bounds = forest.domain_bounds
    extent = max(
        bounds[axis + 3] - bounds[axis] for axis in range(3)
    )
    tolerance = max(extent, 1.0) * 1.0e-11
    reasons: dict[DyadicHexKey, set[str]] = {
        cell.key: set() for cell in forest.leaves
    }
    for cell in forest.leaves:
        if (
            _same(cell.box[2], bounds[2], scale=extent)
            or _same(cell.box[5], bounds[5], scale=extent)
        ):
            reasons[cell.key].add("physical_z_port")
        maximum_axis_span = max(
            cell.box[axis + 3] - cell.box[axis] for axis in range(3)
        )
        optical_axis_wavelengths = (
            maximum_axis_span
            * _material_index_abs(cfg, cell.material_tag)
            / float(cfg.lambda0)
        )
        if (
            optical_axis_wavelengths
            > _STABILITY_AXIS_WAVELENGTH_LIMIT
        ):
            reasons[cell.key].add("wavenumber_stability")

    leaves = tuple(forest.leaves)
    for left_index, left in enumerate(leaves):
        for right in leaves[left_index + 1 :]:
            if (
                left.material_tag != right.material_tag
                and _share_positive_area_face(
                    left.box,
                    right.box,
                    tolerance=tolerance,
                )
            ):
                reasons[left.key].add("material_interface")
                reasons[right.key].add("material_interface")
    return reasons


def _config_identity(
    cfg: SimulationConfig3D,
    root_forest: BalancedDyadicHexForest,
    *,
    path_id: str,
    nominal_h_nm: float,
    comm_size: int,
) -> dict[str, Any]:
    return {
        "path_id": path_id,
        "nominal_h_nm": nominal_h_nm,
        "lambda0_nm": float(cfg.lambda0),
        "comm_size": int(comm_size),
        "stage_case": cfg.stage_case,
        "geometry_kind": cfg.geometry_kind,
        "periods_nm": [float(cfg.period_x), float(cfg.period_y)],
        "domain_bounds_nm": list(root_forest.domain_bounds),
        "interface_z_nm": float(cfg.interface_z),
        "grating_bounds_nm": [
            float(cfg.grating_x_min),
            float(cfg.grating_y_min),
            float(cfg.grating_z_min),
            float(cfg.grating_x_max),
            float(cfg.grating_y_max),
            float(cfg.grating_z_max),
        ],
        "material_indices": {
            "air": [float(cfg.n_air.real), float(cfg.n_air.imag)],
            "substrate": [
                float(complex(cfg.n_substrate).real),
                float(complex(cfg.n_substrate).imag),
            ],
            "grating": [
                float(complex(cfg.n_grating).real),
                float(complex(cfg.n_grating).imag),
            ],
        },
        "root_catalog_sha256": root_forest.audit[
            "leaf_catalog_sha256"
        ],
    }


@dataclass(frozen=True, slots=True)
class Task035eInitialSpacePlan:
    """One immutable initial topology/degree component authority."""

    path_id: str
    forest: BalancedDyadicHexForest
    cell_degree_by_key: Mapping[DyadicHexKey, int]
    canonical_plan_json: str
    audit: Mapping[str, Any]

    def plan_payload(self) -> dict[str, Any]:
        """Return an independent JSON-ready copy of the Stage-4 plan."""

        payload = json.loads(self.canonical_plan_json)
        if not isinstance(payload, dict):
            raise RuntimeError("canonical initial-space plan is not an object")
        return payload


def build_task035e_initial_space_plan(
    cfg: SimulationConfig3D,
    *,
    path_id: str,
    source_sha: str,
    comm_size: int = 8,
) -> Task035eInitialSpacePlan:
    """Build one replayable first-stage h/p plan from fixed physical inputs."""

    source = _require_source_sha(source_sha)
    nominal_h_nm = _validate_scope(
        cfg,
        path_id=path_id,
        comm_size=int(comm_size),
    )
    root_forest = stage4_local_h_root_forest_catalog(
        cfg,
        comm_size=int(comm_size),
    )
    if root_forest.audit.get("pass") is not True:
        raise RuntimeError("root forest geometry audit failed")
    patch_boxes = _initial_patch_boxes(cfg, root_forest)
    refinement_stages = (patch_boxes,)
    forest = stage4_multilevel_local_h_forest_catalog(
        cfg,
        refinement_stages,
        comm_size=int(comm_size),
    )
    reasons = _cell_guard_reasons(cfg, forest)
    degree_by_key = {
        cell.key: 5 if reasons[cell.key] else 4
        for cell in forest.leaves
    }
    degree_by_box = {
        cell.box: degree_by_key[cell.key] for cell in forest.leaves
    }
    degree_counts = {
        f"p{degree}": sum(
            value == degree for value in degree_by_key.values()
        )
        for degree in (4, 5, 6)
    }
    if degree_counts["p4"] == 0 or degree_counts["p5"] == 0:
        raise RuntimeError("initial map must contain both p4 and p5 cells")
    initial_state = build_initial_hp_transition_state(
        forest,
        degree_by_key,
        source_sha=source,
        algorithm_sha256=INITIAL_SPACE_ALGORITHM_SHA256,
    )

    selection_payload = {
        "patch_boxes": [list(box) for box in patch_boxes],
        "cell_degrees": [
            {
                "key": cell.key.to_dict(),
                "box": list(cell.box),
                "degree": degree_by_key[cell.key],
                "guard_reasons": sorted(reasons[cell.key]),
            }
            for cell in forest.leaves
        ],
    }
    config_identity = _config_identity(
        cfg,
        root_forest,
        path_id=path_id,
        nominal_h_nm=nominal_h_nm,
        comm_size=int(comm_size),
    )
    provenance_core = {
        "schema_version": "task035e.blind-initial-provenance.v1",
        "status": "blind_initial_provenance_closed",
        "source_sha": source,
        "algorithm_id": INITIAL_SPACE_ALGORITHM_ID,
        "algorithm_sha256": INITIAL_SPACE_ALGORITHM_SHA256,
        "path_id": path_id,
        "config_identity_sha256": _json_sha256(config_identity),
        "selection_sha256": _json_sha256(selection_payload),
        "initial_state_sha256": initial_state.state_sha256,
        "stage_action_sha256s": [],
        "stage_prefix_sha256": initial_state.audit[
            "stage_prefix_sha256"
        ],
        "input_classes": [
            "fixed_geometry",
            "material_tags_and_indices",
            "wavelength",
            "port_locations",
            "mpi_width",
            "clean_source_identity",
        ],
        "solved_field_inputs_consumed": False,
        "goal_value_inputs_consumed": False,
        "dwr_inputs_consumed": False,
        "error_map_inputs_consumed": False,
        "accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    provenance = {
        **provenance_core,
        "provenance_sha256": _json_sha256(provenance_core),
    }
    plan_payload = stage4_multilevel_local_h_refinement_plan_payload(
        cfg,
        refinement_stages,
        comm_size=int(comm_size),
        trace_degree=4,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degree_by_box,
        variable_trace_from_cell_degrees=True,
    )
    multilevel = plan_payload["multilevel_audit"]
    if (
        plan_payload["refinement_stage_count"] != 1
        or multilevel["actual_maximum_level"] != 1
        or multilevel["spatially_separated_user_patches"] is not True
        or multilevel["strong_2_to_1_balance"] is not True
        or any(
            row["matching"] is not True
            for row in multilevel["periodic_boundary_audit"].values()
        )
    ):
        raise RuntimeError("initial local-h closure audit failed")
    canonical_plan_json = json.dumps(
        plan_payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    guard_rows = [
        {
            "key": cell.key.to_dict(),
            "degree": degree_by_key[cell.key],
            "reasons": sorted(reasons[cell.key]),
        }
        for cell in forest.leaves
        if reasons[cell.key]
    ]
    audit_payload = {
        "schema_version": INITIAL_SPACE_SCHEMA,
        "status": "blind_initial_space_plan_pass",
        "pass": True,
        "path_id": path_id,
        "nominal_h_nm": nominal_h_nm,
        "source_sha": source,
        "algorithm_sha256": INITIAL_SPACE_ALGORITHM_SHA256,
        "config_identity": config_identity,
        "config_identity_sha256": _json_sha256(config_identity),
        "provenance_sha256": provenance["provenance_sha256"],
        "initial_state_sha256": initial_state.state_sha256,
        "stage_prefix_sha256": initial_state.audit[
            "stage_prefix_sha256"
        ],
        "plan_payload_sha256": hashlib.sha256(
            canonical_plan_json.encode("ascii")
        ).hexdigest(),
        "root_catalog_sha256": root_forest.audit[
            "leaf_catalog_sha256"
        ],
        "leaf_catalog_sha256": forest.audit["leaf_catalog_sha256"],
        "cell_degree_plan_sha256": plan_payload[
            "cell_interior_degree_plan_sha256"
        ],
        "cell_degree_counts": degree_counts,
        "complete_cell_degree_map": (
            len(degree_by_key) == len(forest.leaves)
        ),
        "trace_degree": 4,
        "container_degree": 6,
        "variable_trace_from_cell_degrees": True,
        "inactive_p6_requested_by_initial_map": False,
        "guard_cell_count": len(guard_rows),
        "guard_cells": guard_rows,
        "all_guard_cells_at_least_p5": all(
            row["degree"] >= 5 for row in guard_rows
        ),
        "patch_boxes": [list(box) for box in patch_boxes],
        "refinement_stage_count": 1,
        "actual_maximum_level": multilevel["actual_maximum_level"],
        "multilevel_ready_maximum_level": plan_payload["maximum_level"],
        "true_multilevel_claimed": False,
        "spatially_separated_user_patches": True,
        "user_mark_component_count": multilevel[
            "user_mark_component_count"
        ],
        "strong_2_to_1_balance": True,
        "periodic_closure": True,
        "material_interface_protection": True,
        "pde_solve_complete": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    audit_payload["authority_sha256"] = _json_sha256(audit_payload)
    return Task035eInitialSpacePlan(
        path_id=path_id,
        forest=forest,
        cell_degree_by_key=MappingProxyType(degree_by_key),
        canonical_plan_json=canonical_plan_json,
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "INITIAL_SPACE_ALGORITHM_ID",
    "INITIAL_SPACE_ALGORITHM_SHA256",
    "INITIAL_SPACE_SCHEMA",
    "Task035eInitialSpacePlan",
    "build_task035e_initial_space_plan",
]
