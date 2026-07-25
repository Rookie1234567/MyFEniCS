from __future__ import annotations

import argparse
import cmath
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
    _source_provenance,
    _stage_peaks,
)
from benchmarks.task034_wsl_resources import effective_memory_limit
from src.adaptivity.cell_indicator_snapshot import (
    validate_cell_indicator_snapshot,
)
from src.solvers.solve_vector_maxwell import _json_default
from src.geometry.research_axis_profiles import (
    TASK035B_R5_SLAB_BISECT_PROFILE,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task035/actual_global_r5"
GIB = 1024**3
_FIXED_TRACE_TOPOLOGY_CONTRACTS = {
    15.0: {
        "mesh_cells_resolved": [6, 2, 10],
        "num_mesh_cells": 120,
        "candidate_dofs": 74890,
        "global_p6_dofs": 84492,
        "active_rows_with_dtn": 16880,
        "base_schur_nnz": 9129300,
        "predicted_used_nnz": 9195812,
        "safe_allocated_nnz_upper": 9484580,
    },
    14.0: {
        "mesh_cells_resolved": [6, 2, 11],
        "num_mesh_cells": 132,
        "candidate_dofs": 82315,
        "global_p6_dofs": 92850,
        "active_rows_with_dtn": 18500,
        "base_schur_nnz": 10038000,
        "predicted_used_nnz": 10104512,
        "safe_allocated_nnz_upper": 10393280,
    },
    13.0: {
        "mesh_cells_resolved": [6, 2, 12],
        "num_mesh_cells": 144,
        "candidate_dofs": 89740,
        "global_p6_dofs": 101208,
        "active_rows_with_dtn": 20120,
        "base_schur_nnz": 10946700,
        "predicted_used_nnz": 11013212,
        "safe_allocated_nnz_upper": 11301980,
    },
}
_FIXED_TRACE_EXPLICIT_TOPOLOGY_CONTRACTS = {
    (7, 2, 10): {
        "mesh_cells_resolved": [7, 2, 10],
        "num_mesh_cells": 140,
        "candidate_dofs": 87195,
        "global_p6_dofs": 98322,
        "active_rows_with_dtn": 19680,
        "base_schur_nnz": 10650850,
        "predicted_used_nnz": 10728434,
        "safe_allocated_nnz_upper": 11065344,
    },
}
_FIXED_TRACE_EXPLICIT_Z_PROFILE = TASK035B_R5_SLAB_BISECT_PROFILE
_FIXED_TRACE_EXPLICIT_Z_TOPOLOGY_CONTRACT = {
    "mesh_cells_resolved": [6, 2, 12],
    "num_mesh_cells": 144,
    "candidate_dofs": 89740,
    "global_p6_dofs": 101208,
    "active_rows_with_dtn": 20120,
    "base_schur_nnz": 10946700,
    "predicted_used_nnz": 11013212,
    "safe_allocated_nnz_upper": 11301980,
}
_EXPLICIT_AXIS_IDENTITY_CONTRACTS = {
    (7, 2, 10): {
        "axis_sha256": {
            "x": "f99cf720acdbd78d426ef4f36cb22c0944de3a6b23f744750d48a51d85d342cd",
            "y": "d3aac691ebe8875dc45e5817b42b4f33c45277f999f2d010fd29fecd7ec1401f",
            "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
        },
        "partition_independent_mesh_sha256": (
            "326019d01cf2b98a83422e9c0aa520795daaa5bbc1fdeb73d567799504c705b1"
        ),
        "cell_tag_sha256": (
            "1434790f1ba5bb102c57561dd9a925f8f6f46aa4ebcb7c37194e205ee2e3d11c"
        ),
        "facet_tag_sha256": (
            "d2fa4745b79663b1838fa51473545f3b8290b0ed17212c28d162e27ae0e6c693"
        ),
    },
    (6, 3, 10): {
        "axis_sha256": {
            "x": "86dc23ef348c79d9ed51d79c199cbaddf95416e04c51e5569c666234c6613cc3",
            "y": "d7841480e80baeda07536ebc44681af4488f7d61a2eaa7de4d33cdacb9fa19fb",
            "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
        },
        "partition_independent_mesh_sha256": (
            "59d053ac70baaa80c6de82fcd2388d0076291f033cf074197c218055756eec8f"
        ),
        "cell_tag_sha256": (
            "60209a26ca68027775dc54783cc44a67314804ced204928025d35607c4d999e0"
        ),
        "facet_tag_sha256": (
            "270b60e1c061cd539e64219e349e29abe0deb6e414c35c979abb25e2660b9c75"
        ),
    },
}
_EXPLICIT_Z_PROFILE_IDENTITY_CONTRACT = {
    "profile": _FIXED_TRACE_EXPLICIT_Z_PROFILE,
    "axis_sha256": {
        "x": "86dc23ef348c79d9ed51d79c199cbaddf95416e04c51e5569c666234c6613cc3",
        "y": "d3aac691ebe8875dc45e5817b42b4f33c45277f999f2d010fd29fecd7ec1401f",
        "z": "9048a25cdb01a0ef2aa123bc5f7ec66116a2320ed42376e63ec22679e5f3c6d8",
    },
    "partition_independent_mesh_sha256": (
        "dcb2bad6d889ddd98025ae16d5d42d2e0131d48acad0591e0735998c2260cefa"
    ),
    "cell_tag_sha256": (
        "7a881ac7098887ea86ec5cb2c215b5b602128b91a7f4f3bae801083ae143da3d"
    ),
    "facet_tag_sha256": (
        "0d80fd0367b1af554d9c8e550addd5f6dd2bde4cfef906579427d19fca17e0d9"
    ),
}
_Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT = {
    "mesh_cells_resolved": [6, 3, 10],
    "num_mesh_cells": 180,
    "coarse_p4_dofs": 38092,
    "coarse_p4_active_rows_with_dtn": 15776,
    "coarse_p4_base_schur_nnz": 5808384,
    "coarse_p4_predicted_used_nnz": 5872400,
    "enriched_p5_dofs": 72995,
    "enriched_p5_active_rows_with_dtn": 25280,
    "enriched_p5_base_schur_nnz": 14333400,
    "enriched_p5_predicted_used_nnz": 14433128,
}


def _fixed_trace_topology_contract(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if (
        getattr(args, "fixed_trace_explicit_z_profile", None)
        == _FIXED_TRACE_EXPLICIT_Z_PROFILE
    ):
        return _FIXED_TRACE_EXPLICIT_Z_TOPOLOGY_CONTRACT
    explicit = getattr(args, "structured_axis_cells", None)
    if explicit is not None:
        return _FIXED_TRACE_EXPLICIT_TOPOLOGY_CONTRACTS.get(
            tuple(explicit)
        )
    return next(
        (
            contract
            for h_nm, contract in _FIXED_TRACE_TOPOLOGY_CONTRACTS.items()
            if abs(float(args.h_nm) - h_nm) <= 1.0e-12
        ),
        None,
    )


def _axis_sha256(values: Any) -> str:
    encoded = json.dumps(
        [float(value) for value in values],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mode_identity_sha256(modes: Any) -> str:
    encoded = json.dumps(
        [
            (mode.side, int(mode.m), int(mode.n), mode.polarization)
            for mode in modes
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fixed_trace_resource_preflight(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Resolve the actual tensor axes and resource envelope before MPI."""

    from src.common.config_3d import target_stage4_config
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.geometry.mesh_builder_3d import stage4_axis_plan

    topology = _fixed_trace_topology_contract(args)
    if topology is None:
        raise SystemExit(
            "fixed-trace resource preflight has no reviewed topology contract"
        )
    cfg = target_stage4_config(
        degree=int(args.fixed_interior_degree),
        h_nm=float(args.h_nm),
    )
    cfg.mesh_axis_cell_counts = getattr(
        args,
        "structured_axis_cells",
        None,
    )
    explicit_z_profile = getattr(
        args,
        "fixed_trace_explicit_z_profile",
        None,
    )
    if explicit_z_profile is not None:
        from src.adaptivity.target_fixed_trace_candidate import (
            TASK035B_R5_SLAB_BISECT_Z_VALUES_NM,
        )

        if explicit_z_profile != _FIXED_TRACE_EXPLICIT_Z_PROFILE:
            raise SystemExit("unknown fixed-trace explicit z profile")
        cfg.mesh_axis_cell_counts = (6, 2, 12)
        cfg.mesh_axis_z_values = (
            TASK035B_R5_SLAB_BISECT_Z_VALUES_NM
        )
        cfg.mesh_axis_z_profile = explicit_z_profile
    cfg.stage4_dtn_quadrature_degree = (
        args.fixed_trace_dtn_quadrature_degree
    )
    cfg.stage4_dtn_evanescent_buffer = int(
        args.fixed_trace_dtn_evanescent_buffer
    )
    seed_cfg = target_stage4_config(
        degree=int(args.fixed_interior_degree),
        h_nm=15.0,
    )
    plan = stage4_axis_plan(cfg, int(args.mpi_size))
    seed_plan = stage4_axis_plan(seed_cfg, int(args.mpi_size))
    axes = {
        "x": [float(value) for value in plan.x_values],
        "y": [float(value) for value in plan.y_values],
        "z": [float(value) for value in plan.z_values],
    }
    seed_axes = {
        "x": [float(value) for value in seed_plan.x_values],
        "y": [float(value) for value in seed_plan.y_values],
        "z": [float(value) for value in seed_plan.z_values],
    }
    actual_cells = list(plan.mesh_cells_resolved)
    dtn_modes = outgoing_port_modes_3d(cfg)
    dtn_mode_count = len(dtn_modes)
    dtn_propagating_count = sum(
        1 for mode in dtn_modes if mode.propagating
    )
    dtn_evanescent_count = (
        dtn_mode_count - dtn_propagating_count
    )
    dtn_mode_identity_sha256 = _mode_identity_sha256(dtn_modes)
    expected_mode_identity_sha256 = (
        "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
        if int(args.fixed_trace_dtn_evanescent_buffer) == 1
        else "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21"
    )
    effective_quadrature_degree = (
        int(args.fixed_trace_dtn_quadrature_degree)
        if args.fixed_trace_dtn_quadrature_degree is not None
        else 25
    )
    port_area = (
        float(cfg.x_max - cfg.x_min)
        * float(cfg.y_max - cfg.y_min)
    )
    mode_scaling_rows = []
    for mode in dtn_modes:
        boundary_z = float(
            cfg.physical_z_max
            if mode.side == "top"
            else cfg.physical_z_min
        )
        boundary_phase = cmath.exp(
            1j * complex(mode.k_vector[2]) * boundary_z
        )
        denominator = float(
            port_area
            * float(mode.electric_tangential_norm_sq)
            * abs(boundary_phase) ** 2
        )
        boundary_referenced = bool(
            int(args.fixed_trace_dtn_evanescent_buffer) > 0
            and not mode.propagating
        )
        assembly_denominator = (
            float(
                port_area
                * float(mode.electric_tangential_norm_sq)
            )
            if boundary_referenced
            else denominator
        )
        mode_scaling_rows.append(
            {
                "side": mode.side,
                "m": int(mode.m),
                "n": int(mode.n),
                "polarization": mode.polarization,
                "propagating": bool(mode.propagating),
                "abs_boundary_phase": float(abs(boundary_phase)),
                "projection_denominator": denominator,
                "boundary_referenced_auxiliary": boundary_referenced,
                "auxiliary_coordinate_scale_abs": (
                    float(abs(boundary_phase))
                    if boundary_referenced
                    else 1.0
                ),
                "assembly_projection_denominator": (
                    assembly_denominator
                ),
            }
        )
    minimum_abs_boundary_phase = min(
        row["abs_boundary_phase"] for row in mode_scaling_rows
    )
    minimum_projection_denominator = min(
        row["projection_denominator"] for row in mode_scaling_rows
    )
    maximum_projection_denominator = max(
        row["projection_denominator"] for row in mode_scaling_rows
    )
    minimum_assembly_projection_denominator = min(
        row["assembly_projection_denominator"]
        for row in mode_scaling_rows
    )
    maximum_assembly_projection_denominator = max(
        row["assembly_projection_denominator"]
        for row in mode_scaling_rows
    )
    boundary_phase_safety_floor = math.sqrt(
        sys.float_info.epsilon
    )
    mode_scaling_finite_positive = all(
        math.isfinite(row["abs_boundary_phase"])
        and row["abs_boundary_phase"] > 0.0
        and math.isfinite(row["projection_denominator"])
        and row["projection_denominator"] > 0.0
        for row in mode_scaling_rows
    )
    unscaled_port_basis_numerically_safe = bool(
        mode_scaling_finite_positive
        and minimum_abs_boundary_phase
        >= boundary_phase_safety_floor
    )
    boundary_referenced_mode_count = sum(
        row["boundary_referenced_auxiliary"]
        for row in mode_scaling_rows
    )
    assembly_scaling_finite_positive = all(
        math.isfinite(row["auxiliary_coordinate_scale_abs"])
        and row["auxiliary_coordinate_scale_abs"] > 0.0
        and math.isfinite(row["assembly_projection_denominator"])
        and row["assembly_projection_denominator"] > 0.0
        for row in mode_scaling_rows
    )
    assembly_dynamic_range_safe = bool(
        minimum_assembly_projection_denominator
        / maximum_assembly_projection_denominator
        >= boundary_phase_safety_floor
    )
    actual_port_basis_numerically_safe = bool(
        assembly_scaling_finite_positive
        and assembly_dynamic_range_safe
        and (
            int(args.fixed_trace_dtn_evanescent_buffer) == 0
            or boundary_referenced_mode_count == dtn_evanescent_count
        )
    )
    expected_active_rows = int(
        topology["active_rows_with_dtn"] - 80 + dtn_mode_count
    )
    default_appended_used = int(
        topology["predicted_used_nnz"]
        - topology["base_schur_nnz"]
    )
    predicted_appended_used = int(
        round(
            (default_appended_used - 80)
            * dtn_mode_count
            / 80
        )
        + dtn_mode_count
    )
    predicted_used_nnz = int(
        topology["base_schur_nnz"] + predicted_appended_used
    )
    default_safe_increment = int(
        topology["safe_allocated_nnz_upper"]
        - topology["base_schur_nnz"]
    )
    predicted_safe_upper = int(
        topology["base_schur_nnz"]
        + math.ceil(
            default_safe_increment * dtn_mode_count / 80
        )
    )
    directional = bool(args.fixed_trace_directional_recovery)
    directional_axis = getattr(
        args,
        "fixed_trace_directional_axis",
        None,
    )
    axis_sha256 = {
        axis: _axis_sha256(values)
        for axis, values in axes.items()
    }
    seed_axis_sha256 = {
        axis: _axis_sha256(values)
        for axis, values in seed_axes.items()
    }
    changed_axes = [
        axis
        for axis in ("x", "y", "z")
        if axis_sha256[axis] != seed_axis_sha256[axis]
    ]
    explicit_identity = (
        _EXPLICIT_Z_PROFILE_IDENTITY_CONTRACT
        if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
        else _EXPLICIT_AXIS_IDENTITY_CONTRACTS.get(tuple(actual_cells))
    )
    parent_h14_cfg = target_stage4_config(
        degree=int(args.fixed_interior_degree),
        h_nm=14.0,
    )
    parent_h14_plan = stage4_axis_plan(
        parent_h14_cfg,
        int(args.mpi_size),
    )
    parent_h14_z = [
        float(value) for value in parent_h14_plan.z_values
    ]
    expected_bisect_z = list(parent_h14_z)
    expected_bisect_z.insert(
        2,
        0.5 * (parent_h14_z[1] + parent_h14_z[2]),
    )
    checks = {
        "reviewed_topology_contract": actual_cells
        == topology["mesh_cells_resolved"],
        "material_planes_aligned": (
            plan.material_plane_alignment["all_aligned"] is True
        ),
        "candidate_dofs_le_90000": topology["candidate_dofs"] <= 90000,
        "active_rows_positive": expected_active_rows > 0,
        "predicted_nnz_positive": predicted_used_nnz > 0,
        "dtn_mode_identity_frozen": (
            dtn_mode_identity_sha256
            == expected_mode_identity_sha256
        ),
        "actual_port_basis_numerically_safe": (
            actual_port_basis_numerically_safe
        ),
        "directional_exactly_one_axis_changed": (
            (not directional)
            or changed_axes == [directional_axis]
        ),
        "directional_nonselected_axes_match_h15": (
            (not directional)
            or all(
                axis_sha256[axis] == seed_axis_sha256[axis]
                for axis in ("x", "y", "z")
                if axis != directional_axis
            )
        ),
        "explicit_axis_hash_identity_frozen": (
            explicit_identity is None
            or axis_sha256 == explicit_identity["axis_sha256"]
        ),
        "explicit_z_profile_identity_frozen": (
            explicit_z_profile is None
            or (
                explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
                and abs(float(args.h_nm) - 14.0) <= 1.0e-12
                and directional
                and directional_axis == "z"
                and actual_cells == [6, 2, 12]
                and axes["z"] == expected_bisect_z
                and axes["x"]
                == [float(value) for value in parent_h14_plan.x_values]
                and axes["y"]
                == [float(value) for value in parent_h14_plan.y_values]
            )
        ),
    }
    return {
        "schema_version": "task035b.fixed-trace-resource-preflight.v2",
        "pass": all(checks.values()),
        "checks": checks,
        "nominal_h_nm": float(args.h_nm),
        "directional_recovery": directional,
        "directional_axis": directional_axis,
        "directional_mesh_change_semantics": (
            "exact_h14_r5_slab_bisect_not_nested_refinement"
            if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
            else "exact_material_fitted_remeshing_not_nested_refinement"
            if directional
            else "not_applicable"
        ),
        "structured_axis_cells_requested": (
            None
            if getattr(args, "structured_axis_cells", None) is None
            else list(args.structured_axis_cells)
        ),
        "explicit_z_profile": explicit_z_profile,
        "axis_plan": {
            "mesh_cells_resolved": actual_cells,
            "mesh_spacing_mode_resolved": (
                plan.mesh_spacing_mode_resolved
            ),
            "axis_values_nm": axes,
            "axis_sha256": axis_sha256,
            "h15_axis_sha256": seed_axis_sha256,
            "parent_h14_z_axis_sha256": _axis_sha256(parent_h14_z),
            "parent_h14_z_values_nm": parent_h14_z,
            "changed_axes_from_h15": changed_axes,
            "expected_mesh_identity": explicit_identity,
            "material_plane_alignment": (
                plan.material_plane_alignment
            ),
        },
        "predicted_resources": {
            **topology,
            "reviewed_default_dtn_auxiliary_rows": 80,
            "dtn_auxiliary_rows": dtn_mode_count,
            "dtn_propagating_rows": dtn_propagating_count,
            "dtn_evanescent_rows": dtn_evanescent_count,
            "dtn_mode_identity_sha256": dtn_mode_identity_sha256,
            "expected_dtn_mode_identity_sha256": (
                expected_mode_identity_sha256
            ),
            "dtn_surface_quadrature_degree": (
                effective_quadrature_degree
            ),
            "expected_active_rows": expected_active_rows,
            "port_diagnostic_predicted_used_nnz": (
                predicted_used_nnz
            ),
            "port_diagnostic_safe_allocated_nnz_upper": (
                predicted_safe_upper
            ),
        },
        "port_basis_scaling_preflight": {
            "schema_version": (
                "task035b.dtn-port-basis-scaling-preflight.v2"
            ),
            "status": (
                "safe_boundary_referenced_evanescent_basis"
                if (
                    actual_port_basis_numerically_safe
                    and boundary_referenced_mode_count > 0
                )
                else "safe_for_pde"
                if actual_port_basis_numerically_safe
                else "controlled_stop_port_basis_scaling_not_safe"
            ),
            "pde_authorized": actual_port_basis_numerically_safe,
            "mode_count": dtn_mode_count,
            "mode_identity_sha256": dtn_mode_identity_sha256,
            "boundary_referenced_mode_count": (
                boundary_referenced_mode_count
            ),
            "historical_unscaled_basis_numerically_safe": (
                unscaled_port_basis_numerically_safe
            ),
            "minimum_abs_boundary_phase": (
                minimum_abs_boundary_phase
            ),
            "boundary_phase_safety_floor": (
                boundary_phase_safety_floor
            ),
            "minimum_projection_denominator": (
                minimum_projection_denominator
            ),
            "maximum_projection_denominator": (
                maximum_projection_denominator
            ),
            "denominator_dynamic_range": (
                maximum_projection_denominator
                / minimum_projection_denominator
            ),
            "minimum_assembly_projection_denominator": (
                minimum_assembly_projection_denominator
            ),
            "maximum_assembly_projection_denominator": (
                maximum_assembly_projection_denominator
            ),
            "assembly_denominator_dynamic_range": (
                maximum_assembly_projection_denominator
                / minimum_assembly_projection_denominator
            ),
            "assembly_dynamic_range_safe": (
                assembly_dynamic_range_safe
            ),
            "criterion": (
                "the actual opt-in assembly basis has finite positive "
                "coordinate scales and projection denominators, every "
                "evanescent buffer mode is port-plane referenced, and the "
                "assembly denominator minimum/maximum ratio is at least "
                "sqrt(machine epsilon); the historical unscaled metrics "
                "remain recorded separately"
            ),
            "ordinary_default_changed": False,
            "mode_rows": mode_scaling_rows,
        },
        "prediction_semantics": {
            "dofs_and_rows": "exact tensor-entity count",
            "base_schur_nnz": "exact cell-clique structural union",
            "predicted_used_nnz": (
                "topology-scaled port-support prediction for the explicit "
                "axis lane"
                if explicit_identity is not None
                else "exact for the 80-mode default; linear support-count "
                "prediction for an opt-in evanescent-buffer diagnostic"
            ),
            "safe_allocated_nnz_upper": (
                "topology-scaled conservative port-support upper for the "
                "explicit axis lane"
                if explicit_identity is not None
                else "support-safe exact default upper; linear conservative "
                "port-support projection for a buffer diagnostic"
            ),
            "measured": False,
        },
    }


def _structured_axis_global_control_preflight(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Freeze the y-only global-p5 control before any MPI solve."""

    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import stage4_axis_plan

    requested = tuple(args.structured_axis_cells)
    if requested != (6, 3, 10):
        raise ValueError(
            "the reviewed y-only global-p5 control requires exact axis "
            "counts (6, 3, 10)"
        )
    cfg = target_stage4_config(
        degree=int(args.enriched_degree),
        h_nm=float(args.h_nm),
    )
    cfg.mesh_axis_cell_counts = requested
    plan = stage4_axis_plan(cfg, int(args.mpi_size))
    actual = tuple(plan.mesh_cells_resolved)
    axes = {
        "x": [float(value) for value in plan.x_values],
        "y": [float(value) for value in plan.y_values],
        "z": [float(value) for value in plan.z_values],
    }
    axis_sha256 = {
        axis: _axis_sha256(values)
        for axis, values in axes.items()
    }
    expected_identity = _EXPLICIT_AXIS_IDENTITY_CONTRACTS[(6, 3, 10)]
    checks = {
        "reviewed_y_only_topology": actual == (6, 3, 10),
        "requested_topology_resolved_exactly": actual == requested,
        "material_planes_aligned": (
            plan.material_plane_alignment["all_aligned"] is True
        ),
        "axis_hash_identity_frozen": (
            axis_sha256 == expected_identity["axis_sha256"]
        ),
        "global_p5_dofs_le_90000": (
            _Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT["enriched_p5_dofs"]
            <= 90000
        ),
        "global_p5_active_rows_positive": (
            _Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT[
                "enriched_p5_active_rows_with_dtn"
            ]
            > 0
        ),
    }
    return {
        "schema_version": (
            "task035b.structured-axis-global-control-preflight.v1"
        ),
        "status": "pass" if all(checks.values()) else "fail",
        "pass": all(checks.values()),
        "checks": checks,
        "control_role": "y_only_global_p5_directional_control",
        "ordinary_default_changed": False,
        "nominal_h_nm": float(args.h_nm),
        "axis_plan": {
            "mesh_cells_resolved": list(actual),
            "mesh_spacing_mode_resolved": (
                plan.mesh_spacing_mode_resolved
            ),
            "axis_values_nm": axes,
            "axis_sha256": axis_sha256,
            "material_plane_alignment": (
                plan.material_plane_alignment
            ),
            "expected_mesh_identity": expected_identity,
        },
        "predicted_resources": dict(
            _Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT
        ),
        "prediction_semantics": {
            "dofs_and_rows": "exact tensor-entity count",
            "base_schur_nnz": "exact cell-clique structural union",
            "predicted_used_nnz": (
                "exact base plus the measured same-x/y h10 DtN support "
                "correction"
            ),
            "measured": False,
        },
    }


def _parse_theta_schedule(value: str) -> tuple[float, ...]:
    try:
        schedule = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "theta schedule must be comma-separated floating-point values"
        ) from exc
    if not schedule or any(not 0.0 < item <= 1.0 for item in schedule):
        raise argparse.ArgumentTypeError(
            "every theta schedule value must lie in (0, 1]"
        )
    return schedule


def _parse_axis_cell_counts(value: str) -> tuple[int, int, int]:
    try:
        counts = tuple(
            int(item.strip()) for item in value.split(",")
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "structured axis cells must be three comma-separated integers"
        ) from exc
    if len(counts) != 3 or any(item <= 0 for item in counts):
        raise argparse.ArgumentTypeError(
            "structured axis cells must be three positive integers"
        )
    return counts


def _parse_grazing_angles(value: str) -> tuple[float, ...]:
    try:
        angles = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "grazing angles must be comma-separated floating-point values"
        ) from exc
    if (
        not angles
        or any(not 0.0 < item < 90.0 for item in angles)
        or len(set(angles)) != len(angles)
    ):
        raise argparse.ArgumentTypeError("grazing angles must be unique and in (0, 90)")
    return angles


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _preflight_artifact_evidence(
    *,
    fixed_trace_path: Path,
    structured_axis_path: Path,
) -> dict[str, str | None]:
    """Describe only preflight artifacts that were actually written."""

    fixed_exists = fixed_trace_path.is_file()
    structured_exists = structured_axis_path.is_file()
    return {
        "fixed_trace_resource_preflight": (
            _path_from_root(fixed_trace_path) if fixed_exists else None
        ),
        "fixed_trace_resource_preflight_sha256": (
            _sha256(fixed_trace_path) if fixed_exists else None
        ),
        "structured_axis_resource_preflight": (
            _path_from_root(structured_axis_path)
            if structured_exists
            else None
        ),
        "structured_axis_resource_preflight_sha256": (
            _sha256(structured_axis_path)
            if structured_exists
            else None
        ),
    }


def _solve_artifact_file_evidence(
    path: Path,
    *,
    run_dir: Path,
) -> dict[str, Any]:
    """Hash one raw solve artifact without permitting path escape."""

    resolved = path.resolve()
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError(
            f"solve artifact escaped the run directory: {resolved}"
        ) from error
    return {
        "path": _path_from_root(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size if resolved.is_file() else None,
    }


def _global_pair_solve_artifact_manifest(
    *,
    run_dir: Path,
    result: dict[str, Any],
    coarse_degree: int,
    enriched_degree: int,
    mpi_size: int,
) -> dict[str, Any]:
    """Bind summaries, DtN orders, and field shards used by postprocessors."""

    levels: dict[str, Any] = {}
    all_files: list[dict[str, Any]] = []
    for result_key, directory_name, degree in (
        ("coarse", f"coarse_p{int(coarse_degree)}", coarse_degree),
        ("enriched", f"enriched_p{int(enriched_degree)}", enriched_degree),
    ):
        directory = (run_dir / directory_name).resolve()
        worker_summary = (
            (result.get(result_key) or {}).get("summary") or {}
        )
        summary_path = directory / "run_summary.json"
        orders_filename = worker_summary.get("dtn_port_orders_json")
        orders_path = directory / str(orders_filename)
        field_paths = sorted(
            directory.glob("fields_3d_for_paraview_rank*.vtu")
        )
        summary_evidence = _solve_artifact_file_evidence(
            summary_path,
            run_dir=run_dir,
        )
        orders_evidence = _solve_artifact_file_evidence(
            orders_path,
            run_dir=run_dir,
        )
        field_evidence = [
            _solve_artifact_file_evidence(path, run_dir=run_dir)
            for path in field_paths
        ]
        raw_summary: Any = None
        raw_orders: Any = None
        try:
            raw_summary = json.loads(
                summary_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            pass
        try:
            raw_orders = json.loads(
                orders_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            pass
        order_rows = (
            raw_orders.get("orders")
            if isinstance(raw_orders, dict)
            else None
        )
        checks = {
            "canonical_directory": directory == (
                run_dir.resolve() / directory_name
            ),
            "summary_sha256_present": (
                summary_evidence["sha256"] is not None
            ),
            "summary_matches_worker_result": (
                isinstance(raw_summary, dict)
                and raw_summary == worker_summary
            ),
            "canonical_dtn_orders_filename": (
                orders_filename
                == "dtn_port_diffraction_orders_3d.json"
            ),
            "orders_sha256_present": (
                orders_evidence["sha256"] is not None
            ),
            "orders_have_80_rows": (
                isinstance(order_rows, list) and len(order_rows) == 80
            ),
            "field_shard_count_matches_mpi": len(field_evidence)
            == int(mpi_size),
            "all_field_shards_hash_bound": (
                len(field_evidence) == int(mpi_size)
                and all(row["sha256"] is not None for row in field_evidence)
            ),
        }
        files = [
            {"role": "run_summary", **summary_evidence},
            {"role": "dtn_port_orders", **orders_evidence},
            *[
                {"role": "field_shard", **row}
                for row in field_evidence
            ],
        ]
        manifest_sha256 = hashlib.sha256(
            json.dumps(
                files,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        level = {
            "degree": int(degree),
            "directory": _path_from_root(directory),
            "pass": all(checks.values()),
            "checks": checks,
            "run_summary": summary_evidence,
            "dtn_port_orders": {
                **orders_evidence,
                "order_count": (
                    len(order_rows) if isinstance(order_rows, list) else None
                ),
            },
            "field_shards": {
                "shard_count": len(field_evidence),
                "shards": field_evidence,
            },
            "files_manifest_sha256": manifest_sha256,
        }
        levels[directory_name] = level
        all_files.extend(
            {
                "level": directory_name,
                **row,
            }
            for row in files
        )
    checks = {
        "two_global_pair_levels_present": set(levels)
        == {
            f"coarse_p{int(coarse_degree)}",
            f"enriched_p{int(enriched_degree)}",
        },
        "all_levels_pass": all(
            level["pass"] is True for level in levels.values()
        ),
    }
    return {
        "schema_version": "task035b.global-pair-solve-artifact-manifest.v1",
        "requested": True,
        "pass": all(checks.values()),
        "checks": checks,
        "levels": levels,
        "files_manifest_sha256": hashlib.sha256(
            json.dumps(
                all_files,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def _structured_axis_orders_evidence(
    *,
    run_dir: Path,
    enriched_summary: dict[str, Any],
    enriched_degree: int,
) -> dict[str, Any]:
    """Bind the y-control enriched DtN orders to the watchdog record."""

    filename = enriched_summary.get("dtn_port_orders_json")
    canonical_filename = "dtn_port_diffraction_orders_3d.json"
    if filename != canonical_filename:
        return {
            "pass": False,
            "path": None,
            "sha256": None,
            "order_count": None,
            "reason": "noncanonical_or_missing_orders_filename",
        }
    path = (
        run_dir
        / f"enriched_p{int(enriched_degree)}"
        / canonical_filename
    ).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return {
            "pass": False,
            "path": None,
            "sha256": None,
            "order_count": None,
            "reason": "orders_path_escaped_run_directory",
        }
    if not path.is_file():
        return {
            "pass": False,
            "path": _path_from_root(path),
            "sha256": None,
            "order_count": None,
            "reason": "orders_file_missing",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "pass": False,
            "path": _path_from_root(path),
            "sha256": _sha256(path),
            "order_count": None,
            "reason": "orders_file_unreadable",
        }
    orders = payload.get("orders")
    order_count = len(orders) if isinstance(orders, list) else None
    passed = order_count == 80
    return {
        "pass": passed,
        "path": _path_from_root(path),
        "sha256": _sha256(path),
        "order_count": order_count,
        "reason": None if passed else "orders_count_is_not_80",
    }


def _resolve_new_record_path(
    path: Path,
    *,
    input_authorities: tuple[Path | None, ...],
) -> Path:
    """Resolve an output record without permitting evidence replacement."""

    record_path = (
        path if path.is_absolute() else ROOT / path
    ).resolve()
    protected = {
        authority.resolve()
        for authority in input_authorities
        if authority is not None
    }
    if record_path in protected:
        raise SystemExit(
            "output record path must not alias an input authority: "
            f"{record_path}"
        )
    if record_path.exists():
        raise SystemExit(
            "output record already exists; historical evidence will not "
            f"be overwritten: {record_path}"
        )
    return record_path


def _memory_snapshot() -> dict[str, Any]:
    effective = effective_memory_limit()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "effective_limit": effective,
        "artifact_filesystem_free_bytes": shutil.disk_usage(
            DEFAULT_ARTIFACT_ROOT.parent
        ).free,
    }


def _append_progress(path: Path, stage: str, status: str) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _worker(args: argparse.Namespace) -> int:
    progress_path = args.run_dir / "progress_3d.jsonl"

    def progress(stage: str, status: str) -> None:
        _append_progress(progress_path, stage, status)

    if args.fixed_trace_control_record is not None:
        from src.adaptivity.target_fixed_trace_candidate import (
            run_target_fixed_trace_candidate,
        )

        result = run_target_fixed_trace_candidate(
            args.run_dir,
            control_record=args.fixed_trace_control_record,
            control_sha256=args.fixed_trace_control_sha256,
            significant_channel_reference_record=(
                args.fixed_trace_significant_channel_reference_record
            ),
            significant_channel_reference_sha256=(
                args.fixed_trace_significant_channel_reference_sha256
            ),
            global_p6_baseline_record=(
                args.fixed_trace_global_p6_baseline_record
            ),
            global_p6_baseline_sha256=(
                args.fixed_trace_global_p6_baseline_sha256
            ),
            directional_parent_record=(
                args.fixed_trace_directional_parent_record
            ),
            directional_parent_sha256=(
                args.fixed_trace_directional_parent_sha256
            ),
            h_nm=args.h_nm,
            incident_theta_deg=80.0,
            polarization_kind=args.polarization_kind,
            trace_degree=args.fixed_trace_degree,
            interior_degree=args.fixed_interior_degree,
            directional_recovery=args.fixed_trace_directional_recovery,
            directional_axis=args.fixed_trace_directional_axis,
            mesh_axis_cell_counts=args.structured_axis_cells,
            explicit_z_profile=args.fixed_trace_explicit_z_profile,
            channel_adjoint_diagnostic=(
                args.fixed_trace_channel_adjoint_diagnostic
            ),
            dtn_quadrature_degree=(
                args.fixed_trace_dtn_quadrature_degree
            ),
            dtn_evanescent_buffer=(
                args.fixed_trace_dtn_evanescent_buffer
            ),
            progress_observer=progress,
        )
    elif args.regionwise_p_classifier_record is not None:
        from src.adaptivity.target_regionwise_p_candidate import (
            run_target_regionwise_p_candidate,
        )

        result = run_target_regionwise_p_candidate(
            args.run_dir,
            classifier_record=args.regionwise_p_classifier_record,
            classifier_sha256=args.regionwise_p_classifier_sha256,
            control_record=args.regionwise_p_control_record,
            control_sha256=args.regionwise_p_control_sha256,
            h_nm=args.h_nm,
            incident_theta_deg=80.0,
            polarization_kind=args.polarization_kind,
            trace_degree=args.regionwise_p_trace_degree,
            low_interior_degree=args.regionwise_p_low_interior_degree,
            high_cell_count=args.regionwise_p_high_cell_count,
            progress_observer=progress,
        )
    elif args.common_mesh_replay_record is not None:
        from src.adaptivity.target_common_mesh_angle_sweep import (
            run_target_common_mesh_angle_sweep,
        )

        result = run_target_common_mesh_angle_sweep(
            args.run_dir,
            replay_record=args.common_mesh_replay_record,
            replay_record_sha256=args.common_mesh_replay_sha256,
            grazing_angles_deg=args.common_mesh_grazing_angles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
            replay_expected_theta=args.common_mesh_replay_theta,
            replay_expected_final_cells=args.common_mesh_replay_expected_final_cells,
            dof_ceiling=args.hp_dof_ceiling,
            accuracy_control_key=args.hp_accuracy_control_key,
        )
    elif args.goal_dwr_only:
        from src.adaptivity.goal_weighted_two_level import (
            run_target_goal_weighted_two_level,
        )

        result = run_target_goal_weighted_two_level(
            args.run_dir,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            mesh_cell_type=args.mesh_cell_type,
            progress_observer=progress,
        )
    elif args.dwr_adaptive_cycles:
        from src.adaptivity.target_dwr_adaptive_cycles import (
            run_target_dwr_adaptive_cycles,
        )

        result = run_target_dwr_adaptive_cycles(
            args.run_dir,
            marked_cycles=args.dwr_adaptive_cycles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            theta_schedule=args.theta_schedule,
            polarization_kind=args.polarization_kind,
            marker_policy=args.dwr_marker_policy,
            full_boundary_synchronization=(
                not args.minimal_periodic_edge_closure
            ),
            progress_observer=progress,
        )
    elif args.uniform_refinement_levels:
        from src.adaptivity.target_uniform_tetra_control import (
            run_target_uniform_tetra_control,
        )

        result = run_target_uniform_tetra_control(
            args.run_dir,
            refinement_levels=args.uniform_refinement_levels,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            initial_h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
        )
    elif args.adaptive_marked_cycles:
        from src.adaptivity.target_r5_adaptive_cycles import (
            run_target_r5_adaptive_cycles,
        )

        result = run_target_r5_adaptive_cycles(
            args.run_dir,
            marked_cycles=args.adaptive_marked_cycles,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            progress_observer=progress,
        )
    else:
        from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5

        result = run_target_global_two_level_r5(
            args.run_dir,
            coarse_degree=args.coarse_degree,
            enriched_degree=args.enriched_degree,
            h_nm=args.h_nm,
            theta=args.theta,
            polarization_kind=args.polarization_kind,
            mesh_cell_type=args.mesh_cell_type,
            progress_observer=progress,
            reuse_single_mesh=args.single_mesh_pair,
            static_condensation_degrees=tuple(
                args.static_condensation_degree
            ),
            assembly_time_condensation_degrees=tuple(
                args.assembly_time_condensation_degree
            ),
            floquet_slave_elimination_degrees=tuple(
                args.floquet_slave_elimination_degree
            ),
            include_p6_projection_signals=(
                args.p6_projection_signals
            ),
            mesh_axis_cell_counts=args.structured_axis_cells,
        )
    if MPI.COMM_WORLD.rank == 0:
        (args.run_dir / "actual_r5_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task035 actual global two-level R5 target watchdog."
    )
    parser.add_argument("--coarse-degree", type=int, default=2)
    parser.add_argument("--enriched-degree", type=int, default=3)
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--theta", type=float, default=0.5)
    parser.add_argument("--polarization-kind", choices=("s", "p"), default="s")
    parser.add_argument(
        "--mesh-cell-type",
        choices=("hexahedron", "tetrahedron"),
        default="hexahedron",
    )
    parser.add_argument(
        "--structured-axis-cells",
        type=_parse_axis_cell_counts,
        help=(
            "research-only exact material-fitted tensor counts NX,NY,NZ; "
            "ordinary target-size meshing remains unchanged when omitted"
        ),
    )
    parser.add_argument(
        "--single-mesh-pair",
        action="store_true",
        help=(
            "build the fixed target mesh once and reuse that exact in-memory "
            "mesh for both global-p solves"
        ),
    )
    parser.add_argument(
        "--bind-global-pair-solve-artifacts",
        action="store_true",
        help=(
            "research-only watchdog manifest binding both raw run summaries, "
            "DtN order JSON files, and every MPI field shard"
        ),
    )
    parser.add_argument(
        "--p6-projection-signals",
        action="store_true",
        help=(
            "opt-in Task035b p4/p5/p6 nested H(curl) shell and global "
            "conforming projection-defect diagnostics"
        ),
    )
    parser.add_argument(
        "--static-condensation-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree whose cell-interior modes are "
            "exactly condensed; may be repeated"
        ),
    )
    parser.add_argument(
        "--assembly-time-condensation-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree assembled directly into the "
            "cell-condensed Floquet-independent trace matrix; may be repeated"
        ),
    )
    parser.add_argument(
        "--floquet-slave-elimination-degree",
        type=int,
        action="append",
        default=[],
        help=(
            "research-only global-p pair degree whose embedded Floquet "
            "identity rows are physically removed after cell condensation; "
            "may be repeated"
        ),
    )
    parser.add_argument("--mpi-size", type=int, default=8)
    parser.add_argument("--adaptive-marked-cycles", type=int, default=0)
    parser.add_argument("--uniform-refinement-levels", type=int, default=0)
    parser.add_argument("--dwr-adaptive-cycles", type=int, default=0)
    parser.add_argument(
        "--goal-dwr-only",
        action="store_true",
        help=(
            "run one same-mesh R00/R/T goal-adjoint localization pair "
            "without refining the mesh"
        ),
    )
    parser.add_argument(
        "--dwr-marker-policy",
        choices=(
            "combined_relative_R_T",
            "tolerance_normalized_R_T",
            "R_total",
            "T_total",
        ),
        default="combined_relative_R_T",
    )
    parser.add_argument(
        "--minimal-periodic-edge-closure",
        action="store_true",
        help="research-only DWR refinement without the full periodic boundary sleeve",
    )
    parser.add_argument(
        "--theta-schedule",
        type=_parse_theta_schedule,
        help=("comma-separated DWR theta values; exactly one per marked cycle"),
    )
    parser.add_argument(
        "--common-mesh-replay-record",
        type=Path,
        help="accepted theta=0.7 DWR record whose marker deterministically rebuilds the mesh",
    )
    parser.add_argument(
        "--common-mesh-replay-sha256",
        help="required SHA256 authority for --common-mesh-replay-record",
    )
    parser.add_argument(
        "--common-mesh-grazing-angles",
        type=_parse_grazing_angles,
        default=(1.0, 5.0, 10.0),
        help="comma-separated grazing angles solved on the one replayed mesh",
    )
    parser.add_argument(
        "--common-mesh-replay-theta", type=float, default=0.7,
        help="DWR theta bound into the replay authority",
    )
    parser.add_argument(
        "--common-mesh-replay-expected-final-cells", type=int, default=1316,
        help="exact final global cell count bound into the replay authority",
    )
    parser.add_argument(
        "--hp-dof-ceiling", type=int,
        help="optional hard DoF ceiling for the enriched 10-degree candidate",
    )
    parser.add_argument(
        "--hp-accuracy-control-key",
        choices=("p4_h7p5",),
        help="qualified Task034 accuracy control for the enriched candidate",
    )
    parser.add_argument(
        "--regionwise-p-classifier-record",
        type=Path,
        help="Task035b same-mesh p4/p5/p6 classifier authority",
    )
    parser.add_argument(
        "--regionwise-p-classifier-sha256",
        help="required SHA256 for --regionwise-p-classifier-record",
    )
    parser.add_argument(
        "--regionwise-p-control-record",
        type=Path,
        help="Task035b qualified same-mesh p5/p6 control watchdog record",
    )
    parser.add_argument(
        "--regionwise-p-control-sha256",
        help="required SHA256 for --regionwise-p-control-record",
    )
    parser.add_argument(
        "--regionwise-p-trace-degree",
        type=int,
        default=4,
        help="shared edge/face trace degree for the physical local-p candidate",
    )
    parser.add_argument(
        "--regionwise-p-low-interior-degree",
        type=int,
        default=4,
        help="cell-interior degree outside the selected high-cell set",
    )
    parser.add_argument(
        "--regionwise-p-high-cell-count",
        type=int,
        help="number of largest eta_p5p6 classifier cells retaining p6 interior",
    )
    parser.add_argument(
        "--fixed-trace-control-record",
        type=Path,
        help="qualified h10 p5/p6 authority for the h15 fixed-trace upper envelope",
    )
    parser.add_argument(
        "--fixed-trace-control-sha256",
        help="required SHA256 for --fixed-trace-control-record",
    )
    parser.add_argument(
        "--fixed-trace-global-p6-baseline-record",
        type=Path,
        help="qualified same-mesh h15 global-p6 resource baseline",
    )
    parser.add_argument(
        "--fixed-trace-global-p6-baseline-sha256",
        help="required SHA256 for the same-mesh global-p6 baseline",
    )
    parser.add_argument(
        "--fixed-trace-significant-channel-reference-record",
        type=Path,
        help="qualified frozen Task035b significant-channel reference v1",
    )
    parser.add_argument(
        "--fixed-trace-significant-channel-reference-sha256",
        help="required SHA256 for the frozen 12-channel reference v1",
    )
    parser.add_argument(
        "--fixed-trace-degree",
        type=int,
        default=5,
        help="shared edge/face trace degree for the fixed-trace candidate",
    )
    parser.add_argument(
        "--fixed-interior-degree",
        type=int,
        default=6,
        help="cell-interior degree retained on every candidate cell",
    )
    parser.add_argument(
        "--fixed-trace-directional-recovery",
        action="store_true",
        help=(
            "Review-V1 single-axis fixed-trace recovery topology; legacy "
            "calls resolve to z and the x lane requires an exact axis plan"
        ),
    )
    parser.add_argument(
        "--fixed-trace-directional-axis",
        choices=("x", "z"),
        help=(
            "axis changed by directional recovery; omitted legacy calls "
            "resolve to z"
        ),
    )
    parser.add_argument(
        "--fixed-trace-explicit-z-profile",
        choices=(_FIXED_TRACE_EXPLICIT_Z_PROFILE,),
        help=(
            "research-only frozen h14 z-axis profile; no arbitrary "
            "coordinate list is accepted"
        ),
    )
    parser.add_argument(
        "--fixed-trace-directional-parent-record",
        type=Path,
        help=(
            "qualified positive h14 watchdog authority required only before "
            "the one permitted h13 escalation"
        ),
    )
    parser.add_argument(
        "--fixed-trace-directional-parent-sha256",
        help="required SHA256 for the positive h14 directional parent",
    )
    parser.add_argument(
        "--fixed-trace-channel-adjoint-diagnostic",
        action="store_true",
        help=(
            "retain the accepted h15 reduced direct factor only long enough "
            "to run the 16 independent Review-V1 channel adjoints and exact "
            "augmented dual recovery; never a resource-authority run"
        ),
    )
    parser.add_argument(
        "--fixed-trace-dtn-quadrature-degree",
        type=int,
        choices=(31, 37),
        help=(
            "h15 root-cause diagnostic using one reviewed raised DtN trace "
            "quadrature degree; the frozen default remains unchanged"
        ),
    )
    parser.add_argument(
        "--fixed-trace-dtn-evanescent-buffer",
        type=int,
        choices=(0, 1),
        default=0,
        help=(
            "h15 root-cause diagnostic adding exactly one rectangular "
            "evanescent order buffer; zero preserves the ordinary default"
        ),
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK035_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    if args.mpi_size < 1:
        parser.error("--mpi-size must be positive.")
    if args.coarse_degree < 1 or args.enriched_degree <= args.coarse_degree:
        parser.error("require 1 <= coarse-degree < enriched-degree.")
    if args.h_nm <= 0.0:
        parser.error("--h-nm must be positive.")
    if not 0.0 < args.theta <= 1.0:
        parser.error("--theta must lie in (0, 1].")
    if args.poll_interval < 0.05:
        parser.error("--poll-interval must be at least 0.05 seconds.")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be positive.")
    if args.adaptive_marked_cycles < 0:
        parser.error("--adaptive-marked-cycles must be non-negative.")
    if args.uniform_refinement_levels < 0:
        parser.error("--uniform-refinement-levels must be non-negative.")
    if args.dwr_adaptive_cycles < 0:
        parser.error("--dwr-adaptive-cycles must be non-negative.")
    active_cycles = sum(
        bool(value)
        for value in (
            args.adaptive_marked_cycles,
            args.uniform_refinement_levels,
            args.dwr_adaptive_cycles,
        )
    )
    if active_cycles > 1:
        parser.error(
            "R5 adaptive, DWR adaptive, and uniform control are mutually exclusive."
        )
    common_mesh_mode = args.common_mesh_replay_record is not None
    if common_mesh_mode != (args.common_mesh_replay_sha256 is not None):
        parser.error(
            "--common-mesh-replay-record and --common-mesh-replay-sha256 "
            "must be provided together."
        )
    if common_mesh_mode and active_cycles:
        parser.error(
            "common-mesh replay and adaptive/uniform cycle modes are mutually exclusive."
        )
    regionwise_values = (
        args.regionwise_p_classifier_record,
        args.regionwise_p_classifier_sha256,
        args.regionwise_p_control_record,
        args.regionwise_p_control_sha256,
    )
    regionwise_mode = any(value is not None for value in regionwise_values)
    if regionwise_mode and not all(value is not None for value in regionwise_values):
        parser.error(
            "regionwise-p mode requires classifier/control records and both SHA256 values."
        )
    if regionwise_mode and (common_mesh_mode or active_cycles):
        parser.error(
            "regionwise-p, common-mesh, and adaptive/uniform modes are mutually exclusive."
        )
    fixed_trace_control_values = (
        args.fixed_trace_control_record,
        args.fixed_trace_control_sha256,
    )
    fixed_trace_baseline_values = (
        args.fixed_trace_global_p6_baseline_record,
        args.fixed_trace_global_p6_baseline_sha256,
    )
    fixed_trace_channel_reference_values = (
        args.fixed_trace_significant_channel_reference_record,
        args.fixed_trace_significant_channel_reference_sha256,
    )
    fixed_trace_directional_parent_values = (
        args.fixed_trace_directional_parent_record,
        args.fixed_trace_directional_parent_sha256,
    )
    fixed_trace_port_diagnostic = bool(
        args.fixed_trace_dtn_quadrature_degree is not None
        or args.fixed_trace_dtn_evanescent_buffer > 0
    )
    fixed_trace_mode = any(
        value is not None for value in fixed_trace_control_values
    )
    if fixed_trace_mode and not all(
        value is not None for value in fixed_trace_control_values
    ):
        parser.error(
            "fixed-trace mode requires a SHA-bound h10 accuracy control."
        )
    if any(value is not None for value in fixed_trace_baseline_values) and not (
        fixed_trace_mode
        and all(value is not None for value in fixed_trace_baseline_values)
    ):
        parser.error(
            "fixed-trace global-p6 baseline path and SHA256 must be paired "
            "with the fixed-trace control."
        )
    if fixed_trace_mode and not all(
        value is not None for value in fixed_trace_channel_reference_values
    ):
        parser.error(
            "fixed-trace mode requires the SHA-bound frozen significant-"
            "channel reference v1."
        )
    if (
        any(
            value is not None
            for value in fixed_trace_channel_reference_values
        )
        and not fixed_trace_mode
    ):
        parser.error(
            "fixed-trace significant-channel reference is valid only with "
            "fixed-trace mode."
        )
    if args.fixed_trace_directional_recovery and not fixed_trace_mode:
        parser.error(
            "--fixed-trace-directional-recovery requires fixed-trace mode."
        )
    if (
        args.fixed_trace_directional_axis is not None
        and not args.fixed_trace_directional_recovery
    ):
        parser.error(
            "--fixed-trace-directional-axis requires directional recovery."
        )
    if args.fixed_trace_directional_recovery:
        args.fixed_trace_directional_axis = (
            args.fixed_trace_directional_axis or "z"
        )
    if args.fixed_trace_explicit_z_profile is not None:
        if (
            not fixed_trace_mode
            or not args.fixed_trace_directional_recovery
            or args.fixed_trace_directional_axis != "z"
            or abs(float(args.h_nm) - 14.0) > 1.0e-12
            or args.structured_axis_cells is not None
        ):
            parser.error(
                "the explicit z profile requires the fixed-trace h14 "
                "directional-z lane without a structured-axis override"
            )
    if (
        args.fixed_trace_channel_adjoint_diagnostic
        and not fixed_trace_mode
    ):
        parser.error(
            "--fixed-trace-channel-adjoint-diagnostic requires fixed-trace "
            "mode."
        )
    if (
        args.fixed_trace_channel_adjoint_diagnostic
        and args.fixed_trace_directional_recovery
    ):
        parser.error(
            "fixed-trace channel-adjoint seed diagnostic and directional "
            "recovery are mutually exclusive."
        )
    if fixed_trace_port_diagnostic and not fixed_trace_mode:
        parser.error(
            "fixed-trace DtN/port diagnostic requires fixed-trace mode."
        )
    if fixed_trace_port_diagnostic and (
        args.fixed_trace_directional_recovery
        or args.fixed_trace_channel_adjoint_diagnostic
    ):
        parser.error(
            "fixed-trace DtN/port, directional, and channel-adjoint "
            "diagnostics are mutually exclusive."
        )
    if (
        args.fixed_trace_dtn_quadrature_degree is not None
        and args.fixed_trace_dtn_evanescent_buffer > 0
    ):
        parser.error(
            "change only one fixed-trace DtN/port diagnostic control per "
            "run."
        )
    if any(
        value is not None
        for value in fixed_trace_directional_parent_values
    ) and not all(
        value is not None
        for value in fixed_trace_directional_parent_values
    ):
        parser.error(
            "fixed-trace directional parent path and SHA256 must be paired."
        )
    if fixed_trace_mode and (
        common_mesh_mode or active_cycles or regionwise_mode
    ):
        parser.error(
            "fixed-trace, regionwise-p, common-mesh, and cycle modes "
            "are mutually exclusive."
        )
    structured_axis_mode = args.structured_axis_cells is not None
    if structured_axis_mode and (
        args.mesh_cell_type != "hexahedron"
        or args.mpi_size != 8
        or common_mesh_mode
        or active_cycles
        or regionwise_mode
        or args.goal_dwr_only
    ):
        parser.error(
            "structured-axis controls require MPI8 fixed-target hexahedra "
            "without adaptive, replay, regionwise-p, or goal-DWR modes."
        )
    if fixed_trace_mode and structured_axis_mode and (
        not args.fixed_trace_directional_recovery
        or args.fixed_trace_directional_axis != "x"
        or args.structured_axis_cells != (7, 2, 10)
    ):
        parser.error(
            "the only reviewed fixed-trace explicit-axis lane is x-only "
            "(7,2,10)."
        )
    if (
        fixed_trace_mode
        and args.fixed_trace_directional_axis == "x"
        and not structured_axis_mode
    ):
        parser.error(
            "x-only fixed-trace recovery requires "
            "--structured-axis-cells 7,2,10."
        )
    if args.goal_dwr_only and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
    ):
        parser.error(
            "goal-DWR-only, regionwise-p, common-mesh, and cycle modes "
            "are mutually exclusive."
        )
    if args.single_mesh_pair and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
        or args.goal_dwr_only
    ):
        parser.error(
            "--single-mesh-pair is valid only for the plain global-p pair."
        )
    if args.bind_global_pair_solve_artifacts and (
        not args.single_mesh_pair
        or common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
        or args.goal_dwr_only
    ):
        parser.error(
            "--bind-global-pair-solve-artifacts requires a plain "
            "single-mesh global-p pair."
        )
    if args.p6_projection_signals and (
        not args.single_mesh_pair
        or fixed_trace_mode
        or regionwise_mode
        or common_mesh_mode
        or active_cycles
        or args.goal_dwr_only
        or args.coarse_degree != 5
        or args.enriched_degree != 6
    ):
        parser.error(
            "--p6-projection-signals requires a plain single-mesh p5/p6 pair"
        )
    invalid_condensation_degrees = set(args.static_condensation_degree) - {
        args.coarse_degree,
        args.enriched_degree,
    }
    if invalid_condensation_degrees:
        parser.error(
            "--static-condensation-degree must equal coarse-degree or "
            "enriched-degree."
        )
    if args.static_condensation_degree and (
        common_mesh_mode
        or active_cycles
        or regionwise_mode
        or fixed_trace_mode
        or args.goal_dwr_only
        or args.mesh_cell_type != "hexahedron"
    ):
        parser.error(
            "Task035b static condensation is restricted to the plain "
            "fixed-target hexahedron global-p pair."
        )
    if not set(args.assembly_time_condensation_degree).issubset(
        set(args.static_condensation_degree)
    ):
        parser.error(
            "--assembly-time-condensation-degree must also be listed in "
            "--static-condensation-degree."
        )
    if not set(args.floquet_slave_elimination_degree).issubset(
        set(args.static_condensation_degree)
    ):
        parser.error(
            "--floquet-slave-elimination-degree must also be listed in "
            "--static-condensation-degree."
        )
    if not set(args.assembly_time_condensation_degree).issubset(
        set(args.floquet_slave_elimination_degree)
    ):
        parser.error(
            "--assembly-time-condensation-degree must also be listed in "
            "--floquet-slave-elimination-degree."
        )
    if structured_axis_mode and not fixed_trace_mode:
        reviewed_degrees = {
            int(args.coarse_degree),
            int(args.enriched_degree),
        }
        if (
            args.structured_axis_cells != (6, 3, 10)
            or reviewed_degrees != {4, 5}
            or abs(args.h_nm - 15.0) > 1.0e-12
            or args.polarization_kind != "s"
            or not args.single_mesh_pair
            or set(args.static_condensation_degree)
            != reviewed_degrees
            or set(args.assembly_time_condensation_degree)
            != reviewed_degrees
            or set(args.floquet_slave_elimination_degree)
            != reviewed_degrees
        ):
            parser.error(
                "the only reviewed plain structured-axis control is the "
                "y-only (6,3,10) h15 global p4/p5 MPI8 single-mesh pair "
                "with assembly-time static condensation and Floquet slave "
                "elimination on both degrees."
            )
    if args.theta_schedule is not None:
        if not args.dwr_adaptive_cycles:
            parser.error("--theta-schedule is valid only with --dwr-adaptive-cycles.")
        if len(args.theta_schedule) != args.dwr_adaptive_cycles:
            parser.error(
                "--theta-schedule must contain exactly one value per DWR marked cycle."
            )
    if args.minimal_periodic_edge_closure and not args.dwr_adaptive_cycles:
        parser.error(
            "--minimal-periodic-edge-closure requires --dwr-adaptive-cycles."
        )
    if (active_cycles or common_mesh_mode) and args.mesh_cell_type != "tetrahedron":
        parser.error(
            "adaptive/uniform refinement requires --mesh-cell-type tetrahedron."
        )
    if not 0.0 < args.common_mesh_replay_theta <= 1.0:
        parser.error("--common-mesh-replay-theta must lie in (0, 1].")
    if args.common_mesh_replay_expected_final_cells < 1:
        parser.error(
            "--common-mesh-replay-expected-final-cells must be positive."
        )
    hp_budget_mode = args.hp_dof_ceiling is not None
    if hp_budget_mode != (args.hp_accuracy_control_key is not None):
        parser.error(
            "--hp-dof-ceiling and --hp-accuracy-control-key must be provided together."
        )
    if hp_budget_mode:
        if args.hp_dof_ceiling < 1:
            parser.error("--hp-dof-ceiling must be positive.")
        if not common_mesh_mode:
            parser.error("hp budget evaluation requires common-mesh replay mode.")
        if args.common_mesh_grazing_angles != (10.0,):
            parser.error(
                "hp budget evaluation requires exactly --common-mesh-grazing-angles 10."
            )
    if regionwise_mode:
        for value in (
            args.regionwise_p_classifier_sha256,
            args.regionwise_p_control_sha256,
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdefABCDEF" for character in value
            ):
                parser.error("regionwise-p authority SHA256 values must be 64 hex.")
        if (
            args.mpi_size != 8
            or args.mesh_cell_type != "hexahedron"
            or args.coarse_degree != 5
            or args.enriched_degree != 6
            or abs(args.h_nm - 10.0) > 1.0e-12
            or args.polarization_kind != "s"
        ):
            parser.error(
                "formal regionwise-p mode requires MPI8, hexa h10, p5/p6 "
                "controls, and s polarization."
            )
        if not (
            1
            <= args.regionwise_p_low_interior_degree
            <= args.regionwise_p_trace_degree
            < 6
        ):
            parser.error(
                "regionwise-p requires 1 <= low interior degree "
                "<= trace degree < 6."
            )
        if (
            args.regionwise_p_high_cell_count is not None
            and not 0 <= args.regionwise_p_high_cell_count <= 105
        ):
            parser.error(
                "--regionwise-p-high-cell-count must lie in [0, 105]."
            )
        if (
            args.regionwise_p_trace_degree == 5
            and args.regionwise_p_high_cell_count is None
        ):
            parser.error(
                "p5-trace regionwise-p requires an explicit high-cell count."
            )
    if fixed_trace_mode:
        for label, value in (
            ("control", args.fixed_trace_control_sha256),
            (
                "significant-channel reference",
                args.fixed_trace_significant_channel_reference_sha256,
            ),
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdefABCDEF"
                for character in value
            ):
                parser.error(
                    f"fixed-trace {label} SHA256 must be 64 hex."
                )
        if args.fixed_trace_directional_parent_sha256 is not None:
            value = args.fixed_trace_directional_parent_sha256
            if len(value) != 64 or any(
                character not in "0123456789abcdefABCDEF"
                for character in value
            ):
                parser.error(
                    "fixed-trace directional parent SHA256 must be 64 hex."
                )
        fixed_identity = (
            args.mpi_size != 8
            or args.mesh_cell_type != "hexahedron"
            or args.coarse_degree != 5
            or args.enriched_degree != 6
            or args.polarization_kind != "s"
            or args.fixed_trace_degree != 5
            or args.fixed_interior_degree != 6
        )
        if fixed_identity:
            parser.error(
                "formal fixed-trace mode requires MPI8, hexa, p5/p6 "
                "controls, p5 trace, p6 interior, and s polarization."
            )
        baseline_bound = all(
            value is not None for value in fixed_trace_baseline_values
        )
        if args.fixed_trace_directional_recovery:
            if baseline_bound:
                parser.error(
                    "directional fixed-trace recovery must omit a same-mesh "
                    "global-p6 baseline."
                )
            parent_bound = all(
                value is not None
                for value in fixed_trace_directional_parent_values
            )
            if args.fixed_trace_directional_axis == "x":
                if (
                    abs(args.h_nm - 15.0) > 1.0e-12
                    or args.structured_axis_cells != (7, 2, 10)
                    or parent_bound
                ):
                    parser.error(
                        "x-only fixed-trace recovery requires nominal h15, "
                        "exact axes (7,2,10), and no directional parent."
                    )
            else:
                if (
                    not any(
                        abs(args.h_nm - allowed) <= 1.0e-12
                        for allowed in (14.0, 13.0)
                    )
                    or args.structured_axis_cells is not None
                ):
                    parser.error(
                        "legacy z recovery requires nominal h14 or h13 "
                        "without an explicit axis override."
                    )
                if (
                    abs(args.h_nm - 13.0) <= 1.0e-12
                    and not parent_bound
                ):
                    parser.error(
                        "h13 escalation requires a SHA-bound positive h14 "
                        "directional parent."
                    )
                if (
                    abs(args.h_nm - 14.0) <= 1.0e-12
                    and parent_bound
                ):
                    parser.error(
                        "the primary h14 directional point must not provide "
                        "a parent record."
                    )
        elif abs(args.h_nm - 15.0) > 1.0e-12 or not baseline_bound:
            parser.error(
                "the accepted fixed-trace seed requires h15 and a SHA-bound "
                "same-mesh global-p6 baseline; use the directional flag for "
                "the reviewed z h14/h13 or exact x (7,2,10) recovery."
            )
        elif any(
            value is not None
            for value in fixed_trace_directional_parent_values
        ):
            parser.error(
                "directional parent is valid only for h13 recovery."
            )
    if args.goal_dwr_only and (
        args.mpi_size != 8
        or args.mesh_cell_type != "hexahedron"
        or args.coarse_degree != 4
        or args.enriched_degree != 5
        or abs(args.h_nm - 10.0) > 1.0e-12
        or args.polarization_kind != "s"
    ):
        parser.error(
            "formal goal-DWR-only mode requires MPI8, hexa h10, p4/p5, "
            "and s polarization."
        )
    return args


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    process_tree = maximum("mpi_process_tree_rss_mb")
    process_swap = maximum("mpi_process_tree_swap_mb")
    worker_counts = []
    smaps_readable_counts = []
    per_rank_smaps_peaks: dict[int, dict[str, float]] = {}
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_counts.append(len(workers))
        if isinstance(
            row.get("worker_rank_smaps_readable_count"),
            (int, float),
        ):
            smaps_readable_counts.append(
                int(row["worker_rank_smaps_readable_count"])
            )
        try:
            smaps_rows = json.loads(
                str(row.get("worker_rank_smaps_rollup_json", "[]"))
            )
        except json.JSONDecodeError:
            smaps_rows = []
        if not isinstance(smaps_rows, list):
            continue
        for entry in smaps_rows:
            if not isinstance(entry, dict) or not isinstance(
                entry.get("rank"),
                int,
            ):
                continue
            rank = int(entry["rank"])
            peaks = per_rank_smaps_peaks.setdefault(rank, {})
            for field in (
                "rss_mb",
                "pss_mb",
                "uss_mb",
                "shared_mb",
                "anonymous_mb",
                "swap_mb",
                "swap_pss_mb",
            ):
                value = entry.get(field)
                if isinstance(value, (int, float)):
                    peaks[field] = max(
                        peaks.get(field, 0.0),
                        float(value),
                    )
    return {
        "sample_count": len(rows),
        "max_process_tree_rss_mb": process_tree,
        "max_process_tree_swap_mb": process_swap,
        "max_worker_rank_rss_sum_mb": maximum(
            "worker_rank_rss_sum_mb"
        ),
        "max_worker_rank_pss_sum_mb": maximum(
            "worker_rank_pss_sum_mb"
        ),
        "max_worker_rank_uss_sum_mb": maximum(
            "worker_rank_uss_sum_mb"
        ),
        "max_worker_rank_shared_sum_mb": maximum(
            "worker_rank_shared_sum_mb"
        ),
        "max_worker_rank_smaps_swap_sum_mb": maximum(
            "worker_rank_smaps_swap_sum_mb"
        ),
        "per_rank_smaps_rollup_peaks_mb": {
            str(rank): values
            for rank, values in sorted(per_rank_smaps_peaks.items())
        },
        "smaps_rollup_all_ranks_readable_at_least_once": bool(
            worker_counts
            and smaps_readable_counts
            and max(smaps_readable_counts)
            == max(worker_counts)
        ),
        "memory_authority_gib": (
            None if process_tree is None else process_tree / 1024.0
        ),
        "max_observed_worker_rank_count": max(worker_counts, default=0),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _compact_solve(entry: dict[str, Any]) -> dict[str, Any]:
    summary = entry["summary"]
    resolved_config = summary.get("config") or {}
    return {
        "degree": entry["degree"],
        "h_nm": entry["h_nm"],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "mpi_size": summary.get("mpi_size"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "mesh_cells_resolved": summary.get("mesh_cells_resolved"),
        "mesh_cell_type_actual": summary.get("mesh_cell_type_actual"),
        "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
        "mesh_axis_cell_counts_requested": resolved_config.get(
            "mesh_axis_cell_counts_requested"
        ),
        "nedelec_trace_degree_resolved": resolved_config.get(
            "nedelec_trace_degree_resolved"
        ),
        "nedelec_interior_degree_resolved": resolved_config.get(
            "nedelec_interior_degree_resolved"
        ),
        "matrix_stats": summary.get("matrix_stats"),
        "linear_system_relative_residual": summary.get(
            "linear_system_relative_residual"
        ),
        "R00_s": summary.get("R00_s"),
        "R00_p": summary.get("R00_p"),
        "R00_total": summary.get("R00_total"),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_volume_total": summary.get("A_volume_total"),
        "energy_closure_error_port_volume": summary.get(
            "energy_closure_error_port_volume"
        ),
        "floquet_num_constraints": summary.get("floquet_num_constraints"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "stage4_dtn_ksp_setup_seconds": summary.get(
            "stage4_dtn_ksp_setup_seconds"
        ),
        "stage4_dtn_ksp_solve_seconds": summary.get(
            "stage4_dtn_ksp_solve_seconds"
        ),
        "stage4_dtn_factor_inventory": summary.get(
            "stage4_dtn_factor_inventory"
        ),
        "stage4_dtn_base_matrix_assembly_seconds": summary.get(
            "stage4_dtn_base_matrix_assembly_seconds"
        ),
        "stage4_dtn_assembly_time_total_build_seconds": summary.get(
            "stage4_dtn_assembly_time_total_build_seconds"
        ),
        "stage4_dtn_linear_solve_seconds": summary.get(
            "stage4_dtn_linear_solve_seconds"
        ),
        "timings_seconds": summary.get("timings_seconds"),
        "solver_objects_released_before_postprocess": summary.get(
            "solver_objects_released_before_postprocess"
        ),
        "solver_release_audit": summary.get("solver_release_audit"),
        "stage4_cell_static_condensation": summary.get(
            "stage4_cell_static_condensation"
        ),
        "stage4_assembly_time_cell_static_condensation": summary.get(
            "stage4_assembly_time_cell_static_condensation"
        ),
        "stage4_dtn_condensed_matrix_stats": summary.get(
            "stage4_dtn_condensed_matrix_stats"
        ),
        "stage4_floquet_slave_elimination": summary.get(
            "stage4_floquet_slave_elimination"
        ),
        "stage4_dtn_floquet_independent_matrix_stats": summary.get(
            "stage4_dtn_floquet_independent_matrix_stats"
        ),
        "cell_static_condensation": summary.get(
            "cell_static_condensation"
        ),
        "high_order_resource_audit": entry.get(
            "high_order_resource_audit"
        ),
    }


def _watchdog_ordinary_default_identity(
    result: dict[str, Any],
) -> dict[str, Any]:
    """Project the solver's ordinary-default identity into every watchdog."""

    return {
        "ordinary_default_changed": result.get(
            "ordinary_default_changed"
        )
    }


def _canonical_payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _top_proxy_rows(
    rows: list[dict[str, Any]],
    *,
    count: int = 12,
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: float(
            row.get(
                "normalized_sensitivity_proxy",
                row.get("component_proxy_sum", 0.0),
            )
        ),
        reverse=True,
    )[:count]


def _compact_entity_sensitivity_proxy(
    report: dict[str, Any],
) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    for name, payload in (report.get("entities") or {}).items():
        rows = list(payload.get("rows") or [])
        entities[name] = {
            key: value
            for key, value in payload.items()
            if key != "rows"
        }
        entities[name].update(
            {
                "raw_row_count": len(rows),
                "top_normalized_sensitivity_rows": (
                    _top_proxy_rows(rows)
                ),
            }
        )
    periodic: dict[str, Any] = {
        "axes": (
            report.get("periodic_transitive_aggregation") or {}
        ).get("axes")
    }
    for name in ("edge_trace", "face_trace"):
        payload = (
            report.get("periodic_transitive_aggregation") or {}
        ).get(name) or {}
        components = list(payload.get("components") or [])
        periodic[name] = {
            key: value
            for key, value in payload.items()
            if key not in {"components", "member_to_component"}
        }
        periodic[name].update(
            {
                "raw_component_count": len(components),
                "top_component_proxy_rows": (
                    _top_proxy_rows(components)
                ),
            }
        )
    return {
        key: value
        for key, value in report.items()
        if key
        not in {
            "entities",
            "periodic_transitive_aggregation",
        }
    } | {
        "raw_payload_sha256": _canonical_payload_sha256(report),
        "entities": entities,
        "periodic_transitive_aggregation": periodic,
        "compact_record_semantics": (
            "top-12 proxy rows per entity/component group; the complete "
            "hash-bound payload remains in raw actual_r5_result evidence"
        ),
    }


def _compact_channel_adjoint_diagnostic(
    diagnostic: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if diagnostic is None:
        return None
    recovered = {
        label: {
            key: value
            for key, value in row.items()
            if key != "entity_sensitivity_proxy"
        }
        | {
            "entity_sensitivity_proxy": (
                _compact_entity_sensitivity_proxy(
                    row["entity_sensitivity_proxy"]
                )
            )
        }
        for label, row in (
            diagnostic.get("recovered_full_duals") or {}
        ).items()
    }
    return {
        key: value
        for key, value in diagnostic.items()
        if key != "recovered_full_duals"
    } | {
        "raw_payload_sha256": _canonical_payload_sha256(diagnostic),
        "recovered_full_duals": recovered,
        "compact_record_semantics": (
            "complete channel adjoint and entity payload remains in the "
            "hash-bound raw actual_r5_result artifact"
        ),
    }


def _compact_adaptive_cycle(entry: dict[str, Any]) -> dict[str, Any]:
    actual = entry["actual_r5"]
    return {
        "cycle_index": entry["cycle_index"],
        "mesh_audit": entry["mesh_audit"],
        "coarse_observables": entry["coarse_observables"],
        "enriched_observables": entry["enriched_observables"],
        "official_observable_delta_l2": entry["official_observable_delta_l2"],
        "coarse_fixed_reference_error_l2": entry["coarse_fixed_reference_error_l2"],
        "enriched_fixed_reference_error_l2": entry["enriched_fixed_reference_error_l2"],
        "coarse": _compact_solve(actual["coarse"]),
        "enriched": _compact_solve(actual["enriched"]),
        "R5": actual["R5"],
        "elapsed_seconds": actual["elapsed_seconds"],
    }


def _compact_dwr_cycle(entry: dict[str, Any]) -> dict[str, Any]:
    result = entry["goal_dwr"]
    return {
        "cycle_index": entry["cycle_index"],
        "theta": entry.get("theta"),
        "mesh_audit": entry["mesh_audit"],
        "coarse_observables": entry["coarse_observables"],
        "enriched_observables": entry["enriched_observables"],
        "official_observable_delta_l2": entry["official_observable_delta_l2"],
        "coarse_fixed_reference_error_l2": entry["coarse_fixed_reference_error_l2"],
        "enriched_fixed_reference_error_l2": entry["enriched_fixed_reference_error_l2"],
        "marker": entry["marker"],
        "coarse": _compact_solve(result["coarse"]),
        "enriched": _compact_solve(result["enriched"]),
        "DWR": result["DWR"],
        "R5_control": result["R5_control"],
    }


def _compact_common_mesh_angle(entry: dict[str, Any]) -> dict[str, Any]:
    pair = entry["actual_r5_pair"]
    return {
        "grazing_angle_deg": entry["grazing_angle_deg"],
        "incident_theta_deg": entry["incident_theta_deg"],
        "target_identity": pair["target_identity"],
        "coarse": _compact_solve(pair["coarse"]),
        "enriched": _compact_solve(pair["enriched"]),
        "official_observable_delta_l2": pair["official_observable_delta_l2"],
        "R5": pair["R5"],
        "elapsed_seconds": pair["elapsed_seconds"],
        "ordinary_default_changed": pair["ordinary_default_changed"],
    }


def _structured_axis_y_contract_checks(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    preflight: dict[str, Any],
) -> dict[str, bool]:
    """Pure identity/resource checks for the one reviewed y-control."""

    solves = [result.get("coarse") or {}, result.get("enriched") or {}]
    entries = {
        int(entry.get("degree", -1)): entry for entry in solves
    }
    p4 = entries.get(4, {}).get("summary") or {}
    p5 = entries.get(5, {}).get("summary") or {}
    common = result.get("common_mesh_identity") or {}
    expected_identity = _EXPLICIT_AXIS_IDENTITY_CONTRACTS[(6, 3, 10)]
    orders = _structured_axis_orders_evidence(
        run_dir=Path(args.run_dir),
        enriched_summary=p5,
        enriched_degree=5,
    )

    def matrix(summary: dict[str, Any]) -> dict[str, Any]:
        return (
            summary.get(
                "stage4_dtn_floquet_independent_matrix_stats"
            )
            or summary.get("matrix_stats")
            or {}
        )

    checks: dict[str, bool] = {
        "cli_identity": (
            tuple(args.structured_axis_cells or ()) == (6, 3, 10)
            and int(args.mpi_size) == 8
            and int(args.coarse_degree) == 4
            and int(args.enriched_degree) == 5
            and abs(float(args.h_nm) - 15.0) <= 1.0e-12
            and args.polarization_kind == "s"
        ),
        "preflight_identity": (
            preflight.get("pass") is True
            and preflight.get("control_role")
            == "y_only_global_p5_directional_control"
            and preflight.get("predicted_resources")
            == _Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT
        ),
        "mesh_and_tag_identity": (
            all(
                common.get(key) == expected_identity[key]
                for key in (
                    "partition_independent_mesh_sha256",
                    "cell_tag_sha256",
                    "facet_tag_sha256",
                )
            )
            and common.get("mesh_cells_resolved") == [6, 3, 10]
            and common.get("global_cell_count") == 180
        ),
        "topology_and_dofs": (
            set(entries) == {4, 5}
            and all(
                summary.get("mesh_cells_resolved") == [6, 3, 10]
                and summary.get("num_mesh_cells") == 180
                and (
                    summary.get("config") or {}
                ).get("mesh_axis_cell_counts_requested")
                == [6, 3, 10]
                for summary in (p4, p5)
            )
            and p4.get("num_nedelec_dofs") == 38092
            and p5.get("num_nedelec_dofs") == 72995
            and p5.get("num_nedelec_dofs", 90001) <= 90000
        ),
        "matrix_rows_and_nnz": (
            matrix(p4).get("matrix_rows") == 15776
            and matrix(p4).get("matrix_nnz_used") == 5872400
            and matrix(p5).get("matrix_rows") == 25280
            and matrix(p5).get("matrix_nnz_used") == 14433128
        ),
        "full_true_residuals": all(
            isinstance(
                (
                    (
                        summary.get("cell_static_condensation") or {}
                    ).get("full_explicit_true_residual")
                    or {}
                ).get("linear_system_relative_residual"),
                (int, float),
            )
            and math.isfinite(
                float(
                    (
                        (
                            summary.get("cell_static_condensation")
                            or {}
                        ).get("full_explicit_true_residual")
                        or {}
                    )["linear_system_relative_residual"]
                )
            )
            and float(
                (
                    (
                        summary.get("cell_static_condensation") or {}
                    ).get("full_explicit_true_residual")
                    or {}
                )["linear_system_relative_residual"]
            )
            <= 1.0e-9
            for summary in (p4, p5)
        ),
        "orders_sha_bound": orders.get("pass") is True,
    }
    return checks


def _qualify(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    r5 = result.get("R5") or {}
    energy = r5.get("correction_energy") or {}
    marking = r5.get("marking") or {}
    canonical_marking = r5.get("canonical_marking") or {}
    indicator_snapshot = r5.get("cell_indicator_snapshot") or {}
    solves = [result.get("coarse") or {}, result.get("enriched") or {}]
    summaries = [entry.get("summary") or {} for entry in solves]
    resource_audits = [
        entry.get("high_order_resource_audit") or {} for entry in solves
    ]
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_global_r5_pass",
        "formal_hierarchical_fe_r5": r5.get("formal_hierarchical_fe_r5") is True,
        "finite_cell_contributions": r5.get("finite_cell_contributions") is True,
        "nonnegative_cell_contributions": (
            r5.get("nonnegative_cell_contributions") is True
        ),
        "positive_correction_energy": (
            isinstance(r5.get("correction_energy_norm"), (int, float))
            and float(r5["correction_energy_norm"]) > 0.0
        ),
        "cell_energy_closure_le_1e-10": (
            isinstance(energy.get("relative_closure_error"), (int, float))
            and float(energy["relative_closure_error"]) <= 1.0e-10
        ),
        "dorfler_target_captured": (
            isinstance(marking.get("captured_fraction"), (int, float))
            and float(marking["captured_fraction"]) >= args.theta
        ),
        "canonical_dorfler_target_captured": (
            isinstance(
                canonical_marking.get("captured_fraction"), (int, float)
            )
            and float(canonical_marking["captured_fraction"]) >= args.theta
        ),
        "complete_cell_indicator_snapshot": (
            indicator_snapshot.get("storage") == "inline_complete_vector"
            and indicator_snapshot.get("cell_count")
            == r5.get("owned_cell_contribution_count")
            and len(indicator_snapshot.get("canonical_cell_ids") or [])
            == indicator_snapshot.get("cell_count")
            and len(indicator_snapshot.get("indicator_values") or [])
            == indicator_snapshot.get("cell_count")
            and indicator_snapshot.get("mesh_geometry_sha256")
            == r5.get("mesh_geometry_sha256")
            and bool(
                indicator_snapshot.get(
                    "canonical_ids_and_values_sha256"
                )
            )
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in summaries
        ),
        "both_full_observable_vectors_present": all(
            all(
                isinstance(summary.get(name), (int, float))
                for name in (
                    "R00_total",
                    "R_total",
                    "T_total",
                    "A_volume_total",
                )
            )
            for summary in summaries
        ),
        "requested_mesh_backend_used": all(
            summary.get("mesh_cell_type_actual") == args.mesh_cell_type
            for summary in summaries
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in summaries
        ),
        "both_entity_dof_audits_pass": all(
            (audit.get("entity_dof_inventory") or {}).get("pass") is True
            for audit in resource_audits
        ),
        "same_actual_mesh_hashes": result.get("same_mesh_hashes") is True,
        "single_mesh_instance_when_requested": (
            not getattr(args, "single_mesh_pair", False)
            or result.get("single_in_memory_mesh_instance") is True
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    if getattr(args, "p6_projection_signals", False):
        signals = r5.get("p6_local_hp_signals") or {}
        snapshots = signals.get("snapshots") or {}
        expected_snapshots = {
            "shell_p5_energy",
            "shell_p6_energy",
            "hierarchical_decay_ratio",
            "hierarchical_decay_resolved",
            "coefficient_decay_ratio",
            "coefficient_decay_resolved",
            "p4_relative_projection_defect",
            "p5_relative_projection_defect",
        }
        energy_closures = signals.get("energy_closures") or {}
        snapshot_validations = {
            name: validate_cell_indicator_snapshot(
                snapshot,
                expected_mesh_geometry_sha256=signals.get(
                    "mesh_geometry_sha256"
                ),
                expected_cell_count=signals.get("cell_count"),
            )
            for name, snapshot in snapshots.items()
        }
        checks.update(
            {
                "p6_projection_signals_requested": (
                    result.get("p6_projection_signals_requested") is True
                ),
                "p6_projection_signals_pass": signals.get("pass") is True,
                "p6_projection_signal_mesh_identity": (
                    signals.get("mesh_geometry_sha256")
                    == r5.get("mesh_geometry_sha256")
                ),
                "p6_projection_signal_snapshots_complete": (
                    set(snapshots) == expected_snapshots
                    and all(
                        all(validation.values())
                        for validation in snapshot_validations.values()
                    )
                ),
                "p6_projection_element_contract": (
                    (signals.get("element_contract") or {}).get("family")
                    == "N1E"
                    and (signals.get("element_contract") or {}).get(
                        "map_type"
                    )
                    == "covariantPiola"
                    and (signals.get("element_contract") or {}).get(
                        "sobolev_space"
                    )
                    == "HCurl"
                    and (signals.get("element_contract") or {}).get(
                        "continuous"
                    )
                    is True
                ),
                "p6_projection_energy_closures_le_1e-10": (
                    set(energy_closures)
                    == {
                        "p6_field",
                        "shell_p5",
                        "shell_p6",
                        "p4_projection_defect",
                    }
                    and all(
                        isinstance(
                            closure.get("relative_closure_error"),
                            (int, float),
                        )
                        and float(closure["relative_closure_error"])
                        <= 1.0e-10
                        for closure in energy_closures.values()
                    )
                ),
                "p6_projection_all_cells_resolved": (
                    len(
                        (
                            snapshots.get(
                                "hierarchical_decay_resolved"
                            )
                            or {}
                        ).get("indicator_values")
                        or []
                    )
                    == signals.get("cell_count")
                    and all(
                        value == 1.0
                        for value in (
                            (
                                snapshots.get(
                                    "hierarchical_decay_resolved"
                                )
                                or {}
                            ).get("indicator_values")
                            or []
                        )
                    )
                ),
                "p6_projection_p5_roundtrip_le_1e-12": (
                    isinstance(
                        signals.get(
                            "p5_roundtrip_relative_coefficient_error"
                        ),
                        (int, float),
                    )
                    and float(
                        signals[
                            "p5_roundtrip_relative_coefficient_error"
                        ]
                    )
                    <= 1.0e-12
                ),
                "p6_projection_reconstruction_le_1e-12": (
                    isinstance(
                        signals.get(
                            "reconstruction_relative_coefficient_error"
                        ),
                        (int, float),
                    )
                    and float(
                        signals[
                            "reconstruction_relative_coefficient_error"
                        ]
                    )
                    <= 1.0e-12
                ),
            }
        )
    static_condensation_degrees = getattr(
        args, "static_condensation_degree", []
    )
    if static_condensation_degrees:
        requested = set(static_condensation_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_static_condensation_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_cell_static_condensation"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_condensed_rows_physically_measured": all(
                    (
                        (
                            entry.get("high_order_resource_audit") or {}
                        ).get("entity_dof_inventory")
                        or {}
                    ).get("static_condensation_projection_semantics", "").startswith(
                        "measured_active_rows"
                    )
                    for entry in requested_entries
                ),
                "requested_full_residual_audit_present": all(
                    isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("full_explicit_true_residual")
                            or {}
                        ).get("linear_system_relative_residual"),
                        (int, float),
                    )
                    for entry in requested_entries
                ),
            }
        )
    slave_elimination_degrees = getattr(
        args, "floquet_slave_elimination_degree", []
    )
    if slave_elimination_degrees:
        requested = set(slave_elimination_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_floquet_slave_elimination_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_floquet_slave_elimination"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_floquet_slave_rows_physically_removed": all(
                    (
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("floquet_slave_elimination")
                            or {}
                        ).get("status")
                        in {
                            "exact_identity_slave_rows_removed",
                            "exact_mpc_trace_expansion_built",
                        }
                    )
                    for entry in requested_entries
                ),
            }
        )
    assembly_time_degrees = getattr(
        args,
        "assembly_time_condensation_degree",
        [],
    )
    if assembly_time_degrees:
        requested = set(assembly_time_degrees)
        requested_entries = [
            entry
            for entry in solves
            if int(entry.get("degree", -1)) in requested
        ]
        checks.update(
            {
                "requested_assembly_time_condensation_active": (
                    len(requested_entries) == len(requested)
                    and all(
                        (entry.get("summary") or {}).get(
                            "stage4_assembly_time_cell_static_condensation"
                        )
                        is True
                        for entry in requested_entries
                    )
                ),
                "requested_full_matrices_never_allocated": all(
                    (
                        (
                            (entry.get("summary") or {}).get(
                                "cell_static_condensation"
                            )
                            or {}
                        ).get("full_global_matrix_allocated")
                        is False
                        and (
                            (
                                (entry.get("summary") or {}).get(
                                    "cell_static_condensation"
                                )
                                or {}
                            ).get("full_trace_matrix_allocated")
                            is False
                        )
                    )
                    for entry in requested_entries
                ),
                "requested_matrix_free_full_residual_present": all(
                    isinstance(
                        (
                            (
                                (
                                    (entry.get("summary") or {}).get(
                                        "cell_static_condensation"
                                    )
                                    or {}
                                ).get("full_explicit_true_residual")
                                or {}
                            ).get("eliminated_cell_interior_residual_norm")
                        ),
                        (int, float),
                    )
                    for entry in requested_entries
                ),
                "requested_mumps_workspace_is_explicit": all(
                    (
                        (entry.get("summary") or {})
                        .get("config", {})
                        .get("petsc_extra_options", {})
                        .get("mat_mumps_icntl_14")
                        == 100
                    )
                    for entry in requested_entries
                ),
                "requested_solver_objects_released_before_postprocess": all(
                    (entry.get("summary") or {}).get(
                        "solver_objects_released_before_postprocess"
                    )
                    is True
                    for entry in requested_entries
                ),
                "requested_heap_trim_succeeded": all(
                    (
                        (
                            (entry.get("summary") or {}).get(
                                "solver_release_audit"
                            )
                            or {}
                        ).get("process_heap_trim")
                        or {}
                    ).get("succeeded_on_all_ranks")
                    is True
                    for entry in requested_entries
                ),
                "requested_heap_trim_reduced_rss": all(
                    isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        ).get("sum_rss_before_mb"),
                        (int, float),
                    )
                    and isinstance(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        ).get("sum_rss_after_mb"),
                        (int, float),
                    )
                    and float(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        )["sum_rss_after_mb"]
                    )
                    < float(
                        (
                            (
                                (entry.get("summary") or {}).get(
                                    "solver_release_audit"
                                )
                                or {}
                            ).get("process_heap_trim")
                            or {}
                        )["sum_rss_before_mb"]
                    )
                    for entry in requested_entries
                ),
            }
        )
    structured_axis_cells = getattr(
        args,
        "structured_axis_cells",
        None,
    )
    if structured_axis_cells is not None:
        requested_axis_cells = tuple(structured_axis_cells)
        expected_identity = _EXPLICIT_AXIS_IDENTITY_CONTRACTS.get(
            requested_axis_cells
        )
        structured_preflight = getattr(
            args,
            "structured_axis_resource_preflight",
            {},
        )
        entries_by_degree = {
            int(entry.get("degree", -1)): entry for entry in solves
        }
        p4_summary = (
            entries_by_degree.get(4, {}).get("summary") or {}
        )
        p5_summary = (
            entries_by_degree.get(5, {}).get("summary") or {}
        )
        structured_orders = _structured_axis_orders_evidence(
            run_dir=Path(args.run_dir),
            enriched_summary=p5_summary,
            enriched_degree=5,
        )
        p4_matrix = (
            p4_summary.get(
                "stage4_dtn_floquet_independent_matrix_stats"
            )
            or p4_summary.get("matrix_stats")
            or {}
        )
        p5_matrix = (
            p5_summary.get(
                "stage4_dtn_floquet_independent_matrix_stats"
            )
            or p5_summary.get("matrix_stats")
            or {}
        )
        common_identity = result.get("common_mesh_identity") or {}
        expected_resources = _Y_ONLY_GLOBAL_P5_CONTROL_CONTRACT
        checks.update(
            {
                "structured_axis_preflight_pass": (
                    requested_axis_cells == (6, 3, 10)
                    and structured_preflight.get("pass") is True
                    and structured_preflight.get("predicted_resources")
                    == expected_resources
                ),
                "structured_axis_exact_mesh_and_tag_identity": (
                    expected_identity is not None
                    and all(
                        common_identity.get(key)
                        == expected_identity.get(key)
                        for key in (
                            "partition_independent_mesh_sha256",
                            "cell_tag_sha256",
                            "facet_tag_sha256",
                        )
                    )
                ),
                "structured_axis_exact_topology_recorded": (
                    set(entries_by_degree) == {4, 5}
                    and all(
                        summary.get("mesh_cells_resolved")
                        == list(requested_axis_cells)
                        and summary.get("num_mesh_cells")
                        == expected_resources["num_mesh_cells"]
                        and (
                            summary.get("config") or {}
                        ).get("mesh_axis_cell_counts_requested")
                        == list(requested_axis_cells)
                        for summary in summaries
                    )
                ),
                "structured_axis_material_planes_aligned": all(
                    (
                        (audit.get("mesh_identity") or {}).get(
                            "material_plane_alignment"
                        )
                        or {}
                    ).get("all_aligned")
                    is True
                    for audit in resource_audits
                ),
                "structured_axis_global_p4_resources_exact": (
                    p4_summary.get("num_nedelec_dofs")
                    == expected_resources["coarse_p4_dofs"]
                    and p4_matrix.get("matrix_rows")
                    == expected_resources[
                        "coarse_p4_active_rows_with_dtn"
                    ]
                    and p4_matrix.get("matrix_nnz_used")
                    == expected_resources[
                        "coarse_p4_predicted_used_nnz"
                    ]
                ),
                "structured_axis_global_p5_resources_exact": (
                    p5_summary.get("num_nedelec_dofs")
                    == expected_resources["enriched_p5_dofs"]
                    and p5_matrix.get("matrix_rows")
                    == expected_resources[
                        "enriched_p5_active_rows_with_dtn"
                    ]
                    and p5_matrix.get("matrix_nnz_used")
                    == expected_resources[
                        "enriched_p5_predicted_used_nnz"
                    ]
                    and p5_summary.get("num_nedelec_dofs") <= 90000
                ),
                "structured_axis_full_explicit_true_residuals_le_1e-9": all(
                    isinstance(
                        (
                            (
                                summary.get("cell_static_condensation")
                                or {}
                            ).get("full_explicit_true_residual")
                            or {}
                        ).get("linear_system_relative_residual"),
                        (int, float),
                    )
                    and float(
                        (
                            (
                                summary.get("cell_static_condensation")
                                or {}
                            ).get("full_explicit_true_residual")
                            or {}
                        )["linear_system_relative_residual"]
                    )
                    <= 1.0e-9
                    for summary in summaries
                ),
                "structured_axis_enriched_orders_hash_bound": (
                    structured_orders.get("pass") is True
                    and isinstance(
                        structured_orders.get("sha256"),
                        str,
                    )
                    and len(structured_orders["sha256"]) == 64
                    and structured_orders.get("order_count") == 80
                ),
            }
        )
        focused_checks = _structured_axis_y_contract_checks(
            result,
            args=args,
            preflight=structured_preflight,
        )
        checks.update(
            {
                f"structured_axis_contract_{name}": passed
                for name, passed in focused_checks.items()
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_goal_dwr(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    """Qualify one fixed-hexa p4/p5 multi-goal localization run."""

    coarse = (result.get("coarse") or {}).get("summary") or {}
    enriched = (result.get("enriched") or {}).get("summary") or {}
    dwr = result.get("DWR") or {}
    goals = dwr.get("goals") or {}
    combined_reports = [
        dwr.get("combined_relative_R_T") or {},
        dwr.get("tolerance_normalized_R_T") or {},
    ]
    r5 = result.get("R5_control") or {}
    target = result.get("target_identity") or {}
    goal_reports = [
        goals.get(name) or {}
        for name in ("R00_total", "R_total", "T_total")
    ]
    enriched_residual = (dwr.get("residual") or {}).get(
        "enriched_solution_relative_residual_recomputed"
    )
    r5_closure = (r5.get("correction_energy") or {}).get(
        "relative_closure_error"
    )

    def qualified_goal(report: dict[str, Any]) -> bool:
        effectivity = report.get("absolute_effectivity")
        closure = report.get("signed_goal_change_closure")
        return bool(
            report.get("finite_nonnegative_cell_contributions") is True
            and (report.get("marking") or {}).get("captured_fraction", 0.0)
            >= float(args.theta) - 1.0e-12
            and isinstance(effectivity, (int, float))
            and math.isfinite(float(effectivity))
            and abs(float(effectivity) - 1.0) <= 1.0e-8
            and isinstance(closure, (int, float))
            and math.isfinite(float(closure))
            and abs(float(closure)) <= 1.0e-9
            and bool(report.get("mesh_geometry_sha256"))
            and bool(report.get("marked_geometry_sha256"))
        )

    def qualified_marker(report: dict[str, Any]) -> bool:
        return bool(
            report.get("finite_nonnegative_cell_contributions") is True
            and (report.get("marking") or {}).get("captured_fraction", 0.0)
            >= float(args.theta) - 1.0e-12
            and bool(report.get("mesh_geometry_sha256"))
            and bool(report.get("marked_geometry_sha256"))
        )

    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": (
            result.get("status") == "target_goal_weighted_two_level_pass"
        ),
        "result_pass": result.get("pass") is True,
        "fixed_rectangular_hexa_h10_identity": (
            target.get("geometry") == "Task034 fixed rectangular block grating"
            and target.get("mesh_backend")
            == "boundary-fitted conforming hexahedron"
            and abs(float(target.get("h_nm", -1.0)) - 10.0) <= 1.0e-12
        ),
        "p4_p5_pair_identity": (
            (result.get("coarse") or {}).get("degree") == 4
            and (result.get("enriched") or {}).get("degree") == 5
        ),
        "both_official_solves": (
            coarse.get("official_result") is True
            and enriched.get("official_result") is True
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in (coarse, enriched)
        ),
        "same_actual_hexa_mesh_cell_count": (
            coarse.get("mesh_cell_type_actual") == "hexahedron"
            and enriched.get("mesh_cell_type_actual") == "hexahedron"
            and coarse.get("num_mesh_cells") == 252
            and enriched.get("num_mesh_cells") == 252
        ),
        "enriched_residual_recomputed_le_1e-9": (
            isinstance(enriched_residual, (int, float))
            and float(enriched_residual) <= 1.0e-9
        ),
        "actual_adjoint_qualification_pass": (
            (dwr.get("adjoint_qualification") or {}).get("pass") is True
        ),
        "all_R00_R_T_goal_reports_qualified": (
            len(goals) >= 3
            and all(qualified_goal(report) for report in goal_reports)
        ),
        "both_multi_goal_reports_qualified": all(
            qualified_marker(report) for report in combined_reports
        ),
        "tolerance_normalization_authority_bound": (
            (
                (dwr.get("tolerance_normalized_R_T") or {}).get(
                    "normalization_authority"
                )
                or {}
            ).get("independent_adjoint_goals")
            == ["R_total", "T_total"]
        ),
        "R5_control_energy_closure": (
            isinstance(r5_closure, (int, float))
            and float(r5_closure) <= 1.0e-10
        ),
        "algebraic_localization_rejected": (
            (dwr.get("rejected_localization") or {}).get("decision")
            == "controlled_negative_partition_dependent"
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_adaptive(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    cycles = result.get("cycles") or []
    refinements = result.get("refinements") or []
    solves = [
        cycle["actual_r5"][level]["summary"]
        for cycle in cycles
        for level in ("coarse", "enriched")
    ]
    estimates = [cycle["actual_r5"]["R5"] for cycle in cycles]
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_r5_adaptive_cycles_pass",
        "result_pass": result.get("pass") is True,
        "requested_cycle_count_completed": (
            result.get("marked_cycles_completed") == args.adaptive_marked_cycles
            and len(cycles) == args.adaptive_marked_cycles + 1
        ),
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "all_fixed_reference_error_reductions_positive": (
            result.get("all_fixed_reference_error_reductions_positive") is True
        ),
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "all_cycle_mesh_audits_pass": bool(cycles)
        and all(cycle["mesh_audit"].get("pass") is True for cycle in cycles),
        "all_official_solves": bool(solves)
        and all(summary.get("official_result") is True for summary in solves),
        "all_true_residuals_le_1e-9": bool(solves)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "all_tetra_meshes": bool(solves)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "all_r5_energy_closures_le_1e-10": bool(estimates)
        and all(
            estimate["correction_energy"]["relative_closure_error"] <= 1.0e-10
            for estimate in estimates
        ),
        "all_dorfler_targets_captured": bool(estimates)
        and all(
            estimate["marking"]["captured_fraction"] >= args.theta
            for estimate in estimates
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_dwr_adaptive(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    cycles = result.get("cycles") or []
    refinements = result.get("refinements") or []
    solves = [
        cycle["goal_dwr"][level]["summary"]
        for cycle in cycles
        for level in ("coarse", "enriched")
    ]
    dwr_reports = [cycle["goal_dwr"]["DWR"] for cycle in cycles]
    goal_reports = [
        report["goals"][goal]
        for report in dwr_reports
        for goal in ("R_total", "T_total")
    ]
    marker_reports = [
        report[args.dwr_marker_policy]
        if args.dwr_marker_policy
        in {"combined_relative_R_T", "tolerance_normalized_R_T"}
        else report["goals"][args.dwr_marker_policy]
        for report in dwr_reports
    ]

    def normalized_authority_is_bound(report: dict[str, Any]) -> bool:
        authority = report.get("normalization_authority") or {}
        tolerances = authority.get("absolute_error_tolerances") or {}
        return bool(
            authority.get("control_key") == "p4_h7p5"
            and authority.get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
            and authority.get("independent_adjoint_goals")
            == ["R_total", "T_total"]
            and set(tolerances)
            == {"R_total", "T_total", "A_volume_total"}
            and all(
                isinstance(value, (int, float)) and float(value) > 0.0
                for value in tolerances.values()
            )
        )

    requested_theta_schedule = tuple(
        args.theta_schedule or (float(args.theta),) * int(args.dwr_adaptive_cycles)
    )
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_dwr_adaptive_cycles_pass",
        "result_pass": result.get("pass") is True,
        "requested_cycle_count_completed": (
            result.get("marked_cycles_completed") == args.dwr_adaptive_cycles
            and len(cycles) == args.dwr_adaptive_cycles + 1
        ),
        "requested_marker_policy": result.get("marker_policy")
        == args.dwr_marker_policy,
        "requested_periodic_edge_closure_policy": result.get(
            "periodic_edge_closure_policy"
        )
        == (
            "minimal_periodic_mates_only"
            if getattr(args, "minimal_periodic_edge_closure", False)
            else "full_periodic_boundary_synchronization"
        ),
        "requested_theta_schedule": tuple(
            float(value) for value in result.get("theta_schedule", [])
        )
        == requested_theta_schedule,
        "all_cycle_theta_values_bound": bool(cycles)
        and all(isinstance(cycle.get("theta"), (int, float)) for cycle in cycles),
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "all_fixed_reference_error_reductions_positive": result.get(
            "all_fixed_reference_error_reductions_positive"
        )
        is True,
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "all_cycle_mesh_audits_pass": bool(cycles)
        and all(cycle["mesh_audit"].get("pass") is True for cycle in cycles),
        "all_official_solves": bool(solves)
        and all(summary.get("official_result") is True for summary in solves),
        "all_true_residuals_le_1e-9": bool(solves)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "all_tetra_meshes": bool(solves)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "all_actual_adjoint_qualifications_pass": bool(dwr_reports)
        and all(report["adjoint_qualification"]["pass"] for report in dwr_reports),
        "all_goal_effectivities_unity": bool(goal_reports)
        and all(
            abs(report["absolute_effectivity"] - 1.0) <= 1.0e-8
            for report in goal_reports
        ),
        "all_goal_marking_geometry_hashes_present": bool(goal_reports)
        and all(bool(report.get("marked_geometry_sha256")) for report in goal_reports),
        "all_selected_marker_geometry_hashes_match": bool(cycles)
        and all(
            bool(cycle["marker"].get("marked_geometry_sha256"))
            and cycle["marker"]["marked_geometry_sha256"]
            == report.get("marked_geometry_sha256")
            for cycle, report in zip(cycles, marker_reports, strict=True)
        ),
        "all_selected_marker_counts_match": bool(cycles)
        and all(
            cycle["marker"].get("marked_count", 0) > 0
            and cycle["marker"]["marked_count"] == report["marking"].get("count")
            for cycle, report in zip(cycles, marker_reports, strict=True)
        ),
        "all_dorfler_targets_captured": bool(marker_reports)
        and all(
            report["marking"]["captured_fraction"] >= float(cycle["theta"])
            for report, cycle in zip(marker_reports, cycles, strict=True)
        ),
        "selected_multi_goal_normalization_bound": (
            args.dwr_marker_policy != "tolerance_normalized_R_T"
            or all(normalized_authority_is_bound(report) for report in marker_reports)
        ),
        "algebraic_localization_rejected": bool(dwr_reports)
        and all(
            report["rejected_localization"]["decision"]
            == "controlled_negative_partition_dependent"
            for report in dwr_reports
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_uniform(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    refinements = result.get("refinements") or []
    pair = result.get("actual_r5_pair") or {}
    solves = [
        (pair.get(level) or {}).get("summary") or {} for level in ("coarse", "enriched")
    ]
    r5 = pair.get("R5") or {}
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_uniform_tetra_control_pass",
        "result_pass": result.get("pass") is True,
        "requested_uniform_levels_completed": (
            result.get("refinement_levels") == args.uniform_refinement_levels
            and len(refinements) == args.uniform_refinement_levels
        ),
        "all_parent_cells_uniformly_marked": bool(refinements)
        and all(
            entry.get("uniform_all_parent_cells_marked") is True
            for entry in refinements
        ),
        "all_refinement_audits_pass": bool(refinements)
        and all(entry.get("pass") is True for entry in refinements),
        "final_mesh_audit_pass": (result.get("final_mesh_audit") or {}).get("pass")
        is True,
        "fixed_reference_identity": (
            (result.get("fixed_observable_reference") or {}).get("identity")
            == "best_available_discrete_reference_for_case093"
        ),
        "fixed_reference_hash_bound": (
            (result.get("fixed_observable_reference") or {}).get("record_sha256")
            == "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111"
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in solves
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in solves
        ),
        "both_tetra_meshes": all(
            summary.get("mesh_cell_type_actual") == "tetrahedron" for summary in solves
        ),
        "r5_energy_closure_le_1e-10": (
            (r5.get("correction_energy") or {}).get("relative_closure_error", 1.0)
            <= 1.0e-10
        ),
        "dorfler_target_captured": (
            (r5.get("marking") or {}).get("captured_fraction", 0.0) >= args.theta
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_common_mesh_sweep(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    angles = result.get("angle_results") or []
    replay = result.get("mesh_replay") or {}
    contract = replay.get("contract") or {}
    pairs = [entry.get("actual_r5_pair") or {} for entry in angles]
    summaries = [
        (pair.get(level) or {}).get("summary") or {}
        for pair in pairs
        for level in ("coarse", "enriched")
    ]
    requested = [float(value) for value in args.common_mesh_grazing_angles]
    hp_budget = result.get("hp_budget_evaluation")
    hp_budget_requested = getattr(args, "hp_dof_ceiling", None) is not None
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status")
        == "actual_common_mesh_angle_sweep_pass",
        "result_pass": result.get("pass") is True,
        "replay_pass": replay.get("pass") is True,
        "replay_record_hash_bound": (
            contract.get("record_sha256") == args.common_mesh_replay_sha256
        ),
        "replay_theta_bound": (
            contract.get("theta")
            == getattr(args, "common_mesh_replay_theta", 0.7)
        ),
        "replay_final_cell_count_bound": (
            (contract.get("final_mesh_identity") or {}).get("global_cell_count")
            == getattr(args, "common_mesh_replay_expected_final_cells", 1316)
        ),
        "single_in_memory_mesh_instance": (
            result.get("single_in_memory_mesh_instance") is True
            and replay.get("single_in_memory_mesh_instance") is True
        ),
        "requested_angles_completed": (
            [entry.get("grazing_angle_deg") for entry in angles] == requested
        ),
        "all_pairs_pass": bool(pairs)
        and all(pair.get("status") == "actual_global_r5_pass" for pair in pairs),
        "angle_identities_exact": bool(angles)
        and all(
            (pair.get("target_identity") or {}).get("grazing_angle_deg")
            == entry.get("grazing_angle_deg")
            and (pair.get("target_identity") or {}).get("incidence_theta_deg")
            == entry.get("incident_theta_deg")
            for entry, pair in zip(angles, pairs, strict=True)
        ),
        "all_official_solves": bool(summaries)
        and all(summary.get("official_result") is True for summary in summaries),
        "all_true_residuals_le_1e-9": bool(summaries)
        and all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in summaries
        ),
        "all_tetra_meshes": bool(summaries)
        and all(
            summary.get("mesh_cell_type_actual") == "tetrahedron"
            for summary in summaries
        ),
        "all_r5_energy_closures_le_1e-10": bool(pairs)
        and all(
            ((pair.get("R5") or {}).get("correction_energy") or {}).get(
                "relative_closure_error", 1.0
            )
            <= 1.0e-10
            for pair in pairs
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
            and all(pair.get("ordinary_default_changed") is False for pair in pairs)
        ),
    }
    if hp_budget_requested:
        checks.update(
            {
                "hp_budget_evaluation_present": isinstance(hp_budget, dict),
                "hp_dof_ceiling_bound": (
                    isinstance(hp_budget, dict)
                    and hp_budget.get("dof_ceiling") == args.hp_dof_ceiling
                ),
                "hp_accuracy_control_bound": (
                    isinstance(hp_budget, dict)
                    and (hp_budget.get("accuracy_control") or {}).get("key")
                    == args.hp_accuracy_control_key
                ),
                "hp_thresholds_not_relaxed": (
                    isinstance(hp_budget, dict)
                    and hp_budget.get("thresholds_relaxed") is False
                ),
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _fixed_trace_x_contract_checks(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    preflight: dict[str, Any],
) -> dict[str, bool]:
    """Pure identity/resource checks for the reviewed x-only candidate."""

    topology = _FIXED_TRACE_EXPLICIT_TOPOLOGY_CONTRACTS[(7, 2, 10)]
    identity = _EXPLICIT_AXIS_IDENTITY_CONTRACTS[(7, 2, 10)]
    candidate = result.get("candidate") or {}
    summary = candidate.get("summary") or {}
    config = summary.get("config") or {}
    target = result.get("target_identity") or {}
    resource = candidate.get("high_order_resource_audit") or {}
    mesh_identity = resource.get("mesh_identity") or {}
    matrix = summary.get("matrix_stats") or {}
    factor = resource.get("matrix_factor_resource") or {}
    dof_target = result.get("dof_target") or {}
    parent = result.get("directional_parent_authority") or {}
    predicted = preflight.get("predicted_resources") or {}

    def finite_positive(name: str, source: dict[str, Any]) -> bool:
        value = source.get(name)
        return bool(
            isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0.0
        )

    return {
        "cli_identity": (
            bool(args.fixed_trace_directional_recovery)
            and args.fixed_trace_directional_axis == "x"
            and tuple(args.structured_axis_cells or ()) == (7, 2, 10)
            and int(args.mpi_size) == 8
            and abs(float(args.h_nm) - 15.0) <= 1.0e-12
        ),
        "preflight_identity": (
            preflight.get("pass") is True
            and preflight.get("directional_axis") == "x"
            and preflight.get("structured_axis_cells_requested")
            == [7, 2, 10]
            and all(
                predicted.get(key) == value
                for key, value in topology.items()
            )
        ),
        "target_identity": (
            target.get("directional_axis") == "x"
            and target.get("mesh_axis_cell_counts_requested")
            == [7, 2, 10]
            and target.get("actual_mesh_cells_resolved")
            == [7, 2, 10]
            and target.get("directional_mesh_change_semantics")
            == "exact_material_fitted_remeshing_not_nested_refinement"
        ),
        "summary_topology_and_dofs": (
            summary.get("mesh_cells_resolved") == [7, 2, 10]
            and summary.get("num_mesh_cells") == 140
            and summary.get("num_nedelec_dofs") == 87195
            and config.get("mesh_axis_cell_counts_requested")
            == [7, 2, 10]
        ),
        "mesh_and_tag_identity": all(
            mesh_identity.get(key) == identity[key]
            for key in (
                "partition_independent_mesh_sha256",
                "cell_tag_sha256",
                "facet_tag_sha256",
            )
        ),
        "dof_target": (
            dof_target.get("active_full3d_equivalent_dofs") == 87195
            and dof_target.get("same_mesh_global_p6_dofs") == 98322
            and dof_target.get("minimum_le_90000") is True
            and dof_target.get(
                "inactive_p6_trace_modes_physically_absent"
            )
            is True
        ),
        "matrix_structure": (
            matrix.get("matrix_rows") == 19680
            and matrix.get("matrix_nnz_used") == 10728434
            and finite_positive("matrix_average_nnz_per_row", matrix)
            and finite_positive("matrix_maximum_nnz_per_row", matrix)
            and isinstance(
                matrix.get("matrix_nnz_allocated"),
                (int, float),
            )
            and int(matrix["matrix_nnz_allocated"]) <= 11065344
            and matrix.get("matrix_mallocs") == 0
        ),
        "factor_resource": (
            factor.get("factor_inventory_available") is True
            and finite_positive("factor_nnz", factor)
            and finite_positive("factor_average_row_width", factor)
            and finite_positive("factor_fill_ratio", factor)
        ),
        "no_parent_or_same_mesh_p6": (
            parent.get("status") == "not_required_primary_x"
            and parent.get("required") is False
            and result.get("same_mesh_global_p6_baseline", {}).get(
                "required"
            )
            is False
        ),
    }


def _qualify_fixed_trace(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    directional_recovery = bool(
        getattr(args, "fixed_trace_directional_recovery", False)
    )
    directional_axis = getattr(
        args,
        "fixed_trace_directional_axis",
        None,
    )
    channel_adjoint_mode = bool(
        getattr(
            args,
            "fixed_trace_channel_adjoint_diagnostic",
            False,
        )
    )
    port_diagnostic_mode = bool(
        getattr(args, "fixed_trace_dtn_quadrature_degree", None)
        is not None
        or int(
            getattr(args, "fixed_trace_dtn_evanescent_buffer", 0)
        )
        > 0
    )
    explicit_z_profile = getattr(
        args,
        "fixed_trace_explicit_z_profile",
        None,
    )
    topology = _fixed_trace_topology_contract(args)
    explicit_identity = (
        _EXPLICIT_Z_PROFILE_IDENTITY_CONTRACT
        if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
        else (
            None
            if getattr(args, "structured_axis_cells", None) is None
            else _EXPLICIT_AXIS_IDENTITY_CONTRACTS.get(
                tuple(args.structured_axis_cells)
            )
        )
    )
    expected_axis_counts = (
        [6, 2, 12]
        if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
        else (
            None
            if args.structured_axis_cells is None
            else list(args.structured_axis_cells)
        )
    )
    expected_directional_semantics = (
        "exact_h14_r5_slab_bisect_not_nested_refinement"
        if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
        else (
            "exact_material_fitted_remeshing_not_nested_refinement"
            if directional_recovery
            else "not_applicable"
        )
    )
    if explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE:
        from src.adaptivity.target_fixed_trace_candidate import (
            TASK035B_R5_SLAB_BISECT_Z_VALUES_NM,
        )

        expected_z_values = list(
            TASK035B_R5_SLAB_BISECT_Z_VALUES_NM
        )
    else:
        expected_z_values = None
    resource_preflight = getattr(
        args,
        "fixed_trace_resource_preflight",
        {},
    )
    candidate = result.get("candidate") or {}
    summary = candidate.get("summary") or {}
    resolved_config = summary.get("config") or {}
    resource_audit = candidate.get("high_order_resource_audit") or {}
    entity_audit = resource_audit.get("entity_dof_inventory") or {}
    cell_audit = summary.get("cell_static_condensation") or {}
    true_residual = cell_audit.get("full_explicit_true_residual") or {}
    matrix_stats = summary.get("matrix_stats") or {}
    predicted_resources = (
        resource_preflight.get("predicted_resources") or {}
    )
    matrix_factor_resource = (
        resource_audit.get("matrix_factor_resource") or {}
    )
    orientation = summary.get("nedelec_orientation_factor_stats") or {}
    element_audit = result.get("element_audit") or {}
    dof_target = result.get("dof_target") or {}
    scalar_comparison = result.get("observable_comparison") or {}
    channel_comparison = result.get("diffraction_channel_comparison") or {}
    field_gate = result.get("selected_field_interface_error_gate") or {}
    control = result.get("control_authority") or {}
    channel_reference = (
        result.get("significant_channel_reference_authority") or {}
    )
    directional_parent = result.get("directional_parent_authority") or {}
    global_p6_baseline = result.get("global_p6_baseline_authority") or {}
    same_mesh_baseline = result.get("same_mesh_global_p6_baseline") or {}
    resource_comparison = result.get("same_mesh_resource_comparison") or {}
    target_identity = result.get("target_identity") or {}
    directional_signal = result.get("directional_recovery_signal")
    channel_adjoint = result.get("channel_adjoint_diagnostic")
    port_diagnostic = result.get("port_diagnostic")
    port_scaling_contract = (
        (port_diagnostic or {}).get(
            "auxiliary_coordinate_scaling_contract"
        )
        or {}
    )
    actual_port_scaling = (
        port_scaling_contract.get("actual_scaling") or {}
    )
    preflight_port_scaling = (
        resource_preflight.get("port_basis_scaling_preflight") or {}
    )

    def positive_close(left: Any, right: Any) -> bool:
        return bool(
            isinstance(left, (int, float))
            and isinstance(right, (int, float))
            and not isinstance(left, bool)
            and not isinstance(right, bool)
            and math.isfinite(float(left))
            and math.isfinite(float(right))
            and float(left) > 0.0
            and float(right) > 0.0
            and math.isclose(
                float(left),
                float(right),
                rel_tol=2.0e-12,
                abs_tol=0.0,
            )
        )

    accepted_statuses = {
        "actual_fixed_trace_candidate_pass",
        "actual_fixed_trace_controlled_negative",
    }
    if channel_adjoint_mode:
        accepted_statuses = {
            "actual_fixed_trace_channel_adjoint_diagnostic_pass",
        }
    elif port_diagnostic_mode:
        accepted_statuses = {
            "actual_fixed_trace_port_diagnostic_positive",
            "actual_fixed_trace_port_diagnostic_controlled_negative",
        }
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "resource_preflight_pass": (
            resource_preflight.get("pass") is True
            and topology is not None
            and all(
                (
                    resource_preflight.get(
                        "predicted_resources"
                    )
                    or {}
                ).get(key)
                == value
                for key, value in topology.items()
            )
        ),
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status_is_positive_or_controlled_negative": (
            result.get("status") in accepted_statuses
        ),
        "execution_integrity_pass": result.get("pass") is True,
        "accuracy_classification_recorded": isinstance(
            result.get("candidate_accuracy_pass"),
            bool,
        ),
        "channel_adjoint_mode_classified": (
            (
                result.get("channel_adjoint_diagnostic_only") is True
                and result.get("formal_candidate_eligible") is False
                and isinstance(channel_adjoint, dict)
                and channel_adjoint.get("pass") is True
                and (
                    channel_adjoint.get("adjoints") or {}
                ).get("goal_count")
                == 16
                and len(
                    channel_adjoint.get("recovered_full_duals") or {}
                )
                == 16
                and all(
                    (
                        row.get("entity_sensitivity_proxy") or {}
                    ).get("actual_dwr_indicator")
                    is False
                    and (
                        row.get("entity_sensitivity_proxy") or {}
                    ).get("lane_b_formal_selection_authorized")
                    is False
                    for row in (
                        channel_adjoint.get(
                            "recovered_full_duals"
                        )
                        or {}
                    ).values()
                )
            )
            if channel_adjoint_mode
            else (
                result.get("channel_adjoint_diagnostic_only") is False
                and channel_adjoint is None
            )
        ),
        "port_diagnostic_mode_classified": (
            (
                result.get("port_diagnostic_only") is True
                and result.get("formal_candidate_eligible")
                == bool(
                    result.get("pass")
                    and result.get("candidate_accuracy_pass")
                )
                and isinstance(port_diagnostic, dict)
                and port_diagnostic.get("pass") is True
                and port_diagnostic.get("formal_candidate_eligible")
                == bool(
                    result.get("pass")
                    and result.get("candidate_accuracy_pass")
                )
                and port_diagnostic.get("classification_complete")
                is True
                and port_diagnostic.get(
                    "operator_identity_with_frozen_reference"
                )
                is False
                and port_diagnostic.get("requested_quadrature_degree")
                == args.fixed_trace_dtn_quadrature_degree
                and port_diagnostic.get("effective_quadrature_degree")
                == (
                    args.fixed_trace_dtn_quadrature_degree
                    if args.fixed_trace_dtn_quadrature_degree
                    is not None
                    else 25
                )
                and port_diagnostic.get("evanescent_buffer")
                == args.fixed_trace_dtn_evanescent_buffer
                and port_diagnostic.get("mode_count")
                == (
                    resource_preflight.get("predicted_resources")
                    or {}
                ).get("dtn_auxiliary_rows")
                and port_diagnostic.get("evanescent_mode_count")
                == (
                    resource_preflight.get("predicted_resources")
                    or {}
                ).get("dtn_evanescent_rows")
                and summary.get("stage4_dtn_surface_quadrature_degree")
                == port_diagnostic.get("effective_quadrature_degree")
                and summary.get("stage4_dtn_evanescent_buffer")
                == args.fixed_trace_dtn_evanescent_buffer
                and isinstance(
                    (
                        port_diagnostic.get("seed_recovery_signal")
                        or {}
                    ).get("positive_signal"),
                    bool,
                )
                and (
                    port_diagnostic.get("seed_recovery_signal")
                    or {}
                ).get("thresholds_relaxed")
                is False
                and port_diagnostic.get("thresholds_relaxed") is False
            )
            if port_diagnostic_mode
            else (
                result.get("port_diagnostic_only") is False
                and port_diagnostic is None
            )
        ),
        "port_auxiliary_scaling_execution_identity": (
            (
                port_scaling_contract.get("pass") is True
                and port_scaling_contract.get("status")
                == "actual_boundary_referenced_scaling_pass"
                and port_scaling_contract.get("evanescent_buffer")
                == args.fixed_trace_dtn_evanescent_buffer
                and actual_port_scaling.get("status")
                == "boundary_referenced_evanescent_buffer_active"
                and actual_port_scaling.get("ordinary_default_changed")
                is False
                and actual_port_scaling.get("solver_coordinate")
                == "a_solver=exp(i*kz*z_port)*a_global_z"
                and actual_port_scaling.get(
                    "official_output_coordinate"
                )
                == "historical_global_z"
                and actual_port_scaling.get("scaled_mode_count")
                == preflight_port_scaling.get(
                    "boundary_referenced_mode_count"
                )
                and positive_close(
                    actual_port_scaling.get(
                        "minimum_abs_coordinate_scale"
                    ),
                    preflight_port_scaling.get(
                        "minimum_abs_boundary_phase"
                    ),
                )
                and positive_close(
                    actual_port_scaling.get(
                        "minimum_assembly_projection_denominator"
                    ),
                    preflight_port_scaling.get(
                        "minimum_assembly_projection_denominator"
                    ),
                )
            )
            if args.fixed_trace_dtn_evanescent_buffer > 0
            else (
                (
                    port_scaling_contract.get("pass") is True
                    and port_scaling_contract.get("status")
                    == "not_requested"
                    and port_scaling_contract.get("actual_scaling") is None
                )
                if port_diagnostic_mode
                else True
            )
        ),
        "directional_signal_classified": (
            isinstance(directional_signal, dict)
            and isinstance(directional_signal.get("positive_signal"), bool)
            and directional_signal.get("thresholds_relaxed") is False
            if directional_recovery
            else directional_signal is None
        ),
        "official_candidate": summary.get("official_result") is True,
        "candidate_mpi8": summary.get("mpi_size") == 8,
        "fixed_rectangular_directional_topology_identity": (
            topology is not None
            and
            target_identity.get("geometry")
            == "Task034 fixed rectangular block grating"
            and summary.get("mesh_cell_type_actual") == "hexahedron"
            and summary.get("num_mesh_cells")
            == topology["num_mesh_cells"]
            and summary.get("mesh_cells_resolved")
            == topology["mesh_cells_resolved"]
            and abs(
                float(candidate.get("h_nm", -1.0)) - float(args.h_nm)
            )
            <= 1.0e-12
            and target_identity.get("trace_degree")
            == args.fixed_trace_degree
            and target_identity.get("interior_degree")
            == args.fixed_interior_degree
            and target_identity.get("directional_axis")
            == directional_axis
            and target_identity.get(
                "directional_mesh_change_semantics"
            )
            == expected_directional_semantics
            and target_identity.get(
                "mesh_axis_cell_counts_requested"
            )
            == expected_axis_counts
            and resolved_config.get(
                "mesh_axis_cell_counts_requested"
            )
            == expected_axis_counts
            and target_identity.get("explicit_z_profile")
            == explicit_z_profile
            and (
                target_identity.get(
                    "mesh_axis_z_values_requested"
                )
                == resolved_config.get(
                    "mesh_axis_z_values_requested"
                )
            )
        ),
        "control_authority_hash_bound": (
            control.get("sha256") == args.fixed_trace_control_sha256
        ),
        "significant_channel_reference_v1_hash_bound": (
            channel_reference.get("sha256")
            == args.fixed_trace_significant_channel_reference_sha256
            and channel_reference.get("frozen_channel_count") == 12
            and channel_reference.get("unchanged_v0_gate") is True
            and channel_reference.get(
                "numerical_convergence_band_used_as_gate"
            )
            is False
        ),
        "directional_parent_requirement_classified": (
            (
                directional_parent.get("status")
                == "not_required_primary_x"
                and directional_parent.get("required") is False
                and args.fixed_trace_directional_parent_record is None
            )
            if directional_recovery and directional_axis == "x"
            else (
                directional_parent.get("status")
                == "qualified_positive_h14_parent"
                and directional_parent.get("required") is True
                and directional_parent.get("sha256")
                == args.fixed_trace_directional_parent_sha256
            )
            if directional_recovery
            and abs(float(args.h_nm) - 13.0) <= 1.0e-12
            else (
                directional_parent.get("status")
                == "not_required_primary_h14"
                and directional_parent.get("required") is False
            )
            if directional_recovery
            else (
                directional_parent.get("status")
                == "not_applicable_h15_seed"
                and directional_parent.get("required") is False
            )
        ),
        "global_p6_baseline_requirement_classified": (
            (
                global_p6_baseline.get("status")
                == "not_run_directional_recovery"
                and global_p6_baseline.get("required") is False
                and args.fixed_trace_global_p6_baseline_record is None
            )
            if directional_recovery
            else (
                global_p6_baseline.get("sha256")
                == args.fixed_trace_global_p6_baseline_sha256
            )
        ),
        "same_mesh_baseline_requirement_classified": (
            (
                same_mesh_baseline.get("status")
                == "not_run_directional_recovery"
                and same_mesh_baseline.get("required") is False
                and same_mesh_baseline.get("pass") is None
            )
            if directional_recovery
            else (
                same_mesh_baseline.get("pass") is True
                and same_mesh_baseline.get("checks")
                == {
                    "partition_independent_mesh_sha256": True,
                    "cell_tag_sha256": True,
                    "facet_tag_sha256": True,
                }
            )
        ),
        "candidate_mesh_and_tag_hashes_present": all(
            (resource_audit.get("mesh_identity") or {}).get(key)
            for key in (
                "partition_independent_mesh_sha256",
                "cell_tag_sha256",
                "facet_tag_sha256",
            )
        ),
        "explicit_mesh_and_tag_hashes_match_frozen_identity": (
            explicit_identity is None
            or all(
                (resource_audit.get("mesh_identity") or {}).get(key)
                == explicit_identity[key]
                for key in (
                    "partition_independent_mesh_sha256",
                    "cell_tag_sha256",
                    "facet_tag_sha256",
                )
            )
        ),
        "explicit_z_profile_contract": (
            (
                explicit_z_profile == _FIXED_TRACE_EXPLICIT_Z_PROFILE
                and bool(target_identity.get("r5_slab_bisect"))
                and target_identity.get("mesh_axis_z_values_requested")
                == expected_z_values
                and resolved_config.get("mesh_axis_z_values_requested")
                == expected_z_values
                and resolved_config.get("mesh_axis_z_profile_requested")
                == _FIXED_TRACE_EXPLICIT_Z_PROFILE
                and summary.get("mesh_spacing_mode_resolved")
                == "boundary_fitted_exact_counts_explicit_z"
                and (
                    resource_preflight.get("axis_plan") or {}
                ).get("axis_sha256")
                == _EXPLICIT_Z_PROFILE_IDENTITY_CONTRACT[
                    "axis_sha256"
                ]
                and resource_preflight.get("explicit_z_profile")
                == _FIXED_TRACE_EXPLICIT_Z_PROFILE
            )
            if explicit_z_profile is not None
            else (
                not bool(target_identity.get("r5_slab_bisect"))
                and target_identity.get(
                    "mesh_axis_z_values_requested"
                )
                is None
                and resolved_config.get(
                    "mesh_axis_z_values_requested"
                )
                is None
                and resolved_config.get(
                    "mesh_axis_z_profile_requested"
                )
                is None
            )
        ),
        "exact_sequence_space": (
            element_audit.get("pass") is True
            and element_audit.get("both_high_and_low_exact_sequence_pass")
            is True
            and element_audit.get("trace_degree") == args.fixed_trace_degree
            and element_audit.get("interior_degree")
            == args.fixed_interior_degree
            and element_audit.get("low_interior_degree")
            == args.fixed_trace_degree
        ),
        "physical_p5_trace_p6_interior_space": (
            resolved_config.get("nedelec_trace_degree_resolved")
            == args.fixed_trace_degree
            and resolved_config.get("nedelec_interior_degree_resolved")
            == args.fixed_interior_degree
            and isinstance(element_audit.get("custom_dimension"), int)
            and isinstance(element_audit.get("standard_high_dimension"), int)
            and element_audit.get("custom_dimension")
            < element_audit.get("standard_high_dimension")
        ),
        "full3d_equivalent_dof_target": (
            topology is not None
            and summary.get("num_nedelec_dofs")
            == topology["candidate_dofs"]
            and dof_target.get("active_full3d_equivalent_dofs")
            == topology["candidate_dofs"]
            and dof_target.get("same_mesh_global_p6_dofs")
            == topology["global_p6_dofs"]
            and dof_target.get("minimum_le_90000") is True
            and dof_target.get("preferred_65000_to_75000")
            == (not directional_recovery)
            and dof_target.get("inactive_p6_trace_modes_physically_absent")
            is True
        ),
        "no_full_global_or_trace_matrix_allocated": (
            cell_audit.get("full_global_matrix_allocated") is False
            and cell_audit.get("full_trace_matrix_allocated") is False
            and cell_audit.get("inactive_max_p_rows_retained_in_matrix")
            is False
            and cell_audit.get("assembly_cost_avoided") is True
        ),
        "physically_reduced_matrix_rows": (
            isinstance(matrix_stats.get("matrix_rows"), int)
            and matrix_stats.get("matrix_rows") == cell_audit.get("matrix_rows")
            and topology is not None
            and matrix_stats.get("matrix_rows")
            == (
                resource_preflight.get("predicted_resources") or {}
            ).get("expected_active_rows")
            and matrix_stats.get("matrix_rows") < topology["candidate_dofs"]
        ),
        "matrix_nnz_and_row_width_measured": (
            all(
                isinstance(matrix_stats.get(name), (int, float))
                and math.isfinite(float(matrix_stats[name]))
                and float(matrix_stats[name]) > 0.0
                for name in (
                    "matrix_nnz_used",
                    "matrix_nnz_allocated",
                    "matrix_average_nnz_per_row",
                    "matrix_maximum_nnz_per_row",
                )
            )
            and isinstance(
                predicted_resources.get("dtn_auxiliary_rows"),
                (int, float),
            )
            and isinstance(
                predicted_resources.get(
                    "port_diagnostic_predicted_used_nnz"
                ),
                (int, float),
            )
            and isinstance(
                predicted_resources.get(
                    "port_diagnostic_safe_allocated_nnz_upper"
                ),
                (int, float),
            )
            and (
                int(predicted_resources["dtn_auxiliary_rows"])
                != 80
                or int(matrix_stats["matrix_nnz_used"])
                == int(
                    predicted_resources[
                        "port_diagnostic_predicted_used_nnz"
                    ]
                )
            )
            and int(matrix_stats["matrix_nnz_used"])
            <= int(
                predicted_resources[
                    "port_diagnostic_safe_allocated_nnz_upper"
                ]
            )
            and int(matrix_stats["matrix_nnz_allocated"])
            <= int(
                predicted_resources[
                    "port_diagnostic_safe_allocated_nnz_upper"
                ]
            )
            and isinstance(
                matrix_stats.get("matrix_mallocs"),
                (int, float),
            )
            and int(matrix_stats["matrix_mallocs"]) == 0
        ),
        "factor_inventory_measured": (
            (
                summary.get("stage4_dtn_factor_inventory") or {}
            ).get("available")
            is True
            and matrix_factor_resource.get(
                "factor_inventory_available"
            )
            is True
            and all(
                isinstance(
                    matrix_factor_resource.get(name),
                    (int, float),
                )
                and math.isfinite(
                    float(matrix_factor_resource[name])
                )
                and float(matrix_factor_resource[name]) > 0.0
                for name in (
                    "factor_nnz",
                    "factor_average_row_width",
                    "factor_fill_ratio",
                )
            )
        ),
        "resource_comparison_authority_classified": (
            (
                resource_comparison.get("status")
                == "derived_dof_only_directional_recovery"
                and resource_comparison.get(
                    "same_mesh_global_p6_measured"
                )
                is False
            )
            if directional_recovery
            else (
                resource_comparison.get("schema_version")
                == "task035b.fixed-trace-resource-comparison.v1"
                and (
                    (resource_comparison.get("metrics") or {}).get(
                        "full3d_equivalent_dofs"
                    )
                    or {}
                ).get("global_p6")
                == topology["global_p6_dofs"]
                and (
                    (resource_comparison.get("metrics") or {}).get(
                        "active_rows"
                    )
                    or {}
                ).get("candidate")
                == matrix_stats.get("matrix_rows")
                and isinstance(
                    (
                        (resource_comparison.get("metrics") or {}).get(
                            "factor_nnz"
                        )
                        or {}
                    ).get("compression_ratio"),
                    (int, float),
                )
            )
        ),
        "solver_lifecycle_matches_mode": (
            (
                summary.get(
                    "direct_release_solver_before_postprocess"
                )
                is False
                and summary.get(
                    "solver_objects_released_before_postprocess"
                )
                is False
                and (
                    (channel_adjoint or {}).get(
                        "dual_recovery_context_audit"
                    )
                    or {}
                ).get("exact_augmented_interior_coupling")
                is True
            )
            if channel_adjoint_mode
            else (
                summary.get(
                    "direct_release_solver_before_postprocess"
                )
                is True
                and summary.get(
                    "solver_objects_released_before_postprocess"
                )
                is True
                and (summary.get("solver_release_audit") or {}).get(
                    "petsc_garbage_cleanup_called"
                )
                is True
            )
        ),
        "full_true_residual_le_1e-9": (
            isinstance(
                true_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(true_residual["linear_system_relative_residual"])
            <= 1.0e-9
            and isinstance(
                summary.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
        ),
        "entity_dof_audit_pass": entity_audit.get("pass") is True,
        "periodic_trace_identity_pass": (
            summary.get("floquet_constraint_mode_resolved")
            == "topological_trace_p5"
            and summary.get("floquet_num_constraints", 0) > 0
            and summary.get("floquet_x_face_mismatch") == 0.0
            and summary.get("floquet_y_face_mismatch") == 0.0
            and summary.get("floquet_edge_corner_mismatch") == 0.0
            and summary.get("max_face_pairing_coordinate_error") == 0.0
        ),
        "exact_orientation_path": (
            orientation.get("uses_exact_basix_entity_transforms") is True
            and orientation.get("uses_local_moment_fit") is False
            and orientation.get("mapping_kind")
            == "distributed_exact_topological_trace_p5"
        ),
        "material_tag_geometry_alignment_pass": (
            (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
            and set((summary.get("domain_tag_volumes") or {}))
            >= {"air", "substrate", "grating"}
        ),
        "scalar_same_code_comparison_recorded": (
            scalar_comparison.get("schema_version")
            == "task035b.cross-mesh-observable-comparison.v1"
            and isinstance(scalar_comparison.get("pass"), bool)
        ),
        "diffraction_power_and_amplitude_comparison_recorded": (
            channel_comparison.get("schema_version")
            == (
                "task035b.significant-channel-reference-v1-comparison.v1"
            )
            and channel_comparison.get(
                "frozen_significant_channel_count"
            )
            == 12
            and channel_comparison.get(
                "significant_power_pass_count"
            )
            in range(13)
            and channel_comparison.get(
                "significant_complex_amplitude_pass_count"
            )
            in range(13)
            and isinstance(channel_comparison.get("pass"), bool)
            and channel_comparison.get(
                "numerical_convergence_band_used_as_gate"
            )
            is False
            and channel_comparison.get("thresholds_relaxed") is False
        ),
        "selected_field_interface_comparison_recorded": (
            field_gate.get("status")
            == "measured_frozen_physical_gauss_probes"
            and field_gate.get("no_threshold_relaxation") is True
            and isinstance(field_gate.get("pass"), bool)
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
    }
    if directional_recovery and directional_axis == "x":
        focused_checks = _fixed_trace_x_contract_checks(
            result,
            args=args,
            preflight=resource_preflight,
        )
        checks.update(
            {
                f"x_directional_contract_{name}": passed
                for name, passed in focused_checks.items()
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _qualify_regionwise_p(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    candidate = result.get("candidate") or {}
    summary = candidate.get("summary") or {}
    resource_audit = candidate.get("high_order_resource_audit") or {}
    entity_audit = resource_audit.get("entity_dof_inventory") or {}
    cell_audit = summary.get("cell_static_condensation") or {}
    matrix_stats = summary.get("matrix_stats") or {}
    orientation = summary.get("nedelec_orientation_factor_stats") or {}
    field_gate = result.get("selected_field_interface_error_gate") or {}
    scalar_comparison = result.get("observable_comparison") or {}
    channel_comparison = result.get("diffraction_channel_comparison") or {}
    classifier = result.get("classifier_authority") or {}
    control = result.get("control_authority") or {}
    target_identity = result.get("target_identity") or {}
    expected_high_cells = getattr(
        args,
        "regionwise_p_high_cell_count",
        None,
    )
    if expected_high_cells is None:
        expected_high_cells = classifier.get("high_canonical_cell_count")
    active_dof_budget = classifier.get("active_full3d_equivalent_dofs")
    accepted_statuses = {
        "actual_regionwise_p_candidate_pass",
        "actual_regionwise_p_controlled_negative",
    }
    true_residual = cell_audit.get("full_explicit_true_residual") or {}
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status_is_positive_or_controlled_negative": (
            result.get("status") in accepted_statuses
        ),
        "execution_integrity_pass": result.get("pass") is True,
        "official_candidate": summary.get("official_result") is True,
        "fixed_rectangular_hexa_h10_identity": (
            target_identity.get("geometry")
            == "Task034 fixed rectangular block grating"
            and summary.get("mesh_cell_type_actual") == "hexahedron"
            and summary.get("num_mesh_cells") == 252
            and abs(float(candidate.get("h_nm", -1.0)) - 10.0) <= 1.0e-12
            and target_identity.get("trace_degree")
            == getattr(args, "regionwise_p_trace_degree", 4)
            and target_identity.get("low_interior_degree")
            == getattr(args, "regionwise_p_low_interior_degree", 4)
            and target_identity.get("high_interior_degree") == 6
        ),
        "classifier_authority_hash_bound": (
            classifier.get("sha256") == args.regionwise_p_classifier_sha256
        ),
        "control_authority_hash_bound": (
            control.get("sha256") == args.regionwise_p_control_sha256
        ),
        "regionwise_geometry_hash_bound": (
            cell_audit.get("regionwise_mesh_geometry_sha256")
            == target_identity.get("mesh_geometry_sha256")
        ),
        "regionwise_cell_classification_exact": (
            isinstance(expected_high_cells, int)
            and cell_audit.get("regionwise_interior_p_active") is True
            and cell_audit.get("regionwise_high_cell_count")
            == expected_high_cells
            and cell_audit.get("regionwise_low_cell_count")
            == 252 - expected_high_cells
        ),
        "active_full3d_equivalent_budget_le_90k": (
            isinstance(active_dof_budget, int)
            and active_dof_budget <= 90000
            and cell_audit.get("active_full3d_equivalent_dofs")
            == active_dof_budget
        ),
        "inactive_p6_rows_not_retained": (
            cell_audit.get("inactive_max_p_rows_retained_in_matrix") is False
        ),
        "no_full_global_or_trace_matrix_allocated": (
            cell_audit.get("full_global_matrix_allocated") is False
            and cell_audit.get("full_trace_matrix_allocated") is False
        ),
        "low_cells_use_direct_p4_kernel": (
            cell_audit.get("regionwise_low_cell_kernel_compiled_directly") is True
        ),
        "physically_reduced_matrix_rows": (
            isinstance(matrix_stats.get("matrix_rows"), int)
            and matrix_stats.get("matrix_rows") == cell_audit.get("matrix_rows")
            and isinstance(active_dof_budget, int)
            and matrix_stats.get("matrix_rows") < active_dof_budget
        ),
        "matrix_nnz_and_row_width_measured": (
            isinstance(matrix_stats.get("matrix_nnz_used"), (int, float))
            and matrix_stats.get("matrix_nnz_used", 0.0) > 0.0
            and isinstance(
                matrix_stats.get("matrix_average_nnz_per_row"), (int, float)
            )
            and isinstance(
                matrix_stats.get("matrix_maximum_nnz_per_row"), (int, float)
            )
        ),
        "factor_inventory_measured": (
            (summary.get("stage4_dtn_factor_inventory") or {}).get("available")
            is True
        ),
        "full_true_residual_le_1e-9": (
            isinstance(
                true_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(true_residual["linear_system_relative_residual"]) <= 1.0e-9
            and isinstance(
                summary.get("linear_system_relative_residual"), (int, float)
            )
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
        ),
        "entity_dof_audit_pass": entity_audit.get("pass") is True,
        "periodic_trace_identity_pass": (
            summary.get("floquet_num_constraints", 0) > 0
            and summary.get("floquet_x_face_mismatch") == 0.0
            and summary.get("floquet_y_face_mismatch") == 0.0
            and summary.get("floquet_edge_corner_mismatch") == 0.0
            and summary.get("max_face_pairing_coordinate_error") == 0.0
        ),
        "exact_orientation_path": (
            orientation.get("uses_exact_basix_entity_transforms") is True
            and orientation.get("uses_local_moment_fit") is False
        ),
        "material_tag_geometry_alignment_pass": (
            (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
            and set((summary.get("domain_tag_volumes") or {}))
            >= {"air", "substrate", "grating"}
        ),
        "scalar_same_code_comparison_recorded": (
            scalar_comparison.get("schema_version")
            == "task035b.regionwise-p-observable-comparison.v1"
            and isinstance(
                scalar_comparison.get("all_scalar_same_code_bands_pass"), bool
            )
            and isinstance(
                scalar_comparison.get(
                    "normalized_R_T_Aclosure_vector_pass"
                ),
                bool,
            )
        ),
        "diffraction_power_and_amplitude_comparison_recorded": (
            channel_comparison.get("channel_count") == 80
            and isinstance(channel_comparison.get("pass"), bool)
        ),
        "selected_field_interface_comparison_recorded": (
            field_gate.get("status")
            == "measured_common_native_visualization_points"
            and field_gate.get("no_threshold_relaxation") is True
            and isinstance(field_gate.get("pass"), bool)
        ),
        "ordinary_default_unchanged": (
            result.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _select_qualifier(args: argparse.Namespace):
    """Select the formal record qualifier for the mutually exclusive mode."""

    if args.fixed_trace_control_record is not None:
        return _qualify_fixed_trace
    if args.regionwise_p_classifier_record is not None:
        return _qualify_regionwise_p
    if args.common_mesh_replay_record is not None:
        return _qualify_common_mesh_sweep
    if args.goal_dwr_only:
        return _qualify_goal_dwr
    if args.dwr_adaptive_cycles:
        return _qualify_dwr_adaptive
    if args.adaptive_marked_cycles:
        return _qualify_adaptive
    if args.uniform_refinement_levels:
        return _qualify_uniform
    return _qualify


def _run_parent(args: argparse.Namespace) -> int:
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task035 effective WSL memory limit is unreadable.")
    if args.warning_gib is None:
        args.warning_gib = float(effective["warning_bytes"]) / GIB
    if args.terminate_gib is None:
        args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if not 0.0 < args.warning_gib < args.terminate_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    source_before = _source_provenance(args)
    pre_run_status = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    if pre_run_status:
        raise SystemExit(
            "Task035 formal run requires a clean local worktree even when "
            "--verified-clean-sha is supplied."
        )
    source_before["local_git_clean_preflight"] = True
    preflight = _memory_snapshot()
    free_bytes = preflight["artifact_filesystem_free_bytes"]
    if free_bytes < 10 * GIB:
        raise SystemExit(
            "Task035 actual R5 requires at least 10 GiB free artifact space."
        )
    if args.common_mesh_replay_record is not None:
        replay_path = args.common_mesh_replay_record
        if not replay_path.is_absolute():
            replay_path = ROOT / replay_path
        if not replay_path.is_file():
            raise SystemExit(f"common-mesh replay record not found: {replay_path}")
        args.common_mesh_replay_record = replay_path.resolve()
    if args.regionwise_p_classifier_record is not None:
        for path_name, sha_name in (
            (
                "regionwise_p_classifier_record",
                "regionwise_p_classifier_sha256",
            ),
            ("regionwise_p_control_record", "regionwise_p_control_sha256"),
        ):
            authority_path = getattr(args, path_name)
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            if not authority_path.is_file():
                raise SystemExit(
                    f"regionwise-p authority not found: {authority_path}"
                )
            expected_sha = getattr(args, sha_name).lower()
            actual_sha = _sha256(authority_path)
            if actual_sha != expected_sha:
                raise SystemExit(
                    f"regionwise-p authority SHA256 mismatch for {authority_path}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )
            setattr(args, path_name, authority_path.resolve())
            setattr(args, sha_name, expected_sha)
    if args.fixed_trace_control_record is not None:
        authority_pairs = [
            (
                "fixed_trace_control_record",
                "fixed_trace_control_sha256",
            ),
            (
                "fixed_trace_significant_channel_reference_record",
                "fixed_trace_significant_channel_reference_sha256",
            ),
        ]
        if args.fixed_trace_global_p6_baseline_record is not None:
            authority_pairs.append(
                (
                "fixed_trace_global_p6_baseline_record",
                "fixed_trace_global_p6_baseline_sha256",
                )
            )
        if args.fixed_trace_directional_parent_record is not None:
            authority_pairs.append(
                (
                    "fixed_trace_directional_parent_record",
                    "fixed_trace_directional_parent_sha256",
                )
            )
        for path_name, sha_name in authority_pairs:
            authority_path = getattr(args, path_name)
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            if not authority_path.is_file():
                raise SystemExit(
                    f"fixed-trace authority not found: {authority_path}"
                )
            expected_sha = getattr(args, sha_name).lower()
            actual_sha = _sha256(authority_path)
            if actual_sha != expected_sha:
                raise SystemExit(
                    "fixed-trace authority SHA256 mismatch for "
                    f"{authority_path}: expected {expected_sha}, got {actual_sha}"
                )
            setattr(args, path_name, authority_path.resolve())
            setattr(args, sha_name, expected_sha)
    if args.record is not None:
        args.record = _resolve_new_record_path(
            args.record,
            input_authorities=(
                args.fixed_trace_control_record,
                args.fixed_trace_global_p6_baseline_record,
                args.fixed_trace_significant_channel_reference_record,
                args.fixed_trace_directional_parent_record,
                args.regionwise_p_classifier_record,
                args.regionwise_p_control_record,
                args.common_mesh_replay_record,
            ),
        )
    if args.fixed_trace_control_record is not None:
        args.fixed_trace_resource_preflight = (
            _fixed_trace_resource_preflight(args)
        )
        if args.fixed_trace_resource_preflight["pass"] is not True:
            failed_checks = [
                name
                for name, passed in (
                    args.fixed_trace_resource_preflight.get("checks")
                    or {}
                ).items()
                if not passed
            ]
            scaling_status = (
                args.fixed_trace_resource_preflight.get(
                    "port_basis_scaling_preflight"
                )
                or {}
            ).get("status")
            raise SystemExit(
                "fixed-trace topology/resource preflight failed: "
                f"{failed_checks}; port basis status={scaling_status}. "
                "Do not start the PDE until the selected port-coordinate "
                "basis is qualified."
            )
    elif args.structured_axis_cells is not None:
        args.structured_axis_resource_preflight = (
            _structured_axis_global_control_preflight(args)
        )
        if args.structured_axis_resource_preflight["pass"] is not True:
            failed_checks = [
                name
                for name, passed in (
                    args.structured_axis_resource_preflight.get("checks")
                    or {}
                ).items()
                if not passed
            ]
            raise SystemExit(
                "structured-axis global-p control preflight failed: "
                f"{failed_checks}. Do not start the PDE."
            )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.fixed_trace_control_record is not None:
        run_label = (
            f"hexahedron_fixed_p{args.fixed_trace_degree}trace_"
            f"p{args.fixed_interior_degree}interior_h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
        if args.fixed_trace_directional_recovery:
            run_label += (
                f"_directional_{args.fixed_trace_directional_axis}"
            )
        if args.fixed_trace_explicit_z_profile is not None:
            run_label += f"_{args.fixed_trace_explicit_z_profile}"
        if args.fixed_trace_channel_adjoint_diagnostic:
            run_label += "_channel_adjoints"
        if args.fixed_trace_dtn_quadrature_degree is not None:
            run_label += (
                f"_dtn_q{args.fixed_trace_dtn_quadrature_degree}"
            )
        if args.fixed_trace_dtn_evanescent_buffer:
            run_label += (
                "_dtn_evanescent_buffer"
                f"{args.fixed_trace_dtn_evanescent_buffer}"
            )
    elif args.regionwise_p_classifier_record is not None:
        run_label = (
            f"hexahedron_regionwise_p{args.regionwise_p_trace_degree}trace_"
            f"p{args.regionwise_p_low_interior_degree}low_p6high_"
            f"n{105 if args.regionwise_p_high_cell_count is None else args.regionwise_p_high_cell_count}_"
            f"h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
    else:
        run_label = (
            f"{args.mesh_cell_type}_p{args.coarse_degree}_"
            f"p{args.enriched_degree}_h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
    if args.common_mesh_replay_record is not None:
        angle_label = "-".join(
            f"{value:g}" for value in args.common_mesh_grazing_angles
        )
        run_label += (
            f"_common_mesh_theta{args.common_mesh_replay_theta:g}_grazing{angle_label}"
        )
    elif args.goal_dwr_only:
        run_label += f"_goal_dwr_only_theta{args.theta:g}"
    elif args.dwr_adaptive_cycles:
        run_label += f"_dwr_{args.dwr_marker_policy}_{args.dwr_adaptive_cycles}"
        if args.minimal_periodic_edge_closure:
            run_label += "_minimal_periodic_edge_closure"
        if args.theta_schedule is not None:
            schedule_label = "-".join(f"{value:g}" for value in args.theta_schedule)
            run_label += f"_theta{schedule_label}"
    elif args.adaptive_marked_cycles:
        run_label += f"_adaptive{args.adaptive_marked_cycles}"
    elif args.uniform_refinement_levels:
        run_label += f"_uniform{args.uniform_refinement_levels}"
    elif args.single_mesh_pair:
        run_label += "_single_mesh_pair"
    if args.bind_global_pair_solve_artifacts:
        run_label += "_bound_solve_artifacts"
    if args.structured_axis_cells is not None:
        run_label += "_axis" + "x".join(
            str(value) for value in args.structured_axis_cells
        )
    if args.static_condensation_degree:
        run_label += "_condense_" + "-".join(
            f"p{degree}" for degree in args.static_condensation_degree
        )
    if args.assembly_time_condensation_degree:
        run_label += "_assembly_time_" + "-".join(
            f"p{degree}"
            for degree in args.assembly_time_condensation_degree
        )
    if args.floquet_slave_elimination_degree:
        run_label += "_independent_" + "-".join(
            f"p{degree}"
            for degree in args.floquet_slave_elimination_degree
        )
    run_dir = (args.run_dir or args.artifact_root / run_label).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    args.run_dir = run_dir
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    result_path = run_dir / "actual_r5_result.json"
    fixed_trace_preflight_path = (
        run_dir / "fixed_trace_resource_preflight.json"
    )
    structured_axis_preflight_path = (
        run_dir / "structured_axis_resource_preflight.json"
    )
    if args.fixed_trace_control_record is not None:
        fixed_trace_preflight_path.write_text(
            json.dumps(
                args.fixed_trace_resource_preflight,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    elif args.structured_axis_cells is not None:
        structured_axis_preflight_path.write_text(
            json.dumps(
                args.structured_axis_resource_preflight,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task035_actual_r5",
        "--worker",
        "--coarse-degree",
        str(args.coarse_degree),
        "--enriched-degree",
        str(args.enriched_degree),
        "--h-nm",
        str(args.h_nm),
        "--theta",
        str(args.theta),
        "--polarization-kind",
        args.polarization_kind,
        "--mesh-cell-type",
        args.mesh_cell_type,
        "--run-dir",
        str(run_dir),
    ]
    if args.single_mesh_pair:
        command.append("--single-mesh-pair")
    if args.bind_global_pair_solve_artifacts:
        command.append("--bind-global-pair-solve-artifacts")
    if args.structured_axis_cells is not None:
        command.extend(
            [
                "--structured-axis-cells",
                ",".join(
                    str(value) for value in args.structured_axis_cells
                ),
            ]
        )
    if args.p6_projection_signals:
        command.append("--p6-projection-signals")
    for degree in args.static_condensation_degree:
        command.extend(["--static-condensation-degree", str(degree)])
    for degree in args.assembly_time_condensation_degree:
        command.extend(
            ["--assembly-time-condensation-degree", str(degree)]
        )
    for degree in args.floquet_slave_elimination_degree:
        command.extend(
            ["--floquet-slave-elimination-degree", str(degree)]
        )
    if args.fixed_trace_control_record is not None:
        command.extend(
            [
                "--fixed-trace-control-record",
                str(args.fixed_trace_control_record),
                "--fixed-trace-control-sha256",
                args.fixed_trace_control_sha256,
                "--fixed-trace-significant-channel-reference-record",
                str(
                    args.fixed_trace_significant_channel_reference_record
                ),
                "--fixed-trace-significant-channel-reference-sha256",
                args.fixed_trace_significant_channel_reference_sha256,
                "--fixed-trace-degree",
                str(args.fixed_trace_degree),
                "--fixed-interior-degree",
                str(args.fixed_interior_degree),
            ]
        )
        if args.fixed_trace_global_p6_baseline_record is not None:
            command.extend(
                [
                    "--fixed-trace-global-p6-baseline-record",
                    str(args.fixed_trace_global_p6_baseline_record),
                    "--fixed-trace-global-p6-baseline-sha256",
                    args.fixed_trace_global_p6_baseline_sha256,
                ]
            )
        if args.fixed_trace_directional_recovery:
            command.append("--fixed-trace-directional-recovery")
            command.extend(
                [
                    "--fixed-trace-directional-axis",
                    args.fixed_trace_directional_axis,
                ]
            )
        if args.fixed_trace_explicit_z_profile is not None:
            command.extend(
                [
                    "--fixed-trace-explicit-z-profile",
                    args.fixed_trace_explicit_z_profile,
                ]
            )
        if args.fixed_trace_channel_adjoint_diagnostic:
            command.append(
                "--fixed-trace-channel-adjoint-diagnostic"
            )
        if args.fixed_trace_dtn_quadrature_degree is not None:
            command.extend(
                [
                    "--fixed-trace-dtn-quadrature-degree",
                    str(args.fixed_trace_dtn_quadrature_degree),
                ]
            )
        if args.fixed_trace_dtn_evanescent_buffer:
            command.extend(
                [
                    "--fixed-trace-dtn-evanescent-buffer",
                    str(args.fixed_trace_dtn_evanescent_buffer),
                ]
            )
        if args.fixed_trace_directional_parent_record is not None:
            command.extend(
                [
                    "--fixed-trace-directional-parent-record",
                    str(args.fixed_trace_directional_parent_record),
                    "--fixed-trace-directional-parent-sha256",
                    args.fixed_trace_directional_parent_sha256,
                ]
            )
    elif args.regionwise_p_classifier_record is not None:
        command.extend(
            [
                "--regionwise-p-classifier-record",
                str(args.regionwise_p_classifier_record),
                "--regionwise-p-classifier-sha256",
                args.regionwise_p_classifier_sha256,
                "--regionwise-p-control-record",
                str(args.regionwise_p_control_record),
                "--regionwise-p-control-sha256",
                args.regionwise_p_control_sha256,
                "--regionwise-p-trace-degree",
                str(args.regionwise_p_trace_degree),
                "--regionwise-p-low-interior-degree",
                str(args.regionwise_p_low_interior_degree),
            ]
        )
        if args.regionwise_p_high_cell_count is not None:
            command.extend(
                [
                    "--regionwise-p-high-cell-count",
                    str(args.regionwise_p_high_cell_count),
                ]
            )
    elif args.common_mesh_replay_record is not None:
        command.extend(
            [
                "--common-mesh-replay-record",
                str(args.common_mesh_replay_record),
                "--common-mesh-replay-sha256",
                args.common_mesh_replay_sha256,
                "--common-mesh-grazing-angles",
                ",".join(
                    f"{value:g}" for value in args.common_mesh_grazing_angles
                ),
                "--common-mesh-replay-theta",
                str(args.common_mesh_replay_theta),
                "--common-mesh-replay-expected-final-cells",
                str(args.common_mesh_replay_expected_final_cells),
            ]
        )
        if args.hp_dof_ceiling is not None:
            command.extend(["--hp-dof-ceiling", str(args.hp_dof_ceiling)])
            command.extend(["--hp-accuracy-control-key", args.hp_accuracy_control_key])
    elif args.goal_dwr_only:
        command.append("--goal-dwr-only")
    elif args.dwr_adaptive_cycles:
        command.extend(
            [
                "--dwr-adaptive-cycles",
                str(args.dwr_adaptive_cycles),
                "--dwr-marker-policy",
                args.dwr_marker_policy,
            ]
        )
        if args.minimal_periodic_edge_closure:
            command.append("--minimal-periodic-edge-closure")
        if args.theta_schedule is not None:
            command.extend(
                [
                    "--theta-schedule",
                    ",".join(f"{value:g}" for value in args.theta_schedule),
                ]
            )
    elif args.adaptive_marked_cycles:
        command.extend(["--adaptive-marked-cycles", str(args.adaptive_marked_cycles)])
    elif args.uniform_refinement_levels:
        command.extend(
            ["--uniform-refinement-levels", str(args.uniform_refinement_levels)]
        )
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    authority_readable = True
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            rss_mb = row.get("mpi_process_tree_rss_mb")
            swap_mb = row.get("mpi_process_tree_swap_mb")
            readable = isinstance(rss_mb, (int, float)) and isinstance(
                swap_mb, (int, float)
            )
            authority_readable &= readable
            rss_gib = None if not readable else float(rss_mb) / 1024.0
            if rss_gib is not None:
                warning_triggered |= rss_gib >= args.warning_gib
            if process.poll() is None and not readable:
                _terminate_process_group(process)
            elif (
                process.poll() is None
                and rss_gib is not None
                and rss_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                _terminate_process_group(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate_process_group(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    structured_axis_orders = (
        _structured_axis_orders_evidence(
            run_dir=run_dir,
            enriched_summary=(
                (result.get("enriched") or {}).get("summary") or {}
            ),
            enriched_degree=int(args.enriched_degree),
        )
        if args.structured_axis_cells is not None
        and args.fixed_trace_control_record is None
        else None
    )
    solve_artifact_manifest = (
        _global_pair_solve_artifact_manifest(
            run_dir=run_dir,
            result=result,
            coarse_degree=int(args.coarse_degree),
            enriched_degree=int(args.enriched_degree),
            mpi_size=int(args.mpi_size),
        )
        if args.bind_global_pair_solve_artifacts
        else None
    )
    sampler = _sampler_summary(rows)
    qualifier = _select_qualifier(args)
    qualification = qualifier(
        result,
        args=args,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        authority_readable=authority_readable,
        sampler=sampler,
    )
    if args.bind_global_pair_solve_artifacts:
        manifest_pass = bool(
            isinstance(solve_artifact_manifest, dict)
            and solve_artifact_manifest.get("pass") is True
        )
        qualification["checks"][
            "requested_global_pair_solve_artifacts_hash_bound"
        ] = manifest_pass
        if not manifest_pass:
            qualification["failures"].append(
                "requested_global_pair_solve_artifacts_hash_bound"
            )
            qualification["pass"] = False
    head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = head_after == source_before["commit_sha"] and not status_after
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    if qualification["pass"]:
        status = (
            result.get("status")
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            else "actual_common_mesh_angle_sweep_pass"
            if args.common_mesh_replay_record is not None
            else "target_goal_weighted_two_level_pass"
            if args.goal_dwr_only
            else "actual_dwr_adaptive_cycles_pass"
            if args.dwr_adaptive_cycles
            else "actual_r5_adaptive_cycles_pass"
            if args.adaptive_marked_cycles
            else "actual_uniform_tetra_control_pass"
            if args.uniform_refinement_levels
            else "actual_global_r5_pass"
        )
    else:
        status = "formal_not_pass"
    record = {
        "schema_version": (
            "task035b.fixed-trace-watchdog.v1"
            if args.fixed_trace_control_record is not None
            else "task035b.regionwise-p-watchdog.v1"
            if args.regionwise_p_classifier_record is not None
            else "task035.actual-common-mesh-angle-sweep-watchdog.v1"
            if args.common_mesh_replay_record is not None
            else "task035b.actual-goal-dwr-only-watchdog.v1"
            if args.goal_dwr_only
            else "task035.actual-dwr-adaptive-watchdog.v1"
            if args.dwr_adaptive_cycles
            else "task035.actual-r5-adaptive-watchdog.v1"
            if args.adaptive_marked_cycles
            else "task035.actual-uniform-tetra-watchdog.v1"
            if args.uniform_refinement_levels
            else "task035.actual-global-r5-watchdog.v1"
        ),
        "benchmark_id": (
            "task035b_target_fixed_trace_candidate"
            if args.fixed_trace_control_record is not None
            else "task035b_target_regionwise_p_candidate"
            if args.regionwise_p_classifier_record is not None
            else "task035_target_actual_common_mesh_angle_sweep"
            if args.common_mesh_replay_record is not None
            else "task035b_target_actual_goal_dwr_only"
            if args.goal_dwr_only
            else "task035_target_actual_dwr_adaptive_cycles"
            if args.dwr_adaptive_cycles
            else "task035_target_actual_r5_adaptive_cycles"
            if args.adaptive_marked_cycles
            else "task035_target_actual_uniform_tetra_control"
            if args.uniform_refinement_levels
            else "task035_target_actual_global_r5"
        ),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "command": command,
        "source": {
            **source_before,
            "head_after_sha": head_after,
            "status_after_before_record_write": status_after,
            "stable_and_clean_after": source_stable,
        },
        "resource_preflight": preflight,
        "resource_policy": {
            "one_heavy_case_at_a_time": True,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "timeout_seconds": args.timeout_seconds,
            "swap_allowed": False,
            "termination_scope": "complete_process_group",
        },
        "resource_authority": sampler,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "qualification": qualification,
        "target_identity": result.get("target_identity") if result else None,
        **_watchdog_ordinary_default_identity(result),
        "coarse": (
            None
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            or args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["coarse"])
        ),
        "enriched": (
            None
            if args.fixed_trace_control_record is not None
            or args.regionwise_p_classifier_record is not None
            or args.common_mesh_replay_record is not None
            or args.dwr_adaptive_cycles
            or args.adaptive_marked_cycles
            or args.uniform_refinement_levels
            or not result
            else _compact_solve(result["enriched"])
        ),
        "official_observable_delta_l2": result.get("official_observable_delta_l2"),
        "R5": result.get("R5"),
        "common_mesh_identity": result.get("common_mesh_identity"),
        "same_mesh_hashes": result.get("same_mesh_hashes"),
        "single_in_memory_mesh_instance": result.get(
            "single_in_memory_mesh_instance"
        ),
        "reuse_single_mesh_requested": result.get(
            "reuse_single_mesh_requested"
        ),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "fixed_trace_resource_preflight": (
            getattr(args, "fixed_trace_resource_preflight", None)
        ),
        "structured_axis_resource_preflight": (
            getattr(args, "structured_axis_resource_preflight", None)
        ),
        "structured_axis_control_classification": (
            {
                "role": "y_only_global_p5_directional_control",
                "diagnostic_only": True,
                "formal_candidate_eligible": False,
                "reference_v1_gate_evaluated_in_this_record": False,
                "required_followup": (
                    "SHA-bound frozen-reference-v1 channel comparator"
                ),
                "thresholds_relaxed": False,
            }
            if args.structured_axis_cells is not None
            and args.fixed_trace_control_record is None
            else None
        ),
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "actual_r5_result": _path_from_root(result_path),
            "actual_r5_result_sha256": _sha256(result_path),
            "memory_timeline": _path_from_root(timeline_path),
            "memory_timeline_sha256": _sha256(timeline_path),
            "progress": _path_from_root(progress_path),
            "progress_sha256": _sha256(progress_path),
            "stdout": _path_from_root(stdout_path),
            "stdout_sha256": _sha256(stdout_path),
            "global_pair_solve_artifact_manifest": (
                solve_artifact_manifest
            ),
            **_preflight_artifact_evidence(
                fixed_trace_path=fixed_trace_preflight_path,
                structured_axis_path=structured_axis_preflight_path,
            ),
            "structured_axis_enriched_orders": (
                None
                if structured_axis_orders is None
                else structured_axis_orders.get("path")
            ),
            "structured_axis_enriched_orders_sha256": (
                None
                if structured_axis_orders is None
                else structured_axis_orders.get("sha256")
            ),
            "structured_axis_enriched_orders_count": (
                None
                if structured_axis_orders is None
                else structured_axis_orders.get("order_count")
            ),
            "structured_axis_enriched_orders_qualified": (
                None
                if structured_axis_orders is None
                else structured_axis_orders.get("pass")
            ),
        },
    }
    if args.fixed_trace_control_record is not None:
        candidate = result.get("candidate") or {}
        record.update(
            {
                "candidate_accuracy_pass": result.get(
                    "candidate_accuracy_pass"
                ),
                "channel_adjoint_diagnostic_only": result.get(
                    "channel_adjoint_diagnostic_only"
                ),
                "port_diagnostic_only": result.get(
                    "port_diagnostic_only"
                ),
                "formal_candidate_eligible": result.get(
                    "formal_candidate_eligible"
                ),
                "element_audit": result.get("element_audit"),
                "control_authority": result.get("control_authority"),
                "significant_channel_reference_authority": result.get(
                    "significant_channel_reference_authority"
                ),
                "directional_parent_authority": result.get(
                    "directional_parent_authority"
                ),
                "global_p6_baseline_authority": result.get(
                    "global_p6_baseline_authority"
                ),
                "same_mesh_global_p6_baseline": result.get(
                    "same_mesh_global_p6_baseline"
                ),
                "same_mesh_resource_comparison": result.get(
                    "same_mesh_resource_comparison"
                ),
                "dof_target": result.get("dof_target"),
                "candidate": (
                    _compact_solve(candidate) if candidate else None
                ),
                "observable_comparison": result.get(
                    "observable_comparison"
                ),
                "diffraction_channel_comparison": result.get(
                    "diffraction_channel_comparison"
                ),
                "selected_field_interface_error_gate": result.get(
                    "selected_field_interface_error_gate"
                ),
                "directional_recovery_signal": result.get(
                    "directional_recovery_signal"
                ),
                "channel_adjoint_diagnostic": (
                    _compact_channel_adjoint_diagnostic(
                        result.get("channel_adjoint_diagnostic")
                    )
                ),
                "port_diagnostic": result.get("port_diagnostic"),
            }
        )
    elif args.regionwise_p_classifier_record is not None:
        candidate = result.get("candidate") or {}
        record.update(
            {
                "candidate_accuracy_pass": result.get(
                    "candidate_accuracy_pass"
                ),
                "classifier_authority": result.get("classifier_authority"),
                "control_authority": result.get("control_authority"),
                "candidate": (
                    _compact_solve(candidate) if candidate else None
                ),
                "observable_comparison": result.get(
                    "observable_comparison"
                ),
                "diffraction_channel_comparison": result.get(
                    "diffraction_channel_comparison"
                ),
                "selected_field_interface_error_gate": result.get(
                    "selected_field_interface_error_gate"
                ),
            }
        )
    elif args.common_mesh_replay_record is not None:
        record.update(
            {
                "common_mesh_replay": result.get("mesh_replay"),
                "hp_budget_evaluation": result.get("hp_budget_evaluation"),
                "common_mesh_identity": result.get("common_mesh_identity"),
                "single_in_memory_mesh_instance": result.get(
                    "single_in_memory_mesh_instance"
                ),
                "angle_results": [
                    _compact_common_mesh_angle(entry)
                    for entry in result.get("angle_results", [])
                ],
            }
        )
    elif args.goal_dwr_only:
        record.update(
            {
                "goal_changes": result.get("goal_changes"),
                "DWR": result.get("DWR"),
                "R5_control": result.get("R5_control"),
            }
        )
    elif args.dwr_adaptive_cycles:
        record.update(
            {
                "dwr_marker_policy": result.get("marker_policy"),
                "periodic_edge_closure_policy": result.get(
                    "periodic_edge_closure_policy"
                ),
                "theta_schedule": result.get("theta_schedule"),
                "marked_cycles_requested": result.get("marked_cycles_requested"),
                "marked_cycles_completed": result.get("marked_cycles_completed"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "cycles": [
                    _compact_dwr_cycle(entry) for entry in result.get("cycles", [])
                ],
                "refinements": result.get("refinements"),
                "observable_error_reductions": result.get(
                    "observable_error_reductions"
                ),
                "all_fixed_reference_error_reductions_positive": result.get(
                    "all_fixed_reference_error_reductions_positive"
                ),
                "internal_p_gap_is_gate": result.get("internal_p_gap_is_gate"),
            }
        )
    elif args.adaptive_marked_cycles:
        record.update(
            {
                "marked_cycles_requested": result.get("marked_cycles_requested"),
                "marked_cycles_completed": result.get("marked_cycles_completed"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "cycles": [
                    _compact_adaptive_cycle(entry) for entry in result.get("cycles", [])
                ],
                "refinements": result.get("refinements"),
                "observable_error_reductions": result.get(
                    "observable_error_reductions"
                ),
                "all_fixed_reference_error_reductions_positive": (
                    result.get("all_fixed_reference_error_reductions_positive")
                ),
                "internal_p_gap_is_gate": result.get("internal_p_gap_is_gate"),
            }
        )
    elif args.uniform_refinement_levels:
        pair = result.get("actual_r5_pair") or {}
        record.update(
            {
                "uniform_refinement_levels": result.get("refinement_levels"),
                "initial_mesh_audit": result.get("initial_mesh_audit"),
                "refinements": result.get("refinements"),
                "final_mesh_audit": result.get("final_mesh_audit"),
                "fixed_observable_reference": result.get("fixed_observable_reference"),
                "coarse_observables": result.get("coarse_observables"),
                "enriched_observables": result.get("enriched_observables"),
                "coarse_fixed_reference_error_l2": result.get(
                    "coarse_fixed_reference_error_l2"
                ),
                "enriched_fixed_reference_error_l2": result.get(
                    "enriched_fixed_reference_error_l2"
                ),
                "coarse": _compact_solve(pair["coarse"]) if pair else None,
                "enriched": _compact_solve(pair["enriched"]) if pair else None,
                "R5": pair.get("R5"),
            }
        )
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                "status": status,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "record": _path_from_root(record_path),
                "failures": qualification["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if qualification["pass"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir.")
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
