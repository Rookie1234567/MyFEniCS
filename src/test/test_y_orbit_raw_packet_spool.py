"""Isolated metadata/source contracts; no project or numerical imports."""
import ast
from collections.abc import Mapping
import hashlib
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/solvers/y_orbit_raw_packet_spool.py"
TEXT = SOURCE.read_text()
TREE = ast.parse(TEXT)
ORACLE = ast.parse((ROOT / "src/solvers/y_orbit_quotient_raw_qualification.py").read_text())


def _function(name):
    return next(node for node in ast.walk(TREE) if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(node, name):
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)
            and ((isinstance(call.func, ast.Name) and call.func.id == name)
                 or (isinstance(call.func, ast.Attribute) and call.func.attr == name))]


def _constant(name, tree=TREE):
    return ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
                                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)))


@pytest.fixture
def isolated():
    names = {"OBSERVER_SCHEMA", "SPOOL_SCHEMA", "MODE_COUNTS", "METADATA_FIELDS", "PAIR_FIELDS"}
    nodes = [node for node in TREE.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    nodes += [_function(name) for name in ("_profile_errors", "_offset_inventory_errors", "_encode_metadata", "_decode_metadata",
                                          "_metadata_finite", "_write_manifest", "packets")]
    class MetadataScalar:
        pass
    namespace = {"np": SimpleNamespace(generic=MetadataScalar), "math": math, "Mapping": Mapping}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "isolated_raw_spool_metadata", "exec"), namespace)
    return namespace


def _packet(twist):
    packet = {field: None for field in _constant("METADATA_FIELDS")}
    n, branch = (0, None) if twist is None else ((-2, 1) if twist == 0 else (-3, 0))
    packet.update(schema=_constant("OBSERVER_SCHEMA"), local_mode_index=0, original_mode_index=0,
                  original_mode_key=("top", -9, n, "TE"), quotient_twist_index=twist,
                  local_branch_index=branch, quotient_contract_sha256=None if twist is None else "contract",
                  ownership_range=(0, 17204 if twist is None else 8940),
                  single_D_conjugation=True, raw_vectors_destroyed_before_callback=True)
    return packet


@pytest.mark.parametrize("twist", (None, 0, 1))
def test_only_expected_global_and_local_metadata_profiles_are_accepted(isolated, twist):
    assert isolated["_profile_errors"](_packet(twist), next_index=0, original_indices=set()) == []


@pytest.mark.parametrize("field,value", (
    ("local_mode_index", 1), ("local_mode_index", 0.0), ("original_mode_index", -1),
    ("original_mode_index", 532), ("original_mode_index", True), ("quotient_twist_index", 2),
    ("quotient_twist_index", True), ("ownership_range", (0, 17204)),
    ("single_D_conjugation", 1), ("raw_vectors_destroyed_before_callback", False),
    ("local_branch_index", None), ("quotient_contract_sha256", None),
    ("original_mode_key", ("top", -9, -1, "TE")), ("original_mode_key", ("top", -9)),
))
def test_metadata_identity_indices_branch_and_lifecycle_fail_closed(isolated, field, value):
    packet = _packet(0)
    packet[field] = value
    assert isolated["_profile_errors"](packet, next_index=0, original_indices=set())


def test_duplicate_original_index_is_rejected(isolated):
    assert isolated["_profile_errors"](_packet(0), next_index=0, original_indices={0})


def test_global_original_mapping_cannot_be_sector_relabelled(isolated):
    packet = _packet(None)
    packet["original_mode_index"] = 3
    assert isolated["_profile_errors"](packet, next_index=0, original_indices=set())


def test_metadata_codec_preserves_complex_and_explicit_nonfinite_failure_markers(isolated):
    original = {"context": [2+3j, float("nan"), float("inf"), complex(float("-inf"), 2)], "flag": True}
    encoded = isolated["_encode_metadata"](original)
    decoded = isolated["_decode_metadata"](encoded)
    assert decoded["context"][0] == 2+3j
    assert math.isnan(decoded["context"][1])
    assert decoded["context"][2] == float("inf")
    assert decoded["context"][3].real == float("-inf")
    assert decoded["flag"] is True
    assert isolated["_metadata_finite"](decoded) is False
    with pytest.raises(TypeError):
        isolated["_encode_metadata"]({"unsupported": object()})


