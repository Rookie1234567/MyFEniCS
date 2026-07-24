"""Fail-closed Task035b audit for a physical selective-p6-trace lane.

The Review V1 trace lane requires more than a reference-cell complement or a
recovered-adjoint coefficient proxy.  A formal candidate needs physical
Piola/Riesz pullbacks, Floquet-orbit-closed selection, an enriched residual,
residual-weighted DWR, exact-sequence closure, and physically reduced global
numbering.  This command recomputes the available local algebra, binds all
relevant records by SHA256, and stops before a PDE when those capabilities do
not close.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.adaptivity.inverse_trace_interior_budget_audit import (
    audit_inverse_trace_interior_budget_exchange,
)
from src.adaptivity.missing_p6_trace_sensitivity import (
    build_missing_p6_trace_complement,
    build_missing_p6_trace_riesz_metric,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = RECORDS / "physical_trace_lane_capability_gate.json"
FULL3D_EQUIVALENT_DOF_LIMIT = 90_000
SOURCE_FILES = (
    "benchmarks/task035b_physical_trace_lane_capability_gate.py",
    "src/adaptivity/hcurl_regionwise_p.py",
    "src/adaptivity/inverse_trace_interior_budget_audit.py",
    "src/adaptivity/missing_p6_trace_sensitivity.py",
)
AUTHORITY_SPECS: dict[str, tuple[Path, str, str]] = {
    "missing_complement": (
        RECORDS / "missing_p6_trace_complement_preflight_v2.json",
        "899b320ed6659f745cb1ed8532cb6752cdfca338c703f1608cd4233473370a32",
        "task035b.missing-p6-trace-complement-preflight.v2",
    ),
    "inverse_budget": (
        RECORDS
        / "inverse_trace_interior_budget_exchange_preflight.json",
        "d010d69d26429993c1f07725a4b63653cf6d79d1155ea4eef76d0077c3b189f9",
        "task035b.inverse-trace-interior-budget-exchange-audit.v1",
    ),
    "global_p6_h14_discriminator": (
        RECORDS / "global_p6_h14_trace_discriminator.json",
        "a16bb533222a73cbe5dede8b3abe93d2e047ef168a6ebc74e85790433f767cad",
        "task035b.global-p6-h14-trace-discriminator.v1",
    ),
    "fixed_h14": (
        RECORDS / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json",
        "e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127",
        "task035b.fixed-trace-watchdog.v1",
    ),
    "fixed_h13": (
        RECORDS / "fixed_p5trace_p6interior_h13_directional_z_mpi8.json",
        "81ba43d91c4c9a35121676ae40368d56116f3a381e4559d630fb547a94dc4a5c",
        "task035b.fixed-trace-watchdog.v1",
    ),
    "h15_channel_adjoint_proxy": (
        RECORDS
        / (
            "fixed_p5trace_p6interior_h15_channel_adjoints_"
            "verification_v2_mpi8.json"
        ),
        "56023fcbf5a85d8d5d2db062283cae8b66771c1543d025731a0c9eefa4a8d0e5",
        "task035b.fixed-trace-watchdog.v1",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _is_full_sha(value: Any, *, length: int) -> bool:
    normalized = str(value).lower()
    return len(normalized) == length and all(
        character in "0123456789abcdef" for character in normalized
    )


def _source_file_hashes(repo_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = repo_root / relative
        if not path.is_file():
            raise RuntimeError(f"required source file is missing: {relative}")
        hashes[relative] = _sha256(path)
    return hashes


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _is_full_sha(verified, length=40),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "physical trace capability source gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": status,
        "source_files_sha256_before": _source_file_hashes(repo_root),
        "checks": checks,
    }


def _close_source_identity(
    repo_root: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    hashes_after = _source_file_hashes(repo_root)
    checks = {
        "head_stable_after_build": head == source["commit_sha"],
        "branch_stable_after_build": branch == source["branch"],
        "worktree_still_clean_before_exclusive_write": status == "",
        "source_files_stable_after_build": (
            hashes_after == source["source_files_sha256_before"]
        ),
    }
    if not all(checks.values()):
        raise SystemExit(
            "physical trace capability source closure failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        **dict(source),
        "head_after_build": head,
        "status_after_build_before_write": status,
        "source_files_sha256_after": hashes_after,
        "stable_and_clean_after_build": True,
        "closure_checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": (
            np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
        ),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_postprocess_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "physical trace capability ABI gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
    }


def _load_authorities(
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for label, (relative, expected_sha, expected_schema) in (
        AUTHORITY_SPECS.items()
    ):
        path = (repo_root / relative).resolve()
        if not path.is_file():
            raise ValueError(f"{label} authority is unreadable: {path}")
        payload = path.read_bytes()
        actual_sha = hashlib.sha256(payload).hexdigest()
        record = json.loads(payload)
        actual_schema = record.get("schema_version")
        checks = {
            "sha256_match": actual_sha == expected_sha,
            "schema_match": actual_schema == expected_schema,
        }
        if not all(checks.values()):
            raise ValueError(
                f"{label} authority mismatch: "
                + ", ".join(
                    name for name, passed in checks.items() if not passed
                )
            )
        records[label] = record
        evidence[label] = {
            "path": str(relative),
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "sha256_match": True,
            "expected_schema_version": expected_schema,
            "actual_schema_version": actual_schema,
            "schema_match": True,
            "source_commit_sha": (
                (record.get("source") or {}).get("commit_sha")
            ),
        }
    return records, evidence


def _structured_entity_counts(axis_cells: tuple[int, int, int]) -> dict[str, int]:
    nx, ny, nz = axis_cells
    return {
        "vertices": (nx + 1) * (ny + 1) * (nz + 1),
        "edges": (
            nx * (ny + 1) * (nz + 1)
            + (nx + 1) * ny * (nz + 1)
            + (nx + 1) * (ny + 1) * nz
        ),
        "faces": (
            (nx + 1) * ny * nz
            + nx * (ny + 1) * nz
            + nx * ny * (nz + 1)
        ),
        "cells": nx * ny * nz,
    }


def _mesh_budget(record: Mapping[str, Any]) -> dict[str, Any]:
    candidate = record["candidate"]
    audit = candidate["high_order_resource_audit"]
    mesh = audit["mesh_identity"]
    inventory = audit["entity_dof_inventory"]
    axis_cells = tuple(int(value) for value in mesh["mesh_cells_resolved"])
    counts = _structured_entity_counts(axis_cells)
    recorded_counts = {
        key: int(value)
        for key, value in inventory["global_entity_counts"].items()
    }
    if counts != recorded_counts:
        raise ValueError(
            f"structured entity counts do not close: {counts} != "
            f"{recorded_counts}"
        )
    fixed_dofs = int(candidate["num_nedelec_dofs"])
    global_p6_dofs = int(record["dof_target"]["same_mesh_global_p6_dofs"])
    edge_increment = counts["edges"]
    face_increment = 20 * counts["faces"]
    full_trace_increment = edge_increment + face_increment
    if fixed_dofs + full_trace_increment != global_p6_dofs:
        raise ValueError("fixed-to-global p6 trace DoF increment does not close")
    return {
        "axis_cells": list(axis_cells),
        "fixed_dofs": fixed_dofs,
        "global_edges": counts["edges"],
        "global_faces": counts["faces"],
        "edge_shell_increment": edge_increment,
        "face_shell_increment": face_increment,
        "full_trace_increment": full_trace_increment,
        "recomputed_global_p6_dofs": global_p6_dofs,
        "available_headroom": FULL3D_EQUIVALENT_DOF_LIMIT - fixed_dofs,
        "full_trace_over_limit_by": max(
            0, global_p6_dofs - FULL3D_EQUIVALENT_DOF_LIMIT
        ),
        "full_trace_fits": global_p6_dofs
        <= FULL3D_EQUIVALENT_DOF_LIMIT,
    }


def _recompute_local_algebra() -> dict[str, Any]:
    complement = build_missing_p6_trace_complement()
    riesz = build_missing_p6_trace_riesz_metric(complement)
    complement_rank = int(
        np.linalg.matrix_rank(complement.missing_to_enriched)
    )
    riesz_rank = int(np.linalg.matrix_rank(riesz.block_diagonal_gram))
    return {
        "retained_local_dimension": complement.retained_dimension,
        "enriched_local_dimension": complement.enriched_dimension,
        "retained_local_trace_dimension": int(
            complement.audit["retained_local_trace_dimension"]
        ),
        "enriched_local_trace_dimension": int(
            complement.audit["enriched_local_trace_dimension"]
        ),
        "missing_local_trace_dimension": complement.missing_dimension,
        "edge_block_count": sum(
            block.entity_dimension == 1 for block in complement.entity_blocks
        ),
        "edge_block_dimension": int(
            complement.audit["missing_edge_modes_per_entity"][0]
        ),
        "face_block_count": sum(
            block.entity_dimension == 2 for block in complement.entity_blocks
        ),
        "face_block_dimension": int(
            complement.audit["missing_face_modes_per_entity"][0]
        ),
        "recomputed_complement_rank": complement_rank,
        "recomputed_complement_nullity": (
            complement.missing_dimension - complement_rank
        ),
        "recomputed_reference_riesz_rank": riesz_rank,
        "recomputed_reference_riesz_nullity": (
            riesz.missing_dimension - riesz_rank
        ),
        "rank_nullity_closure_pass": (
            complement_rank == complement.missing_dimension
            and riesz_rank == riesz.missing_dimension
        ),
        "reference_entity_riesz_pass": riesz.audit["pass"] is True,
        "physical_mesh_riesz": False,
    }


def _inverse_budget_audit() -> dict[str, Any]:
    audit = audit_inverse_trace_interior_budget_exchange()
    output: dict[str, Any] = {}
    for output_name, source_name in (
        ("p6_trace_p5_interior", "p6_trace_p5_cell_interior"),
        ("p6_trace_p4_interior", "p6_trace_p4_cell_interior"),
    ):
        pair = audit["inverse_budget_exchange_pairs"][source_name]
        exact = pair["exact_sequence"]
        output[output_name] = {
            "dimension": int(pair["mixed_vector_space_dimension"]),
            "curl_rank": int(exact["measured_curl_rank"]),
            "curl_nullity": int(exact["measured_curl_nullity"]),
            "expected_gradient_dimension": int(
                exact["expected_nonconstant_gradient_dimension"]
            ),
            "missing_gradient_modes": int(
                exact["missing_gradient_mode_count"]
            ),
            "rank_plus_nullity_closes": (
                int(exact["measured_curl_rank"])
                + int(exact["measured_curl_nullity"])
                == int(pair["mixed_vector_space_dimension"])
            ),
            "exact_sequence_pass": bool(pair["exact_sequence_pass"]),
            "pde_authorized": False,
        }
    return output


def _adjoint_proxy_audit(record: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = record["channel_adjoint_diagnostic"]
    adjoints = diagnostic["adjoints"]
    recovered = diagnostic["recovered_full_duals"]
    proxies = [
        item["entity_sensitivity_proxy"] for item in recovered.values()
    ]
    return {
        "goal_count": int(adjoints["goal_count"]),
        "actual_hermitian_adjoint_solves_available": (
            adjoints["pass"] is True
            and all(
                goal["pass"] is True
                and goal["actual_discrete_system"] is True
                for goal in adjoints["goals"].values()
            )
        ),
        "exact_full_dual_recovery_available": (
            len(recovered) == int(adjoints["goal_count"])
            and all(
                item["exact_augmented_dual_recovery"] is True
                for item in recovered.values()
            )
        ),
        "coefficient_proxy_periodic_components_available": all(
            "periodic_transitive_aggregation" in proxy for proxy in proxies
        ),
        "actual_enriched_residual_available": any(
            proxy["actual_enriched_residual_available"] is True
            for proxy in proxies
        ),
        "residual_weighted": any(
            proxy["residual_weighted"] is True for proxy in proxies
        ),
        "actual_dwr_indicator": any(
            proxy["actual_dwr_indicator"] is True for proxy in proxies
        ),
        "proxy_is_dwr": False,
        "lane_b_selection_authorized": False,
    }


def build_capability_gate(
    *,
    records: Mapping[str, Mapping[str, Any]],
    authority_evidence: Mapping[str, Mapping[str, Any]],
    source_identity: Mapping[str, Any],
    environment_identity: Mapping[str, Any],
    local_algebra: Mapping[str, Any] | None = None,
    inverse_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the controlled-stop record without writing it."""

    complement_record = records["missing_complement"]
    complement_semantics = complement_record["diagnostic_semantics"]
    inverse_record = records["inverse_budget"]
    global_record = records["global_p6_h14_discriminator"]
    global_gates = global_record["global_p6_h14_gates"]
    channels = global_gates[
        "significant_12_power_and_complex_amplitude"
    ]
    adjoint_audit = _adjoint_proxy_audit(
        records["h15_channel_adjoint_proxy"]
    )
    local = dict(
        _recompute_local_algebra()
        if local_algebra is None
        else local_algebra
    )
    inverse = dict(
        _inverse_budget_audit() if inverse_audit is None else inverse_audit
    )
    mesh_budgets = {
        "full3d_equivalent_dof_limit": FULL3D_EQUIVALENT_DOF_LIMIT,
        "h14": _mesh_budget(records["fixed_h14"]),
        "h13": _mesh_budget(records["fixed_h13"]),
    }
    complement_authority = complement_record["complement_audit"]
    inventory_authority = complement_record["missing_trace_mode_inventory"]
    local_authority_match = (
        local["retained_local_dimension"]
        == int(complement_authority["retained_local_dimension"])
        == 750
        and local["enriched_local_dimension"]
        == int(complement_authority["enriched_local_dimension"])
        == 882
        and local["retained_local_trace_dimension"]
        == int(complement_authority["retained_local_trace_dimension"])
        == 300
        and local["enriched_local_trace_dimension"]
        == int(complement_authority["enriched_local_trace_dimension"])
        == 432
        and local["missing_local_trace_dimension"]
        == int(complement_authority["missing_local_trace_dimension"])
        == int(inventory_authority["reference_cell_missing_trace_modes"])
        == 132
        and local["edge_block_count"]
        == int(inventory_authority["edge_count"])
        == 12
        and local["edge_block_dimension"]
        == len(set(inventory_authority["missing_modes_per_edge"]))
        == 1
        and set(inventory_authority["missing_modes_per_edge"]) == {1}
        and local["face_block_count"]
        == int(inventory_authority["face_count"])
        == 6
        and local["face_block_dimension"] == 20
        and set(inventory_authority["missing_modes_per_face"]) == {20}
        and local["recomputed_complement_rank"] == 132
        and local["recomputed_complement_nullity"] == 0
        and local["recomputed_reference_riesz_rank"] == 132
        and local["recomputed_reference_riesz_nullity"] == 0
    )
    inverse_authority_match = True
    for output_name, source_name in (
        ("p6_trace_p5_interior", "p6_trace_p5_cell_interior"),
        ("p6_trace_p4_interior", "p6_trace_p4_cell_interior"),
    ):
        recomputed = inverse[output_name]
        recorded_pair = inverse_record["inverse_budget_exchange_pairs"][
            source_name
        ]
        recorded_exact = recorded_pair["exact_sequence"]
        inverse_authority_match = inverse_authority_match and (
            recomputed["dimension"]
            == int(recorded_pair["mixed_vector_space_dimension"])
            and recomputed["curl_rank"]
            == int(recorded_exact["measured_curl_rank"])
            and recomputed["curl_nullity"]
            == int(recorded_exact["measured_curl_nullity"])
            and recomputed["expected_gradient_dimension"]
            == int(recorded_exact["expected_nonconstant_gradient_dimension"])
            and recomputed["missing_gradient_modes"]
            == int(recorded_exact["missing_gradient_mode_count"])
            and recomputed["exact_sequence_pass"] is False
            and recorded_pair["exact_sequence_pass"] is False
        )
    prerequisites = {
        "reference_entity_complement_available": (
            complement_record["complement_audit"]["pass"] is True
        ),
        "reference_entity_riesz_available": (
            complement_semantics["reference_entity_trace_riesz_available"]
            is True
        ),
        "actual_hermitian_channel_adjoints_available": adjoint_audit[
            "actual_hermitian_adjoint_solves_available"
        ],
        "physical_piola_riesz_available": False,
        "missing_p6_trace_closed_floquet_orbits_available": False,
        "missing_mode_orientation_phase_pullbacks_available": False,
        "actual_global_missing_trace_residual_available": False,
        "complement_schur_inverse_available": False,
        "true_active_global_numbering_available": False,
        "actual_residual_weighted_dwr_available": False,
        "selected_subset_exact_sequence_proved": False,
        "selected_candidate_physically_reduced_rows_proved": False,
        "all_required_capabilities_available": False,
    }
    exact_authority_set = set(authority_evidence) == set(AUTHORITY_SPECS)
    checks = {
        "all_authorities_sha_bound": (
            exact_authority_set
            and all(
                evidence["sha256_match"] is True
                for evidence in authority_evidence.values()
            )
        ),
        "all_schemas_match": (
            exact_authority_set
            and all(
                evidence["schema_match"] is True
                for evidence in authority_evidence.values()
            )
        ),
        "budgets_recomputed_from_entity_counts": (
            mesh_budgets["h14"]["full_trace_increment"] == 10_535
            and mesh_budgets["h13"]["full_trace_increment"] == 11_468
        ),
        "local_rank_nullity_recomputed": (
            local["rank_nullity_closure_pass"] is True
        ),
        "local_algebra_matches_sha_bound_authority": local_authority_match,
        "inverse_algebra_matches_sha_bound_authority": (
            inverse_authority_match
        ),
        "inverse_budget_record_is_controlled_negative": (
            inverse_record["controlled_negative"] is True
            and inverse_record["candidate_count"] == 0
        ),
        "proxy_not_mislabeled_as_dwr": (
            adjoint_audit["actual_dwr_indicator"] is False
            and adjoint_audit["proxy_is_dwr"] is False
        ),
        "no_subset_selected": True,
        "pde_denied_when_capabilities_missing": (
            prerequisites["all_required_capabilities_available"] is False
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(
            "physical trace capability gate did not close: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "schema_version": (
            "task035b.physical-trace-lane-capability-gate.v1"
        ),
        "benchmark_id": "task035b_physical_trace_lane_capability_gate",
        "status": "capability_stop_not_run",
        "pass": True,
        "audit_completed": True,
        "classification": (
            "controlled_stop_missing_physical_trace_dwr_capabilities"
        ),
        "record_semantics": (
            "pass means the fail-closed capability audit completed; it does "
            "not authorize a trace subset, a PDE, or a candidate"
        ),
        "candidate_count": 0,
        "candidate_authorized": False,
        "pde_run_count": 0,
        "pde_authorized": False,
        "ordinary_default_changed": False,
        "source": dict(source_identity),
        "environment": dict(environment_identity),
        "authorities": {
            name: dict(evidence)
            for name, evidence in authority_evidence.items()
        },
        "execution_scope": {
            "pure_postprocess": True,
            "mesh_built": False,
            "form_compiled": False,
            "matrix_assembled": False,
            "solver_started": False,
            "pde_run": False,
            "subset_selected": False,
        },
        "local_missing_block_audit": local,
        "inverse_budget_exact_sequence_audit": inverse,
        "mesh_budget_audit": mesh_budgets,
        "global_h14_discriminator_audit": {
            "scalar_pass": global_gates["scalar"]["pass"] is True,
            "selected_field_interface_pass": (
                global_gates["selected_field_interface"]["pass"] is True
            ),
            "significant_power_pass_count": int(
                channels["significant_power_pass_count"]
            ),
            "significant_complex_amplitude_pass_count": int(
                channels["significant_complex_amplitude_pass_count"]
            ),
            "all_12_power_pass": (
                channels["all_12_significant_powers_pass"] is True
            ),
            "all_12_complex_amplitude_pass": (
                channels[
                    "all_12_significant_complex_amplitudes_pass"
                ]
                is True
            ),
            "formal_candidate_eligible": (
                global_record["formal_candidate_eligible"] is True
            ),
            "selective_trace_lane_physically_supported": (
                global_record["selective_trace_lane_physically_supported"]
                is True
            ),
        },
        "h15_adjoint_proxy_audit": adjoint_audit,
        "physical_prerequisites": prerequisites,
        "selection_contract": {
            "subset_selected": False,
            "coordinatewise_mode_ranking_authorized": False,
            "partial_face_mode_selection_authorized": False,
            "minimum_local_edge_block_dimension": 1,
            "minimum_local_face_selection_unit": (
                "whole_missing_p6_face_shell"
            ),
            "minimum_local_face_selection_unit_dofs": 20,
            "global_orbit_closed_selection_unit_dofs": None,
            "global_orbit_cost_status": (
                "unknown_without_true_numbering_and_missing-mode "
                "Floquet-orbit pullbacks"
            ),
            "exact_sequence_closure_required_for_any_entity_combination": True,
        },
        "decision": {
            "classification": "controlled_stop",
            "reason": (
                "reference-cell complement/Riesz and recovered-adjoint "
                "coefficient proxies do not supply physical Piola/Riesz, "
                "missing-mode Floquet-orbit pullbacks, a complement Schur "
                "solve, actual enriched residual-weighted DWR, or true "
                "active numbering"
            ),
            "subset_may_not_be_claimed": True,
            "next_pde_authorized": False,
            "lane_b_not_currently_executable": True,
            "selection_not_authorized": True,
        },
        "qualification": {
            "pass": True,
            "evidence_valid": True,
            "checks": checks,
        },
    }


def _resolve_output(path: Path) -> Path:
    output = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        output.relative_to((ROOT / RECORDS).resolve())
    except ValueError as error:
        raise ValueError(
            "physical trace capability evidence must remain in Case095 records"
        ) from error
    return output


def _write_json_exclusive(
    path: Path,
    record: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = _resolve_output(args.output)
    if output.exists():
        raise FileExistsError(f"exclusive output already exists: {output}")
    source = _verified_source_identity(ROOT, args.verified_clean_sha)
    environment = _environment_identity(ROOT)
    records, authorities = _load_authorities(ROOT)
    record = build_capability_gate(
        records=records,
        authority_evidence=authorities,
        source_identity=source,
        environment_identity=environment,
    )
    record["source"] = _close_source_identity(ROOT, source)
    _write_json_exclusive(output, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
