from __future__ import annotations

import copy
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
        "requested_modes": mode_count,
        "candidate_modes": 2 * mode_count,
        "formal_pass": True,
        "numeric_pass": True,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "memory_authority_pass": True,
        "resource_authority": {"gate": {"pass": True}},
        "source_gate": {"pass": True},
        "launch_gate": {"pass": True},
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


def _controlled_physical_negative(mode_count: int, *, delta: float = 0.0) -> dict:
    shard = _shard(mode_count, delta=delta)
    shard.update(
        {
            "status": "formal_not_pass",
            "return_code": 2,
            "formal_pass": False,
            "numeric_pass": False,
            "terminated_for_authority_unreadable": False,
            "resource_authority": {"gate": {"pass": True}},
            "source_gate": {"pass": True},
            "launch_gate": {"pass": True},
        }
    )
    measurements = shard["measurements"]
    measurements["status"] = "physical_integration_failed"
    measurements["gates"]["sampled_interface_h_t_relative_l2_le_1e-2"] = False
    measurements["qualification"].update(
        {
            "integration_pass": False,
            "physical_field_gates_pass": False,
            "mode_count_converged": False,
            "official_record": False,
        }
    )
    return shard


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

    def test_controlled_physical_negatives_at_m80_and_m120_can_qualify(self) -> None:
        record = build_hybrid_funnel(
            [
                _controlled_physical_negative(80, delta=2.0e-7),
                _controlled_physical_negative(120, delta=1.0e-7),
                _shard(160),
            ]
        )
        self.assertEqual(record["status"], "qualified", record["failures"])
        self.assertTrue(record["qualification"]["all_external_watchdogs_pass"])
        self.assertTrue(
            record["individual_gates"]["160"][
                "candidate_pool_is_twice_requested_modes"
            ]
        )
        self.assertEqual(
            record["qualification"]["selected_mode_count_per_direction"], 160
        )

    def test_controlled_negative_contract_fails_closed(self) -> None:
        valid = _controlled_physical_negative(120, delta=1.0e-7)
        mutations = {
            "wrong_return_code": lambda row: row.update(return_code=3),
            "short_candidate_pool": lambda row: row.update(candidate_modes=239),
            "wide_candidate_pool": lambda row: row.update(candidate_modes=241),
            "memory_failure": lambda row: row.update(memory_authority_pass=False),
            "swap_failure": lambda row: row.update(no_swap=False),
            "algebraic_failure": lambda row: row["measurements"]["qualification"].update(
                algebraic_chain_pass=False
            ),
            "nonphysical_worker_gate_failure": lambda row: row["measurements"][
                "gates"
            ].update(monolithic_true_relative_residual_le_1e_9=False),
            "resource_failure": lambda row: row["resource_authority"]["gate"].__setitem__(
                "pass", False
            ),
            "source_failure": lambda row: row["source_gate"].__setitem__("pass", False),
            "launch_failure": lambda row: row["launch_gate"].__setitem__("pass", False),
            "official_record": lambda row: row["measurements"][
                "qualification"
            ].update(official_record=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                rejected = copy.deepcopy(valid)
                mutate(rejected)
                record = build_hybrid_funnel(
                    [_shard(80, delta=2.0e-7), rejected, _shard(160)]
                )
                self.assertEqual(record["status"], "not_qualified")
                self.assertFalse(
                    record["qualification"]["all_external_watchdogs_pass"]
                )

    def test_m160_cannot_be_a_controlled_physical_negative(self) -> None:
        record = build_hybrid_funnel(
            [
                _controlled_physical_negative(80, delta=2.0e-7),
                _controlled_physical_negative(120, delta=1.0e-7),
                _controlled_physical_negative(160),
            ]
        )
        self.assertEqual(record["status"], "not_qualified")
        self.assertIn(
            "one or more individual Hybrid physical/algebraic gates failed",
            record["failures"],
        )

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
