from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.task035e_multigoal_snapshot import (
    LoadedTask035eSnapshot,
    _goal_context_identity,
)
from src.adaptivity.task035e_shadow_observer import (
    Task035eShadowObserverError,
    _atomic_json,
    _collective_local_call,
    _current_auxiliary_solver_coordinates,
    _json_sha256,
    _p6_coefficient_projection_audit,
    _public_affine_complement_audit,
    _public_trace_conformance_audit,
    _release_h_shadow_projection_temporaries,
    _requires_exact_nested_current_projection,
    _validate_observed_shadow_kind,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d


def _balanced_ranges(total: int, size: int) -> list[list[int]]:
    quotient, remainder = divmod(total, size)
    ranges: list[list[int]] = []
    start = 0
    for rank in range(size):
        end = start + quotient + int(rank < remainder)
        ranges.append([start, end])
        start = end
    return ranges


def _h_trace_conformance_fixture(
    *,
    local_selected_rows: int,
) -> dict[str, object]:
    pipeline = {
        "schema_version": (
            "task035e.physical-root-primal-projection-pipeline.v1"
        ),
        "status": "physical_root_primal_projection_pipeline_pass",
        "pass": True,
        "input_receives_exact_nested_transfer_credit": False,
        "active_interior_rows_bitwise_unchanged": True,
        "strict_reextraction_closure_l2_norm": 2.0e-12,
        "strict_reextraction_closure_linf_norm": 3.0e-13,
        "strict_reextraction_reference_l2_norm": 376.0,
        "strict_reextraction_reference_linf_norm": 37.0,
        "strict_reextraction_relative_l2": 6.0e-15,
        "strict_reextraction_relative_linf": 8.0e-15,
        "strict_reextraction_tolerance": 5.0e-10,
        "full_vector_allgather_used": False,
        "ordinary_default_changed": False,
        "input_extraction": {
            "active_selected_row_count_local": local_selected_rows,
        },
        "trace_projection": {
            "selected_unique_row_count_local": local_selected_rows,
        },
        "strict_reextraction": {
            "requested_row_count_local": local_selected_rows,
        },
    }
    recovery = {
        "schema_version": "task035d.variable-p-p6-recovery.v1",
        "status": "conforming_p6_storage_recovery_pass",
        "pass": True,
        "absolute_shared_coefficient_error_max": 1.0e-13,
        "relative_shared_coefficient_error_max": 4.0e-15,
        "conformity_tolerance": 5.0e-10,
        "target_field_reused": True,
        "new_p6_function_allocated": False,
        "replaced_field_coefficients_audited_before_overwrite": True,
        "replaced_coefficient_delta_l2_norm": 0.04,
        "replaced_coefficient_reference_l2_norm": 773.0,
        "replaced_coefficient_delta_relative_l2": 5.2e-5,
        "replaced_coefficient_delta_linf_norm": 0.015,
        "replaced_coefficient_reference_linf_norm": 32.7,
        "replaced_coefficient_delta_relative_linf": 4.6e-4,
        "replaced_coefficient_rows_designated_exactly_once": True,
        "selected_values_reused_for_recovery_and_conformity_audit": True,
        "full_active_vector_replicated_bytes_per_rank": 0,
        "global_embedding_matrix_allocated": False,
        "ordinary_default_changed": False,
        "active_selected_row_count_local": local_selected_rows,
        "active_selected_rows": {
            "selected_unique_row_count_local": local_selected_rows,
        },
    }
    return {
        "schema_version": "task035e.h-shadow-trace-conformance.v1",
        "status": "physical_root_conforming_h_shadow_projection_pass",
        "pass": True,
        "shadow_kind": "h-shadow",
        "exact_nested_projection_retained": False,
        "physical_root_projection_applied": True,
        "ordinary_default_changed": False,
        "pre_recovery_temporary_release": {
            "schema_version": (
                "task035e.h-shadow-projection-temporary-release.v1"
            ),
            "status": "h_shadow_projection_temporaries_released",
            "pass": True,
            "phase": "before_in_place_p6_recovery",
            "sum_rss_before_mb": 7700.0,
            "sum_rss_after_mb": 7510.0,
            "sum_rss_released_mb": 190.0,
            "ordinary_default_changed": False,
        },
        "projection_pipeline": pipeline,
        "conforming_p6_recovery": recovery,
        "coefficient_projection": {
            "schema_version": (
                "task035e.h-shadow-conforming-p6-"
                "coefficient-projection.v1"
            ),
            "status": (
                "h_shadow_conforming_p6_coefficient_projection_pass"
            ),
            "pass": True,
            "coefficient_delta_relative_l2": 5.2e-5,
            "exact_nested_transfer_credit": False,
            "ordinary_default_changed": False,
        },
    }


def test_h_shadow_conforming_coefficient_audit_is_scale_bound() -> None:
    audit = _p6_coefficient_projection_audit(
        delta_l2=1.0e-4,
        delta_linf=8.0e-5,
        reference_l2=4.0,
        reference_linf=3.0,
        source_projection_relative_scale=1.0e-3,
    )
    assert audit["pass"] is True
    assert audit["exact_nested_transfer_credit"] is False
    with pytest.raises(
        RuntimeError,
        match="exceeds its source projection scale",
    ):
        _p6_coefficient_projection_audit(
            delta_l2=1.0e-4,
            delta_linf=8.0e-5,
            reference_l2=4.0,
            reference_linf=3.0,
            source_projection_relative_scale=1.0e-8,
        )


def test_h_shadow_projection_temporary_release_is_audited() -> None:
    audit = _release_h_shadow_projection_temporaries(
        MPI.COMM_SELF,
        phase="before_goal_gradients",
    )
    assert audit["pass"] is True
    assert audit["phase"] == "before_goal_gradients"
    assert audit["python_gc_called_twice"] is True
    assert audit["petsc_garbage_cleanup_called"] is True
    assert audit["glibc_malloc_trim_called"] is True
    assert audit["release_occurs_before_formal_goal_gradients"] is True
    assert audit["release_occurs_before_in_place_p6_recovery"] is False

    with pytest.raises(ValueError, match="cleanup phase is invalid"):
        _release_h_shadow_projection_temporaries(
            MPI.COMM_SELF,
            phase="after_goal_gradients",
        )


def test_trace_conformance_public_audit_omits_rank_local_rows() -> None:
    public = _public_trace_conformance_audit(
        MPI.COMM_SELF,
        _h_trace_conformance_fixture(local_selected_rows=17),
        rank_pipeline_catalog_sha256="a" * 64,
    )
    assert public["pass"] is True
    assert public["rank_pipeline_catalog_sha256"] == "a" * 64
    assert (
        public[
            "rank_local_selected_row_fields_omitted_from_public_payload"
        ]
        is True
    )
    assert "input_extraction" not in public["projection_pipeline"]
    assert (
        "active_selected_row_count_local"
        not in public["conforming_p6_recovery"]
    )
    assert "active_selected_rows" not in public["conforming_p6_recovery"]


def test_p_shadow_trace_public_audit_needs_no_physical_projection() -> None:
    public = _public_trace_conformance_audit(
        MPI.COMM_SELF,
        {
            "schema_version": "task035e.h-shadow-trace-conformance.v1",
            "status": "physical_root_trace_projection_not_required",
            "pass": True,
            "shadow_kind": "p-shadow",
            "exact_nested_projection_retained": True,
            "physical_root_projection_applied": False,
            "ordinary_default_changed": False,
        },
        rank_pipeline_catalog_sha256="b" * 64,
    )
    assert public["pass"] is True
    assert public["physical_root_projection_applied"] is False
    assert "projection_pipeline" not in public


def test_mpi8_trace_conformance_public_audit_replays_identically() -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        pytest.skip("trace-conformance replay fixture requires MPI8")
    local_rows = 100 + int(comm.rank)
    local_audit = _h_trace_conformance_fixture(
        local_selected_rows=local_rows,
    )
    rank_catalog = comm.allgather(
        {
            "rank": int(comm.rank),
            "local_selected_rows": local_rows,
        }
    )
    catalog_sha = _json_sha256(
        rank_catalog,
        namespace="task035e.shadow-pipeline-rank-catalog.v1",
    )
    public = dict(
        _public_trace_conformance_audit(
            comm,
            local_audit,
            rank_pipeline_catalog_sha256=catalog_sha,
        )
    )
    packets = comm.allgather(public)
    assert packets == [packets[0]] * comm.size
    assert "active_selected_row_count_local" not in public[
        "conforming_p6_recovery"
    ]


def test_current_auxiliary_tail_is_reconstructed_without_full_gather() -> None:
    comm = MPI.COMM_WORLD
    config = target_stage4_config(degree=6, h_nm=15.0)
    modes = tuple(outgoing_port_modes_3d(config))
    appended = len(modes)
    current_trace = 13
    shadow_trace = 17
    indices = np.arange(appended, dtype=np.float64)
    solver_coordinates = (
        np.cos(0.07 * (indices + 1.0))
        + 1j * np.sin(0.11 * (indices + 1.0))
    )
    scales = (
        1.0
        + 0.03 * np.cos(0.05 * (indices + 1.0))
        + 0.02j * np.sin(0.09 * (indices + 1.0))
    )
    physical = solver_coordinates / scales
    incident = (
        0.1 * np.cos(0.13 * (indices + 1.0))
        + 0.05j * np.sin(0.17 * (indices + 1.0))
    )
    current_context = {
        "modes": modes,
        "auxiliary_values": physical,
        "incident_projections": incident,
        "auxiliary_coordinate_scales": scales,
        "num_fem_dofs_after_mpc": current_trace,
        "normalization": (
            "finite-port outgoing modal power / incident power"
        ),
    }
    shadow_context = {
        **current_context,
        "auxiliary_values": physical * (1.0 + 0.01j),
        "num_fem_dofs_after_mpc": shadow_trace,
    }
    global_reduced = np.concatenate(
        (
            np.linspace(
                0.1,
                0.9,
                current_trace,
                dtype=np.complex128,
            ),
            solver_coordinates,
        )
    )
    ranges = _balanced_ranges(len(global_reduced), comm.size)
    start, end = ranges[comm.rank]
    manifest = {
        "common_identity": {
            "reduction": {
                "independent_trace_rows": current_trace,
                "appended_auxiliary_rows": appended,
            },
            "goal_context": _goal_context_identity(current_context),
        },
        "partitions": {
            "reduced": {
                "global_size": len(global_reduced),
                "ownership_ranges": ranges,
            }
        },
    }
    snapshot = LoadedTask035eSnapshot(
        manifest_path=Path("/tmp/task035e-test-snapshot.json"),
        manifest_file_sha256="a" * 64,
        shard_path=Path(
            f"/tmp/task035e-test-snapshot-rank{comm.rank:04d}.npz"
        ),
        manifest=MappingProxyType(manifest),
        arrays=MappingProxyType(
            {
                "reduced_x_owned": np.asarray(
                    global_reduced[start:end]
                )
            }
        ),
    )
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        reduction=SimpleNamespace(
            system=SimpleNamespace(appended_rows=appended)
        ),
        goal_context=shadow_context,
    )
    observed, audit = _current_auxiliary_solver_coordinates(
        snapshot,
        view,
    )
    np.testing.assert_allclose(
        observed,
        solver_coordinates,
        rtol=2.0e-15,
        atol=2.0e-15,
    )
    assert audit["coverage_min"] == 1
    assert audit["coverage_max"] == 1
    assert audit["rank_local_validation_rendezvous"] is True
    assert audit["python_full_reduced_vector_allgather_used"] is False
    assert audit["native_small_auxiliary_allreduce_used"] is True


