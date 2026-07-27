#!/usr/bin/env python3
"""Generate the first production-bound Task035d local-h authority.

The generator is intentionally component-only.  It binds the tracked h15
refinement plan to the real Stage-4 broken-hexa carrier and the production
hanging/Floquet reduction, but it does not start a Maxwell PDE.  Formal
accuracy credit remains reserved for the MPI8 watchdog plus independent
12-channel checker.
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
from typing import Any, Mapping

import basix
import dolfinx
from mpi4py import MPI
import mpi4py
import numpy as np
from petsc4py import PETSc
import petsc4py

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
CHECKER_NAME = "check_local_h_production_authority.py"
GENERATOR_NAME = Path(__file__).name
DEFAULT_CANDIDATE_ID = "h15_top_air_local_h_v1"
SELECTIVE_FACE_CANDIDATE_ID = "h15_grating_top_selective_p6_faces_v1"
OUTER_TOP_HP_CANDIDATE_ID = "h15_outer_top_periodic_p5fine_v1"
LEFT_GRATING_TOP_HP_CANDIDATE_ID = (
    "h15_left_grating_top_closure_p5fine_v1"
)
SELECTIVE_P6_FACE_GEOMETRY_KEYS = (
    (2, 92857142857, 0, 5892857143, 0, 8928571429),
    (2, 92857142857, 0, 5892857143, 8928571429, 17857142857),
    (2, 92857142857, 11785714286, 17857142857, 0, 8928571429),
    (
        2,
        92857142857,
        11785714286,
        17857142857,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 17857142857, 23928571429, 0, 8928571429),
    (
        2,
        92857142857,
        17857142857,
        23928571429,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 23928571429, 29821428571, 0, 8928571429),
    (
        2,
        92857142857,
        23928571429,
        29821428571,
        8928571429,
        17857142857,
    ),
    (2, 92857142857, 29821428571, 35714285714, 0, 8928571429),
    (
        2,
        92857142857,
        29821428571,
        35714285714,
        8928571429,
        17857142857,
    ),
)
CANDIDATE_SPECS = {
    DEFAULT_CANDIDATE_ID: {
        "plan_name": "h15_top_air_local_h_plan_v1.json",
        "component_names": {
            1: "local_h_production_mpi1_v3_owner_gate_fix1.json",
            2: "local_h_production_mpi2_v3_owner_gate_fix1.json",
            8: "local_h_production_mpi8_v3_owner_gate_fix1.json",
        },
        "schema_version": (
            "case097.local-h-production-component.v3-integration"
        ),
        "pass_status": "local_h_production_component_pass",
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
        "variable_interior": False,
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 134,
            "hanging_patch_count": 6,
            "raw_broken_active_fe_dofs": 84_175,
            "raw_broken_trace_rows": 23_875,
            "hanging_slave_rows": 1_250,
            "periodic_slave_rows": 4_235,
            "actual_full3d_equivalent_active_fe_dofs": 82_925,
            "independent_trace_rows": 18_390,
            "predicted_direct_solve_rows": 18_470,
        },
    },
    "h15_symmetric_top_air_remote_p5_interior_v1": {
        "plan_name": (
            "h15_symmetric_top_air_remote_p5_interior_plan_v1.json"
        ),
        "component_names": {
            1: "combined_hp_interior_mpi1_v2.json",
            2: "combined_hp_interior_mpi2_v2.json",
            8: "combined_hp_interior_mpi8_v2.json",
        },
        "schema_version": (
            "case097.combined-hp-interior-component.v2"
        ),
        "pass_status": "combined_hp_interior_component_pass",
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
            (33.5, 0.0, 120.0, 41.75, 12.5, 130.0),
        ),
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 116},
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 148,
            "hanging_patch_count": 12,
            "raw_broken_active_fe_dofs": 86_740,
            "raw_broken_trace_rows": 26_860,
            "hanging_slave_rows": 2_500,
            "periodic_slave_rows": 4_380,
            "actual_full3d_equivalent_active_fe_dofs": 84_240,
            "independent_trace_rows": 19_980,
            "predicted_direct_solve_rows": 20_060,
        },
    },
    "h15_top_air_remote_p5_interior_bridge_v1": {
        "plan_name": (
            "h15_top_air_remote_p5_interior_bridge_plan_v1.json"
        ),
        "component_names": {
            1: "hp_factorial_bridge_mpi1_v1.json",
            2: "hp_factorial_bridge_mpi2_v1.json",
            8: "hp_factorial_bridge_mpi8_v1.json",
        },
        "schema_version": "case097.hp-factorial-bridge-component.v1",
        "pass_status": "hp_factorial_bridge_component_pass",
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 102},
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 134,
            "hanging_patch_count": 6,
            "raw_broken_active_fe_dofs": 77_455,
            "raw_broken_trace_rows": 23_875,
            "hanging_slave_rows": 1_250,
            "periodic_slave_rows": 4_235,
            "actual_full3d_equivalent_active_fe_dofs": 76_205,
            "independent_trace_rows": 18_390,
            "predicted_direct_solve_rows": 18_470,
        },
    },
    SELECTIVE_FACE_CANDIDATE_ID: {
        "plan_name": "h15_grating_top_selective_p6_faces_plan_v1.json",
        "component_names": {
            1: "selective_p6_face_mpi1_v1.json",
            2: "selective_p6_face_mpi2_v1.json",
            8: "selective_p6_face_mpi8_v1.json",
        },
        "schema_version": "case097.selective-p6-face-component.v1",
        "pass_status": "selective_p6_face_component_pass",
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
        "variable_interior": False,
        "selected_p6_face_geometry_keys": (
            SELECTIVE_P6_FACE_GEOMETRY_KEYS
        ),
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 134,
            "hanging_patch_count": 6,
            "raw_broken_active_fe_dofs": 84_375,
            "raw_broken_trace_rows": 24_075,
            "hanging_slave_rows": 1_250,
            "periodic_slave_rows": 4_235,
            "actual_full3d_equivalent_active_fe_dofs": 83_125,
            "independent_trace_rows": 18_590,
            "predicted_direct_solve_rows": 18_670,
        },
    },
    OUTER_TOP_HP_CANDIDATE_ID: {
        "plan_name": "h15_outer_top_periodic_p5fine_plan_v1.json",
        "component_names": {
            1: "outer_top_periodic_p5fine_mpi1_v2.json",
            2: "outer_top_periodic_p5fine_mpi2_v2.json",
            8: "outer_top_periodic_p5fine_mpi8_v2.json",
        },
        "schema_version": (
            "case097.outer-top-periodic-p5fine-component.v2"
        ),
        "pass_status": "outer_top_periodic_p5fine_component_pass",
        "marked_root_boxes": (
            (41.75, 0.0, 120.0, 50.0, 12.5, 130.0),
        ),
        "variable_interior": True,
        "cell_interior_policy": "all_refined_children_p5",
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 116},
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 148,
            "hanging_patch_count": 8,
            "raw_broken_active_fe_dofs": 86_530,
            "raw_broken_trace_rows": 26_650,
            "hanging_slave_rows": 1_680,
            "periodic_slave_rows": 4_690,
            "actual_full3d_equivalent_active_fe_dofs": 84_850,
            "independent_trace_rows": 20_280,
            "predicted_direct_solve_rows": 20_360,
        },
    },
    LEFT_GRATING_TOP_HP_CANDIDATE_ID: {
        "plan_name": "h15_left_grating_top_closure_p5fine_plan_v1.json",
        "selection_name": (
            "bounded_single_seed_top_air_hp_selection_v2.json"
        ),
        "selection_algorithm_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/"
            "analyze_bounded_single_seed_top_air_hp_selection.py"
        ),
        "component_names": {
            1: "left_grating_top_closure_p5fine_mpi1_v1.json",
            2: "left_grating_top_closure_p5fine_mpi2_v1.json",
            8: "left_grating_top_closure_p5fine_mpi8_v1.json",
        },
        "schema_version": (
            "case097.left-grating-top-closure-p5fine-component.v1"
        ),
        "pass_status": (
            "left_grating_top_closure_p5fine_component_pass"
        ),
        "marked_root_boxes": (
            (16.5, 0.0, 120.0, 25.0, 12.5, 130.0),
        ),
        "variable_interior": True,
        "cell_interior_policy": "all_refined_children_p5",
        "cell_degree_counts": {"p4": 0, "p5": 48, "p6": 114},
        "expected": {
            "root_cell_count": 120,
            "leaf_cell_count": 162,
            "hanging_patch_count": 14,
            "raw_broken_active_fe_dofs": 91_805,
            "raw_broken_trace_rows": 28_985,
            "hanging_slave_rows": 2_890,
            "periodic_slave_rows": 4_525,
            "actual_full3d_equivalent_active_fe_dofs": 88_915,
            "independent_trace_rows": 21_570,
            "predicted_direct_solve_rows": 21_650,
        },
    },
}


def _candidate_spec(candidate_id: str) -> Mapping[str, Any]:
    try:
        return CANDIDATE_SPECS[str(candidate_id)]
    except KeyError as exc:
        raise ValueError(f"unknown Task035d candidate {candidate_id!r}") from exc


def _plan_path(spec: Mapping[str, Any]) -> Path:
    return RECORD_DIR / str(spec["plan_name"])
PRIOR_AUTHORITIES = {
    "phase_a_compact": {
        "path": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "compact_authority_v1.json"
        ),
        "sha256": (
            "2e896ef45bbfc5c11901503269d11c0321106c9e41f71729ac7c6fc722687403"
        ),
    },
    "local_h_attempt2_mpi_identity_v3": {
        "path": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "local_h_attempt2_mpi_identity_v3.json"
        ),
        "sha256": (
            "c293fc07284435c075fc54ba4948f5809d9553cb4693929c270848aca8fd15e2"
        ),
    },
}
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
    "src/adaptivity/selective_face_complement.py",
    "src/adaptivity/selective_face_root_transfer.py",
    "src/adaptivity/variable_p_selective_face_dwr.py",
    "src/constraints/high_order_floquet_trace.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/dtn_port_3d.py",
    (
        "benchmarks/cases/"
        "097_goal_oriented_exact_sequence_hp_adaptivity/"
        f"{GENERATOR_NAME}"
    ),
    (
        "benchmarks/cases/"
        "097_goal_oriented_exact_sequence_hp_adaptivity/"
        f"{CHECKER_NAME}"
    ),
)


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


def _write_new(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                _plain(payload),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    return _sha256(path)


def _git_output(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args),
        cwd=ROOT,
        text=True,
    ).strip()


def _commit_blob_sha(source_sha: str, relative: str) -> str:
    content = subprocess.check_output(
        ("git", "show", f"{source_sha}:{relative}"),
        cwd=ROOT,
    )
    return hashlib.sha256(content).hexdigest()


def _live_source_identity(
    comm: MPI.Intracomm,
    *,
    expected_sha: str,
    extra_relative_files: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    relative_files = tuple(
        dict.fromkeys((*NUMERICAL_RELATIVE_FILES, *extra_relative_files))
    )
    head = _git_output("rev-parse", "HEAD")
    status = [
        line
        for line in _git_output(
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            *relative_files,
        ).splitlines()
        if line
    ]
    live = {
        relative: _sha256(ROOT / relative)
        for relative in relative_files
    }
    committed = {
        relative: _commit_blob_sha(expected_sha, relative)
        for relative in relative_files
    }
    local = {
        "rank": int(comm.rank),
        "head": head,
        "expected_sha": expected_sha,
        "status_lines": status,
        "mismatched_files": sorted(
            relative
            for relative in relative_files
            if live[relative] != committed[relative]
        ),
    }
    rows = comm.allgather(local)
    passed = all(
        row["head"] == expected_sha
        and not row["status_lines"]
        and not row["mismatched_files"]
        for row in rows
    )
    if not passed:
        raise RuntimeError("production authority requires clean numerical source")
    return {
        "head": head,
        "expected_sha": expected_sha,
        "verified_clean_numerical_source": True,
        "rank_checks": rows,
        "numerical_file_sha256": live,
    }


def _environment(comm: MPI.Intracomm) -> dict[str, Any]:
    local = {
        "rank": int(comm.rank),
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "python_executable": sys.executable,
        "dolfinx": dolfinx.__version__,
        "basix": basix.__version__,
        "petsc4py": petsc4py.__version__,
        "mpi4py": mpi4py.__version__,
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_vendor": list(MPI.get_vendor()),
        "mpi_library_version": MPI.Get_library_version().strip(),
    }
    rows = comm.allgather(local)
    comparable = [
        {key: value for key, value in row.items() if key != "rank"}
        for row in rows
    ]
    passed = bool(
        os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        and str(np.dtype(PETSc.ScalarType)) == "complex128"
        and str(np.dtype(PETSc.IntType)) == "int32"
        and all(row == comparable[0] for row in comparable[1:])
    )
    if not passed:
        raise RuntimeError("MPI ABI preflight failed")
    return {
        "mpi_size": int(comm.size),
        "rank_environments": rows,
        "all_ranks_identical": True,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
    }


def _prior_authorities() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, expected in PRIOR_AUTHORITIES.items():
        path = ROOT / expected["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _sha256(path) != expected["sha256"] or payload.get("pass") is not True:
            raise RuntimeError(f"prior authority drifted or failed: {name}")
        result[name] = {
            **expected,
            "status": payload.get("status"),
            "pass": True,
        }
    return result


def build_plan_payload(
    candidate_id: str = DEFAULT_CANDIDATE_ID,
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    cfg = target_stage4_config(degree=6, h_nm=15.0)
    marked = tuple(spec["marked_root_boxes"])
    selected_p6_faces = tuple(
        tuple(map(int, key))
        for key in spec.get("selected_p6_face_geometry_keys", ())
    )
    overrides = None
    provenance: dict[str, Any]
    if spec["variable_interior"]:
        forest = _build_forest(
            cfg,
            comm_size=8,
            marked_root_boxes=marked,
            maximum_level=1,
        )
        policy = spec.get(
            "cell_interior_policy",
            "remote_outer_level0_p5",
        )
        if policy == "remote_outer_level0_p5":
            overrides = {
                cell.box: 5
                for cell in forest.leaves
                if (
                    cell.key.level == 0
                    and cell.material_tag == int(cfg.tags.air)
                    and cell.box[2] >= 0.0
                    and cell.box[5] <= 120.0
                    and (
                        cell.box[3] <= 8.25
                        or cell.box[0] >= 41.75
                    )
                )
            }
        elif policy == "all_refined_children_p5":
            overrides = {
                cell.box: 5
                for cell in forest.leaves
                if cell.key.level == 1
            }
        else:
            raise RuntimeError(
                f"unknown local-h cell-interior policy {policy!r}"
            )
        expected_p5 = int(spec["cell_degree_counts"]["p5"])
        if len(overrides) != expected_p5:
            raise RuntimeError(
                "combined h/p classifier marked "
                f"{len(overrides)} cells, expected {expected_p5}"
            )
        is_factorial_bridge = (
            candidate_id
            == "h15_top_air_remote_p5_interior_bridge_v1"
        )
        is_bounded_fine_p5_hp = candidate_id in {
            OUTER_TOP_HP_CANDIDATE_ID,
            LEFT_GRATING_TOP_HP_CANDIDATE_ID,
        }
        if is_bounded_fine_p5_hp:
            is_selected_left_grating = (
                candidate_id == LEFT_GRATING_TOP_HP_CANDIDATE_ID
            )
            selection_authority = None
            if is_selected_left_grating:
                selection_path = RECORD_DIR / str(
                    spec["selection_name"]
                )
                selection_payload = json.loads(
                    selection_path.read_text(encoding="utf-8")
                )
                if not (
                    selection_payload.get("pass") is True
                    and selection_payload.get("selected_action", {}).get(
                        "candidate_id"
                    )
                    == candidate_id
                ):
                    raise RuntimeError(
                        "bounded single-seed selection authority is invalid"
                    )
                selection_authority = {
                    "path": str(selection_path.relative_to(ROOT)),
                    "sha256": _sha256(selection_path),
                    "status": selection_payload["status"],
                    "location_oracle_only": True,
                    "actual_local_h_dwr_surplus_available": False,
                }
            provenance = {
                "purpose": (
                    "Task035d bounded single-seed-catalog left-grating-top "
                    "local-h closure plus fine-cell p5-interior "
                    "discriminator"
                    if is_selected_left_grating
                    else (
                        "Task035d cost-aware outer-top periodic local-h plus "
                        "fine-cell p5-interior discriminator"
                    )
                ),
                "candidate_id": candidate_id,
                "h_action": (
                    "split the x=16.5..25 nm grating-top root at "
                    "z=120..130 nm, with exact y-periodic and material "
                    "interface closure"
                    if is_selected_left_grating
                    else (
                        "split the x-periodic outer top-air root orbit at "
                        "z=120..130 nm, with exact x/y periodic closure"
                    )
                ),
                "h_action_evidence": (
                    "the complete bounded single-seed compact-DWR catalog gives "
                    "this budget-feasible closure the largest positive "
                    "failed-goal alignment and the best alignment per "
                    "added DoF and solve row; face DWR remains a location "
                    "oracle, not an unrun local-h surplus"
                    if is_selected_left_grating
                    else (
                        "the frozen actual selected-face DWR ranks both "
                        "outer top-port periodic faces among the sensitive "
                        "actions, while directional-z h13 is the positive "
                        "h oracle; this is not an unrun-face or local-h "
                        "DWR claim"
                    )
                ),
                "p_action": (
                    f"use p5 cell interiors on all {expected_p5} h/2 "
                    "children and "
                    "physically omit their inactive p6 interior modes"
                ),
                "p_action_evidence": (
                    "cost guard required by the 90000 active-FE-DoF gate; "
                    "the p5 action is restricted to newly h-refined cells "
                    "and carries no standalone accuracy credit"
                ),
                "factorial_bridge": False,
                "accuracy_credit": False,
                "complete_combined_hp_credit": False,
                "ordinary_default_changed": False,
            }
            if is_selected_left_grating:
                provenance.update(
                    {
                        "single_seed_closure_catalog_complete_for_"
                        "available_compact_dwr": True,
                        "selection_authority": selection_authority,
                    }
                )
        else:
            provenance = {
            "purpose": (
                "Task035d factorial bridge isolating remote interior "
                "p-down on the accepted one-sided local-h mesh"
                if is_factorial_bridge
                else (
                    "Task035d first local-h plus true variable-interior "
                    "candidate"
                )
            ),
            "candidate_id": candidate_id,
            "h_action": (
                "the frozen one-sided top-air split and y-periodic closure "
                "are unchanged from h15_top_air_local_h_v1"
                if is_factorial_bridge
                else (
                    "one split in each top-air root immediately outside "
                    "the left and right grating sidewalls, then "
                    "y-periodic closure"
                )
            ),
            "h_action_evidence": (
                "factorial control: no new h action relative to the "
                "one-sided 6/12 power plus 6/12 amplitude anchor; "
                "not actual DWR or adjoint credit"
                if is_factorial_bridge
                else (
                    "symmetric diagnostic response to the h15 one-sided "
                    "local-h 6/12 power plus 6/12 amplitude controlled "
                    "negative; heuristic channel-directed action, not "
                    "actual DWR or adjoint credit"
                )
            ),
            "p_action": (
                "p6-to-p5 cell-interior only in 32 unrefined homogeneous "
                "air leaves at the two far lateral columns, excluding "
                "grating, sidewall-adjacent, local-h, top-port, and "
                "bottom-port cells"
            ),
            "p_action_evidence": (
                "factorial A-to-B discriminator for the degradation seen "
                "after the mixed symmetric-h plus remote-p5 action; "
                "no variable trace, DWR, or full combined-hp completion "
                "credit"
                if is_factorial_bridge
                else (
                    "geometry smoothness and distance guard; no variable "
                    "trace, DWR, or full combined-hp completion credit"
                )
            ),
            "factorial_bridge": is_factorial_bridge,
            "accuracy_credit": False,
            "complete_combined_hp_credit": False,
            "ordinary_default_changed": False,
            }
    elif selected_p6_faces:
        provenance = {
            "purpose": (
                "Task035d root-cause-guided selective p6 whole-face "
                "enrichment on the accepted one-sided local-h mesh"
            ),
            "candidate_id": candidate_id,
            "seed": (
                "ten safe non-hanging, non-periodic grating-top z=120 "
                "physical faces; no port face and no periodic slave"
            ),
            "selection_evidence": (
                "root-cause-guided first discriminator only; no pre-run "
                "DWR credit. The actual cross-trace Galerkin and "
                "12-channel adjoint report must independently qualify "
                "or reject this action"
            ),
            "accuracy_credit": False,
            "goal_oriented_selection_credit_before_run": False,
            "ordinary_default_changed": False,
        }
    else:
        provenance = {
            "purpose": "Task035d h-only first formal candidate",
            "candidate_id": candidate_id,
            "seed": (
                "Task035b fixed p5-trace/p6-interior h15 plus "
                "minimum top-air local-h split"
            ),
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    return stage4_local_h_refinement_plan_payload(
        cfg,
        marked,
        comm_size=8,
        trace_degree=5,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=overrides,
        selected_p6_face_geometry_keys=selected_p6_faces,
    )


def _stable_identity(
    context: Any,
    reduction: Any,
) -> dict[str, Any]:
    mesh = context.audit
    forest = mesh["forest"]
    carrier = mesh["carrier"]
    physical = reduction.audit["physical_trace"]
    constraints = reduction.audit["trace_constraints"]
    degree_plan = reduction.audit["degree_plan"]
    return {
        "plan_file_sha256": context.plan_file_sha256,
        "base_config_identity_sha256": mesh[
            "base_config_identity_sha256"
        ],
        "root_cell_count": mesh["root_cell_count"],
        "leaf_cell_count": mesh["leaf_cell_count"],
        "hanging_patch_count": mesh["hanging_patch_count"],
        "leaf_catalog_sha256": forest["leaf_catalog_sha256"],
        "hanging_face_catalog_sha256": forest[
            "hanging_face_catalog_sha256"
        ],
        "carrier_connectivity_sha256": carrier[
            "canonical_connectivity_sha256"
        ],
        "physical_facet_catalog_sha256": carrier[
            "physical_facet_catalog_sha256"
        ],
        "material_catalog_sha256": carrier["material_catalog_sha256"],
        "physical_authority_sha256": physical[
            "physical_authority_sha256"
        ],
        "flattened_graph_sha256": constraints[
            "flattened_graph_sha256"
        ],
        "canonical_cell_graph_sha256": constraints[
            "canonical_cell_graph_sha256"
        ],
        "mesh_cell_box_catalog_sha256": degree_plan[
            "mesh_cell_box_catalog_sha256"
        ],
        "cell_degree_plan_sha256": degree_plan[
            "cell_degree_plan_sha256"
        ],
        "cell_degree_counts": degree_plan["cell_degree_counts"],
        "geometry_canonical_entity_degree_sha256": degree_plan[
            "geometry_canonical_entity_degree_sha256"
        ],
        "trace_degree_values": degree_plan["trace_degree_values"],
        "selected_p6_face_count": physical["selected_p6_face_count"],
        "selected_p6_face_geometry_keys": physical[
            "selected_p6_face_geometry_keys"
        ],
        "selected_p6_periodic_orbit_count": physical[
            "selected_p6_periodic_orbit_count"
        ],
        "selective_trace_full3d_dof_delta": physical[
            "selective_trace_full3d_dof_delta"
        ],
        "local_variable_trace_implemented": degree_plan[
            "local_variable_trace_implemented"
        ],
        "raw_broken_active_fe_dofs": reduction.audit[
            "raw_broken_active_fe_dofs"
        ],
        "raw_broken_trace_rows": reduction.audit[
            "raw_broken_trace_rows"
        ],
        "hanging_slave_rows": reduction.audit["hanging_slave_rows"],
        "periodic_slave_rows": reduction.audit["periodic_slave_rows"],
        "actual_full3d_equivalent_active_fe_dofs": reduction.audit[
            "actual_full3d_equivalent_active_fe_dofs"
        ],
        "independent_trace_rows": reduction.audit[
            "independent_trace_rows"
        ],
        "predicted_direct_solve_rows": (
            int(reduction.audit["independent_trace_rows"]) + 80
        ),
    }


def generate_component(
    comm: MPI.Intracomm,
    *,
    source_sha: str,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    plan_path = _plan_path(spec)
    plan_relative = str(plan_path.relative_to(ROOT))
    if not plan_path.is_file():
        raise FileNotFoundError(f"tracked local-h plan is missing: {plan_path}")
    tracked = subprocess.run(
        ("git", "ls-files", "--error-unmatch", plan_relative),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    if not tracked:
        raise RuntimeError("production local-h plan must be tracked")
    extra_relative_files = [plan_relative]
    selection_relative = None
    selection_input_identity = True
    if spec.get("selection_name") is not None:
        selection_path = RECORD_DIR / str(spec["selection_name"])
        selection_relative = str(selection_path.relative_to(ROOT))
        if not selection_path.is_file():
            raise FileNotFoundError(
                f"tracked selection authority is missing: {selection_path}"
            )
        selection_tracked = subprocess.run(
            (
                "git",
                "ls-files",
                "--error-unmatch",
                selection_relative,
            ),
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
        if not selection_tracked:
            raise RuntimeError(
                "production selection authority must be tracked"
            )
        extra_relative_files.append(selection_relative)
        selection_payload = json.loads(
            selection_path.read_text(encoding="utf-8")
        )
        selection_inputs = selection_payload.get("inputs")
        if not isinstance(selection_inputs, dict) or not selection_inputs:
            raise RuntimeError(
                "selection authority has no frozen input manifest"
            )
        selection_source_files = selection_payload.get(
            "source_identity",
            {},
        ).get("file_sha256")
        selection_source_sha = str(
            selection_payload.get("source_sha", "")
        )
        expected_selection_files = set(selection_inputs) | {
            str(spec["selection_algorithm_relative"])
        }
        if (
            not isinstance(selection_source_files, dict)
            or not selection_source_files
            or set(selection_source_files) != expected_selection_files
            or selection_payload.get("source_identity", {}).get(
                "verified_clean_algorithm_and_inputs"
            )
            is not True
            or selection_payload.get("source_identity", {}).get("head")
            != selection_source_sha
            or not re.fullmatch(
                r"[0-9a-f]{40}",
                selection_source_sha,
            )
            or any(
                selection_source_files.get(str(relative))
                != str(digest)
                for relative, digest in selection_inputs.items()
            )
            or any(
                _commit_blob_sha(selection_source_sha, str(relative))
                != str(digest)
                for relative, digest in selection_source_files.items()
            )
        ):
            raise RuntimeError(
                "selection algorithm/input source manifest is invalid"
            )
        for relative, expected_digest in selection_source_files.items():
            relative = str(relative)
            dependency = (ROOT / relative).resolve()
            try:
                dependency.relative_to(ROOT.resolve())
            except ValueError as exc:
                raise RuntimeError(
                    "selection dependency escapes repository root"
                ) from exc
            dependency_tracked = subprocess.run(
                ("git", "ls-files", "--error-unmatch", relative),
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode == 0
            if not dependency_tracked or not dependency.is_file():
                raise RuntimeError(
                    f"selection dependency is not tracked: {relative}"
                )
            if _sha256(dependency) != str(expected_digest):
                raise RuntimeError(
                    f"selection dependency hash drifted: {relative}"
                )
            extra_relative_files.append(relative)
    source = _live_source_identity(
        comm,
        expected_sha=source_sha,
        extra_relative_files=tuple(extra_relative_files),
    )
    environment = _environment(comm)
    prior = _prior_authorities()

    cfg = target_stage4_config(degree=6, h_nm=15.0)
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        plan_path,
        comm=comm,
    )
    context = mesh_data.local_h_context
    if context is None:
        raise RuntimeError("production local-h context was not retained")
    reduction = build_stage4_local_h_reduction_authority(
        context,
        phase_x=cfg.floquet_phase_x,
        phase_y=cfg.floquet_phase_y,
    )
    stable = _stable_identity(context, reduction)
    selected_p6_faces = tuple(
        tuple(map(int, key))
        for key in spec.get("selected_p6_face_geometry_keys", ())
    )
    physical = reduction.audit["physical_trace"]
    degree_plan = reduction.audit["degree_plan"]
    trace = reduction.audit["trace_constraints"]
    reduction_mesh = reduction.audit["mesh"]
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    expected_face_keys = [list(key) for key in selected_p6_faces]
    recorded_degree_plan_sha = plan_payload.get(
        "cell_interior_degree_plan_sha256"
    )
    runtime_degree_plan_sha = context.audit[
        "cell_interior_degree_plan_sha256"
    ]
    effective_degree_plan_sha = (
        recorded_degree_plan_sha or runtime_degree_plan_sha
    )
    entity_degree_identity: dict[str, Any] = {
        "edge_degree": int(plan_payload["trace_degree"]),
        "face_degree": int(plan_payload["trace_degree"]),
        "cell_interior_degree_plan_sha256": (
            effective_degree_plan_sha
        ),
    }
    if selected_p6_faces:
        entity_degree_identity["selected_p6_face_geometry_keys"] = (
            expected_face_keys
        )
    expected_entity_degree_sha = hashlib.sha256(
        json.dumps(
            entity_degree_identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    forest = context.audit["forest"]
    reduction_forest = reduction_mesh["forest"]
    expected_forest = plan_payload["expected_forest"]
    trace_values = [5, 6] if selected_p6_faces else [5]
    expected_selective_action = (
        "non_hanging_whole_physical_face_p5_to_p6"
        if selected_p6_faces
        else "uniform_base_trace"
    )
    expected_variable_trace = bool(selected_p6_faces)
    expected_marked_roots = [
        {
            "lower": list(mark[:3]),
            "upper": list(mark[3:]),
        }
        for mark in spec["marked_root_boxes"]
    ]
    plan_degree_rows = plan_payload.get("cell_interior_degrees")
    plan_degree_rows = (
        plan_degree_rows
        if isinstance(plan_degree_rows, list)
        else []
    )
    plan_degree_counts = {
        f"p{degree}": sum(
            isinstance(row, dict)
            and int(row.get("degree", -1)) == degree
            for row in plan_degree_rows
        )
        for degree in (4, 5, 6)
    }
    plan_scope_identity = (
        plan_payload["schema_version"]
        == "task035d.stage4-local-h-refinement-plan.v1"
        and plan_payload["trace_degree"] == 5
        and plan_payload["cell_interior_degree"] == 6
        and plan_payload["marked_root_boxes"] == expected_marked_roots
        and plan_payload.get("selected_p6_face_geometry_keys", [])
        == expected_face_keys
        and plan_payload["ordinary_default_changed"] is False
        and (
            (
                isinstance(recorded_degree_plan_sha, str)
                and plan_degree_counts == spec["cell_degree_counts"]
            )
            if spec["variable_interior"]
            else not plan_degree_rows
        )
    )
    checks = {
        "plan_is_tracked": tracked,
        "plan_scope_identity": plan_scope_identity,
        "plan_source_identity": (
            source["numerical_file_sha256"][plan_relative]
            == _sha256(plan_path)
            == _commit_blob_sha(source_sha, plan_relative)
        ),
        "selection_source_identity": (
            selection_relative is None
            or (
                plan_payload["provenance"]["selection_authority"][
                    "path"
                ]
                == selection_relative
                and plan_payload["provenance"]["selection_authority"][
                    "sha256"
                ]
                == source["numerical_file_sha256"][selection_relative]
                == _commit_blob_sha(source_sha, selection_relative)
                and selection_input_identity
                and all(
                    source["numerical_file_sha256"].get(str(relative))
                    == str(digest)
                    for relative, digest in selection_payload[
                        "source_identity"
                    ]["file_sha256"].items()
                )
            )
        ),
        "mesh_authority": context.audit["pass"] is True,
        "reduction_authority": reduction.audit["pass"] is True,
        "mesh_audit_identity": context.audit == reduction_mesh,
        "forest_catalog_identity": (
            expected_forest["leaf_catalog_sha256"]
            == forest["leaf_catalog_sha256"]
            == reduction_forest["leaf_catalog_sha256"]
            == stable["leaf_catalog_sha256"]
            and expected_forest["hanging_face_catalog_sha256"]
            == forest["hanging_face_catalog_sha256"]
            == reduction_forest["hanging_face_catalog_sha256"]
            == stable["hanging_face_catalog_sha256"]
        ),
        "degree_identity": (
            (
                not spec["variable_interior"]
                or recorded_degree_plan_sha
                == runtime_degree_plan_sha
            )
            and effective_degree_plan_sha
            == runtime_degree_plan_sha
            == reduction_mesh["cell_interior_degree_plan_sha256"]
            == degree_plan["cell_degree_plan_sha256"]
            == stable["cell_degree_plan_sha256"]
            and degree_plan["mesh_cell_box_catalog_sha256"]
            == stable["mesh_cell_box_catalog_sha256"]
            and degree_plan["geometry_canonical_entity_degree_sha256"]
            == stable["geometry_canonical_entity_degree_sha256"]
            == expected_entity_degree_sha
        ),
        "expected_dimensions": all(
            int(stable[name]) == int(expected)
            for name, expected in spec["expected"].items()
        ),
        "constraint_kinds": (
            reduction.audit["trace_constraints"]["constraint_kinds"]
            == ["hanging", "floquet"]
        ),
        "owner_routing_qualified": (
            reduction.audit["trace_constraints"][
                "pde_launch_ownership_gate"
            ]
            is True
        ),
        "physical_dof_gate": (
            reduction.audit["active_fe_dof_gate_pass"] is True
        ),
        "cell_interior_policy": (
            (
                reduction.degree_plan.audit[
                    "cell_degree_counts"
                ]
                == spec["cell_degree_counts"]
                and reduction.degree_plan.audit[
                    "local_variable_trace_implemented"
                ]
                is False
                and reduction.degree_plan.audit[
                    "complete_combined_hp_credit"
                ]
                is False
            )
            if spec["variable_interior"]
            else (
                reduction.degree_plan.audit[
                    "cell_degree_counts"
                ]
                == {"p4": 0, "p5": 0, "p6": 134}
            )
        ),
        "selective_trace_policy": (
            context.audit["selected_p6_face_geometry_keys"]
            == expected_face_keys
            and reduction_mesh["selected_p6_face_geometry_keys"]
            == expected_face_keys
            and physical["selected_p6_face_geometry_keys"]
            == expected_face_keys
            and stable["selected_p6_face_geometry_keys"]
            == expected_face_keys
            and all(
                row["selected_p6_face_count"] == len(expected_face_keys)
                for row in (
                    context.audit,
                    reduction_mesh,
                    degree_plan,
                    physical,
                    trace,
                    stable,
                )
            )
            and physical["selected_p6_periodic_orbit_count"] == 0
            and physical["selected_p6_periodic_orbits"] == []
            and stable["selected_p6_periodic_orbit_count"] == 0
            and physical["selective_trace_full3d_dof_delta"]
            == stable["selective_trace_full3d_dof_delta"]
            == 20 * len(expected_face_keys)
            and all(
                row["trace_degree_values"] == trace_values
                for row in (degree_plan, physical, trace, stable)
            )
            and all(
                row["local_variable_trace_implemented"]
                is expected_variable_trace
                for row in (degree_plan, trace, stable)
            )
            and trace["selective_trace_action"]
            == expected_selective_action
        ),
        "prior_attempt2_hash_bound": all(
            row["pass"] is True for row in prior.values()
        ),
        "ordinary_default_unchanged": (
            context.audit["ordinary_default_changed"] is False
            and reduction.audit["ordinary_default_changed"] is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            spec["schema_version"]
        ),
        "status": (
            spec["pass_status"]
            if not failures
            else f"{spec['pass_status']}_failed"
        ),
        "pass": not failures,
        "candidate_id": candidate_id,
        "source_sha": source_sha,
        "source_identity": source,
        "environment": environment,
        "plan": {
            "path": plan_relative,
            "file_sha256": _sha256(plan_path),
            "payload": plan_payload,
        },
        "prior_authorities": prior,
        "stable_identity": stable,
        "mesh_audit": dict(context.audit),
        "reduction_audit": dict(reduction.audit),
        "checks": checks,
        "failures": failures,
        "formal_MPI": 8,
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        choices=tuple(CANDIDATE_SPECS),
        default=DEFAULT_CANDIDATE_ID,
    )
    parser.add_argument(
        "--mode",
        choices=("plan", "component"),
        required=True,
    )
    parser.add_argument("--source-sha")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    spec = _candidate_spec(args.candidate)
    plan_path = _plan_path(spec)
    if args.mode == "plan":
        if comm.size != 1:
            raise ValueError("plan generation is serial")
        output = args.output or plan_path
        if output.resolve() != plan_path.resolve():
            raise ValueError("formal plan output path is fixed")
        payload = build_plan_payload(args.candidate)
    else:
        expected_name = spec["component_names"].get(int(comm.size))
        if expected_name is None:
            raise ValueError("component authority requires MPI1, MPI2, or MPI8")
        if args.source_sha is None:
            raise ValueError("--source-sha is required for component mode")
        output = args.output or (RECORD_DIR / expected_name)
        if output.resolve() != (RECORD_DIR / expected_name).resolve():
            raise ValueError("formal component output path is MPI-specific")
        payload = generate_component(
            comm,
            source_sha=str(args.source_sha),
            candidate_id=args.candidate,
        )
    if comm.rank == 0:
        if output.exists():
            envelope = {
                "ok": False,
                "error": f"authority output is immutable: {output}",
            }
        else:
            digest = _write_new(output, payload)
            envelope = {
                "ok": True,
                "path": str(output),
                "sha256": digest,
                "status": payload["status"],
                "pass": payload.get("pass", True),
            }
    else:
        envelope = None
    envelope = comm.bcast(envelope, root=0)
    if not envelope["ok"]:
        raise FileExistsError(str(envelope["error"]))
    if comm.rank == 0:
        print(json.dumps(envelope, sort_keys=True))
    return 0 if payload.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
