from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from benchmarks.task033_hybrid_funnel import (
    P1_H5_CAPACITY_FAILURE,
    P1_TERMINAL_PHYSICAL_FAILURE,
    build_hybrid_funnel,
    is_controlled_p1_h5_capacity_funnel,
    is_controlled_p1_terminal_physical_funnel,
)
from benchmarks.task033_evidence_checker import _semantic_problems


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
        "command": ["mpiexec", "-n", "4", "python", "hybrid"],
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


def _p1_h5_capacity_negative() -> dict:
    shard = _shard(160)
    shard.update(
        {
            "status": "formal_not_pass",
            "return_code": 2,
            "formal_pass": False,
            "numeric_pass": False,
        }
    )
    measurements = shard["measurements"]
    measurements["status"] = "insufficient_finite_admissible_modes"
    measurements["case"]["degree"] = 1
    measurements["case"]["candidate_modes_per_target_branch"] = 320
    measurements["solve"] = {"true_relative_residual": None}
    measurements["gates"] = {"finite_admissible_mode_capacity": False}
    measurements["qualification"] = {
        "integration_pass": False,
        "algebraic_chain_pass": False,
        "physical_field_gates_pass": False,
        "task033_physical_truncation_allowed": False,
        "mode_count_converged": False,
        "modal_basis_capacity_pass": False,
        "capacity_disposition": "insufficient_finite_admissible_modes",
        "official_record": False,
    }
    measurements["modal_basis_capacity"] = {
        "status": "insufficient_finite_admissible_modes",
        "direction": "positive",
        "requested_modes_per_direction": 160,
        "delivered_finite_admissible_modes": 120,
        "finite_candidate_count_both_directions": 240,
        "numerically_infinite_candidate_count": 80,
        "finite_spectrum_abs_beta_h_cutoff": 1.0e4,
        "finite_spectrum_abs_beta_cutoff_per_nm": 2.0e3,
        "leading_coefficient_singular_by_design": True,
        "pair_tolerance_relaxed": False,
        "left_pair_relative_error_tolerance": 1.0e-7,
        "first_rejected_numerical_infinity_beta_per_nm": [1.1e7, 2.0e6],
    }
    measurements["object_payload_ledger"] = {"mode_count_per_direction": 120}
    return shard


def _p1_h3_terminal_physical_negative() -> dict:
    shard = _controlled_physical_negative(160)
    case = shard["measurements"]["case"]
    case.update(
        {
            "degree": 1,
            "h_nm": 3.0,
            "candidate_modes_per_target_branch": 320,
        }
    )
    measurements = shard["measurements"]
    measurements["physical_field_reconstruction"] = {
        "selected_plane_full3d_comparison": {
            "reference_binding_verified": True,
            "reference_record": (
                "benchmarks/cases/080_hybrid_fem_modal_direct_baseline/"
                "records/full3d_h3_reference.json"
            ),
            "reference_record_sha256": "2" * 64,
            "reference_record_source_commit_full_sha": "3" * 40,
            "reference_npz_sha256_expected": "4" * 64,
            "reference_npz_sha256_observed": "4" * 64,
        }
    }
    measurements["full3d_reference_comparison"] = {
        "reference_file": (
            "benchmarks/cases/080_hybrid_fem_modal_direct_baseline/"
            "records/full3d_h3_reference.json"
        ),
        "reference_commit_sha": "3" * 40,
        "reference_grid_converged": False,
    }
    return shard


