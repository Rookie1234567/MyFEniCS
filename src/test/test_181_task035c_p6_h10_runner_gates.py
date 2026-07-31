from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mpi4py import MPI
import numpy as np

from benchmarks import run_task032_phase6_augmented as phase6_runner
from benchmarks.run_task032_phase6_augmented import (
    _discrete_axial_qualification_scope,
    _hybrid_p_disposition,
    _parse_args as parse_phase6_args,
    _task036_middle_material_audit,
    _task036_hybrid_candidate_direct_projection_checks,
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
from src.solvers.hybrid_fem_modal_augmented_direct import (
    evaluate_hybrid_recovered_direct_projection_audit,
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


def _hybrid_projection_audit() -> dict:
    rows = [
        {
            "side": side,
            "m": 0,
            "n": 0,
            "polarization": polarization,
            "absolute_total_projection_difference": 1.0e-12,
            "absolute_outgoing_projection_difference": 1.0e-12,
        }
        for side in ("bottom", "top")
        for polarization in ("s", "p")
    ]
    return {
        "requested": True,
        "scope": "hybrid_candidate",
        "tolerance": 1.0e-10,
        "expected_mode_count": len(rows),
        "audited_mode_count": len(rows),
        "max_absolute_outgoing_projection_difference": 1.0e-12,
        "pass": True,
        "orders": rows,
    }


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
            "verified_clean_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "status_after": "",
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


def _task036_strong_hybrid_cli(
    *,
    modes: int = 120,
    point_id: str = "A001-P",
    interfaces: tuple[float, float] = (10.0, 110.0),
) -> list[str]:
    cli = _task036_hybrid_cli()
    cli[cli.index("--solver-path") + 1] = "strong-trace-direct"
    cli[cli.index("--requested-modes") + 1] = str(modes)
    cli[cli.index("--candidate-modes") + 1] = str(2 * modes)
    points = {
        "A004-S": ("0.5", "45", "120", "17", "s"),
        "A049-P": ("10", "90", "120", "17", "p"),
        "A001-P": ("0.5", "0", "120", "17", "p"),
    }
    grazing, azimuth, height, width, polarization = points[point_id]
    for option, value in (
        ("--incident-grazing-deg", grazing),
        ("--incident-phi-deg", azimuth),
        ("--grating-height-nm", height),
        ("--grating-width-x-nm", width),
        ("--polarization-kind", polarization),
    ):
        cli[cli.index(option) + 1] = value
    cli.extend(
        [
            "--bottom-interface-nm",
            str(interfaces[0]),
            "--top-interface-nm",
            str(interfaces[1]),
        ]
    )
    return cli


class Task035cP6H10RunnerGateTests(unittest.TestCase):
    def test_phase6_memory_stage_claim_is_exclusive_and_preserves_existing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_dir = root / "artifacts"
            owner = output_dir / "result.json"
            stage = output_dir / "memory_stages.jsonl"
            phase6_runner._claim_memory_stage_file(
                MPI.COMM_SELF,
                stage,
                owner_path=owner,
            )
            self.assertEqual(stage.read_bytes(), b"")

            sentinel = b'{"stage":"preserved"}\n'
            with stage.open("ab") as stream:
                stream.write(sentinel)
            with self.assertRaisesRegex(RuntimeError, "FileExistsError"):
                phase6_runner._claim_memory_stage_file(
                    MPI.COMM_SELF,
                    stage,
                    owner_path=owner,
                )
            self.assertEqual(stage.read_bytes(), sentinel)

            with self.assertRaisesRegex(RuntimeError, "must differ"):
                phase6_runner._claim_memory_stage_file(
                    MPI.COMM_SELF,
                    owner,
                    owner_path=owner,
                )
            external_stage = root / "other" / "memory_stages.jsonl"
            phase6_runner._claim_memory_stage_file(
                MPI.COMM_SELF,
                external_stage,
                owner_path=owner,
            )
            self.assertEqual(external_stage.read_bytes(), b"")
            phase6_runner._claim_memory_stage_file(
                MPI.COMM_SELF,
                None,
                owner_path=owner,
            )

    def test_phase6_memory_stage_existing_claim_is_collective_mpi2(self) -> None:
        comm = MPI.COMM_WORLD
        if comm.size != 2:
            self.skipTest("This cooperative claim regression requires MPI2.")
        temporary = tempfile.TemporaryDirectory() if comm.rank == 0 else None
        directory = comm.bcast(
            temporary.name if temporary is not None else None,
            root=0,
        )
        root = Path(directory)
        owner = root / "result.json"
        stage = root / "memory_stages.jsonl"
        sentinel = b'{"stage":"preserved-by-mpi2"}\n'
        if comm.rank == 0:
            stage.write_bytes(sentinel)
        comm.barrier()

        try:
            phase6_runner._claim_memory_stage_file(
                comm,
                stage,
                owner_path=owner,
            )
        except RuntimeError as exc:
            error = str(exc)
        else:
            error = None
        errors = comm.allgather(error)
        observed = stage.read_bytes() if comm.rank == 0 else None
        observed = comm.bcast(observed, root=0)
        if temporary is not None:
            temporary.cleanup()

        self.assertIsNotNone(errors[0])
        self.assertEqual(errors, [errors[0], errors[0]])
        self.assertIn("FileExistsError", errors[0])
        self.assertEqual(observed, sentinel)

    def test_task036_review_v5_middle_material_audit(self) -> None:
        cfg = SimpleNamespace(
            period_x=50.0,
            period_y=40.0,
            geometry_kind="rectangular_block_grating",
            grating_x_min=-8.5,
            grating_x_max=8.5,
            grating_y_min=-20.0,
            grating_y_max=20.0,
            interface_z=0.0,
            grating_z_min=0.0,
            grating_z_max=120.0,
        )
        cross_section = SimpleNamespace(
            axis_plan=SimpleNamespace(
                x_values=np.asarray([-25.0, -8.5, 8.5, 25.0]),
                y_values=np.asarray([-20.0, 20.0]),
                z_values=np.arange(-10.0, 131.0, 10.0),
            )
        )
        audit = _task036_middle_material_audit(
            cfg,
            cross_section,
            bottom_interface_nm=30.0,
            top_interface_nm=90.0,
        )
        self.assertTrue(audit["epsilon_x_y_z_equals_epsilon_x_y"])
        self.assertEqual(audit["middle_z_cell_count"], 6)
        self.assertEqual(len(audit["unique_material_layer_hashes"]), 1)

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

    def test_task036_strong_trace_port_is_narrow_and_round_trips(self) -> None:
        for point_id, modes in (
            ("A004-S", 120),
            ("A049-P", 120),
            ("A001-P", 120),
            ("A001-P", 160),
        ):
            with self.subTest(point_id=point_id, modes=modes):
                args = parse_memory_args(
                    _task036_strong_hybrid_cli(
                        modes=modes,
                        point_id=point_id,
                    )
                )
                self.assertEqual(args.solver_path, "strong-trace-direct")
                command = _worker_command(
                    args, Path("record.json"), Path("stages.jsonl")
                )
                self.assertEqual(
                    command[command.index("--solver-path") + 1],
                    "strong-trace-direct",
                )
                module_index = command.index(
                    "benchmarks.run_task032_phase6_augmented"
                )
                worker = parse_phase6_args(command[module_index + 1 :])
                self.assertEqual(
                    worker.solver_path, "strong-trace-direct"
                )
                self.assertEqual(worker.requested_modes, modes)

        for interfaces in ((30.0, 90.0), (40.0, 80.0)):
            with self.subTest(interfaces=interfaces):
                cli = _task036_strong_hybrid_cli(
                    point_id="A004-S",
                    interfaces=interfaces,
                )
                watchdog = parse_memory_args(cli)
                command = _worker_command(
                    watchdog, Path("record.json"), Path("stages.jsonl")
                )
                module_index = command.index(
                    "benchmarks.run_task032_phase6_augmented"
                )
                worker = parse_phase6_args(command[module_index + 1 :])
                self.assertEqual(
                    (worker.bottom_interface_nm, worker.top_interface_nm),
                    interfaces,
                )

        for point_id, interfaces in (
            ("A049-P", (30.0, 90.0)),
            ("A001-P", (40.0, 80.0)),
            ("A004-S", (20.0, 100.0)),
        ):
            with self.subTest(point_id=point_id, interfaces=interfaces):
                with self.assertRaises(SystemExit):
                    parse_memory_args(
                        _task036_strong_hybrid_cli(
                            point_id=point_id,
                            interfaces=interfaces,
                        )
                    )

        preflight = _task036_strong_hybrid_cli(
            point_id="A004-S",
            interfaces=(30.0, 90.0),
        )
        module_args = _worker_command(
            parse_memory_args(preflight),
            Path("record.json"),
            Path("stages.jsonl"),
        )
        module_index = module_args.index(
            "benchmarks.run_task032_phase6_augmented"
        )
        worker_cli = module_args[module_index + 1 :]
        worker_cli.append("--task036-interface-preflight-only")
        self.assertTrue(
            parse_phase6_args(worker_cli).task036_interface_preflight_only
        )
        with self.assertRaises(SystemExit):
            parse_phase6_args(
                [
                    *worker_cli[: worker_cli.index("--bottom-interface-nm") + 1],
                    "20",
                    *worker_cli[worker_cli.index("--bottom-interface-nm") + 2 :],
                ]
            )

        defaults = parse_phase6_args([])
        self.assertEqual(defaults.solver_path, "augmented")
        for option, value in (
            ("--degree", "6"),
            ("--requested-modes", "240"),
        ):
            cli = _task036_strong_hybrid_cli()
            cli[cli.index(option) + 1] = value
            if option == "--degree":
                cli[cli.index("--modal-degree") + 1] = value
            if option == "--requested-modes":
                cli[cli.index("--candidate-modes") + 1] = "480"
            with self.subTest(option=option):
                with self.assertRaises(SystemExit):
                    parse_memory_args(cli)
        for point_id in ("A004-S", "A049-P"):
            with self.subTest(point_id=point_id, modes=160):
                with self.assertRaises(SystemExit):
                    parse_memory_args(
                        _task036_strong_hybrid_cli(
                            modes=160,
                            point_id=point_id,
                        )
                    )
        off_contract = _task036_strong_hybrid_cli()
        off_contract[
            off_contract.index("--grating-width-x-nm") + 1
        ] = "18"
        with self.assertRaises(SystemExit):
            parse_memory_args(off_contract)

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
            (
                "current_source_sha",
                "f" * 40,
                "reference_source_exact_or_component_disjoint",
            ),
        )
        for key, value, failure in mutations:
            with self.subTest(key=key):
                rejected = task036_full3d_reference_gate(
                    reference, **{**common, key: value}
                )
                self.assertFalse(rejected["pass"])
                self.assertIn(failure, rejected["failures"])

    def test_task036_reference_source_compatibility_is_fail_closed(self) -> None:
        reference = _task036_full3d_reference()
        common = {
            "expected_sha256": RECORD_SHA256,
            "observed_sha256": RECORD_SHA256,
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
        with patch(
            "benchmarks.task035c_p6_h10_gates._git",
            side_effect=AssertionError("exact source must not query Git"),
        ):
            exact = task036_full3d_reference_gate(
                reference,
                current_source_sha=SOURCE_SHA,
                **common,
            )
        self.assertTrue(exact["pass"], exact["failures"])
        self.assertTrue(
            exact["source_compatibility"]["exact_source_sha"]
        )

        current = "f" * 40

        def compatible_git(*arguments: str) -> str | None:
            if arguments[0] == "merge-base":
                return SOURCE_SHA
            if arguments[0] == "diff":
                return "\n".join(
                    (
                        "src/solvers/hybrid_strong_trace_direct.py",
                        "src/test/test_199_task036_strong_trace_hybrid.py",
                        "src/test/test_59_task033_memory_watchdog_contract.py",
                    )
                )
            self.fail(f"Unexpected Git query: {arguments}")

        with patch(
            "benchmarks.task035c_p6_h10_gates._git",
            side_effect=compatible_git,
        ):
            compatible = task036_full3d_reference_gate(
                reference,
                current_source_sha=current,
                **common,
            )
        self.assertTrue(compatible["pass"], compatible["failures"])
        self.assertFalse(
            compatible["source_compatibility"]["exact_source_sha"]
        )

        def full3d_drift_git(*arguments: str) -> str | None:
            if arguments[0] == "merge-base":
                return SOURCE_SHA
            if arguments[0] == "diff":
                return "src/solvers/dtn_port_3d.py"
            return None

        with patch(
            "benchmarks.task035c_p6_h10_gates._git",
            side_effect=full3d_drift_git,
        ):
            rejected = task036_full3d_reference_gate(
                reference,
                current_source_sha=current,
                **common,
            )
        self.assertFalse(rejected["pass"])
        self.assertEqual(
            rejected["source_compatibility"]["disallowed_changed_paths"],
            ["src/solvers/dtn_port_3d.py"],
        )
        self.assertIn(
            "reference_source_exact_or_component_disjoint",
            rejected["failures"],
        )

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

    def test_task036_hybrid_candidate_projection_gate_recomputes_record(self) -> None:
        audit = _hybrid_projection_audit()
        checks = _task036_hybrid_candidate_direct_projection_checks(audit)
        self.assertTrue(all(checks.values()), checks)

        mutations = (
            ("missing_rows", lambda row: row.update(orders=[])),
            (
                "wrong_tolerance",
                lambda row: row.update(tolerance=2.0e-10),
            ),
            (
                "reported_failure",
                lambda row: row.update(**{"pass": False}),
            ),
            (
                "nonfinite_difference",
                lambda row: row["orders"][0].update(
                    absolute_outgoing_projection_difference=float("inf")
                ),
            ),
            (
                "duplicate_identity",
                lambda row: row["orders"].__setitem__(
                    1, dict(row["orders"][0])
                ),
            ),
            (
                "truncated_count",
                lambda row: row.update(audited_mode_count=3),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = _hybrid_projection_audit()
                mutate(candidate)
                rejected = (
                    _task036_hybrid_candidate_direct_projection_checks(
                        candidate
                    )
                )
                self.assertFalse(all(rejected.values()), rejected)

    def test_hybrid_recovered_projection_audit_is_opt_in_and_fail_closed(
        self,
    ) -> None:
        disabled = SimpleNamespace(
            dtn_auxiliary_direct_projection_audit=False
        )
        audit = evaluate_hybrid_recovered_direct_projection_audit(
            disabled,
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
        )
        self.assertFalse(audit["requested"])
        self.assertEqual(audit["status"], "not_requested")

        enabled = SimpleNamespace(
            dtn_auxiliary_direct_projection_audit=True,
            dtn_auxiliary_direct_projection_tolerance=1.0e-10,
        )
        with self.assertRaisesRegex(
            ValueError,
            "requires static-condensation recovered",
        ):
            evaluate_hybrid_recovered_direct_projection_audit(
                enabled,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(
                    bottom_recovered=None,
                    top_recovered=None,
                ),
            )

    def test_hybrid_recovered_projection_audit_merges_both_ports(self) -> None:
        cfg = SimpleNamespace(
            dtn_auxiliary_direct_projection_audit=True,
            dtn_auxiliary_direct_projection_tolerance=1.0e-10,
        )

        def system(side: str) -> SimpleNamespace:
            return SimpleNamespace(
                n_fe=3,
                n_external_aux=2,
                external_modes=[
                    SimpleNamespace(side=side),
                    SimpleNamespace(side=side),
                ],
                incident_projections=[0.0j, 0.0j],
                local_mesh=SimpleNamespace(
                    mesh=SimpleNamespace(comm=SimpleNamespace()),
                    mesh_data=SimpleNamespace(),
                ),
                dtn_quadrature_degree=12,
            )

        bottom = system("bottom")
        top = system("top")
        solution = SimpleNamespace(
            bottom_recovered=SimpleNamespace(),
            top_recovered=SimpleNamespace(),
            bottom_physical=SimpleNamespace(),
            top_physical=SimpleNamespace(),
            bottom=SimpleNamespace(),
            top=SimpleNamespace(),
        )

        def side_audit(_field, modes, *_args, **_kwargs) -> dict:
            side = modes[0].side
            rows = [
                {
                    "side": side,
                    "m": index,
                    "n": 0,
                    "polarization": polarization,
                    "absolute_total_projection_difference": 1.0e-12,
                    "absolute_outgoing_projection_difference": 1.0e-12,
                }
                for index, polarization in enumerate(("s", "p"))
            ]
            return {"pass": True, "orders": rows}

        module = "src.solvers.hybrid_fem_modal_augmented_direct"
        with (
            patch(
                f"{module}._gather_auxiliary_values",
                return_value=[0.0j, 0.0j],
            ),
            patch(
                f"{module}._auxiliary_direct_tangential_projection_audit",
                side_effect=side_audit,
            ),
        ):
            audit = evaluate_hybrid_recovered_direct_projection_audit(
                cfg,
                bottom,
                top,
                solution,
            )
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["expected_mode_count"], 4)
        self.assertEqual(audit["audited_mode_count"], 4)
        self.assertEqual(audit["side_mode_count"], {"bottom": 2, "top": 2})
        self.assertEqual(
            {row["side"] for row in audit["orders"]},
            {"bottom", "top"},
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