def test_collective_local_call_propagates_one_rank_failure() -> None:
    comm = MPI.COMM_WORLD

    def local_probe() -> int:
        if comm.rank == 0:
            raise ValueError("rank-zero validation failure")
        return int(comm.rank)

    with pytest.raises(
        Task035eShadowObserverError,
        match="rank-local probe failed collectively",
    ):
        _collective_local_call(
            comm,
            "rank-local probe",
            local_probe,
        )


def test_current_auxiliary_rank_local_failure_rendezvous() -> None:
    comm = MPI.COMM_WORLD
    config = target_stage4_config(degree=6, h_nm=15.0)
    modes = tuple(outgoing_port_modes_3d(config))
    appended = len(modes)
    current_trace = 1
    current_context = {
        "modes": modes,
        "auxiliary_values": np.ones(appended, dtype=np.complex128),
        "incident_projections": np.zeros(
            appended,
            dtype=np.complex128,
        ),
        "num_fem_dofs_after_mpc": current_trace,
        "normalization": "fixture",
    }
    global_reduced = np.concatenate(
        (
            np.zeros(current_trace, dtype=np.complex128),
            np.ones(appended, dtype=np.complex128),
        )
    )
    ranges = _balanced_ranges(len(global_reduced), comm.size)
    start, end = ranges[comm.rank]
    local_reduced = np.asarray(global_reduced[start:end])
    if comm.rank == 0:
        local_reduced = local_reduced[:-1]
    manifest = {
        "common_identity": {
            "reduction": {
                "independent_trace_rows": current_trace,
                "appended_auxiliary_rows": appended,
            },
            "goal_context": _goal_context_identity(current_context),
        },
        "partitions": {
            "reduced": {
                "global_size": len(global_reduced),
                "ownership_ranges": ranges,
            }
        },
    }
    snapshot = LoadedTask035eSnapshot(
        manifest_path=Path("/tmp/task035e-test-snapshot.json"),
        manifest_file_sha256="a" * 64,
        shard_path=Path(
            f"/tmp/task035e-test-snapshot-rank{comm.rank:04d}.npz"
        ),
        manifest=MappingProxyType(manifest),
        arrays=MappingProxyType(
            {"reduced_x_owned": local_reduced}
        ),
    )
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        reduction=SimpleNamespace(
            system=SimpleNamespace(appended_rows=appended)
        ),
        goal_context=current_context,
    )

    with pytest.raises(
        Task035eShadowObserverError,
        match="current auxiliary rank-local preflight failed collectively",
    ):
        _current_auxiliary_solver_coordinates(snapshot, view)


