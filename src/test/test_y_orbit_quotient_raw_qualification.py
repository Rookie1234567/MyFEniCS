"""Static and isolated metadata checks; no project import or numerical run.

Passing these checks is only a source-wiring contract. No UFL/JIT/FE/PDE,
literal coefficient, actual Gauss, MPC, folding, factor, or operator gate runs.
"""
import ast
import hashlib
from pathlib import Path

import pytest


STAGE = Path(__file__).resolve().parents[2]
SOURCE = STAGE / "src/solvers/y_orbit_quotient_raw_qualification.py"
SOURCE_TEXT = SOURCE.read_text()
TREE = ast.parse(SOURCE_TEXT)
EXPERIMENTS = STAGE.parents[1]
REPO = STAGE if (STAGE / "AGENTS.md").is_file() else EXPERIMENTS.parent / "repo"
HELPER = REPO / "src/solvers/dtn_boundary_plane_qualification.py"
PLAN = (REPO / "docs/task40extra_dot_parallel_cloud/two_cell_p4_minimal_implementation_plan_v1_zh.md"
        if REPO == STAGE else EXPERIMENTS / "y_reference_scalability/two_cell_p4_minimal_implementation_plan_v1_zh.md")


def _function(name, tree=TREE):
    return next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(node, name):
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)
            and ((isinstance(call.func, ast.Name) and call.func.id == name)
                 or (isinstance(call.func, ast.Attribute) and call.func.attr == name))]


def _constant(name):
    return ast.literal_eval(next(node.value for node in TREE.body if isinstance(node, ast.Assign)
                                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)))


@pytest.fixture
def metadata_gate():
    # Execute only this pure metadata function and literal constants. The
    # numerical module is never imported and none of its numerical code runs.
    names = {"REQUIRED_PACKET_METADATA", "RAW_PACKET_SCHEMA"}
    constants = [node for node in TREE.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    isolated = ast.Module(body=constants + [_function("_packet_metadata_errors")], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(isolated), "isolated_raw_packet_metadata", "exec"), namespace)
    return namespace["_packet_metadata_errors"]


@pytest.fixture
def valid_metadata():
    packet = {name: None for name in _constant("REQUIRED_PACKET_METADATA")}
    packet.update({"schema": _constant("RAW_PACKET_SCHEMA"), "local_mode_index": 0,
                   "original_mode_index": 19, "original_mode_key": ("top", -9, -2, "TE"),
                   "local_branch_index": 1, "quotient_twist_index": 0,
                   "physical_generator_manifest_sha256": "physical",
                   "assembly_context_sha256": "context", "quotient_contract_sha256": "contract",
                   "ownership_range": (0, 8940), "single_D_conjugation": True,
                   "raw_vectors_destroyed_before_callback": True})
    expected = {"local_index": 0, "original_index": 19, "original_key": ("top", -9, -2, "TE"),
                "branch": 1, "twist": 0, "physical_manifest": "physical", "context_sha": "context",
                "contract_sha": "contract", "ownership_range": (0, 8940)}
    return packet, expected


def test_source_and_expected_authority_parse_and_hash_without_imports():
    ast.parse(SOURCE_TEXT, filename=str(SOURCE))
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == "baf07751697ec92bb209571927fec41223b735a14d19dd3f55710a6c8bddb136"
    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == "0e30704302472ee421e0dd5b250ef0361d6c6f96a84fea6082298a4baab8ebd2"


def test_exact_raw_packet_metadata_is_accepted(metadata_gate, valid_metadata):
    packet, expected = valid_metadata
    assert metadata_gate(packet, **expected) == []


@pytest.mark.parametrize("field,replacement", (
    ("local_mode_index", 1), ("local_mode_index", 0.0), ("original_mode_index", 20),
    ("original_mode_key", ("top", -9, 0, "TE")), ("local_branch_index", 0),
    ("quotient_twist_index", 1), ("physical_generator_manifest_sha256", "other"),
    ("assembly_context_sha256", "other"), ("quotient_contract_sha256", "other"),
    ("ownership_range", (0, 17204)), ("single_D_conjugation", False),
    ("single_D_conjugation", 1), ("raw_vectors_destroyed_before_callback", False),
))
def test_wrong_sector_original_phase_context_or_lifecycle_is_rejected(metadata_gate, valid_metadata, field, replacement):
    packet, expected = valid_metadata
    packet[field] = replacement
    assert "mismatch " + field in metadata_gate(packet, **expected)


