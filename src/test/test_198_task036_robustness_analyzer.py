from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.analyze_task036_robustness_scan import (
    AnalysisError,
    analyze_point,
    build_failure_clusters,
)


SOURCE_SHA = "a" * 40


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(point_id: str = "D001-S", polarization: str = "s") -> dict[str, Any]:
    return {
        "point_id": point_id,
        "round": "D",
        "degree": 6,
        "h_nm": 10.0,
        "height_nm": 120.0,
        "width_x_nm": 17.0,
        "grazing_deg": 0.5,
        "azimuth_deg": 0.0,
        "polarization": polarization,
        "axis_counts": [6, 4, 14],
        "initial_m": 120,
    }


def _order(
    *,
    side: str,
    m: int,
    n: int,
    polarization: str,
    amplitude: complex,
    power: float,
    full3d: bool,
    propagating: bool = True,
    power_carrying: bool = True,
) -> dict[str, Any]:
    value = {
        "side": side,
        "polarization": polarization,
        "outgoing_amplitude_at_boundary": [amplitude.real, amplitude.imag],
        "power_ratio": power,
        "propagating": propagating,
        "power_carrying": power_carrying,
    }
    if full3d:
        value.update({"order_m": m, "order_n": n})
    else:
        value.update({"m": m, "n": n})
    return value


def _default_orders(*, full3d: bool) -> list[dict[str, Any]]:
    return [
        _order(
            side="top",
            m=0,
            n=0,
            polarization="s",
            amplitude=complex(0.6, 0.2),
            power=0.4,
            full3d=full3d,
        ),
        _order(
            side="bottom",
            m=-1,
            n=0,
            polarization="p",
            amplitude=complex(1.0e-7, -2.0e-7),
            power=1.0e-12,
            full3d=full3d,
            propagating=False,
            power_carrying=True,
        ),
    ]


def _full3d(
    point_dir: Path,
    point: dict[str, Any],
    *,
    orders: list[dict[str, Any]] | None = None,
    peak_gib: float = 20.0,
    wall_seconds: float = 100.0,
) -> str:
    full_dir = point_dir / "full3d"
    summary_path = full_dir / "run_summary.json"
    orders_path = full_dir / "dtn_port_diffraction_orders_3d.json"
    watchdog_path = full_dir / "watchdog_summary.json"
    summary = {
        "config": {
            "mesh_axis_cell_counts": point["axis_counts"],
            "grating_height": point["height_nm"],
            "grating_width_x": point["width_x_nm"],
        },
        "mpi_size": 8,
        "polarization_kind": point["polarization"],
        "nedelec_degree": point["degree"],
        "mesh_cells_resolved": point["axis_counts"],
        "incident_theta_deg": 90.0 - point["grazing_deg"],
        "incident_phi_deg": point["azimuth_deg"],
        "geometry_kind": "rectangular_block_grating",
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "linear_system_relative_residual": 1.0e-11,
        "R_total": 0.4,
        "T_total": 0.2,
        "A_volume_total": 0.4,
        "auxiliary_direct_tangential_projection_audit": {
            "requested": True,
            "max_absolute_outgoing_projection_difference": 1.0e-12,
            "pass": True,
        },
        "num_active_condensed_dofs": 1000,
        "num_independent_trace_rows": 900,
        "matrix_stats": {"matrix_nnz_used": 10000.0},
        "stage4_dtn_factor_inventory": {
            "available": True,
            "factor_nnz_corrected": None,
            "matrix_stats": {"matrix_nnz_used": 50000.0},
        },
        "elapsed_seconds": wall_seconds,
    }
    _write_json(summary_path, summary)
    _write_json(
        orders_path,
        {"orders": orders if orders is not None else _default_orders(full3d=True)},
    )
    watchdog = {
        "degree": point["degree"],
        "h_nm": point["h_nm"],
        "mpi_size": 8,
        "return_code": 0,
        "no_swap": True,
        "command": ["full3d"],
        "source": {
            "commit_sha": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "stable_and_clean_after": True,
            "tracked_source_dirty": False,
            "status_after": "",
        },
        "qualification": {"pass": True},
        "raw_evidence": {
            "solver_summary": str(summary_path),
            "dtn_orders": str(orders_path),
        },
        "solver_summary_sha256": _sha256(summary_path),
        "dtn_orders_sha256": _sha256(orders_path),
        "resource_authority": {"memory_authority_gib": peak_gib},
    }
    _write_json(watchdog_path, watchdog)
    return _sha256(watchdog_path)


