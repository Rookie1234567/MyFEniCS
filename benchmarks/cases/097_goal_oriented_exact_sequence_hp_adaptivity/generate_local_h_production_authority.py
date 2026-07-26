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
            1: "combined_hp_interior_mpi1_v1.json",
            2: "combined_hp_interior_mpi2_v1.json",
            8: "combined_hp_interior_mpi8_v1.json",
        },
        "schema_version": (
            "case097.combined-hp-interior-component.v1"
        ),
        "pass_status": "combined_hp_interior_component_pass",
        "marked_root_boxes": (
            (8.25, 0.0, 120.0, 16.5, 12.5, 130.0),
            (33.5, 0.0, 120.0, 41.75, 12.5, 130.0),
        ),
        "variable_interior": True,
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
    "src/geometry/mesh_builder_3d.py",
    "src/adaptivity/stage4_local_h.py",
    "src/adaptivity/dyadic_hexa_refinement.py",
    "src/adaptivity/dyadic_hexa_broken_mesh.py",
    "src/adaptivity/hcurl_hanging_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_trace_constraint_graph.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/adaptivity/variable_p_transfer.py",
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
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    head = _git_output("rev-parse", "HEAD")
    status = [
        line
        for line in _git_output(
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            *NUMERICAL_RELATIVE_FILES,
        ).splitlines()
        if line
    ]
    live = {
        relative: _sha256(ROOT / relative)
        for relative in NUMERICAL_RELATIVE_FILES
    }
    committed = {
        relative: _commit_blob_sha(expected_sha, relative)
        for relative in NUMERICAL_RELATIVE_FILES
    }
    local = {
        "rank": int(comm.rank),
        "head": head,
        "expected_sha": expected_sha,
        "status_lines": status,
        "mismatched_files": sorted(
            relative
            for relative in NUMERICAL_RELATIVE_FILES
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
    overrides = None
    provenance: dict[str, Any]
    if spec["variable_interior"]:
        forest = _build_forest(
            cfg,
            comm_size=8,
            marked_root_boxes=marked,
            maximum_level=1,
        )
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
        if len(overrides) != 32:
            raise RuntimeError(
                "combined h/p remote-air classifier must mark 32 cells"
            )
        provenance = {
            "purpose": (
                "Task035d first local-h plus true variable-interior "
                "candidate"
            ),
            "candidate_id": candidate_id,
            "h_action": (
                "one split in each top-air root immediately outside the "
                "left and right grating sidewalls, then y-periodic closure"
            ),
            "h_action_evidence": (
                "symmetric diagnostic response to the h15 one-sided "
                "local-h 6/12 power plus 6/12 amplitude controlled "
                "negative; heuristic channel-directed action, not actual "
                "DWR or adjoint credit"
            ),
            "p_action": (
                "p6-to-p5 cell-interior only in 32 unrefined homogeneous "
                "air leaves at the two far lateral columns, excluding "
                "grating, sidewall-adjacent, local-h, top-port, and "
                "bottom-port cells"
            ),
            "p_action_evidence": (
                "geometry smoothness and distance guard; no variable "
                "trace, DWR, or full combined-hp completion credit"
            ),
            "accuracy_credit": False,
            "complete_combined_hp_credit": False,
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
    entity_map = reduction.degree_plan.entity_map.audit
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
        "canonical_degree_map_sha256": entity_map[
            "canonical_degree_map_sha256"
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
    source = _live_source_identity(comm, expected_sha=source_sha)
    environment = _environment(comm)
    prior = _prior_authorities()
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
    checks = {
        "plan_is_tracked": tracked,
        "mesh_authority": context.audit["pass"] is True,
        "reduction_authority": reduction.audit["pass"] is True,
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
                == {"p4": 0, "p5": 32, "p6": 116}
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
            "payload": json.loads(plan_path.read_text(encoding="utf-8")),
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
    if output.exists():
        raise FileExistsError(f"authority output is immutable: {output}")
    if comm.rank == 0:
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
    if comm.rank == 0:
        print(json.dumps(envelope, sort_keys=True))
    return 0 if payload.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
