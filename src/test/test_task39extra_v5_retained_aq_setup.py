from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from benchmarks.physical_intermediate_checker import (
    _retained_v5_aq_projection_errors,
)
from src.common.config_3d import target_stage4_config
from src.io.native_capacity_profile import native_profile_facts
from src.runners.physical_retained_condensed_v20 import (
    run_retained_condensed_workflow,
)


class StopAfterSetup(RuntimeError):
    pass


class _ProbeLedger:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.last_stage = ""
        self.phase = "setup"

    def marker(self, name, facts):
        self.last_stage = name
        if name == "retained_same_object_setup_checks_complete":
            raise StopAfterSetup(name)

    def append(self, name, facts):
        path = self.directory / name
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(facts, sort_keys=True, allow_nan=False) + "\n")

    def set_phase(self, phase):
        self.phase = phase


@unittest.skipUnless(
    os.environ.get("TASK39EXTRA_RUN_V5_RUNTIME_QUALIFICATION") == "1"
    and os.environ.get("TASK39EXTRA_PORD64_ROOT"),
    "requires explicit task-local PORD64 qualification activation",
)
class Task39ExtraV5RetainedAqSetupTests(unittest.TestCase):
    def test_q3_and_q4_v5_setup_invoke_aq_projection_and_checker_contract(self):
        for degree, identity in (
            (3, "dual_condensed_balh_native_13p5_q3_v5"),
            (4, "dual_condensed_balh_native_13p5_q4_v5"),
        ):
            with self.subTest(coarse_degree=degree), tempfile.TemporaryDirectory(
                prefix=f"task39extra-v5-aq-q{degree}-"
            ) as temp:
                output = Path(temp)
                cfg = replace(
                    target_stage4_config(degree=6, h_nm=100),
                    period_x=20.0,
                    period_y=15.0,
                    grating_width_x=8.0,
                    grating_width_y=15.0,
                    grating_height=2.0,
                    z_min=-1.0,
                    z_max=3.0,
                    air_height=3.0,
                    substrate_thickness=1.0,
                    mesh_cell_type="hexahedron",
                    mesh_spacing_mode="boundary_fitted",
                    mesh_axis_cell_counts=(3, 2, 3),
                    incident_theta_deg=74.0,
                    incident_phi_deg=17.0,
                    n_substrate=1.4 + 0.05j,
                    n_grating=0.9 + 0.02j,
                )
                ledger = _ProbeLedger(output)
                payload = {
                    "solver": {"preconditioner": identity, "coarse_degree": degree},
                    "provenance": {
                        "input_sha256": "b" * 64,
                        "physical_model_sha256": "c" * 64,
                    },
                }
                summary = {"profile": native_profile_facts(identity)}

                def sample():
                    return {
                        "sample_kind": "synthetic_test_injection_not_resource_qualification",
                        "reference_memory_admission": "measured_rss",
                        "resource_stop_policy": "measured_tree_rss_only_v3",
                        "swap_policy": "observe_only",
                        "rss_bytes": 0,
                        "swap_bytes": 0,
                        "all_status_readable": True,
                        "launch_cap_bytes": 1_300_000_000_000,
                        "icntl23": 0,
                    }

                with self.assertRaises(StopAfterSetup):
                    run_retained_condensed_workflow(
                        payload,
                        output,
                        source_sha="a" * 40,
                        cfg=cfg,
                        contract={},
                        ledger=ledger,
                        sample=sample,
                        summary=summary,
                    )

                retained = summary["retained_runtime"]
                setup = retained["setup_checks"]
                aq = retained["native_aq_projection_check"]
                self.assertEqual(setup["status"], "PASS")
                self.assertTrue(aq["passed"])
                self.assertEqual(setup["native_aq_projection"], aq)
                self.assertEqual(aq["space_identity"], retained["space_identity"])
                self.assertTrue(aq["input_unchanged"])
                self.assertTrue(aq["input_slave_zero"])
                self.assertLessEqual(
                    aq["native_Aq_volume_vs_PqH_A6_volume_P"]["relative"],
                    1.0e-10,
                )
                self.assertLessEqual(
                    aq["native_Aq_DtN_vs_PqH_A6_DtN_P"]["relative"],
                    1.0e-10,
                )
                self.assertEqual(
                    aq["total_identity_policy"],
                    "record_only; native volume and DtN components gate independently",
                )
                errors = _retained_v5_aq_projection_errors(
                    identity,
                    summary["profile"],
                    retained["space_identity"],
                    retained["native_aq_projection_check"],
                    setup["native_aq_projection"],
                )
                self.assertEqual(errors, [])
                print(
                    "V5_AQ_SETUP_PASS "
                    + json.dumps(
                        {
                            "coarse_degree": degree,
                            "cells": 18,
                            "modes": retained["mode_count"],
                            "space_identity": aq["space_identity"],
                            "volume_relative": aq[
                                "native_Aq_volume_vs_PqH_A6_volume_P"
                            ]["relative"],
                            "dtn_relative": aq[
                                "native_Aq_DtN_vs_PqH_A6_DtN_P"
                            ]["relative"],
                            "total_relative_record_only": aq[
                                "native_Aq_total_vs_PqH_A6_total_P"
                            ]["relative"],
                            "transfer_deltas": aq["calls"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    unittest.main()
