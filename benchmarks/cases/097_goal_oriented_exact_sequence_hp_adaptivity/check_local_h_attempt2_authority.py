#!/usr/bin/env python3
"""Independent fail-closed checker for Task035d Attempt2 authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
SCHEMA = "case097.local-h-attempt2-authority.v1"
EXPECTED_NAMES = {
    1: "local_h_attempt2_mpi1_v1.json",
    2: "local_h_attempt2_mpi2_v1.json",
    8: "local_h_attempt2_mpi8_v1.json",
}
FIXTURE_CONFIG = {
    "root_cells": [3, 3, 1],
    "refined_root": [0, 0, 0, 0, 0],
    "periodic_axes": ["x", "y"],
    "trace_degree": 5,
    "cell_interior_degree": 6,
    "phase_x": [float(np.cos(0.2)), float(np.sin(0.2))],
    "phase_y": [float(np.cos(-0.3)), float(np.sin(-0.3))],
    "form": "curlcurl + (2.5+0.17j) mass",
}
NUMERICAL_RELATIVE_FILES = (
    "src/adaptivity/dyadic_hexa_refinement.py",
    "src/adaptivity/dyadic_hexa_broken_mesh.py",
    "src/adaptivity/hcurl_hanging_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_trace_constraint_graph.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/constraints/high_order_floquet_trace.py",
    "src/solvers/hcurl_assembly_time_condensation.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "generate_local_h_attempt2_authority.py"
    ),
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "check_local_h_attempt2_authority.py"
    ),
)
PRIOR_AUTHORITY_SHA256 = {
    "phase_a_compact": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/compact_authority_v1.json",
        "2e896ef45bbfc5c11901503269d11c0321106c9e41f71729ac7c6fc722687403",
    ),
    "phase_a_reference_active_space": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/reference_active_space_authority_v1.json",
        "4c1c5e68540dca4ddcc4165b0cc175abb4671ad254a44c1aa3518e4c9398ea9b",
    ),
    "local_h_attempt1_mpi_identity": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/local_h_attempt1_mpi_identity_v1.json",
        "d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44",
    ),
}
EXPECTED_P5_RESTRICTION_SHA256 = (
    "90bd8eb7c612f044c0026ce0551c2f96d8241adc9b63b8e402652b5b738ccf2a"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _strict_load(path: Path) -> Mapping[str, Any]:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject,
    )
    if not isinstance(payload, dict):
        raise TypeError("record root must be an object")
    return payload


def _all_finite(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_finite(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _solver_blob_manifest(source_sha: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("solver source SHA is invalid")
    result = {}
    for relative in NUMERICAL_RELATIVE_FILES:
        content = subprocess.check_output(
            ("git", "show", f"{source_sha}:{relative}"),
            cwd=ROOT,
        )
        result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _prior_authority_manifest() -> dict[str, Any]:
    records = {}
    for name, (relative, expected_sha) in PRIOR_AUTHORITY_SHA256.items():
        path = ROOT / relative
        payload = _strict_load(path)
        if _sha256(path) != expected_sha or payload.get("pass") is not True:
            raise RuntimeError(f"prior authority drifted or failed: {name}")
        records[name] = {
            "path": relative,
            "sha256": expected_sha,
            "status": payload.get("status"),
            "pass": True,
        }
        if name == "local_h_attempt1_mpi_identity":
            restriction = payload["stable_identity"][
                "canonical_hcurl_restriction_sha256"
            ]["5"]
            if restriction != EXPECTED_P5_RESTRICTION_SHA256:
                raise RuntimeError("Attempt1 p5 restriction hash drifted")
            records[name]["p5_hanging_restriction_sha256"] = restriction
    return {
        "records": records,
        "phase_a_exact_sequence_hash_bound": True,
        "attempt1_orientation_restriction_hash_bound": True,
        "p5_hanging_restriction_sha256": (
            EXPECTED_P5_RESTRICTION_SHA256
        ),
    }


def _validate_record(
    path: Path,
    payload: Mapping[str, Any],
    *,
    prior_manifest: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    try:
        mpi_size = int(payload["mpi_size"])
        source_sha = str(payload["source_sha"])
        if path.resolve().parent != RECORD_DIR.resolve():
            failures.append("record_directory")
        if path.name != EXPECTED_NAMES.get(mpi_size):
            failures.append("record_filename")
        if payload["schema_version"] != SCHEMA:
            failures.append("schema")
        if not _all_finite(payload):
            failures.append("nonfinite")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            failures.append("source_sha")
        source = payload["source_identity"]
        if not (
            source["head"] == source_sha
            and source["verified_clean_numerical_source"] is True
            and source["disallowed_status_lines"] == []
        ):
            failures.append("generation_source_identity")
        if not (
            payload["fixture_config"] == FIXTURE_CONFIG
            and payload["fixture_config_sha256"]
            == _json_sha256(FIXTURE_CONFIG)
        ):
            failures.append("fixture_config")
        if payload["prior_authorities"] != prior_manifest:
            failures.append("prior_authorities")
        environment = payload["environment"]
        rank_env = environment["rank_environments"]
        comparable = [
            {key: value for key, value in row.items() if key != "rank"}
            for row in rank_env
        ]
        if not (
            environment["qualified_activation"] == "1"
            and environment["petsc_scalar_type"] == "complex128"
            and environment["petsc_int_type"] == "int32"
            and environment["rank_ids"] == list(range(mpi_size))
            and environment["all_ranks_identical"] is True
            and len(rank_env) == mpi_size
            and [row["rank"] for row in rank_env] == list(range(mpi_size))
            and all(row == comparable[0] for row in comparable[1:])
        ):
            failures.append("rank_abi")

        fixture = payload["p5_trace_p6_interior_hanging_floquet"]
        forest = fixture["forest_audit"]
        carrier = fixture["carrier_audit"]
        entity_map = fixture["entity_map_audit"]
        physical = fixture["physical_trace_audit"]
        trace = fixture["cell_trace_binding_audit"]
        assembly = fixture["assembly_audit"]
        diagnostic = fixture["raw_oracle_assembly_audit"]
        observables = fixture["observables"]
        if not (
            fixture["trace_degree"] == 5
            and fixture["cell_interior_degree"] == 6
            and forest["pass"] is True
            and carrier["pass"] is True
            and entity_map["pass"] is True
            and physical["pass"] is True
            and trace["pass"] is True
            and assembly["pass"] is True
        ):
            failures.append("component_authorities")
        if not (
            physical["periodic_axes"] == ["x", "y"]
            and physical["maximum_relation_residual"] <= 5.0e-11
            and physical["periodic_cycle_error"] <= 5.0e-11
            and physical["mpi_physical_catalog_identity_qualified"] is True
            and physical["mpi_constraint_row_ownership_qualified"] is False
            and physical["mpi_ghost_expansion_qualified"] is False
        ):
            failures.append("physical_graph")
        if not (
            trace["constraint_kinds"] == ["hanging", "floquet"]
            and trace["raw_trace_rows"]
            - trace["independent_trace_rows"]
            == trace["eliminated_hanging_or_floquet_rows"]
            and trace["maximum_entity_transform_orthogonality_error"]
            <= 5.0e-11
            and trace["maximum_cell_transform_error"] <= 5.0e-11
            and trace["maximum_unpermuted_cell_chart_error"] <= 5.0e-11
            and trace["maximum_trace_interior_mixing_error"] <= 5.0e-11
            and trace["maximum_cell_expansion_condition"] > 1.0e8
            and trace["cell_expansion_inverse_used"] is False
            and trace["distributed_scalability_qualified"] is False
        ):
            failures.append("cell_trace_binding")
        if not (
            assembly["trace_constraint_kinds"] == ["floquet", "hanging"]
            and assembly["matrix_rows"] == trace["independent_trace_rows"]
            and assembly["hanging_or_floquet_slave_rows"]
            == trace["eliminated_hanging_or_floquet_rows"]
            and assembly["matrix_nnz"]
            == assembly["matrix_nnz_preallocated"]
            == assembly["matrix_nnz_allocated"]
            and assembly["matrix_mallocs"] == 0
            and diagnostic["matrix_nnz"]
            == diagnostic["matrix_nnz_preallocated"]
            == diagnostic["matrix_nnz_allocated"]
            and diagnostic["matrix_mallocs"] == 0
            and assembly["compiled_p6_tensor_builder"] is True
            and assembly[
                "compiled_trace_constraint_binding_complete"
            ]
            is True
            and assembly["full_p6_global_matrix_constructed"] is False
            and assembly["full_active_global_matrix_constructed"] is False
            and assembly[
                "hanging_or_floquet_slave_rows_globally_numbered"
            ]
            is False
        ):
            failures.append("matrix_structure")
        residual_fields = (
            assembly["interior_recovery_operator_residual_max"],
            assembly["interior_adjoint_operator_residual_max"],
            observables["full_trace_recovery_max_abs_error"],
            observables[
                "full_active_rhs_recovery_mapping_max_abs_error"
            ],
            observables[
                "zero_rhs_recovered_interior_equation_relative_residual"
            ],
            observables[
                "nonzero_rhs_recovered_interior_equation_relative_residual"
            ],
        )
        if any(float(value) > 5.0e-11 for value in residual_fields):
            failures.append("recovery_residual")
        congruence = observables["implementation_congruence_errors"]
        if any(
            float(congruence[name]) > 5.0e-10
            for name in (
                "action_root_max_relative",
                "action_probe_max_relative",
                "bilinear_relative",
                "right_rhs_max_relative",
                "left_rhs_max_relative",
                "zero_rhs_recovery_max_relative",
                "nonzero_rhs_recovery_max_relative",
            )
        ):
            failures.append("implementation_congruence")
        gram = observables["component_gram"]
        if not (
            gram["rows"] == trace["independent_trace_rows"]
            and gram["hermitian_max_abs_error"] <= 5.0e-11
            and gram["dual_solve_relative_residual"] <= 5.0e-9
            and gram["primal_norm_relative_error"] <= 5.0e-11
            and gram["dual_norm_relative_error"] <= 5.0e-9
        ):
            failures.append("component_gram")
        ranges = [
            tuple(map(int, row)) for row in fixture["petsc_ownership_ranges"]
        ]
        rows = int(trace["independent_trace_rows"])
        if not (
            len(ranges) == mpi_size
            and ranges[0][0] == 0
            and ranges[-1][1] == rows
            and all(0 <= start <= stop <= rows for start, stop in ranges)
            and sum(stop - start for start, stop in ranges) == rows
            and all(
                left[1] == right[0]
                for left, right in zip(
                    ranges[:-1], ranges[1:], strict=True
                )
            )
        ):
            failures.append("petsc_ownership_ranges")
        if not (
            payload["pass"] is True
            and payload["failures"] == []
            and fixture["pass"] is True
            and fixture["failures"] == []
            and payload["status"]
            == "local_h_attempt2_cell_tensor_component_pass_pde_blocked"
            and payload["distributed_scalability_qualified"] is False
            and payload["pde_launch_gate"] is False
            and payload["heavy_pde_started"] is False
            and payload["pde_accuracy_credit"] is False
            and payload["ordinary_default_changed"] is False
        ):
            failures.append("declared_scope")
        ledger = payload["component_resource_ledger"]
        if not (
            ledger["raw_oracle_and_candidate_co_resident"] is True
            and ledger[
                "process_peak_is_not_candidate_memory_authority"
            ]
            is True
            and ledger["factorization_or_pde_solve_memory_measured"]
            is False
            and ledger["timings_are_per_stage_mpi_max_not_rank_sum"]
            is True
        ):
            failures.append("resource_semantics")
    except (KeyError, TypeError, ValueError, IndexError):
        failures.append("required_field_or_type")
    return sorted(set(failures))


def _signature_matches(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    try:
        if (
            int(left["size"]) != int(right["size"])
            or left["sample_indices"] != right["sample_indices"]
        ):
            return False
        for name in ("linf", "l2"):
            if not np.isclose(
                float(left[name]),
                float(right[name]),
                rtol=3.0e-10,
                atol=3.0e-11,
            ):
                return False
        for name in ("sum", "weighted_sum", "normalized_samples"):
            if not np.allclose(
                np.asarray(left[name], dtype=np.float64),
                np.asarray(right[name], dtype=np.float64),
                rtol=3.0e-10,
                atol=3.0e-9,
            ):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def check_records(records: tuple[Path, ...]) -> dict[str, Any]:
    failures: list[str] = []
    payloads: list[Mapping[str, Any] | None] = []
    load_failures: dict[str, list[str]] = {}
    try:
        prior = _prior_authority_manifest()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        prior = {}
        failures.append(f"prior_authority_probe:{type(exc).__name__}")
    for path in records:
        try:
            payload = _strict_load(path)
            record_failures = _validate_record(
                path,
                payload,
                prior_manifest=prior,
            )
        except (OSError, ValueError, TypeError) as exc:
            payload = None
            record_failures = [f"load:{type(exc).__name__}"]
        payloads.append(payload)
        load_failures[path.name] = record_failures
        failures.extend(f"{path.name}:{item}" for item in record_failures)

    valid_payloads = [payload for payload in payloads if payload is not None]
    source_sha = None
    solver_blobs: dict[str, str] = {}
    cross_checks: dict[str, bool] = {}
    digest_diagnostics: dict[str, bool] = {}
    if len(records) != 3:
        failures.append("record_count")
    if len(valid_payloads) == 3 and not failures:
        mpi_sizes = {int(payload["mpi_size"]) for payload in valid_payloads}
        sources = {str(payload["source_sha"]) for payload in valid_payloads}
        source_sha = next(iter(sources)) if len(sources) == 1 else None
        try:
            solver_blobs = (
                _solver_blob_manifest(source_sha)
                if source_sha is not None
                else {}
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            solver_blobs = {}
        abi = [
            {
                key: payload["environment"]["rank_environments"][0][key]
                for key in (
                    "qualified_activation",
                    "python_executable",
                    "dolfinx",
                    "basix",
                    "petsc4py",
                    "mpi4py",
                    "petsc_scalar_type",
                    "petsc_int_type",
                    "mpi_vendor",
                    "mpi_library_version",
                )
            }
            for payload in valid_payloads
        ]
        fixture_name = "p5_trace_p6_interior_hanging_floquet"
        observable_names = (
            "matrix_action_root",
            "matrix_action_probe",
            "right_reduced_rhs",
            "left_reduced_rhs",
            "zero_rhs_full_recovery",
            "nonzero_rhs_full_recovery",
        )
        cross_checks = {
            "mpi_sizes_are_1_2_8": mpi_sizes == {1, 2, 8},
            "same_solver_source_sha": len(sources) == 1,
            "same_solver_blob_manifest": all(
                payload["numerical_files"]
                == valid_payloads[0]["numerical_files"]
                == solver_blobs
                for payload in valid_payloads
            ),
            "same_fixture_identity": all(
                payload[fixture_name]["stable_identity"]
                == valid_payloads[0][fixture_name]["stable_identity"]
                for payload in valid_payloads[1:]
            ),
            "same_abi": all(row == abi[0] for row in abi[1:]),
        }
        for observable_name in observable_names:
            reference = valid_payloads[0][fixture_name]["observables"][
                observable_name
            ]
            cross_checks[f"{observable_name}_mpi_identity"] = all(
                _signature_matches(
                    reference,
                    payload[fixture_name]["observables"][observable_name],
                )
                for payload in valid_payloads[1:]
            )
            digest_diagnostics[f"{observable_name}_digest_equal"] = all(
                payload[fixture_name]["observables"][observable_name][
                    "normalized_quantized_1e10_sha256"
                ]
                == reference["normalized_quantized_1e10_sha256"]
                for payload in valid_payloads[1:]
            )
        failures.extend(
            f"cross:{name}"
            for name, passed in cross_checks.items()
            if not passed
        )
    elif not failures:
        failures.append("valid_record_count")

    return {
        "schema_version": "case097.local-h-attempt2-independent-check.v1",
        "status": (
            "local_h_attempt2_component_pass_pde_blocked"
            if not failures
            else "local_h_attempt2_evidence_fail"
        ),
        "pass": not failures,
        "source_sha": source_sha,
        "input_records": [
            {"path": f"records/{path.name}", "sha256": _sha256(path)}
            for path in records
            if path.exists()
        ],
        "record_failures": load_failures,
        "cross_checks": cross_checks,
        "non_gating_digest_diagnostics": digest_diagnostics,
        "solver_commit_numerical_files": solver_blobs,
        "failures": failures,
        "component_only": True,
        "pde_launch_gate": False,
        "pde_accuracy_credit": False,
        "distributed_scalability_qualified": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--records",
        type=Path,
        nargs=3,
        required=True,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = check_records(tuple(args.records))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            result,
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
                "output": str(args.output),
                "sha256": _sha256(args.output),
                "status": result["status"],
                "pass": result["pass"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
