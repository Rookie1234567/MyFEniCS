from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.run_task033_formal_records import main as formal_records_main
from benchmarks.task033_evidence_checker import REQUIRED_FORMAL_ROLES, ROLE_SPECS
from benchmarks.task033_formal_records import (
    FormalRecordError,
    build_adaptive_evidence,
    build_formal_manifest,
    build_interface_buffer_tradeoff,
    build_qep_order_study,
    build_uniform_p_h_matrix,
)
from benchmarks.task033_qep_qualification import TREND_DEGREES, TREND_H_NM
from benchmarks.task033_watchdog_launch import (
    DEFAULT_RESOURCE_MATRIX,
    hybrid_launch_gate,
)
from src.geometry.task033_periodic_graded_mesh import (
    build_adaptive_planning_record,
    build_physics_informed_graded_plan,
)


SOURCE_SHA = "a" * 40
BUFFER_INTERFACES = {
    10.0: (10.0, 110.0),
    7.5: (7.5, 112.5),
    5.0: (5.0, 115.0),
    2.5: (2.5, 117.5),
}


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(sha: str = SOURCE_SHA) -> dict:
    return {
        "commit_sha": sha,
        "head_before_sha": sha,
        "head_after_sha": sha,
        "verified_clean_sha": sha,
        "tracked_status_before": "",
        "tracked_status_after": "",
        "source_stable_during_run": True,
        "source_clean_verified": True,
    }


def _resource_authority() -> dict:
    return {
        "simultaneous_live_worker_rss_sum_bytes": 2 * 1024**3,
        "container_cgroup_current_bytes": 3 * 1024**3,
        "memory_authority_bytes": 3 * 1024**3,
        "container_memory_limit_bytes": 14 * 1024**3,
        "host_available_memory_bytes": 20 * 1024**3,
        "container_swap_current_bytes": 0,
        "pswpin_delta_pages": 0,
        "pswpout_delta_pages": 0,
    }


def _anchor_requalification(requested_mode: int = 160) -> dict:
    matrix = json.loads(DEFAULT_RESOURCE_MATRIX.read_text(encoding="utf-8"))
    gate = hybrid_launch_gate(
        matrix,
        degree=2,
        h_nm=3.0,
        requested_modes=requested_mode,
        candidate_modes=160,
        solver_path="modal-schur-memory-minimal",
        compare_modal_schur=False,
        bottom_interface_nm=10.0,
        top_interface_nm=110.0,
        graded_reference_h=None,
        container_limit_bytes=14 * 1024**3,
        host_available_memory_bytes=16 * 1024**3,
        warning_gib=11.5,
        terminate_gib=13.0,
        core_evidence=None,
        expected_core_sha256=None,
        current_source_sha=SOURCE_SHA,
        task033_same_sha_anchor_requalification=True,
        source_clean_verified=True,
        resource_matrix_is_canonical=True,
        resource_matrix_is_tracked=True,
        external_watchdog_active=True,
    )
    if gate.get("pass") is not True:
        raise AssertionError(f"real launch fixture did not qualify: {gate['failures']}")
    return gate["task033_anchor_requalification"]