def _hybrid(
    point_dir: Path,
    point: dict[str, Any],
    full3d_sha: str,
    mode_count: int,
    *,
    orders: list[dict[str, Any]] | None = None,
    candidate_projection: bool = True,
    peak_gib: float = 8.0,
    wall_seconds: float = 60.0,
    explicit_capacity: bool = False,
) -> None:
    run_dir = point_dir / f"hybrid_m{mode_count}"
    solver_path = run_dir / "solver_record.json"
    memory_path = run_dir / "memory_sampler_summary.json"
    binding = {
        "pass": True,
        "expected_sha256": full3d_sha,
        "observed_sha256": full3d_sha,
        "reference_source_sha": SOURCE_SHA,
        "current_source_sha": SOURCE_SHA,
    }
    validation: dict[str, Any] = {
        "interface_e_projection": {"combined_relative_residual": 1.0e-11},
        "fe_modal_traction_equilibrium": {
            "bottom_dual": {"relative_dual": 1.0e-11},
            "top_dual": {"relative_dual": 2.0e-11},
        },
        "port_power": {"R_total": 0.4, "T_total": 0.2},
        "external_diffraction_orders": (
            orders if orders is not None else _default_orders(full3d=False)
        ),
    }
    if candidate_projection:
        projection_orders = [
            {
                "side": side,
                "m": 0,
                "n": 0,
                "polarization": polarization,
                "absolute_total_projection_difference": 2.0e-12,
                "absolute_outgoing_projection_difference": 2.0e-12,
            }
            for side in ("bottom", "top")
            for polarization in ("s", "p")
        ]
        validation["auxiliary_direct_tangential_projection_audit"] = {
            "requested": True,
            "scope": "hybrid_candidate",
            "tolerance": 1.0e-10,
            "expected_mode_count": len(projection_orders),
            "audited_mode_count": len(projection_orders),
            "max_absolute_outgoing_projection_difference": 2.0e-12,
            "pass": True,
            "orders": projection_orders,
        }
    solver: dict[str, Any] = {
        "metadata": {
            "commit_sha": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
            "source_commit_at_end_full_sha": SOURCE_SHA,
            "source_clean_and_stable": True,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "mpi_size": 8,
            "task036_domain_robustness_authority_gate": dict(binding),
        },
        "case": {
            "degree": point["degree"],
            "modal_degree": point["degree"],
            "h_nm": point["h_nm"],
            "modal_h_nm": point["h_nm"],
            "grating_height_nm": point["height_nm"],
            "grating_width_x_nm": point["width_x_nm"],
            "incident_grazing_deg": point["grazing_deg"],
            "incident_phi_deg": point["azimuth_deg"],
            "polarization_kind": point["polarization"],
            "mesh_axis_cell_counts_actual_full_plan": point["axis_counts"],
            "requested_modes_per_direction": mode_count,
        },
        "qep": {
            "positive_directional_selection": {
                "selected_modes": mode_count,
                "finite_candidate_count": 2 * mode_count,
            },
            "negative_directional_selection": {
                "selected_modes": mode_count,
                "finite_candidate_count": 2 * mode_count,
            },
            "positive": {"max_biorthogonality_identity_error": 1.0e-7},
            "negative": {"max_biorthogonality_identity_error": 2.0e-7},
            "task036_scalar_stage4_reciprocal_basis": {
                "independent_negative": {
                    "max_biorthogonality_identity_error": 1.5e-7
                }
            },
        },
        "hybrid_system": {
            "bottom_assembly_backend_actual": "assembly_time_static_condensed",
            "top_assembly_backend_actual": "assembly_time_static_condensed",
            "bottom_static_condensation": {"local_algebra_rows": 400},
            "top_static_condensation": {"local_algebra_rows": 400},
            "bottom_matrix_stats": {"matrix_nnz_used": 3000.0},
            "top_matrix_stats": {"matrix_nnz_used": 3200.0},
            "internal_unknown_count": 2 * mode_count,
            "modal_schur": {"shape": [2 * mode_count, 2 * mode_count]},
        },
        "solve": {"true_relative_residual": 1.0e-11},
        "validation": validation,
        "physical_field_reconstruction": {
            "volume_absorption": {"A_volume_total": 0.4}
        },
        "object_payload_ledger": {
            "local_or_augmented_factor_inventory": {
                "bottom": {
                    "available": True,
                    "factor_nnz_corrected": None,
                    "matrix_stats": {"matrix_nnz_used": 12000.0},
                },
                "top": {
                    "available": True,
                    "factor_nnz_corrected": None,
                    "matrix_stats": {"matrix_nnz_used": 13000.0},
                },
            }
        },
        "timing_seconds_max_rank": {"total": wall_seconds},
    }
    if explicit_capacity:
        solver["modal_basis_capacity"] = {
            "available_finite_trace_rank": mode_count,
            "maximum_finite_full_trace_rank_reached": True,
        }
    _write_json(solver_path, solver)
    memory = {
        "requested_modes": mode_count,
        "candidate_modes": 2 * mode_count,
        "return_code": 0,
        "no_swap": True,
        "memory_authority_pass": True,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "solver_record_sha256": _sha256(solver_path),
        "source": {
            "commit_sha": SOURCE_SHA,
            "verified_clean_sha": SOURCE_SHA,
            "head_before_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "source_clean_verified": True,
            "source_stable_during_run": True,
            "tracked_status_before": "",
            "tracked_status_after": "",
            "worktree_status_before": "",
            "worktree_status_after": "",
            "nonignored_untracked_before": [],
            "nonignored_untracked_after": [],
        },
        "source_gate": {"pass": True},
        "launch_gate": {
            "pass": True,
            "matching_full3d_reference": dict(binding),
        },
        "resource_authority": {
            "memory_authority_gib": peak_gib,
            "gate": {"pass": True},
        },
    }
    _write_json(memory_path, memory)