class Task033HybridFunnelTests(unittest.TestCase):
    def test_p1_h3_terminal_physical_negative_is_never_promoted(self) -> None:
        m80 = _controlled_physical_negative(80)
        m120 = _controlled_physical_negative(120, delta=1.0e-8)
        for shard in (m80, m120):
            shard["measurements"]["case"].update(
                {"degree": 1, "h_nm": 3.0}
            )
        record = build_hybrid_funnel(
            [m80, m120, _p1_h3_terminal_physical_negative()]
        )
        self.assertEqual(record["status"], "not_qualified")
        self.assertEqual(record["failures"], [P1_TERMINAL_PHYSICAL_FAILURE])
        self.assertTrue(
            record["qualification"]["terminal_physical_gate_limited"]
        )
        self.assertFalse(record["qualification"]["mode_count_converged"])
        self.assertIsNone(
            record["qualification"]["selected_mode_count_per_direction"]
        )
        self.assertTrue(is_controlled_p1_terminal_physical_funnel(record))
        self.assertEqual(_semantic_problems("hybrid_funnel_p1", record), [])
        Draft202012Validator(
            json.loads(SCHEMA.read_text(encoding="utf-8"))
        ).validate(record)

    def test_terminal_physical_negative_rejects_wrong_degree(self) -> None:
        m80 = _controlled_physical_negative(80)
        m120 = _controlled_physical_negative(120)
        terminal = _p1_h3_terminal_physical_negative()
        for shard in (m80, m120, terminal):
            shard["measurements"]["case"].update(
                {"degree": 2, "h_nm": 3.0}
            )
        record = build_hybrid_funnel([m80, m120, terminal])
        self.assertEqual(record["status"], "not_qualified")
        self.assertFalse(is_controlled_p1_terminal_physical_funnel(record))
        self.assertIn(
            "one or more individual Hybrid physical/algebraic gates failed",
            record["failures"],
        )

    def test_p1_h5_m160_capacity_negative_is_structured_and_not_promoted(self) -> None:
        m80 = _controlled_physical_negative(80)
        m120 = _controlled_physical_negative(120)
        for shard in (m80, m120):
            shard["measurements"]["case"]["degree"] = 1
        record = build_hybrid_funnel([m80, m120, _p1_h5_capacity_negative()])
        self.assertEqual(record["status"], "not_qualified")
        self.assertEqual(record["failures"], [P1_H5_CAPACITY_FAILURE])
        self.assertTrue(record["qualification"]["modal_basis_capacity_limited"])
        self.assertEqual(
            record["modal_basis_capacity"]["delivered_finite_admissible_modes"],
            120,
        )
        self.assertTrue(is_controlled_p1_h5_capacity_funnel(record))
        self.assertEqual(_semantic_problems("hybrid_funnel_p1", record), [])

    def test_aggregate_capacity_contract_rejects_mutated_cutoff(self) -> None:
        shards = [_controlled_physical_negative(mode) for mode in (80, 120)]
        for shard in shards:
            shard["measurements"]["case"]["degree"] = 1
        record = build_hybrid_funnel(
            [*shards, _p1_h5_capacity_negative()]
        )
        record["modal_basis_capacity"][
            "finite_spectrum_abs_beta_cutoff_per_nm"
        ] = 123.0
        self.assertFalse(is_controlled_p1_h5_capacity_funnel(record))
        self.assertTrue(_semantic_problems("hybrid_funnel_p1", record))

    def test_p1_h5_capacity_negative_contract_fails_closed_per_field(self) -> None:
        mutations = {
            "integration_pass": lambda row: row["measurements"][
                "qualification"
            ].update(integration_pass=True),
            "algebraic_chain_pass": lambda row: row["measurements"][
                "qualification"
            ].update(algebraic_chain_pass=True),
            "physical_field_gates_pass": lambda row: row["measurements"][
                "qualification"
            ].update(physical_field_gates_pass=True),
            "physical_truncation_allowed": lambda row: row["measurements"][
                "qualification"
            ].update(task033_physical_truncation_allowed=True),
            "mode_count_converged": lambda row: row["measurements"][
                "qualification"
            ].update(mode_count_converged=True),
            "non_null_true_residual": lambda row: row["measurements"][
                "solve"
            ].update(true_relative_residual=0.0),
            "wrong_solver_path": lambda row: row["measurements"][
                "hybrid_system"
            ].update(primary_solver_path="augmented-direct"),
            "wrong_dimensionless_cutoff": lambda row: row["measurements"][
                "modal_basis_capacity"
            ].update(finite_spectrum_abs_beta_h_cutoff=1.0e3),
            "wrong_per_nm_cutoff": lambda row: row["measurements"][
                "modal_basis_capacity"
            ].update(finite_spectrum_abs_beta_cutoff_per_nm=200.0),
        }
        m80 = _controlled_physical_negative(80)
        m120 = _controlled_physical_negative(120)
        for shard in (m80, m120):
            shard["measurements"]["case"]["degree"] = 1
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                rejected = _p1_h5_capacity_negative()
                mutate(rejected)
                record = build_hybrid_funnel([m80, m120, rejected])
                self.assertEqual(record["status"], "not_qualified")
                self.assertNotEqual(record["failures"], [P1_H5_CAPACITY_FAILURE])
                self.assertFalse(
                    record["qualification"]["modal_basis_capacity_limited"]
                )

    def test_missing_or_wrong_mpi4_command_fails_closed(self) -> None:
        for command in (None, ["mpiexec", "-n", "2", "python", "hybrid"]):
            with self.subTest(command=command):
                shards = [_shard(mode) for mode in (80, 120, 160)]
                if command is None:
                    shards[1].pop("command")
                else:
                    shards[1]["command"] = command
                record = build_hybrid_funnel(shards)
                self.assertEqual(record["status"], "not_qualified")
                self.assertIn(
                    "one or more funnel shards failed the external watchdog contract",
                    record["failures"],
                )

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
