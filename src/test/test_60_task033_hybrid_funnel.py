from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from benchmarks.task033_hybrid_funnel import build_hybrid_funnel


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "hybrid_funnel_schema.json"
)
SHA = "1" * 40


def _shard(mode_count: int, *, delta: float = 0.0) -> dict:
    amplitude = [0.4 + delta, -0.2]
    power = 0.2 + delta
    return {
        "schema_version": 2,
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "target": "hybrid",
        "return_code": 0,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "memory_authority_pass": True,
        "source": {
            "commit_sha": SHA,
            "verified_clean_sha": SHA,
            "tracked_source_dirty": False,
            "source_clean_verified": True,
        },
        "measurements": {
            "case": {
                "degree": 3,
                "h_nm": 5.0,
                "wavelength_nm": 13.5,
                "incident_grazing_deg": 10.0,
                "polarization_kind": "s",
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "graded_reference_h_nm": None,
                "graded_plan_hash": None,
                "requested_modes_per_direction": mode_count,
            },
            "hybrid_system": {
                "primary_solver_path": "modal-schur-memory-minimal",
            },
            "solve": {"true_relative_residual": 1.0e-12},
            "port_power": {
                "R_total": 0.1 + delta,
                "T_total": 0.7 - delta,
                "A_balance": 0.2,
            },
            "external_diffraction_orders": [
                {
                    "side": "top",
                    "m": 0,
                    "n": 0,
                    "polarization": "s",
                    "propagating": True,
                    "outgoing_amplitude_at_boundary": amplitude,
                    "power_ratio": power,
                }
            ],
            "gates": {
                "monolithic_true_relative_residual_le_1e-9": True,
                "sampled_interface_e_t_relative_l2_le_5e-3": True,
                "sampled_interface_h_t_relative_l2_le_1e-2": True,
            },
            "qualification": {
                "integration_pass": True,
                "algebraic_chain_pass": True,
                "physical_field_gates_pass": True,
                "task033_physical_truncation_allowed": True,
            },
        },
    }


class Task033HybridFunnelTests(unittest.TestCase):
    def test_m80_m120_m160_can_qualify(self) -> None:
        record = build_hybrid_funnel(
            [_shard(80, delta=2.0e-7), _shard(120, delta=1.0e-7), _shard(160)]
        )
        self.assertEqual(record["status"], "qualified")
        self.assertEqual(
            record["qualification"]["selected_mode_count_per_direction"], 160
        )
        self.assertTrue(record["qualification"]["mode_count_converged"])

    def test_single_m_and_legacy_formal_label_never_qualify(self) -> None:
        single = build_hybrid_funnel([_shard(80)])
        self.assertEqual(single["status"], "not_qualified")
        shards = [_shard(80), _shard(120), _shard(160)]
        shards[-1]["status"] = "formal_measured_pass"
        legacy = build_hybrid_funnel(shards)
        self.assertEqual(legacy["status"], "not_qualified")
        self.assertFalse(legacy["qualification"]["all_external_watchdogs_pass"])

    def test_m240_is_conditional_recovery(self) -> None:
        record = build_hybrid_funnel(
            [
                _shard(80, delta=3.0e-3),
                _shard(120, delta=2.0e-3),
                _shard(160, delta=1.0e-3),
                _shard(240, delta=1.0e-3 + 1.0e-8),
            ]
        )
        self.assertEqual(record["status"], "qualified")
        self.assertEqual(
            record["qualification"]["selected_mode_count_per_direction"], 240
        )

    def test_dirty_or_missing_order_evidence_fails_closed(self) -> None:
        dirty = [_shard(80), _shard(120), _shard(160)]
        dirty[1]["source"]["tracked_source_dirty"] = True
        self.assertEqual(build_hybrid_funnel(dirty)["status"], "not_qualified")
        missing = [_shard(80), _shard(120), _shard(160)]
        missing[-1]["measurements"]["external_diffraction_orders"] = []
        self.assertEqual(build_hybrid_funnel(missing)["status"], "not_qualified")

    def test_schema_accepts_qualified_record_and_rejects_0p7nm_claim(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        record = build_hybrid_funnel([_shard(80), _shard(120), _shard(160)])
        Draft202012Validator(schema).validate(record)
        record["identity"]["proves_0p7nm_feasible"] = True
        errors = list(Draft202012Validator(schema).iter_errors(record))
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
