from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]
    ValidationError = ValueError  # type: ignore[misc,assignment]

from src.validation.task033_high_order_floquet_fixtures import (
    AIR_INDEX,
    CASE_ID,
    CORE_GATE_LIMITS,
    CORE_GATE_SCHEMA_VERSION,
    CURRENT_SI_INDEX,
    build_case090_record,
    complex_from_json,
    fixture_contract,
    fresnel_oracle,
    incident_direction,
    plane_wave_oracle,
    polarization_vector,
    theta_from_normal_deg,
    validate_case090_json_schema,
    validate_case090_record,
)


ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "benchmarks" / "cases" / CASE_ID


def _dot(left, right) -> complex:
    return sum(complex(a) * complex(b) for a, b in zip(left, right))


def _valid_core_gate() -> dict:
    return {
        "schema_version": CORE_GATE_SCHEMA_VERSION,
        "record_type": "high_order_floquet_core_gate_result",
        "case_id": CASE_ID,
        "evidence_id": "clean-fixture-gate-example",
        "evidence_sha256": "2" * 64,
        "identity": {
            "is_pde_run": True,
            "is_solver_pass": True,
            "tracked_source_dirty": False,
            "source_commit_full_sha": "1" * 40,
        },
        "all_core_gates_passed": True,
        "gates": [
            {"name": name, "observed": 0.5 * limit, "passed": True}
            for name, limit in CORE_GATE_LIMITS.items()
        ],
        "coverage": [
            {
                "degree": degree,
                "mpi_size": mpi_size,
                "core_algebra_gates_passed": True,
            }
            for degree in (1, 2, 3, 4)
            for mpi_size in (1, 2, 4)
        ],
        "storage_contract": {
            "sparse_distributed_constraints": True,
            "global_boundary_allgather_used": False,
            "dense_boundary_square_formed": False,
        },
        "ordinary_regression": {
            "p1_existing_floquet_passed": True,
            "p2_existing_floquet_passed": True,
        },
    }