def test_current_auxiliary_tail_rejects_mode_identity_drift() -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial failure fixture")
    config = target_stage4_config(degree=6, h_nm=15.0)
    modes = tuple(outgoing_port_modes_3d(config))
    appended = len(modes)
    current_context = {
        "modes": modes,
        "auxiliary_values": np.ones(appended, dtype=np.complex128),
        "incident_projections": np.zeros(
            appended, dtype=np.complex128
        ),
        "num_fem_dofs_after_mpc": 2,
        "normalization": "fixture",
    }
    manifest = {
        "common_identity": {
            "reduction": {
                "independent_trace_rows": 2,
                "appended_auxiliary_rows": appended,
            },
            "goal_context": _goal_context_identity(current_context),
        },
        "partitions": {
            "reduced": {
                "global_size": 2 + appended,
                "ownership_ranges": [[0, 2 + appended]],
            }
        },
    }
    snapshot = LoadedTask035eSnapshot(
        manifest_path=Path("/tmp/task035e-test-snapshot.json"),
        manifest_file_sha256="a" * 64,
        shard_path=Path("/tmp/task035e-test-snapshot-rank0000.npz"),
        manifest=MappingProxyType(manifest),
        arrays=MappingProxyType(
            {
                "reduced_x_owned": np.concatenate(
                    (
                        np.zeros(2, dtype=np.complex128),
                        np.ones(appended, dtype=np.complex128),
                    )
                )
            }
        ),
    )
    shadow_context = {
        **current_context,
        "incident_projections": np.full(
            appended,
            0.01 + 0.0j,
            dtype=np.complex128,
        ),
    }
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_WORLD)
        ),
        reduction=SimpleNamespace(
            system=SimpleNamespace(appended_rows=appended)
        ),
        goal_context=shadow_context,
    )
    with pytest.raises(
        Task035eShadowObserverError,
        match="DtN identities differ",
    ):
        _current_auxiliary_solver_coordinates(snapshot, view)


