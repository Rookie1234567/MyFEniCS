from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from benchmarks.run_task032_phase6_augmented import (
    _discrete_axial_qualification_scope,
    _hybrid_p_disposition,
    _parse_args as parse_phase6_args,
)
from benchmarks.run_task033_full3d_watchdog import (
    _parse_args as parse_full3d_args,
    _validate_task035c_p6_preflight,
)
from benchmarks.run_task033_memory_watchdog import (
    _parse_args as parse_memory_args,
    _worker_command,
)
from benchmarks.task035c_p6_h10_gates import (
    task036_full3d_reference_gate,
    task035c_p6_h10_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
)


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json"
)
AUTHORITY_SHA256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
SOURCE_SHA = "a" * 40
RECORD_SHA256 = "b" * 64


def _full3d_reference(backend: str) -> dict:
    return {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": "full3d_reference_pass",
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 8,
        "polarization_kind": "s",
        "run_kind": "full-solve",
        "return_code": 0,
        "stage4_full3d_assembly_backend_requested": backend,
        "stage4_full3d_assembly_backend_actual": backend,
        "solver_summary_sha256": "c" * 64,
        "progress_sha256": "d" * 64,
        "timeline_sha256": "e" * 64,
        "source": {
            "commit_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
        },
        "qualification": {
            "pass": True,
            "failures": [],
            "checks": {
                "official_result": True,
                "ksp_converged": True,
                "reference_exported": True,
                "swap_policy_satisfied": True,
            },
        },
        "solver_summary": {
            "stage_case": "stage4_block_grating",
            "geometry_kind": "rectangular_block_grating",
            "stage4_full3d_assembly_backend_actual": backend,
            "official_result": True,
            "full3d_reference_exported": True,
            "linear_system_relative_residual": 1.0e-12,
            "config": {
                "nedelec_degree": 6,
                "mesh_target_size": 10.0,
                "lambda0": 13.5,
                "incident_theta_deg": 80.0,
                "incident_phi_deg": 0.0,
                "period_x": 50.0,
                "period_y": 25.0,
                "z_min": -10.0,
                "z_max": 130.0,
                "grating_height": 120.0,
                "grating_width_x": 17.0,
                "grating_width_y": 25.0,
                "use_floquet_xy": True,
                "stage4_boundary_model": "dtn_port",
                "stage4_dtn_assembly": "auxiliary",
                "scattering_background": "layered",
                "full3d_reference_plane_z": [
                    10.0,
                    30.0,
                    60.0,
                    90.0,
                    110.0,
                ],
            },
        },
    }


def _task036_full3d_reference() -> dict:
    reference = _full3d_reference("assembly_time_static_condensed")
    reference.update(
        {
            "degree": 5,
            "polarization_kind": "p",
            "no_swap": True,
            "task036_forward_robustness_gate": True,
            "task036_direct_projection_audit": {
                "requested": True,
                "pass": True,
                "max_absolute_outgoing_projection_difference": 1.0e-12,
            },
            "parent_launch_descriptor": {
                "payload": {
                    "schema_version": "task033.watchdog-parent-launch.v1",
                    "worker_contract": {
                        "degree": 5,
                        "h_nm": 10.0,
                        "mpi_size": 8,
                        "polarization_kind": "p",
                        "run_kind": "full-solve",
                        "stage4_full3d_assembly_backend": (
                            "assembly_time_static_condensed"
                        ),
                        "task036_forward_robustness_gate": True,
                        "incident_grazing_deg": 0.5,
                        "incident_phi_deg": 90.0,
                        "grating_height_nm": 115.0,
                        "grating_width_x_nm": 18.0,
                        "task036_mesh_axis_cell_counts": [6, 4, 14],
                        "task036_y_invariant_n0_alias_preflight": True,
                        "task036_dtn_direct_projection_audit": True,
                        "verified_clean_sha": SOURCE_SHA,
                    },
                },
            },
        }
    )
    config = reference["solver_summary"]["config"]
    config.update(
        {
            "nedelec_degree": 5,
            "incident_theta_deg": 89.5,
            "incident_phi_deg": 90.0,
            "polarization_kind": "p",
            "grating_height": 115.0,
            "grating_width_x": 18.0,
            "mesh_axis_cell_counts": [6, 4, 14],
            "mesh_axis_cell_counts_requested": [6, 4, 14],
            "dtn_y_invariant_n0_alias_preflight": True,
            "dtn_auxiliary_direct_projection_audit": True,
        }
    )
    return reference


