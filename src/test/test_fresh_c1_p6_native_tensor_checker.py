"""Native-orientation authority contracts; no mesh/form/JIT/PDE or factors.

Saved-transform tests are opt-in. Their nonidentity native hash is a newly
derived diagnostic witness, not the unavailable original failed-worker hash.
The default tests use only source inspection, metadata, and primitive arrays.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest import mock

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "benchmarks/check_fresh_c1_p6_component.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("fresh_p6_native_checker_contract", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checker_import_remains_standard_library_only():
    tree = ast.parse(SOURCE.read_text())
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert {alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names} == {
        "hashlib", "json", "math", "re"}
    assert all(node.module == "__future__" for node in imports if isinstance(node, ast.ImportFrom))


@pytest.mark.parametrize("key,value", [("degree", 4), ("dtype", "complex128"),
    ("basix_hash", 0), ("coefficient_matrix_C_sha256", "0"*64), ("local_interiors", 449)])
def test_wrong_native_basis_metadata_rejected_before_import(checker, key, value):
    metadata = {**checker.NATIVE_ELEMENT, key: value}
    with mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        with pytest.raises(ValueError, match="native element metadata"):
            checker._native_element(metadata, lambda *_: None)


def test_historical_basis_byte_pin_is_not_accepted_for_fresh_qualified_factory(checker):
    metadata = {**checker.NATIVE_ELEMENT, "coefficient_matrix_C_sha256":
        "780d9a4529041f8cb8138a78c8314d757822a1f5bc984f254c5790db208e911d"}
    with mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        with pytest.raises(ValueError, match="native element metadata"):
            checker._native_element(metadata, lambda *_: None)


def test_actual_public_factory_matches_fresh_producer_exact_byte_pin(checker):
    admissions = []
    element = checker._native_element(dict(checker.NATIVE_ELEMENT),
        lambda name, facts: admissions.append((name, facts)))
    assert checker._native_element_identity(element) == checker.NATIVE_ELEMENT
    assert checker.NATIVE_ELEMENT["coefficient_matrix_C_sha256"] == (
        "c0be730f050c40e2333362ceac4fac0d656eaf029cf7454a1dbbc21253e064da")
    assert len(admissions) == 1 and admissions[0][1]["native_element_factory_only"]
    assert not admissions[0][1]["mesh_created"] and not admissions[0][1]["JIT"]


def test_rebuilt_native_factory_identity_must_still_match_every_saved_byte_field(checker):
    wrong = {**checker.NATIVE_ELEMENT, "coefficient_matrix_C_sha256": "1" * 64}
    with mock.patch.object(checker, "_native_element_identity", return_value=wrong):
        with pytest.raises(ValueError, match="live native basis hash"):
            checker._native_element(dict(checker.NATIVE_ELEMENT), lambda *_: None)


def test_native_basis_pin_source_bridge_is_exact_hash_bounded():
    from benchmarks.check_y_orbit_sparse_probe import _bind_worker_dependencies, NATIVE_BASIS_PIN_SOURCE_DELTA
    old = {"head": "worker", "branch": "task40extra_dot_parallel_cloud", "dirty": "",
           "files_sha256": {name: pair[0] for name, pair in NATIVE_BASIS_PIN_SOURCE_DELTA.items()}}
    new = {"head": "checker", "branch": old["branch"], "dirty": "",
           "files_sha256": {name: pair[1] for name, pair in NATIVE_BASIS_PIN_SOURCE_DELTA.items()}}
    receipt = _bind_worker_dependencies(old, new)
    assert set(receipt["native_basis_pin_hash_binding"]) == set(NATIVE_BASIS_PIN_SOURCE_DELTA)
    for name, pair in NATIVE_BASIS_PIN_SOURCE_DELTA.items():
        assert pair[1] == hashlib.sha256((SOURCE.parents[1] / name).read_bytes()).hexdigest()
        bad = copy.deepcopy(new); bad["files_sha256"][name] = "0" * 64
        with pytest.raises(RuntimeError, match="exact native basis pin"):
            _bind_worker_dependencies(old, bad)
    bad = copy.deepcopy(new); bad["files_sha256"]["src/solvers/fresh_c1_p6_component.py"] = "0" * 64
    with pytest.raises(RuntimeError, match="byte-identical"):
        _bind_worker_dependencies(old, bad)


def test_native_basis_allocation_denial_precedes_import(checker):
    def denied(stage, facts):
        assert stage.endswith("native_basis_wrapper")
        assert facts["native_element_factory_only"] and not facts["JIT"]
        raise MemoryError("basis wrapper allocation denied")
    with mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        with pytest.raises(MemoryError, match="allocation denied"):
            checker._native_element(dict(checker.NATIVE_ELEMENT), denied)


def test_native_recipe_uses_two_c_order_row_operations_without_conjugation(checker):
    import numpy as np
    transform = np.asarray([[1., .25], [-.5, 1.]])
    calls = []
    class Element:
        space_dimension = 2
        def T_apply(self, flat, info, dimension):
            assert flat.flags.c_contiguous and flat.flags.writeable
            assert flat.dtype == np.complex128 and info.dtype == np.uint32
            assert int(info[0]) == 7 and dimension == 2
            matrix = flat.reshape(2, 2)
            calls.append(matrix.copy())
            matrix[:] = transform @ matrix
    raw = np.asarray([[1.+2j, 3.-4j], [5.+6j, 7.-8j]])
    before = checker._sha(raw, header=False)
    result = checker._native_row_transpose_row(Element(), raw, 7)
    np.testing.assert_array_equal(calls[0], raw)
    np.testing.assert_array_equal(calls[1], (transform @ raw).T)
    np.testing.assert_array_equal(result, transform @ raw @ transform.T)
    assert result.flags.c_contiguous and len(calls) == 2
    assert checker._sha(raw, header=False) == before


def test_native_hash_preserves_signed_zero_bytes(checker):
    import numpy as np
    positive = np.zeros((2, 2), dtype=np.complex128)
    negative = positive.copy()
    negative.real[0, 0] = -0.
    assert np.array_equal(positive, negative)
    assert checker._sha(positive, header=False) != checker._sha(negative, header=False)


@pytest.fixture(scope="module")
def saved_transform(checker):
    run_path = os.environ.get("FRESH_C1_SAVED_TRANSFORM_RUN")
    diagnostic_path = os.environ.get("FRESH_C1_SAVED_TRANSFORM_DIAGNOSTIC")
    if not run_path or not diagnostic_path:
        pytest.skip("explicit saved-transform artifact/diagnostic paths required")
    import numpy as np
    run, diagnostic = Path(run_path), Path(diagnostic_path)
    manifest = json.loads((run / "probe_report.json").read_text())
    derived = json.loads((diagnostic / "diagnostic.json").read_text())
    assert derived["original_strict_byte_gate"] == "FAILED_PRESERVED"
    arrays, references = {}, {}
    names = ["original/raw_class/0/tensor", "original/raw_class/0/coordinates"]
    names += ["original/orientation/32769/" + name for name in ("indptr", "indices", "data")]
    for name in names:
        artifact = manifest["artifacts"][name]
        path = run / artifact["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["file_sha256"]
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        assert list(array.shape) == artifact["shape"] and str(array.dtype) == artifact["dtype"]
        arrays[name] = array
        references[name] = {"name": name, "shape": list(array.shape), "dtype": str(array.dtype),
                            "numeric_bytes": int(array.nbytes), "sha256": checker._sha(array)}
    native = np.load(diagnostic / "derived_native_oriented_32769.npy", allow_pickle=False, mmap_mode="r")
    native_hash = derived["orientations"]["32769"]["final"]["reference_c_sha256"]
    assert checker._sha(native, header=False) == native_hash == "5e3d57a8f9bdd2e673087806536573130066cf7e2f503c37f51a75518c5526d5"
    raw_ref = references[names[0]]
    coordinates = arrays[names[1]].reshape(8, 3)
    widths = tuple(map(float, coordinates.max(axis=0) - coordinates.min(axis=0)))
    class_key = [0, *widths, 32769]
    orientation = {"representation": "actual_Basix_T_apply_CSR", "shape": [882, 882],
                   "cell_info": 32769, "basis_hash": checker.NATIVE_ELEMENT["basix_hash"],
                   "small_entry_threshold": None}
    orientation.update({name: references["original/orientation/32769/"+name]
                        for name in ("indptr", "indices", "data")})
    entry = {"class_index": 0, "class_key": class_key, "raw_tensor": raw_ref,
             "original_tensor": {"representation": checker.NATIVE_TENSOR_REPRESENTATION,
                 "recipe": checker.NATIVE_TENSOR_RECIPE, "raw_tensor": raw_ref,
                 "native_element": dict(checker.NATIVE_ELEMENT), "orientation": orientation,
                 "shape": [882, 882], "dtype": "complex128", "C_order_bytes_sha256": native_hash}}
    identity = {"shape": [882, 882], "dtype": "complex128",
                "raw_sha256": checker._sha(arrays[names[0]], header=False), "oriented_sha256": native_hash}
    identities = {repr(tuple(class_key)): identity}
    numeric_bytes = sum(a.nbytes for a in arrays.values())
    upper = numeric_bytes + 4096*len(arrays)
    report = {"snapshot": {"roles": references, "members": list(references.values()),
                "unique_member_count": len(arrays), "numeric_bytes": numeric_bytes,
                "archive_members_bytes_upper": upper, "archive_payload_limit_bytes": upper},
              "original_sources": {"pre_elimination_tensor_identities": identities},
              "condensation_audit": {"action_only_complete_tensor_identities": copy.deepcopy(identities)}}
    element = checker._native_element(dict(checker.NATIVE_ELEMENT), lambda *_: None)
    ipos = np.asarray(element.basix_element.entity_dofs[3][0], dtype=np.int32)
    tpos = np.setdiff1d(np.arange(882, dtype=np.int32), ipos)
    return report, entry, {"coordinates": references[names[1]]}, arrays, native, element, ipos, tpos


def reconstruct(checker, packet, *, mutate=None):
    report, entry, raw_record, arrays, native, element, ipos, tpos = packet
    report, entry = copy.deepcopy(report), copy.deepcopy(entry)
    if mutate:
        mutate(report, entry)
    measures = checker._Measurements(lambda *_: None)
    reader = checker._Reader(report, lambda ref: arrays[ref["name"]], lambda *_: None)
    result = checker._original_tensor(reader, report, entry, raw_record, lambda *_: None,
                                      measures, ipos, tpos, element)
    return result, measures


def test_saved_native_exact_hash_and_csr_all_blocks(checker, saved_transform):
    (tensor, sha), measures = reconstruct(checker, saved_transform)
    assert sha == checker._sha(saved_transform[4], header=False)
    assert len(measures.records) == 6 and all(record["passed"] for record in measures.records.values())
    assert all(record["limit"] == 1.e-12 for record in measures.records.values())
    assert measures.records["class/0/orientation/CSR_native_tensor"]["error_norm"] > 0
    assert checker._sha(tensor, header=False) != "dd9b6e04225469a872784ce589edd0bdc54a0adba31c3ed692e547bc06481d39"


@pytest.mark.parametrize("corruption", ["missing_hash", "wrong_hash", "basis", "old_recipe",
                                       "missing_inventory", "identity_mismatch", "raw_hash"])
def test_saved_native_authority_corruption_rejected(checker, saved_transform, corruption):
    def mutate(report, entry):
        descriptor = entry["original_tensor"]
        key = repr(tuple(entry["class_key"]))
        if corruption == "missing_hash":
            descriptor.pop("C_order_bytes_sha256")
        elif corruption == "wrong_hash":
            descriptor["C_order_bytes_sha256"] = "0"*64
        elif corruption == "basis":
            descriptor["native_element"]["basix_hash"] = 0
        elif corruption == "old_recipe":
            descriptor.update(representation="raw_tensor_congruence", recipe="T@raw@T.T; no conjugation")
        elif corruption == "missing_inventory":
            report["original_sources"].pop("pre_elimination_tensor_identities")
        elif corruption == "identity_mismatch":
            report["condensation_audit"]["action_only_complete_tensor_identities"][key]["oriented_sha256"] = "0"*64
        else:
            report["original_sources"]["pre_elimination_tensor_identities"][key]["raw_sha256"] = "0"*64
    with pytest.raises(ValueError):
        reconstruct(checker, saved_transform, mutate=mutate)


@pytest.mark.parametrize("operation", ["omitted", "one_sided"])
def test_saved_omitted_and_one_sided_native_operations_rejected(checker, saved_transform, operation):
    import numpy as np
    def wrong(element, raw, info):
        result = np.array(raw, order="C", copy=True)
        if operation == "one_sided":
            element.T_apply(result.ravel(), np.asarray([info], dtype=np.uint32), 882)
        return result
    with mock.patch.object(checker, "_native_row_transpose_row", side_effect=wrong):
        with pytest.raises(ValueError, match="raw/native tensor hashes differ"):
            reconstruct(checker, saved_transform)