def test_requested_shadow_kind_must_match_executed_transition() -> None:
    p_transition = {
        "transition_identity": {
            "observed_shadow_kind": "p-shadow",
            "same_forest_geometry": True,
            "same_degree_plan": False,
        }
    }
    h_transition = {
        "transition_identity": {
            "observed_shadow_kind": "h-shadow",
            "same_forest_geometry": False,
            "same_degree_plan": False,
        }
    }

    p_audit = _validate_observed_shadow_kind(
        p_transition,
        expected_shadow_kind="p-shadow",
    )
    h_audit = _validate_observed_shadow_kind(
        h_transition,
        expected_shadow_kind="h-shadow",
    )
    assert p_audit["pass"] is True
    assert h_audit["pass"] is True
    assert (
        p_audit["whole_plan_file_sha_used_for_classification"] is False
    )

    with pytest.raises(
        ValueError,
        match="requested shadow kind differs",
    ):
        _validate_observed_shadow_kind(
            p_transition,
            expected_shadow_kind="h-shadow",
        )
    with pytest.raises(
        ValueError,
        match="inconsistent with its classified shadow kind",
    ):
        _validate_observed_shadow_kind(
            {
                "transition_identity": {
                    "observed_shadow_kind": "p-shadow",
                    "same_forest_geometry": True,
                    "same_degree_plan": True,
                }
            },
            expected_shadow_kind="p-shadow",
        )