class Task033FixtureOracleTests(unittest.TestCase):
    def test_grazing_conversion_is_explicit_and_fail_closed(self) -> None:
        self.assertEqual(theta_from_normal_deg(1.0), 89.0)
        self.assertEqual(theta_from_normal_deg(5.0), 85.0)
        self.assertEqual(theta_from_normal_deg(10.0), 80.0)
        for invalid in (0.0, 90.0, -1.0, math.inf, math.nan):
            with self.assertRaises(ValueError):
                theta_from_normal_deg(invalid)

    def test_s_and_p_plane_waves_are_transverse_and_bloch_periodic(self) -> None:
        for grazing in (1.0, 5.0, 10.0):
            direction = incident_direction(grazing)
            self.assertAlmostEqual(math.sqrt(_dot(direction, direction).real), 1.0)
            self.assertLess(direction[2], 0.0)
            for kind in ("s", "p"):
                electric = polarization_vector(grazing, kind)
                self.assertLess(abs(_dot(direction, electric)), 1.0e-14)
                self.assertAlmostEqual(math.sqrt(_dot(electric, electric).real), 1.0)
                oracle = plane_wave_oracle(grazing_deg=grazing, polarization=kind)
                kx = complex_from_json(oracle["wavevector_per_nm"][0])
                expected = complex_from_json(oracle["bloch_phase_plus_period"]["x"])
                self.assertLess(
                    abs(
                        expected
                        - complex(math.cos((kx * 10).real), math.sin((kx * 10).real))
                    ),
                    1.0e-12,
                )

    def test_complex_fresnel_oracles_cover_air_air_and_current_si(self) -> None:
        for kind in ("s", "p"):
            no_interface = fresnel_oracle(
                grazing_deg=10.0,
                polarization=kind,
                n_incident=AIR_INDEX,
                n_transmitted=AIR_INDEX,
            )
            self.assertLess(abs(complex_from_json(no_interface["r"])), 1.0e-14)
            self.assertLess(abs(complex_from_json(no_interface["t"]) - 1.0), 1.0e-14)
            self.assertLess(abs(no_interface["R_interface"]), 1.0e-14)
            self.assertLess(
                abs(no_interface["T_into_substrate_at_interface"] - 1.0),
                1.0e-14,
            )

            lossy = fresnel_oracle(
                grazing_deg=10.0,
                polarization=kind,
                n_transmitted=CURRENT_SI_INDEX,
            )
            self.assertTrue(lossy["substrate_is_absorbing"])
            self.assertTrue(math.isfinite(lossy["R_interface"]))
            self.assertTrue(math.isfinite(lossy["T_into_substrate_at_interface"]))
            self.assertLess(abs(lossy["interface_power_closure"] - 1.0), 1.0e-12)

    def test_complex_fresnel_amplitudes_satisfy_tangential_boundaries(self) -> None:
        for grazing in (1.0, 5.0, 10.0):
            theta_i = math.radians(theta_from_normal_deg(grazing))
            cos_i = math.cos(theta_i)
            for kind in ("s", "p"):
                oracle = fresnel_oracle(
                    grazing_deg=grazing,
                    polarization=kind,
                    n_transmitted=CURRENT_SI_INDEX,
                )
                cos_t = complex_from_json(oracle["cos_theta_transmitted"])
                reflection = complex_from_json(oracle["r"])
                transmission = complex_from_json(oracle["t"])
                if kind == "s":
                    electric_jump = 1.0 + reflection - transmission
                    magnetic_jump = (
                        AIR_INDEX * cos_i * (1.0 - reflection)
                        - CURRENT_SI_INDEX * cos_t * transmission
                    )
                else:
                    electric_jump = cos_i * (1.0 - reflection) - cos_t * transmission
                    magnetic_jump = (
                        AIR_INDEX * (1.0 + reflection) - CURRENT_SI_INDEX * transmission
                    )
                self.assertLess(abs(electric_jump), 1.0e-12)
                self.assertLess(abs(magnetic_jump), 1.0e-12)

    def test_fresnel_phase_samples_include_consistent_e_and_h_fields(self) -> None:
        for grazing in (1.0, 5.0, 10.0):
            for kind in ("s", "p"):
                oracle = fresnel_oracle(
                    grazing_deg=grazing,
                    polarization=kind,
                    n_transmitted=CURRENT_SI_INDEX,
                )
                samples = oracle["field_phase_samples"]
                for wave_name in ("incident", "reflected", "transmitted"):
                    wave = samples[wave_name]
                    amplitude_phase = complex_from_json(
                        wave["amplitude"]
                    ) * complex_from_json(wave["phase"])
                    for field_name, basis_name in (
                        ("electric_field", "electric_basis"),
                        ("magnetic_code_field", "magnetic_code_basis"),
                    ):
                        observed = [
                            complex_from_json(value) for value in wave[field_name]
                        ]
                        expected = [
                            amplitude_phase * complex_from_json(value)
                            for value in wave[basis_name]
                        ]
                        self.assertLess(
                            max(abs(a - b) for a, b in zip(observed, expected)),
                            1.0e-12,
                        )
                for field_name in ("electric_field", "magnetic_code_field"):
                    incident = [
                        complex_from_json(value)
                        for value in samples["incident"][field_name]
                    ]
                    reflected = [
                        complex_from_json(value)
                        for value in samples["reflected"][field_name]
                    ]
                    total = [
                        complex_from_json(value)
                        for value in samples["upper_total"][field_name]
                    ]
                    self.assertLess(
                        max(
                            abs(a + b - combined)
                            for a, b, combined in zip(incident, reflected, total)
                        ),
                        1.0e-12,
                    )

    def test_fixture_semantics_freeze_two_distinct_ten_nm_problems(self) -> None:
        fixtures = fixture_contract()
        air = fixtures["fixture_a_air_box"]
        flat = fixtures["fixture_b_flat_air_si"]
        self.assertEqual(air["geometry"]["x_nm"], [0.0, 10.0])
        self.assertEqual(air["geometry"]["y_nm"], [0.0, 10.0])
        self.assertEqual(air["geometry"]["z_nm"], [-5.0, 5.0])
        self.assertEqual(air["material"]["uniform"], "air")
        self.assertEqual(flat["geometry"]["interface_z_nm"], 0.0)
        self.assertEqual(flat["incidence"]["smoke_grazing_deg"], [1.0, 5.0])
        self.assertEqual(
            complex_from_json(flat["material"]["lower"]["n"]),
            CURRENT_SI_INDEX,
        )

    def test_matrix_has_required_smoke_and_not_run_identity(self) -> None:
        record = build_case090_record()
        self.assertEqual(record["status"], "not_run")
        self.assertFalse(record["identity"]["is_pde_run"])
        self.assertFalse(record["identity"]["is_solver_pass"])
        self.assertEqual(record["core_gate"]["status"], "not_provided")
        self.assertEqual(record["matrix_summary"]["total"], 192)
        self.assertEqual(
            record["matrix_summary"]["requirements"],
            {"not_run": 80, "required": 96, "smoke": 16},
        )
        self.assertEqual(
            record["matrix_summary"]["execution_statuses"],
            {"not_run_by_core_gate": 112, "not_run_by_scope": 80},
        )
        self.assertTrue(
            all(
                entry["result_identity"] == "not_run"
                for entry in record["execution_matrix"]
            )
        )

    def test_schema_validator_rejects_forged_pde_or_solver_pass(self) -> None:
        record = build_case090_record()
        forged = copy.deepcopy(record)
        forged["identity"]["is_solver_pass"] = True
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            validate_case090_record(forged)
        forged = copy.deepcopy(record)
        forged["execution_matrix"][0]["result_identity"] = "pass"
        with self.assertRaisesRegex(ValueError, "forged"):
            validate_case090_record(forged)
        forged = copy.deepcopy(record)
        forged["execution_matrix"][0]["execution_status"] = "eligible_not_run"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            validate_case090_record(forged)

    def test_valid_core_gate_only_marks_cases_eligible_and_never_passed(self) -> None:
        core_gate = _valid_core_gate()
        record = build_case090_record(core_gate_payload=core_gate)
        self.assertEqual(record["core_gate"]["status"], "passed")
        self.assertEqual(record["status"], "not_run")
        self.assertEqual(
            record["matrix_summary"]["execution_statuses"],
            {"eligible_not_run": 112, "not_run_by_scope": 80},
        )
        self.assertTrue(
            all(not entry["is_pde_run"] for entry in record["execution_matrix"])
        )

        core_gate["gates"][0]["observed"] = 2.0 * next(iter(CORE_GATE_LIMITS.values()))
        blocked = build_case090_record(core_gate_payload=core_gate)
        self.assertEqual(blocked["core_gate"]["status"], "failed")
        self.assertEqual(
            blocked["matrix_summary"]["execution_statuses"],
            {"not_run_by_core_gate": 112, "not_run_by_scope": 80},
        )

    def test_core_gate_rejects_incomplete_coverage_storage_and_regression(self) -> None:
        defects = (
            ("coverage", lambda gate: gate["coverage"].pop()),
            (
                "coverage integer types",
                lambda gate: gate["coverage"][0].update({"degree": True}),
            ),
            (
                "numeric gate observed type",
                lambda gate: gate["gates"][0].update({"observed": False}),
            ),
            (
                "global allgather",
                lambda gate: gate["storage_contract"].update(
                    {"global_boundary_allgather_used": True}
                ),
            ),
            (
                "p1/p2 regression",
                lambda gate: gate["ordinary_regression"].update(
                    {"p2_existing_floquet_passed": False}
                ),
            ),
            (
                "source SHA",
                lambda gate: gate["identity"].update(
                    {"source_commit_full_sha": "short"}
                ),
            ),
            (
                "evidence_sha256",
                lambda gate: gate.update({"evidence_sha256": "short"}),
            ),
        )
        for label, mutate in defects:
            with self.subTest(label=label):
                core_gate = _valid_core_gate()
                mutate(core_gate)
                record = build_case090_record(core_gate_payload=core_gate)
                self.assertEqual(record["core_gate"]["status"], "failed")
                self.assertEqual(
                    record["matrix_summary"]["execution_statuses"],
                    {"not_run_by_core_gate": 112, "not_run_by_scope": 80},
                )

    def test_checked_in_json_contracts_match_deterministic_builder(self) -> None:
        fixture_payload = json.loads(
            (CASE_ROOT / "fixture.json").read_text(encoding="utf-8")
        )
        self.assertEqual(fixture_payload["fixtures"], fixture_contract())
        schema = json.loads((CASE_ROOT / "schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertEqual(schema["properties"]["status"]["const"], "not_run")
        record = json.loads(
            (CASE_ROOT / "records" / "analytic_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        validate_case090_record(record)
        self.assertEqual(record, build_case090_record())

    @unittest.skipUnless(
        Draft202012Validator is not None,
        "The fixed DOLFINx image omits optional jsonschema; host CI validates it.",
    )
    def test_real_draft_2020_12_schema_rejects_nested_unknown_fields(self) -> None:
        schema = json.loads((CASE_ROOT / "schema.json").read_text(encoding="utf-8"))
        record = build_case090_record()
        validate_case090_json_schema(record)
        assert Draft202012Validator is not None
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(record)
        forged = copy.deepcopy(record)
        forged["oracles"]["flat_air_si_fresnel"][0]["unexpected"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(forged)


if __name__ == "__main__":
    unittest.main()