def _full3d_cli(backend: str = "standard_full") -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        backend,
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        str(AUTHORITY),
        "--task035c-p6-preflight-sha256",
        AUTHORITY_SHA256,
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _hybrid_cli(backend: str = "standard_full") -> list[str]:
    return [
        "--target",
        "hybrid",
        "--case-label",
        f"task035c_p6_h10_{backend}_m120",
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--mpi-size",
        "8",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "modal-schur-memory-minimal",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--stage4-full3d-assembly-backend",
        backend,
        "--full3d-reference",
        "fresh_full3d.json",
        "--full3d-reference-sha256",
        RECORD_SHA256,
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        str(AUTHORITY),
        "--task035c-p6-preflight-sha256",
        AUTHORITY_SHA256,
        "--verified-clean-sha",
        SOURCE_SHA,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]


def _phase6_cli(backend: str = "standard_full") -> list[str]:
    watchdog = _hybrid_cli(backend)
    remove_pairs = {
        "--target",
        "--case-label",
        "--mpi-size",
    }
    result: list[str] = []
    index = 0
    while index < len(watchdog):
        option = watchdog[index]
        if option in remove_pairs:
            index += 2
            continue
        result.append(option)
        index += 1
    return result


def _task036_hybrid_cli() -> list[str]:
    return [
        "--target",
        "hybrid",
        "--case-label",
        "task036_p5_h10_dynamic_p_m120",
        "--degree",
        "5",
        "--h-nm",
        "10",
        "--modal-degree",
        "5",
        "--modal-h-nm",
        "10",
        "--mpi-size",
        "8",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "modal-schur-memory-minimal",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--full3d-reference",
        "fresh_task036_full3d.json",
        "--full3d-reference-sha256",
        RECORD_SHA256,
        "--incident-grazing-deg",
        "0.5",
        "--incident-phi-deg",
        "90",
        "--grating-height-nm",
        "115",
        "--grating-width-x-nm",
        "18",
        "--polarization-kind",
        "p",
        "--task036-domain-robustness-gate",
        "--task036-mesh-axis-cell-counts",
        "6",
        "4",
        "14",
        "--task036-y-invariant-n0-alias-preflight",
        "--task036-dtn-direct-projection-audit",
        "--task036-scalar-stage4-reciprocal-basis",
        "--verified-clean-sha",
        SOURCE_SHA,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]


