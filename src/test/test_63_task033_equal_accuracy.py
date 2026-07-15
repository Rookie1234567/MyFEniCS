from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from benchmarks.task033_equal_accuracy import (
    build_equal_accuracy,
    classify_compression,
)
from benchmarks.task033_hybrid_funnel import build_hybrid_funnel_from_paths


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "equal_accuracy_schema.json"
)
SHA = "a" * 40


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(sha: str) -> dict:
    return {
        "commit_sha": sha,
        "head_before_sha": sha,
        "head_after_sha": sha,
        "verified_clean_sha": sha,
        "tracked_status_before": "",
        "tracked_status_after": "",
        "worktree_status_before": "",
        "worktree_status_after": "",
        "nonignored_untracked_before": [],
        "nonignored_untracked_after": [],
        "cleanliness_semantics": (
            "git status including all nonignored untracked paths; ignored artifacts excluded"
        ),
        "source_stable_during_run": True,
        "source_clean_verified": True,
    }


def _watchdog(
    mode: int,
    *,
    degree: int,
    h_nm: float,
    local_dofs: int,
    assembled_nnz: int,
    rss_bytes: int,
    total_seconds: float,
    sha: str,
    observable_offset: float,
    plane_error: float = 1.0e-3,
) -> dict:
    bottom = local_dofs // 2
    top = local_dofs - bottom
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
        "terminated_for_authority_unreadable": False,
        "source": _source(sha),
        "resource_authority": {
            "memory_authority_bytes": rss_bytes,
            "gate": {"pass": True},
        },
        "launch_gate": {"pass": True},
        "measurements": {
            "case": {
                "degree": degree,
                "h_nm": h_nm,
                "wavelength_nm": 13.5,
                "incident_grazing_deg": 10.0,
                "polarization_kind": "s",
                "bottom_interface_nm": 10.0,
                "top_interface_nm": 110.0,
                "graded_reference_h_nm": None,
                "graded_plan_hash": None,
                "requested_modes_per_direction": mode,
            },
            "hybrid_system": {
                "primary_solver_path": "modal-schur-memory-minimal",
                "bottom_local_fe_dofs": bottom,
                "top_local_fe_dofs": top,
                "bottom_global_size": bottom + 40,
                "top_global_size": top + 40,
                "internal_unknown_count": 2 * mode,
                "assembled_nnz": assembled_nnz,
            },
            "solve": {"true_relative_residual": 1.0e-12},
            "validation": {
                "port_power": {
                    "R_total": 0.1 + observable_offset,
                    "T_total": 0.6 - observable_offset,
                    "A_balance": 0.3,
                },
                "external_diffraction_orders": [
                    {
                        "side": "top",
                        "m": 0,
                        "n": 0,
                        "polarization": "s",
                        "propagating": True,
                        "power_ratio": 0.6,
                        "outgoing_amplitude_at_boundary": [
                            0.7 + observable_offset,
                            -0.1,
                        ],
                    }
                ],
            },
            "physical_field_reconstruction": {
                "interface_continuity": {
                    side: {
                        "electric_tangential": {"relative_l2": 1.0e-3},
                        "magnetic_tangential": {"relative_l2": 2.0e-3},
                    }
                    for side in ("bottom", "top")
                },
                "selected_plane_full3d_comparison": {
                    "reference_npz": "same_full3d_reference.npz",
                    "sample_shape_z_y_x_component": [2, 4, 8, 3],
                    "planes": [
                        {
                            "z_nm": z_nm,
                            "electric": {"relative_l2": plane_error},
                            "magnetic": {"relative_l2": plane_error * 0.8},
                        }
                        for z_nm in (30.0, 90.0)
                    ],
                },
            },
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
            "timing_seconds_max_rank": {"total": total_seconds},
        },
    }


def _funnel(
    root: Path,
    name: str,
    *,
    degree: int,
    h_nm: float,
    local_dofs: int,
    assembled_nnz: int,
    rss_bytes: int,
    total_seconds: float,
    sha: str = SHA,
    candidate_offset: float = 0.0,
    plane_error: float = 1.0e-3,
) -> Path:
    paths = []
    for mode, funnel_offset in ((80, 2.0e-7), (120, 1.0e-7), (160, 0.0)):
        paths.append(
            _write(
                root / name / f"m{mode}.json",
                _watchdog(
                    mode,
                    degree=degree,
                    h_nm=h_nm,
                    local_dofs=local_dofs,
                    assembled_nnz=assembled_nnz,
                    rss_bytes=rss_bytes,
                    total_seconds=total_seconds,
                    sha=sha,
                    observable_offset=candidate_offset + funnel_offset,
                    plane_error=plane_error,
                ),
            )
        )
    funnel = build_hybrid_funnel_from_paths(paths)
    assert funnel["status"] == "qualified", funnel["failures"]
    return _write(root / f"{name}_funnel.json", funnel)


