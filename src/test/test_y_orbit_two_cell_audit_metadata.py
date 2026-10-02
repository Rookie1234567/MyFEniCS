"""Isolated AST-extracted metadata negatives; never imports project modules."""
import ast
import cmath
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import unittest


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        source = root / "benchmarks/y_orbit_two_cell_authority.py"
        tree = ast.parse(source.read_text())
        keep = {"digest_json", "dependency_diff", "validate_old_metadata", "validate_supervision", "bound_path"}
        body = [node for node in tree.body if isinstance(node, ast.Assign)
                or isinstance(node, ast.FunctionDef) and node.name in keep]
        cls.scope = {"hashlib": hashlib, "json": json, "math": math, "Path": Path}
        exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), cls.scope)
        # Locate the canonical immutable JSON metadata, never its arrays.
        cloud = next(p for p in source.parents if (p / "repo/AGENTS.md").is_file())
        directory = cloud / "repo/benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_centered_attempt1"
        cls.report = json.loads((directory / "probe_report.json").read_text())
        cls.checker = json.loads((directory / "independent_checker.json").read_text())
        cls.provenance = json.loads((directory / "provenance.json").read_text())
        cls.new_source = deepcopy(cls.report["source"])
        cls.new_source["head"] = "26776386d1245572b3d693a905b608c16c870e5e"
        cls.new_source["files_sha256"]["src/solvers/y_orbit_two_cell_audit.py"] = "f" * 64
        cls.environment = deepcopy(cls.report["environment"])
        checker_path = root / "benchmarks/check_y_orbit_two_cell_audit.py"
        checker_tree = ast.parse(checker_path.read_text())
        checker_body = [node for node in checker_tree.body if isinstance(node, ast.Assign)
                        or isinstance(node, ast.FunctionDef) and node.name in
                        {"number", "expected_sector_keys", "validate_local_row_partition",
                         "validate_bound_array_signature", "validate_raw_transport_ledger", "validate_candidate_inventory"}]
        cls.scope["cmath"] = cmath
        exec(compile(ast.Module(body=checker_body, type_ignores=[]), str(checker_path), "exec"), cls.scope)
        runner_path = root / "benchmarks/run_y_orbit_two_cell_audit.py"
        runner_tree = ast.parse(runner_path.read_text())
        runner_body = [node for node in runner_tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "apply_supervisor_classification"]
        exec(compile(ast.Module(body=runner_body, type_ignores=[]), str(runner_path), "exec"), cls.scope)

    def candidate(self):
        keys = self.report["mode_keys"]
        phase = complex(*self.report["layout"]["phase_y"])
        twists = []
        for b in range(2):
            theta = (cmath.phase(phase) + 2 * math.pi * b) / 4
            eta = cmath.exp(1j * theta)
            indices = [i for i, key in enumerate(keys) if key[2] % 2 == b]
            branches = [{"local_branch": a, "q": b + 2 * a,
                         "shape": [self.scope["Q_ROWS"][b + 2 * a]] * 2,
                         "csr_prefix": f"q_{b + 2 * a}_S",
                         "original_mode_indices": [i for i in indices if ((keys[i][2] - b) // 2) % 2 == a]}
                        for a in range(2)]
            twists.append({"b": b, "theta": theta, "eta": [eta.real, eta.imag],
                           "tau": [(eta**2).real, (eta**2).imag], "sector_original_indices": indices,
                           "branches": branches, "local_original_H_artifact": f"twist_{b}_original_H",
                           "original_action_witness": {"twist": b, "local_FE_rows": 7936,
                               "all_local_interior_rows": 4320, "global_FE_rows": 15872,
                               "q_factors_used": False, "volume_and_DtN_original_action": True,
                               "relative_original_FE_action_defect": 0.0},
                           "complete_interior_port_recovery_witness": {"twist": b, "all_interior_rows": 4320,
                               "arbitrary_interior_rhs_nonzero_count": 4320, "strict_slave_zero": True,
                               "global_and_q_factors": 0, "inherited_cell_interior_LU_used": True,
                               "port_rhs_norm": 1.0, "reduced_original_augmented_action_defect": 0.0,
                               "full_original_storage_recovery_defect": 0.0}})
        cross = [{"p": p, "q": q, "shape": [self.scope["Q_ROWS"][p], self.scope["Q_ROWS"][q]],
                  "csr_prefix": f"cross_{p}_{q}", "scope": "local_twist" if p % 2 == q % 2 else "full_original_action"}
                 for p in range(4) for q in range(4) if p != q]
        artifacts = {f"q_{q}_S_{part}": {} for q in range(4) for part in ("data", "indices", "indptr")}
        artifacts.update({f"q_{q}_map_{part}": {} for q in range(4)
                          for part in ("column_error_norms", "reference_column_norms")})
        artifacts.update({f"folded_masked_port_{side}_{part}": {} for side in ("C", "D")
                          for part in ("data", "indices", "indptr")})
        artifacts.update({f"cross_{p}_{q}_{part}": {} for p in range(4) for q in range(4) if p != q
                          for part in ("data", "indices", "indptr")})
        artifacts.update({f"twist_{b}_original_H": {} for b in range(2)})
        for b in range(2):
            mode_count = (228, 304)[b]
            artifacts.update({f"twist_{b}_original_action_{name}": {"shape": [size]} for name, size in
                              (("local", 7936), ("folded", 7936), ("local_state", 7936), ("global_state", 15872))})
            artifacts.update({f"twist_{b}_complete_recovery_{name}": {"shape": [size]} for name, size in
                              (("state", 8940), ("alpha", mode_count), ("FE_rhs", 8940), ("port_rhs", mode_count),
                               ("reduced_rhs", 3616 + mode_count), ("reduced_action", 3616 + mode_count), ("recovered", 8940))})
            artifacts.update({f"twist_{b}_{name}": {"shape": [size]} for name, size in
                              (("independent_storage_rows", 7936), ("trace_original_rows", 3616),
                               ("interior_original_rows", 4320), ("slave_storage_rows", 1004))})
        return {"schema": self.scope["SCHEMA"], "status": self.scope["PASS"], "degree": 4,
                "factor_count": 0, "audit_only": True, "PDE_solved": False, "official_results": False,
                "source_clean_unchanged": True, "physical_generator_manifest_sha256": self.scope["PHYSICAL_MANIFEST"],
                "global_mode_keys": keys, "twists": twists, "cross_branch_blocks": cross, "artifacts": artifacts,
                "raw_fold_per_mode": self.raw_ledger()}

    def raw_ledger(self):
        return [{"original_mode_index": i, **{f"raw_{side}_{direction}_{field}": value
                 for side in ("C", "D") for direction in ("fold", "lift")
                 for field, value in (("error_norm", 0.0), ("operation_scale", 1.0))}} for i in range(532)]

    def local_rows(self):
        return [list(range(7936)), list(range(3616)), list(range(3616, 7936)), list(range(7936, 8940))]

    def check_candidate(self, candidate):
        return self.scope["validate_candidate_inventory"](candidate, self.report)

    def validate(self, report=None, checker=None, provenance=None, source=None, environment=None):
        return self.scope["validate_old_metadata"](
            report or self.report, checker or self.checker, provenance or self.provenance,
            new_source=source or self.new_source, new_environment=environment or self.environment)

    def test_distinct_old_new_diff_keeps_every_path(self):
        difference = self.validate()
        self.assertFalse(difference["source_equality_claimed"])
        self.assertEqual(len(difference["all_dependencies"]), len(self.new_source["files_sha256"]))
        self.assertIn("src/solvers/y_orbit_two_cell_audit.py", difference["changed_paths"])

    def test_stale_swapped_report_hash(self):
        checker = deepcopy(self.checker)
        checker["report_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.validate(checker=checker)

    def test_stale_swapped_provenance_hash(self):
        checker = deepcopy(self.checker)
        checker["provenance_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.validate(checker=checker)

    def test_stale_swapped_source(self):
        checker = deepcopy(self.checker)
        checker["checker_source"]["head"] = self.new_source["head"]
        with self.assertRaises(ValueError):
            self.validate(checker=checker)

    def test_wrong_degree(self):
        report = deepcopy(self.report)
        report["degree"] = 2
        with self.assertRaises(ValueError):
            self.validate(report=report)

    def test_missing_branch(self):
        report = deepcopy(self.report)
        report["reference_factor"]["input_blocks"].pop()
        with self.assertRaises(ValueError):
            self.validate(report=report)

    def test_missing_q_array_despite_rebound_manifest(self):
        report, checker = deepcopy(self.report), deepcopy(self.checker)
        report["artifacts"].pop("q_3_S_indptr")
        checker["artifact_manifest_sha256"] = self.scope["digest_json"](report["artifacts"])
        with self.assertRaises(ValueError):
            self.validate(report=report, checker=checker)

    def test_stale_checker_gate_list(self):
        checker = deepcopy(self.checker)
        checker["checks"].pop()
        with self.assertRaises(ValueError):
            self.validate(checker=checker)

    def test_wrong_abi(self):
        environment = deepcopy(self.environment)
        environment["petsc_scalar_type"] = "float64"
        with self.assertRaises(ValueError):
            self.validate(environment=environment)

    def test_source_equality_is_not_a_bridge(self):
        with self.assertRaises(ValueError):
            self.validate(source=self.report["source"])

    def test_changed_deleted_added_dependency_inventory(self):
        source = deepcopy(self.new_source)
        paths = list(source["files_sha256"])
        deleted, changed = paths[:2]
        source["files_sha256"].pop(deleted)
        source["files_sha256"][changed] = "e" * 64
        records = {v["path"]: v for v in self.validate(source=source)["all_dependencies"]}
        self.assertEqual(records[deleted]["relation"], "deleted")
        self.assertEqual(records[changed]["relation"], "changed")
        self.assertEqual(records["src/solvers/y_orbit_two_cell_audit.py"]["relation"], "added")

    def test_complete_candidate_metadata(self):
        self.assertTrue(self.check_candidate(self.candidate()))

    def test_candidate_missing_twist(self):
        candidate = self.candidate()
        candidate["twists"].pop()
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_missing_branch(self):
        candidate = self.candidate()
        candidate["twists"][1]["branches"].pop()
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_missing_csr_array(self):
        candidate = self.candidate()
        candidate["artifacts"].pop("q_3_S_data")
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_missing_cross_pair(self):
        candidate = self.candidate()
        candidate["cross_branch_blocks"].pop()
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_wrong_eta_branch(self):
        candidate = self.candidate()
        candidate["twists"][1]["eta"] = candidate["twists"][0]["eta"]
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_duplicate_global_mode(self):
        candidate = self.candidate()
        candidate["global_mode_keys"] = deepcopy(candidate["global_mode_keys"])
        candidate["global_mode_keys"][-1] = candidate["global_mode_keys"][0]
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_candidate_factor_scope_rejected(self):
        candidate = self.candidate()
        candidate["factor_count"] = 1
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_numerical_failure_is_not_a_resource_stop(self):
        report = {"status": "QUOTIENT_OPERATOR_AUDIT_FAILED", "error": "actual map negative"}
        result = self.scope["apply_supervisor_classification"](report, "WORKER_FAILED")
        self.assertEqual(result["status"], "QUOTIENT_OPERATOR_AUDIT_FAILED")
        self.assertEqual(result["error"], "actual map negative")

    def test_resource_stop_preserves_original_worker_status(self):
        result = self.scope["apply_supervisor_classification"]({"status": "STARTED"}, "RESOURCE_CONTROLLED_STOP")
        self.assertEqual(result["status"], "QUOTIENT_OPERATOR_AUDIT_CONTROLLED_STOP")
        self.assertEqual(result["worker_status_before_supervisor_classification"], "STARTED")

    def test_monitor_failure_is_distinct(self):
        result = self.scope["apply_supervisor_classification"]({"status": "STARTED"}, "MONITORING_FAILED")
        self.assertEqual(result["status"], "QUOTIENT_OPERATOR_AUDIT_SUPERVISION_FAILED")

    def test_raw_receipt_keys_have_four_fields_and_separate_indices(self):
        keys = self.report["mode_keys"]
        indices = [i for i, key in enumerate(keys) if key[2] % 2 == 1]
        actual = self.scope["expected_sector_keys"](keys, indices)
        self.assertEqual(actual, [keys[i] for i in indices])
        self.assertTrue(all(len(key) == 4 for key in actual))

    def test_index_prefixed_raw_key_rejected(self):
        keys = deepcopy(self.report["mode_keys"])
        keys[0] = [0, *keys[0]]
        with self.assertRaises(ValueError):
            self.scope["expected_sector_keys"](keys, [0])

    def test_missing_actual_action_witness(self):
        candidate = self.candidate()
        candidate["twists"][1].pop("original_action_witness")
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_missing_recovery_witness_array(self):
        candidate = self.candidate()
        candidate["artifacts"].pop("twist_0_complete_recovery_FE_rhs")
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_missing_native_row_map(self):
        candidate = self.candidate()
        candidate["artifacts"].pop("twist_1_trace_original_rows")
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_wrong_witness_shape(self):
        candidate = self.candidate()
        candidate["artifacts"]["twist_1_complete_recovery_port_rhs"]["shape"] = [228]
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_partial_interior_load_metadata(self):
        candidate = self.candidate()
        candidate["twists"][0]["complete_interior_port_recovery_witness"]["arbitrary_interior_rhs_nonzero_count"] = 4319
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_zero_port_rhs_metadata(self):
        candidate = self.candidate()
        candidate["twists"][0]["complete_interior_port_recovery_witness"]["port_rhs_norm"] = 0.0
        with self.assertRaises(ValueError):
            self.check_candidate(candidate)

    def test_exact_native_row_partition(self):
        self.assertTrue(self.scope["validate_local_row_partition"](*self.local_rows()))

    def test_reordered_independent_map(self):
        rows = self.local_rows()
        rows[0][0], rows[0][1] = rows[0][1], rows[0][0]
        with self.assertRaises(ValueError):
            self.scope["validate_local_row_partition"](*rows)

    def test_reordered_trace_map(self):
        rows = self.local_rows()
        rows[1][0], rows[1][1] = rows[1][1], rows[1][0]
        with self.assertRaises(ValueError):
            self.scope["validate_local_row_partition"](*rows)

    def test_interior_cell_iterator_order_is_not_assumed_sorted(self):
        rows = self.local_rows()
        rows[2].reverse()
        self.assertTrue(self.scope["validate_local_row_partition"](*rows))

    def test_duplicate_native_map_row(self):
        rows = self.local_rows()
        rows[2][-1] = rows[2][0]
        with self.assertRaises(ValueError):
            self.scope["validate_local_row_partition"](*rows)

    def test_changed_slave_signature(self):
        signature = {"shape": [1004], "dtype": "int32", "sha256": "a" * 64}
        actual = {**signature, "sha256": "b" * 64}
        with self.assertRaises(ValueError):
            self.scope["validate_bound_array_signature"](actual, signature)

    def test_slave_dtype_cast_rejected(self):
        signature = {"shape": [1004], "dtype": "int32", "sha256": "a" * 64}
        actual = {**signature, "dtype": "int64"}
        with self.assertRaises(ValueError):
            self.scope["validate_bound_array_signature"](actual, signature)

    def test_all532_both_raw_transport_directions(self):
        self.assertTrue(self.scope["validate_raw_transport_ledger"](self.raw_ledger()))

    def test_missing_raw_lift_witness(self):
        rows = self.raw_ledger()
        rows[531].pop("raw_D_lift_error_norm")
        with self.assertRaises(ValueError):
            self.scope["validate_raw_transport_ledger"](rows)

    def test_nonfinite_raw_lift(self):
        rows = self.raw_ledger()
        rows[300]["raw_C_lift_error_norm"] = math.nan
        with self.assertRaises(ValueError):
            self.scope["validate_raw_transport_ledger"](rows)

    def test_zero_raw_lift_scale(self):
        rows = self.raw_ledger()
        rows[2]["raw_D_lift_operation_scale"] = 0.0
        with self.assertRaises(ValueError):
            self.scope["validate_raw_transport_ledger"](rows)

    def test_raw_lift_negative(self):
        rows = self.raw_ledger()
        rows[100]["raw_C_lift_error_norm"] = 2e-10
        with self.assertRaises(ValueError):
            self.scope["validate_raw_transport_ledger"](rows)


if __name__ == "__main__":
    unittest.main()