@pytest.mark.parametrize("profile,count", ((None, 532), (0, 228), (1, 304)))
def test_complete_metadata_stream_is_still_unqualified(isolated, profile, count):
    captured = []
    dummy = SimpleNamespace(_profile=profile, _identity={"context": "frozen"}, _failure=None,
                            _mode_counts=isolated["MODE_COUNTS"], _direct_identity=None,
                            _records=[{"all_finite": True} for _ in range(count)],
                            root_directory=Path("/tmp/run"), manifest_path=Path("/tmp/manifest.json"),
                            _write_json=lambda path, value: captured.append(value))
    isolated["_write_manifest"](dummy)
    packet = captured[0]
    assert packet["status"] == "READY_RAW_PACKETS_UNQUALIFIED"
    assert packet["complete_finite_stream"] is True
    for field in ("raw_port_qualified", "PDE_solved", "official_results"):
        assert packet[field] is False
    assert packet["factor_count"] == 0
    dummy.packet = lambda index: index
    assert list(isolated["packets"](dummy)) == list(range(count))


def test_incomplete_or_captured_failed_stream_cannot_supply_ready_packets(isolated):
    dummy = SimpleNamespace(_profile=0, _identity={}, _failure=None, _records=[],
                            _mode_counts=isolated["MODE_COUNTS"], _direct_identity=None)
    with pytest.raises(ValueError, match="partial"):
        list(isolated["packets"](dummy))
    dummy._records = [None]*228
    dummy._failure = {"reason": "failure"}
    with pytest.raises(ValueError, match="captured failure"):
        list(isolated["packets"](dummy))


def test_complete_nonfinite_evidence_is_diagnostic_only(isolated):
    captured = []
    dummy = SimpleNamespace(_profile=0, _identity={}, _failure=None,
                            _mode_counts=isolated["MODE_COUNTS"], _direct_identity=None,
                            _records=[{"all_finite": False}]+[{"all_finite": True}]*227,
                            root_directory=Path("/tmp/run"), manifest_path=Path("/tmp/manifest.json"),
                            _write_json=lambda path, value: captured.append(value))
    isolated["_write_manifest"](dummy)
    assert captured[0]["status"] == "COMPLETE_RAW_FAILURE_DIAGNOSTIC_ONLY"
    assert captured[0]["complete_finite_stream"] is False
    assert captured[0]["raw_port_qualified"] is False


def test_packet_fields_match_the_frozen_oracle_without_changing_its_source():
    raw = _constant("RAW_FIELDS")
    assert raw == _constant("RAW_VECTOR_FIELDS", ORACLE)
    assert set(_constant("METADATA_FIELDS")) | {"component_masked_entries", "stored_C_sparse", "stored_D_sparse"} == set(
        _constant("REQUIRED_PACKET_METADATA", ORACLE))
    oracle_path = ROOT / "src/solvers/y_orbit_quotient_raw_qualification.py"
    assert hashlib.sha256(oracle_path.read_bytes()).hexdigest() == "269f27e57fe2de214086b51485749f35d066d697fc129a7b48ac18e126314a45"


def test_allocation_gate_precedes_every_current_nonzero_extract_copy_write():
    observe = _function("observe")
    gate = _calls(observe, "allocation_gate")[0]
    assert gate.lineno < _calls(observe, "flatnonzero")[0].lineno
    assert gate.lineno < _calls(observe, "_encode_metadata")[0].lineno
    assert gate.lineno < _calls(observe, "_save")[0].lineno
    assert gate.lineno < _calls(observe, "_write_json")[0].lineno
    facts = gate.args[1]
    keys = {ast.literal_eval(key) for key in facts.keys}
    assert {"matrix_payload_bytes", "workspace_bytes", "evidence_reserve_bytes", "factor_count"} <= keys
    assert "vector != 0" in ast.unparse(observe)
    assert not _calls(observe, "abs") and "cutoff" not in ast.unparse(observe)


def _valid_offsets():
    return [{"field": field, "offset": index*2, "length": 2, "original_rows_dtype": "int64"}
            for index, field in enumerate(_constant("PAIR_FIELDS"))]


def test_exact_fixed_offset_inventory_accepts_only_complete_ordered_layout(isolated):
    assert isolated["_offset_inventory_errors"](_valid_offsets(), 20) == []


@pytest.mark.parametrize("mutation", ("missing", "overlap", "gap", "reordered", "negative", "overflow", "wrong_type", "uncovered"))
def test_missing_overlap_reordered_or_invalid_offsets_are_rejected(isolated, mutation):
    inventory, total = _valid_offsets(), 20
    if mutation == "missing":
        inventory.pop()
    elif mutation == "overlap":
        inventory[3]["offset"] -= 1
    elif mutation == "gap":
        inventory[3]["offset"] += 1
    elif mutation == "reordered":
        inventory[0], inventory[1] = inventory[1], inventory[0]
    elif mutation == "negative":
        inventory[3]["length"] = -1
    elif mutation == "overflow":
        inventory[-1]["length"] = 3
    elif mutation == "wrong_type":
        inventory[3]["offset"] = 6.0
    elif mutation == "uncovered":
        total = 21
    assert isolated["_offset_inventory_errors"](inventory, total)


