"""Scalar software decisions only; no A, labels, model forward or solver."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.solvers.neural_deployment_cost import (
    BOUNDARY,
    PHASES,
    consume_timing,
    frozen_v45_costs,
    necessary_time_condition,
    select_cold_n1,
    summarize,
    twenty_percent_time,
)
from src.solvers.neural_engine_contract import (
    check_engine,
    consume_contract,
    memory_condition,
    read_metadata,
)


def route(name, total, *, unknown=None, proof=False):
    evidence = {"path": "synthetic.json", "sha256": "a" * 64, "source_sha": "b" * 40}
    terms = [
        {
            "phase": phase,
            "value": total if phase == "training" else 0,
            "unit": "s",
            "classification": "derived",
            "boundary": BOUNDARY,
            "consumption_id": name + ":" + phase,
            "consumed_object": name + ":" + phase,
            "evidence": evidence,
        }
        for phase in PHASES
    ]
    if unknown:
        term = {
            "phase": "setup",
            "value": None,
            "unit": "s",
            "classification": "unknown",
            "boundary": BOUNDARY,
            "consumption_id": name + ":unknown",
            "consumed_object": "c" * 64,
            "evidence": evidence,
            "semantics": unknown,
        }
        if proof:
            term["common_unknown_proof"] = {
                "object_hash": "c" * 64,
                "source_sha": "b" * 40,
                "evidence_sha256": "a" * 64,
                "lifetime": "identical fresh geometry lifetime",
                "boundary": BOUNDARY,
                "same_consumption_count": 1,
                "same_object_and_lifetime": True,
            }
        terms.append(term)
    return {"route": name, "boundary": BOUNDARY, "terms": terms}


def engine_fixture():
    request = {
        "physics": {
            "geometry_nm": [50, 25, -10, 130],
            "wavelength_nm": "0.7",
            "material_hash": "1" * 64,
        },
        "discretization": {
            "degree": 6,
            "native_map_hash": "2" * 64,
            "owner_hash": "3" * 64,
        },
        "problem": {
            "full_ports": 32060,
            "full_A": True,
            "full_AH": True,
            "rhs_kind": "physical",
            "recovery": True,
        },
        "correctness": {"full_residual": True, "field": True, "power": True},
        "engineering": {
            "payload_consumable": True,
            "cold_cost_complete": True,
            "MPI": 1,
        },
        "neural": {"full_residual_adjoint_interface": True},
    }
    offered = copy.deepcopy(request)
    offered["evidence"] = {"source_sha": "f" * 40, "sha256": "e" * 64}
    return request, offered


def study_fixture(routes, correct):
    names = {"R0": "R0", "CL44": "CL44", "LH": "LIN-H", "NL": "NN-L", "NH": "NN-H"}
    seen = []
    scope = SimpleNamespace(
        stage=lambda _: ({"full_pass_by_route": correct}, None),
        deployment_cost_contract=lambda: routes,
    )
    frozen = {
        c: {"selected": {"median_qe": 1, "max_qe": 1, "median_qr": 1, "update": 0}}
        for c in ("NL", "NH")
    }
    study = SimpleNamespace(
        scope=scope,
        routes=names,
        control_routes=("R0", "CL44", "LIN-H"),
        frozen_models=lambda: frozen,
        evaluate=lambda folder, budget, code: (
            seen.append(code) or {"synthetic_only": True}
        ),
    )
    return study, seen


class Costs(unittest.TestCase):
    def test_all_actual_routes_unqualified_reject_before_evaluate(self):
        routes = {r: route(r, 1) for r in ("R0", "CL44", "LIN-H")}
        counts = dict.fromkeys(("R0", "CL44", "LIN-H", "NN-L", "NN-H"), 0)
        self.assertEqual(
            select_cold_n1(routes, counts)["status"], "NO_ALL_EIGHT_CORRECT_ROUTE"
        )
        study, seen = study_fixture(routes, counts)
        with self.assertRaisesRegex(ValueError, "all-eight correctness"):
            consume_timing(study, None, None, "CONTROL")
        self.assertEqual(seen, [])

    def test_cl44_linh_counterexample_corrected_in_actual_consumer(self):
        routes = {
            "CL44": route("CL44", 619.2285887566395),
            "LIN-H": route("LIN-H", 701.5235948761692),
        }
        counts = {"CL44": 8, "LIN-H": 8, "NN-L": 8, "NN-H": 8}
        # Historical mixed scores would choose LIN-H; complete-boundary scores choose CL44.
        self.assertLess(242.6734232934, 616.6864592782)
        self.assertEqual(select_cold_n1(routes, counts)["selected"], "CL44")
        study, seen = study_fixture(routes, counts)
        study.control_routes = ("CL44", "LIN-H")
        result = consume_timing(study, None, None, "CONTROL")
        self.assertEqual(seen, ["CL44"])
        self.assertEqual(result["selected_control"], "CL44")

    def test_different_unknown_does_not_turn_into_zero(self):
        routes = {
            "a": route("a", 1, unknown="fresh geometry"),
            "b": route("b", 2, unknown="different geometry"),
        }
        self.assertEqual(
            select_cold_n1(routes, {"a": 8, "b": 8})["status"], "COST_ORDER_UNRESOLVED"
        )
        self.assertIsNone(summarize(routes["a"])["complete_seconds"])

    def test_proven_identical_unknown_order_not_percentage(self):
        routes = {
            "a": route("a", 100, unknown="same", proof=True),
            "b": route("b", 70, unknown="same", proof=True),
        }
        result = select_cold_n1(routes, {"a": 8, "b": 8})
        self.assertEqual(result["selected"], "b")
        self.assertEqual(result["status"], "COMMON_UNKNOWN_CANCELLED_FOR_ORDER_ONLY")
        self.assertEqual(
            twenty_percent_time(
                routes["a"],
                routes["b"],
                same_correctness=True,
                measured_comparable=True,
            )["status"],
            "UNKNOWN_FULL_COST_DENOMINATOR",
        )

    def test_unbound_common_label_and_wrong_lifetime_rejected(self):
        a, b = (
            route("a", 1, unknown="same", proof=True),
            route("b", 2, unknown="same", proof=True),
        )
        b["terms"][-1]["common_unknown_proof"]["lifetime"] = "cached rather than cold"
        self.assertEqual(
            select_cold_n1({"a": a, "b": b}, {"a": 8, "b": 8})["status"],
            "COST_ORDER_UNRESOLVED",
        )
        b["terms"][-1]["common_unknown_proof"]["object_hash"] = "d" * 64
        self.assertIsNone(
            select_cold_n1({"a": a, "b": b}, {"a": 8, "b": 8})["selected"]
        )

    def test_duplicate_inherited_consumption_rejected(self):
        a = route("a", 4)
        a["terms"].append(dict(a["terms"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            summarize(a)

    def test_unit_nonfinite_and_missing_phase_rejected(self):
        for alteration in ("unit", "nonfinite", "phase"):
            a = route("a", 4)
            if alteration == "unit":
                a["terms"][0]["unit"] = "ms"
            elif alteration == "nonfinite":
                a["terms"][0]["value"] = float("nan")
            else:
                a["terms"].pop()
            with self.assertRaises(ValueError):
                summarize(a)

    def test_unknown_zero_filling_rejected(self):
        a = route("a", 1, unknown="unknown")
        a["terms"][-1]["value"] = 0
        with self.assertRaisesRegex(ValueError, "zero-filled"):
            summarize(a)

    def test_necessary_time_conditions_zero_and_unknown(self):
        d = necessary_time_condition(
            common=20, unavoidable=20, variable=60, overhead=5, fraction=0.5
        )
        self.assertEqual(d["maximum_actual_saving_seconds"], 25)
        self.assertTrue(d["time_condition"])
        self.assertEqual(d["NN20"], "NOT_QUALIFIED")
        self.assertFalse(
            necessary_time_condition(
                common=20, unavoidable=20, variable=60, overhead=0, fraction=0
            )["time_condition"]
        )
        self.assertEqual(
            necessary_time_condition(
                common=None, unavoidable=20, variable=60, overhead=5, fraction=0.5
            )["status"],
            "UNKNOWN",
        )


class Contracts(unittest.TestCase):
    def test_nonhex_evidence_and_integer_compatible_flag_rejected(self):
        request, offered = engine_fixture()
        offered["evidence"]["source_sha"] = "x" * 40
        self.assertFalse(check_engine(request, offered)["accepted"])
        request, offered = engine_fixture()
        offered["problem"]["full_A"] = 1
        self.assertFalse(check_engine(request, offered)["accepted"])

    def test_complete_synthetic_contract_consumes_only_fixture(self):
        request, offered = engine_fixture()
        seen = []
        result = consume_contract(
            request, offered, lambda p: seen.append(p) or "synthetic consumption"
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(len(seen), 1)
        self.assertFalse(result["solver_qualification_granted"])

    def test_partial_q0_real_semantics_reject_before_consumption(self):
        request, offered = engine_fixture()
        seen = []
        offered["problem"].update(full_ports=532, full_A=False, rhs_kind="manufactured")
        offered["correctness"]["field"] = False
        result = consume_contract(request, offered, lambda p: seen.append(p))
        self.assertEqual(result["status"], "NO_MATCHED_QUALIFIED_ENGINE")
        self.assertEqual(seen, [])

    def test_same_wavelength_different_physics_rejected(self):
        request, offered = engine_fixture()
        offered["physics"]["geometry_nm"] = [2.5, 1.25, 0, 7]
        self.assertFalse(check_engine(request, offered)["layer_pass"]["physics"])

    def test_direction_mpc_owner_and_ah_are_independent_gates(self):
        for layer, key in (
            ("discretization", "native_map_hash"),
            ("discretization", "owner_hash"),
            ("problem", "full_AH"),
        ):
            request, offered = engine_fixture()
            offered[layer][key] = "wrong"
            self.assertFalse(check_engine(request, offered)["layer_pass"][layer])

    def test_unknown_requirement_does_not_match_unknown(self):
        request, offered = engine_fixture()
        request["physics"]["incidence"] = None
        offered["physics"]["incidence"] = None
        self.assertFalse(check_engine(request, offered)["accepted"])

    def test_compatible_flag_and_unbound_evidence_cannot_pass(self):
        request, offered = engine_fixture()
        offered["compatible"] = True
        offered["evidence"] = {}
        self.assertFalse(check_engine(request, offered)["accepted"])

    def test_no_empty_layer_false_pass(self):
        request, offered = engine_fixture()
        request["neural"] = {}
        self.assertFalse(check_engine(request, offered)["accepted"])

    def test_simultaneous_memory_not_sum_or_archives(self):
        base = [
            {"bytes": 100, "start": 0, "end": 2, "kind": "solver"},
            {"bytes": 50, "start": 2, "end": 3, "kind": "solver"},
        ]
        neural = [{"bytes": 79, "start": 0, "end": 3, "kind": "solver"}]
        result = memory_condition(base, neural, time_seconds=172800)
        self.assertEqual(result["baseline_peak_bytes"], 100)
        self.assertTrue(result["memory_condition"])
        base[0]["bytes"] = None
        self.assertEqual(
            memory_condition(base, neural, time_seconds=None)["status"], "UNKNOWN"
        )

    def test_small_metadata_hash_and_path_refuse(self):
        import hashlib

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text('{"toy":true}')
            r = {"path": "m.json", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertTrue(read_metadata(r, td)["toy"])
            with self.assertRaisesRegex(ValueError, "hash"):
                read_metadata({**r, "sha256": "0" * 64}, td)
            with self.assertRaisesRegex(ValueError, "capacity"):
                read_metadata(r, td, limit=1)


class FrozenDataAndConfig(unittest.TestCase):
    def test_complete_scalar_workflow_consumes_frozen_records_without_engine(self):
        from benchmarks.neural_deployment_decision import run

        root = Path(__file__).resolve().parents[2]
        plan = json.loads(
            (
                root / "input/task042_neural_coarse_inverse/neural_deployment_v46.json"
            ).read_text()
        )
        with tempfile.TemporaryDirectory() as td:
            result = run(plan, root, td)
            self.assertEqual(result["numeric_actions"], 0)
            self.assertEqual(result["cost_selection"], "NO_ALL_EIGHT_CORRECT_ROUTE")
            self.assertEqual(result["engine"], "NO_MATCHED_QUALIFIED_ENGINE")
            self.assertEqual(len(list(Path(td).glob("*.json"))), 4)
            bad = copy.deepcopy(plan)
            bad["parents"]["cost"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash"):
                run(bad, root, td)

    def test_frozen_scalar_costs_and_single_cl44_inheritance(self):
        root = Path(__file__).resolve().parents[2]
        rec = root / "docs/task042_neural_coarse_inverse/outcomes/records"
        from src.solvers.neural_deployment_cost import file_receipt

        report = json.loads((rec / "resource_costs_v45.json").read_text())
        comparison = json.loads(
            (rec / "neural_candidate_comparison_v45.json").read_text()
        )
        evidence = file_receipt(
            rec / "resource_costs_v45.json",
            source="53b7a109160e52caf6a712b1d4059b6adbb049ce",
        )
        old = file_receipt(
            rec / "resource_costs_v44.json",
            source="9c6d8491a34ff3aae8e77fbe8c041a79a8ef0898",
        )
        routes = frozen_v45_costs(
            report, comparison, evidence=evidence, inherited_evidence=old
        )
        for name, r in routes.items():
            self.assertAlmostEqual(
                summarize(r)["known_lower_seconds"],
                report["route_costs"][name]["N1_known_lower_scenario_seconds"],
                places=9,
            )
        inherited = [
            t for t in routes["CL44"]["terms"] if ":inherited:" in t["consumption_id"]
        ]
        self.assertAlmostEqual(sum(t["value"] for t in inherited), 493.7489533459302)
        self.assertEqual(
            {t["phase"] for t in inherited}, {"setup", "training", "data_teacher"}
        )
        self.assertTrue(
            all(
                any(t["phase"] == "failures" and t["value"] is None for t in r["terms"])
                for r in routes.values()
            )
        )

    def test_storage_profile_new_and_old_namespace_changes(self):
        from src.runners.port_preparation import storage_limits

        self.assertEqual(storage_limits("v43")["task_storage_bytes"], 24 * 2**30)
        self.assertEqual(storage_limits("v42")["task_storage_bytes"], 64 * 2**30)
        self.assertEqual(storage_limits("v36")["task_storage_bytes"], 20 * 2**30)
        frozen = {
            "new_storage_bytes": 64 * 2**20,
            "task_storage_bytes": 24 * 2**30,
            "free_bytes": 50 * 2**30,
            "evidence_reserve_bytes": 256 * 2**20,
        }
        with patch(
            "src.solvers.neural_decision_scope.plan_record", return_value=frozen
        ):
            self.assertEqual(storage_limits("v46"), frozen)

    def test_live_guard_rejects_wrong_profile(self):
        from src.runners.port_preparation import PreparationHealth

        with self.assertRaisesRegex(ValueError, "identical frozen plan"):
            PreparationHealth(
                Path("."), [], "v46", limits={"task_storage_bytes": 20 * 2**30}
            )

    def test_closed_window_refuses_even_with_correct_storage(self):
        import time
        from datetime import datetime, timezone

        from src.runners.task042_shared import write_json
        from src.solvers.port_preparation_window import PreparationWindow

        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            w = PreparationWindow(
                p, label="V46-FIXTURE", total=900, probe=60, reserve=60, bootstrap=0
            )
            write_json(
                p / "window.json",
                {
                    "start_utc": datetime.now(timezone.utc).isoformat(),
                    "start_monotonic": time.monotonic(),
                    "boot_id": Path("/proc/sys/kernel/random/boot_id")
                    .read_text()
                    .strip(),
                    "total_limit_seconds": 86400,
                    "heavy_limit_seconds": 82800,
                },
            )
            write_json(p / "ledger.json", {"runs": [], "active": None, "closed": True})
            with self.assertRaisesRegex(RuntimeError, "closed/active"):
                w.require_ready()

    @unittest.skipUnless(
        os.environ.get("TASK042_ENV_MODE") == "ml",
        "isolated ML import-only wiring check",
    )
    def test_actual_fullmoment_method_calls_pure_consumer(self):
        import torch

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        from src.solvers.full_moment_study import FullMomentStudy

        routes = {"CL44": route("CL44", 619), "LIN-H": route("LIN-H", 701)}
        study, seen = study_fixture(
            routes, {"CL44": 8, "LIN-H": 8, "NN-L": 8, "NN-H": 8}
        )
        study.control_routes = ("CL44", "LIN-H")
        result = FullMomentStudy.timing(study, None, None, "CONTROL")
        self.assertEqual(result["selected_control"], "CL44")
        self.assertEqual(seen, ["CL44"])


if __name__ == "__main__":
    unittest.main()
