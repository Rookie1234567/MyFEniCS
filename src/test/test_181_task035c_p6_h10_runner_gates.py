from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from benchmarks.run_task032_phase6_augmented import (
    _discrete_axial_qualification_scope,
    _parse_args as parse_phase6_args,
)
from benchmarks.run_task033_full3d_watchdog import (
    _parse_args as parse_full3d_args,
    _validate_task035c_p6_preflight,
)
from benchmarks.run_task033_memory_watchdog import (
    _parse_args as parse_memory_args,
    _hybrid_measurements,
    _worker_command,
)
from benchmarks.task035c_p6_h10_gates import (
    task035c_p6_h10_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
    task037b_h1_pinned_full3d_reference_gate,
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


def _h1_hybrid_cli() -> list[str]:
    cli = _hybrid_cli("assembly_time_static_condensed")
    cli[cli.index("--solver-path") + 1] = "augmented"
    cli[cli.index("--task035c-p6-h10-gate")] = "--task037b-h1-gate"
    return cli


def _h3_hybrid_cli() -> list[str]:
    cli = _hybrid_cli("assembly_time_static_condensed")
    cli[cli.index("--solver-path") + 1] = "block-ldu-exact"
    cli[cli.index("--task035c-p6-h10-gate")] = "--task037b-h3-gate"
    return cli


def _h4_hybrid_cli() -> list[str]:
    cli = _hybrid_cli("assembly_time_static_condensed")
    cli[cli.index("--solver-path") + 1] = "block-ldu-exact"
    cli[cli.index("--task035c-p6-h10-gate")] = "--task037b-h4-gate"
    return cli


def _h5_hybrid_cli() -> list[str]:
    cli = _h4_hybrid_cli()
    cli[cli.index("--solver-path") + 1] = "local-inverse-qualification"
    cli[cli.index("--task037b-h4-gate")] = "--task037b-h5-gate"
    return cli


def _v1_hybrid_cli() -> list[str]:
    cli = _h4_hybrid_cli()
    cli[cli.index("--solver-path") + 1] = "dtn-component-qualification"
    cli[cli.index("--task037b-h4-gate")] = "--task037b-v1-gate"
    return cli


def _v1_r2_hybrid_cli() -> list[str]:
    cli = _v1_hybrid_cli()
    cli[cli.index("--solver-path") + 1] = "f-only-local-inverse-qualification"
    return cli


class Task035cP6H10RunnerGateTests(unittest.TestCase):
    def test_ordinary_defaults_remain_unchanged(self) -> None:
        phase6 = parse_phase6_args([])
        self.assertEqual(phase6.degree, 2)
        self.assertEqual(phase6.solver_path, "augmented")
        self.assertEqual(phase6.stage4_full3d_assembly_backend, "standard_full")
        self.assertFalse(phase6.task035c_p6_h10_gate)
        self.assertFalse(phase6.task037b_h1_gate)
        self.assertFalse(phase6.task037b_h3_gate)
        self.assertFalse(phase6.task037b_h4_gate)
        self.assertFalse(phase6.task037b_h5_gate)
        self.assertFalse(phase6.task037b_v1_gate)

        full3d = parse_full3d_args(["--degree", "3"])
        self.assertEqual(full3d.stage4_full3d_assembly_backend, "standard_full")
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

    def test_task037b_h1_gate_and_worker_forwarding_are_scoped(self) -> None:
        args = parse_memory_args(_h1_hybrid_cli())
        self.assertTrue(args.task037b_h1_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(args.requested_modes, 120)
        self.assertEqual(args.candidate_modes, 240)
        self.assertEqual(args.solver_path, "augmented")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-h1-gate", command)
        self.assertNotIn("--task035c-p6-h10-gate", command)
        worker_cli = _h1_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_h1_gate)

    def test_task037b_h3_gate_and_worker_forwarding_are_scoped(self) -> None:
        args = parse_memory_args(_h3_hybrid_cli())
        self.assertTrue(args.task037b_h3_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(args.requested_modes, 120)
        self.assertEqual(args.candidate_modes, 240)
        self.assertEqual(args.solver_path, "block-ldu-exact")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-h3-gate", command)
        self.assertNotIn("--task037b-h1-gate", command)
        self.assertNotIn("--task035c-p6-h10-gate", command)
        worker_cli = _h3_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_h3_gate)
        self.assertEqual(worker.solver_path, "block-ldu-exact")

    def test_task037b_h3_gate_rejects_wrong_solver(self) -> None:
        cli = _h3_hybrid_cli()
        cli[cli.index("--solver-path") + 1] = "augmented"
        with self.assertRaises(SystemExit):
            parse_memory_args(cli)

    def test_task037b_h3_gate_rejects_h1_combination(self) -> None:
        cli = _h3_hybrid_cli()
        cli.append("--task037b-h1-gate")
        with self.assertRaises(SystemExit):
            parse_memory_args(cli)

    def test_task037b_h4_gate_and_worker_forwarding_are_scoped(self) -> None:
        args = parse_memory_args(_h4_hybrid_cli())
        self.assertTrue(args.task037b_h4_gate)
        self.assertFalse(args.task037b_h3_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(args.requested_modes, 120)
        self.assertEqual(args.candidate_modes, 240)
        self.assertEqual(args.solver_path, "block-ldu-exact")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-h4-gate", command)
        self.assertNotIn("--task037b-h3-gate", command)
        worker_cli = _h4_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_h4_gate)
        self.assertEqual(worker.solver_path, "block-ldu-exact")

    def test_task037b_h4_gate_rejects_wrong_solver_and_h3_combination(self) -> None:
        wrong_solver = _h4_hybrid_cli()
        wrong_solver[wrong_solver.index("--solver-path") + 1] = "augmented"
        with self.assertRaises(SystemExit):
            parse_memory_args(wrong_solver)
        combined = _h4_hybrid_cli()
        combined.append("--task037b-h3-gate")
        with self.assertRaises(SystemExit):
            parse_memory_args(combined)

    def test_task037b_h5_gate_and_worker_forwarding_are_scoped(self) -> None:
        args = parse_memory_args(_h5_hybrid_cli())
        self.assertTrue(args.task037b_h5_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(args.requested_modes, 120)
        self.assertEqual(args.candidate_modes, 240)
        self.assertEqual(args.solver_path, "local-inverse-qualification")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-h5-gate", command)
        self.assertIn("--solver-path", command)
        self.assertEqual(
            command[command.index("--solver-path") + 1],
            "local-inverse-qualification",
        )
        self.assertNotIn("--task037b-h4-gate", command)
        worker_cli = _h5_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_h5_gate)
        self.assertEqual(worker.solver_path, "local-inverse-qualification")

    def test_task037b_h5_gate_rejects_missing_wrong_solver_and_combination(
        self,
    ) -> None:
        wrong_solver = _h5_hybrid_cli()
        wrong_solver[wrong_solver.index("--solver-path") + 1] = "block-ldu-exact"
        with self.assertRaises(SystemExit):
            parse_memory_args(wrong_solver)
        missing_flag = [
            value for value in _h5_hybrid_cli() if value != "--task037b-h5-gate"
        ]
        with self.assertRaises(SystemExit):
            parse_memory_args(missing_flag)
        with self.assertRaises(SystemExit):
            parse_memory_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "ordinary_local_inverse",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "80",
                    "--candidate-modes",
                    "160",
                    "--solver-path",
                    "local-inverse-qualification",
                    "--verified-clean-sha",
                    SOURCE_SHA,
                ]
            )
        combined = _h5_hybrid_cli()
        combined.append("--task037b-h4-gate")
        with self.assertRaises(SystemExit):
            parse_memory_args(combined)

    def test_task037b_v1_gate_and_worker_forwarding_are_scoped(self) -> None:
        args = parse_memory_args(_v1_hybrid_cli())
        self.assertTrue(args.task037b_v1_gate)
        self.assertEqual(args.mpi_size, 8)
        self.assertEqual(args.requested_modes, 120)
        self.assertEqual(args.candidate_modes, 240)
        self.assertEqual(args.solver_path, "dtn-component-qualification")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-v1-gate", command)
        self.assertNotIn("--task037b-h5-gate", command)
        self.assertEqual(
            command[command.index("--solver-path") + 1],
            "dtn-component-qualification",
        )
        worker_cli = _v1_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_v1_gate)
        self.assertEqual(worker.solver_path, "dtn-component-qualification")

    def test_task037b_v1_gate_rejects_missing_wrong_solver_and_combination(
        self,
    ) -> None:
        wrong_solver = _v1_hybrid_cli()
        wrong_solver[wrong_solver.index("--solver-path") + 1] = "block-ldu-exact"
        with self.assertRaises(SystemExit):
            parse_memory_args(wrong_solver)
        missing_flag = [
            value for value in _v1_hybrid_cli() if value != "--task037b-v1-gate"
        ]
        with self.assertRaises(SystemExit):
            parse_memory_args(missing_flag)
        ordinary = [
            "--target",
            "hybrid",
            "--case-label",
            "ordinary_dtn_component",
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--mpi-size",
            "1",
            "--requested-modes",
            "80",
            "--candidate-modes",
            "160",
            "--solver-path",
            "dtn-component-qualification",
            "--verified-clean-sha",
            SOURCE_SHA,
        ]
        with self.assertRaises(SystemExit):
            parse_memory_args(ordinary)
        combined = _v1_hybrid_cli()
        combined.append("--task037b-h5-gate")
        with self.assertRaises(SystemExit):
            parse_memory_args(combined)

    def test_task037b_v1_r2_f_only_gate_and_worker_forwarding(self) -> None:
        args = parse_memory_args(_v1_r2_hybrid_cli())
        self.assertTrue(args.task037b_v1_gate)
        self.assertEqual(args.solver_path, "f-only-local-inverse-qualification")
        command = _worker_command(args, Path("record.json"), Path("stages.jsonl"))
        self.assertIn("--task037b-v1-gate", command)
        self.assertEqual(
            command[command.index("--solver-path") + 1],
            "f-only-local-inverse-qualification",
        )
        worker_cli = _v1_r2_hybrid_cli()
        remove_pairs = {"--target", "--case-label", "--mpi-size"}
        phase6_cli: list[str] = []
        index = 0
        while index < len(worker_cli):
            if worker_cli[index] in remove_pairs:
                index += 2
                continue
            phase6_cli.append(worker_cli[index])
            index += 1
        worker = parse_phase6_args(phase6_cli)
        self.assertTrue(worker.task037b_v1_gate)
        self.assertEqual(worker.solver_path, "f-only-local-inverse-qualification")
        with self.assertRaises(SystemExit):
            parse_memory_args(
                [
                    "--target",
                    "hybrid",
                    "--case-label",
                    "ordinary_f_only",
                    "--degree",
                    "2",
                    "--h-nm",
                    "5",
                    "--mpi-size",
                    "1",
                    "--requested-modes",
                    "80",
                    "--candidate-modes",
                    "160",
                    "--solver-path",
                    "f-only-local-inverse-qualification",
                    "--verified-clean-sha",
                    SOURCE_SHA,
                ]
            )

    def test_task035c_rejects_augmented_and_h1_summary_forwards(self) -> None:
        old_augmented = _hybrid_cli("assembly_time_static_condensed")
        old_augmented[old_augmented.index("--solver-path") + 1] = "augmented"
        with self.assertRaises(SystemExit):
            parse_memory_args(old_augmented)
        summary = _hybrid_measurements(
            {
                "metadata": {"task037b_h1_gate": True},
                "h1_telemetry": {"task037b_h1_gate": True},
                "h3_telemetry": {"task037b_h3_gate": True},
                "h4_telemetry": {"task037b_h4_gate": True},
                "h5_telemetry": {"task037b_h5_gate": True},
                "v1_telemetry": {"task037b_v1_gate": True},
                "hybrid_system": {
                    "block_shapes": {"A": [1, 1]},
                    "inserted_nnz_by_block": {"A": 1},
                    "operator_inventory": {"global_A_materialized": False},
                },
                "validation": {
                    "interface_e_projection": {"relative": 1.0e-12},
                    "fe_modal_traction_equilibrium": {"relative": 2.0e-12},
                },
            }
        )
        self.assertTrue(summary["h1_telemetry"]["task037b_h1_gate"])
        self.assertTrue(summary["h3_telemetry"]["task037b_h3_gate"])
        self.assertTrue(summary["h4_telemetry"]["task037b_h4_gate"])
        self.assertTrue(summary["h5_telemetry"]["task037b_h5_gate"])
        self.assertTrue(summary["v1_telemetry"]["task037b_v1_gate"])
        self.assertNotIn("h5_memory_stages", summary)
        self.assertEqual(summary["hybrid_system"]["block_shapes"], {"A": [1, 1]})
        self.assertFalse(
            summary["hybrid_system"]["operator_inventory"]["global_A_materialized"]
        )
        self.assertEqual(
            summary["validation"]["fe_modal_traction_equilibrium"]["relative"],
            2.0e-12,
        )

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
            pinned = task037b_h1_pinned_full3d_reference_gate(
                reference,
                expected_sha256=RECORD_SHA256,
                observed_sha256=RECORD_SHA256,
                current_source_sha="f" * 40,
                assembly_backend=backend,
                mpi_size=8,
            )
            self.assertTrue(pinned["pass"], pinned["failures"])
            self.assertEqual(pinned["reference_role"], "pinned_historical_case096")
            self.assertEqual(pinned["reference_source_sha"], SOURCE_SHA)
            self.assertEqual(pinned["current_hybrid_source_sha"], "f" * 40)
            self.assertNotIn("exact_final_source_sha", pinned["checks"])


if __name__ == "__main__":
    unittest.main()
