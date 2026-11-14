"""No-FE fixtures for the opt-in native-Linux PSTDDM workstation profile."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.pstddm_partition_pilot import supervise
from src.runners.pstddm_workstation_case import (
    _sha256,
    _source_sha,
    run_workstation_case,
    validate_supervisor_handoff,
    validate_workstation_cgroup,
)
from src.solvers.pstddm_material import derive_si_optical_identity
from src.solvers.pstddm_model import make_cfg, workstation_spec_from_material_identity


ROOT = Path(__file__).resolve().parents[2]


class WorkstationProfileFixtures(unittest.TestCase):
    def test_13p5_direct_dat_dry_run_is_a_no_fe_preflight(self):
        result = run_workstation_case(
            ROOT / "input/pstddm_workstation_pilot/13p5_direct.dat", dry_run=True,
        )

        self.assertEqual(result["status"], "VALID_CONFIGURATION_NOT_RUN")
        preflight = result["preflight"]["model_preflight"]
        self.assertEqual(preflight["axis_cell_counts"], [4, 4, 16])
        self.assertEqual(preflight["cells"], 256)
        self.assertEqual(preflight["independent_fe_rows"], 6272)
        self.assertEqual(preflight["mode_count"], 612)
        self.assertEqual((preflight["selected_m_max"], preflight["selected_n_max"]), (4, 8))
        self.assertEqual(preflight["mode_window_policy"], "all_propagating_plus_rectangular_one_order_padding")

    def test_stationary_dtn_is_global_and_legacy_pml_remains_available(self):
        legacy_pml = make_cfg("pml", degree=2)
        self.assertTrue(legacy_pml.use_pml)

        material = derive_si_optical_identity(13.5)
        model = workstation_spec_from_material_identity(material)
        stationary_dtn = make_cfg("dtn", degree=2, model_spec=model)
        self.assertFalse(stationary_dtn.use_pml)
        self.assertEqual(stationary_dtn.mesh_axis_cell_counts_requested, (4, 4, 16))
        with self.assertRaisesRegex(ValueError, "local to PSTDDM"):
            make_cfg("pml", degree=2, model_spec=model)

    def test_case_cgroup_must_be_distinct_capped_and_swap_free(self):
        facts = {
            "memory_current_bytes": 1_000_000_000,
            "memory_max_bytes": 8_000_000_000,
            "swap_current_bytes": 0,
            "swap_max_bytes": 0,
        }
        validate_workstation_cgroup(
            "/system.slice/pstddm-case.scope", facts,
            "/system.slice/pstddm-abi-receipt-20261114.service",
        )
        with self.assertRaisesRegex(ValueError, "separate"):
            validate_workstation_cgroup(
                "/system.slice/pstddm-abi-receipt-20261114.service", facts,
                "/system.slice/pstddm-abi-receipt-20261114.service",
            )
        wrong_cap = {**facts, "memory_max_bytes": 7_000_000_000}
        with self.assertRaisesRegex(ValueError, "memory.max"):
            validate_workstation_cgroup(
                "/system.slice/pstddm-case.scope", wrong_cap,
                "/system.slice/pstddm-abi-receipt-20261114.service",
            )

    def test_supervisor_handoff_accepts_only_its_precreated_empty_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            scope = Path(temporary).resolve()
            input_dir = scope / "input"
            runs = scope / "runs"
            input_dir.mkdir()
            runs.mkdir()
            case_path = input_dir / "13p5_direct.dat"
            case_path.write_text("fixture input\n", encoding="utf-8")
            case_id = "13p5_direct"
            output = runs / case_id
            input_sha = _sha256(case_path)
            parent_pid = os.getpid()
            runtime = {"runtime_profile": "native_linux", "fixture": True}
            identity = {
                "case_id": case_id,
                "supervisor_pid": parent_pid,
                "source_sha": _source_sha(),
                "input_path": str(case_path),
                "input_sha256": input_sha,
                "scope_root": str(scope),
                "runs_root": str(runs),
            }
            supervise._workstation_prepare_case_output(output, runtime, identity)

            with patch.dict(os.environ, {"PSTDDM_WORKSTATION_SUPERVISOR_PID": str(parent_pid)}):
                accepted = validate_supervisor_handoff(
                    case_path, case_id, input_sha, scope, output, parent_pid=parent_pid,
                )
                self.assertEqual(accepted["case_id"], case_id)
                (output / "A.npz").write_bytes(b"science output")
                with self.assertRaisesRegex(RuntimeError, "unexpected artifacts"):
                    validate_supervisor_handoff(
                        case_path, case_id, input_sha, scope, output, parent_pid=parent_pid,
                    )


if __name__ == "__main__":
    unittest.main()
