from __future__ import annotations

import json
from pathlib import Path

from benchmarks.task034_adaptive_compression import (
    build_adaptive_compression_summary,
    write_adaptive_csv,
)


def _payload(profile: str, factor: float, modes: int, *, all_pass: bool) -> dict:
    gates = {
        "monolithic_true_relative_residual_le_1e-9": True,
        "middle_plane_e_relative_l2_le_5e-3": all_pass,
    }
    return {
        "target": "hybrid",
        "return_code": 2,
        "requested_modes": modes,
        "memory_authority_pass": True,
        "no_swap": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "memory": {"max_simultaneous_worker_rss_gib": 1.0},
        "resource_authority": {"gate": {"pass": True}},
        "source_gate": {"pass": True},
        "launch_gate": {"pass": True},
        "source": {"head_before_sha": "a" * 40},
        "measurements": {
            "case": {
                "graded_profile": profile,
                "graded_coarse_factor": factor,
                "graded_plan_hash": profile,
                "graded_plan": {"mesh_cells": [2, 2, 2], "element_count": 8},
            },
            "hybrid_system": {
                "bottom_local_fe_dofs": 10,
                "top_local_fe_dofs": 10,
                "bottom_global_size": 12,
                "top_global_size": 12,
                "bottom_matrix_stats": {"matrix_nnz_used": 20},
                "top_matrix_stats": {"matrix_nnz_used": 20},
            },
            "solve": {"true_relative_residual": 1e-12},
            "validation": {"port_power": {"R_total": 0.1, "T_total": 0.7, "A_balance": 0.2}},
            "physical_field_reconstruction": {
                "interface_continuity": {},
                "volume_absorption": {"A_volume_total": 0.2},
                "selected_plane_full3d_comparison": {},
            },
            "full3d_reference_comparison": {"hybrid_minus_full3d": {}},
            "object_payload_ledger": {},
            "gates": gates,
            "timing_seconds_max_rank": {"total": 2.0},
        },
    }


def test_fail_closed_summary_withholds_compression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_payload("uniform", 1.0, 160, all_pass=True)))
    profiles = {}
    for profile, factor in (("conservative", 1.5), ("balanced", 2.0), ("aggressive", 3.0)):
        paths = []
        for modes in (80, 120, 160):
            path = tmp_path / f"{profile}_{modes}.json"
            path.write_text(json.dumps(_payload(profile, factor, modes, all_pass=False)))
            paths.append(path)
        profiles[profile] = paths
    summary = build_adaptive_compression_summary(
        baseline_path=baseline, profile_paths=profiles
    )
    assert summary["status"] == "controlled_negative"
    assert summary["decision"]["same_error_compression_demonstrated"] is False
    assert summary["profiles"]["conservative"]["modal_totals_converged"] is True
    assert summary["profiles"]["conservative"]["qualified_compression_ratio"] is None
    csv_path = tmp_path / "summary.csv"
    write_adaptive_csv(summary, csv_path)
    assert "failed_gate_names" in csv_path.read_text()
