"""Fail-closed DtN wiring for the live standard-p6 local Schur hook."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
from mpi4py import MPI

from benchmarks.run_task035b_direct_setup_profile import _direct_config
from src.adaptivity.physical_missing_p6_action_only_complement import (
    FullP6LocalSchurClassCollector,
)
from src.common.config_3d import (
    SimulationConfig3D,
    target_stage4_config,
)
from src.solvers.dtn_port_3d import (
    _build_assembly_time_condensation_with_request,
    _canonical_orientation_class_reuse_request_audit,
    _live_full_p6_local_schur_capture_request,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


def _qualified_config(*, requested: bool) -> SimulationConfig3D:
    with tempfile.TemporaryDirectory() as directory:
        config = _direct_config(
            source_sha="a" * 40,
            cache_directory=Path(directory) / "cache",
            cache_state="warm",
            h_nm=15.0,
        )
    return replace(
        config,
        stage4_live_full_p6_local_schur_capture=requested,
    )


def test_ordinary_default_does_not_create_a_live_observer() -> None:
    ordinary = SimulationConfig3D()
    assert ordinary.stage4_live_full_p6_local_schur_capture is False
    collector, audit = _live_full_p6_local_schur_capture_request(
        ordinary
    )
    assert collector is None
    assert audit["requested"] is False
    assert audit["accepted"] is False
    assert audit["ordinary_default_changed"] is False


def test_qualified_explicit_request_creates_typed_collector() -> None:
    collector, audit = _live_full_p6_local_schur_capture_request(
        _qualified_config(requested=True)
    )
    assert isinstance(collector, FullP6LocalSchurClassCollector)
    assert audit == {
        "schema_version": (
            "task035b.live-full-p6-local-schur-request.v1"
        ),
        "requested": True,
        "eligible": True,
        "accepted": True,
        "rejection_reasons": [],
        "required_path": (
            "assembly_time_affine_fixed_p5_trace_p6_interior_dtn"
        ),
        "full_p6_global_matrix_authorized": False,
        "inactive_missing_p6_rows_authorized": 0,
        "ordinary_default_changed": False,
    }


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {"stage4_assembly_time_cell_static_condensation": False},
            "assembly_time_cell_static_condensation_required",
        ),
        (
            {"stage4_affine_isotropic_reference_tensor": False},
            "affine_isotropic_reference_tensor_required",
        ),
        (
            {"nedelec_trace_degree": 4},
            "fixed_p5_trace_p6_interior_required",
        ),
        (
            {"stage4_regionwise_interior_p": True},
            "regionwise_p_conflict",
        ),
        (
            {
                "stage4_dtn_order_policy": "zero_order",
                "incident_theta_deg": 0.0,
            },
            "zero_order_local_robin_path_unsupported",
        ),
    ],
)
def test_ineligible_explicit_request_fails_closed(
    updates: dict[str, object],
    reason: str,
) -> None:
    config = replace(_qualified_config(requested=True), **updates)
    with pytest.raises(ValueError, match=reason):
        _live_full_p6_local_schur_capture_request(config)


def test_typed_collector_reaches_only_the_low_level_opt_in_keyword() -> None:
    collector, _audit = _live_full_p6_local_schur_capture_request(
        _qualified_config(requested=True)
    )
    canonical_audit = _canonical_orientation_class_reuse_request_audit(
        _qualified_config(requested=False)
    )
    sentinel = object()
    with patch(
        "src.solvers.dtn_port_3d."
        "build_unconstrained_assembly_time_condensation",
        return_value=sentinel,
    ) as core:
        result = _build_assembly_time_condensation_with_request(
            object(),
            object(),
            object(),
            canonical_orientation_request_audit=canonical_audit,
            full_p6_storage_local_schur_observer=collector,
        )
    assert result is sentinel
    assert (
        core.call_args.kwargs[
            "full_p6_storage_local_schur_observer"
        ]
        is collector
    )
    assert (
        core.call_args.kwargs[
            "canonical_orientation_class_reuse"
        ]
        is False
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="run with mpiexec -n 2",
)
def test_mpi2_actual_dtn_exposes_the_live_core_capture() -> None:
    config = replace(
        target_stage4_config(degree=6, h_nm=100.0),
        case_name="task035b_live_full_p6_local_schur_mpi2_v3",
        nedelec_trace_degree=5,
        nedelec_interior_degree=6,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        stage4_affine_isotropic_reference_tensor=True,
        stage4_live_full_p6_local_schur_capture=True,
        direct_release_base_after_augmentation=True,
        direct_release_solver_before_postprocess=True,
        unique_output=False,
    )
    captured: dict[str, object] = {}

    def observer(**state) -> None:
        captured.update(
            state["dtn_result"]["goal_context"][
                "live_full_p6_local_schur_capture"
            ]
        )

    summary = run_stage4b_block_grating_3d_case(
        config,
        Path(
            "/tmp/task035b_live_full_p6_local_schur_mpi2_v3"
        ),
        solution_observer=observer,
    )
    assert summary["case_status"] == "completed"
    assert summary["official_result"] is True
    assert summary["linear_system_relative_residual"] <= 1.0e-9
    core_audit = captured["core_audit"]
    assert isinstance(core_audit, dict)
    assert core_audit["pass"] is True
    assert core_audit["communicator_size"] == 2
    assert core_audit["communicator_ordered_world_ranks"] == [0, 1]
    assert (
        core_audit["owned_cell_count_global"]
        == summary["num_mesh_cells"]
    )
    assert core_audit["storage_trace_dimension"] == 432
    assert core_audit["retained_trace_dimension"] == 300
    assert core_audit["full_p6_trace_matrix_materialized"] is False
    assert core_audit["inactive_missing_p6_rows_allocated"] == 0
    collector = captured["collector"]
    assert isinstance(collector, FullP6LocalSchurClassCollector)
    assert len(collector.cell_class_keys) == int(
        core_audit["owned_cell_count_local"]
    )