def _tracking_compact(h_nm: float) -> dict:
    modes = []
    for index, beta in enumerate((1.0 + h_nm * 1.0e-3, 2.0 + h_nm * 1.0e-3)):
        vector = [[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        if index == 1:
            vector = [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]
        modes.append(
            {
                "mode_index": index,
                "beta_per_nm": [beta, 0.0],
                "direction": "forward",
                "kind": "propagating",
                "right_fourier_fingerprint": vector,
                "left_fourier_fingerprint": vector,
            }
        )
    return {
        "evidence_kind": "measured_per_shard_input_for_cross_h_tracking",
        "status": "compact_input_ready_for_aggregate",
        "aggregate_recomputation_required": True,
        "compact_evidence": {
            "evidence_kind": "measured_common_fourier_left_right_mode_fingerprints",
            "status": "compact_input_ready_for_cross_h_aggregate",
            "assignment_performed_in_shard": False,
            "cross_h_vector_dot_performed": False,
            "full_eigenvector_gathered": False,
            "probe_orders": [[0, 0]],
            "components_per_order": ["Ex", "Ey", "Ez"],
            "fingerprint_length": 3,
            "mode_count": 2,
            "modes": modes,
        },
    }


def _qep_shard(
    material: str, degree: int, h_nm: float, *, sha: str = SOURCE_SHA
) -> dict:
    analytic_error = (
        None
        if material == "stage4_xy"
        else 1.0e-3 * (h_nm / 5.0) ** 2 / degree**2
    )
    tracking = _tracking_compact(h_nm) if material == "stage4_xy" else None
    return {
        "schema_version": "task033.case091.qep-measurement.v2",
        "record_type": "task033_qep_measurement_shard",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "measured_shard_pass",
        "identity": {
            "is_pde_run": True,
            "is_solver_pass": True,
            "is_memory_measurement": True,
            "is_physical_qualification_record": False,
            "physical_qualified": False,
        },
        "candidate": {
            "material_kind": material,
            "degree": degree,
            "h_nm": h_nm,
            "mpi_size": 1,
        },
        "memory_prediction": {},
        "runtime_preflight": {},
        "provenance": _source(sha),
        "numerical_results": {
            "analytic_beta_relative_error": analytic_error,
            "left_right_classification": {
                "right_polynomial_relative_residual_max": 1.0e-12,
                "left_polynomial_relative_residual_max": 1.0e-10,
                "biorthogonality_identity_error": 1.0e-8,
            },
            "quadrature": {
                "raised_comparison": {
                    "max_matrix_relative_difference": 1.0e-13,
                    "pass": True,
                }
            },
            "cross_h_tracking": tracking,
        },
        "resource_measurements": {
            "formal_resource_authority": _resource_authority()
        },
        "gates": {"all_required_numerical_gates_pass": True},
    }


def _qep_watchdog(shard: dict, *, sha: str = SOURCE_SHA) -> dict:
    return {
        "schema_version": "task033.memory-watchdog.v2",
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "target": "qep",
        "return_code": 0,
        "formal_pass": True,
        "memory_authority_pass": True,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "source": _source(sha),
        "resource_authority": {"gate": {"pass": True}},
        "measurements": shard,
    }


def _funnel(
    degree: int,
    h_nm: float,
    *,
    bottom: float = 10.0,
    top: float = 110.0,
    source_records: list[dict] | None = None,
    graded_reference_h: float | None = None,
    graded_plan_hash: str | None = None,
    sha: str = SOURCE_SHA,
) -> dict:
    return {
        "schema_version": "task033.case091.hybrid-funnel.v1",
        "record_type": "task033_hybrid_mode_truncation_funnel",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "qualified",
        "identity": {
            "is_pde_run": True,
            "is_solver_pass": True,
            "is_mode_convergence_measurement": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
            "source_commit_full_sha": sha,
            "tracked_source_clean": True,
        },
        "case": {
            "degree": degree,
            "h_nm": h_nm,
            "wavelength_nm": 13.5,
            "incident_grazing_deg": 10.0,
            "polarization_kind": "s",
            "bottom_interface_nm": bottom,
            "top_interface_nm": top,
            "graded_reference_h_nm": graded_reference_h,
            "graded_plan_hash": graded_plan_hash,
            "primary_solver_path": "modal-schur-memory-minimal",
            "mode_counts": [80, 120, 160],
        },
        "tolerances": {},
        "source_records": source_records or [],
        "individual_gates": {},
        "comparisons": [],
        "qualification": {
            "mode_count_converged": True,
            "selected_mode_count_per_direction": 160,
            "selected_pair_strong": True,
            "all_sources_same_clean_sha": True,
            "all_external_watchdogs_pass": True,
        },
        "failures": [],
        "limitations": [],
    }


def _matrix_key(degree: int, h_nm: float) -> str:
    h_label = str(h_nm).replace(".", "p").removesuffix("p0")
    return f"p{degree}_h{h_label}"


def _resource_matrix() -> tuple[dict, set[str]]:
    memory_gated = {
        "p2_h2",
        "p2_h1p5",
        "p3_h3",
        "p3_h2p5",
        "p3_h2",
        "p3_h1p5",
        "p4_h5",
        "p4_h3",
        "p4_h2p5",
        "p4_h2",
        "p4_h1p5",
    }
    rows = []
    for degree in (1, 2, 3, 4):
        for h_nm in (5.0, 3.0, 2.5, 2.0, 1.5):
            key = _matrix_key(degree, h_nm)
            if key in memory_gated:
                planning = launch = "not_run_by_memory_gate"
            elif key == "p2_h3":
                planning = launch = "reuse_task032_clean_anchor"
            else:
                planning = "planning_eligible_by_resource_prediction"
                launch = "formal_measured_evidence_supplied"
            row = {
                "matrix_key": key,
                "degree": degree,
                "h_nm": h_nm,
                "planning_decision": planning,
                "launch_decision": launch,
            }
            if key == "p2_h3":
                row["measured_anchor"] = {
                    "data_identity": "measured",
                    "degree": 2,
                    "h_nm": 3.0,
                    "modes_per_direction": 160,
                }
            rows.append(row)
    return (
        {
            "schema_version": 2,
            "record_type": "task033_resource_prediction_and_launch_decision",
            "status": "planning_complete_runtime_launch_fail_closed",
            "identity": {"is_pde_run": False, "is_solver_pass": False},
            "entries": rows,
        },
        memory_gated,
    )


def _anchor(sha: str = SOURCE_SHA) -> dict:
    return {
        "schema_version": 1,
        "benchmark_id": "task032_external_simultaneous_memory_forensics",
        "h_nm": 3.0,
        "requested_modes_per_direction": 160,
        "return_code": 0,
        "numeric_pass": True,
        "no_swap": True,
        "source": {
            "commit_sha": sha,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "verified_clean_sha": sha,
        },
    }


def _watchdog_summary(
    *,
    bottom: float,
    top: float,
    local_dofs: int,
    interface_dofs: int,
    total_seconds: float,
    memory_bytes: int,
    degree: int = 2,
    h_nm: float = 3.0,
    graded_reference_h: float | None = None,
    graded_plan_hash: str | None = None,
    local_rta_offset: float = 0.0,
    amplitude_offset: float = 0.0,
    full_field_available: bool = False,
    interface_e_error: float = 1.0e-3,
    interface_h_error: float = 2.0e-3,
    selected_plane_error: float = 1.0e-3,
    sha: str = SOURCE_SHA,
) -> dict:
    h_tag = str(float(h_nm)).replace(".", "p")
    reference_npz_sha = "1" * 64
    reference_record_sha = "2" * 64
    sample_shape = [5, 2, 2, 3]
    z_planes = [bottom, 30.0, 60.0, 90.0, top]
    selected_plane_comparison = {
        "reference_npz": f"/work/reference/h{h_tag}/samples.npz",
        "reference_npz_sha256_expected": reference_npz_sha,
        "reference_npz_sha256_observed": reference_npz_sha,
        "reference_record": f"benchmarks/reference_h{h_tag}.json",
        "reference_record_sha256": reference_record_sha,
        "reference_record_source_commit_full_sha": SOURCE_SHA,
        "reference_binding_verified": True,
        "sample_shape_z_y_x_component": sample_shape,
        "planes": [
            {
                "z_nm": z_nm,
                "electric": {"relative_l2": selected_plane_error},
                "magnetic": {"relative_l2": selected_plane_error},
            }
            for z_nm in z_planes
        ],
        "max_middle_plane_electric_relative_l2": selected_plane_error,
        "max_middle_plane_magnetic_relative_l2": selected_plane_error,
    }
    return {
        "schema_version": "task033.memory-watchdog.v2",
        "benchmark_id": "task033_external_memory_watchdog",
        "status": "measured_shard_pass",
        "target": "hybrid",
        "return_code": 0,
        "formal_pass": True,
        "memory_authority_pass": True,
        "physical_qualified": False,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "source": _source(sha),
        "resource_authority": {
            "memory_authority_bytes": memory_bytes,
            "gate": {"pass": True},
        },
        "measurements": {
            "case": {
                "degree": degree,
                "h_nm": h_nm,
                "wavelength_nm": 13.5,
                "incident_grazing_deg": 10.0,
                "polarization_kind": "s",
                "bottom_interface_nm": bottom,
                "top_interface_nm": top,
                "requested_modes_per_direction": 160,
                "graded_reference_h_nm": graded_reference_h,
                "graded_plan_hash": graded_plan_hash,
            },
            "hybrid_system": {
                "bottom_local_fe_dofs": local_dofs // 2,
                "top_local_fe_dofs": local_dofs - local_dofs // 2,
                "internal_unknown_count": 320,
            },
            "object_payload_ledger": {
                "interface_active_dofs": {
                    "bottom": interface_dofs // 2,
                    "top": interface_dofs - interface_dofs // 2,
                }
            },
            "qualification": {
                "integration_pass": True,
                "algebraic_chain_pass": True,
                "physical_field_gates_pass": True,
                "task033_physical_truncation_allowed": True,
            },
            "solve": {"true_relative_residual": 1.0e-12},
            "validation": {
                "port_power": {
                    "R_total": 0.1 + local_rta_offset,
                    "T_total": 0.5 - local_rta_offset,
                    "A_balance": 0.4,
                },
                "external_diffraction_orders": [
                    {
                        "side": "top",
                        "m": 0,
                        "n": 0,
                        "polarization": "s",
                        "propagating": True,
                        "power_ratio": 0.5,
                        "outgoing_amplitude_at_boundary": [
                            1.0 + amplitude_offset,
                            0.2,
                        ],
                    }
                ],
            },
            "physical_field_reconstruction": {
                "full_middle_volume_reconstructed": full_field_available,
                "sample_grid_shape_z_y_x_component": sample_shape,
                "selected_plane_full3d_comparison": selected_plane_comparison,
                "interface_continuity": {
                    side: {
                        "electric_tangential": {"relative_l2": interface_e_error},
                        "magnetic_tangential": {"relative_l2": interface_h_error},
                    }
                    for side in ("bottom", "top")
                },
            },
            "timing_seconds_max_rank": {
                "cross_section_and_qep_assembly": 4.0,
                "positive_and_negative_biorthogonal_bases": 6.0,
                "two_local_fem_dtn_systems": total_seconds * 0.5,
                "internal_modal_coupling": total_seconds * 0.1,
                "primary_system_build": total_seconds * 0.1,
                "total": total_seconds,
            },
        },
    }


def _set_pointer(payload: dict, pointer: str, value: object) -> None:
    current = payload
    tokens = pointer.removeprefix("/").split("/")
    for token in tokens[:-1]:
        current = current.setdefault(token, {})
    current[tokens[-1]] = value


class Task033FormalRecordTests(unittest.TestCase):
    def test_qep_order_study_uses_native_aggregate_and_same_clean_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for material in ("air", "lossy_homogeneous", "stage4_xy"):
                for degree in TREND_DEGREES:
                    for h_nm in TREND_H_NM:
                        path = root / f"{material}_p{degree}_h{h_nm}.json"
                        paths.append(
                            _write(
                                path,
                                _qep_watchdog(
                                    _qep_shard(material, degree, h_nm)
                                ),
                            )
                        )
            result = build_qep_order_study(paths)
            self.assertEqual(result["status"], "qep_component_aggregate_qualified")
            self.assertEqual(result["required_shard_count"], 36)
            self.assertEqual(result["formal_source"]["commit_sha"], SOURCE_SHA)

            changed = json.loads(paths[-1].read_text(encoding="utf-8"))
            changed["source"] = _source("b" * 40)
            changed["measurements"]["provenance"] = _source("b" * 40)
            _write(paths[-1], changed)
            with self.assertRaisesRegex(FormalRecordError, "mixes clean-source SHAs"):
                build_qep_order_study(paths)

    def test_uniform_matrix_requires_every_non_memory_gated_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix, memory_gated = _resource_matrix()
            matrix_path = _write(root / "resource_matrix.json", matrix)
            watchdogs = {}
            p2_h3_watchdog = None
            for row in matrix["entries"]:
                key = row["matrix_key"]
                if key in memory_gated:
                    continue
                path = root / f"{key}_watchdog.json"
                watchdog = _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=2000,
                    interface_dofs=400,
                    total_seconds=20.0,
                    memory_bytes=2_000_000_000,
                    degree=row["degree"],
                    h_nm=row["h_nm"],
                )
                if key == "p2_h3":
                    watchdog["task033_anchor_requalification"] = (
                        _anchor_requalification()
                    )
                    p2_h3_watchdog = json.loads(json.dumps(watchdog))
                watchdogs[key] = _write(
                    path,
                    watchdog,
                )
            result = build_uniform_p_h_matrix(
                matrix_path,
                funnel_paths={},
                anchor_paths={},
                watchdog_paths=watchdogs,
            )
            self.assertEqual(result["status"], "formal_matrix_complete")
            self.assertEqual(len(result["entries"]), 20)
            self.assertEqual(result["summary"]["not_run_by_memory_gate_entries"], 11)
            self.assertEqual(result["summary"]["measured_watchdog_entries"], 9)
            self.assertIsNotNone(p2_h3_watchdog)
            invalid_contract_values = (
                ("/task033_anchor_requalification/allowed", False),
                ("/task033_anchor_requalification/reason", "wrong reason"),
                (
                    "/task033_anchor_requalification/source_commit_full_sha",
                    "b" * 40,
                ),
                ("/task033_anchor_requalification/current_requested_mode", 240),
                (
                    "/task033_anchor_requalification/required_complete_mode_funnel",
                    [80, 160],
                ),
                (
                    "/task033_anchor_requalification/"
                    "requires_same_case_and_source_sha_across_funnel",
                    False,
                ),
                (
                    "/task033_anchor_requalification/checks/"
                    "common_candidate_basis_is_m160",
                    False,
                ),
                (
                    "/task033_anchor_requalification/checks/"
                    "complete_nonignored_worktree_clean",
                    False,
                ),
                (
                    "/task033_anchor_requalification/checks/"
                    "canonical_resource_matrix",
                    False,
                ),
                (
                    "/task033_anchor_requalification/checks/"
                    "canonical_resource_matrix_tracked",
                    False,
                ),
                (
                    "/task033_anchor_requalification/checks/"
                    "external_watchdog_is_launch_authority",
                    False,
                ),
            )
            for pointer, value in invalid_contract_values:
                with self.subTest(invalid_requalification=pointer):
                    broken = json.loads(json.dumps(p2_h3_watchdog))
                    _set_pointer(broken, pointer, value)
                    _write(watchdogs["p2_h3"], broken)
                    with self.assertRaisesRegex(
                        FormalRecordError,
                        "Task033 anchor requalification contract is incomplete",
                    ):
                        build_uniform_p_h_matrix(
                            matrix_path,
                            funnel_paths={},
                            anchor_paths={},
                            watchdog_paths=watchdogs,
                        )
            _write(watchdogs["p2_h3"], p2_h3_watchdog)
            missing = dict(watchdogs)
            missing.pop(next(iter(missing)))
            with self.assertRaisesRegex(FormalRecordError, "lacks a measured"):
                build_uniform_p_h_matrix(
                    matrix_path,
                    funnel_paths={},
                    anchor_paths={},
                    watchdog_paths=missing,
                )

    def test_adaptive_record_recomputes_gate_and_rejects_mixed_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = build_physics_informed_graded_plan(reference_h_nm=5.0)
            plan_path = _write(
                root / "plan.json", build_adaptive_planning_record(plan)
            )
            reference_watchdog = _write(
                root / "reference_m160.json",
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=2000,
                    interface_dofs=400,
                    total_seconds=30.0,
                    memory_bytes=2_000_000_000,
                    h_nm=5.0,
                ),
            )
            candidate_watchdog = _write(
                root / "candidate_m160.json",
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=1000,
                    interface_dofs=400,
                    total_seconds=25.0,
                    memory_bytes=1_800_000_000,
                    h_nm=5.0,
                    graded_reference_h=5.0,
                    graded_plan_hash=plan.plan_hash,
                    local_rta_offset=1.0e-7,
                    amplitude_offset=1.0e-5,
                ),
            )
            reference_path = _write(
                root / "reference_funnel.json",
                _funnel(
                    2,
                    5.0,
                    source_records=[
                        {
                            "path": str(reference_watchdog),
                            "sha256": _sha256(reference_watchdog),
                            "mode_count_per_direction": 160,
                        }
                    ],
                ),
            )
            candidate_path = _write(
                root / "candidate_funnel.json",
                _funnel(
                    2,
                    5.0,
                    source_records=[
                        {
                            "path": str(candidate_watchdog),
                            "sha256": _sha256(candidate_watchdog),
                            "mode_count_per_direction": 160,
                        }
                    ],
                    graded_reference_h=5.0,
                    graded_plan_hash=plan.plan_hash,
                ),
            )
            result = build_adaptive_evidence(
                plan_path, reference_path, candidate_path
            )
            self.assertEqual(
                result["status"], "measured_same_accuracy_qualification_attached"
            )
            self.assertEqual(result["same_accuracy_qualification"]["compression"], 2.0)
            self.assertEqual(
                result["measured_evidence"]["reference"]["field_evidence_kind"],
                "sampled_interface_EH_and_pinned_full3d_selected_planes",
            )
            self.assertFalse(
                result["measured_evidence"]["reference"][
                    "selected_plane_reference"
                ]["full_middle_volume_reconstructed"]
            )
            self.assertEqual(
                result["measured_evidence"]["reference"][
                    "selected_plane_reference"
                ]["binding"]["reference_npz_sha256_expected"],
                "1" * 64,
            )

            missing_binding = json.loads(
                reference_watchdog.read_text(encoding="utf-8")
            )
            missing_binding["measurements"]["physical_field_reconstruction"][
                "selected_plane_full3d_comparison"
            ] = None
            _write(reference_watchdog, missing_binding)
            changed_reference_funnel = json.loads(
                reference_path.read_text(encoding="utf-8")
            )
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)
            with self.assertRaisesRegex(
                FormalRecordError, "lacks pinned selected-plane field evidence"
            ):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

            _write(
                reference_watchdog,
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=2000,
                    interface_dofs=400,
                    total_seconds=30.0,
                    memory_bytes=2_000_000_000,
                    h_nm=5.0,
                ),
            )
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)

            bad_reference_interface = _watchdog_summary(
                bottom=10.0,
                top=110.0,
                local_dofs=2000,
                interface_dofs=400,
                total_seconds=30.0,
                memory_bytes=2_000_000_000,
                h_nm=5.0,
                interface_e_error=6.0e-3,
            )
            _write(reference_watchdog, bad_reference_interface)
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)
            with self.assertRaisesRegex(
                FormalRecordError, "native same-accuracy gate did not qualify"
            ):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

            _write(
                reference_watchdog,
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=2000,
                    interface_dofs=400,
                    total_seconds=30.0,
                    memory_bytes=2_000_000_000,
                    h_nm=5.0,
                ),
            )
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)

            missing_reference_field = json.loads(
                reference_watchdog.read_text(encoding="utf-8")
            )
            del missing_reference_field["measurements"][
                "physical_field_reconstruction"
            ]["interface_continuity"]
            _write(reference_watchdog, missing_reference_field)
            changed_reference_funnel = json.loads(
                reference_path.read_text(encoding="utf-8")
            )
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)
            with self.assertRaisesRegex(
                FormalRecordError, "adaptive reference lacks interface E/H evidence"
            ):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

            _write(
                reference_watchdog,
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=2000,
                    interface_dofs=400,
                    total_seconds=30.0,
                    memory_bytes=2_000_000_000,
                    h_nm=5.0,
                ),
            )
            changed_reference_funnel["source_records"][0]["sha256"] = _sha256(
                reference_watchdog
            )
            _write(reference_path, changed_reference_funnel)

            bad_candidate_binding = json.loads(
                candidate_watchdog.read_text(encoding="utf-8")
            )
            bad_candidate_binding["measurements"][
                "physical_field_reconstruction"
            ]["selected_plane_full3d_comparison"][
                "reference_npz_sha256_observed"
            ] = "3" * 64
            _write(candidate_watchdog, bad_candidate_binding)
            changed_candidate_funnel = json.loads(
                candidate_path.read_text(encoding="utf-8")
            )
            changed_candidate_funnel["source_records"][0]["sha256"] = _sha256(
                candidate_watchdog
            )
            _write(candidate_path, changed_candidate_funnel)
            with self.assertRaisesRegex(
                FormalRecordError, "selected-plane NPZ SHA256 differs"
            ):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

            _write(
                candidate_watchdog,
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=1000,
                    interface_dofs=400,
                    total_seconds=25.0,
                    memory_bytes=1_800_000_000,
                    h_nm=5.0,
                    graded_reference_h=5.0,
                    graded_plan_hash=plan.plan_hash,
                    local_rta_offset=1.0e-7,
                    amplitude_offset=1.0e-5,
                    selected_plane_error=6.0e-3,
                ),
            )
            changed_candidate_funnel["source_records"][0]["sha256"] = _sha256(
                candidate_watchdog
            )
            _write(candidate_path, changed_candidate_funnel)
            with self.assertRaisesRegex(
                FormalRecordError, "selected middle-plane field Gate failed"
            ):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

            _write(
                candidate_watchdog,
                _watchdog_summary(
                    bottom=10.0,
                    top=110.0,
                    local_dofs=1000,
                    interface_dofs=400,
                    total_seconds=25.0,
                    memory_bytes=1_800_000_000,
                    h_nm=5.0,
                    graded_reference_h=5.0,
                    graded_plan_hash=plan.plan_hash,
                    local_rta_offset=1.0e-7,
                    amplitude_offset=1.0e-5,
                ),
            )
            changed_candidate_funnel["source_records"][0]["sha256"] = _sha256(
                candidate_watchdog
            )
            _write(candidate_path, changed_candidate_funnel)

            changed_watchdog = json.loads(
                candidate_watchdog.read_text(encoding="utf-8")
            )
            changed_watchdog["source"] = _source("b" * 40)
            _write(candidate_watchdog, changed_watchdog)
            changed_funnel = json.loads(candidate_path.read_text(encoding="utf-8"))
            changed_funnel["identity"]["source_commit_full_sha"] = "b" * 40
            changed_funnel["source_records"][0]["sha256"] = _sha256(
                candidate_watchdog
            )
            _write(candidate_path, changed_funnel)
            with self.assertRaisesRegex(FormalRecordError, "mixes clean-source SHAs"):
                build_adaptive_evidence(plan_path, reference_path, candidate_path)

    def test_buffer_tradeoff_reads_selected_watchdogs_and_never_guesses_cost(self) -> None:
        costs = {
            10.0: (4000, 500, 100.0, 4_000_000_000),
            7.5: (3000, 600, 90.0, 3_500_000_000),
            5.0: (2500, 800, 85.0, 3_300_000_000),
            2.5: (2000, 1200, 95.0, 3_800_000_000),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            funnel_paths = []
            summary_paths = {}
            for buffer_nm, (bottom, top) in BUFFER_INTERFACES.items():
                local, interface, seconds, memory = costs[buffer_nm]
                summary = _write(
                    root / f"buffer_{buffer_nm}_m160.json",
                    _watchdog_summary(
                        bottom=bottom,
                        top=top,
                        local_dofs=local,
                        interface_dofs=interface,
                        total_seconds=seconds,
                        memory_bytes=memory,
                    ),
                )
                summary_paths[buffer_nm] = summary
                descriptor = {
                    "path": str(summary),
                    "sha256": _sha256(summary),
                    "mode_count_per_direction": 160,
                }
                funnel_paths.append(
                    _write(
                        root / f"buffer_{buffer_nm}_funnel.json",
                        _funnel(
                            2,
                            3.0,
                            bottom=bottom,
                            top=top,
                            source_records=[descriptor],
                        ),
                    )
                )
            result = build_interface_buffer_tradeoff(funnel_paths)
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(result["selected_buffer_nm"], 7.5)
            self.assertEqual(len(result["candidates"]), 4)

            broken = json.loads(
                summary_paths[10.0].read_text(encoding="utf-8")
            )
            del broken["measurements"]["hybrid_system"]["bottom_local_fe_dofs"]
            _write(summary_paths[10.0], broken)
            funnel = json.loads(funnel_paths[0].read_text(encoding="utf-8"))
            funnel["source_records"][0]["sha256"] = _sha256(summary_paths[10.0])
            _write(funnel_paths[0], funnel)
            with self.assertRaisesRegex(FormalRecordError, "bottom_local_fe_dofs"):
                build_interface_buffer_tradeoff(funnel_paths)

    def test_manifest_binds_all_roles_hashes_statuses_and_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = {
                "formal_source": {
                    "commit_sha": SOURCE_SHA,
                    "tracked_source_clean": True,
                }
            }
            _set_pointer(
                shared,
                ROLE_SPECS["case090_clean_core"].status_pointer,
                ROLE_SPECS["case090_clean_core"].accepted_statuses[0],
            )
            _set_pointer(
                shared,
                ROLE_SPECS["case090_mpi_memory"].status_pointer,
                ROLE_SPECS["case090_mpi_memory"].accepted_statuses[0],
            )
            shared_path = _write(root / "case090.json", shared)
            role_paths = {
                "case090_clean_core": shared_path,
                "case090_mpi_memory": shared_path,
            }
            for role in REQUIRED_FORMAL_ROLES[2:]:
                payload = {
                    "formal_source": {
                        "commit_sha": SOURCE_SHA,
                        "tracked_source_clean": True,
                    }
                }
                _set_pointer(
                    payload,
                    ROLE_SPECS[role].status_pointer,
                    ROLE_SPECS[role].accepted_statuses[0],
                )
                role_paths[role] = _write(root / f"{role}.json", payload)
            with (
                patch(
                    "benchmarks.task033_formal_records._validate_payload"
                ),
                patch(
                    "benchmarks.task033_formal_records.checker_semantic_problems",
                    return_value=[],
                ),
            ):
                result = build_formal_manifest(role_paths, repo_root=root)
                self.assertEqual(result["status"], "submitted_for_verification")
                self.assertEqual(len(result["entries"]), 16)
                self.assertEqual(result["clean_source_sha"], SOURCE_SHA)
                self.assertEqual(
                    result["entries"][0]["path"], result["entries"][1]["path"]
                )

                changed_role = REQUIRED_FORMAL_ROLES[-1]
                changed = json.loads(
                    Path(role_paths[changed_role]).read_text(encoding="utf-8")
                )
                changed["formal_source"]["commit_sha"] = "b" * 40
                _write(Path(role_paths[changed_role]), changed)
                with self.assertRaisesRegex(FormalRecordError, "mixes clean-source SHAs"):
                    build_formal_manifest(role_paths, repo_root=root)

    def test_cli_reports_blocker_and_returns_two(self) -> None:
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = formal_records_main(
                ["qep-order-study", "definitely_missing_task033_record.json"]
            )
        self.assertEqual(code, 2)
        report = json.loads(stream.getvalue())
        self.assertEqual(report["status"], "blocked_fail_closed")
        self.assertTrue(report["problems"])


if __name__ == "__main__":
    unittest.main()