def _mutate_selected(funnel_path: Path, callback) -> None:
    funnel = json.loads(funnel_path.read_text(encoding="utf-8"))
    selected_m = funnel["qualification"]["selected_mode_count_per_direction"]
    descriptor = next(
        row
        for row in funnel["source_records"]
        if row["mode_count_per_direction"] == selected_m
    )
    watchdog_path = Path(descriptor["path"])
    payload = json.loads(watchdog_path.read_text(encoding="utf-8"))
    callback(payload)
    _write(watchdog_path, payload)
    descriptor["sha256"] = _sha256(watchdog_path)
    _write(funnel_path, funnel)


class Task033EqualAccuracyTests(unittest.TestCase):
    def test_selects_best_arbitrary_degree_and_records_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _funnel(
                root,
                "reference_p2",
                degree=2,
                h_nm=3.0,
                local_dofs=1000,
                assembled_nnz=10000,
                rss_bytes=5_000_000,
                total_seconds=100.0,
            )
            candidate_p1 = _funnel(
                root,
                "candidate_p1",
                degree=1,
                h_nm=2.0,
                local_dofs=600,
                assembled_nnz=7000,
                rss_bytes=3_500_000,
                total_seconds=70.0,
                candidate_offset=1.0e-7,
            )
            candidate_p4 = _funnel(
                root,
                "candidate_p4",
                degree=4,
                h_nm=5.0,
                local_dofs=200,
                assembled_nnz=3000,
                rss_bytes=1_500_000,
                total_seconds=30.0,
                candidate_offset=2.0e-7,
            )
            result = build_equal_accuracy(reference, [candidate_p1, candidate_p4])
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(result["selection"]["best_candidate_id"], "candidate_2")
            self.assertEqual(
                result["candidates"][1]["local_dof_compression_classification"],
                "strong",
            )
            self.assertEqual(
                result["candidates"][0]["comparisons"]["qep_beta"]["status"],
                "not_available",
            )
            self.assertEqual(len(result["payload_sha256"]), 64)
            self.assertEqual(len(result["inputs"]["reference"]["funnel_sha256"]), 64)
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(result)

    def test_source_mismatch_and_dirty_source_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _funnel(
                root,
                "reference",
                degree=2,
                h_nm=3.0,
                local_dofs=1000,
                assembled_nnz=10000,
                rss_bytes=5_000_000,
                total_seconds=100.0,
            )
            changed = _funnel(
                root,
                "changed_sha",
                degree=3,
                h_nm=5.0,
                local_dofs=500,
                assembled_nnz=5000,
                rss_bytes=2_500_000,
                total_seconds=50.0,
                sha="b" * 40,
            )
            result = build_equal_accuracy(reference, [changed])
            self.assertEqual(result["status"], "not_qualified")
            self.assertIn("source_sha_mismatch", result["candidates"][0]["failures"])

            dirty = _funnel(
                root,
                "dirty",
                degree=3,
                h_nm=5.0,
                local_dofs=500,
                assembled_nnz=5000,
                rss_bytes=2_500_000,
                total_seconds=50.0,
            )
            _mutate_selected(
                dirty,
                lambda payload: payload["source"].update(
                    {
                        "worktree_status_after": "?? uncommitted_solver.py",
                        "nonignored_untracked_after": ["uncommitted_solver.py"],
                    }
                ),
            )
            result = build_equal_accuracy(reference, [dirty])
            self.assertEqual(result["status"], "not_qualified")
            self.assertIn("dirty", result["candidates"][0]["failures"][0])

    def test_missing_selected_plane_and_field_gate_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _funnel(
                root,
                "reference",
                degree=2,
                h_nm=3.0,
                local_dofs=1000,
                assembled_nnz=10000,
                rss_bytes=5_000_000,
                total_seconds=100.0,
            )
            missing = _funnel(
                root,
                "missing",
                degree=3,
                h_nm=5.0,
                local_dofs=500,
                assembled_nnz=5000,
                rss_bytes=2_500_000,
                total_seconds=50.0,
            )
            _mutate_selected(
                missing,
                lambda payload: payload["measurements"][
                    "physical_field_reconstruction"
                ].pop("selected_plane_full3d_comparison"),
            )
            missing_result = build_equal_accuracy(reference, [missing])
            self.assertEqual(missing_result["status"], "not_qualified")
            self.assertIn(
                "missing selected-plane",
                missing_result["candidates"][0]["failures"][0],
            )

            inaccurate = _funnel(
                root,
                "inaccurate",
                degree=4,
                h_nm=5.0,
                local_dofs=200,
                assembled_nnz=3000,
                rss_bytes=1_500_000,
                total_seconds=30.0,
                plane_error=6.0e-3,
            )
            field_result = build_equal_accuracy(reference, [inaccurate])
            self.assertEqual(field_result["status"], "not_qualified")
            self.assertIn(
                "selected_plane_field_gate_failed",
                field_result["candidates"][0]["failures"],
            )

    def test_classification_boundaries_are_exact(self) -> None:
        for ratio, expected in (
            (1.299999, "weak"),
            (1.3, "positive"),
            (1.999999, "positive"),
            (2.0, "clear"),
            (2.999999, "clear"),
            (3.0, "engineering"),
            (4.999999, "engineering"),
            (5.0, "strong"),
        ):
            with self.subTest(ratio=ratio):
                self.assertEqual(classify_compression(ratio), expected)


if __name__ == "__main__":
    unittest.main()
