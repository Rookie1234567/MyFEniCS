from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from mpi4py import MPI

from src.common.config_3d import SimulationConfig3D
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import build_owner_local_slab_plan
from src.solvers.static_lor_hcurl_slab_oracle import (
    build_physical_lor_hcurl_slab_oracle,
)
from src.solvers.static_lor_hcurl_transfer import (
    build_lor_slab_edge_space,
    build_owner_local_lor_transfer,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture
from src.test.test_260_task037_extra_owner_lor_transfer import (
    _empty_floquet,
    _packing_records,
)


_TOLERANCE = 1.0e-12


def _config() -> SimulationConfig3D:
    return SimulationConfig3D(
        lambda0=13.5,
        n_air=1.0 + 0.0j,
        n_substrate=1.45 + 0.03j,
        n_grating=2.1 + 0.07j,
        divergence_penalty=0.0,
        stage4_boundary_model="dtn_port",
    )


@pytest.fixture(scope="module")
def real_case():
    mesh, cell_tags, function_space, compiled = _build_fixture(MPI.COMM_SELF)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        retain_fullspace_slab_blocks_for_research=True,
    )
    try:
        plan = build_owner_local_slab_plan(
            condensed,
            mesh,
            domain_z=(0.0, 1.0),
            num_slabs=3,
            overlap_fraction=0.0,
        )
        records, cells, owner_rows, _recoveries, _collector_audit = (
            _packing_records(
                condensed,
                mesh,
                cell_tags,
                plan,
                0,
            )
        )
        topologies = [record.topology for record in records]
        edge_space = build_lor_slab_edge_space(
            topologies,
            _empty_floquet(2),
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
        )
        transfer = build_owner_local_lor_transfer(
            records,
            edge_space,
            owner_rows,
        )
        oracle = build_physical_lor_hcurl_slab_oracle(
            transfer,
            topologies,
            _config(),
        )
        yield oracle, transfer, topologies, _config()
    finally:
        condensed.destroy()


def _reference_trace(oracle, rhs: np.ndarray, two: bool) -> np.ndarray:
    transfer = oracle.transfer
    trace_offset = int(transfer.audit["trace_offset"])
    full_rhs = np.zeros(int(transfer.audit["full_rows"]), dtype=np.complex128)
    full_rhs[trace_offset:] = rhs
    active_rhs = transfer.apply_adjoint(full_rhs)
    active_correction = (
        oracle.hcurl_vcycle.apply_two(active_rhs)
        if two
        else oracle.hcurl_vcycle.apply_one(active_rhs)
    )
    full_correction = transfer.apply(active_correction)
    return np.array(full_correction[trace_offset:], copy=True)


def _relative(first: np.ndarray, second: np.ndarray) -> float:
    return float(
        np.linalg.norm(first - second)
        / max(float(np.linalg.norm(second)), np.finfo(float).tiny)
    )


def test_physical_trace_oracle_matches_independent_lift_and_audit(real_case):
    oracle, transfer, topologies, cfg = real_case
    trace_rows = int(transfer.audit["trace_rows"])
    rng = np.random.default_rng(2690)
    rhs = rng.normal(size=trace_rows) + 1j * rng.normal(size=trace_rows)
    other = rng.normal(size=trace_rows) + 1j * rng.normal(size=trace_rows)

    expected_one = _reference_trace(oracle, rhs, False)
    expected_two = _reference_trace(oracle, rhs, True)
    assert _relative(oracle.apply_one_trace(rhs), expected_one) <= _TOLERANCE
    assert _relative(oracle.apply_two_trace(rhs), expected_two) <= _TOLERANCE
    assert np.array_equal(
        oracle.apply_one_trace(rhs), oracle.apply_one_trace(rhs)
    )
    assert np.array_equal(
        oracle.apply_two_trace(rhs), oracle.apply_two_trace(rhs)
    )
    alpha = 0.23 - 0.17j
    beta = -0.31 + 0.29j
    assert _relative(
        oracle.apply_one_trace(alpha * rhs + beta * other),
        alpha * oracle.apply_one_trace(rhs)
        + beta * oracle.apply_one_trace(other),
    ) <= _TOLERANCE

    full_rhs = np.zeros(int(transfer.audit["full_rows"]), dtype=np.complex128)
    full_rhs[int(transfer.audit["trace_offset"]) :] = rhs
    assert np.count_nonzero(full_rhs[: int(transfer.audit["trace_offset"])]) == 0
    assert oracle.audit["parent_topologies_retained"] is False
    assert "parent_topologies" not in vars(oracle)
    assert "proxy" not in vars(oracle)
    assert "hx" not in vars(oracle)
    assert "scratch" not in vars(oracle)
    assert oracle.transfer is transfer
    assert oracle.audit["present_material_tags"] == [cfg.tags.air]
    assert oracle.audit["curl_coefficient"] == [1.0, 0.0]
    expected_mass = -cfg.k0**2 * cfg.eps_air
    assert np.allclose(
        oracle.audit["mass_coefficient_by_tag"][str(cfg.tags.air)],
        [expected_mass.real, expected_mass.imag],
        rtol=0.0,
        atol=0.0,
    )
    assert oracle.audit["volume_proxy_only"] is True
    assert oracle.audit["dtn_surface_in_proxy"] is False
    assert oracle.audit["literal_p6_shift_galerkin"] is False
    assert oracle.audit["zero_interior_trace_lift"] is True
    assert oracle.audit["factor_count"] == 2
    assert oracle.audit["coarsest_factor_count"] == 2
    assert oracle.audit["fine_p6_trace_factor_count"] == 0
    assert oracle.audit["fine_p6_full_factor_count"] == 0
    assert oracle.audit["large_lor_factor_count"] == 0
    assert oracle.audit["fine_intermediate_factor_count"] == 0
    assert oracle.audit["coarsest_only"] is True
    assert oracle.audit["global_dense"] is False
    assert oracle.audit["exact_outer_changed"] is False
    assert oracle.audit["contraction_not_evaluated"] is True
    assert oracle.audit["transfer_retained_numeric_payload_lower_bound_bytes"] == (
        transfer.audit["retained_numeric_payload_lower_bound_bytes"]
    )
    assert oracle.audit["d2c_retained_numeric_payload_lower_bound_bytes"] == (
        oracle.hcurl_vcycle.audit["retained_numeric_payload_lower_bound_bytes"]
    )
    assert oracle.audit["retained_numeric_payload_lower_bound_bytes"] == (
        oracle.audit["transfer_retained_numeric_payload_lower_bound_bytes"]
        + oracle.audit["d2c_retained_numeric_payload_lower_bound_bytes"]
    )
    assert topologies[0].canonical_cell_id in transfer.audit["parent_ids"]


def test_physical_trace_oracle_rejects_divergence_penalty(real_case):
    oracle, transfer, topologies, cfg = real_case
    del oracle
    with pytest.raises(ValueError):
        build_physical_lor_hcurl_slab_oracle(
            transfer,
            topologies,
            replace(cfg, divergence_penalty=1.0),
        )


@pytest.mark.parametrize("bad_tag", (999, 4))
def test_physical_trace_oracle_rejects_unknown_or_pml_tag(real_case, bad_tag):
    oracle, transfer, topologies, cfg = real_case
    del oracle
    bad_topologies = [
        replace(topologies[0], material_tag=int(bad_tag)),
        *topologies[1:],
    ]
    with pytest.raises(NotImplementedError):
        build_physical_lor_hcurl_slab_oracle(
            transfer,
            bad_topologies,
            cfg,
        )