def _build_point(
    tmp_path: Path,
    *,
    candidate_projection: bool = True,
    modes: tuple[int, ...] = (120, 240),
    full_orders: list[dict[str, Any]] | None = None,
    hybrid_orders: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], Path]:
    point = _point()
    point_dir = tmp_path / point["point_id"]
    watchdog_sha = _full3d(point_dir, point, orders=full_orders)
    for index, mode_count in enumerate(modes):
        _hybrid(
            point_dir,
            point,
            watchdog_sha,
            mode_count,
            orders=hybrid_orders,
            candidate_projection=candidate_projection,
            peak_gib=8.0 + 2.0 * index,
            wall_seconds=60.0 + 20.0 * index,
        )
    return point, point_dir


def test_happy_adjacent_pair_yields_formal_m120_and_live_resource_ratios(
    tmp_path: Path,
) -> None:
    point, point_dir = _build_point(tmp_path)
    result = analyze_point(point, point_dir, SOURCE_SHA)

    assert result["status"] == "qualified"
    assert result["classification"]["numerical_minimum_passing_M"] == 120
    assert result["classification"]["formal_minimum_passing_M"] == 120
    assert result["classification"]["formal_evidence_complete"] is True
    m120 = result["hybrid_by_m"]["120"]
    assert m120["full3d_comparison"]["fixed_channels"]["pass_count"] == 2
    assert m120["resource_ratio"]["hybrid_over_full3d_peak_memory"] == 0.4
    assert m120["resource_ratio"]["hybrid_over_full3d_wall"] == 0.6
    assert (
        m120["metrics"]["factor_nnz_inventory_sum_not_simultaneous_peak"]
        == 25000.0
    )
    assert m120["capacity"]["finite_candidate_count_not_used_as_capacity"] is True


def test_legacy_hybrid_projection_gap_preserves_numerical_but_not_formal_m(
    tmp_path: Path,
) -> None:
    point, point_dir = _build_point(tmp_path, candidate_projection=False)
    result = analyze_point(point, point_dir, SOURCE_SHA)

    assert result["status"] == "formal_evidence_incomplete"
    assert result["classification"]["numerical_minimum_passing_M"] == 120
    assert result["classification"]["formal_minimum_passing_M"] is None
    assert result["classification"]["formal_evidence_complete"] is False
    assert result["hybrid_by_m"]["120"]["candidate_direct_projection"] == {
        "present": False,
        "available": False,
        "difference": None,
        "pass": False,
        "reason": "hybrid_candidate_direct_projection_missing",
    }
    assert result["failure_buckets"][
        "candidate_direct_projection_evidence_missing"
    ] == [120, 240]


