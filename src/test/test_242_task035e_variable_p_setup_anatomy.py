from __future__ import annotations

from mpi4py import MPI
import numpy as np
import pytest
from types import SimpleNamespace

from src.adaptivity.hcurl_broken_cell_trace import (
    _CellExpansionRankAuditCache,
    _collective_rank_audit_cache,
    _maximal_rank_profile,
)
from src.adaptivity.stage4_local_h import _collective_phase_timings
from src.solvers.hcurl_variable_p_assembly import (
    _collective_setup_phase_timings,
)
from src.solvers import hcurl_variable_p_reduction


def _expansions() -> tuple[np.ndarray, np.ndarray]:
    canonical = np.asarray(
        [
            [1.0 + 0.0j, 0.0 + 0.0j, 0.25 - 0.5j],
            [0.0 + 0.0j, 2.0 + 0.0j, -0.5 + 0.25j],
        ],
        dtype=np.complex128,
    )
    oriented = canonical[[1, 0]].copy()
    return canonical, oriented


def test_exact_expansion_identity_cache_reuses_only_identical_svd() -> None:
    canonical, oriented = _expansions()
    cache = _CellExpansionRankAuditCache.create()

    first = cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented,
    )
    second = cache.profile(
        canonical_expansion=canonical.copy(),
        oriented_expansion=oriented.copy(),
    )
    direct = _maximal_rank_profile(oriented)

    assert first[:2] == direct[:2]
    assert second[:2] == direct[:2]
    assert first[2] == pytest.approx(direct[2], rel=1.0e-14)
    assert second[2] == pytest.approx(direct[2], rel=1.0e-14)
    assert first[3] == second[3]
    assert first[4] is False
    assert second[4] is True
    assert cache.miss_count == 1
    assert cache.hit_count == 1
    assert len(cache.profiles) == 1
    assert all(
        not isinstance(value, np.ndarray)
        for profile in cache.profiles.values()
        for value in profile.values()
    )


def test_cache_key_binds_exact_canonical_content_not_orientation() -> None:
    canonical, oriented = _expansions()
    cache = _CellExpansionRankAuditCache.create()
    first = cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented,
    )

    canonical_changed = canonical.copy()
    canonical_changed[0, 0] = np.nextafter(
        canonical_changed[0, 0].real,
        np.inf,
    )
    second = cache.profile(
        canonical_expansion=canonical_changed,
        oriented_expansion=oriented,
    )
    oriented_changed = oriented.copy()
    oriented_changed[:, [0, 1]] = oriented_changed[:, [1, 0]]
    third = cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented_changed,
    )

    assert first[3] != second[3]
    assert third[3] == first[3]
    assert third[4] is True
    assert cache.miss_count == 2
    assert cache.hit_count == 1


def test_collective_cache_audit_reports_hits_bytes_and_mpi_identity() -> None:
    canonical, oriented = _expansions()
    cache = _CellExpansionRankAuditCache.create()
    cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented,
    )
    cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented,
    )

    audit = _collective_rank_audit_cache(cache, MPI.COMM_WORLD)

    assert audit["pass"] is True
    assert audit["global_unique_profile_count"] == 1
    assert audit["cache_hit_count_global"] == MPI.COMM_WORLD.size
    assert audit["cache_miss_count_global"] == MPI.COMM_WORLD.size
    assert audit["matrix_payload_retained_by_cache"] is False
    assert audit["actual_expansion_built_and_validated_per_cell"] is True
    assert audit["mpi_profile_identity_fail_closed"] is True
    assert audit["locally_avoided_svd_input_bytes_global_sum"] == (
        oriented.nbytes * MPI.COMM_WORLD.size
    )


def test_collective_cache_audit_fails_on_cross_rank_profile_drift() -> None:
    if MPI.COMM_WORLD.size < 2:
        pytest.skip("cross-rank drift requires MPI")
    canonical, oriented = _expansions()
    cache = _CellExpansionRankAuditCache.create()
    profile = cache.profile(
        canonical_expansion=canonical,
        oriented_expansion=oriented,
    )
    if MPI.COMM_WORLD.rank == 0:
        cache.profiles[profile[3]]["condition"] += 1.0

    with pytest.raises(
        RuntimeError,
        match="MPI ranks disagree",
    ):
        _collective_rank_audit_cache(cache, MPI.COMM_WORLD)


def test_phase_timing_payloads_keep_rank_values_and_mpi_maximum() -> None:
    local = {
        "phase_a": float(MPI.COMM_WORLD.rank + 1),
        "phase_b": float(2 * MPI.COMM_WORLD.rank + 0.5),
    }
    stage4 = _collective_phase_timings(MPI.COMM_WORLD, local)
    assembly = _collective_setup_phase_timings(MPI.COMM_WORLD, local)

    for audit in (stage4, assembly):
        assert audit["seconds_by_rank"]["phase_a"] == [
            float(rank + 1) for rank in range(MPI.COMM_WORLD.size)
        ]
        assert audit["seconds_max"]["phase_b"] == pytest.approx(
            2 * (MPI.COMM_WORLD.size - 1) + 0.5
        )
        assert "diagnostic only" in audit["semantics"]


def test_reduction_setup_anatomy_includes_global_transfer_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = SimpleNamespace(comm=MPI.COMM_WORLD)
    entity_map = SimpleNamespace(
        mesh=mesh,
        active_rows=10,
        active_trace_rows=6,
    )
    degree_plan = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": True},
    )
    transfer = SimpleNamespace(audit={"pass": True})
    periodic = SimpleNamespace(audit={"pass": True})
    system = SimpleNamespace(
        build_audit={
            "phase_timings_seconds_by_rank": {"cell_loop": [0.1]},
            "compiled_builder_phase_timings_seconds_by_rank": {
                "raw_tensor_global_cache_outer_envelope": [0.1]
            },
        }
    )
    p6_space = SimpleNamespace(mesh=mesh)

    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "load_variable_p_cell_degree_plan",
        lambda *_args, **_kwargs: degree_plan,
    )
    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_periodic_constraint_map",
        lambda *_args, **_kwargs: periodic,
    )
    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_global_transfer",
        lambda *_args, **_kwargs: transfer,
    )
    monkeypatch.setattr(
        hcurl_variable_p_reduction,
        "build_variable_p_condensed_trace_system_from_compiled_form",
        lambda *_args, **_kwargs: system,
    )

    reduction = (
        hcurl_variable_p_reduction
        .build_variable_p_assembly_time_reduction(
            object(),
            p6_space,
            object(),
            degree_plan_path="synthetic-plan.json",
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
        )
    )
    anatomy = reduction.build_audit["setup_anatomy"]
    timing = anatomy["global_transfer"]

    assert anatomy["schema_version"] == (
        "task035e.variable-p-setup-anatomy.v1"
    )
    assert len(timing["seconds_by_rank"]) == MPI.COMM_WORLD.size
    assert all(value >= 0.0 for value in timing["seconds_by_rank"])
    assert timing["seconds_max"] == max(timing["seconds_by_rank"])
    assert "without an added barrier" in timing["semantics"]
    assert anatomy["timing_fields_are_diagnostic_only"] is True
    assert (
        system.build_audit["variable_p_reduction"]
        is reduction.build_audit
    )
