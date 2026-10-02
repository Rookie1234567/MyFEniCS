"""NEW_UNQUALIFIED pure unittest definitions; execution needs later approval.

Synthetic complex non-Hermitian algebra only. These tests do not import P6,
PETSc, FEniCS or pytest and do not qualify a PDE or a physical fixture.
"""

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np


ORIGINAL_SHA256 = "de6940522d97343484851f7abe75dbb6302a3b64be2f0903cee3361bc9816645"


def source_paths(test_file):
    """Select repository sources at src/test, or the explicit staging pair."""

    test_file = Path(test_file)
    if test_file.parent.name == "test" and test_file.parent.parent.name == "src":
        solvers = test_file.parents[2] / "src/solvers"
        return solvers / "original_port_blocks.py", solvers / "retained_port_block_layout.py"
    staging = test_file.parent
    workspace = staging.parents[1]
    return (workspace / "task40extra_cloud/recovered_v15/src/solvers/original_port_blocks.py",
            staging / "NEW_UNQUALIFIED/src/solvers/retained_port_block_layout.py")


ORIGINAL, HELPER = source_paths(Path(__file__).resolve())


def load_candidate():
    """Import only the two exact pure modules into an isolated package."""

    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != ORIGINAL_SHA256:
        raise RuntimeError("exact restored original_port_blocks source identity differs")
    name = "retained_h_reconstruction_candidate"
    package = ModuleType(name)
    package.__path__ = [str(HELPER.parent)]
    sys.modules[name] = package
    modules = []
    for suffix, path in (("original_port_blocks", ORIGINAL), ("retained_port_block_layout", HELPER)):
        spec = importlib.util.spec_from_file_location(name + "." + suffix, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return tuple(modules)


def readonly(values, dtype=np.complex128):
    result = np.array(values, dtype=dtype, copy=True)
    result.flags.writeable = False
    return result


def fixture(blocks):
    """Cache XiB, while preserving separate Vii/Bi for the dense oracle."""

    rng = np.random.default_rng(400203)
    diagonal = np.array([1.2 + .4j, 2.3 - .7j, -.8 + 1.1j,
                         3.1 + .2j, .7 - 1.3j, 1.9 + .8j, -.6 - .9j])
    keys = [(i, "top" if i % 2 else "bottom", i - 3, i % 3 - 1,
             "TE" if i % 2 else "TM") for i in range(len(diagonal))]
    original = blocks.DiagonalOriginalPortBlock(diagonal, keys)
    cells = []
    oracle_terms = []
    for indices, ni in (([0, 2, 5, 6], 3), ([], 3), ([2, 3], 4)):
        ports = readonly(indices, np.int32)
        vi = rng.normal(size=(ni, ni)) + 1j * rng.normal(size=(ni, ni))
        vi += (4.0 + .2j) * np.eye(ni)
        bi = rng.normal(size=(ni, len(ports))) + 1j * rng.normal(size=(ni, len(ports)))
        di = 2.0 * (rng.normal(size=(len(ports), ni)) + 1j * rng.normal(size=(len(ports), ni)))
        xib = np.linalg.solve(vi, bi)
        cells.append(SimpleNamespace(ports=ports, Di=readonly(di), XiB=readonly(xib), Hlocal=None))
        oracle_terms.append((ports, vi.copy(), bi.copy(), di.copy()))
    probes = rng.normal(size=(len(diagonal), 3)) + 1j * rng.normal(size=(len(diagonal), 3))
    return original, tuple(cells), tuple(oracle_terms), probes


def independent_dense(original, oracle_terms):
    """Assemble from Vii/Bi, never from the candidate's cached XiB."""

    dense = np.diag(original.diagonal).astype(np.complex128)
    for ports, vi, bi, di in oracle_terms:
        correction = di @ np.linalg.solve(vi, bi)
        for local_i, port_i in enumerate(ports):
            for local_j, port_j in enumerate(ports):
                dense[port_i, port_j] += correction[local_i, local_j]
    return dense


def relative_defect(actual, expected):
    scale = np.linalg.norm(expected)
    defect = np.linalg.norm(actual - expected)
    return defect / scale if scale else (0.0 if defect == 0 else float("inf"))


def forbidden(*_args, **_kwargs):
    raise AssertionError("candidate called a forbidden materialization/solve")


class MatmulGuard(np.ndarray):
    """Reject Di@XiB while permitting Di@(XiB@vector/multiRHS)."""

    def __new__(cls, source):
        value = np.asarray(source).view(cls)
        value.forbidden_operand = None
        value.flags.writeable = False
        return value

    def __array_finalize__(self, source):
        self.forbidden_operand = getattr(source, "forbidden_operand", None)

    def __matmul__(self, other):
        if other is self.forbidden_operand:
            raise AssertionError("candidate formed the square Di@XiB correction")
        return super().__matmul__(other)


class CachedPortReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks, cls.helper = load_candidate()

    def setUp(self):
        self.original, self.cells, self.oracle_terms, self.probes = fixture(self.blocks)

    def build(self, cells=None, original=None):
        return self.helper.build_cached_port_representation(
            self.original if original is None else original,
            self.cells if cells is None else cells,
        )

    def identity(self, condensed, original=None):
        return self.helper.port_block_representation_identity(
            self.original if original is None else original, condensed,
            layout=self.helper.RESEARCH_PORT_LAYOUT,
        )

    def test_portable_source_selection_preserves_explicit_staging_fallback(self):
        original, helper = source_paths("checkout/src/test/test_retained_port_block_layout.py")
        self.assertEqual(original, Path("checkout/src/solvers/original_port_blocks.py"))
        self.assertEqual(helper, Path("checkout/src/solvers/retained_port_block_layout.py"))
        original, helper = source_paths("workspace/recovery_staging/retained_H_reconstruction/test_retained_port_block_layout.py")
        self.assertEqual(original, Path("workspace/task40extra_cloud/recovered_v15/src/solvers/original_port_blocks.py"))
        self.assertEqual(helper, Path("workspace/recovery_staging/retained_H_reconstruction/NEW_UNQUALIFIED/src/solvers/retained_port_block_layout.py"))

    def test_constants_and_returned_original_identity(self):
        self.assertEqual(self.helper.LEGACY_PORT_LAYOUT, "dense_legacy")
        self.assertEqual(self.helper.RESEARCH_PORT_LAYOUT, "cached_representation_research")
        original, condensed = self.build()
        self.assertIs(original, self.original)
        self.assertIs(condensed.original_h, original)
        self.assertIsInstance(condensed, self.blocks.CachedCondensedPortBlock)

    def test_material_complex_nonhermitian_action_against_independent_dense(self):
        dense = independent_dense(self.original, self.oracle_terms)
        correction = dense - np.diag(self.original.diagonal)
        self.assertGreater(np.linalg.norm(correction), 1.0)
        self.assertGreater(np.linalg.norm(dense - dense.conj().T), 1.0)
        self.assertGreater(np.linalg.norm(self.oracle_terms[0][3] - self.oracle_terms[0][2].conj().T), 1.0)
        _, condensed = self.build()
        for rhs in (self.probes, self.probes[:, 0], np.zeros_like(self.probes)):
            with self.subTest(shape=rhs.shape):
                self.assertLess(relative_defect(condensed.apply(rhs), dense @ rhs), 1e-12)

    def test_original_h_solve_is_materially_distinct_from_hhat_solve(self):
        dense = independent_dense(self.original, self.oracle_terms)
        original, _ = self.build()
        expected = np.linalg.solve(np.diag(original.diagonal), self.probes)
        observed = original.solve(self.probes)
        np.testing.assert_allclose(observed, expected, rtol=1e-12, atol=1e-12)
        self.assertGreater(relative_defect(observed, np.linalg.solve(dense, self.probes)), .1)

    def test_exact_borrowed_owner_and_nonempty_correction_order(self):
        _, condensed = self.build()
        self.assertEqual(len(condensed._corrections), 2)
        self.assertEqual(len(condensed._retained_cell_port_inventory), 3)
        for correction, cell in zip(condensed._corrections, (self.cells[0], self.cells[2]), strict=True):
            self.assertIs(correction.port_indices, cell.ports)
            self.assertIs(correction.Di, cell.Di)
            self.assertIs(correction.XiB, cell.XiB)
        for retained, cell in zip(condensed._retained_cell_port_inventory, self.cells, strict=True):
            self.assertIs(retained.ports, cell.ports)
            self.assertIs(retained.Di, cell.Di)
            self.assertIs(retained.XiB, cell.XiB)
            self.assertIs(retained.Hlocal, cell.Hlocal)
        self.assertIs(condensed.numeric_arrays[0], self.original.numeric_arrays[0])
        self.assertEqual(len(condensed.numeric_arrays), 7)

    def test_none_hlocal_never_allocates_a_square_or_uses_a_new_solve(self):
        expected = independent_dense(self.original, self.oracle_terms) @ self.probes
        guarded = []
        for cell in self.cells:
            di, xib = MatmulGuard(cell.Di), MatmulGuard(cell.XiB)
            di.forbidden_operand = xib
            guarded.append(SimpleNamespace(ports=cell.ports, Di=di, XiB=xib, Hlocal=None))
        with patch.object(np, "zeros", forbidden), patch.object(np, "diag", forbidden), \
                patch.object(np.linalg, "solve", forbidden), patch.object(np.linalg, "inv", forbidden):
            original, condensed = self.build(tuple(guarded))
            np.testing.assert_allclose(condensed.apply(self.probes), expected, rtol=1e-12, atol=1e-12)
            original.solve(self.probes)
            identity = self.identity(condensed)
        self.assertTrue(all(cell.Hlocal is None for cell in condensed._retained_cell_port_inventory))
        self.assertEqual(identity["backing_inventory"]["new_helper_owned_numeric_arrays"], 0)
        self.assertFalse(hasattr(condensed, "_Hhat"))
        self.assertFalse(hasattr(condensed, "_H_p"))
        self.assertEqual(condensed.audit["new_local_LU_solves_per_apply"], 0)
        self.assertEqual(condensed.audit["new_square_Hhat_arrays"], 0)

    def test_helper_never_reads_bi_or_local_factor(self):
        class CachedOnlyCell:
            @property
            def Bi(self):
                return forbidden()

            @property
            def interior_lu(self):
                return forbidden()
        cells = []
        for original in self.cells:
            cell = CachedOnlyCell()
            for name in ("ports", "Di", "XiB", "Hlocal"):
                setattr(cell, name, getattr(original, name))
            cells.append(cell)
        _, condensed = self.build(cells)
        np.testing.assert_allclose(condensed.apply(self.probes), independent_dense(self.original, self.oracle_terms) @ self.probes)

    def test_generator_is_consumed_once_with_every_zero_cell(self):
        visits = []
        def cells():
            for index, cell in enumerate(self.cells):
                visits.append(index)
                yield cell
        _, condensed = self.build(cells())
        self.assertEqual(visits, [0, 1, 2])
        self.assertEqual(self.identity(condensed)["all_cell_count"], 3)

    def test_no_cells_and_only_empty_cells_are_explicitly_distinct(self):
        _, no_cells = self.build(())
        _, empty_cell = self.build((self.cells[1],))
        np.testing.assert_array_equal(no_cells.apply(self.probes), self.original.apply(self.probes))
        np.testing.assert_array_equal(empty_cell.apply(self.probes), self.original.apply(self.probes))
        self.assertNotEqual(self.identity(no_cells)["numerical_identity_sha256"],
                            self.identity(empty_cell)["numerical_identity_sha256"])

    def test_exact_zero_hlocal_is_borrowed_and_hashed(self):
        cell = SimpleNamespace(**vars(self.cells[0]))
        cell.Hlocal = readonly(np.zeros((len(cell.ports), len(cell.ports))))
        _, baseline = self.build()
        _, candidate = self.build((cell, *self.cells[1:]))
        np.testing.assert_array_equal(candidate.apply(self.probes), baseline.apply(self.probes))
        identity = self.identity(candidate)
        self.assertIn("cell/0/Hlocal", identity["cell_array_sha256"])
        self.assertIs(candidate._retained_cell_port_inventory[0].Hlocal, cell.Hlocal)
        self.assertNotEqual(identity["numerical_identity_sha256"], self.identity(baseline)["numerical_identity_sha256"])

    def test_any_nonzero_hlocal_stops_even_with_dense_original(self):
        dense = self.blocks.DenseOriginalPortBlock(np.diag(self.original.diagonal), self.original.mode_keys,
                                                  reason="explicit bounded synthetic fallback", max_bytes=7 * 7 * 16)
        for value in (1.0 + 2.0j, 1e-250):
            cell = SimpleNamespace(**vars(self.cells[0]))
            hlocal = np.zeros((len(cell.ports), len(cell.ports)), dtype=np.complex128)
            hlocal[0, 1] = value
            cell.Hlocal = readonly(hlocal)
            for original in (self.original, dense):
                with self.subTest(value=value, original=type(original).__name__), self.assertRaises(NotImplementedError):
                    self.build((cell, *self.cells[1:]), original)

    def test_explicit_complex_dense_original_is_preserved(self):
        dense = np.diag(self.original.diagonal)
        dense[0, 4] = .6 - .8j
        original = self.blocks.DenseOriginalPortBlock(dense, self.original.mode_keys,
                                                     reason="bounded nondiagonal test", max_bytes=dense.nbytes)
        returned, condensed = self.build(original=original)
        self.assertIs(returned, original)
        expected = independent_dense(self.original, self.oracle_terms) + dense - np.diag(self.original.diagonal)
        np.testing.assert_allclose(condensed.apply(self.probes), expected @ self.probes, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(original.solve(self.probes), np.linalg.solve(dense, self.probes))
        self.assertEqual(self.identity(condensed, original)["original_H_kind"], "explicit_generic_dense_original_H")

    def test_every_array_is_validated_on_empty_cells(self):
        for name in ("ports", "Di", "XiB"):
            cell = SimpleNamespace(**vars(self.cells[1]))
            value = getattr(cell, name).copy()
            value.flags.writeable = True
            setattr(cell, name, value)
            with self.subTest(field=name), self.assertRaises(ValueError):
                self.build((self.cells[0], cell, self.cells[2]))
        missing = SimpleNamespace(ports=self.cells[1].ports, Di=self.cells[1].Di, Hlocal=None)
        with self.assertRaises(TypeError):
            self.build((missing,))
        uncached = SimpleNamespace(**vars(self.cells[1]))
        uncached.XiB = None
        with self.assertRaises(TypeError):
            self.build((uncached,))

    def test_invalid_ports_shape_dtype_and_range_are_rejected(self):
        for ports in (readonly([0, 0], np.int32), readonly([-1, 2], np.int32),
                      readonly([2, 7], np.int32), readonly([2, 3], np.float64),
                      readonly([[2, 3]], np.int32)):
            cell = SimpleNamespace(**vars(self.cells[2]))
            cell.ports = ports
            with self.subTest(ports=ports), self.assertRaises(ValueError):
                self.build((cell,))

    def test_every_nonfinite_complex_array_is_rejected(self):
        for name in ("Di", "XiB", "Hlocal"):
            for bad in (float("nan"), float("inf"), complex(1, float("inf"))):
                cell = SimpleNamespace(**vars(self.cells[0]))
                value = np.zeros((4, 4), dtype=np.complex128) if name == "Hlocal" else getattr(cell, name).copy()
                value.flat[0] = bad
                value.flags.writeable = False
                setattr(cell, name, value)
                with self.subTest(field=name, bad=bad), self.assertRaises(ValueError):
                    self.build((cell,))

    def test_wrong_dtype_shape_or_writeability_is_rejected(self):
        for name in ("Di", "XiB", "Hlocal"):
            template = np.zeros((4, 4), dtype=np.complex128) if name == "Hlocal" else getattr(self.cells[0], name)
            for kind in ("real", "complex64", "one_dimensional", "wrong_shape", "writeable", "list"):
                value = template.copy()
                if kind == "real":
                    value = value.real.astype(np.float64)
                elif kind == "complex64":
                    value = value.astype(np.complex64)
                elif kind == "one_dimensional":
                    value = value.ravel()
                elif kind == "wrong_shape":
                    value = value[:-1]
                elif kind == "list":
                    value = value.tolist()
                if isinstance(value, np.ndarray) and kind != "writeable":
                    value.flags.writeable = False
                cell = SimpleNamespace(**vars(self.cells[0]))
                setattr(cell, name, value)
                with self.subTest(field=name, kind=kind), self.assertRaises((TypeError, ValueError)):
                    self.build((cell,))

    def test_array_hashes_match_recovered_evidence_complex_cast_contract(self):
        _, condensed = self.build()
        identity = self.identity(condensed)
        self.assertEqual(list(identity["array_sha256"]), [f"port_block/{i}" for i in range(7)])
        for index, array in enumerate(condensed.numeric_arrays):
            expected = hashlib.sha256(repr((array.shape, "complex128")).encode()
                                      + np.ascontiguousarray(array, dtype=np.complex128).tobytes()).hexdigest()
            self.assertEqual(identity["array_sha256"][f"port_block/{index}"], expected)
        self.assertEqual(len(identity["cell_array_sha256"]), 9)
        self.assertEqual(identity["Hhat_recipe"], "original_H+sum(scatter(Di@(XiB@gather(alpha))))")
        self.assertEqual(identity["ordered_mode_keys"], [list(key) for key in self.original.mode_keys])
        json.dumps(identity, allow_nan=False)

    def test_mode_keys_original_h_and_every_cell_factor_bind_numerical_identity(self):
        _, baseline = self.build()
        expected = self.identity(baseline)["numerical_identity_sha256"]
        for name in ("ports", "Di", "XiB"):
            cell = SimpleNamespace(**vars(self.cells[0]))
            values = getattr(cell, name).copy()
            if name == "ports":
                values[[0, 1]] = values[[1, 0]]
            else:
                values.flat[0] += .5 + .4j
            values.flags.writeable = False
            setattr(cell, name, values)
            _, candidate = self.build((cell, *self.cells[1:]))
            with self.subTest(field=name):
                self.assertNotEqual(self.identity(candidate)["numerical_identity_sha256"], expected)
        keys = list(self.original.mode_keys)
        keys[0] = (0, "bottom", -3, 19, "TM")
        for original in (self.blocks.DiagonalOriginalPortBlock(self.original.diagonal, keys),
                         self.blocks.DiagonalOriginalPortBlock(self.original.diagonal * (1 + .1j), self.original.mode_keys)):
            _, candidate = self.build(original=original)
            self.assertNotEqual(self.identity(candidate, original)["numerical_identity_sha256"], expected)

    def test_omitted_and_reordered_empty_cell_change_full_identity(self):
        _, baseline = self.build()
        identity = self.identity(baseline)
        for cells in ((self.cells[0], self.cells[2]), (self.cells[1], self.cells[0], self.cells[2])):
            _, candidate = self.build(cells)
            observed = self.identity(candidate)
            np.testing.assert_array_equal(candidate.apply(self.probes), baseline.apply(self.probes))
            self.assertEqual(observed["array_sha256"], identity["array_sha256"])
            self.assertNotEqual(observed["numerical_identity_sha256"], identity["numerical_identity_sha256"])
        baseline._retained_cell_port_inventory = baseline._retained_cell_port_inventory[:-1]
        with self.assertRaises(ValueError):
            self.identity(baseline)

    def test_nonempty_omission_is_a_material_negative_control(self):
        dense = independent_dense(self.original, self.oracle_terms)
        _, omitted = self.build(self.cells[1:])
        self.assertGreater(relative_defect(omitted.apply(self.probes), dense @ self.probes), .1)
        _, baseline = self.build()
        baseline._corrections = baseline._corrections[1:]
        with self.assertRaises(ValueError):
            self.identity(baseline)

    def test_wrong_projection_and_conjugate_d_are_material_negative_controls(self):
        dense = independent_dense(self.original, self.oracle_terms)
        for field in ("ports", "Di"):
            cell = SimpleNamespace(**vars(self.cells[0]))
            if field == "ports":
                cell.ports = readonly([1, 2, 5, 6], np.int32)
            else:
                cell.Di = readonly(self.oracle_terms[0][2].conj().T)
            _, wrong = self.build((cell, *self.cells[1:]))
            with self.subTest(field=field):
                self.assertGreater(relative_defect(wrong.apply(self.probes), dense @ self.probes), .1)

    def test_replaced_reordered_or_copied_corrections_fail_owner_validation(self):
        for kind in ("reorder", "copy", "omit"):
            _, condensed = self.build()
            if kind == "reorder":
                condensed._corrections = condensed._corrections[::-1]
            elif kind == "omit":
                condensed._corrections = condensed._corrections[:-1]
            else:
                first = condensed._corrections[0]
                condensed._corrections = (replace(first, Di=readonly(first.Di)), condensed._corrections[1])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.identity(condensed)

    def test_original_mutation_or_foreign_block_is_rejected(self):
        _, condensed = self.build()
        self.original.mode_keys = (*self.original.mode_keys[1:], self.original.mode_keys[0])
        with self.assertRaises(ValueError):
            self.identity(condensed)
        with self.assertRaises(TypeError):
            self.build(original=np.eye(7))
        other = self.blocks.DiagonalOriginalPortBlock(np.ones(7), [(i,) for i in range(7)])
        with self.assertRaises(ValueError):
            self.helper.port_block_representation_identity(other, condensed)

    def test_mutated_factor_readonly_state_is_revalidated(self):
        _, condensed = self.build()
        self.cells[0].XiB.flags.writeable = True
        with self.assertRaises(ValueError):
            self.identity(condensed)

    def test_unique_backing_inventory_deduplicates_shared_views_and_is_not_rss(self):
        backing = readonly(np.arange(24).reshape(6, 4))
        di = backing[:2, :3]
        xib = backing[2:5, :2]
        ports = readonly([0, 1], np.int32)
        cell = SimpleNamespace(ports=ports, Di=di, XiB=xib, Hlocal=None)
        _, condensed = self.build((cell, cell))
        identity = self.identity(condensed)
        inventory = identity["backing_inventory"]
        self.assertEqual(inventory["unique_backing_count"], 3)
        self.assertEqual(inventory["named_unique_backing_bytes_including_borrowed"],
                         self.original.numeric_arrays[0].nbytes + ports.nbytes + backing.nbytes)
        self.assertTrue(inventory["named_inventory_is_not_RSS"])
        self.assertIn("not RSS", inventory["byte_scope"])
        self.assertNotIn("RSS", identity)

    def test_same_numerical_identity_can_have_different_backing_inventory(self):
        _, first = self.build()
        cells = []
        for cell in self.cells:
            larger = np.zeros((cell.Di.shape[0] + 1, cell.Di.shape[1]), dtype=np.complex128)
            larger[:cell.Di.shape[0]] = cell.Di
            larger.flags.writeable = False
            cells.append(SimpleNamespace(ports=readonly(cell.ports, cell.ports.dtype),
                                         Di=larger[:cell.Di.shape[0]], XiB=readonly(cell.XiB), Hlocal=cell.Hlocal))
        _, second = self.build(cells)
        self.assertEqual(self.identity(first)["numerical_identity_sha256"], self.identity(second)["numerical_identity_sha256"])
        self.assertNotEqual(self.identity(first)["backing_inventory"]["named_unique_backing_bytes_including_borrowed"],
                            self.identity(second)["backing_inventory"]["named_unique_backing_bytes_including_borrowed"])

    def test_missing_inventory_and_legacy_identity_request_fail_explicitly(self):
        bare = self.blocks.CachedCondensedPortBlock(self.original)
        with self.assertRaises(ValueError):
            self.identity(bare)
        _, condensed = self.build()
        with self.assertRaises(ValueError):
            self.helper.port_block_representation_identity(self.original, condensed,
                                                           layout=self.helper.LEGACY_PORT_LAYOUT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
