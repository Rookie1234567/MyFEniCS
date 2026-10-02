"""Isolated metadata/codec/tamper tests. No project, MPI or FE import."""
from __future__ import annotations

import ast
import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


MODULE_PATH = Path(__file__).parents[1]/"solvers/y_orbit_qualified_snapshot.py"
spec = importlib.util.spec_from_file_location("isolated_snapshot", MODULE_PATH)
snapshot = importlib.util.module_from_spec(spec)
with patch.object(builtins, "__import__", wraps=builtins.__import__) as imports:
    spec.loader.exec_module(snapshot)
IMPORTED_NAMES = tuple(call.args[0] for call in imports.call_args_list)


def gate(label, facts):
    if facts["factor_count"] != 0 or facts["evidence_reserve_bytes"] != 128 << 20:
        raise AssertionError("all snapshot allocations must retain the exact evidence reserve")


def encode(value):
    if isinstance(value, complex):
        return {"__raw_spool_complex__": [value.real, value.imag]}
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))
    return snapshot._file_sha(path)


class SnapshotContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, *, mutate=None):
        directory = "raw_twist_0"
        context = {"schema": "isolated.context.v1", "phase": 0.125+0.25j}
        context_sha = hashlib.sha256(snapshot._canonical(context)).hexdigest()
        identity = {"physical_generator_manifest_sha256": snapshot.PHYSICAL_MANIFEST,
            "assembly_context_sha256": context_sha, "quotient_contract_sha256": "isolated-contract",
            "quotient_twist_index": 0, "ownership_range": [0, 8940]}
        packet = {"schema": snapshot.OBSERVER_SCHEMA, "local_mode_index": 0,
            "original_mode_index": 2, "original_mode_key": ["top", -9, -2, "s"],
            "original_mode_row": {"z": -0.0, "a": 2-0j}, "assembly_context": context,
            **identity, "local_branch_index": 1, "component_masks": {}, "combination_masks": {},
            "local_plane_H": 1.25, "original_plane_H": 2.5, "single_D_conjugation": True,
            "raw_vectors_destroyed_before_callback": True,
            "array_ownership": "borrowed_readonly_during_synchronous_callback; copy_to_retain"}
        rr = np.array([3, 7]*10, dtype=np.int64)
        vv = np.array([0.125+2j, 1e-40-0.25j]*10, dtype=np.complex128)
        payload = {}
        for name, array in (("rows", rr), ("values", vv)):
            path = self.root/f"arrays/{name}.npy"
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, array, allow_pickle=False)
            payload[name] = {"path": str(path.relative_to(self.root)), "file_sha256": snapshot._file_sha(path),
                "array_sha256": snapshot._signature(array)["sha256"], "shape": list(array.shape),
                "dtype": str(array.dtype), "payload_bytes": array.nbytes, "finite_entries": array.size,
                "nonfinite_entries": 0, "raw_failure_diagnostic_only": False}
        descriptor = {"schema": snapshot.SPOOL_SCHEMA, "metadata": encode(packet),
            "sparse_payload": payload, "offset_inventory": [{"field": field, "offset": i*2,
                "length": 2, "original_rows_dtype": "int32"} for i, field in enumerate(snapshot.PAIR_FIELDS)],
            "all_finite": True, "raw_failure_diagnostic_only": False}
        if mutate is not None:
            mutate(descriptor)
        sha = write_json(self.root/f"{directory}/packet_0000.json", descriptor)
        # The reader verifies the whole exact index inventory before any payload read.
        records = [{"local_mode_index": i, "original_mode_index": i+2,
                    "descriptor_path": f"{directory}/packet_{i:04d}.json",
                    "descriptor_sha256": sha, "all_finite": True} for i in range(228)]
        manifest = {"schema": snapshot.SPOOL_SCHEMA, "observer_schema": snapshot.OBSERVER_SCHEMA,
            "status": "READY_RAW_PACKETS_UNQUALIFIED", "complete_finite_stream": True,
            "all_finite": True, "failure": None, "expected_mode_count": 228, "recorded_mode_count": 228,
            "factor_count": 0, "PDE_solved": False, "raw_port_qualified": False,
            "frozen_stream_identity": identity, "records": records}
        manifest_sha = write_json(self.root/f"{directory}/raw_packet_manifest.json", manifest)
        return snapshot._FrozenRawReader(self.root, directory, 0, gate, manifest_sha=manifest_sha)

    def test_import_is_isolated_and_numerical_entry_is_deferred(self):
        forbidden = ("src", "petsc4py", "mpi4py", "dolfinx", "ufl", "scipy")
        self.assertFalse(any(name.startswith(forbidden) for name in IMPORTED_NAMES))
        tree = ast.parse(MODULE_PATH.read_text())
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.assertNotIn(getattr(node, "module", None), forbidden)
        forbidden_calls = {"splu", "spilu", "spsolve", "solve", "assemble_matrix", "assemble_vector"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", None))
                self.assertNotIn(name, forbidden_calls)

    def test_exact_sparse_values_readonly_and_backing_release(self):
        reader = self.fixture()
        with reader.packet(0) as (metadata, pairs):
            self.assertEqual(len(pairs), 10)
            rr, vv = pairs["stored_D_sparse"]
            np.testing.assert_array_equal(rr, [3, 7])
            np.testing.assert_array_equal(vv, [0.125+2j, 1e-40-0.25j])
            self.assertFalse(rr.flags.writeable)
            self.assertFalse(vv.flags.writeable)
            owner = vv
            while isinstance(getattr(owner, "base", None), np.ndarray):
                owner = owner.base
            mmap = owner._mmap
            self.assertFalse(mmap.closed)
        self.assertTrue(mmap.closed)

    def test_packet_backing_release_when_consumer_fails(self):
        reader = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "consumer stop"):
            with reader.packet(0) as (_, pairs):
                owner = pairs["stored_C_sparse"][1]
                while isinstance(getattr(owner, "base", None), np.ndarray):
                    owner = owner.base
                mmap = owner._mmap
                raise RuntimeError("consumer stop")
        self.assertTrue(mmap.closed)

    def test_json_allocation_denial_precedes_read(self):
        p = self.root/"blocked.json"
        p.write_text("{}")
        def deny(*args):
            raise RuntimeError("allocation denied")
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(RuntimeError, "allocation denied"):
                snapshot._read_json(self.root, "blocked.json", deny)

    def test_mmap_allocation_denial_precedes_load(self):
        reader = self.fixture()
        _, descriptor = reader.descriptor(0)
        def deny(*args):
            raise RuntimeError("allocation denied")
        with patch.object(np, "load", side_effect=AssertionError("must not mmap")):
            with self.assertRaisesRegex(RuntimeError, "allocation denied"):
                snapshot._load_array(self.root, descriptor["sparse_payload"]["values"], deny, "blocked")

    def test_exact_ten_pairs_reject_reorder_gap_missing_overlap(self):
        for mutation in (lambda d: d["offset_inventory"].reverse(),
                         lambda d: d["offset_inventory"][1].update(offset=3),
                         lambda d: d["offset_inventory"].pop(),
                         lambda d: d["offset_inventory"][1].update(offset=0)):
            with self.subTest(mutation=mutation):
                reader = self.fixture(mutate=mutation)
                with self.assertRaises(ValueError):
                    reader.descriptor(0)

    def test_nonfinite_diagnostic_metadata_cannot_restore(self):
        reader = self.fixture(mutate=lambda d: d["metadata"].update(local_plane_H={"__raw_spool_nonfinite__": "nan"}))
        with self.assertRaises(ValueError):
            reader.descriptor(0)

    def test_second_D_conjugation_has_no_code_path(self):
        tree = ast.parse(MODULE_PATH.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self.assertNotIn(getattr(node.func, "attr", getattr(node.func, "id", None)), ("conj", "conjugate"))

    def test_hash_and_path_changes_fail_closed(self):
        reader = self.fixture()
        (self.root/"raw_twist_0/packet_0000.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            reader.descriptor(0)
        for relative in ("../outside.json", "/tmp/outside.json"):
            with self.assertRaises(ValueError):
                snapshot._bound(self.root, relative)
        outside = self.root.parent/(self.root.name + "-outside.json")
        outside.write_text("{}")
        try:
            (self.root/"escape.json").symlink_to(outside)
            with self.assertRaises(ValueError):
                snapshot._bound(self.root, "escape.json")
        finally:
            outside.unlink()

    def test_npy_bytes_and_dtype_changes_fail_closed(self):
        reader = self.fixture()
        _, d = reader.descriptor(0)
        path = self.root/"arrays/values.npy"
        np.save(path, np.zeros(20, dtype=np.complex128), allow_pickle=False)
        with self.assertRaisesRegex(ValueError, "file hash changed"):
            snapshot._load_array(self.root, d["sparse_payload"]["values"], gate, "tampered")
        descriptor = dict(d["sparse_payload"]["rows"])
        descriptor.update(dtype="int16")
        with self.assertRaisesRegex(ValueError, "payload size"):
            snapshot._load_array(self.root, descriptor, gate, "overflow")

    def test_codec_preserves_signed_zero_and_complex_and_rejects_nonfinite(self):
        original = {"real": -0.0, "complex": complex(-0.0, -0.0)}
        decoded = snapshot._decode_metadata(encode(original))
        self.assertEqual(snapshot._canonical(original), snapshot._canonical(decoded))
        self.assertEqual(np.signbit(decoded["complex"].real), True)
        with self.assertRaises(ValueError):
            snapshot._canonical(snapshot._decode_metadata({"__raw_spool_nonfinite__": "inf"}))

    def test_duplicate_json_keys_fail_closed(self):
        (self.root/"duplicate.json").write_text('{"H":1,"H":2}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            snapshot._read_json(self.root, "duplicate.json", gate)

    def test_source_and_environment_drift_are_rejected(self):
        source = {"head": snapshot.AUTHORITY_HEAD, "branch": "task40extra_dot_parallel_cloud", "dirty": "",
                  "files_sha256": {"src/solvers/physics.py": "immutable", "benchmarks/doc.md": "old-doc"}}
        env = {name: "frozen" for name in ("python", "prefix", "modules", "petsc_scalar_type", "petsc_int_type",
            "petsc_version", "mpi_library", "qualification_manifest_sha256", "qualification_scope")}
        candidate = {**source, "head": "new-docs-only", "files_sha256": {**source["files_sha256"], "benchmarks/doc.md": "new-doc"}}
        self.assertEqual(snapshot._source_environment_gate(source, candidate, env, env)["unchanged_numerical_dependency_count"], 1)
        changed = {**candidate, "files_sha256": {"src/solvers/physics.py": "changed"}}
        with self.assertRaisesRegex(ValueError, "numerical dependency"):
            snapshot._source_environment_gate(source, changed, env, env)
        with self.assertRaisesRegex(ValueError, "environment"):
            snapshot._source_environment_gate(source, candidate, env, {**env, "petsc_int_type": "int64"})

    def historical_fixture(self):
        gauss = {}
        for name in ("top/0", "top/1", "bottom/0", "bottom/1"):
            stem = name.replace("/", "_")
            binary, generated = self.root/(stem + ".so"), self.root/(stem + ".c")
            binary.write_bytes(b"isolated historical binary " + name.encode())
            generated.write_bytes(b"isolated historical generated C " + name.encode())
            gauss[name] = {"loaded_kernel": {
                "schema": "task40extra.loaded-surface-kernel.v1",
                "module_path": str(binary), "binary_sha256": snapshot._file_sha(binary),
                "module_bound_C_path": str(generated), "module_bound_C_sha256": snapshot._file_sha(generated)}}
        return {"gauss": {"compiled_forms_verified": gauss}}

    def test_historical_files_verified_as_bytes_without_loading(self):
        context = self.historical_fixture()
        labels = []
        def admitted(label, facts):
            gate(label, facts)
            self.assertFalse(facts["load_module"])
            self.assertFalse(facts["rebuild_JIT"])
            self.assertEqual(facts["read_chunk_upper_bytes"], 1 << 20)
            labels.append(label)
        with patch.object(importlib.util, "spec_from_file_location", side_effect=AssertionError("must not load binary")):
            receipt = snapshot._verify_historical_surface_files(context, admitted)
        self.assertEqual(len(labels), 8)
        self.assertEqual(receipt["verified_file_references"], 8)
        self.assertEqual(set(receipt["records"]), {"top/0", "top/1", "bottom/0", "bottom/1"})
        self.assertTrue(receipt["historical_kernel_provenance_retained"])
        self.assertFalse(receipt["new_volume_kernel_qualified"])
        self.assertFalse(receipt["new_JIT_performed"])
        for record in receipt["records"].values():
            for file in record.values():
                self.assertEqual(file["expected_sha256"], file["verified_sha256"])

    def test_historical_missing_binary_or_C_file_stops(self):
        for field in ("module_path", "module_bound_C_path"):
            with self.subTest(field=field):
                context = self.historical_fixture()
                Path(context["gauss"]["compiled_forms_verified"]["top/0"]["loaded_kernel"][field]).unlink()
                with self.assertRaisesRegex(FileNotFoundError, "historical primary kernel file is missing"):
                    snapshot._verify_historical_surface_files(context, gate)

    def test_historical_mismatched_binary_or_C_file_stops(self):
        for field in ("module_path", "module_bound_C_path"):
            with self.subTest(field=field):
                context = self.historical_fixture()
                Path(context["gauss"]["compiled_forms_verified"]["top/0"]["loaded_kernel"][field]).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "historical primary kernel file hash/identity changed"):
                    snapshot._verify_historical_surface_files(context, gate)

    def test_historical_file_read_admission_precedes_open(self):
        context = self.historical_fixture()
        def denied(*args):
            raise RuntimeError("historical read denied")
        with patch.object(Path, "open", side_effect=AssertionError("must not open")):
            with self.assertRaisesRegex(RuntimeError, "historical read denied"):
                snapshot._verify_historical_surface_files(context, denied)

    def test_historical_missing_primary_record_stops(self):
        context = self.historical_fixture()
        del context["gauss"]["compiled_forms_verified"]["bottom/1"]
        with self.assertRaisesRegex(ValueError, "complete frozen primary Gauss kernel inventory"):
            snapshot._verify_historical_surface_files(context, gate)

    def test_historical_verification_precedes_discrete_and_public_restore(self):
        tree = ast.parse(MODULE_PATH.read_text())
        authority = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SavedQuotientSnapshotAuthority")
        restore = next(n for n in authority.body if isinstance(n, ast.FunctionDef) and n.name == "restore_bundle")
        calls = {getattr(n.func, "id", None): n.lineno for n in ast.walk(restore) if isinstance(n, ast.Call)}
        self.assertLess(calls["_verify_historical_surface_files"], calls["_validate_actual_discrete"])
        self.assertLess(calls["_verify_historical_surface_files"], calls["FullspaceDtnCarrier"])
        self.assertLess(calls["_verify_historical_surface_files"], calls["_build_split_volume_action"])

    def test_snapshot_context_accessor_is_readonly_metadata_only(self):
        authority = snapshot.SavedQuotientSnapshotAuthority.__new__(snapshot.SavedQuotientSnapshotAuthority)
        calls = []
        class MetadataReader:
            def __init__(self, twist):
                self.twist = twist
            def descriptor(self, index):
                calls.append((self.twist, index))
                return {"assembly_context": {"twist": self.twist, "nested": {"values": [1, 2]}}}, {}
        authority._readers = {twist: MetadataReader(twist) for twist in (None, 0, 1)}
        with patch.object(np, "load", side_effect=AssertionError("metadata accessor must not open arrays")):
            for twist in (None, 0, 1):
                context = authority.snapshot_context(twist)
                self.assertEqual(context["twist"], twist)
                self.assertEqual(context["nested"]["values"], (1, 2))
                with self.assertRaises(TypeError):
                    context["nested"]["values"] = ()
            for invalid in (-1, 2, False, 0.0, "0"):
                with self.assertRaises(ValueError):
                    authority.snapshot_context(invalid)
        self.assertEqual(calls, [(None, 0), (0, 0), (1, 0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