@pytest.mark.parametrize("field", ("local_branch_index", "original_mode_row", "component_masks", "stored_D_sparse"))
def test_missing_required_metadata_is_not_silently_assumed(metadata_gate, valid_metadata, field):
    packet, expected = valid_metadata
    packet.pop(field)
    assert "missing " + field in metadata_gate(packet, **expected)


def test_narrow_api_has_no_primary_rebuild_generator_rhs_or_factor_call():
    main = _function("qualify_quotient_raw_bundle")
    assert [arg.arg for arg in main.args.args] == ["bundle"]
    assert {arg.arg for arg in main.args.kwonlyargs} == {
        "raw_mode_packets", "record_path", "expected_physical_manifest", "expected_global_ordered_keys", "seed", "tolerance",
        "direct_profile", "literal_mode_observer"}
    defaults = dict(zip((arg.arg for arg in main.args.kwonlyargs), main.args.kw_defaults))
    assert ast.literal_eval(defaults["direct_profile"]) is None
    assert ast.literal_eval(defaults["literal_mode_observer"]) is None
    forbidden = {"build_same_mesh_physical_action", "build_fullspace_dtn_carrier_from_surface",
                 "outgoing_port_modes_3d", "build_dynamic_mode_inventory", "build_physical_rhs",
                 "prepare_boundary_plane_outputs", "splu", "factor", "solve", "solve_repeated"}
    assert all(not _calls(TREE, name) for name in forbidden)
    assert not any(isinstance(node, ast.ImportFrom) and any(alias.name in forbidden for alias in node.names)
                   for node in ast.walk(TREE))


