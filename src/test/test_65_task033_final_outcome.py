from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from benchmarks.run_task033_final_outcome import main as cli_main
from benchmarks.task033_final_outcome import (
    FinalOutcomeError,
    SCHEMA_PATH,
    build_final_outcome,
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

        qep = {
            "schema_version": "task033.qep-aggregate.v1",
            "record_type": "task033_qep_aggregate",
            "status": "qep_component_aggregate_qualified",
            "formal_source": _formal_source(),
            "identity": {"is_qep_component_qualified": True},
            "gates": {"complete": True, "numerical": True},
            "missing_candidates": [],
            "duplicate_count": 0,
        }

        def timeout(mpi: int) -> dict:
            return {
                "schema_version": "task033.memory-watchdog.v2",
                "benchmark_id": "task033_external_memory_watchdog",
                "status": "formal_not_pass",
                "target": "qep",
                "formal_pass": False,
                "terminated_for_timeout": True,
                "terminated_for_memory": False,
                "terminated_for_authority_unreadable": False,
                "memory_authority_pass": True,
                "no_swap": True,
                "launch_gate": {"pass": True},
                "source_gate": _source_gate(),
                "command": ["mpiexec", "-n", str(mpi), "python", "qep"],
            }

        def anchor(degree: int) -> dict:
            return {
                "schema_version": "task033.memory-watchdog.v2",
                "benchmark_id": "task033_external_memory_watchdog",
                "status": "measured_shard_pass",
                "target": "hybrid",
                "formal_pass": True,
                "terminated_for_timeout": False,
                "terminated_for_memory": False,
                "terminated_for_authority_unreadable": False,
                "memory_authority_pass": True,
                "no_swap": True,
                "launch_gate": {"pass": True},
                "source_gate": _source_gate(),
                "command": ["mpiexec", "-n", "4", "python", "hybrid"],
                "measurements": {
                    "case": {"degree": degree, "h_nm": 5.0},
                    "hybrid_system": {"primary_solver_path": "augmented"},
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
        }
        return paths

    def _load(self, key: str) -> dict:
        return json.loads(Path(self.paths[key]).read_text(encoding="utf-8"))

    def _replace(self, key: str, payload: dict) -> None:
        Path(self.paths[key]).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
        argv.extend(("--output", str(output), "--require-nonfailed"))
        self.assertEqual(cli_main(argv), 0)
        self.assertEqual(
            json.loads(output.read_text(encoding="utf-8"))["status"], "classified"
        )


if __name__ == "__main__":
    unittest.main()