def test_projection_without_explicit_hybrid_candidate_scope_is_not_formal(
    tmp_path: Path,
) -> None:
    point, point_dir = _build_point(tmp_path)
    solver_path = point_dir / "hybrid_m120" / "solver_record.json"
    memory_path = point_dir / "hybrid_m120" / "memory_sampler_summary.json"
    solver = json.loads(solver_path.read_text(encoding="utf-8"))
    solver["validation"][
        "auxiliary_direct_tangential_projection_audit"
    ].pop("scope")
    _write_json(solver_path, solver)
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    memory["solver_record_sha256"] = _sha256(solver_path)
    _write_json(memory_path, memory)

    result = analyze_point(point, point_dir, SOURCE_SHA)
    projection = result["hybrid_by_m"]["120"][
        "candidate_direct_projection"
    ]
    assert projection["present"] is True
    assert projection["available"] is False
    assert projection["pass"] is False
    assert (
        projection["reason"]
        == "hybrid_candidate_direct_projection_incomplete"
    )
    assert result["classification"]["formal_minimum_passing_M"] is None


def test_solver_hash_mutation_fails_closed(tmp_path: Path) -> None:
    point, point_dir = _build_point(tmp_path)
    solver_path = point_dir / "hybrid_m120" / "solver_record.json"
    solver = json.loads(solver_path.read_text(encoding="utf-8"))
    solver["solve"]["true_relative_residual"] = 3.0e-11
    _write_json(solver_path, solver)

    with pytest.raises(AnalysisError, match="solver_record_sha256"):
        analyze_point(point, point_dir, SOURCE_SHA)


def test_source_sha_mismatch_fails_closed(tmp_path: Path) -> None:
    point, point_dir = _build_point(tmp_path)
    memory_path = point_dir / "hybrid_m120" / "memory_sampler_summary.json"
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    memory["source"]["head_after_sha"] = "b" * 40
    _write_json(memory_path, memory)

    with pytest.raises(AnalysisError, match=r"source\.head_after_sha"):
        analyze_point(point, point_dir, SOURCE_SHA)


def test_lossy_nonpropagating_channel_and_complex_phase_are_not_dropped(
    tmp_path: Path,
) -> None:
    full_orders = [
        _order(
            side="bottom",
            m=-2,
            n=0,
            polarization="p",
            amplitude=complex(1.0, 0.0),
            power=2.0e-2,
            full3d=True,
            propagating=False,
            power_carrying=True,
        )
    ]
    hybrid_orders = [
        _order(
            side="bottom",
            m=-2,
            n=0,
            polarization="p",
            amplitude=complex(-1.0, 0.0),
            power=2.0e-2,
            full3d=False,
            propagating=False,
            power_carrying=True,
        )
    ]
    point, point_dir = _build_point(
        tmp_path,
        full_orders=full_orders,
        hybrid_orders=hybrid_orders,
    )
    result = analyze_point(point, point_dir, SOURCE_SHA)

    row = result["hybrid_by_m"]["120"]["full3d_comparison"]["fixed_channels"][
        "rows"
    ][0]
    assert row["significant"] is True
    assert row["cross_polarization"] is True
    assert row["left_propagating"] is False
    assert row["right_propagating"] is False
    assert row["power_pass"] is True
    assert row["complex_amplitude_pass"] is False
    assert result["status"] == "rank_plateau_not_sufficient"


def test_candidate_promoted_channel_uses_one_point_significance_inventory(
    tmp_path: Path,
) -> None:
    full_orders = [
        _order(
            side="top",
            m=1,
            n=0,
            polarization="s",
            amplitude=0j,
            power=0.0,
            full3d=True,
        )
    ]
    hybrid_orders = [
        _order(
            side="top",
            m=1,
            n=0,
            polarization="s",
            amplitude=complex(2.0e-4, 0.0),
            power=2.0e-8,
            full3d=False,
        )
    ]
    point, point_dir = _build_point(
        tmp_path,
        full_orders=full_orders,
        hybrid_orders=hybrid_orders,
    )
    result = analyze_point(point, point_dir, SOURCE_SHA)

    assert result["significance_inventory"]["significant_keys"] == [
        ["top", 1, 0, "s"]
    ]
    failure = result["hybrid_by_m"]["120"]["full3d_comparison"][
        "fixed_channels"
    ]["failures"][0]
    assert failure["significant"] is True
    assert failure["power_relative_error"] == 1.0


