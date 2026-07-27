#!/usr/bin/env python3
"""Independent checker for Task035d production local-h component records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
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
CHECKER_RELATIVE = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/"
    "check_local_h_production_authority.py"
)
CANDIDATE_SPECS = {
    DEFAULT_CANDIDATE_ID: {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_top_air_local_h_plan_v1.json"
        ),
        "record_names": {
            1: "local_h_production_mpi1_v3_owner_gate_fix1.json",
            2: "local_h_production_mpi2_v3_owner_gate_fix1.json",
            8: "local_h_production_mpi8_v3_owner_gate_fix1.json",
        },
        "output_name": (
            "local_h_production_mpi_identity_v3_owner_gate_fix2.json"
        ),
        "schema": "case097.local-h-production-component.v3-integration",
        "pass_status": "local_h_production_component_pass",
        "identity_schema": (
            "case097.local-h-production-mpi-identity.v3-integration"
        ),
        "identity_status": "local_h_production_mpi_identity_pass",
        "pde_launch_scope": "one formal MPI8 h15 local-h direct PDE",
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
        "variable_interior": False,
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
    },
    "h15_symmetric_top_air_remote_p5_interior_v1": {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_symmetric_top_air_remote_p5_interior_plan_v1.json"
        ),
        "record_names": {
            1: "combined_hp_interior_mpi1_v2.json",
            2: "combined_hp_interior_mpi2_v2.json",
            8: "combined_hp_interior_mpi8_v2.json",
        },
        "output_name": "combined_hp_interior_mpi_identity_v2.json",
        "schema": "case097.combined-hp-interior-component.v2",
        "pass_status": "combined_hp_interior_component_pass",
        "identity_schema": (
            "case097.combined-hp-interior-mpi-identity.v2"
        ),
        "identity_status": "combined_hp_interior_mpi_identity_pass",
        "pde_launch_scope": (
            "one formal MPI8 h15 symmetric local-h plus "
            "variable-interior direct PDE"
        ),
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
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 116},
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
            (33.5, 0.0, 120.0, 41.75, 12.5, 130.0),
        ),
    },
    "h15_top_air_remote_p5_interior_bridge_v1": {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_top_air_remote_p5_interior_bridge_plan_v1.json"
        ),
        "record_names": {
            1: "hp_factorial_bridge_mpi1_v1.json",
            2: "hp_factorial_bridge_mpi2_v1.json",
            8: "hp_factorial_bridge_mpi8_v1.json",
        },
        "output_name": "hp_factorial_bridge_mpi_identity_v1.json",
        "schema": "case097.hp-factorial-bridge-component.v1",
        "pass_status": "hp_factorial_bridge_component_pass",
        "identity_schema": (
            "case097.hp-factorial-bridge-mpi-identity.v1"
        ),
        "identity_status": "hp_factorial_bridge_mpi_identity_pass",
        "pde_launch_scope": (
            "one formal MPI8 h15 one-sided local-h plus remote-p5 "
            "interior factorial-bridge direct PDE"
        ),
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
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 102},
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
    },
    SELECTIVE_FACE_CANDIDATE_ID: {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_grating_top_selective_p6_faces_plan_v1.json"
        ),
        "record_names": {
            1: "selective_p6_face_mpi1_v1.json",
            2: "selective_p6_face_mpi2_v1.json",
            8: "selective_p6_face_mpi8_v1.json",
        },
        "output_name": "selective_p6_face_mpi_identity_v1.json",
        "schema": "case097.selective-p6-face-component.v1",
        "pass_status": "selective_p6_face_component_pass",
        "identity_schema": (
            "case097.selective-p6-face-mpi-identity.v1"
        ),
        "identity_status": "selective_p6_face_mpi_identity_pass",
        "pde_launch_scope": (
            "one formal MPI8 h15 one-sided local-h plus ten "
            "selective-p6-whole-face direct PDE"
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
        "variable_interior": False,
        "selected_p6_face_geometry_keys": (
            SELECTIVE_P6_FACE_GEOMETRY_KEYS
        ),
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
        ),
    },
    OUTER_TOP_HP_CANDIDATE_ID: {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_outer_top_periodic_p5fine_plan_v1.json"
        ),
        "record_names": {
            1: "outer_top_periodic_p5fine_mpi1_v2.json",
            2: "outer_top_periodic_p5fine_mpi2_v2.json",
            8: "outer_top_periodic_p5fine_mpi8_v2.json",
        },
        "output_name": "outer_top_periodic_p5fine_mpi_identity_v2.json",
        "schema": "case097.outer-top-periodic-p5fine-component.v2",
        "pass_status": "outer_top_periodic_p5fine_component_pass",
        "identity_schema": (
            "case097.outer-top-periodic-p5fine-mpi-identity.v2"
        ),
        "identity_status": "outer_top_periodic_p5fine_mpi_identity_pass",
        "pde_launch_scope": (
            "one formal MPI8 h15 outer-top periodic local-h plus "
            "fine-cell p5-interior direct PDE"
        ),
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
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 32, "p6": 116},
        "marked_root_boxes": (
            (41.75, 0.0, 120.0, 50.0, 12.5, 130.0),
        ),
    },
    LEFT_GRATING_TOP_HP_CANDIDATE_ID: {
        "plan_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "h15_left_grating_top_closure_p5fine_plan_v1.json"
        ),
        "record_names": {
            1: "left_grating_top_closure_p5fine_mpi1_v1.json",
            2: "left_grating_top_closure_p5fine_mpi2_v1.json",
            8: "left_grating_top_closure_p5fine_mpi8_v1.json",
        },
        "selection_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
            "bounded_single_seed_top_air_hp_selection_v2.json"
        ),
        "selection_algorithm_relative": (
            "benchmarks/cases/"
            "097_goal_oriented_exact_sequence_hp_adaptivity/"
            "analyze_bounded_single_seed_top_air_hp_selection.py"
        ),
        "output_name": (
            "left_grating_top_closure_p5fine_mpi_identity_v1.json"
        ),
        "schema": (
            "case097.left-grating-top-closure-p5fine-component.v1"
        ),
        "pass_status": (
            "left_grating_top_closure_p5fine_component_pass"
        ),
        "identity_schema": (
            "case097.left-grating-top-closure-p5fine-mpi-identity.v1"
        ),
        "identity_status": (
            "left_grating_top_closure_p5fine_mpi_identity_pass"
        ),
        "pde_launch_scope": (
            "one formal MPI8 h15 left-grating-top local-h closure plus "
            "fine-cell p5-interior direct PDE"
        ),
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
        "variable_interior": True,
        "cell_degree_counts": {"p4": 0, "p5": 48, "p6": 114},
        "marked_root_boxes": (
            (16.5, 0.0, 120.0, 25.0, 12.5, 130.0),
        ),
    },
}


def _candidate_spec(candidate_id: str) -> Mapping[str, Any]:
    try:
        return CANDIDATE_SPECS[str(candidate_id)]
    except KeyError as exc:
        raise ValueError(f"unknown Task035d candidate {candidate_id!r}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value}")
        ),
    )
    if not isinstance(payload, dict):
        raise TypeError("record root must be an object")
    return payload


def _commit_blob_sha(source_sha: str, relative: str) -> str:
    content = subprocess.check_output(
        ("git", "show", f"{source_sha}:{relative}"),
        cwd=ROOT,
    )
    return hashlib.sha256(content).hexdigest()


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _validate_one(
    path: Path,
    payload: Mapping[str, Any],
    *,
    candidate_id: str,
    spec: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    try:
        mpi_size = int(payload["environment"]["mpi_size"])
        source_sha = str(payload["source_sha"])
        source = payload["source_identity"]
        stable = payload["stable_identity"]
        mesh = payload["mesh_audit"]
        reduction = payload["reduction_audit"]
        reduction_mesh = reduction["mesh"]
        trace = reduction["trace_constraints"]
        environment = payload["environment"]
        rank_rows = environment["rank_environments"]
        comparable = [
            {key: value for key, value in row.items() if key != "rank"}
            for row in rank_rows
        ]
        if path.name != spec["record_names"].get(mpi_size):
            failures.append("record_name")
        if payload.get("schema_version") != spec["schema"]:
            failures.append("schema")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            failures.append("source_sha")
        if not (
            payload.get("pass") is True
            and payload.get("status") == spec["pass_status"]
            and payload.get("candidate_id") == candidate_id
            and payload.get("heavy_pde_started") is False
            and payload.get("pde_accuracy_credit") is False
            and payload.get("ordinary_default_changed") is False
        ):
            failures.append("component_scope")
        if not (
            source.get("head") == source_sha
            and source.get("expected_sha") == source_sha
            and source.get("verified_clean_numerical_source") is True
        ):
            failures.append("source_identity")
        numerical = source.get("numerical_file_sha256")
        if not isinstance(numerical, dict) or not numerical:
            failures.append("numerical_manifest")
        elif any(
            _commit_blob_sha(source_sha, relative) != digest
            for relative, digest in numerical.items()
        ):
            failures.append("numerical_blob_identity")
        if not (
            environment.get("petsc_scalar_type") == "complex128"
            and environment.get("petsc_int_type") == "int32"
            and environment.get("all_ranks_identical") is True
            and len(rank_rows) == mpi_size
            and [row["rank"] for row in rank_rows] == list(range(mpi_size))
            and all(row == comparable[0] for row in comparable[1:])
        ):
            failures.append("mpi_abi")
        plan_relative = str(spec["plan_relative"])
        if payload["plan"]["path"] != plan_relative:
            failures.append("plan_path")
        plan_path = ROOT / plan_relative
        live_plan = _strict_load(plan_path)
        live_plan_sha = _sha256(plan_path)
        committed_plan_sha = _commit_blob_sha(source_sha, plan_relative)
        plan_status = subprocess.check_output(
            (
                "git",
                "status",
                "--short",
                "--untracked-files=all",
                "--",
                plan_relative,
            ),
            cwd=ROOT,
            text=True,
        ).strip()
        if not (
            payload["plan"]["file_sha256"]
            == live_plan_sha
            == committed_plan_sha
            and payload["plan"]["payload"] == live_plan
            and not plan_status
        ):
            failures.append("plan_source_identity")
        selected_p6_faces = tuple(
            tuple(map(int, key))
            for key in spec.get("selected_p6_face_geometry_keys", ())
        )
        expected_face_keys = [list(key) for key in selected_p6_faces]
        expected_marked_roots = [
            {
                "lower": list(mark[:3]),
                "upper": list(mark[3:]),
            }
            for mark in spec["marked_root_boxes"]
        ]
        plan_degree_rows = live_plan.get("cell_interior_degrees")
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
        plan_scope_pass = (
            live_plan.get("schema_version")
            == "task035d.stage4-local-h-refinement-plan.v1"
            and live_plan.get("trace_degree") == 5
            and live_plan.get("cell_interior_degree") == 6
            and live_plan.get("marked_root_boxes")
            == expected_marked_roots
            and live_plan.get(
                "selected_p6_face_geometry_keys",
                [],
            )
            == expected_face_keys
            and live_plan.get("ordinary_default_changed") is False
        )
        if spec["variable_interior"]:
            plan_scope_pass = (
                plan_scope_pass
                and isinstance(
                    live_plan.get(
                        "cell_interior_degree_plan_sha256"
                    ),
                    str,
                )
                and plan_degree_counts == spec["cell_degree_counts"]
            )
        elif plan_degree_rows:
            plan_scope_pass = False
        if not plan_scope_pass:
            failures.append("plan_scope_identity")
        selection_relative = spec.get("selection_relative")
        selection = None
        if selection_relative is not None:
            selection_relative = str(selection_relative)
            selection_path = ROOT / selection_relative
            selection = _strict_load(selection_path)
            selection_status = subprocess.check_output(
                (
                    "git",
                    "status",
                    "--short",
                    "--untracked-files=all",
                    "--",
                    selection_relative,
                ),
                cwd=ROOT,
                text=True,
            ).strip()
            plan_selection = live_plan.get("provenance", {}).get(
                "selection_authority"
            )
            selection_inputs = selection.get("inputs")
            selection_inputs_pass = (
                isinstance(selection_inputs, dict)
                and bool(selection_inputs)
            )
            selection_source_files = selection.get(
                "source_identity",
                {},
            ).get("file_sha256")
            selection_source_sha = str(
                selection.get("source_sha", "")
            )
            expected_selection_files = (
                set(selection_inputs)
                if isinstance(selection_inputs, dict)
                else set()
            ) | {str(spec["selection_algorithm_relative"])}
            selection_inputs_pass = bool(
                selection_inputs_pass
                and isinstance(selection_source_files, dict)
                and bool(selection_source_files)
                and set(selection_source_files)
                == expected_selection_files
                and selection.get("source_identity", {}).get(
                    "verified_clean_algorithm_and_inputs"
                )
                is True
                and selection.get("source_identity", {}).get("head")
                == selection_source_sha
                and re.fullmatch(
                    r"[0-9a-f]{40}",
                    selection_source_sha,
                )
                and all(
                    selection_source_files.get(str(relative))
                    == str(digest)
                    for relative, digest in (
                        selection_inputs.items()
                        if isinstance(selection_inputs, dict)
                        else ()
                    )
                )
                and all(
                    _commit_blob_sha(
                        selection_source_sha,
                        str(relative),
                    )
                    == str(digest)
                    for relative, digest in (
                        selection_source_files.items()
                        if isinstance(selection_source_files, dict)
                        else ()
                    )
                )
            )
            if isinstance(selection_source_files, dict):
                for relative, recorded_digest in (
                    selection_source_files.items()
                ):
                    relative = str(relative)
                    dependency = (ROOT / relative).resolve()
                    try:
                        dependency.relative_to(ROOT.resolve())
                    except ValueError:
                        selection_inputs_pass = False
                        continue
                    dependency_status = subprocess.check_output(
                        (
                            "git",
                            "status",
                            "--short",
                            "--untracked-files=all",
                            "--",
                            relative,
                        ),
                        cwd=ROOT,
                        text=True,
                    ).strip()
                    selection_inputs_pass = bool(
                        selection_inputs_pass
                        and dependency.is_file()
                        and not dependency_status
                        and _sha256(dependency)
                        == str(recorded_digest)
                        == _commit_blob_sha(source_sha, relative)
                        and isinstance(numerical, dict)
                        and numerical.get(relative)
                        == str(recorded_digest)
                    )
            selected_action = selection.get("selected_action")
            selected_action = (
                selected_action
                if isinstance(selected_action, dict)
                else {}
            )
            if not (
                isinstance(plan_selection, dict)
                and plan_selection.get("path") == selection_relative
                and plan_selection.get("sha256")
                == _sha256(selection_path)
                == _commit_blob_sha(source_sha, selection_relative)
                and plan_selection.get("location_oracle_only") is True
                and plan_selection.get(
                    "actual_local_h_dwr_surplus_available"
                )
                is False
                and selection.get("pass") is True
                and selection.get("selected_action", {}).get(
                    "candidate_id"
                )
                == candidate_id
                and selection_inputs_pass
                and selected_action.get("marked_root_nm")
                == list(spec["marked_root_boxes"][0])
                and selected_action.get(
                    "actual_full3d_equivalent_active_fe_dofs"
                )
                == spec["expected"][
                    "actual_full3d_equivalent_active_fe_dofs"
                ]
                and selected_action.get(
                    "predicted_direct_solve_rows"
                )
                == spec["expected"]["predicted_direct_solve_rows"]
                and selected_action.get("fine_p5_cell_count")
                == spec["cell_degree_counts"]["p5"]
                and selected_action.get("remaining_p6_cell_count")
                == spec["cell_degree_counts"]["p6"]
                and selected_action.get("selected_p6_face_count")
                == len(expected_face_keys)
                and not selection_status
            ):
                failures.append("selection_source_identity")
        if any(
            int(stable.get(name, -1)) != expected
            for name, expected in spec["expected"].items()
        ):
            failures.append("frozen_dimensions")
        if not (
            reduction.get("pass") is True
            and reduction.get("active_fe_dof_gate_pass") is True
            and trace.get("pass") is True
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
        ):
            failures.append("production_reduction")
        if spec["variable_interior"] and not (
            reduction["degree_plan"].get("cell_degree_counts")
            == spec["cell_degree_counts"]
            and reduction["degree_plan"].get(
                "local_variable_trace_implemented"
            )
            is False
            and reduction["degree_plan"].get(
                "complete_combined_hp_credit"
            )
            is False
            and stable.get("cell_degree_counts")
            == spec["cell_degree_counts"]
            and isinstance(stable.get("cell_degree_plan_sha256"), str)
            and isinstance(
                stable.get(
                    "geometry_canonical_entity_degree_sha256"
                ),
                str,
            )
        ):
            failures.append("variable_interior_scope")
        physical = reduction["physical_trace"]
        degree_plan = reduction["degree_plan"]
        recorded_plan_degree_sha = live_plan.get(
            "cell_interior_degree_plan_sha256"
        )
        runtime_plan_degree_sha = mesh.get(
            "cell_interior_degree_plan_sha256"
        )
        effective_plan_degree_sha = (
            recorded_plan_degree_sha or runtime_plan_degree_sha
        )
        entity_degree_identity: dict[str, Any] = {
            "edge_degree": int(live_plan["trace_degree"]),
            "face_degree": int(live_plan["trace_degree"]),
            "cell_interior_degree_plan_sha256": (
                effective_plan_degree_sha
            ),
        }
        if selected_p6_faces:
            entity_degree_identity["selected_p6_face_geometry_keys"] = (
                expected_face_keys
            )
        expected_entity_degree_sha = _json_sha256(
            entity_degree_identity
        )
        legacy_uniform_component = (
            candidate_id == DEFAULT_CANDIDATE_ID
            and "cell_degree_plan_sha256" not in degree_plan
            and "selected_p6_face_count" not in physical
            and not selected_p6_faces
            and not spec["variable_interior"]
        )
        if mesh != reduction_mesh:
            failures.append("mesh_audit_identity")
        degree_identity_pass = (
            degree_plan.get("cell_degree_counts")
            == {"p4": 0, "p5": 0, "p6": 134}
            and degree_plan.get("trace_degree") == 5
            and physical.get("degree") == 5
            if legacy_uniform_component
            else (
                (
                    not spec["variable_interior"]
                    or recorded_plan_degree_sha
                    == runtime_plan_degree_sha
                )
                and effective_plan_degree_sha
                == runtime_plan_degree_sha
                == reduction_mesh.get(
                    "cell_interior_degree_plan_sha256"
                )
                == degree_plan.get("cell_degree_plan_sha256")
                == stable.get("cell_degree_plan_sha256")
                and degree_plan.get("mesh_cell_box_catalog_sha256")
                == stable.get("mesh_cell_box_catalog_sha256")
                and degree_plan.get(
                    "geometry_canonical_entity_degree_sha256"
                )
                == stable.get(
                    "geometry_canonical_entity_degree_sha256"
                )
                == expected_entity_degree_sha
            )
        )
        if not degree_identity_pass:
            failures.append("degree_identity")
        expected_forest = live_plan.get("expected_forest")
        expected_forest = (
            expected_forest
            if isinstance(expected_forest, dict)
            else {}
        )
        mesh_forest = mesh.get("forest")
        mesh_forest = mesh_forest if isinstance(mesh_forest, dict) else {}
        reduction_forest = reduction_mesh.get("forest")
        reduction_forest = (
            reduction_forest
            if isinstance(reduction_forest, dict)
            else {}
        )
        if not (
            expected_forest.get("leaf_catalog_sha256")
            == mesh_forest.get("leaf_catalog_sha256")
            == reduction_forest.get("leaf_catalog_sha256")
            == stable.get("leaf_catalog_sha256")
            and expected_forest.get("hanging_face_catalog_sha256")
            == mesh_forest.get("hanging_face_catalog_sha256")
            == reduction_forest.get("hanging_face_catalog_sha256")
            == stable.get("hanging_face_catalog_sha256")
        ):
            failures.append("forest_catalog_identity")
        expected_trace_values = [5, 6] if selected_p6_faces else [5]
        expected_variable_trace = bool(selected_p6_faces)
        expected_selective_action = (
            "non_hanging_whole_physical_face_p5_to_p6"
            if selected_p6_faces
            else "uniform_base_trace"
        )
        trace_rows = (
            mesh,
            reduction_mesh,
            degree_plan,
            physical,
            trace,
            stable,
        )
        trace_scope_pass = (
            (
                degree_plan.get("trace_degree") == 5
                and physical.get("degree") == 5
                and trace.get("degree") == 5
                and live_plan.get(
                    "selected_p6_face_geometry_keys",
                    [],
                )
                == []
            )
            if legacy_uniform_component
            else (
            mesh.get("selected_p6_face_geometry_keys")
            == expected_face_keys
            and reduction_mesh.get("selected_p6_face_geometry_keys")
            == expected_face_keys
            and physical.get("selected_p6_face_geometry_keys")
            == expected_face_keys
            and stable.get("selected_p6_face_geometry_keys")
            == expected_face_keys
            and all(
                row.get("selected_p6_face_count")
                == len(expected_face_keys)
                for row in trace_rows
            )
            and physical.get("selected_p6_periodic_orbit_count") == 0
            and physical.get("selected_p6_periodic_orbits") == []
            and stable.get("selected_p6_periodic_orbit_count") == 0
            and physical.get("selective_trace_full3d_dof_delta")
            == stable.get("selective_trace_full3d_dof_delta")
            == 20 * len(expected_face_keys)
            and all(
                row.get("trace_degree_values")
                == expected_trace_values
                for row in (degree_plan, physical, trace, stable)
            )
            and all(
                row.get("local_variable_trace_implemented")
                is expected_variable_trace
                for row in (degree_plan, trace, stable)
            )
            and trace.get("selective_trace_action")
            == expected_selective_action
            )
        )
        if not trace_scope_pass:
            failures.append(
                "selective_trace_scope"
                if selected_p6_faces
                else "p5_only_trace_scope"
            )
        checks = payload.get("checks")
        if not isinstance(checks, dict) or not checks or not all(checks.values()):
            failures.append("embedded_checks")
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        failures.append(f"exception:{type(exc).__name__}")
    return failures


def check_records(
    paths: tuple[Path, ...],
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    payloads = [_strict_load(path) for path in paths]
    record_failures = {
        path.name: _validate_one(
            path,
            payload,
            candidate_id=candidate_id,
            spec=spec,
        )
        for path, payload in zip(paths, payloads, strict=True)
    }
    failures = [
        f"{name}:{failure}"
        for name, row in record_failures.items()
        for failure in row
    ]
    sources = {str(payload.get("source_sha")) for payload in payloads}
    stable = [payload.get("stable_identity") for payload in payloads]
    numerical = [
        payload.get("source_identity", {}).get("numerical_file_sha256")
        for payload in payloads
    ]
    distributed = [
        payload
        for payload in payloads
        if int(payload["environment"]["mpi_size"]) > 1
    ]
    zero_cross_rank = [
        payload
        for payload in distributed
        if payload["reduction_audit"]["trace_constraints"][
            "cross_rank_hanging_patch_count"
        ]
        == 0
    ]
    positive_cross_rank = [
        payload
        for payload in distributed
        if payload["reduction_audit"]["trace_constraints"][
            "cross_rank_hanging_patch_count"
        ]
        > 0
    ]
    cross_checks = {
        "mpi_sizes_are_1_2_8": {
            int(payload["environment"]["mpi_size"])
            for payload in payloads
        }
        == {1, 2, 8},
        "same_source_sha": len(sources) == 1,
        "same_numerical_blobs": all(row == numerical[0] for row in numerical[1:]),
        "same_physical_identity": all(row == stable[0] for row in stable[1:]),
        "same_selective_trace_identity": all(
            (
                row.get("selected_p6_face_count"),
                row.get("selected_p6_face_geometry_keys"),
                row.get("geometry_canonical_entity_degree_sha256"),
            )
            == (
                stable[0].get("selected_p6_face_count"),
                stable[0].get("selected_p6_face_geometry_keys"),
                stable[0].get(
                    "geometry_canonical_entity_degree_sha256"
                ),
            )
            for row in stable[1:]
        ),
        "rank_local_and_cross_rank_hanging_partitions_qualified": (
            bool(zero_cross_rank)
            and bool(positive_cross_rank)
            and all(
                payload["reduction_audit"]["trace_constraints"][
                    "pde_launch_ownership_gate"
                ]
                is True
                for payload in distributed
            )
            and all(
                sum(
                    payload["reduction_audit"]["trace_constraints"][
                        "owner_routed_trace_cache_audit"
                    ]["request_counts_by_rank"]
                )
                > 0
                for payload in zero_cross_rank
            )
            and all(
                sum(
                    payload["reduction_audit"]["trace_constraints"][
                        "cross_rank_hanging_remote_lookup_counts_by_rank"
                    ]
                )
                > 0
                for payload in positive_cross_rank
            )
        ),
        "no_heavy_pde_or_accuracy_credit": all(
            payload["heavy_pde_started"] is False
            and payload["pde_accuracy_credit"] is False
            for payload in payloads
        ),
    }
    failures.extend(
        f"cross:{name}"
        for name, passed in cross_checks.items()
        if not passed
    )
    source_sha = next(iter(sources)) if len(sources) == 1 else None
    live_head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    checker_status = subprocess.check_output(
        (
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            CHECKER_RELATIVE,
        ),
        cwd=ROOT,
        text=True,
    ).strip()
    checker_live_sha256 = _sha256(Path(__file__))
    checker_committed_sha256 = _commit_blob_sha(
        live_head,
        CHECKER_RELATIVE,
    )
    checker_identity = {
        "path": CHECKER_RELATIVE,
        "source_sha": live_head,
        "live_sha256": checker_live_sha256,
        "committed_sha256": checker_committed_sha256,
        "status_lines": checker_status.splitlines(),
        "verified_clean_checker": (
            checker_live_sha256 == checker_committed_sha256
            and not checker_status
        ),
    }
    if checker_identity["verified_clean_checker"] is not True:
        failures.append("checker_source_identity")
    return {
        "schema_version": (
            spec["identity_schema"]
        ),
        "status": (
            spec["identity_status"]
            if not failures
            else f"{spec['identity_status']}_failed"
        ),
        "pass": not failures,
        "candidate_id": candidate_id,
        "source_sha": source_sha,
        "live_head": live_head,
        "checker_identity": checker_identity,
        "input_records": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path),
                "mpi_size": int(payload["environment"]["mpi_size"]),
            }
            for path, payload in zip(paths, payloads, strict=True)
        ],
        "plan": {
            "path": spec["plan_relative"],
            "sha256": _sha256(ROOT / str(spec["plan_relative"])),
        },
        "stable_identity": stable[0] if stable else None,
        "record_failures": record_failures,
        "cross_checks": cross_checks,
        "failures": failures,
        "pde_launch_gate": not failures,
        "pde_launch_scope": spec["pde_launch_scope"],
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
        "--records",
        nargs=3,
        type=Path,
        required=True,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    spec = _candidate_spec(args.candidate)
    expected = tuple(
        (RECORD_DIR / spec["record_names"][size]).resolve()
        for size in (1, 2, 8)
    )
    paths = tuple(path.resolve() for path in args.records)
    if paths != expected:
        raise ValueError("formal inputs must be ordered MPI1/MPI2/MPI8 records")
    output = args.output.resolve()
    if output != (RECORD_DIR / str(spec["output_name"])).resolve():
        raise ValueError("formal MPI identity output path is fixed")
    if output.exists():
        raise FileExistsError("formal MPI identity record is immutable")
    result = check_records(paths, candidate_id=args.candidate)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
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
