"""Pure stdlib negative metadata tests; no FE/numerical module imports."""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if ROOT.name == "pipeline":
    CHECKER = ROOT / "benchmarks/check_y_orbit_direct_probe.py"
else:
    CHECKER = ROOT / "benchmarks/check_y_orbit_direct_probe.py"
spec = importlib.util.spec_from_file_location("_direct_pipeline_metadata_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def profile():
    scale = 7 / 135
    axes = [[v*scale for v in axis] for axis in
        ((0, 8.25, 16.5, 25, 33.5, 41.75, 50), (0, 6.25, 12.5, 18.75, 25), (-10, 0, 40, 80, 120, 130))]
    return {"name": "X", "dimensions": [6, 4, 5], "global_axes": axes,
        "local_axes": [axes[0], axes[1][:3], axes[2]], "replication_count": 2, "local_y_cells": 2,
        "cell_count": 120, "storage_rows": 25468, "independent_rows": 23808, "interior_rows": 12960,
        "trace_rows": 10848, "rows_per_q": 5952, "trace_rows_per_q": 2712, "local_cell_count": 60,
        "local_storage_rows": 13236, "local_independent_rows": 11904, "local_interior_rows": 6480,
        "local_trace_rows": 5424, "q_port_counts": [76, 152, 152, 152], "sector_port_counts": [228, 304],
        "augmented_rows_per_q": [2788, 2864, 2864, 2864], "physical_mode_count": 532,
        "complete_cell_dimension": 300, "complete_cell_interior_dimension": 108,
        "factor_allowance_per_q_bytes": 128*1024**2, "factor_allowance_aggregate_bytes": 512*1024**2,
        "evidence_reserve_bytes": 128*1024**2}


def report(stage="prefactor"):
    blocks = [{"q": q, "shape": [n, n], "nnz": 3, "csr_prefix": f"q_{q}_S", "CSR_sha256": "a"*64}
              for q, n in enumerate(checker.Q_ROWS)]
    providers = []
    for b in range(2):
        for p in range(2):
            for q in range(2):
                gp, gq = b+2*p, b+2*q
                providers.append({"twist": b, "p": p, "q": q, "global_p": gp, "global_q": gq,
                    "shape": [checker.Q_ROWS[gp], checker.Q_ROWS[gq]], "nnz": 3 if p == q else 0,
                    "csr_prefix": f"direct_twist_{b}_block_{p}_{q}", "CSR_sha256": "a"*64})
    value = {"schema": checker.SCHEMA, "direct_profile": "X", "profile": profile(), "stage": stage,
        "status": checker.PASSES[stage], "degree": 4, "physical_mode_count": 532, "source_clean_unchanged": True,
        "official_results": False, "prefactor_only": stage == "prefactor", "PDE_solved": stage == "solve",
        "factor_count": 0 if stage == "prefactor" else 4, "input_sha256": checker.INPUT_SHA,
        "physical_generator_manifest_sha256": checker.PHYSICAL_MANIFEST, "shared_transforms": True,
        "scope_flags": {"full_layout_entity_stream": True, "fresh_global_and_local_carriers": True,
            "snapshots_reused": False, "candidate_full_Ny_CSR_created": False, "candidate_full_F_created": False,
            "candidate_full_Q_created": False, "candidate_global_FE_square_matrix_created": False,
            "performance_or_target_capacity_claim": False}, "reformed_blocks": blocks, "direct_provider_blocks": providers,
        "original_operator_qualification": {"metadata_witness": "original_complete"},
        "fresh_carrier_qualification": {"metadata_witness": "fresh_complete"}}
    if stage == "solve":
        value.update(factor={"input_blocks": copy.deepcopy(blocks),
            "tests": [{"q": q, "true_block_residual": 0., "repeated_difference": 0., "linearity_difference": 0.} for q in range(4)],
            "all_reformed_blocks_compared_before_factor": True, "all_four_retained_simultaneously": True},
            regular_sources={name: {} for name in checker.SOURCES}, notched_sources={name: {} for name in checker.SOURCES},
            sampled_right_PC_defect={name: .001 for name in checker.SOURCES}, PC_defect_is_norm_bound=False,
            target_geometry_accuracy=False, no_2TB_or_48h_claim=True, changed_cells=[0, 1], sampled_notch_off_q_delta_relative=.01)
    return value


def artifacts(value, stage):
    shapes = checker.expected_array_shapes(value, stage)
    shapes.update({name: [2] for name in ("full_mpc_masters", "full_mpc_coefficients", "original_port_C_data",
        "original_port_C_indices", "original_port_D_data", "original_port_D_indices")})
    return {name: {"path": name+".npy", "file_sha256": "f"*64, "shape": shape, "dtype": "complex128",
        "payload_bytes": 16*__import__("math").prod(shape), "finite_entries": __import__("math").prod(shape),
        "nonfinite_entries": 0} for name, shape in shapes.items()}


def provenance(value):
    source = {"head": "a"*40, "branch": "task40extra_dot_parallel_cloud", "dirty": "",
              "files_sha256": {"benchmarks/check_y_orbit_direct_probe.py": "b"*64}}
    environment = {"petsc_scalar_type": "complex128", "qualification_manifest_sha256": "c"*64}
    value.update(source=source, environment=environment)
    stage = value["stage"]
    return {"source": source, "environment": environment, "schema": checker.SCHEMA, "direct_profile": "X",
        "stage": stage, "degree": 4, "input_sha256": checker.INPUT_SHA, "command": ["run.py", "--direct-profile", "X"],
        "resource_contract": {"stage": stage, "wall_seconds": 600, "swap_bytes": 0, "mpi": 1, "math_threads": 1,
            "tree_cap_bytes": checker.TREE_CAP_BYTES, "evidence_reserve_bytes": checker.RESERVE_BYTES,
            "factor_workspace_allowance_bytes": 0 if stage == "prefactor" else checker.FACTOR_ALLOWANCE_BYTES,
            "factor_fill_and_temporary_workspace_unknown": True, "factor_L_U_statistics_copies_permitted": False,
            "performance_or_target_capacity_claim": False}}


def events(value, stage):
    result = [{"event": name} for name in ("direct_fresh_carrier_qualification_complete",
        "direct_complete_original_operator_qualification", "shared_complete_equivalence_before_any_factor")]
    result.append({"event": "direct_complete_original_qualification_before_any_factor",
        "operator_receipt": value["original_operator_qualification"], "fresh_carrier_receipt": value["fresh_carrier_qualification"],
        "input_blocks": value["reformed_blocks"], "factor_count": 0})
    if stage == "solve":
        for q in range(4):
            actual = sum(value["artifacts"][f"q_{q}_S_{key}"]["payload_bytes"] for key in ("data", "indices", "indptr"))
            allowance = (4-q)*128*1024**2
            result.extend([{"event": "allocation_admission", "boundary": f"quotient_factor_q_{q}", "admitted": True,
                "facts": {"retained_factor_count": q, "LU_fill_and_workspace_unknown": True,
                    "factor_workspace_allowance_bytes": allowance}, "remaining_factor_allowance_bytes": allowance,
                "current_tree_rss_bytes": 10**6, "additional_payload_bytes": 3*actual, "declared_workspace_bytes": 2*actual,
                "evidence_reserve_bytes": checker.RESERVE_BYTES,
                "projected_tree_bytes": 10**6+5*actual+allowance+checker.RESERVE_BYTES,
                "effective_tree_cap_bytes": checker.TREE_CAP_BYTES},
                {"event": "all_branch_factor_created", "q": q, "factor_count": q+1, "retained_factor_count": q+1,
                    "input_CSR_sha256": value["reformed_blocks"][q]["CSR_sha256"]},
                {"event": "all_branch_factor_retained", "q": q, "retained_factor_count": q+1}])
    return result


class DirectPipelineMetadataTests(unittest.TestCase):
    def test_profile_exact_and_nonvacuous(self):
        self.assertTrue(checker.validate_profile(profile()))
        for key, bad in (("name", "XZ"), ("name", "Y"), ("cell_count", 80), ("interior_rows", 8640),
                         ("q_port_counts", [76, 76, 76, 76]), ("local_storage_rows", 8940), ("rows_per_q", 3968)):
            value = profile(); value[key] = bad
            with self.assertRaises(ValueError): checker.validate_profile(value)
        for value in ({}, None):
            with self.assertRaises(ValueError): checker.validate_profile(value)

    def test_scope_prefactor_and_solve_boundaries(self):
        for stage in checker.PASSES:
            self.assertTrue(checker.validate_scope(report(stage), stage))
        for key, bad in (("direct_profile", "Y"), ("degree", 2), ("physical_mode_count", 80),
                         ("source_clean_unchanged", False), ("shared_transforms", False), ("official_results", True),
                         ("factor_count", 1), ("regular_sources", {"generic": {}})):
            value = report(); value[key] = bad
            with self.assertRaises(ValueError): checker.validate_scope(value, "prefactor")
        value = report("solve"); value["sampled_right_PC_defect"]["generic"] = float("nan")
        with self.assertRaises(ValueError): checker.validate_scope(value, "solve")

    def test_manifest_missing_nonfinite_wrongshape_or_byte_count(self):
        value = report(); value["artifacts"] = artifacts(value, "prefactor")
        self.assertTrue(checker.validate_array_inventory(value, "prefactor"))
        for key, bad in (("shape", [23807]), ("payload_bytes", 0), ("finite_entries", 0),
                         ("nonfinite_entries", 1), ("dtype", "object"), ("file_sha256", "")):
            changed = copy.deepcopy(value); changed["artifacts"]["independent_storage_rows"][key] = bad
            with self.assertRaises(ValueError): checker.validate_array_inventory(changed, "prefactor")
        value["artifacts"].pop("actual_interior_positions")
        with self.assertRaises(ValueError): checker.validate_array_inventory(value, "prefactor")

    def test_all_q_and_provider_pairs_required(self):
        value = report("solve"); shapes = checker.expected_array_shapes(value, "solve")
        self.assertEqual(shapes["q_0_rhs_a"], [2788])
        self.assertEqual(shapes["aug_q_3_FE_rhs"], [23808])
        self.assertEqual(shapes["notch_physical_solution_storage"], [25468])
        self.assertEqual(shapes["regular_interior_only_recovered_field"], [25468])
        for key in ("direct_provider_blocks", "reformed_blocks"):
            changed = copy.deepcopy(value); changed[key].pop()
            with self.assertRaises(ValueError): checker.expected_array_shapes(changed, "solve")
        changed = copy.deepcopy(value); changed["factor"]["input_blocks"][0]["CSR_sha256"] = "c"*64
        with self.assertRaises(ValueError): checker.expected_array_shapes(changed, "solve")

    def test_exact_same_source_abi_and_resource_contract(self):
        value = report(); value["artifacts"] = artifacts(value, "prefactor"); prior = provenance(value)
        kwargs = {"checker_source": value["source"], "checker_environment": value["environment"], "stage": "prefactor"}
        self.assertTrue(checker.validate_metadata_bindings(value, prior, value["artifacts"], **kwargs))
        for key, bad in (("mpi", 2), ("swap_bytes", 1), ("math_threads", 2), ("wall_seconds", 601),
                         ("factor_L_U_statistics_copies_permitted", True)):
            changed = copy.deepcopy(prior); changed["resource_contract"][key] = bad
            with self.assertRaises(ValueError): checker.validate_metadata_bindings(value, changed, value["artifacts"], **kwargs)
        changed = copy.deepcopy(prior); changed["source"]["head"] = "d"*40
        with self.assertRaises(ValueError): checker.validate_metadata_bindings(value, changed, value["artifacts"], **kwargs)
        changed = copy.deepcopy(value); changed["source"]["dirty"] = " M benchmarks/check_y_orbit_direct_probe.py"
        dirty_prior = copy.deepcopy(prior); dirty_prior["source"] = changed["source"]
        with self.assertRaises(ValueError):
            checker.validate_metadata_bindings(changed, dirty_prior, changed["artifacts"],
                checker_source=changed["source"], checker_environment=changed["environment"], stage="prefactor")
        changed = copy.deepcopy(prior); changed["environment"]["petsc_scalar_type"] = "float64"
        with self.assertRaises(ValueError): checker.validate_metadata_bindings(value, changed, value["artifacts"], **kwargs)

    def test_event_order_all_four_actual_csr_and_retention(self):
        for stage in checker.PASSES:
            value = report(stage); value["artifacts"] = artifacts(value, stage)
            self.assertTrue(checker.validate_direct_event_contract(events(value, stage), value, stage))
        value = report("solve"); value["artifacts"] = artifacts(value, "solve"); actual = events(value, "solve")
        for mutation in ("missing", "early", "different_carrier", "wrong_bytes", "no_retention", "over_cap", "wrong_hash"):
            changed = copy.deepcopy(actual)
            if mutation == "missing": changed.pop(0)
            elif mutation == "early": changed[0], changed[4] = changed[4], changed[0]
            elif mutation == "different_carrier": changed[3]["fresh_carrier_receipt"] = {}
            elif mutation == "wrong_bytes": changed[4]["additional_payload_bytes"] += 1
            elif mutation == "no_retention": changed.pop(6)
            elif mutation == "over_cap": changed[4]["effective_tree_cap_bytes"] = changed[4]["projected_tree_bytes"]
            else: changed[5]["input_CSR_sha256"] = "f"*64
            with self.assertRaises(ValueError): checker.validate_direct_event_contract(changed, value, "solve")

    def test_complete_finite_spool_alias_inventory(self):
        for literal in (False, True):
            value = {"schema": "task40extra.direct-literal-current-mode-spool.v1" if literal else "task40extra.lossless-raw-packet-spool.v1",
                "status": "READY_LITERAL_CONTROLS_UNQUALIFIED" if literal else "READY_RAW_PACKETS_UNQUALIFIED",
                "expected_mode_count": 2, "recorded_mode_count": 2, "factor_count": 0, "PDE_solved": False,
                "records": [{"local_mode_index": j, "original_mode_index": j, "all_finite": True} for j in range(2)],
                "original_mode_indices": [0, 1], "ownership_range": [0, 25468], "literal_controls_qualified": False,
                "all_mode_dense_cache": False, "raw_port_qualified": False, "complete_finite_stream": True,
                "all_finite": True, "failure": None, "direct_profile_metadata": profile()}
            kwargs = dict(literal=literal, count=2, indices=[0, 1], storage=25468, profile=profile())
            self.assertTrue(checker.validate_spool_manifest(value, **kwargs))
            for mutation in ("duplicate", "missing", "passed_as_control"):
                changed = copy.deepcopy(value)
                if mutation == "duplicate": changed["records"][1]["original_mode_index"] = 0
                elif mutation == "missing": changed["records"].pop()
                else: changed["status"] = "PASS"
                with self.assertRaises(ValueError): checker.validate_spool_manifest(changed, **kwargs)

    def test_same_live_carrier_chain_cannot_drift(self):
        value = report()
        current = {"global": {"numeric_sha256": "g"*64}, "local": [{"numeric_sha256": "a"*64}, {"numeric_sha256": "b"*64}]}
        value["fresh_carrier_qualification"].update(global_carrier_identity_before=current["global"],
            global_carrier_identity_after=current["global"], local_carrier_identities=current["local"])
        value.update(same_live_carrier_identity_before_factor=current, same_live_carrier_identity_at_exit=current)
        actual = [{"event": "direct_same_live_carrier_identity", "boundary": "before_all_q_factors",
            "actual": current, "expected": current, "unchanged": True},
            {"event": "direct_complete_original_qualification_before_any_factor"},
            {"event": "direct_same_live_carrier_identity", "boundary": "before_successful_exit",
             "actual": current, "expected": current, "unchanged": True}]
        self.assertTrue(checker.validate_same_live_carrier_chain(actual, value))
        changed = copy.deepcopy(actual); changed[2]["actual"]["local"][1]["numeric_sha256"] = "c"*64
        with self.assertRaises(ValueError): checker.validate_same_live_carrier_chain(changed, value)
        with self.assertRaises(ValueError): checker.validate_same_live_carrier_chain(actual[:-1], value)
        changed = copy.deepcopy(actual); changed[0], changed[1] = changed[1], changed[0]
        with self.assertRaises(ValueError): checker.validate_same_live_carrier_chain(changed, value)

    def test_actual_gauss_kernel_file_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, generated = Path(temporary)/"current.so", Path(temporary)/"current.c"
            binary.write_text("metadata-only kernel witness"); generated.write_text("metadata-only C witness")
            kernel = {"schema": "task40extra.loaded-surface-kernel.v1", "module_path": str(binary),
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "module_bound_C_path": str(generated),
                "module_bound_C_sha256": hashlib.sha256(generated.read_bytes()).hexdigest()}
            rule = {"degree": 23, "facet_cell": "quadrilateral", "integral_type": "exterior_facet",
                "points": {"shape": [144, 2], "dtype": "float64"}, "weights": {"shape": [144], "dtype": "float64"}}
            primary = {name: {"rules": [copy.deepcopy(rule)], "loaded_kernel": copy.deepcopy(kernel)}
                for name in ("top/0", "top/1", "bottom/0", "bottom/1")}
            literal = {gauge+"/"+name: copy.deepcopy(value) for gauge in ("global_z", "boundary_plane")
                       for name, value in primary.items()}
            self.assertTrue(checker.validate_gauss(primary, literal))
            changed = copy.deepcopy(literal); changed["boundary_plane/top/0"]["rules"][0]["degree"] = 22
            with self.assertRaises(ValueError): checker.validate_gauss(primary, changed)
            generated.write_text("changed source")
            with self.assertRaises(ValueError): checker.validate_gauss(primary, literal)

    def test_no_numeric_import_at_module_load_or_fe_constructors(self):
        tree = ast.parse(CHECKER.read_text())
        allowed = {"__future__", "hashlib", "json", "math", "pathlib", "re"}
        for node in tree.body:
            if isinstance(node, ast.Import): self.assertTrue({item.name for item in node.names} <= allowed)
            elif isinstance(node, ast.ImportFrom): self.assertIn(node.module, allowed)
        forbidden = {"splu", "spsolve", "solve", "_build_same_mesh_levels", "build_same_mesh_physical_action",
                     "build_fresh_direct_carriers", "audit_direct_original_cell_contributions", "SavedQuotientSnapshotAuthority", "SavedFullP4Authority"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                self.assertNotIn(name, forbidden)
        runtime = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "check_direct")
        self.assertIn("check_direct_original_cell_contributions", ast.unparse(runtime))
        self.assertIn("check_raw_carriers", ast.unparse(runtime))
        self.assertIn("check_shared_storage_evidence", ast.unparse(runtime))
        self.assertIn("historical_original312_reused_for_new_point", ast.unparse(runtime))
        for path in (CHECKER, Path(__file__)): ast.parse(path.read_text(), filename=str(path))
        # Source-only packaging guard: prior ignored numerical evidence stays
        # in benchmarks/artifacts and is deliberately preserved by this task.
        self.assertFalse(list((ROOT / "src").rglob("*.npy")))
        self.assertFalse([path for path in (ROOT / "benchmarks").rglob("*.npy")
                          if "artifacts" not in path.relative_to(ROOT / "benchmarks").parts])
        self.assertFalse(list(ROOT.rglob("*.npz")))

    def test_nonfinite_markers_and_owned_paths_fail_closed(self):
        with self.assertRaises(ValueError): checker.decode_metadata({"__raw_spool_nonfinite__": "nan"})
        with self.assertRaises(ValueError): checker.decode_metadata({"measurement_status": "NONFINITE"})
        with self.assertRaises(ValueError): checker.finite_gate(float("nan"), 1e-10, "test")
        with self.assertRaises(ValueError): checker.finite_gate(True, 1e-10, "test")
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary)/"receipt.json"; file.write_text("{}")
            self.assertEqual(checker.bound_path(temporary, "receipt.json"), file)
            with self.assertRaises(ValueError): checker.bound_path(temporary, str(file))
            with self.assertRaises(ValueError): checker.bound_path(temporary, "../receipt.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