def test_eight_literal_forms_reuse_the_existing_literal_expressions_exactly():
    old = _function("qualify_boundary_plane_bundle", ast.parse(HELPER.read_text()))
    new = _function("qualify_quotient_raw_bundle")
    def literal_block(function):
        return next(node for node in ast.walk(function) if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Name) and node.target.id == "gauge")
    old_block, new_block = literal_block(old), literal_block(new)
    assert ast.unparse(old_block.iter) == ast.unparse(new_block.iter) == "(GLOBAL_Z, BOUNDARY_PLANE)"
    assert ast.unparse(new_block.body[0].iter) == "('top', 'bottom')"
    assert ast.unparse(new_block.body[0].body[0].iter) == "(0, 1)"
    for name in ("alpha", "gamma", "kz", "x", "z", "phase", "vector", "form", "compiled", "oracle_identity", "primary_identity"):
        def assignment(block):
            return next(node for node in ast.walk(block) if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
        assert ast.dump(assignment(old_block), include_attributes=False) == ast.dump(assignment(new_block), include_attributes=False)


def test_raw_coefficients_are_measured_before_cutoff_with_one_D_conjugation():
    function = _function("qualify_quotient_raw_bundle")
    source = ast.unparse(function)
    assert source.index("current['raw_literal_errors'] = raw_errors") < source.index("after_components = tuple")
    assert len(_calls(function, "_assemble_mpc_form_vector")) == 1
    for name in ("Dg", "Dp", "Dm"):
        assignment = next(node for node in ast.walk(function) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
        assert len(_calls(assignment, "conjugate")) == 1
    assert not _calls(_function("_rank_one_loss_bound"), "conjugate")
    assert "Dg / np.conjugate(phase)" in source


def test_two_unchanged_cutoffs_and_original_rank_one_tolerance_are_explicit():
    assert _constant("ABSOLUTE_SPARSE_FLOOR") == 1e-30
    assert _constant("RELATIVE_SPARSE_CUTOFF") == 1e-13
    assert _constant("FIXED_TOLERANCE") == 1e-10
    assert "np.abs(vector) > threshold" in ast.unparse(_function("_mask"))
    main = ast.unparse(_function("qualify_quotient_raw_bundle"))
    for name in ("component_mask", "final_mask", "all_masks", "literal_vs_primary_raw"):
        assert name in main
    assert "relative_bounds.values()" in main and "value <= tolerance" in main
    assert "stored_H'] <= 1e-14" in main
    assert "diagnostic['threshold'] == threshold" in main
    assert "np.array_equal(values != 0, expected != 0)" in main


def test_sparse_snapshots_cannot_use_masked_carrier_or_unsafe_row_casts():
    assert _constant("RAW_VECTOR_FIELDS") == ("raw_C", "raw_D", "after_component_mask_C", "after_component_mask_D")
    dense = _function("_dense_sparse")
    assert _calls(dense, "astype")[0].lineno > next(node.lineno for node in ast.walk(dense) if isinstance(node, ast.Raise))
    source = ast.unparse(dense)
    for token in ("rows.dtype.kind", "rows >= n", "rows < 0", "rows[1:] <= rows[:-1]", "np.isfinite(values)"):
        assert token in source
    assert "raw_components_sparse" in SOURCE_TEXT
    assert "stored data cannot substitute" in SOURCE_TEXT
    assert "including values below either cutoff" in SOURCE_TEXT


def test_actual_carrier_basis_MPC_source_Gauss_are_checked_at_both_ends():
    function = _function("qualify_quotient_raw_bundle")
    assert len(_calls(function, "_actual_discrete_binding")) == 2
    assert len(_calls(function, "_source_binding")) == 2
    assert len(_calls(function, "_check_loaded_primary_provenance")) == 4
    assert len(_calls(function, "select_inventory")) == 2
    for token in ("carrier is carrier", "carrier.quotient_context is ctx", "carrier_numeric_identity(carrier) == identity_before",
                  "actual_local_cells", "n == expected_storage", "actual_finalized_slave_rows", "== expected_slaves", "ctx.tau == ctx.eta**2"):
        assert token in SOURCE_TEXT
    for name, unchanged_default in (("expected_cells", 40), ("expected_storage", 8940), ("expected_slaves", 1004)):
        value = next(node.value for node in ast.walk(function) if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
        assert isinstance(value, ast.IfExp)
        assert ast.unparse(value.test) == "direct is not None"
        assert ast.literal_eval(value.orelse) == unchanged_default
    discrete = ast.unparse(_function("_actual_discrete_binding"))
    assert "mpc.coefficients()" in discrete and "basix_coefficients" in discrete and "orientation" in discrete


def test_stream_checks_missing_and_extra_packets_and_releases_current_raw_arrays():
    function = _function("qualify_quotient_raw_bundle")
    source = ast.unparse(function)
    assert "stream = iter(raw_mode_packets)" in source
    assert len(_calls(function, "next")) == 2
    assert "missing current-mode raw observer packet" in source
    assert "extra or repeated raw packet" in source
    deletes = {target.id for node in ast.walk(function) if isinstance(node, ast.Delete)
               for target in node.targets if isinstance(target, ast.Name)}
    assert {"supplied", "observed_components", "observed", "literal", "stored", "Cm", "Dm", "left", "right", "functional"} <= deletes
    assert "supplied = literal_current = None" in SOURCE_TEXT
    assert len(_calls(function, "destroy")) == 3


def test_rejecting_gate_preserves_partial_before_raising_and_keeps_failed_raw():
    gate = _function("require")
    rejecting = gate.body[0]
    assert isinstance(rejecting, ast.If)
    assert _calls(rejecting, "preserve")[0].lineno < next(node.lineno for node in ast.walk(rejecting) if isinstance(node, ast.Raise))
    main = ast.unparse(_function("qualify_quotient_raw_bundle"))
    for token in ("current_raw_packet", "current_literal_raw_components", "current_mode", "completed_mode_count",
                  "FAILED_QUOTIENT_RAW_PORT_AUDIT", "partial/negative audit-only evidence"):
        assert token in main
    assert _calls(_function("write"), "_failure_diagnostic")


def test_receipt_cannot_claim_component_PDE_factor_RHS_or_official_pass():
    assert _constant("PASS_STATUS") == "PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY"
    function = _function("qualify_quotient_raw_bundle")
    base = next(node.value for node in ast.walk(function) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "base" for target in node.targets))
    flags = {ast.literal_eval(key): ast.literal_eval(value) for key, value in zip(base.keys, base.values)
             if isinstance(value, ast.Constant)}
    for key in ("full_component_qualified", "full_case_pass", "PDE_solved", "official_results",
                "physical_rhs_qualified", "physical_output_qualified"):
        assert flags[key] is False
    assert flags["factor_count"] == 0
    assert "global dual-folded physical forcing" in SOURCE_TEXT
    assert "no certified relative norm of summed operator" in SOURCE_TEXT
    assert len(_constant("DEFERRED_GATES")) == 6
