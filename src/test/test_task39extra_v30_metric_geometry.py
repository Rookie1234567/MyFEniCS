"""Bounded candidate-only geometry inventory and timing for V30 H6 diagonal."""
from __future__ import annotations

import gc
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
from mpi4py import MPI

from src.geometry.mesh_builder_3d import _stage4_axis_plan
from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_metric_positive_diagonal import (
    build_reference_metric_positive_diagonal,
)
from src.solvers.fullspace_quadrature_diagonal import (
    PositiveCellBasis,
    _affine_cell_jacobian,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    _build_same_mesh_levels,
)


ROOT = Path(__file__).resolve().parents[2]
V30_INPUT = ROOT / "input/task39extra/v30_workstation_guided_original_h7p5.dat"


def _counter_sha256(counter):
    payload = bytearray()
    for key, count in sorted(counter.items()):
        payload.extend(len(key).to_bytes(4, "little"))
        payload.extend(key)
        payload.extend(int(count).to_bytes(8, "little"))
    return hashlib.sha256(payload).hexdigest()


def test_v30_p6_candidate_only_geometry_inventory_and_timing():
    if MPI.COMM_WORLD.size != 1:
        raise AssertionError("the frozen geometry diagnostic requires MPI1")
    specification = load_and_resolve(V30_INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    assert cfg.nedelec_degree == 6 and cfg.mesh_target_size == 7.5
    axis_plan = _stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
    )
    space = levels["spaces"][6]
    mpc = levels["floquets"][6].mpc
    mu, mass = levels["mu"], levels["mass"]
    cells = int(space.mesh.topology.index_map(space.mesh.topology.dim).size_local)
    assert cells == 990

    # Count both exact floating-point Jacobian identities and the structured
    # cell edge widths that define physical size/shape.  The former are a
    # cache-key diagnostic only: last-bit differences do not become new shape
    # classes.  This inventory is released before candidate timing.
    start_wall, start_cpu = perf_counter(), process_time()
    basis = PositiveCellBasis(space, mu, mass)
    space.mesh.topology.create_entity_permutations()
    permutations = space.mesh.topology.get_cell_permutation_info()
    raw_jacobian_counts = Counter()
    raw_metric_key_counts = Counter()
    physical_size_counts = Counter()
    for cell in range(cells):
        coordinates = space.mesh.geometry.x[space.mesh.geometry.dofmap[cell]]
        jacobian = _affine_cell_jacobian(basis.geometry_derivatives, coordinates)
        raw_key = jacobian.tobytes()
        raw_jacobian_counts[raw_key] += 1
        metric_key = raw_key + int(permutations[cell]).to_bytes(8, "little")
        raw_metric_key_counts[metric_key] += 1
        # DOLFINx may reverse local corner order to repair cell orientation.
        # Use translation-invariant coordinate spans, then sort axes because
        # this is a physical size/shape class rather than a reference-axis ID.
        edge_widths = np.sort(np.ptp(coordinates, axis=0))[::-1].astype(
            np.float64, copy=False
        )
        if np.any(edge_widths <= 0):
            raise AssertionError("structured cell coordinate spans must be positive")
        physical_size_key = edge_widths.tobytes()
        physical_size_counts[physical_size_key] += 1
    geometry_inventory_wall = perf_counter() - start_wall
    geometry_inventory_cpu = process_time() - start_cpu
    del basis
    gc.collect()

    axis_widths = {
        name: np.diff(getattr(axis_plan, f"{name}_values"))
        for name in ("x", "y", "z")
    }
    axis_width_summary = {
        name: {
            "interval_count": int(widths.size),
            "unique_exact_width_count": len({float(value).hex() for value in widths}),
            "minimum": float(widths.min()),
            "maximum": float(widths.max()),
            "unique_widths_coordinate_units": sorted(
                {float(value) for value in widths}
            ),
        }
        for name, widths in axis_widths.items()
    }
    size_classes = []
    for key, count in sorted(physical_size_counts.items()):
        widths = np.frombuffer(key, dtype=np.float64)
        size_classes.append(
            {
                "edge_widths_coordinate_units": [float(value) for value in widths],
                "aspect_ratios_to_largest_edge": [
                    float(value / widths.max()) for value in widths
                ],
                "cell_count": int(count),
            }
        )

    candidate_audit = {}
    start_wall, start_cpu = perf_counter(), process_time()
    diagonal = build_reference_metric_positive_diagonal(
        space, mu, mass, mpc, audit=candidate_audit
    )
    candidate_wall = perf_counter() - start_wall
    candidate_cpu = process_time() - start_cpu
    try:
        values = diagonal.array.copy()
        source_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        tracked_diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=ROOT, check=True,
            capture_output=True,
        ).stdout
        candidate_source = ROOT / "src/solvers/fullspace_metric_positive_diagonal.py"
        record = {
            "schema": "task39extra.v30.l2.geometry-diagnostic.v1",
            "status": "MEASURED_BEFORE_ASSERTIONS",
            "scope": "candidate_only_no_old_or_v29_diagonal_no_h6_no_pde",
            "diagnostic_attempt_history": [
                {
                    "attempt": 1,
                    "status": "CONTROLLED_DIAGNOSTIC_HARNESS_FAILURE",
                    "reason": (
                        "assumed positive local corner edge slots; DOLFINx cell "
                        "orientation can reverse those slots, so inventory stopped "
                        "before candidate diagonal construction"
                    ),
                    "correction": (
                        "classify rectilinear physical spans from coordinate minima "
                        "and maxima, sorted independent of local orientation"
                    ),
                }
            ],
            "source_head": source_head,
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "diagnostic_test_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "candidate_source_sha256": hashlib.sha256(
                candidate_source.read_bytes()
            ).hexdigest(),
            "input_path": V30_INPUT.relative_to(ROOT).as_posix(),
            "input_sha256": hashlib.sha256(V30_INPUT.read_bytes()).hexdigest(),
            "run_id": specification.identity["run_id"],
            "degree": 6,
            "mesh_target_size": 7.5,
            "mesh_cells": cells,
            "mpi_size": MPI.COMM_WORLD.size,
            "geometry_source": {
                "axis_plan_builder": "src.geometry.mesh_builder_3d._stage4_axis_plan",
                "mesh_builder": "src.geometry.mesh_builder_3d._structured_hexa_mesh",
                "resolved_spacing_mode": axis_plan.mesh_spacing_mode_resolved,
                "cells_per_axis": list(axis_plan.mesh_cells_resolved),
                "axis_widths": axis_width_summary,
            },
            "geometry_inventory": {
                "structured_cell_edge_size_identity": (
                    "sorted_exact_coordinate_spans_of_rectilinear_hexa_corners"
                ),
                "unique_physical_size_and_shape_classes": len(physical_size_counts),
                "physical_size_shape_class_sha256": _counter_sha256(
                    physical_size_counts
                ),
                "physical_size_shape_classes": size_classes,
                "exact_jacobian_bit_pattern_count_cache_diagnostic_only": len(
                    raw_jacobian_counts
                ),
                "exact_jacobian_permutation_bit_pattern_count_cache_diagnostic_only": len(
                    raw_metric_key_counts
                ),
                "jacobian_bit_pattern_histogram": {
                    str(count): sum(v == count for v in raw_jacobian_counts.values())
                    for count in sorted(set(raw_jacobian_counts.values()))
                },
                "jacobian_permutation_bit_pattern_histogram": {
                    str(count): sum(v == count for v in raw_metric_key_counts.values())
                    for count in sorted(set(raw_metric_key_counts.values()))
                },
                "bit_pattern_counts_are_not_physical_shape_counts": True,
                "geometry_inventory_wall_seconds": geometry_inventory_wall,
                "geometry_inventory_process_cpu_seconds": geometry_inventory_cpu,
            },
            "candidate_timing_seconds": {
                "wall": candidate_wall,
                "process_cpu": candidate_cpu,
            },
            "candidate_audit": candidate_audit,
            "candidate_diagonal": {
                "sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                "all_finite": bool(np.isfinite(values).all()),
                "minimum_owned_real": float(
                    values[: space.dofmap.index_map.size_local].real.min()
                ),
            },
            "memory_accounting": {
                "orientation_build_known_array_peak_bytes_scope": (
                    "retained_reference_values_and_curls_plus_one_oriented_copy_pair"
                    "_plus_two_tensor_outputs; excludes NumPy einsum/BLAS internal scratch"
                ),
                "cache_storage_bytes_scope": (
                    "retained ndarray payload for bounded orientation and metric caches"
                ),
                "process_rss_not_measured": True,
            },
        }
        record_path = ROOT / (
            "docs/task039_extra_physical_multilevel/outcomes/records/"
            "workstation_guided_local_v30_l2_geometry_diagnostic.json"
        )
        if os.environ.get("TASK39EXTRA_V30_SAVE_GEOMETRY_RECORD") == "1":
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print("L2_GEOMETRY_RECORD " + json.dumps(record, sort_keys=True), flush=True)

        assert candidate_audit["metric_cache_limit"] == 64
        assert candidate_audit["metric_cache_entries"] <= 64
        assert candidate_audit["orientation_tensor_cache_entries"] <= 64
        assert candidate_audit["target_merge_fallbacks"] == 0
        assert candidate_audit["per_cell_physical_basis_table_builds"] == 0
        assert candidate_audit["metric_cache_storage_bytes"] > 0
        assert candidate_audit["retained_cache_ndarray_storage_bytes"] == (
            candidate_audit["metric_cache_storage_bytes"]
            + candidate_audit["orientation_tensor_cache_storage_bytes"]
        )
        assert candidate_audit["orientation_tensor_build_count"] == (
            candidate_audit["orientation_tensor_cache_misses"]
        )
        assert candidate_audit["orientation_build_input_copy_bytes_cumulative"] == (
            candidate_audit["orientation_build_input_copy_bytes_per_build"]
            * candidate_audit["orientation_tensor_build_count"]
        )
        assert len(physical_size_counts) > 0
        assert sum(physical_size_counts.values()) == cells
        assert sum(raw_jacobian_counts.values()) == cells
        assert values.size > 0 and record["candidate_diagonal"]["all_finite"]
        record["status"] = "PASS"
        if os.environ.get("TASK39EXTRA_V30_SAVE_GEOMETRY_RECORD") == "1":
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    finally:
        diagonal.destroy()