def test_actual_concatenation_payload_is_admitted_and_only_two_artifacts_are_written():
    observe = _function("observe")
    assert len(_calls(observe, "concatenate")) == 2
    assert len(_calls(observe, "_save")) == 2
    gate = _calls(observe, "allocation_gate")[1]
    assert gate.lineno < _calls(observe, "concatenate")[0].lineno
    validation = _calls(observe, "_validate_pair")[0]
    assert validation.lineno < gate.lineno
    source = ast.unparse(observe)
    assert "complete_payload_bytes = total_entries * (8 + 16)" in source
    assert "current_pairs = []" in source
    assert "dtype=np.int64" in source and "dtype=np.complex128" in source
    read = ast.unparse(_function("packet"))
    assert "combined_rows[start:end]" in read and "combined_values[start:end]" in read
    assert "_offset_inventory_errors(descriptor['offset_inventory'], shape[0])" in read


def test_artifact_hashes_and_safe_shared_root_paths_are_verified_on_write_and_read():
    for name in ("_save", "_load"):
        source = ast.unparse(_function(name))
        assert "_artifact_path(descriptor)" in source
        assert "_file_sha256(path)" in source
        assert "descriptor['file_sha256']" in source
        assert "array_sha256" in source and "payload_bytes" in source
    assert "path.relative_to(self.root_directory)" in ast.unparse(_function("_artifact_path"))
    load = ast.unparse(_function("_load"))
    assert "mmap_mode='r'" in load and "allow_pickle=False" in load
    read = _function("packet")
    assert _calls(read, "allocation_gate")[0].lineno < _calls(read, "read_text")[0].lineno
    assert _calls(read, "allocation_gate")[1].lineno < _calls(read, "_load")[0].lineno


def test_spool_retains_descriptors_only_and_generator_yields_one_current_packet():
    observe = ast.unparse(_function("observe"))
    assert "self._records.append({'local_mode_index': index" in observe
    appended = _calls(_function("observe"), "append")[0]
    keys = {ast.literal_eval(key) for key in appended.args[0].keys}
    assert keys == {"local_mode_index", "original_mode_index", "descriptor_path", "descriptor_sha256", "all_finite"}
    assert "yield self.packet(index)" in ast.unparse(_function("packets"))
    deletes = {target.id for node in ast.walk(_function("observe")) if isinstance(node, ast.Delete)
               for target in node.targets if isinstance(target, ast.Name)}
    assert {"rows", "values", "combined_rows", "combined_values", "current_pairs"} <= deletes
    forbidden = {"outgoing_port_modes_3d", "build_fullspace_dtn_carrier_from_surface", "assemble_raw_mpc_vector",
                 "build_physical_rhs", "splu", "solve", "conjugate"}
    assert all(not _calls(TREE, name) for name in forbidden)
    # Only the reviewed standard-library metadata profile is imported, and
    # only in the explicit opt-in branch. The old None path stays import-free.
    relative = [node for node in ast.walk(TREE) if isinstance(node, ast.ImportFrom) and node.level]
    assert len(relative) == 2
    assert all(node.level == 1 and node.module == "y_orbit_direct_profile"
               and [alias.name for alias in node.names] == ["direct_profile_metadata"] for node in relative)
    guarded = [node for node in ast.walk(TREE) if isinstance(node, ast.If)
               and ast.unparse(node.test) == "direct_profile is not None"]
    assert all(any(item is node for branch in guarded for item in ast.walk(branch)) for node in relative)


def test_row_validation_precedes_writing_and_no_narrowing_is_added():
    function = _function("_validate_pair")
    assert not _calls(function, "_save")
    assert not _calls(TREE, "astype")
    source = ast.unparse(function)
    for token in ("rows.dtype.kind", "rows < 0", "rows >= n", "rows[1:] <= rows[:-1]"):
        assert token in source


def test_partial_write_failures_record_artifact_descriptors_after_admission():
    observe = ast.unparse(_function("observe"))
    assert "partial_sparse_artifacts" in observe and "offset_inventory" in observe
    assert "if admitted:\n            self._write_manifest()" in observe
    assert "metadata_encoding_failure" in observe
    write = ast.unparse(_function("_write_json"))
    assert "allow_nan=False" in write and "temporary.open('xb')" in write and "temporary.replace(path)" in write