def test_projection_contract_is_exact_only_for_same_forest_p_shadow() -> None:
    assert _requires_exact_nested_current_projection("p-shadow") is True
    assert _requires_exact_nested_current_projection("h-shadow") is False
    with pytest.raises(ValueError, match="shadow kind"):
        _requires_exact_nested_current_projection("p-keep")


def test_atomic_shadow_json_is_mode_0600_and_immutable(
    tmp_path: Path,
) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial filesystem fixture")
    output = tmp_path / "shadow.json"
    _atomic_json(output, {"schema_version": "fixture", "pass": True})
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "pass": True,
        "schema_version": "fixture",
    }
    with pytest.raises(FileExistsError, match="immutable"):
        _atomic_json(output, {"schema_version": "replacement"})


def test_affine_complement_public_audit_uses_rank_hash_catalog() -> None:
    comm = MPI.COMM_WORLD
    local_audit = {
        "schema_version": (
            "task035e.variable-p-primal-affine-complement.v1"
        ),
        "status": "active_interior_affine_complement_pass",
        "pass": True,
        "definition": "fixture",
        "active_full_rows": 17,
        "raw_active_trace_rows": 11,
        "active_interior_rows": 6,
        "owned_cell_count_local": int(comm.rank + 1),
        "owned_cell_count_global": int(
            comm.size * (comm.size + 1) // 2
        ),
        "selected_row_layout": {
            "requested_unique_rows_local": int(3 + comm.rank)
        },
    }
    local_digest = _json_sha256(
        local_audit,
        namespace=(
            "task035e.actual-dwr.rank-affine-complement-audit.v1"
        ),
    )
    rank_catalog = comm.allgather(local_digest)
    aggregate = {
        "schema_version": local_audit["schema_version"],
        "status": local_audit["status"],
        "pass": True,
        "definition": "fixture",
        "active_full_rows": 17,
        "raw_active_trace_rows": 11,
        "active_interior_rows": 6,
        "owned_cell_count_global": local_audit[
            "owned_cell_count_global"
        ],
        "rank_local_audit_sha256": rank_catalog,
    }
    report = {
        "active_interior_affine_complement": {
            "present": True,
            "audit_identity": aggregate,
            "vector_identity": {"global_size": 17},
            "active_full_gradient_goal_ids": ["fixture"],
        }
    }

    public = _public_affine_complement_audit(
        comm,
        local_audit,
        report,
    )
    assert public["audit_identity"] == aggregate
    assert (
        "owned_cell_count_local"
        not in public["audit_identity"]
    )
    public_digest = _json_sha256(
        public,
        namespace="task035e.test.public-affine-audit.v1",
    )
    assert len(set(comm.allgather(public_digest))) == 1
