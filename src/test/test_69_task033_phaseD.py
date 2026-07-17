from __future__ import annotations

import unittest

from benchmarks.task033_source_compatibility import (
    build_d1_source_compatibility_audit,
    build_full3d_hybrid_source_compatibility_audit,
    normalized_phase6_ast,
)


class Task033PhaseDTests(unittest.TestCase):
    def test_reference_registry_is_the_only_ignored_phase6_ast_region(
        self,
    ) -> None:
        before = """
REFERENCE_BY_DEGREE_AND_H = {(2, 5.0): "old"}
def solve(value):
    return value + 1
"""
        after = """
REFERENCE_BY_DEGREE_AND_H = {(2, 5.0): "old", (3, 5.0): "new"}
def solve(value):
    return value + 1
"""
        changed_solver = """
REFERENCE_BY_DEGREE_AND_H = {(2, 5.0): "old", (3, 5.0): "new"}
def solve(value):
    return value + 2
"""
        self.assertEqual(
            normalized_phase6_ast(before),
            normalized_phase6_ast(after),
        )
        self.assertNotEqual(
            normalized_phase6_ast(before),
            normalized_phase6_ast(changed_solver),
        )

    def test_historical_p3_closure_sources_are_compatible(self) -> None:
        record = build_full3d_hybrid_source_compatibility_audit()
        self.assertTrue(record["compatible"], record["failures"])
        self.assertTrue(
            record["checks"][
                "all_critical_numerical_kernel_blobs_identical"
            ]
        )
        self.assertTrue(
            record["phase6_reference_registry_audit"][
                "identical_after_registry_removed"
            ]
        )
        self.assertEqual(record["disallowed_changed_paths"], [])

    def test_d1_direct_to_hybrid_source_splits_are_compatible(self) -> None:
        record = build_d1_source_compatibility_audit()
        self.assertTrue(record["compatible"])
        self.assertEqual(
            record["status"],
            "d1_source_splits_numerically_compatible",
        )
        self.assertEqual(
            [row["candidate"] for row in record["source_splits"]],
            ["p3_h10", "p3_h7p5"],
        )
        for row in record["source_splits"]:
            self.assertTrue(row["compatible"], row["failures"])
            self.assertEqual(row["unexpected_changed_paths"], [])
            self.assertEqual(row["missing_expected_changed_paths"], [])
            self.assertTrue(
                row["checks"][
                    "all_critical_numerical_kernel_blobs_identical"
                ]
            )


if __name__ == "__main__":
    unittest.main()
