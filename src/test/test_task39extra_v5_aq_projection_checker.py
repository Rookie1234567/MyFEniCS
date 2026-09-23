from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import physical_intermediate_checker
from benchmarks.physical_intermediate_checker import (
    _retained_v5_aq_projection_errors,
    _retained_v5_reference_authority_errors,
)
from src.runners.physical_balanced_output import compare_retained_v5_output


class Task39ExtraV5AqProjectionCheckerTests(unittest.TestCase):
    def _facts(self):
        facts = {
            "source_contract": (
                "4bf2bba56cc2e568d56ff3096aeb4a108744f28d:"
                "_build_common.native_aq_projection_check"
            ),
            "passed": True,
            "input_unchanged": True,
            "input_slave_zero": True,
            "coarse_degree": 3,
            "space_identity": {
                "coarse_global_rows": 1944,
                "fine_global_rows": 6240,
                "coarse_mode_sha256": "a" * 64,
                "fine_mode_sha256": "b" * 64,
            },
            "limit": 1.0e-10,
            "native_Aq_volume_vs_PqH_A6_volume_P": {"relative": 2.0e-12},
            "native_Aq_DtN_vs_PqH_A6_DtN_P": {"relative": 3.0e-12},
            # A summed comparison is informative, never an additional gate.
            "native_Aq_total_vs_PqH_A6_total_P": {"relative": 0.25},
            "total_identity_policy": (
                "record_only; native volume and DtN components gate independently"
            ),
            "projected_A6_slave_rows_zero": {"volume": True, "dtn": True},
            "calls": {
                "native_Aq_volume": 1,
                "projected_A6_volume": 1,
                "native_Aq_DtN": 1,
                "projected_A6_DtN": 1,
                "transfer_primal_delta": 1,
                "transfer_adjoint_delta": 2,
            },
        }
        return facts

    def test_v5_checks_split_volume_and_dtn_but_records_total_only(self):
        facts = self._facts()
        profile = {"retained_condensed_v20": {"coarse_degree": 3}}
        self.assertEqual(
            _retained_v5_aq_projection_errors(
                "dual_condensed_balh_native_13p5_q3_v5",
                profile,
                facts["space_identity"],
                facts,
                facts,
            ),
            [],
        )

    def test_v5_rejects_component_error_but_legacy_does_not_enable_check(self):
        facts = self._facts()
        facts["native_Aq_volume_vs_PqH_A6_volume_P"]["relative"] = 1.1e-10
        profile = {"retained_condensed_v20": {"coarse_degree": 3}}
        errors = _retained_v5_aq_projection_errors(
            "dual_condensed_balh_native_13p5_q3_v5",
            profile,
            facts["space_identity"],
            facts,
            facts,
        )
        self.assertTrue(any("native_Aq_volume" in error for error in errors))
        facts = self._facts()
        facts["input_unchanged"] = False
        errors = _retained_v5_aq_projection_errors(
            "dual_condensed_balh_native_13p5_q3_v5",
            profile,
            facts["space_identity"],
            facts,
            facts,
        )
        self.assertTrue(any("modified its coarse input" in error for error in errors))
        facts = self._facts()
        actual_space_identity = dict(facts["space_identity"], coarse_global_rows=1945)
        errors = _retained_v5_aq_projection_errors(
            "dual_condensed_balh_native_13p5_q3_v5",
            profile,
            actual_space_identity,
            facts,
            facts,
        )
        self.assertTrue(any("runtime's FE/operator identity" in error for error in errors))
        self.assertEqual(
            _retained_v5_aq_projection_errors(
                "dual_condensed_balh_native_5nm_v3", {}, None, None, None
            ),
            [],
        )

    def test_whole_checker_dispatches_each_v5_case_to_retained_contract(self):
        identities = (
            "dual_condensed_balh_native_13p5_q3_v5",
            "dual_condensed_balh_native_13p5_q4_v5",
            "dual_condensed_balh_native_5nm_v5",
            "dual_condensed_balh_native_2nm_v5",
            "dual_condensed_balh_native_5nm_v3",
        )
        for identity in identities:
            with self.subTest(identity=identity), tempfile.TemporaryDirectory(
                prefix="task39extra-v5-checker-dispatch-"
            ) as temp:
                directory = Path(temp)
                (directory / "physical_intermediate_summary.json").write_text(
                    json.dumps({"profile": {"identity": identity}}),
                    encoding="utf-8",
                )
                with patch.object(
                    physical_intermediate_checker,
                    "check_retained_v20",
                    return_value={"route": "retained"},
                ) as retained_checker:
                    result = physical_intermediate_checker.check(directory)
                self.assertEqual(result, {"route": "retained"})
                retained_checker.assert_called_once()

    def test_r13_compact_comparison_checks_all_available_rta_and_r00(self):
        source = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "docs/task39extra_para_workstation_capacity/outcomes/records/"
                "v5_r13_source_compact_observations_v1.json"
            ).read_text(encoding="utf-8")
        )
        outputs = {
            "port_metrics": {
                key: source["q3"]["official_observations"][key]
                for key in (
                    "R_total", "T_total", "A_balance", "R00_s", "R00_p", "R00_total"
                )
            },
            "volume_metrics": {
                "A_volume_total": source["q3"]["official_observations"][
                    "A_volume_total"
                ]
            },
        }
        identity = {
            "run_id": "synthetic-q3",
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        }
        result = compare_retained_v5_output(
            "dual_condensed_balh_native_13p5_q3_v5",
            outputs,
            Path("unused-numerical-output"),
            current_run_identity=identity,
        )
        self.assertEqual(result["status"], "REFERENCE_AUTHORITY_LIMITED")
        compact = result["source_compact_comparison"]
        self.assertEqual(compact["status"], "SOURCE_COMPACT_OBSERVABLES_PASS")
        self.assertEqual(
            set(compact["comparisons"]),
            {
                "R_total", "T_total", "A_balance", "A_volume_total",
                "R00_s", "R00_p", "R00_total",
            },
        )
        self.assertEqual(compact["comparisons"]["R00_s"]["limit"], 1.0e-6)
        self.assertEqual(
            _retained_v5_reference_authority_errors(
                "dual_condensed_balh_native_13p5_q3_v5", result, identity
            ),
            [],
        )

        outputs["port_metrics"]["R00_s"] += 2.0e-6
        failed = compare_retained_v5_output(
            "dual_condensed_balh_native_13p5_q3_v5",
            outputs,
            Path("unused-numerical-output"),
            current_run_identity=identity,
        )
        self.assertEqual(failed["status"], "MATCHED_REFERENCE_FAIL")
        self.assertEqual(
            _retained_v5_reference_authority_errors(
                "dual_condensed_balh_native_13p5_q3_v5", failed, identity
            )[0],
            "R13 source compact observables did not pass",
        )

        forged = deepcopy(result)
        forged_row = forged["source_compact_comparison"]["comparisons"]["R00_s"]
        forged_row["current"] += 2.0e-6
        forged_row["passed"] = True
        forged_identity = dict(identity, physical_model_sha256="d" * 64)
        errors = _retained_v5_reference_authority_errors(
            "dual_condensed_balh_native_13p5_q3_v5", forged, forged_identity
        )
        self.assertTrue(any("exceeds limit: R00_s" in error for error in errors))
        self.assertTrue(any("identity disagrees with summary" in error for error in errors))

    def test_q4_and_f2_reference_scope_are_not_mislabeled(self):
        source = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "docs/task39extra_para_workstation_capacity/outcomes/records/"
                "v5_r13_source_compact_observations_v1.json"
            ).read_text(encoding="utf-8")
        )
        q4 = source["q4"]["official_observations"]
        outputs = {
            "port_metrics": {
                key: q4[key]
                for key in (
                    "R_total", "T_total", "A_balance", "R00_s", "R00_p", "R00_total"
                )
            },
            "volume_metrics": {},
        }
        identity = {
            "run_id": "synthetic-q4",
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        }
        result = compare_retained_v5_output(
            "dual_condensed_balh_native_13p5_q4_v5",
            outputs,
            Path("unused-numerical-output"),
            current_run_identity=identity,
        )
        self.assertEqual(result["source_compact_comparison"]["status"],
                         "SOURCE_COMPACT_OBSERVABLES_PASS")
        self.assertNotIn(
            "A_volume_total", result["source_compact_comparison"]["comparisons"]
        )
        f2 = compare_retained_v5_output(
            "dual_condensed_balh_native_2nm_v5",
            {},
            Path("unused-numerical-output"),
        )
        self.assertEqual(f2["status"], "REFERENCE_AUTHORITY_LIMITED")
        self.assertEqual(f2["reference_kind"], "no_legacy_full_field_reference")


if __name__ == "__main__":
    unittest.main()
