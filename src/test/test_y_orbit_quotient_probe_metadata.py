"""Isolated scalar/schema/AST contract tests; no numerical project imports."""
import ast
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "benchmarks/run_y_orbit_quotient_probe.py"
CHECKER = ROOT / "benchmarks/check_y_orbit_quotient_probe.py"


def extracted(path, names):
    tree = ast.parse(path.read_text())
    body = [node for node in tree.body if isinstance(node, ast.Assign)
            or isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {"__file__": str(path), "Path": Path, "math": math, "json": json,
             "re": re, "hashlib": hashlib}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), scope)
    return scope


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = extracted(RUNNER, {"plan_metadata", "allocation_request", "validate_worker_result",
                                      "apply_supervisor_classification", "plain_metadata", "factor_policy"})
        cls.checker = extracted(CHECKER, {"finite_gate", "per_mode_operation_error", "validate_scope", "validate_metadata_bindings",
            "expected_array_shapes", "validate_array_inventory", "validate_restoration_metadata", "validate_factor_event_contract", "validate_recovery_identity_bindings", "validate_historical_file_metadata"})

    def candidate(self, stage="prefactor"):
        flags = {key: False for key in ("candidate_full_Ny_CSR_created", "candidate_full_F_created",
            "candidate_full_Q_created", "candidate_global_FE_square_matrix_created", "raw_port_reassembled",
            "raw_literal_qualification_rerun", "performance_or_target_capacity_claim")}
        flags["full_layout_entity_stream"] = True
        blocks = [{"q": q, "shape": [size, size], "nnz": 1000,
                   "csr_prefix": f"q_{q}_S", "CSR_sha256": str(q) * 64,
                   "relative_frobenius_difference": 0., "relative_max_difference": 0.}
                  for q, size in enumerate(self.checker["Q_ROWS"])]
        report = {"schema": self.checker["SCHEMA"], "status": self.checker["PASSES"][stage],
            "stage": stage, "degree": 4, "physical_mode_count": 532, "official_results": False,
            "source_clean_unchanged": True, "prefactor_only": stage == "prefactor",
            "PDE_solved": stage == "solve", "factor_count": 0 if stage == "prefactor" else 4,
            "input_sha256": self.checker["INPUT_SHA"], "physical_generator_manifest_sha256": self.checker["PHYSICAL_MANIFEST"],
            "scope_flags": flags, "reformed_blocks": blocks}
        if stage == "solve":
            report.update(regular_sources={key: {} for key in self.checker["SOURCES"]},
                          notched_sources={key: {} for key in self.checker["SOURCES"]},
                          sampled_right_PC_defect={key: .01 for key in self.checker["SOURCES"]},
                          PC_defect_is_norm_bound=False, changed_cells=[1, 2], sampled_notch_off_q_delta_relative=.01)
            report["factor"] = {"input_blocks": deepcopy(blocks), "tests": [{"q": q,
                "true_block_residual": 0., "repeated_difference": 0., "linearity_difference": 0.} for q in range(4)],
                "all_reformed_blocks_compared_before_factor": True, "all_four_retained_simultaneously": True}
        return report

    def with_inventory(self, stage="prefactor"):
        report = self.candidate(stage)
        shapes = self.checker["expected_array_shapes"](report, stage)
        report["artifacts"] = {name: {"shape": shape, "nonfinite_entries": 0,
            "raw_failure_diagnostic_only": False, "file_sha256": "a" * 64} for name, shape in shapes.items()}
        for name in ("full_mpc_masters", "full_mpc_coefficients", "original_port_C_data",
                     "original_port_C_indices", "original_port_D_data", "original_port_D_indices"):
            report["artifacts"][name] = {"shape": [100], "nonfinite_entries": 0,
                "raw_failure_diagnostic_only": False, "file_sha256": "a" * 64}
        return report

    def metadata(self, stage="prefactor"):
        report = self.with_inventory(stage)
        source = {"head": "a" * 40, "branch": "task40extra_dot_parallel_cloud", "dirty": "",
                  "files_sha256": {"src/solvers/old.py": "b" * 64}}
        environment = {"petsc_scalar_type": "complex128", "qualification_manifest_sha256": "c" * 64}
        resource = {"stage": stage, "wall_seconds": 600, "swap_bytes": 0, "mpi": 1, "math_threads": 1,
            "evidence_reserve_bytes": self.checker["RESERVE_BYTES"], "tree_cap_bytes": self.checker["TREE_CAP_BYTES"],
            "factor_workspace_allowance_bytes": 0 if stage == "prefactor" else self.checker["FACTOR_ALLOWANCE_BYTES"],
            "factor_fill_and_temporary_workspace_unknown": True, "factor_L_U_statistics_copies_permitted": False,
            "performance_or_target_capacity_claim": False}
        report.update(source=source, environment=environment)
        provenance = {"source": deepcopy(source), "environment": deepcopy(environment), "schema": report["schema"],
                      "stage": stage, "degree": 4, "input_sha256": report["input_sha256"], "resource_contract": resource}
        return report, provenance, source, environment

    def validate_metadata(self, report, provenance, source, environment, stage="prefactor"):
        return self.checker["validate_metadata_bindings"](report, provenance, report["artifacts"],
            checker_source=source, checker_environment=environment, stage=stage)

    def test_default_invocation_has_no_project_imports(self):
        result = subprocess.run([sys.executable, str(RUNNER)], capture_output=True, text=True, check=True)
        facts = json.loads(result.stdout)
        self.assertEqual(facts["status"], "NOT_RUN_STAGED_PLAN_ONLY")
        self.assertEqual(facts["stage"], "prefactor")
        self.assertEqual(facts["factor_count"], 0)
        self.assertEqual(facts["factor_workspace_allowance_bytes"], 0)

    def test_solve_without_run_still_plan_only(self):
        facts = self.runner["plan_metadata"]("solve")
        self.assertFalse(facts["PDE_solved"])
        self.assertEqual(facts["factor_count"], 0)

    def test_external_staging_run_is_blocked_before_import(self):
        # Exercise an actual external layout even after this test is integrated
        # into canonical; it must reject before any project import or mkdir.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "benchmarks/run_y_orbit_quotient_probe.py"
            runner.parent.mkdir()
            runner.write_bytes(RUNNER.read_bytes())
            target = root / "benchmarks/artifacts/task40extra_dot_parallel_cloud/never_created_contract_test"
            result = subprocess.run([sys.executable, str(runner), "--run", "--expected-head", "a" * 40,
                "--run-directory", str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("external staging cannot run", result.stderr)
            self.assertFalse(target.exists())

    def test_unknown_plan_stage(self):
        with self.assertRaises(ValueError):
            self.runner["plan_metadata"]("audit")

    def test_prefactor_allocation_rejects_every_factor_declaration(self):
        for key in ("factor_count", "retained_factor_count", "resident_factor_count",
                    "factor_workspace_allowance_bytes", "declared_factor_workspace_allowance_bytes"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.runner["allocation_request"]("prefactor", {key: 1})

    def test_prefactor_allocation_has_only_additional_bytes_and_reserve(self):
        request = self.runner["allocation_request"]("prefactor", {"matrix_payload_bytes": 1024, "workspace_bytes": 2048})
        self.assertEqual(request, (1024, 2048, 128 * 1024**2, 0))

    def test_remaining_factor_policy_uses_actual_retained_count(self):
        for retained in range(4):
            allowance = (4 - retained) * 128 * 1024**2
            request = self.runner["allocation_request"]("solve", {"retained_factor_count": retained,
                "factor_workspace_allowance_bytes": allowance, "LU_fill_and_workspace_unknown": True})
            self.assertEqual(request[-1], allowance)

    def test_factor_readding_full_allowance_after_first_factor_fails(self):
        with self.assertRaises(ValueError):
            self.runner["allocation_request"]("solve", {"retained_factor_count": 1,
                "factor_workspace_allowance_bytes": 512 * 1024**2, "LU_fill_and_workspace_unknown": True})

    def test_unknown_factor_fill_cannot_be_called_measured(self):
        with self.assertRaises(ValueError):
            self.runner["allocation_request"]("solve", {"retained_factor_count": 0,
                "factor_workspace_allowance_bytes": 512 * 1024**2})

    def test_stage_result_contract(self):
        for stage in ("prefactor", "solve"):
            self.assertTrue(self.runner["validate_worker_result"](self.candidate(stage), stage))

    def test_prefactor_rejects_hidden_pde_or_factor_or_sources(self):
        for key, value in (("factor_count", 1), ("PDE_solved", True), ("regular_sources", {"generic": {}})):
            report = self.candidate(); report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.runner["validate_worker_result"](report, "prefactor")

    def test_numeric_negative_is_preserved_on_resource_stop(self):
        report = {"status": "QUOTIENT_INVERSE_PROBE_FAILED"}
        self.runner["apply_supervisor_classification"](report, "MEMORY_CONTROLLED_STOP")
        self.assertEqual(report["status"], "QUOTIENT_INVERSE_PROBE_FAILED")

    def test_complete_metadata_inventories(self):
        for stage in ("prefactor", "solve"):
            self.assertTrue(self.checker["validate_array_inventory"](self.with_inventory(stage), stage))
            self.assertTrue(self.validate_metadata(*self.metadata(stage), stage=stage))

    def test_missing_mode_output_array_is_not_vacuous_pass(self):
        report = self.with_inventory("solve")
        report["artifacts"].pop("notch_physical_plane_electric")
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_missing_factor_result_array(self):
        report = self.with_inventory("solve"); report["artifacts"].pop("q_3_solution_sum")
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_missing_manufactured_port_load(self):
        report = self.with_inventory("solve"); report["artifacts"].pop("aug_q_2_port_rhs")
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_rebound_nonfinite_diagnostic_is_not_success(self):
        report = self.with_inventory("solve")
        report["artifacts"]["q_0_solution_a"].update(nonfinite_entries=1, raw_failure_diagnostic_only=True)
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_missing_branch(self):
        report = self.with_inventory(); report["reformed_blocks"].pop()
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "prefactor")

    def test_duplicate_branch(self):
        report = self.with_inventory(); report["reformed_blocks"][3]["q"] = 2
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "prefactor")

    def test_factor_input_hash_detached_from_fresh_block(self):
        report = self.with_inventory("solve"); report["factor"]["input_blocks"][1]["CSR_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_false_empty_factor_tests(self):
        report = self.with_inventory("solve"); report["factor"]["tests"] = []
        with self.assertRaises(ValueError):
            self.checker["validate_array_inventory"](report, "solve")

    def test_full_candidate_matrix_or_map_is_forbidden(self):
        for key in ("full_Q_data", "full_F_data", "reference_S_data"):
            report = self.with_inventory(); report["artifacts"][key] = {"shape": [1], "nonfinite_entries": 0,
                "raw_failure_diagnostic_only": False, "file_sha256": "a" * 64}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.checker["validate_array_inventory"](report, "prefactor")

    def test_false_source_or_environment_or_schema_binding(self):
        for field in ("source", "environment", "schema", "stage", "degree", "input_sha256"):
            report, provenance, source, environment = self.metadata()
            provenance[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate_metadata(report, provenance, source, environment)

    def test_false_manifest_binding(self):
        report, provenance, source, environment = self.metadata()
        rebound = deepcopy(report["artifacts"]); rebound.pop("q_3_S_data")
        with self.assertRaises(ValueError):
            self.checker["validate_metadata_bindings"](report, provenance, rebound,
                checker_source=source, checker_environment=environment, stage="prefactor")

    def test_wrong_abi(self):
        report, provenance, source, environment = self.metadata()
        environment["petsc_scalar_type"] = "float64"; provenance["environment"] = deepcopy(environment)
        with self.assertRaises(ValueError):
            self.validate_metadata(report, provenance, source, environment)

    def test_prefactor_cannot_claim_factor_allowance(self):
        report, provenance, source, environment = self.metadata()
        provenance["resource_contract"]["factor_workspace_allowance_bytes"] = 512 * 1024**2
        with self.assertRaises(ValueError):
            self.validate_metadata(report, provenance, source, environment)

    def test_missing_source_inventory(self):
        report, provenance, source, environment = self.metadata()
        source["files_sha256"] = {}; provenance["source"] = deepcopy(source)
        with self.assertRaises(ValueError):
            self.validate_metadata(report, provenance, source, environment)

    def test_finite_metrics_reject_nan_infinity_negative_and_bool(self):
        for value in (float("nan"), float("inf"), -1., True, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.checker["finite_gate"](value, 1e-10, "fixture")

    def test_new_raw_assembly_scope_flag_fails(self):
        report = self.candidate(); report["scope_flags"]["raw_port_reassembled"] = True
        with self.assertRaises(ValueError):
            self.checker["validate_scope"](report, "prefactor")

    def test_missing_source_dictionary_fails_solve(self):
        report = self.candidate("solve"); report["regular_sources"].pop("interior_only")
        with self.assertRaises(ValueError):
            self.checker["validate_scope"](report, "solve")

    def restoration_fixture(self):
        _, _, source, environment = self.metadata()
        authority = {"schema": "fixed-snapshot-authority", "restorer_source_sha256": "e" * 64}
        keys = [["top", i, 0, "s"] for i in range(532)]
        sectors, receipts = {}, []
        for twist, count, cells, rows, slaves in zip((None, 0, 1), (532, 228, 304), (80, 40, 40),
                                                   (17204, 8940, 8940), (1332, 1004, 1004)):
            identity = {"mode_count": count, "physical_generator_manifest_sha256": self.checker["PHYSICAL_MANIFEST"],
                        "assembly_mode_manifest_sha256": "d" * 64, "assembly_context_sha256": "e" * 64,
                        "carrier_numeric_sha256": "f" * 64, "ordered_mode_keys": [[i, *key] for i, key in enumerate(keys[:count])]}
            if twist is None:
                identity.update(assembly_context_sha256="40bef5d252789a12236b19feeb5f417e053c76cbab4cab3a2252138f45b894f5",
                    carrier_numeric_sha256="199d3bb28c624672d5d263877fa00c53909a1976fd69ae3e63a77bec11910cfd")
            else:
                sectors[str(twist)] = deepcopy(identity)
            receipts.append({"schema": "task40extra.qualified-quotient-snapshot-restoration.v1",
                "status": "RESTORED_EXACT_SNAPSHOT_NEW_VOLUME_UNQUALIFIED", "quotient_twist_index": twist,
                "authority": deepcopy(authority), "new_volume_source": deepcopy(source), "new_volume_environment": deepcopy(environment),
                "stored_D_second_conjugation": False, "packet_mmaps_released": True, "factor_count": 0, "PDE_solved": False,
                "expected_snapshot_identity": deepcopy(identity), "restored_public_carrier_identity": identity,
                "new_volume_audit": {"new_form": True}, "historical_raw_JIT_context_sha256": identity["assembly_context_sha256"],
                "historical_primary_surface_file_verification": self.historical_file_fixture(identity["assembly_context_sha256"]),
                "local_raw_receipt_sha256": None if twist is None else "c" * 64,
                "actual_discrete_binding": {"actual_cells": cells, "actual_storage_rows": rows, "actual_finalized_slave_rows": slaves,
                    "ABI_equal": True, "config_equal": True, "actual_source_sha256": {"old.py": "b" * 64}, "cell_dofmap_sha256": "a" * 64}})
        kwargs = {"authority_receipt": authority, "source": source, "environment": environment,
                  "sector_identities": sectors, "global_keys": keys}
        return receipts, kwargs

    def test_complete_restoration_metadata(self):
        receipts, kwargs = self.restoration_fixture()
        self.assertTrue(self.checker["validate_restoration_metadata"](receipts, **kwargs))

    def test_restoration_requires_three_complete_profiles(self):
        receipts, kwargs = self.restoration_fixture(); receipts.pop()
        with self.assertRaises(ValueError):
            self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_second_D_conjugation_or_historical_JIT_as_new_proof_fails(self):
        for field, value in (("stored_D_second_conjugation", True), ("new_volume_audit", {}),
                             ("packet_mmaps_released", False), ("factor_count", 1)):
            receipts, kwargs = self.restoration_fixture(); receipts[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_swapped_restoration_source_environment_or_authority(self):
        for field in ("new_volume_source", "new_volume_environment", "authority"):
            receipts, kwargs = self.restoration_fixture(); receipts[1][field] = {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_changed_global_digest_even_when_both_identity_copies_rebound(self):
        receipts, kwargs = self.restoration_fixture()
        for key in ("expected_snapshot_identity", "restored_public_carrier_identity"):
            receipts[0][key]["carrier_numeric_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_actual_source_binding_not_in_new_source_inventory(self):
        receipts, kwargs = self.restoration_fixture()
        receipts[1]["actual_discrete_binding"]["actual_source_sha256"]["old.py"] = "0" * 64
        with self.assertRaises(ValueError):
            self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_factor_test_nonfinite_or_failed_cannot_be_metadata_pass(self):
        for value in (float("nan"), 1e-4, "NONFINITE"):
            report = self.with_inventory("solve"); report["factor"]["tests"][0]["true_block_residual"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.checker["validate_array_inventory"](report, "solve")

    def event_fixture(self, stage="prefactor"):
        events = [{"event": "complete_recovery_identity_before_factor", "twist": b} for b in range(2)]
        events += [{"event": "rebuilt_q_block_compared_before_any_factor", "q": q,
                   "relative_frobenius_difference": 0., "relative_max_difference": 0., "CSR_sha256": str(q) * 64} for q in range(4)]
        if stage == "solve":
            for q in range(4):
                allowance = (4 - q) * 128 * 1024**2
                events.append({"event": "allocation_admission", "boundary": f"quotient_factor_q_{q}",
                    "facts": {"retained_factor_count": q, "factor_workspace_allowance_bytes": allowance,
                              "LU_fill_and_workspace_unknown": True}, "remaining_factor_allowance_bytes": allowance,
                    "admitted": True, "current_tree_rss_bytes": 1000, "additional_payload_bytes": 2000,
                    "declared_workspace_bytes": 3000, "evidence_reserve_bytes": self.checker["RESERVE_BYTES"],
                    "projected_tree_bytes": 6000 + allowance + self.checker["RESERVE_BYTES"],
                    "effective_tree_cap_bytes": self.checker["TREE_CAP_BYTES"]})
                events.append({"event": "all_branch_factor_created", "q": q, "factor_count": q + 1,
                               "retained_factor_count": q + 1, "input_CSR_sha256": str(q) * 64})
                events.append({"event": "all_branch_factor_retained", "q": q, "retained_factor_count": q + 1})
        return events

    def test_complete_prefactor_and_solve_event_contract(self):
        for stage in ("prefactor", "solve"):
            self.assertTrue(self.checker["validate_factor_event_contract"](self.event_fixture(stage), stage))

    def test_factor_before_last_comparison_fails(self):
        events = self.event_fixture("solve"); events[5], events[6] = events[6], events[5]
        with self.assertRaises(ValueError):
            self.checker["validate_factor_event_contract"](events, "solve")

    def test_wrong_remaining_allowance_or_unread_actual_rss_fails(self):
        for key, value in (("remaining_factor_allowance_bytes", 0), ("current_tree_rss_bytes", 0),
                           ("projected_tree_bytes", 1), ("admitted", False)):
            events = self.event_fixture("solve"); events[6][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.checker["validate_factor_event_contract"](events, "solve")

    def test_prefactor_cannot_hide_factor_or_solve_event(self):
        for name in ("all_branch_factor_test", "all_branch_factor_created", "all_branch_factor_retained", "original_augmented_manufactured_control"):
            events = self.event_fixture(); events.append({"event": name, "q": 0})
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.checker["validate_factor_event_contract"](events, "prefactor")

    def test_every_mode_uses_own_scale_and_zero_error_rule(self):
        scales = [1.] * 532; errors = [0.] * 532
        scales[411] = 1e-20; errors[411] = 1e-29
        self.assertAlmostEqual(self.checker["per_mode_operation_error"](errors, scales), 1e-9)
        scales[411] = 0.
        with self.assertRaises(ValueError):
            self.checker["per_mode_operation_error"](errors, scales)

    def test_missing_or_nonfinite_global_comparison_modes_fail(self):
        for errors, scales in (([0.] * 531, [1.] * 532), ([0.] * 532, [1.] * 531),
                               ([float("nan")] + [0.] * 531, [1.] * 532),
                               ([0.] * 532, [float("inf")] + [1.] * 531)):
            with self.assertRaises(ValueError):
                self.checker["per_mode_operation_error"](errors, scales)

    def recovery_fixture(self):
        tensors = {str(i): {"shape": [300, 300], "dtype": "complex128", "raw_sha256": "a" * 64,
                            "oriented_sha256": "b" * 64} for i in range(20)}
        old = {"key_dependencies": ["material", "basis"], "scope": "single builder invocation",
               "policy_signatures": {"actual_space": {"dimension": 300, "dtype": "complex128",
                                    "kernel_ids": [1, 2, 3], "ufcx_form_signature": "old-volume-JIT"}}}
        current = deepcopy(old); current["policy_signatures"]["actual_space"]["ufcx_form_signature"] = "new-primary-volume-JIT"
        historical = [{"action_only_complete_tensor_identities": deepcopy(tensors), "operator_cache_identity": deepcopy(old)} for b in range(2)]
        bindings = [{"twist": b, "native_row_inventory_equal": {key: True for key in
            ("independent_storage_rows", "trace_original_rows", "interior_original_rows", "slave_storage_rows")},
            "raw_oriented_tensor_inventory": deepcopy(tensors), "raw_oriented_tensor_exact_equal": True,
            "tensor_count": 20, "cache_recipe_equal": True, "new_cache_recipe": deepcopy(current),
            "historical_cache_recipe": deepcopy(old), "compiler_signatures": {"actual_space": {
                "historical": "old-volume-JIT", "new": "new-primary-volume-JIT"}},
            "new_volume_identity_claimed_equal_to_old_JIT": False} for b in range(2)]
        return bindings, historical

    def test_exact_recovery_bridge_allows_distinct_primary_volume_signature(self):
        self.assertTrue(self.checker["validate_recovery_identity_bindings"](*self.recovery_fixture()))

    def test_missing_tensor_or_false_native_row_or_changed_cache_recipe_fails(self):
        for field in ("tensor", "row", "recipe"):
            bindings, historical = self.recovery_fixture()
            if field == "tensor":
                bindings[0]["raw_oriented_tensor_inventory"].pop("19")
            elif field == "row":
                bindings[0]["native_row_inventory_equal"]["interior_original_rows"] = False
            else:
                bindings[0]["new_cache_recipe"]["policy_signatures"]["actual_space"]["dimension"] = 301
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.checker["validate_recovery_identity_bindings"](bindings, historical)

    def test_rebound_historical_tensor_cannot_rewrite_authority(self):
        bindings, historical = self.recovery_fixture()
        bindings[0]["raw_oriented_tensor_inventory"]["0"]["raw_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self.checker["validate_recovery_identity_bindings"](bindings, historical)

    def test_missing_recovery_receipt_or_after_factor_event_fails(self):
        events = self.event_fixture("solve"); events.pop(0)
        with self.assertRaises(ValueError):
            self.checker["validate_factor_event_contract"](events, "solve")

    def historical_file_fixture(self, context_sha="a" * 64):
        records = {}
        for name in ("top/0", "top/1", "bottom/0", "bottom/1"):
            records[name] = {}
            for role in ("binary", "generated_C"):
                path = str(Path("/tmp/fixture_" + name.replace("/", "_") + "_" + role).resolve())
                records[name][role] = {"recorded_path": path, "resolved_path": path,
                    "expected_sha256": "a" * 64, "verified_sha256": "a" * 64, "verified_bytes": 100}
        return {"schema": "task40extra.historical-primary-surface-file-verification.v1",
                "status": "VERIFIED_HISTORICAL_FILES_ONLY", "verified_primary_gauss_records": 4,
                "verified_file_references": 8, "assembly_context_sha256": context_sha,
                "read_chunk_upper_bytes": 1 << 20, "historical_kernel_provenance_retained": True,
                "modules_loaded": False, "new_JIT_performed": False, "new_volume_kernel_qualified": False,
                "records": records}

    def test_complete_historical_file_receipts(self):
        self.assertTrue(self.checker["validate_historical_file_metadata"](self.historical_file_fixture(), context_sha="a" * 64))

    def test_historical_file_receipt_missing_hash_or_false_scope_fails(self):
        for field in ("missing", "hash", "scope", "context"):
            verification = self.historical_file_fixture()
            if field == "missing":
                verification["records"]["top/0"].pop("generated_C")
            elif field == "hash":
                verification["records"]["top/0"]["binary"]["verified_sha256"] = "b" * 64
            elif field == "scope":
                verification["new_volume_kernel_qualified"] = True
            else:
                verification["assembly_context_sha256"] = "c" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.checker["validate_historical_file_metadata"](verification, context_sha="a" * 64)

    def test_missing_restoration_historical_file_gate_fails(self):
        receipts, kwargs = self.restoration_fixture(); receipts[0].pop("historical_primary_surface_file_verification")
        with self.assertRaises(ValueError):
            self.checker["validate_restoration_metadata"](receipts, **kwargs)

    def test_checker_has_no_solve_factor_or_rebuild_call(self):
        tree = ast.parse(CHECKER.read_text())
        forbidden = {"splu", "solve", "restore_bundle", "build_same_mesh_physical_action",
                     "qualify_quotient_raw_bundle", "build_quotient_condensed"}
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                 for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, (ast.Name, ast.Attribute))}
        self.assertFalse(calls & forbidden)

    def test_no_project_module_at_top_level(self):
        for path in (RUNNER, CHECKER):
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(("src", "benchmarks", "numpy", "scipy")))
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith(("src", "benchmarks", "numpy", "scipy")) for alias in node.names))


if __name__ == "__main__":
    unittest.main()
