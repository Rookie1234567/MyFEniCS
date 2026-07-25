from __future__ import annotations

import time
import unittest

import basix
import basix.ufl
import numpy as np

from src.adaptivity.fast_custom_element_ufl import (
    _custom_element_sha256_unchecked,
    basix_ufl_private_api_audit,
    custom_element_sha256,
    wrap_custom_element_fast,
)
from src.adaptivity.hcurl_regionwise_p import (
    _create_trace_interior_element,
)


def _custom_clone(degree: int) -> basix.finite_element.FiniteElement:
    source = basix.ufl.element(
        "N1curl",
        "hexahedron",
        degree,
    ).basix_element
    return basix.create_custom_element(
        source.cell_type,
        source.value_shape,
        np.asarray(source.wcoeffs).copy(),
        [
            [np.asarray(array).copy() for array in entities]
            for entities in source.x
        ],
        [
            [np.asarray(array).copy() for array in entities]
            for entities in source.M
        ],
        source.interpolation_nderivs,
        source.map_type,
        source.sobolev_space,
        source.discontinuous,
        source.embedded_subdegree,
        source.embedded_superdegree,
        source.polyset_type,
    )


class _ElementDataView:
    def __init__(self, element, **overrides) -> None:
        self._element = element
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._element, name)

    def entity_transformations(self):
        if "entity_transformations" in self._overrides:
            return self._overrides["entity_transformations"]
        return self._element.entity_transformations()


def _modified_nested_arrays(nested, delta: float):
    copied = [
        [np.asarray(array).copy() for array in entities]
        for entities in nested
    ]
    for entities in copied:
        for array in entities:
            if array.size:
                array.flat[0] += delta
                return copied
    raise AssertionError("expected at least one non-empty custom-element array")


class Task035bFastCustomElementUFLTests(unittest.TestCase):
    def assert_wrapper_identity(self, raw) -> None:
        fast = wrap_custom_element_fast(raw)
        fast_again = wrap_custom_element_fast(raw)
        reference = basix.ufl.wrap_element(raw)
        points = np.asarray(
            (
                (0.17, 0.23, 0.31),
                (0.61, 0.47, 0.73),
            ),
            dtype=np.float64,
        )

        self.assertIs(fast.basix_element, raw)
        self.assertIs(reference.basix_element, raw)
        self.assertEqual(fast.basix_hash(), reference.basix_hash())
        self.assertEqual(fast, fast_again)
        self.assertEqual(hash(fast), hash(fast_again))
        self.assertNotEqual(fast, reference)
        np.testing.assert_allclose(
            fast.tabulate(1, points),
            reference.tabulate(1, points),
            rtol=0.0,
            atol=0.0,
        )
        self.assertEqual(fast.entity_dofs, reference.entity_dofs)
        self.assertEqual(
            fast.entity_closure_dofs,
            reference.entity_closure_dofs,
        )
        self.assertEqual(
            fast.num_entity_dofs,
            reference.num_entity_dofs,
        )
        self.assertEqual(
            fast.num_entity_closure_dofs,
            reference.num_entity_closure_dofs,
        )
        self.assertIs(fast.pullback, reference.pullback)
        self.assertEqual(fast.map_type, reference.map_type)
        self.assertEqual(fast.cell, reference.cell)
        self.assertEqual(
            fast.reference_value_shape,
            reference.reference_value_shape,
        )
        self.assertEqual(
            fast.fast_wrapper_audit["serialization"],
            "canonical_binary_no_pickle",
        )

    def test_private_api_audit_is_version_and_source_bound(self) -> None:
        audit = basix_ufl_private_api_audit()
        self.assertEqual(audit.status, "qualified_fail_closed_private_api")
        self.assertEqual(audit.basix_version, basix.__version__)
        self.assertIn(audit.basix_version, audit.supported_basix_versions)
        self.assertEqual(len(audit.basix_ufl_module_sha256), 64)
        self.assertIn(
            audit.basix_ufl_module_sha256,
            audit.qualified_basix_ufl_module_sha256,
        )
        self.assertEqual(
            audit.private_basix_element_init_parameters,
            ("self", "element"),
        )

    def test_small_p2_and_p3_custom_wrappers_match_basix_behavior(self) -> None:
        for degree in (2, 3):
            with self.subTest(degree=degree):
                raw = _custom_clone(degree)
                self.assertEqual(raw.family, basix.ElementFamily.custom)
                self.assert_wrapper_identity(raw)

    def test_signature_is_deterministic_and_sensitive_to_all_payloads(
        self,
    ) -> None:
        raw = _custom_clone(2)
        baseline = custom_element_sha256(raw)
        self.assertEqual(baseline, custom_element_sha256(raw))
        self.assertEqual(len(baseline), 64)

        wcoeffs = np.asarray(raw.wcoeffs).copy()
        wcoeffs.flat[0] += 0.125
        x = _modified_nested_arrays(raw.x, 0.125)
        matrices = _modified_nested_arrays(raw.M, 0.125)
        transformations = {
            name: np.asarray(matrix).copy()
            for name, matrix in raw.entity_transformations().items()
        }
        first_name = sorted(transformations)[0]
        transformations[first_name].flat[0] += 0.125
        variants = {
            "metadata": _ElementDataView(
                raw,
                embedded_superdegree=raw.embedded_superdegree + 1,
            ),
            "wcoeffs": _ElementDataView(raw, wcoeffs=wcoeffs),
            "x": _ElementDataView(raw, x=x),
            "M": _ElementDataView(raw, M=matrices),
            "entity_transformations": _ElementDataView(
                raw,
                entity_transformations=transformations,
            ),
        }
        signatures = set()
        for label, view in variants.items():
            with self.subTest(payload=label):
                changed = _custom_element_sha256_unchecked(view)
                self.assertNotEqual(changed, baseline)
                signatures.add(changed)
        self.assertEqual(len(signatures), len(variants))

    def test_noncustom_elements_fail_closed(self) -> None:
        standard = basix.ufl.element(
            "N1curl",
            "hexahedron",
            2,
        ).basix_element
        with self.assertRaises(ValueError):
            wrap_custom_element_fast(standard)

    def test_fixed_p5_trace_p6_interior_wrapper_timing_and_identity(
        self,
    ) -> None:
        raw, audit = _create_trace_interior_element(5, 6, False)
        self.assertTrue(audit["custom"])
        self.assertFalse(audit["qualification_audit_executed"])

        started = time.perf_counter()
        fast = wrap_custom_element_fast(raw)
        fast_seconds = time.perf_counter() - started
        started = time.perf_counter()
        reference = basix.ufl.wrap_element(raw)
        reference_seconds = time.perf_counter() - started

        self.assertLess(fast_seconds, reference_seconds)
        self.assertEqual(fast.basix_hash(), reference.basix_hash())
        self.assertEqual(fast.dim, reference.dim)
        self.assertEqual(fast.entity_dofs, reference.entity_dofs)
        self.assertIs(fast.pullback, reference.pullback)
        self.assertGreaterEqual(
            fast.fast_wrapper_audit["signature_seconds"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
