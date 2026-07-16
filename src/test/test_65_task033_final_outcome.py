from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, ValidationError

from benchmarks.run_task033_final_outcome import main as cli_main
from benchmarks.task033_evidence_checker import (
    FINAL_OUTCOME_INPUT_ROLE_MAP,
    final_outcome_manifest_closure_problems,
)
from benchmarks.task033_qep_qualification import (
    qep_p4_controlled_negative_gate,
    qep_shard_gate,
    source_identity_gate,
)
from benchmarks.task033_final_outcome import (
    FinalOutcomeError,
    SCHEMA_PATH,
    build_final_outcome,
)
from src.test.test_62_task033_formal_records import (
    _controlled_p4_negative,
    _qep_shard,
)


SOURCE_SHA = "a" * 40


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _payload_sha(payload: dict, field: str) -> str:
    stripped = dict(payload)
    stripped.pop(field, None)
    rendered = json.dumps(
        stripped,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(rendered).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _formal_source(sha: str = SOURCE_SHA) -> dict:
    return {"commit_sha": sha, "tracked_source_clean": True}


def _source_gate(sha: str = SOURCE_SHA) -> dict:
    return {
        "pass": True,
        "checks": {
            "head_before_full_sha": True,
            "head_after_full_sha": True,
            "attested_full_sha": True,
            "all_shas_identical": True,
            "tracked_clean_before": True,
            "tracked_clean_after": True,
            "source_stable_during_run": True,
            "source_clean_verified": True,
        },
        "failures": [],
        "head_sha": sha,
    }


class Task033FinalOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = self._records()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, name: str, payload: dict) -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return path

    def _records(self) -> dict[str, Path | str]:
        core = {
            "schema_version": "task033.case090.core-gates.v1",
            "record_type": "high_order_floquet_core_gate_result",
            "case_id": "090_high_order_3d_floquet_hcurl",
            "identity": {
                "is_pde_run": True,
                "is_solver_pass": True,
                "tracked_source_dirty": False,
                "source_commit_full_sha": SOURCE_SHA,
            },
            "all_core_gates_passed": True,
            "coverage": [
                {
                    "degree": degree,
                    "mpi_size": mpi,
                    "core_algebra_gates_passed": True,
                }
                for degree in (1, 2, 3, 4)
                for mpi in (1, 2, 4)
            ],
            "external_memory_watchdog": {"all_three_qualified": True},
            "failures": [],
        }
        core["evidence_sha256"] = _payload_sha(core, "evidence_sha256")

        qep = self._materialize_qep_sources(self._full_qep_payload())

        def timeout(mpi: int) -> dict:
            return {
                "schema_version": "task033.memory-watchdog.v2",
                "benchmark_id": "task033_external_memory_watchdog",
                "status": "formal_not_pass",
                "target": "qep",
                "formal_pass": False,
                "numeric_pass": False,
                "return_code": -15,
                "terminated_for_timeout": True,
                "terminated_for_memory": False,
                "terminated_for_authority_unreadable": False,
                "memory_authority_pass": True,
                "no_swap": True,
                "resource_authority": {"gate": {"pass": True}},
                "launch_gate": {"pass": True},
                "source_gate": _source_gate(),
                "command": ["mpiexec", "-n", str(mpi), "python", "qep"],
            }

        def anchor(degree: int) -> dict:
            mode_count = 120 if degree == 1 else 160
            controlled = degree == 1
            return {
                "schema_version": "task033.memory-watchdog.v2",
                "benchmark_id": "task033_external_memory_watchdog",
                "status": "formal_not_pass" if controlled else "measured_shard_pass",
                "target": "hybrid",
                "formal_pass": not controlled,
                "numeric_pass": not controlled,
                "return_code": 2 if controlled else 0,
                "requested_modes": mode_count,
                "candidate_modes": 2 * mode_count,
                "terminated_for_timeout": False,
                "terminated_for_memory": False,
                "terminated_for_authority_unreadable": False,
                "memory_authority_pass": True,
                "no_swap": True,
                "resource_authority": {"gate": {"pass": True}},
                "launch_gate": {"pass": True},
                "source_gate": _source_gate(),
                "command": ["mpiexec", "-n", "4", "python", "hybrid"],
                "measurements": {
                    "status": (
                        "physical_integration_failed" if controlled else "pass"
                    ),
                    "case": {
                        "degree": degree,
                        "h_nm": 5.0,
                        "requested_modes_per_direction": mode_count,
                    },
                    "hybrid_system": {"primary_solver_path": "augmented"},
                    "solve": {"true_relative_residual": 1.0e-12},
                    "gates": {
                        "algebraic": True,
                        "sampled_interface_h_t_relative_l2_le_1e-2": (
                            not controlled
                        ),
                    },
                    "qualification": {
                        "integration_pass": not controlled,
                        "algebraic_chain_pass": True,
                        "physical_field_gates_pass": not controlled,
                        "task033_physical_truncation_allowed": True,
                        "mode_count_converged": not controlled,
                        "official_record": False,
                    },
                    "modal_schur_comparison": {
                        "status": "pass",
                        "comparison_solver_path": "modal-schur-memory-minimal",
                        "comparison_solver_path_argument": "minimal",
                        "dense_interface_square_formed": False,
                        "gates": {"solutions": True, "rta": True, "sparse": True},
                    },
                },
            }

        uniform_entries = []
        measured_coordinates = {
            (1, 5.0),
            (2, 5.0),
            (2, 3.0),
            (3, 5.0),
        }
        for degree in (1, 2, 3, 4):
            for h_nm in (5.0, 3.0, 2.5, 2.0, 1.5):
                key = f"p{degree}_h{str(h_nm).replace('.', 'p').removesuffix('p0')}"
                if (degree, h_nm) in measured_coordinates:
                    uniform_entries.append(
                        {
                            "matrix_key": key,
                            "degree": degree,
                            "h_nm": h_nm,
                            "planning_decision": "run",
                            "launch_decision": "run",
                            "evidence_disposition": "measured_qualified_funnel",
                            "data_identity": "measured",
                            "source_commit_sha": SOURCE_SHA,
                            "source_record_sha256": _digest(f"uniform-{degree}-{h_nm}"),
                        }
                    )
                else:
                    uniform_entries.append(
                        {
                            "matrix_key": key,
                            "degree": degree,
                            "h_nm": h_nm,
                            "planning_decision": "not_run_by_memory_gate",
                            "launch_decision": "not_run_by_memory_gate",
                            "evidence_disposition": "not_run_by_memory_gate",
                            "data_identity": "not_run",
                            "source_record_sha256": None,
                        }
                    )
        uniform = {
            "schema_version": "task033.case091.uniform-p-h-matrix.v1",
            "record_type": "task033_uniform_p_h_matrix",
            "status": "formal_matrix_complete",
            "formal_source": _formal_source(),
            "entries": uniform_entries,
        }

        def candidate(
            candidate_id: str,
            *,
            degree: int,
            h_nm: float,
            local_dofs: int,
            funnel_sha: str,
            graded_reference_h_nm: float | None = None,
        ) -> dict:
            case = {"degree": degree, "h_nm": h_nm}
            if graded_reference_h_nm is not None:
                case["graded_reference_h_nm"] = graded_reference_h_nm
            compression = 1000.0 / local_dofs
            return {
                "candidate_id": candidate_id,
                "label": candidate_id,
                "status": "equal_accuracy_qualified",
                "case": case,
                "source_commit_full_sha": SOURCE_SHA,
                "input": {
                    "funnel_path": f"{candidate_id}.json",
                    "funnel_sha256": funnel_sha,
                },
                "costs": {
                    "local_dofs": local_dofs,
                    "total_rows": local_dofs * 2,
                    "assembled_nnz": local_dofs * 10,
                    "authoritative_rss_bytes": local_dofs * 100,
                    "total_time_seconds": float(local_dofs),
                },
                "compression_ratios": {"local_dofs": compression},
                "local_dof_compression_classification": (
                    "engineering" if compression == 4.0 else "clear"
                ),
                "gates": {"physical": True},
                "failures": [],
            }

        equal_candidates = [
            candidate(
                "uniform_p2_h5",
                degree=2,
                h_nm=5.0,
                local_dofs=400,
                funnel_sha=_digest("uniform-2-5.0"),
            ),
            candidate(
                "graded_p2_h5",
                degree=2,
                h_nm=5.0,
                local_dofs=350,
                funnel_sha=_digest("graded-2-5.0"),
                graded_reference_h_nm=5.0,
            ),
            candidate(
                "uniform_p3_h5",
                degree=3,
                h_nm=5.0,
                local_dofs=250,
                funnel_sha=_digest("uniform-3-5.0"),
            ),
        ]
        equal = {
            "schema_version": "task033.case091.equal-accuracy.v1",
            "record_type": "task033_global_equal_accuracy_efficiency",
            "status": "qualified",
            "identity": {
                "source_commit_full_sha": SOURCE_SHA,
                "all_qualified_inputs_same_clean_sha": True,
                "consumes_measured_pde_records": True,
                "proves_0p7nm_feasible": False,
            },
            "inputs": {
                "reference": {},
                "candidates": [
                    {
                        "candidate_id": row["candidate_id"],
                        **row["input"],
                    }
                    for row in equal_candidates
                ],
            },
            "reference": {
                "case": {"degree": 2, "h_nm": 3.0},
                "source_commit_full_sha": SOURCE_SHA,
                "costs": {
                    "local_dofs": 1000,
                    "total_rows": 2000,
                    "assembled_nnz": 10000,
                    "authoritative_rss_bytes": 100000,
                    "total_time_seconds": 1000.0,
                },
            },
            "candidates": equal_candidates,
            "selection": {
                "qualified_candidate_count": 3,
                "pareto_frontier_candidate_ids": ["uniform_p3_h5"],
                "best_candidate_id": "uniform_p3_h5",
                "best_candidate_label": "uniform_p3_h5",
            },
        }
        equal["payload_sha256"] = _payload_sha(equal, "payload_sha256")
        equal_path = self._write("equal_accuracy.json", equal)

        def adaptive(h_nm: float, compression: float) -> dict:
            return {
                "schema_version": 1,
                "task_id": "Task033",
                "record_type": "p2_periodic_graded_mesh_plan",
                "status": "measured_same_accuracy_qualification_attached",
                "formal_source": _formal_source(),
                "plan": {"degree": 2, "reference_h_nm": h_nm},
                "same_accuracy_qualification": {
                    "status": "same_accuracy_mandatory_gate_pass",
                    "mandatory_gate_pass": True,
                    "compression": compression,
                    "compression_unit": "dimensionless_local_fe_row_ratio",
                    "compression_baseline": f"uniform_p2_h{h_nm:g}",
                    "compression_denominator": "candidate_local_fe_rows",
                },
                "measured_evidence": {
                    kind: {
                        "sha256": _digest(f"adaptive-{h_nm}-{kind}"),
                        "selected_watchdog_sha256": _digest(
                            f"adaptive-{h_nm}-{kind}-watchdog"
                        ),
                    }
                    for kind in ("reference", "candidate")
                },
            }

        buffer = {
            "schema_version": "task033.case091.interface-buffer-tradeoff.v1",
            "record_type": "task033_interface_buffer_tradeoff",
            "status": "qualified",
            "formal_source": _formal_source(),
            "candidates": [
                {
                    "buffer_nm": value,
                    "source_record_sha256": _digest(f"buffer-{value}"),
                }
                for value in (10.0, 7.5, 5.0, 2.5)
            ],
            "selected_buffer_nm": 5.0,
        }
        variable_p = {
            "schema_version": "task033.case091.variable-p-audit.v1",
            "record_type": "task033_variable_p_hcurl_capability_audit",
            "status": "not_qualified_fail_closed",
            "formal_source": _formal_source(),
            "decision": {
                "native_cellwise_variable_p_hcurl_qualified": False,
                "implement_bespoke_arbitrary_variable_p_constraints": False,
                "disposition": "fail_closed_no_hp_zoning_prototype",
            },
        }
        one_tib = {
            "schema_version": "task033.case091.one-tib-projection.v1",
            "record_type": "task033_one_tib_local_fe_row_projection",
            "status": "classified",
            "route_basis": "equal_accuracy_best_candidate",
            "formal_source": _formal_source(),
            "identity": {
                "is_0p7nm_wavelength_transfer_validation": False,
                "is_0p7nm_feasibility_proof": False,
            },
            "input": {
                "same_error_local_dof_compression": 4.0,
                "evidence_record": str(equal_path),
                "evidence_record_type": "task033_global_equal_accuracy_efficiency",
                "evidence_schema_version": "task033.case091.equal-accuracy.v1",
                "evidence_payload_sha256": equal["payload_sha256"],
                "source_commit_sha": SOURCE_SHA,
                "same_accuracy_status": "equal_accuracy_qualified",
                "compression_source_unit": "dimensionless_local_fe_row_ratio",
                "compression_baseline": "measured_equal_accuracy_reference_local_dofs",
                "physical_equal_accuracy_qualified": True,
                "best_candidate_id": "uniform_p3_h5",
                "best_candidate_label": "uniform_p3_h5",
                "reference_local_dofs": 1000,
                "candidate_local_dofs": 250,
                "qualified": True,
            },
            "result": {
                "projected_local_fe_rows": 230836500,
                "classification": "candidate",
            },
        }

        paths: dict[str, Path | str] = {
            "case090_core": self._write("case090.json", core),
            "qep_mpi1_aggregate": self._write("qep.json", qep),
            "qep_mpi2_timeout_negative": self._write("qep_mpi2.json", timeout(2)),
            "qep_mpi4_timeout_negative": self._write("qep_mpi4.json", timeout(4)),
            "augmented_vs_minimal_p1": self._write("anchor_p1.json", anchor(1)),
            "augmented_vs_minimal_p3": self._write("anchor_p3.json", anchor(3)),
            "uniform_p_h_matrix": self._write("uniform.json", uniform),
            "equal_accuracy": equal_path,
            "adaptive_p2_h5": self._write("adaptive_h5.json", adaptive(5.0, 1.5)),
            "adaptive_p2_h3": self._write("adaptive_h3.json", adaptive(3.0, 2.5)),
            "interface_buffer_tradeoff": self._write("buffer.json", buffer),
            "variable_p_capability_audit": self._write("variable_p.json", variable_p),
            "one_tib_projection": self._write("one_tib.json", one_tib),
            "expected_source_sha": SOURCE_SHA,
            "repo_root": self.root,
        }
        return paths

    def _load(self, key: str) -> dict:
        return json.loads(Path(self.paths[key]).read_text(encoding="utf-8"))

    def _replace(self, key: str, payload: dict) -> None:
        Path(self.paths[key]).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _materialize_qep_sources(self, payload: dict) -> dict:
        for index, row in enumerate(payload["source_records"]):
            negative = row["disposition"] == "controlled_numeric_negative"
            candidate = row["candidate"]
            solver_payload = _qep_shard(
                candidate["material_kind"],
                candidate["degree"],
                candidate["h_nm"],
            )
            if negative:
                solver_payload = _controlled_p4_negative(solver_payload)
            source = solver_payload["provenance"]
            solver_path = self._write(
                f"qep_source_{index}.solver.json", solver_payload
            )
            summary = {
                "schema_version": "task033.memory-watchdog.v2",
                "benchmark_id": "task033_external_memory_watchdog",
                "target": "qep",
                "status": "formal_not_pass" if negative else "measured_shard_pass",
                "formal_pass": not negative,
                "numeric_pass": not negative,
                "return_code": 2 if negative else 0,
                "memory_authority_pass": True,
                "no_swap": True,
                "terminated_for_memory": False,
                "terminated_for_timeout": False,
                "terminated_for_authority_unreadable": False,
                "resource_authority": {"gate": {"pass": True}},
                "source": source,
                "source_gate": source_identity_gate(source),
                "worker_source": source,
                "launch_gate": {"pass": True},
                "solver_record_sha256": _file_sha(solver_path),
                "solver_record_ignored_path": solver_path.relative_to(
                    self.root
                ).as_posix(),
                "measurements": solver_payload,
            }
            watchdog_path = self._write(
                f"qep_source_{index}.watchdog.json", summary
            )
            row["path"] = watchdog_path.relative_to(self.root).as_posix()
            row["sha256"] = _file_sha(watchdog_path)
            row["solver_record"] = {
                "path": solver_path.relative_to(self.root).as_posix(),
                "sha256": _file_sha(solver_path),
            }
            key = "|".join(
                str(candidate[name])
                for name in ("material_kind", "degree", "h_nm", "mpi_size")
            )
            positive_gate = qep_shard_gate(solver_payload)
            controlled_gate = qep_p4_controlled_negative_gate(solver_payload)
            payload["shard_gates"][key] = {
                "pass": positive_gate["pass"],
                "disposition": (
                    "controlled_numeric_negative" if negative else "pass"
                ),
                "positive_gate": positive_gate,
                "controlled_negative_gate": controlled_gate,
            }
        by_candidate = {
            (
                row["candidate"]["material_kind"],
                row["candidate"]["degree"],
                row["candidate"]["h_nm"],
                row["candidate"]["mpi_size"],
            ): row
            for row in payload["source_records"]
        }
        for observation in payload["negative_observations"]:
            candidate = observation["candidate"]
            source = by_candidate[
                (
                    candidate["material_kind"],
                    candidate["degree"],
                    candidate["h_nm"],
                    candidate["mpi_size"],
                )
            ]
            observation["evidence"] = {
                "watchdog_summary": {
                    "path": source["path"],
                    "sha256": source["sha256"],
                },
                "solver_record": source["solver_record"],
                "watchdog_return_code": 2,
            }
        return payload

    @staticmethod
    def _partial_qep_payload() -> dict:
        materials = ("air", "lossy_homogeneous", "stage4_xy")
        degrees = (1, 2, 3, 4)
        levels = (5.0, 3.0, 2.5)
        shard_gates = {}
        source_records = []
        for material in materials:
            for degree in degrees:
                for h_nm in levels:
                    key = f"{material}|{degree}|{h_nm}|1"
                    shard_gates[key] = {
                        "pass": True,
                        "disposition": "pass",
                        "positive_gate": {
                            "pass": True,
                            "checks": {"complete": True},
                            "failures": [],
                        },
                        "controlled_negative_gate": {
                            "pass": False,
                            "checks": {"not_negative": False},
                            "failures": ["not_negative"],
                            "controlled_failure_gates": [],
                        },
                    }
                    source_records.append(
                        {
                            "candidate": {
                                "material_kind": material,
                                "degree": degree,
                                "h_nm": h_nm,
                                "mpi_size": 1,
                            },
                            "path": f"qep/{key}/watchdog.json",
                            "sha256": _digest(f"watchdog-{key}"),
                            "disposition": "pass",
                            "solver_record": {
                                "path": f"qep/{key}/solver.json",
                                "sha256": _digest(f"solver-{key}"),
                            },
                        }
                    )
        controlled_key = "lossy_homogeneous|4|3.0|1"
        positive_check_names = {
            "measured_shard_status",
            "measured_pde_solver_identity",
            "no_exception_failure_payload",
            "source_identity",
            "resource_authority",
            "converged_eigenpairs",
            "right_residual",
            "left_residual",
            "biorthogonality",
            "left_candidate_pool_policy",
            "right_requested_modes",
            "left_candidate_requested_modes",
            "left_candidate_converged_modes",
            "left_pair_relative_errors_complete_and_finite",
            "left_pair_relative_error_max_matches_list",
            "left_right_beta_pair_relative_error_le_1e-7",
            "reported_left_right_beta_pair_gate_matches_recomputed",
            "raised_quadrature",
            "analytic_beta_identity",
            "patterned_tracking_compact_input",
            "runtime_preflight_complete",
            "reported_all_required_numerical_gates_pass",
            "reported_converged_eigenpair_gate",
            "reported_right_residual_gate_matches_recomputed",
            "reported_left_residual_gate_matches_recomputed",
            "reported_biorthogonality_gate_matches_recomputed",
            "reported_no_swap_gate",
            "reported_below_termination_gate",
            "reported_formal_resource_gate",
            "reported_raised_quadrature_gate_matches_recomputed",
            "reported_tracking_gate_matches_recomputed",
            "reported_single_shard_identity_gate",
            "reported_source_identity_gate",
            "reported_analytic_gate_matches_recomputed",
        }
        expected_failures = {
            "measured_shard_status",
            "measured_pde_solver_identity",
            "biorthogonality",
            "reported_all_required_numerical_gates_pass",
        }
        shard_gates[controlled_key] = {
            "pass": False,
            "disposition": "controlled_numeric_negative",
            "positive_gate": {
                "pass": False,
                "checks": {
                    name: name not in expected_failures
                    for name in positive_check_names
                },
                "failures": sorted(expected_failures),
            },
            "controlled_negative_gate": {
                "pass": True,
                "checks": {"complete": True},
                "failures": [],
                "controlled_failure_gates": [
                    "biorthogonality_identity_error_le_1e-6"
                ],
            },
        }
        controlled_source = next(
            row
            for row in source_records
            if row["candidate"]
            == {
                "material_kind": "lossy_homogeneous",
                "degree": 4,
                "h_nm": 3.0,
                "mpi_size": 1,
            }
        )
        controlled_source["disposition"] = "controlled_numeric_negative"
        analytic_trends = {
            material: {
                f"p{degree}": {
                    "h_nm": list(levels),
                    "relative_errors": [1.0e-3, 5.0e-4, 2.5e-4],
                    "h_refinement_trend_pass": True,
                }
                for degree in degrees
            }
            for material in ("air", "lossy_homogeneous")
        }
        relative_to_p2 = {
            material: [
                {
                    "h_nm": h_nm,
                    **{
                        f"p{degree}_error_over_p2": 1.0
                        for degree in degrees
                    },
                }
                for h_nm in levels
            ]
            for material in ("air", "lossy_homogeneous")
        }
        patterned_tracking = {
            f"p{degree}": [{"pass": True}, {"pass": True}]
            for degree in degrees
        }
        return {
            "schema_version": "task033.qep-aggregate.v1",
            "record_type": "task033_qep_aggregate",
            "status": "qep_component_aggregate_not_qualified",
            "qualification_classification": "partial_p3_only",
            "formal_source": _formal_source(),
            "identity": {
                "is_qep_component_qualified": False,
                "is_qep_p3_only_partial": True,
                "is_physical_qualification_record": False,
            },
            "mpi_size": 1,
            "required_shard_count": 36,
            "received_unique_shard_count": 36,
            "duplicate_count": 0,
            "unexpected_record_count": 0,
            "missing_candidates": [],
            "p1_p2_p3_passed_shard_count": 27,
            "p4_completed_shard_count": 9,
            "negative_observation_count": 1,
            "negative_observations": [
                {
                    "candidate": {
                        "material_kind": "lossy_homogeneous",
                        "degree": 4,
                        "h_nm": 3.0,
                        "mpi_size": 1,
                    },
                    "status": "measured_shard_failed",
                    "disposition": "controlled_numeric_negative",
                    "controlled_failure_gates": [
                        "biorthogonality_identity_error_le_1e-6"
                    ],
                    "is_qep_component_qualified": False,
                    "evidence": {
                        "watchdog_summary": {
                            "path": controlled_source["path"],
                            "sha256": controlled_source["sha256"],
                        },
                        "solver_record": controlled_source["solver_record"],
                        "watchdog_return_code": 2,
                    },
                }
            ],
            "degree_qualification": {
                **{
                    f"p{degree}": {
                        "status": "qualified",
                        "required_shard_count": 9,
                        "passed_shard_count": 9,
                        "controlled_negative_shard_count": 0,
                    }
                    for degree in (1, 2, 3)
                },
                "p4": {
                    "status": "controlled_numeric_negative",
                    "required_shard_count": 9,
                    "passed_shard_count": 8,
                    "controlled_negative_shard_count": 1,
                },
            },
            "shard_gates": shard_gates,
            "analytic_beta_trends": analytic_trends,
            "relative_to_p2": relative_to_p2,
            "patterned_cross_h_tracking": patterned_tracking,
            "source_records": source_records,
            "gates": {
                "complete_unique_required_shards": True,
                "p1_p2_p3_27_shards_pass": True,
                "p4_9_shards_complete_pass_or_controlled_numeric_negative": True,
                "p1_p2_p3_analytic_trends_and_p2_relative_pass": True,
                "p1_p2_p3_patterned_cross_h_tracking_pass": True,
                "all_shard_contracts_pass": False,
                "air_lossy_h_p_trends_and_p2_relative_pass": True,
                "patterned_residual_biorth_and_cross_h_tracking_pass": False,
            },
        }

    @classmethod
    def _full_qep_payload(cls) -> dict:
        payload = cls._partial_qep_payload()
        payload["status"] = "qep_component_aggregate_qualified"
        payload["qualification_classification"] = "full_p1_p4_qualified"
        payload["identity"]["is_qep_component_qualified"] = True
        payload["identity"]["is_qep_p3_only_partial"] = False
        payload["negative_observation_count"] = 0
        payload["negative_observations"] = []
        payload["degree_qualification"]["p4"] = {
            "status": "qualified",
            "required_shard_count": 9,
            "passed_shard_count": 9,
            "controlled_negative_shard_count": 0,
        }
        controlled_key = "lossy_homogeneous|4|3.0|1"
        payload["shard_gates"][controlled_key] = {
            "pass": True,
            "disposition": "pass",
            "positive_gate": {
                "pass": True,
                "checks": {"complete": True},
                "failures": [],
            },
            "controlled_negative_gate": {
                "pass": False,
                "checks": {"not_negative": False},
                "failures": ["not_negative"],
                "controlled_failure_gates": [],
            },
        }
        for row in payload["source_records"]:
            row["disposition"] = "pass"
        for name in payload["gates"]:
            payload["gates"][name] = True
        return payload

    def test_equal_route_builds_strict_partial_outcome(self) -> None:
        result = build_final_outcome(**self.paths)
        Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))).validate(
            result
        )
        classifications = result["classifications"]
        self.assertEqual(classifications["overall"]["disposition"], "partial")
        self.assertEqual(
            classifications["overall"]["partial_reasons"][0],
            "matching_interface_qep_mpi2_mpi4_not_positively_qualified",
        )
        self.assertEqual(classifications["equal_accuracy"]["p3"]["disposition"], "pass")
        self.assertEqual(
            classifications["equal_accuracy"]["p4"]["disposition"],
            "legitimate_not_run",
        )
        self.assertEqual(classifications["one_tib"]["compression_evidence_role"], "equal_accuracy")
        self.assertEqual(classifications["hp_compression"]["classification"], "hp_compression_engineering")
        self.assertFalse(result["identity"]["proves_0p7nm_feasible"])
        self.assertFalse(
            classifications["distributed_qep"]["mpi2"]["proves_pep_or_mumps_boundary"]
        )

    def test_uniform_and_graded_p2_h5_do_not_collide(self) -> None:
        result = build_final_outcome(**self.paths)
        self.assertEqual(result["classifications"]["equal_accuracy"]["p3"]["best_h_nm"], 5.0)

    def test_input_descriptors_are_repo_relative_and_escape_is_rejected(self) -> None:
        result = build_final_outcome(**self.paths)
        self.assertEqual(len(result["input_evidence"]), 13)
        self.assertTrue(
            all(
                not Path(item["path"]).is_absolute()
                and "\\" not in item["path"]
                for item in result["input_evidence"]
            )
        )
        escaped = dict(self.paths)
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "outside.json"
            path.write_text("{}", encoding="utf-8")
            escaped["case090_core"] = path
            with self.assertRaisesRegex(
                FinalOutcomeError, "escapes repository root"
            ):
                build_final_outcome(**escaped)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        descriptors = {item["role"]: item for item in result["input_evidence"]}
        entries = [
            {
                "role": manifest_role,
                "path": descriptors[input_role]["path"],
                "sha256": descriptors[input_role]["sha256"],
            }
            for input_role, manifest_role in FINAL_OUTCOME_INPUT_ROLE_MAP
        ]
        for bad_path in (
            "/absolute.json",
            "C:/absolute.json",
            "nested\\record.json",
            "../escape.json",
            "nested/../escape.json",
            "./record.json",
            "nested/./record.json",
            "nested//record.json",
            "nested/",
        ):
            with self.subTest(descriptor_path=bad_path):
                forged = copy.deepcopy(result)
                forged["input_evidence"][0]["path"] = bad_path
                self.assertTrue(list(validator.iter_errors(forged)))
                forged_entries = copy.deepcopy(entries)
                forged_entries[0]["path"] = bad_path
                self.assertTrue(
                    final_outcome_manifest_closure_problems(
                        forged, forged_entries, SOURCE_SHA
                    )
                )

    def test_mixed_clean_source_sha_is_rejected(self) -> None:
        payload = self._load("interface_buffer_tradeoff")
        payload["formal_source"]["commit_sha"] = "b" * 40
        self._replace("interface_buffer_tradeoff", payload)
        with self.assertRaisesRegex(FinalOutcomeError, "mixes clean-source SHAs"):
            build_final_outcome(**self.paths)

    def test_tampered_equal_accuracy_payload_is_rejected(self) -> None:
        payload = self._load("equal_accuracy")
        payload["selection"]["best_candidate_label"] = "tampered"
        self._replace("equal_accuracy", payload)
        with self.assertRaisesRegex(FinalOutcomeError, "payload SHA-256 is invalid"):
            build_final_outcome(**self.paths)

    def test_invalid_timeout_negative_makes_outcome_failed(self) -> None:
        payload = self._load("qep_mpi2_timeout_negative")
        payload["terminated_for_memory"] = True
        self._replace("qep_mpi2_timeout_negative", payload)
        result = build_final_outcome(**self.paths)
        self.assertEqual(result["classifications"]["overall"]["disposition"], "failed")
        self.assertEqual(
            result["classifications"]["distributed_qep"]["mpi2"]["classification"],
            "invalid_timeout_negative",
        )

    def test_timeout_negative_missing_hard_contract_fields_fails_closed(self) -> None:
        original = self._load("qep_mpi2_timeout_negative")
        expected_failure = {
            "numeric_pass": "numeric_not_pass",
            "return_code": "nonzero_integer_return_code",
            "resource_authority": "resource_authority_gate_pass",
            "source_gate": "source_gate_pass",
        }
        for field, failure in expected_failure.items():
            with self.subTest(field=field):
                payload = dict(original)
                payload.pop(field)
                self._replace("qep_mpi2_timeout_negative", payload)
                if field == "source_gate":
                    with self.assertRaisesRegex(
                        FinalOutcomeError, "source_gate must be one JSON object"
                    ):
                        build_final_outcome(**self.paths)
                    continue
                result = build_final_outcome(**self.paths)
                mpi2 = result["classifications"]["distributed_qep"]["mpi2"]
                self.assertEqual(mpi2["disposition"], "failed")
                self.assertIn(failure, mpi2["failures"])
        self._replace("qep_mpi2_timeout_negative", original)

    def test_final_schema_rejects_cross_classification_contradictions(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        baseline = build_final_outcome(**self.paths)

        contradictions: dict[str, dict] = {}

        overall = copy.deepcopy(baseline)
        overall["classifications"]["overall"]["classification"] = (
            "task033_failed"
        )
        contradictions["overall_disposition_classification"] = overall

        high_order = copy.deepcopy(baseline)
        high_order["classifications"]["high_order_floquet"][
            "classification"
        ] = "high_order_floquet_failed"
        contradictions["high_order_failed_with_pass_flags"] = high_order

        distributed_failed = copy.deepcopy(baseline)
        distributed_failed["classifications"]["distributed_qep"][
            "disposition"
        ] = "failed"
        contradictions["distributed_failed_with_partial_contract"] = (
            distributed_failed
        )

        timeout = copy.deepcopy(baseline)
        timeout["classifications"]["distributed_qep"]["mpi2"][
            "classification"
        ] = "invalid_timeout_negative"
        contradictions["timeout_disposition_classification"] = timeout

        distributed_partial = copy.deepcopy(baseline)
        mpi2 = distributed_partial["classifications"]["distributed_qep"][
            "mpi2"
        ]
        mpi2["disposition"] = "failed"
        mpi2["classification"] = "invalid_timeout_negative"
        mpi2[
            "proves_watchdog_source_resource_timeout_contract_only"
        ] = False
        mpi2["checks"]["numeric_not_pass"] = False
        mpi2["failures"] = ["numeric_not_pass"]
        contradictions["distributed_partial_with_failed_mpi2"] = (
            distributed_partial
        )

        for name, record in contradictions.items():
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validator.validate(record)

    def test_controlled_p4_qep_negative_classifies_high_order_as_p3_only(self) -> None:
        partial = self._materialize_qep_sources(self._partial_qep_payload())
        self._replace("qep_mpi1_aggregate", partial)
        result = build_final_outcome(**self.paths)
        high_order = result["classifications"]["high_order_floquet"]
        self.assertEqual(
            high_order["classification"],
            "high_order_floquet_partial_p3_only",
        )
        self.assertFalse(high_order["qep_mpi1_component_pass"])
        self.assertTrue(high_order["qep_mpi1_p3_only_partial"])
        self.assertNotIn(
            "qep_mpi1_aggregate_not_qualified",
            result["classifications"]["overall"]["mandatory_failures"],
        )
        self.assertIn(
            "qep_p4_controlled_numeric_negative",
            result["classifications"]["overall"]["partial_reasons"],
        )

        forged = self._materialize_qep_sources(self._partial_qep_payload())
        forged["negative_observations"][0]["controlled_failure_gates"] = [
            "raised_quadrature_pass"
        ]
        self._replace("qep_mpi1_aggregate", forged)
        failed = build_final_outcome(**self.paths)
        self.assertEqual(
            failed["classifications"]["high_order_floquet"]["classification"],
            "high_order_floquet_failed",
        )

    def test_measured_p4_without_equal_accuracy_is_failed_not_not_run(self) -> None:
        payload = self._load("uniform_p_h_matrix")
        row = next(
            row
            for row in payload["entries"]
            if row["degree"] == 4 and row["h_nm"] == 5.0
        )
        row.update(
            {
                "planning_decision": "run",
                "launch_decision": "run",
                "evidence_disposition": "measured_qualified_funnel",
                "data_identity": "measured",
                "source_commit_sha": SOURCE_SHA,
                "source_record_sha256": _digest("uniform-4-5.0"),
            }
        )
        self._replace("uniform_p_h_matrix", payload)
        result = build_final_outcome(**self.paths)
        self.assertEqual(result["classifications"]["equal_accuracy"]["p4"]["disposition"], "failed")
        self.assertEqual(result["classifications"]["overall"]["disposition"], "failed")

    def test_uniform_capacity_disposition_requires_exact_p1_h5_evidence(self) -> None:
        payload = self._load("uniform_p_h_matrix")
        row = next(
            row
            for row in payload["entries"]
            if row["degree"] == 1 and row["h_nm"] == 5.0
        )
        row.update(
            {
                "evidence_disposition": (
                    "measured_not_qualified_by_modal_basis_capacity"
                ),
                "source_status": "not_qualified",
                "source_is_pde_run": True,
                "source_is_solver_pass": False,
                "selected_mode_count_per_direction": None,
                "candidate_modes_per_target_branch": 320,
                "attempted_mode_count_per_direction": 160,
                "modal_basis_capacity": {
                    "status": "insufficient_finite_admissible_modes",
                    "direction": "positive",
                    "requested_modes_per_direction": 160,
                    "delivered_finite_admissible_modes": 120,
                    "finite_candidate_count_both_directions": 240,
                    "numerically_infinite_candidate_count": 80,
                    "finite_spectrum_abs_beta_h_cutoff": 1.0e4,
                    "finite_spectrum_abs_beta_cutoff_per_nm": 123.0,
                    "first_rejected_numerical_infinity_beta_per_nm": [
                        1.1e7,
                        2.0e6,
                    ],
                    "leading_coefficient_singular_by_design": True,
                    "pair_tolerance_relaxed": False,
                    "left_pair_relative_error_tolerance": 1.0e-7,
                },
            }
        )
        self._replace("uniform_p_h_matrix", payload)
        with self.assertRaisesRegex(
            FinalOutcomeError,
            "non-exact modal-basis capacity negative",
        ):
            build_final_outcome(**self.paths)

    def test_uniform_terminal_p1_negative_is_partial_and_fail_closed(self) -> None:
        payload = self._load("uniform_p_h_matrix")
        row = next(
            row
            for row in payload["entries"]
            if row["degree"] == 1 and row["h_nm"] == 3.0
        )
        row.update(
            {
                "planning_decision": "run",
                "launch_decision": "run",
                "evidence_disposition": (
                    "measured_not_qualified_by_physical_field_gates"
                ),
                "data_identity": "measured",
                "source_commit_sha": SOURCE_SHA,
                "source_record_sha256": _digest("uniform-p1-h3-terminal"),
                "source_status": "not_qualified",
                "source_is_pde_run": True,
                "source_is_solver_pass": False,
                "selected_mode_count_per_direction": None,
                "candidate_modes_per_target_branch": 320,
                "attempted_mode_count_per_direction": 160,
                "modal_basis_capacity": None,
                "terminal_physical_gate_limited": True,
                "terminal_physical_gate_evidence": {
                    "integration_pass": False,
                    "algebraic_chain_pass": True,
                    "physical_field_gates_pass": False,
                    "task033_physical_truncation_allowed": True,
                    "candidate_pool_is_twice_requested_modes": True,
                    "true_relative_residual": 8.0e-13,
                    "true_relative_residual_le_1e-9": True,
                    "all_reported_gates_pass": False,
                    "failed_gate_names": [
                        "sampled_interface_h_t_relative_l2_le_1e-2"
                    ],
                },
                "terminal_physical_reference_evidence": None,
            }
        )
        self._replace("uniform_p_h_matrix", payload)
        result = build_final_outcome(**self.paths)
        uniform = result["classifications"]["uniform_p_h_matrix"]
        self.assertEqual(uniform["p1_terminal_physical_gate_negative_entries"], 1)
        self.assertIn(
            "p1_terminal_physical_field_gate_negatives",
            result["classifications"]["overall"]["partial_reasons"],
        )

        row["terminal_physical_gate_evidence"]["algebraic_chain_pass"] = False
        self._replace("uniform_p_h_matrix", payload)
        with self.assertRaisesRegex(
            FinalOutcomeError,
            "non-exact p1 terminal physical negative",
        ):
            build_final_outcome(**self.paths)

        row["terminal_physical_gate_evidence"]["algebraic_chain_pass"] = True
        row["terminal_physical_reference_evidence"] = {
            "reference_degree": 2,
            "reference_binding_verified": True,
        }
        self._replace("uniform_p_h_matrix", payload)
        with self.assertRaisesRegex(
            FinalOutcomeError,
            "non-exact p1 terminal physical negative",
        ):
            build_final_outcome(**self.paths)

    def test_cli_writes_same_classified_record(self) -> None:
        output = self.root / "final.json"
        option_names = {
            "case090_core": "--case090-core",
            "qep_mpi1_aggregate": "--qep-mpi1-aggregate",
            "qep_mpi2_timeout_negative": "--qep-mpi2-timeout-negative",
            "qep_mpi4_timeout_negative": "--qep-mpi4-timeout-negative",
            "augmented_vs_minimal_p1": "--augmented-vs-minimal-p1",
            "augmented_vs_minimal_p3": "--augmented-vs-minimal-p3",
            "uniform_p_h_matrix": "--uniform-p-h-matrix",
            "equal_accuracy": "--equal-accuracy",
            "adaptive_p2_h5": "--adaptive-p2-h5",
            "adaptive_p2_h3": "--adaptive-p2-h3",
            "interface_buffer_tradeoff": "--interface-buffer-tradeoff",
            "variable_p_capability_audit": "--variable-p-capability-audit",
            "one_tib_projection": "--one-tib-projection",
            "expected_source_sha": "--expected-source-sha",
        }
        argv: list[str] = []
        for key, option in option_names.items():
            argv.extend((option, str(self.paths[key])))
        argv.extend(
            (
                "--repo-root",
                str(self.root),
                "--output",
                str(output),
                "--require-nonfailed",
            )
        )
        self.assertEqual(cli_main(argv), 0)
        self.assertEqual(
            json.loads(output.read_text(encoding="utf-8"))["status"], "classified"
        )


if __name__ == "__main__":
    unittest.main()
