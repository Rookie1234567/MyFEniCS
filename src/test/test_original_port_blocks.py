"""Staged tests, NOT RUN. Actual saved 80-mode original H plus algebra checks."""

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from src.solvers.original_port_blocks import (
    CachedCondensedPortBlock, CachedPortCorrection,
    DenseOriginalPortBlock, DiagonalOriginalPortBlock,
)


MANIFEST_SHA256 = "0694682ff5e3477f50432a022d4fb9db142e58e3d651d3c53ebd3b0e3811b656"
SOURCE_SHA = "c619854a371fdb3330d21747a53a440dd1d427ae"
MODES_SHA256 = "a6e018984902aef4da3377acaf16128ff1de030de6aebb1405fdb112fe5502d0"


def record(name, values):
    if "TASK40EXTRA_H_BLOCK_RECORD" not in os.environ:
        return
    path = Path(os.environ["TASK40EXTRA_H_BLOCK_RECORD"])
    data = json.loads(path.read_text()) if path.exists() else {}
    data[name] = values
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def actual_saved_entries():
    if "TASK40EXTRA_ACTUAL_OPERATOR" not in os.environ:
        pytest.skip("requires an explicit hash-bound actual saved operator")
    from src.solvers.fullspace_dtn_action import FullspaceDtnModeFunctional
    path = Path(os.environ["TASK40EXTRA_ACTUAL_OPERATOR"])
    raw = (path / "export_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(raw)
    assert manifest["source"]["source"]["head"] == SOURCE_SHA
    modes_raw = (path / "ordered_modes.json").read_bytes()
    assert hashlib.sha256(modes_raw).hexdigest() == MODES_SHA256
    modes = json.loads(modes_raw)
    entries = []
    for item, mode in zip(manifest["carrier_entries"], modes, strict=True):
        assert item["index"] == len(entries)
        def actual_array(name):
            descriptor = manifest["arrays"][item[name]]
            file = path / descriptor["path"]
            assert hashlib.sha256(file.read_bytes()).hexdigest() == descriptor["file_sha256"]
            return np.load(file, allow_pickle=False)
        assert item["normalization_h"]["imag"] == 0.0
        entries.append(FullspaceDtnModeFunctional(
            normalization_h=float(item["normalization_h"]["real"]),
            mode_key=(item["index"], mode["side"], mode["m"], mode["n"], mode["polarization"]),
            coupling_rows=actual_array("coupling_rows"),
            coupling_values=actual_array("coupling_values"),
            projection_rows=actual_array("projection_rows"),
            projection_values=actual_array("projection_values"),
            mode_identity=mode,
        ))
    assert len(entries) == 80
    return entries


def test_actual_original_H_arbitrary_complex_multiRHS():
    entries = actual_saved_entries()
    block = DiagonalOriginalPortBlock.from_carrier(entries)
    dense = np.diag(np.asarray([entry.normalization_h for entry in entries], dtype=np.complex128))
    assert dense.dtype == np.dtype(np.complex128)
    rng = np.random.default_rng(400701)
    rhs = rng.normal(size=(80, 5)) + 1j * rng.normal(size=(80, 5))
    defects = []
    for values in (rhs, rhs[:, 0], np.zeros_like(rhs)):
        expected_solve = np.linalg.solve(dense, values)
        expected_apply = dense @ values
        observed_solve, observed_apply = block.solve(values), block.apply(values)
        np.testing.assert_allclose(observed_solve, expected_solve, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(observed_apply, expected_apply, rtol=1e-12, atol=1e-12)
        defects.append({"RHS_shape": list(values.shape),
                        "solve_relative_defect": float(np.linalg.norm(observed_solve-expected_solve)/max(np.linalg.norm(expected_solve), 1e-30)),
                        "apply_relative_defect": float(np.linalg.norm(observed_apply-expected_apply)/max(np.linalg.norm(expected_apply), 1e-30))})
    assert block.audit["resident_numeric_bytes"] == 80 * 16
    assert block.audit["resident_square_arrays"] == 0
    assert block.mode_keys == tuple(entry.mode_key for entry in entries)
    record("actual_80_mode_H", {"source_sha": SOURCE_SHA, "manifest_sha256": MANIFEST_SHA256,
                               "ordered_modes_sha256": MODES_SHA256, "seed": 400701,
                               "defects": defects, "audit": block.audit,
                               "dense_oracle_bytes": dense.nbytes, "PDE_solved": False})


def test_diagonal_path_never_calls_dense_solve_or_diag(monkeypatch):
    entries = actual_saved_entries()
    def forbidden(*args, **kwargs):
        raise AssertionError("diagonal construction/action must not call a dense path")
    monkeypatch.setattr(np.linalg, "solve", forbidden)
    monkeypatch.setattr(np, "diag", forbidden)
    block = DiagonalOriginalPortBlock.from_carrier(entries)
    source = np.ones((80, 3), dtype=np.complex128) * (1 + 2j)
    np.testing.assert_allclose(block.apply(block.solve(source)), source, rtol=1e-12, atol=1e-12)
    assert all(array.ndim == 1 for array in block.numeric_arrays)
    with pytest.raises(MemoryError):
        block.materialize_for_small_oracle(max_bytes=16)


def test_generic_complex_diagonal_semantics():
    # Algebraic supplement, not a physical mode inventory.
    diagonal = np.array([1 + 2j, -3 + 0.2j, 0.004 - 0.003j])
    block = DiagonalOriginalPortBlock(diagonal, [(i, "algebraic") for i in range(3)])
    source = np.array([[1 + 1j, 2 - 3j], [3 + 2j, -1j], [0.3, 2j]])
    np.testing.assert_allclose(block.solve(source), np.linalg.solve(np.diag(diagonal), source), rtol=1e-12, atol=1e-12)
    assert np.iscomplexobj(block.diagonal)
    assert not block.diagonal.flags.writeable


def test_explicit_nonHermitian_nondiagonal_fallback():
    dense = np.array([[2 + 1j, 0.4 - 0.7j], [0.8 + 0.2j, 3 - 0.4j]])
    keys = [(0, "generic"), (1, "generic")]
    block = DenseOriginalPortBlock(dense, keys, reason="actual nondiagonal Hlocal contract", max_bytes=64)
    rhs = np.array([[1 + 1j, 2j], [4 - 0.5j, 1]])
    np.testing.assert_allclose(block.solve(rhs), np.linalg.solve(dense, rhs), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(block.apply(rhs), dense @ rhs, rtol=1e-12, atol=1e-12)
    with pytest.raises(MemoryError):
        DenseOriginalPortBlock(dense, keys, reason="bounded fallback", max_bytes=63)


def test_Hhat_action_preserves_original_H_and_borrows_cached_factors():
    original = DiagonalOriginalPortBlock.from_carrier(actual_saved_entries())
    rng = np.random.default_rng(400702)
    corrections = []
    dense = original.materialize_for_small_oracle(max_bytes=80 * 80 * 16)
    for ports in (np.array([0, 3, 7]), np.array([3, 11])):
        ni = 4
        di = rng.normal(size=(len(ports), ni)) + 1j * rng.normal(size=(len(ports), ni))
        xib = rng.normal(size=(ni, len(ports))) + 1j * rng.normal(size=(ni, len(ports)))
        dense[np.ix_(ports, ports)] += di @ xib
        for array in (ports, di, xib):
            array.flags.writeable = False
        corrections.append(CachedPortCorrection(ports, di, xib))
    block = CachedCondensedPortBlock(original, corrections)
    source = rng.normal(size=(80, 3)) + 1j * rng.normal(size=(80, 3))
    np.testing.assert_allclose(block.apply(source), dense @ source, rtol=1e-12, atol=1e-12)
    # The bridge still solves ORIGINAL H, not this Hhat.
    np.testing.assert_allclose(original.solve(source), source / original.diagonal[:, None], rtol=0, atol=0)
    assert block.audit["new_square_Hhat_arrays"] == 0
    assert block.audit["new_local_LU_solves_per_apply"] == 0
    assert block.numeric_arrays[1] is corrections[0].port_indices
    assert block.numeric_arrays[2] is corrections[0].Di
    assert block.numeric_arrays[3] is corrections[0].XiB
    record("synthetic_Hhat_algebraic_supplement", {
        "seed": 400702, "relative_action_defect": float(np.linalg.norm(block.apply(source)-dense@source)/max(np.linalg.norm(dense@source), 1e-30)),
        "audit": block.audit, "actual_p6_condensation_qualified": False,
    })


def test_Hhat_with_no_interior_port_terms_is_exactly_original_H():
    original = DiagonalOriginalPortBlock.from_carrier(actual_saved_entries())
    block = CachedCondensedPortBlock(original)
    source = np.arange(80, dtype=np.complex128) * (1 - 0.3j)
    np.testing.assert_array_equal(block.apply(source), original.apply(source))
    assert block.audit["correction_count"] == 0


def test_invalid_diagonal_is_not_silently_approximated():
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock([1, 0], [(0,), (1,)])
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock([1, 2], [(0,), (0,)])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), complex(1, float("inf"))])
def test_nonfinite_diagonal_or_rhs_is_rejected(bad):
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock([bad], [(0,)])
    block = DiagonalOriginalPortBlock([1, 2], [(0,), (1,)])
    for operation in (block.apply, block.solve):
        with pytest.raises(ValueError):
            operation([bad, 1])


@pytest.mark.parametrize("bad", [np.zeros((2, 2)), np.array([]), np.array(2)])
def test_diagonal_shape_is_rejected(bad):
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock(bad, [(0,), (1,)])


@pytest.mark.parametrize("bad", [np.zeros(3), np.zeros((3, 2)), np.zeros((2, 1, 1)), np.array(1)])
def test_RHS_shape_is_rejected(bad):
    block = DiagonalOriginalPortBlock([1, 2], [(0,), (1,)])
    for operation in (block.apply, block.solve):
        with pytest.raises(ValueError):
            operation(bad)


def test_actual_carrier_order_identity_is_required():
    from dataclasses import replace
    entries = actual_saved_entries()
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock.from_carrier([entries[1], entries[0], *entries[2:]])
    with pytest.raises(ValueError):
        DiagonalOriginalPortBlock.from_carrier([replace(entries[0], normalization_h=2 * entries[0].normalization_h), *entries[1:]])
    with pytest.raises(TypeError):
        DiagonalOriginalPortBlock.from_carrier([object()])


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_generic_fallback_nonfinite_is_rejected(bad):
    with pytest.raises(ValueError):
        DenseOriginalPortBlock([[bad]], [(0,)], reason="negative test", max_bytes=16)
