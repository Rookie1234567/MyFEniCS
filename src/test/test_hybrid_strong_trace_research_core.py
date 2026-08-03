from __future__ import annotations

import unittest

import numpy as np

from src.solvers.hybrid_strong_trace_direct import (
    build_hybrid_strong_trace_direct_system,
    exact_trace_dense_fixture,
    strong_trace_research_contract,
)


class HybridStrongTraceResearchCoreTests(unittest.TestCase):
    def test_ordinary_call_requires_explicit_research_opt_in(self):
        with self.assertRaisesRegex(ValueError, "research_only"):
            build_hybrid_strong_trace_direct_system(None, None, None)

        contract = strong_trace_research_contract()
        self.assertEqual(contract["status"], "research_only")
        self.assertEqual(
            contract["qualified_claims"],
            ("complete_tangential_e_continuity",),
        )
        self.assertFalse(contract["hybrid_p_production_qualified"])
        self.assertIn(
            "joint_cauchy_continuity",
            contract["unqualified_claims"],
        )
        self.assertIn(
            "all_diffraction_channels",
            contract["unqualified_claims"],
        )

    def test_dense_oracle_closes_complete_trace_without_complement(self):
        interface = np.asarray([1, 2], dtype=np.int64)
        right = np.zeros((4, 1), dtype=np.complex128)
        right[interface, 0] = (1.0, 1.0j)
        projection = np.zeros((1, 4), dtype=np.complex128)
        projection[0, interface] = (0.5, -0.5j)
        petrov = np.zeros_like(right)
        petrov[interface, 0] = (0.4 + 0.1j, 0.3 - 0.2j)
        operator = np.diag(np.asarray((3.0, 4.0 + 0.2j, 5.0 - 0.1j, 6.0)))
        coupling = np.asarray(
            ((0.2 + 0.1j,), (0.4,), (-0.3j,), (0.1,)),
            dtype=np.complex128,
        )
        propagation = np.asarray(((0.85 + 0.05j,),), dtype=np.complex128)
        forcing = np.asarray((1.0, -0.2j, 0.3, -0.1), dtype=np.complex128)

        audit = exact_trace_dense_fixture(
            operator,
            forcing,
            projection,
            right,
            petrov,
            coupling,
            propagation,
            interface,
            research_opt_in=True,
        )

        self.assertEqual(audit["qualification"]["status"], "research_only")
        self.assertTrue(audit["complete_tangential_e_continuity_pass"])
        self.assertLess(audit["dr_identity_error"], 1.0e-12)
        self.assertLess(audit["trace_identity_residual"], 1.0e-12)
        self.assertLess(audit["noninterface_residual"], 1.0e-12)
        self.assertLess(audit["petrov_residual"], 1.0e-12)
        self.assertEqual(audit["trace_complement_unknown_count"], 0)
        self.assertFalse(audit["dense_interface_square_formed"])

        arbitrary = np.asarray((0.0, 1.0, 0.0, 0.0), dtype=np.complex128)
        complement = arbitrary - right @ (projection @ arbitrary)
        self.assertGreater(np.linalg.norm(complement), 1.0e-3)
        self.assertLess(np.linalg.norm(projection @ complement), 1.0e-12)


if __name__ == "__main__":
    unittest.main()
