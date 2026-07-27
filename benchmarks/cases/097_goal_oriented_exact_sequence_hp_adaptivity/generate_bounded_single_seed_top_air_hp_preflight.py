#!/usr/bin/env python3
"""Build the bounded single-root-seed top-air h/p action catalog.

This is a serial structural preflight.  It exercises the production Stage-4
mesh, exact-sequence entity map, hanging constraints, and Floquet reduction,
but it never assembles or solves a Maxwell PDE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.stage4_local_h import (  # noqa: E402
    _build_forest,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_local_h_refinement_plan_payload,
)
from src.common.config_3d import target_stage4_config  # noqa: E402


CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
DEFAULT_OUTPUT = (
    RECORD_DIR / "bounded_single_seed_top_air_hp_preflight_v1.json"
)
GENERATOR_RELATIVE = str(Path(__file__).resolve().relative_to(ROOT))
H15_RECORD_RELATIVE = (
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
    "fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json"
)
DTN_AUXILIARY_ROWS = 80
MAXIMUM_ACTIVE_FE_DOFS = 90_000

NUMERICAL_RELATIVE_FILES = (
    "src/common/config_3d.py",
    "src/common/units.py",
    "src/geometry/mesh_builder_3d.py",
    "src/adaptivity/stage4_local_h.py",
    "src/adaptivity/dyadic_hexa_refinement.py",
    "src/adaptivity/dyadic_hexa_broken_mesh.py",
    "src/adaptivity/hcurl_hanging_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_trace_constraint_graph.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/variable_p_degree_plan.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/adaptivity/variable_p_transfer.py",
    "src/constraints/high_order_floquet_trace.py",
    H15_RECORD_RELATIVE,
    GENERATOR_RELATIVE,
)

ROOT_MARKS = (
    ("outer_left_alias", (0.0, 0.0, 120.0, 8.25, 12.5, 130.0)),
    (
        "left_inner_without_compact_dwr",
        (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
    ),
    (
        "left_grating_top",
        (16.5, 0.0, 120.0, 25.0, 12.5, 130.0),
    ),
    (
        "right_grating_top",
        (25.0, 0.0, 120.0, 33.5, 12.5, 130.0),
    ),
    (
        "right_inner",
        (33.5, 0.0, 120.0, 41.75, 12.5, 130.0),
    ),
    (
        "outer_right_alias",
        (41.75, 0.0, 120.0, 50.0, 12.5, 130.0),
    ),
)

def _two_y_root_boxes(
    x0: float,
    x1: float,
    z0: float,
    z1: float,
) -> list[list[float]]:
    return [
        [x0, 0.0, z0, x1, 12.5, z1],
        [x0, 12.5, z0, x1, 25.0, z1],
    ]


EXPECTED_ACTION_CATALOG = {
    "outer_left_alias": {
        "requested_mark_nm": [0.0, 0.0, 120.0, 8.25, 12.5, 130.0],
        "closed_refined_root_boxes_nm": sorted(
            _two_y_root_boxes(0.0, 8.25, 120.0, 130.0)
            + _two_y_root_boxes(41.75, 50.0, 120.0, 130.0)
        ),
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 3,
            "user": 1,
        },
        "dimensions": (
            120,
            4,
            148,
            8,
            32,
            116,
            86_530,
            26_650,
            1_680,
            4_690,
            84_850,
            20_280,
            20_360,
        ),
    },
    "outer_right_alias": {
        "requested_mark_nm": [
            41.75,
            0.0,
            120.0,
            50.0,
            12.5,
            130.0,
        ],
        "closed_refined_root_boxes_nm": sorted(
            _two_y_root_boxes(0.0, 8.25, 120.0, 130.0)
            + _two_y_root_boxes(41.75, 50.0, 120.0, 130.0)
        ),
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 3,
            "user": 1,
        },
        "dimensions": (
            120,
            4,
            148,
            8,
            32,
            116,
            86_530,
            26_650,
            1_680,
            4_690,
            84_850,
            20_280,
            20_360,
        ),
    },
    "left_inner_without_compact_dwr": {
        "requested_mark_nm": [
            8.25,
            0.0,
            120.0,
            16.5,
            12.5,
            130.0,
        ],
        "closed_refined_root_boxes_nm": _two_y_root_boxes(
            8.25,
            16.5,
            120.0,
            130.0,
        ),
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 1,
            "user": 1,
        },
        "dimensions": (
            120,
            2,
            134,
            6,
            16,
            118,
            80_815,
            23_875,
            1_250,
            4_235,
            79_565,
            18_390,
            18_470,
        ),
    },
    "left_grating_top": {
        "requested_mark_nm": [
            16.5,
            0.0,
            120.0,
            25.0,
            12.5,
            130.0,
        ],
        "closed_refined_root_boxes_nm": sorted(
            _two_y_root_boxes(8.25, 16.5, 105.0, 120.0)
            + _two_y_root_boxes(16.5, 25.0, 105.0, 120.0)
            + _two_y_root_boxes(16.5, 25.0, 120.0, 130.0)
        ),
        "closure_counts": {
            "balance": 0,
            "material": 4,
            "periodic": 1,
            "user": 1,
        },
        "dimensions": (
            120,
            6,
            162,
            14,
            48,
            114,
            91_805,
            28_985,
            2_890,
            4_525,
            88_915,
            21_570,
            21_650,
        ),
    },
    "right_grating_top": {
        "requested_mark_nm": [
            25.0,
            0.0,
            120.0,
            33.5,
            12.5,
            130.0,
        ],
        "closed_refined_root_boxes_nm": sorted(
            _two_y_root_boxes(25.0, 33.5, 105.0, 120.0)
            + _two_y_root_boxes(25.0, 33.5, 120.0, 130.0)
            + _two_y_root_boxes(33.5, 41.75, 105.0, 120.0)
        ),
        "closure_counts": {
            "balance": 0,
            "material": 4,
            "periodic": 1,
            "user": 1,
        },
        "dimensions": (
            120,
            6,
            162,
            14,
            48,
            114,
            91_805,
            28_985,
            2_890,
            4_525,
            88_915,
            21_570,
            21_650,
        ),
    },
    "right_inner": {
        "requested_mark_nm": [
            33.5,
            0.0,
            120.0,
            41.75,
            12.5,
            130.0,
        ],
        "closed_refined_root_boxes_nm": _two_y_root_boxes(
            33.5,
            41.75,
            120.0,
            130.0,
        ),
        "closure_counts": {
            "balance": 0,
            "material": 0,
            "periodic": 1,
            "user": 1,
        },
        "dimensions": (
            120,
            2,
            134,
            6,
            16,
            118,
            80_815,
            23_875,
            1_250,
            4_235,
            79_565,
            18_390,
            18_470,
        ),
    },
}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit_blob_sha(source_sha: str, relative: str) -> str:
    content = subprocess.check_output(
        ("git", "show", f"{source_sha}:{relative}"),
        cwd=ROOT,
    )
    return hashlib.sha256(content).hexdigest()


def _source_identity(source_sha: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            *NUMERICAL_RELATIVE_FILES,
        ),
        cwd=ROOT,
        text=True,
    ).strip()
    live = {
        relative: _sha256(ROOT / relative)
        for relative in NUMERICAL_RELATIVE_FILES
    }
    committed = {
        relative: _commit_blob_sha(source_sha, relative)
        for relative in NUMERICAL_RELATIVE_FILES
    }
    if head != source_sha or status or live != committed:
        raise RuntimeError(
            "structural preflight requires clean committed numerical source"
        )
    return {
        "head": head,
        "status_lines": [],
        "verified_clean_numerical_source": True,
        "numerical_file_sha256": live,
    }


def _structural_action(
    action_id: str,
    mark: tuple[float, ...],
) -> dict[str, Any]:
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    forest = _build_forest(
        cfg,
        comm_size=8,
        marked_root_boxes=(mark,),
        maximum_level=1,
    )
    closed_roots = sorted(
        {
            forest.root_boxes[cell.key.root]
            for cell in forest.leaves
            if cell.key.level == 1
        }
    )
    overrides = {
        cell.box: 5 for cell in forest.leaves if cell.key.level == 1
    }
    plan = stage4_local_h_refinement_plan_payload(
        cfg,
        (mark,),
        comm_size=8,
        trace_degree=5,
        cell_interior_degree=6,
        provenance={
            "purpose": (
                "Task035d bounded single-root-seed top-air structural "
                "preflight"
            ),
            "action_id": action_id,
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
        cell_interior_degree_overrides=overrides,
        selected_p6_face_geometry_keys=(),
    )
    with TemporaryDirectory(
        prefix="task035d-all-top-air-",
        dir="/tmp",
    ) as temporary:
        plan_path = Path(temporary) / "plan.json"
        plan_path.write_text(
            json.dumps(
                _plain(plan),
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        mesh_data = build_stage4_local_h_mesh_data(
            cfg,
            plan_path,
            comm=MPI.COMM_WORLD,
        )
        context = mesh_data.local_h_context
        if context is None:
            raise RuntimeError("Stage-4 local-h context was not retained")
        reduction = build_stage4_local_h_reduction_authority(
            context,
            phase_x=cfg.floquet_phase_x,
            phase_y=cfg.floquet_phase_y,
        )
        audit = reduction.audit
        degree = audit["degree_plan"]
        physical = audit["physical_trace"]
        constraints = audit["trace_constraints"]
        row = {
            "action_id": action_id,
            "requested_mark_nm": list(mark),
            "closed_refined_root_boxes_nm": [
                list(box) for box in closed_roots
            ],
            "closure_counts": dict(
                forest.audit["closure_split_counts"]
            ),
            "split_root_count": len(closed_roots),
            "root_cell_count": len(forest.root_boxes),
            "leaf_cell_count": len(forest.leaves),
            "hanging_patch_count": len(forest.hanging_faces),
            "p5_cell_count": len(overrides),
            "p6_cell_count": len(forest.leaves) - len(overrides),
            "raw_broken_active_fe_dofs": int(
                audit["raw_broken_active_fe_dofs"]
            ),
            "raw_broken_trace_rows": int(
                audit["raw_broken_trace_rows"]
            ),
            "hanging_slave_rows": int(audit["hanging_slave_rows"]),
            "periodic_slave_rows": int(audit["periodic_slave_rows"]),
            "actual_full3d_equivalent_active_fe_dofs": int(
                audit["actual_full3d_equivalent_active_fe_dofs"]
            ),
            "independent_trace_rows": int(
                audit["independent_trace_rows"]
            ),
            "appended_dtn_rows": DTN_AUXILIARY_ROWS,
            "predicted_direct_solve_rows": (
                int(audit["independent_trace_rows"])
                + DTN_AUXILIARY_ROWS
            ),
            "leaf_catalog_sha256": forest.audit[
                "leaf_catalog_sha256"
            ],
            "hanging_face_catalog_sha256": forest.audit[
                "hanging_face_catalog_sha256"
            ],
            "carrier_connectivity_sha256": context.audit["carrier"][
                "canonical_connectivity_sha256"
            ],
            "mesh_cell_box_catalog_sha256": degree[
                "mesh_cell_box_catalog_sha256"
            ],
            "cell_degree_plan_sha256": degree[
                "cell_degree_plan_sha256"
            ],
            "geometry_canonical_entity_degree_sha256": degree[
                "geometry_canonical_entity_degree_sha256"
            ],
            "flattened_graph_sha256": constraints[
                "flattened_graph_sha256"
            ],
            "canonical_cell_graph_sha256": constraints[
                "canonical_cell_graph_sha256"
            ],
        }
    expected_tuple = (
        row["root_cell_count"],
        row["split_root_count"],
        row["leaf_cell_count"],
        row["hanging_patch_count"],
        row["p5_cell_count"],
        row["p6_cell_count"],
        row["raw_broken_active_fe_dofs"],
        row["raw_broken_trace_rows"],
        row["hanging_slave_rows"],
        row["periodic_slave_rows"],
        row["actual_full3d_equivalent_active_fe_dofs"],
        row["independent_trace_rows"],
        row["predicted_direct_solve_rows"],
    )
    expected = EXPECTED_ACTION_CATALOG[action_id]
    checks = {
        "mesh_and_reduction_pass": (
            context.audit["pass"] is True and audit["pass"] is True
        ),
        "ownership_gate": (
            constraints["pde_launch_ownership_gate"] is True
        ),
        "expected_dimensions": (
            expected_tuple == expected["dimensions"]
        ),
        "exact_seed_and_closure": (
            row["requested_mark_nm"] == expected["requested_mark_nm"]
            and row["closed_refined_root_boxes_nm"]
            == expected["closed_refined_root_boxes_nm"]
            and row["closure_counts"] == expected["closure_counts"]
        ),
        "p5_is_exactly_refined_children": (
            row["p5_cell_count"] == 8 * row["split_root_count"]
        ),
        "cell_degree_counts": (
            degree["cell_degree_counts"]
            == {
                "p4": 0,
                "p5": row["p5_cell_count"],
                "p6": row["p6_cell_count"],
            }
        ),
        "p5_only_trace": (
            degree["trace_degree_values"] == [5]
            and physical["selected_p6_face_count"] == 0
            and physical["selected_p6_face_geometry_keys"] == []
            and physical["selected_p6_periodic_orbit_count"] == 0
            and physical["selective_trace_full3d_dof_delta"] == 0
        ),
        "active_dof_identity": (
            row["raw_broken_active_fe_dofs"]
            - row["hanging_slave_rows"]
            == row["actual_full3d_equivalent_active_fe_dofs"]
        ),
        "trace_row_identity": (
            row["raw_broken_trace_rows"]
            - row["hanging_slave_rows"]
            - row["periodic_slave_rows"]
            == row["independent_trace_rows"]
        ),
        "dof_budget": (
            row["actual_full3d_equivalent_active_fe_dofs"]
            <= MAXIMUM_ACTIVE_FE_DOFS
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    row["checks"] = checks
    row["failures"] = failures
    row["pass"] = not failures
    return row


def build_preflight(source_sha: str) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise ValueError(
            "bounded single-root-seed structural preflight is serial"
        )
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified WSL activation is required")
    if (
        str(np.dtype(PETSc.ScalarType)) != "complex128"
        or str(np.dtype(PETSc.IntType)) != "int32"
    ):
        raise RuntimeError("qualified complex PETSc ABI is required")
    source = _source_identity(source_sha)
    rows: dict[str, dict[str, Any]] = {}
    for index, (action_id, mark) in enumerate(ROOT_MARKS, start=1):
        print(
            f"[structural-preflight {index}/{len(ROOT_MARKS)}] {action_id}",
            flush=True,
        )
        rows[action_id] = _structural_action(action_id, mark)
    alias_identity_keys = (
        "closed_refined_root_boxes_nm",
        "closure_counts",
        "split_root_count",
        "root_cell_count",
        "leaf_cell_count",
        "hanging_patch_count",
        "p5_cell_count",
        "p6_cell_count",
        "raw_broken_active_fe_dofs",
        "raw_broken_trace_rows",
        "hanging_slave_rows",
        "periodic_slave_rows",
        "actual_full3d_equivalent_active_fe_dofs",
        "independent_trace_rows",
        "predicted_direct_solve_rows",
        "leaf_catalog_sha256",
        "hanging_face_catalog_sha256",
        "carrier_connectivity_sha256",
        "mesh_cell_box_catalog_sha256",
        "cell_degree_plan_sha256",
        "geometry_canonical_entity_degree_sha256",
        "flattened_graph_sha256",
        "canonical_cell_graph_sha256",
    )
    outer_left = rows["outer_left_alias"]
    outer_right = rows["outer_right_alias"]
    outer_alias_identity = all(
        outer_left[key] == outer_right[key]
        for key in alias_identity_keys
    )
    h15_path = ROOT / H15_RECORD_RELATIVE
    h15 = json.loads(h15_path.read_text(encoding="utf-8"))
    baseline = {
        "path": H15_RECORD_RELATIVE,
        "sha256": _sha256(h15_path),
        "committed_sha256": _commit_blob_sha(
            source_sha,
            H15_RECORD_RELATIVE,
        ),
        "actual_full3d_equivalent_active_fe_dofs": 74_890,
        "predicted_direct_solve_rows": 16_880,
        "recorded_active_fe_dofs": h15["candidate"][
            "num_nedelec_dofs"
        ],
        "recorded_solve_rows": h15["candidate"]["matrix_stats"][
            "matrix_rows"
        ],
    }
    checks = {
        "source_identity": source["verified_clean_numerical_source"],
        "all_six_alias_rows_pass": (
            len(rows) == 6 and all(row["pass"] for row in rows.values())
        ),
        "outer_periodic_alias_identity": outer_alias_identity,
        "fixed_h15_baseline_identity": (
            baseline["sha256"] == baseline["committed_sha256"]
            and baseline["recorded_active_fe_dofs"]
            == baseline["actual_full3d_equivalent_active_fe_dofs"]
            and baseline["recorded_solve_rows"]
            == baseline["predicted_direct_solve_rows"]
        ),
        "all_actions_within_budget": all(
            row["actual_full3d_equivalent_active_fe_dofs"]
            <= MAXIMUM_ACTIVE_FE_DOFS
            for row in rows.values()
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "case097.bounded-single-seed-top-air-hp-preflight.v1"
        ),
        "status": (
            "bounded_single_seed_top_air_hp_preflight_pass"
            if not failures
            else "bounded_single_seed_top_air_hp_preflight_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "source_sha": source_sha,
        "source_identity": source,
        "environment": {
            "qualified_activation": True,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "mpi_size": 1,
            "formal_target_mpi_size": 8,
        },
        "fixed_h15_baseline": baseline,
        "action_rows": rows,
        "unique_action_aliases": {
            "outer_periodic": [
                "outer_left_alias",
                "outer_right_alias",
            ],
            "left_inner_without_compact_dwr": [
                "left_inner_without_compact_dwr"
            ],
            "left_grating_top": ["left_grating_top"],
            "right_grating_top": ["right_grating_top"],
            "right_inner": ["right_inner"],
        },
        "measurement_scope": (
            "production Stage-4 mesh, entity-map, hanging, and Floquet "
            "reduction only; no Maxwell assembly, factorization, or PDE"
        ),
        "ordinary_default_changed": False,
        "production_qualified": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise ValueError("formal structural preflight output path is fixed")
    if output.exists():
        raise FileExistsError("formal structural preflight is immutable")
    result = build_preflight(str(args.source_sha))
    output.write_text(
        json.dumps(
            _plain(result),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output),
                "status": result["status"],
                "pass": result["pass"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