def test_adjacent_plateau_against_full3d_has_no_minimum_m(
    tmp_path: Path,
) -> None:
    full_orders = [
        _order(
            side="top",
            m=0,
            n=0,
            polarization="s",
            amplitude=complex(1.0, 0.0),
            power=0.4,
            full3d=True,
        )
    ]
    hybrid_orders = [
        _order(
            side="top",
            m=0,
            n=0,
            polarization="s",
            amplitude=complex(1.01, 0.0),
            power=0.4,
            full3d=False,
        )
    ]
    point, point_dir = _build_point(
        tmp_path,
        full_orders=full_orders,
        hybrid_orders=hybrid_orders,
    )
    result = analyze_point(point, point_dir, SOURCE_SHA)

    assert result["adjacent_pairs"][0]["adjacent_numerical_pass"] is True
    assert result["adjacent_pairs"][0]["numerical_qualification_pass"] is False
    assert result["classification"]["adjacent_m_converged"] is True
    assert result["classification"]["numerical_minimum_passing_M"] is None
    assert result["classification"]["formal_minimum_passing_M"] is None
    assert result["status"] == "rank_plateau_not_sufficient"
    assert result["hybrid_by_m"]["240"]["finite_candidate_count"] == {
        "positive": 480,
        "negative": 480,
    }
    assert (
        result["classification"]["finite_candidate_count_used_as_capacity"] is False
    )


def test_single_last_m_needs_explicit_full_rank_capacity(tmp_path: Path) -> None:
    point, point_dir = _build_point(tmp_path, modes=(120,))
    pending = analyze_point(point, point_dir, SOURCE_SHA)
    assert pending["status"] == "rank_pending_next_m"
    assert pending["classification"]["formal_minimum_passing_M"] is None

    solver_path = point_dir / "hybrid_m120" / "solver_record.json"
    memory_path = point_dir / "hybrid_m120" / "memory_sampler_summary.json"
    solver = json.loads(solver_path.read_text(encoding="utf-8"))
    solver["modal_basis_capacity"] = {
        "available_finite_trace_rank": 120,
        "maximum_finite_full_trace_rank_reached": True,
    }
    _write_json(solver_path, solver)
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    memory["solver_record_sha256"] = _sha256(solver_path)
    _write_json(memory_path, memory)

    qualified = analyze_point(point, point_dir, SOURCE_SHA)
    assert qualified["status"] == "qualified"
    assert qualified["classification"]["numerical_minimum_passing_M"] == 120
    assert qualified["classification"]["formal_minimum_passing_M"] == 120


def test_failure_buckets_and_clusters_separate_cross_and_weak_mechanisms(
    tmp_path: Path,
) -> None:
    full_orders = [
        _order(
            side="bottom",
            m=-2,
            n=0,
            polarization="p",
            amplitude=complex(1.0, 0.0),
            power=0.1,
            full3d=True,
        ),
        _order(
            side="top",
            m=-3,
            n=0,
            polarization="s",
            amplitude=0j,
            power=0.0,
            full3d=True,
        ),
    ]
    hybrid_orders = [
        _order(
            side="bottom",
            m=-2,
            n=0,
            polarization="p",
            amplitude=complex(1.01, 0.0),
            power=0.1,
            full3d=False,
        ),
        _order(
            side="top",
            m=-3,
            n=0,
            polarization="s",
            amplitude=complex(2.0e-8, 0.0),
            power=0.0,
            full3d=False,
        ),
    ]
    point, point_dir = _build_point(
        tmp_path,
        full_orders=full_orders,
        hybrid_orders=hybrid_orders,
    )
    result = analyze_point(point, point_dir, SOURCE_SHA)

    assert {
        "significant_cross_polarization",
        "weak_co_polarization",
    }.issubset(result["failure_buckets"])
    clusters = build_failure_clusters([result])
    assert len(clusters) == 1
    assert clusters[0]["mechanisms"] == [
        "significant_cross",
        "weak_co",
    ]
    assert clusters[0]["point_ids"] == ["D001-S"]
    rows = result["hybrid_by_m"]["120"]["full3d_comparison"]["fixed_channels"][
        "rows"
    ]
    assert [row["key"] for row in rows] == [
        ["bottom", -2, 0, "p"],
        ["top", -3, 0, "s"],
    ]
