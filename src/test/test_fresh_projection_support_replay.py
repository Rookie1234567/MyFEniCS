"""Synthetic all-eight saved projection contracts; no actual saved arrays."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest
from scipy import sparse

from src.solvers import fresh_projection_support_replay as replay


@pytest.fixture(scope="module")
def classes():
    repo = Path(os.environ.get("TEST_REPLAY_REPO", Path.cwd()))
    candidate_path = Path(os.environ.get("TEST_REPLAY_NEW_SOURCE", repo / "src/solvers/bounded_compact_q_projection.py"))
    candidate_bytes = candidate_path.read_bytes()
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()
    new = replay.load_verified_accumulator(candidate_bytes, expected_sha256=candidate_sha)
    old_bytes = subprocess.run(["git", "cat-file", "blob", replay.BASELINE_GIT_BLOB],
                               cwd=repo, check=True, capture_output=True).stdout
    old = replay.load_verified_accumulator(old_bytes, expected_sha256=replay.BASELINE_SHA256,
                                           git_blob=replay.BASELINE_GIT_BLOB)
    return old, new, {"scope": replay.SCOPE, "source_git_head": "1" * 40,
                     "candidate_source_sha256": candidate_sha,
                     "worker_report_sha256": "2" * 64, "independent_checker_sha256": "3" * 64,
                     "synthetic": True}


def synthetic():
    rng = np.random.default_rng(20261004)
    arrays, descriptors = {}, {}
    def ref(name, value, dtype=None):
        value = np.array(value, dtype=dtype, copy=True, order="C")
        value.flags.writeable = False
        arrays[name] = value
        descriptors[name] = {"path": name + ".npy", "shape": list(value.shape),
                             "dtype": str(value.dtype), "payload_bytes": value.nbytes,
                             "file_sha256": hashlib.sha256(name.encode()).hexdigest()}
        return {"name": name, "shape": list(value.shape), "dtype": str(value.dtype),
                "numeric_bytes": value.nbytes, "sha256": replay._numeric_sha(value),
                "callback_reference": descriptors[name].copy()}
    def csr(prefix, matrix):
        matrix = sparse.csr_matrix(matrix, dtype=np.complex128)
        matrix.sort_indices()
        return {"shape": list(matrix.shape),
                **{key: ref(prefix + "_" + key, getattr(matrix, key)) for key in ("data", "indices", "indptr")}}
    def complex_values(shape):
        return rng.normal(size=shape) + 1j * rng.normal(size=shape)
    snapshots, blocks, crosses = [], [], []
    for twist, widths in ((0, (9, 11)), (1, (10, 12))):
        maps = []
        for width in widths:
            matrix = complex_values((6, width))
            matrix[:, 2:-2] = 0  # structural gaps exercise exact support skipping
            maps.append(sparse.csr_matrix(matrix))
        prefix = f"twist{twist}"
        qmaps = [csr(prefix + f"_map{i}", matrix) for i, matrix in enumerate(maps)]
        recipes, dense = [], []
        def recipe(label, rows, cols, kind, **data):
            item = {"label": label, "rows": ref(prefix + label + "rows", rows, np.int32),
                    "cols": ref(prefix + label + "cols", cols, np.int32), "kind": kind}
            item.update({key: ref(prefix + label + key, value, np.complex128) for key, value in data.items()})
            recipes.append(item)
            exact = data["Di"] @ data["XiB"] if kind == "correction" else np.diag(data["values"]) if kind == "diagonal" else data["values"]
            dense.append((np.asarray(rows), np.asarray(cols), exact))
        recipe("ports/H_original", [5], [5], "diagonal", values=np.array([2+.25j]))
        recipe("volume/cell/0", [0, 2, 4], [0, 2, 4], "dense", values=complex_values((3, 3)))
        recipe("volume/cell/1", [1, 3], [1, 3], "dense", values=complex_values((2, 2)))
        recipe("cell/C_hat/1", [1, 3], [5], "dense", values=complex_values((2, 1)))
        recipe("cell/-D_hat/1", [5], [1, 3], "dense", values=complex_values((1, 2)))
        recipe("cell/Hhat_correction/1", [5], [5], "correction", Di=complex_values((1, 3)), XiB=complex_values((3, 1)))
        recipe("direct/C/port/0", [0, 4], [5], "dense", values=complex_values((2, 1)))
        recipe("direct/-D/port/0", [5], [0, 4], "dense", values=complex_values((1, 2)))
        snapshot = {"twist": twist, "q_indices": [twist, twist+2], "port_count": 1,
                    "qmaps": qmaps, "recipes": recipes,
                    "cells": [{"ports": ref(prefix + "cell0_ports", [], np.int32)},
                              {"ports": ref(prefix + "cell1_ports", [0], np.int32)}]}
        snapshots.append(snapshot)
        for p, q in replay.PAIRS:
            gp, gq = snapshot["q_indices"][p], snapshot["q_indices"][q]
            result = np.zeros((widths[p], widths[q]), complex)
            for rows, cols, values in dense:
                result += maps[p].toarray()[rows].conj().T @ values @ maps[q].toarray()[cols]
            target = sparse.csr_matrix(result)
            target.eliminate_zeros()
            prefix_target = f"q_{gp}_S" if p == q else f"cross_{gp}_{gq}"
            csr(prefix_target, target)
            record = {"csr_prefix": prefix_target, **replay.csr_fingerprint(target)}
            record.update({"q": gp} if p == q else {"p": gp, "q": gq})
            (blocks if p == q else crosses).append(record)
    report = {"artifacts": descriptors, "local_compact_snapshots": snapshots,
              "reformed_blocks": sorted(blocks, key=lambda b:b["q"]), "cross_blocks": crosses}
    opened = []
    def load(reference):
        name = reference if isinstance(reference, str) else reference["name"]
        opened.append(name)
        return arrays[name]
    return report, arrays, load, opened


def callbacks():
    events, gates = [], []
    def gate(label, facts):
        gates.append((label, facts))
    def event(record, encoded):
        assert encoded == replay._json_bytes(record) + b"\n"
        events.append((record, encoded))
    return gate, event, gates, events


def test_complete_all8_complex_dense_diagonal_factorized_direct_oracle(classes, monkeypatch):
    _, new, metadata = classes
    report, _, load, _ = synthetic()
    gate, event, gates, events = callbacks()
    def forbidden(*args, **kwargs):
        raise AssertionError("FE/new factor/recovery path called")
    import scipy.linalg
    import scipy.sparse.linalg
    monkeypatch.setattr(scipy.linalg, "lu_factor", forbidden)
    monkeypatch.setattr(scipy.linalg, "lu_solve", forbidden)
    monkeypatch.setattr(scipy.sparse.linalg, "splu", forbidden)
    result = replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
        allocation_gate=gate, event=event, source_metadata=metadata, tile_width=2, max_owned_bytes=1 << 20)
    assert result["passed"] and result["all8_complete"] and len(result["pairs"]) == 8
    assert all(p["recipe_count"] == 8 and p["peak_projection_owned_upper_bytes"] <= 1 << 20 for p in result["pairs"])
    assert all(p["owned_diagonal_reservation_bytes"] == 16 for p in result["pairs"])
    assert result["event_count"] == len(events) and result["log_bytes"] == sum(len(e[1]) for e in events)
    assert result["FE_calls"] == result["JIT_calls"] == result["new_factor_calls"] == result["PDE_calls"] == 0
    for pair in result["pairs"]:
        assert all(check["all_entries_checked"] for check in pair["checks"])
        assert len(pair["checks"]) == (2 if pair["p"] == pair["q"] else 4)
    assert any(facts.get("before_diagonal_copy") for _, facts in gates)
    assert all(record["name"].startswith(("twist", "q_", "cross_"))
               for record, _ in events if record["kind"] == "saved_array_verified")


def test_matched_subset_uses_verified_git_blob_and_bitwise_identical_order(classes):
    old, new, metadata = classes
    report, _, load, _ = synthetic()
    gate, event, _, _ = callbacks()
    result = replay.compare_matched_subset(report, old_accumulator_class=old,
        new_accumulator_class=new, load_array=load, allocation_gate=gate, event=event,
        source_metadata=metadata, tile_width=2, max_owned_bytes=1 << 20)
    assert result["passed"] and all(p["bitwise_CSR_equal"] for p in result["pairs"])
    assert result["baseline"]["git_blob"] == replay.BASELINE_GIT_BLOB
    assert result["runs"][0]["array_reads"] == result["runs"][1]["array_reads"]
    assert result["runs"][0]["event_count"] > result["runs"][1]["event_count"]
    assert all(r["wall_seconds"] > 0 and r["log_bytes"] > 0 for r in result["runs"])
    assert result["old_full_replay_permitted"] is False
    with pytest.raises(ValueError, match="only first two/four"):
        replay.select_matched_recipe_subset(report["local_compact_snapshots"][0], volume_cells=40)


def test_gate_denial_precedes_saved_callback(classes):
    _, new, metadata = classes
    report, _, load, opened = synthetic()
    def denied(label, facts):
        raise MemoryError("read denied")
    with pytest.raises(MemoryError, match="read denied"):
        replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
            allocation_gate=denied, event=lambda *args:None, source_metadata=metadata)
    assert opened == []


@pytest.mark.parametrize("tamper", ["labels", "ref_shape", "file_binding", "q_pair"])
def test_metadata_inventory_rejects_before_any_saved_open(classes, tamper):
    _, new, metadata = classes
    report, _, load, opened = synthetic()
    if tamper == "labels":
        report["local_compact_snapshots"][0]["recipes"].pop()
    elif tamper == "ref_shape":
        report["local_compact_snapshots"][0]["recipes"][0]["values"]["shape"] = [2]
    elif tamper == "file_binding":
        report["local_compact_snapshots"][0]["recipes"][0]["values"]["callback_reference"]["file_sha256"] = "0" * 64
    else:
        report["local_compact_snapshots"][1]["q_indices"] = [1, 2]
    with pytest.raises(ValueError):
        replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
            allocation_gate=lambda *args:None, event=lambda *args:None, source_metadata=metadata)
    assert opened == []


@pytest.mark.parametrize("tamper", ["numeric", "nonfinite", "writeable"])
def test_actual_read_validation_prevents_projection(classes, tamper):
    _, new, metadata = classes
    report, arrays, load, _ = synthetic()
    key = "q_0_S_data"
    value = arrays[key].copy()
    if tamper == "nonfinite":
        value[0] = np.nan
    elif tamper == "numeric":
        # First actual snapshot read carrying a numeric hash is the q map.
        key = "twist0_map0_data"
        value = arrays[key].copy()
        value[0] += 1
    if tamper != "writeable":
        value.flags.writeable = False
    arrays[key] = value
    with pytest.raises(ValueError, match="numeric SHA|nonfinite|readonly"):
        replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
            allocation_gate=lambda *args:None, event=lambda *args:None, source_metadata=metadata)


def test_cross_difference_uses_both_diagonal_norms_and_maximum():
    actual = sparse.csr_matrix([[1e-10+1e-10j, 0], [0, 0]], dtype=complex)
    expected = sparse.csr_matrix((2, 2), dtype=complex)
    checks = replay.compare_complete_csr(actual, expected, diagonal_scales=(100, 1))
    assert [check["passed"] for check in checks] == [True, False, True, False]
    zero = replay.compare_complete_csr(actual, expected, diagonal_scales=(0, 100))
    assert not zero[0]["passed"] and not zero[2]["passed"]
    identical = replay.compare_complete_csr(expected, expected)
    assert all(check["passed"] for check in identical)


def test_fortran_saved_recipe_borrowing_preserves_C_order_numeric_hash(classes):
    _, new, metadata = classes
    report, arrays, load, _ = synthetic()
    converted = 0
    for name, value in list(arrays.items()):
        if value.ndim == 2:
            array = np.array(value, order="F", copy=True)
            array.flags.writeable = False
            assert replay._numeric_sha(value) == replay._numeric_sha(array)
            arrays[name] = array
            converted += 1
    assert converted
    result = replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
        allocation_gate=lambda *args:None, event=lambda *args:None,
        source_metadata=metadata, tile_width=2, max_owned_bytes=1 << 20)
    assert result["passed"]


def test_new_source_and_git_blob_must_verify_before_exec(classes):
    _, new, metadata = classes
    bad = b'raise AssertionError("executed unverified source")\n'
    with pytest.raises(ValueError, match="source SHA"):
        replay.load_verified_accumulator(bad, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="Git blob"):
        replay.load_verified_accumulator(bad, expected_sha256=hashlib.sha256(bad).hexdigest(), git_blob="0" * 40)
    report, _, load, opened = synthetic()
    changed = copy.deepcopy(metadata)
    changed["candidate_source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="verified source bytes"):
        replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
            allocation_gate=lambda *args:None, event=lambda *args:None, source_metadata=changed)
    assert opened == []


def test_complete_replay_recomputes_failure_instead_of_trusting_saved_status(classes):
    _, new, metadata = classes
    report, arrays, load, _ = synthetic()
    report["status"] = "FRESH_PAIRED_COMPACT_FULL3D_INVERSE_PASS"
    key = "q_0_S_data"
    value = arrays[key].copy()
    value[0] += 0.5j
    value.flags.writeable = False
    arrays[key] = value
    result = replay.replay_saved_all8(report, accumulator_class=new, load_array=load,
        allocation_gate=lambda *args:None, event=lambda *args:None,
        source_metadata=metadata, tile_width=2, max_owned_bytes=1 << 20)
    assert result["all8_complete"] and not result["passed"]
    assert result["status"] == "ALL8_SAVED_PROJECTION_REPLAY_FAILED"
    failed = [pair for pair in result["pairs"] if not pair["passed"]]
    assert len(failed) == 1 and failed[0]["p"] == failed[0]["q"] == 0