class Task035cP6H10RunnerGateTests(unittest.TestCase):
    def test_task036_dynamic_p5_hybrid_port_round_trip(self) -> None:
        args = parse_memory_args(_task036_hybrid_cli())
        self.assertTrue(args.task036_domain_robustness_gate)
        self.assertEqual(args.degree, 5)
        self.assertEqual(args.modal_degree, 5)
        self.assertEqual(args.task036_mesh_axis_cell_counts, [6, 4, 14])
        command = _worker_command(
            args, Path("record.json"), Path("stages.jsonl")
        )
        for option, value in (
            ("--incident-phi-deg", "90.0"),
            ("--grating-height-nm", "115.0"),
            ("--grating-width-x-nm", "18.0"),
            ("--full3d-reference-sha256", RECORD_SHA256),
        ):
            self.assertIn(option, command)
            self.assertEqual(command[command.index(option) + 1], value)
        self.assertIn("--task036-domain-robustness-gate", command)
        self.assertIn("--task036-y-invariant-n0-alias-preflight", command)
        self.assertIn("--task036-dtn-direct-projection-audit", command)
        self.assertIn("--task036-scalar-stage4-reciprocal-basis", command)
        module_index = command.index(
            "benchmarks.run_task032_phase6_augmented"
        )
        worker = parse_phase6_args(command[module_index + 1 :])
        self.assertTrue(worker.task036_domain_robustness_gate)
        self.assertEqual(worker.degree, 5)
        self.assertEqual(worker.modal_degree, 5)
        self.assertEqual(worker.task036_mesh_axis_cell_counts, [6, 4, 14])

    def test_task036_dynamic_full3d_reference_is_exactly_bound(self) -> None:
        reference = _task036_full3d_reference()
        common = {
            "expected_sha256": RECORD_SHA256,
            "observed_sha256": RECORD_SHA256,
            "current_source_sha": SOURCE_SHA,
            "assembly_backend": "assembly_time_static_condensed",
            "degree": 5,
            "h_nm": 10.0,
            "mpi_size": 8,
            "polarization_kind": "p",
            "incident_grazing_deg": 0.5,
            "incident_phi_deg": 90.0,
            "grating_height_nm": 115.0,
            "grating_width_x_nm": 18.0,
            "mesh_axis_cell_counts": (6, 4, 14),
        }
        accepted = task036_full3d_reference_gate(reference, **common)
        self.assertTrue(accepted["pass"], accepted["failures"])

        mutations = (
            ("incident_phi_deg", 89.0, "matching_task036_physics_identity"),
            ("grating_height_nm", 116.0, "matching_task036_physics_identity"),
            ("grating_width_x_nm", 17.0, "matching_task036_physics_identity"),
            (
                "mesh_axis_cell_counts",
                (6, 3, 14),
                "same_discretization_and_polarization",
            ),
            ("polarization_kind", "s", "same_discretization_and_polarization"),
            ("current_source_sha", "f" * 40, "exact_final_source_sha"),
        )
        for key, value, failure in mutations:
            with self.subTest(key=key):
                rejected = task036_full3d_reference_gate(
                    reference, **{**common, key: value}
                )
                self.assertFalse(rejected["pass"])
                self.assertIn(failure, rejected["failures"])

    def test_task036_gate_rejects_scope_drift_and_p5_stays_opt_in(self) -> None:
        with self.assertRaises(SystemExit):
            parse_memory_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "p5_without_task036",
                    "--degree",
                    "5",
                    "--h-nm",
                    "10",
                    "--mpi-size",
                    "8",
                    "--verified-clean-sha",
                    SOURCE_SHA,
                ]
            )
        for option, value in (
            ("--mpi-size", "4"),
            ("--incident-grazing-deg", "0.49"),
            ("--incident-phi-deg", "90.1"),
            ("--grating-height-nm", "126"),
            ("--grating-width-x-nm", "15.9"),
            ("--modal-degree", "6"),
        ):
            cli = _task036_hybrid_cli()
            cli[cli.index(option) + 1] = value
            with self.subTest(option=option):
                with self.assertRaises(SystemExit):
                    parse_memory_args(cli)

    def test_task036_phi_alias_cli_and_hybrid_p_disposition(self) -> None:
        defaults = parse_phase6_args([])
        self.assertEqual(defaults.incident_phi_deg, 0.0)
        self.assertFalse(defaults.task036_y_invariant_n0_alias_preflight)
        explicit = parse_phase6_args(
            [
                "--incident-phi-deg",
                "54.420819",
                "--task036-y-invariant-n0-alias-preflight",
                "--task036-mesh-axis-cell-counts",
                "6",
                "3",
                "14",
            ]
        )
        self.assertAlmostEqual(explicit.incident_phi_deg, 54.420819)
        self.assertEqual(
            explicit.task036_mesh_axis_cell_counts,
            [6, 3, 14],
        )
        full3d = parse_full3d_args(
            [
                "--degree",
                "5",
                "--h-nm",
                "10",
                "--polarization-kind",
                "s",
                "--run-kind",
                "full-solve",
                "--mpi-size",
                "8",
                "--stage4-full3d-assembly-backend",
                "assembly_time_static_condensed",
                "--task036-forward-robustness-gate",
                "--incident-grazing-deg",
                "4.538499870338",
                "--incident-phi-deg",
                "54.420819282532",
                "--grating-height-nm",
                "116.446369998157",
                "--grating-width-x-nm",
                "17.513626368716",
                "--task036-mesh-axis-cell-counts",
                "6",
                "4",
                "14",
                "--task036-y-invariant-n0-alias-preflight",
                "--task036-dtn-direct-projection-audit",
                "--verified-clean-sha",
                SOURCE_SHA,
            ]
        )
        self.assertTrue(full3d.task036_forward_robustness_gate)
        self.assertEqual(
            full3d.task036_mesh_axis_cell_counts,
            [6, 4, 14],
        )
        self.assertTrue(
            full3d.task036_y_invariant_n0_alias_preflight
        )
        self.assertTrue(full3d.task036_dtn_direct_projection_audit)

        common = {
            "full3d_physical_solution_exists": True,
            "modal_rank_evidence": "unit",
            "interface_closure_gate_names": ("interface",),
            "diagnostic_projection_evidence": "unit",
        }
        projection = _hybrid_p_disposition(
            "p",
            modal_rank_sufficient=True,
            interface_closure_pass=True,
            diagnostic_projection_bug=True,
            **common,
        )
        self.assertEqual(
            projection["primary_status"],
            "diagnostic_projection_bug",
        )
        rank = _hybrid_p_disposition(
            "p",
            modal_rank_sufficient=False,
            interface_closure_pass=True,
            diagnostic_projection_bug=False,
            **common,
        )
        self.assertEqual(
            rank["primary_status"],
            "hybrid_modal_rank_insufficient",
        )
        pending = _hybrid_p_disposition(
            "p",
            modal_rank_sufficient=None,
            interface_closure_pass=True,
            diagnostic_projection_bug=False,
            **common,
        )
        self.assertEqual(
            pending["primary_status"],
            "hybrid_modal_rank_pending_actual_M_convergence",
        )
        self.assertFalse(pending["hybrid_modal_rank_insufficient"])
        interface = _hybrid_p_disposition(
            "p",
            modal_rank_sufficient=True,
            interface_closure_pass=False,
            diagnostic_projection_bug=False,
            **common,
        )
        self.assertEqual(
            interface["primary_status"],
            "hybrid_interface_closure_failed",
        )
        quarantined = _hybrid_p_disposition(
            "p",
            modal_rank_sufficient=True,
            interface_closure_pass=True,
            diagnostic_projection_bug=False,
            **common,
        )
        self.assertFalse(quarantined["hybrid_p_production_qualified"])
        self.assertFalse(
            quarantined["full3d_fallback_is_hybrid_success"]
        )
        self.assertFalse(
            _hybrid_p_disposition(
                "s",
                modal_rank_sufficient=True,
                interface_closure_pass=True,
                diagnostic_projection_bug=False,
                **common,
            )["applicable"]
        )

    def test_ordinary_defaults_remain_unchanged(self) -> None:
        phase6 = parse_phase6_args([])
        self.assertEqual(phase6.degree, 2)
        self.assertEqual(phase6.solver_path, "augmented")
        self.assertEqual(
            phase6.stage4_full3d_assembly_backend, "standard_full"
        )
        self.assertFalse(phase6.task035c_p6_h10_gate)

        full3d = parse_full3d_args(["--degree", "3"])
        self.assertEqual(
            full3d.stage4_full3d_assembly_backend, "standard_full"
        )
        self.assertFalse(full3d.task035c_p6_h10_gate)

    def test_discrete_axial_scope_is_user_visible_and_fail_closed(self) -> None:
        ordinary = _discrete_axial_qualification_scope(
            "continuous_beta",
            "continuous_qep_beta",
        )
        self.assertFalse(ordinary["selected"])
        self.assertEqual(
            ordinary["status"],
            "not_selected_ordinary_continuous_symbols",
        )

        selected = _discrete_axial_qualification_scope(
            "full3d_uniform_cg",
            "scalar_cg_discrete_derivative",
        )
        self.assertTrue(selected["selected"])
        self.assertIn(
            "uniform z segmentation in the modal middle region",
            selected["qualified"],
        )
        self.assertIn("nonuniform z spacing", selected["not_qualified"])
        self.assertIn(
            "locally refined or hanging-node hexa mesh",
            selected["not_qualified"],
        )
        self.assertIn("no fallback", selected["failure_policy"])

    def test_p6_remains_closed_without_explicit_task035c_gate(self) -> None:
        with self.assertRaises(SystemExit):
            parse_full3d_args(["--degree", "6", "--h-nm", "10"])
        with self.assertRaises(SystemExit):
            parse_memory_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "closed",
                    "--degree",
                    "6",
                    "--h-nm",
                    "10",
                    "--mpi-size",
                    "1",
                    "--verified-clean-sha",
                    SOURCE_SHA,
                ]
            )
        with self.assertRaises(SystemExit):
            parse_phase6_args(["--degree", "6", "--h-nm", "10"])

    def test_full3d_gate_accepts_only_scoped_p6_h10_authority(self) -> None:
        for backend in ("standard_full", "assembly_time_static_condensed"):
            with self.subTest(backend=backend):
                args = parse_full3d_args(_full3d_cli(backend))
                self.assertEqual(args.degree, 6)
                self.assertTrue(_validate_task035c_p6_preflight(args)["pass"])

        invalid = _full3d_cli()
        invalid[invalid.index("--polarization-kind") + 1] = "p"
        with self.assertRaises(SystemExit):
            parse_full3d_args(invalid)
        invalid = _full3d_cli()
        invalid[invalid.index("--task035c-p6-preflight-sha256") + 1] = "0" * 64
        args = parse_full3d_args(invalid)
        with self.assertRaises(SystemExit):
            _validate_task035c_p6_preflight(args)

    def test_hybrid_gate_accepts_m120_m160_and_both_backends(self) -> None:
        for backend in ("standard_full", "assembly_time_static_condensed"):
            for modes in (120, 160):
                cli = _hybrid_cli(backend)
                cli[cli.index("--requested-modes") + 1] = str(modes)
                cli[cli.index("--candidate-modes") + 1] = str(2 * modes)
                with self.subTest(backend=backend, modes=modes):
                    args = parse_memory_args(cli)
                    command = _worker_command(
                        args, Path("record.json"), Path("stages.jsonl")
                    )
                    self.assertIn("--task035c-p6-h10-gate", command)
                    self.assertIn("--full3d-reference-sha256", command)
                    self.assertIn("--modal-degree", command)
                    self.assertIn("--modal-h-nm", command)

                    worker = parse_phase6_args(_phase6_cli(backend))
                    self.assertTrue(worker.task035c_p6_h10_gate)

    def test_hybrid_gate_rejects_scope_drift(self) -> None:
        replacements = (
            ("--h-nm", "7.5"),
            ("--modal-degree", "5"),
            ("--modal-h-nm", "7.5"),
            ("--requested-modes", "80"),
            ("--candidate-modes", "241"),
            ("--solver-path", "modal-schur-fast"),
            ("--internal-propagation-model", "continuous_beta"),
            ("--internal-traction-model", "continuous_qep_beta"),
            ("--polarization-kind", "p"),
        )
        for option, value in replacements:
            cli = _hybrid_cli()
            if option in cli:
                cli[cli.index(option) + 1] = value
            else:
                cli.extend((option, value))
            with self.subTest(option=option, value=value):
                with self.assertRaises(SystemExit):
                    parse_memory_args(cli)

    def test_historical_and_fresh_reference_gates_fail_closed(self) -> None:
        historical = json.loads(AUTHORITY.read_text(encoding="utf-8"))
        accepted = task035c_p6_h10_preflight_authority_gate(
            historical,
            expected_sha256=AUTHORITY_SHA256,
            observed_sha256=AUTHORITY_SHA256,
            authority_is_tracked=True,
        )
        self.assertTrue(accepted["pass"], accepted["failures"])
        rejected = task035c_p6_h10_preflight_authority_gate(
            historical,
            expected_sha256="0" * 64,
            observed_sha256=AUTHORITY_SHA256,
            authority_is_tracked=True,
        )
        self.assertFalse(rejected["pass"])
        self.assertIn("record_hash_matches_expected", rejected["failures"])

        for backend in ("standard_full", "assembly_time_static_condensed"):
            reference = _full3d_reference(backend)
            accepted = task035c_p6_h10_full3d_reference_gate(
                reference,
                expected_sha256=RECORD_SHA256,
                observed_sha256=RECORD_SHA256,
                current_source_sha=SOURCE_SHA,
                assembly_backend=backend,
                mpi_size=8,
            )
            self.assertTrue(accepted["pass"], accepted["failures"])
            stale = task035c_p6_h10_full3d_reference_gate(
                reference,
                expected_sha256=RECORD_SHA256,
                observed_sha256=RECORD_SHA256,
                current_source_sha="f" * 40,
                assembly_backend=backend,
                mpi_size=8,
            )
            self.assertFalse(stale["pass"])
            self.assertIn("exact_final_source_sha", stale["failures"])

            oblique = _full3d_reference(backend)
            oblique["solver_summary"]["config"]["incident_phi_deg"] = 45.0
            accepted_oblique = task035c_p6_h10_full3d_reference_gate(
                oblique,
                expected_sha256=RECORD_SHA256,
                observed_sha256=RECORD_SHA256,
                current_source_sha=SOURCE_SHA,
                assembly_backend=backend,
                mpi_size=8,
                incident_grazing_deg=10.0,
                incident_phi_deg=45.0,
            )
            self.assertTrue(
                accepted_oblique["pass"],
                accepted_oblique["failures"],
            )
            rejected_wrong_phi = task035c_p6_h10_full3d_reference_gate(
                oblique,
                expected_sha256=RECORD_SHA256,
                observed_sha256=RECORD_SHA256,
                current_source_sha=SOURCE_SHA,
                assembly_backend=backend,
                mpi_size=8,
            )
            self.assertFalse(rejected_wrong_phi["pass"])
            self.assertIn(
                "fixed_rectangular_physics",
                rejected_wrong_phi["failures"],
            )


if __name__ == "__main__":
    unittest.main()
