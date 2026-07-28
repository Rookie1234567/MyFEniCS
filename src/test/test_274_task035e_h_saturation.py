from __future__ import annotations

import hashlib
import os

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.task035e_h_saturation import (
    FORMAL_GOAL_COUNT,
    PRODUCTION_MAXIMUM_LEVEL,
    SHADOW_MAXIMUM_LEVEL,
    build_level3_h_saturation_catalog,
    build_level3_h_saturation_patch,
    evaluate_level3_h_saturation_local_lower_bound,
    materialize_level3_h_saturation_constraints,
)
from src.adaptivity.task035e_hp_transition import (
    build_initial_hp_transition_state,
)


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"
_ALGORITHM_SHA = hashlib.sha256(b"task035e-h-saturation-test").hexdigest()


@pytest.fixture(scope="module")
def multilevel_state():
    forest = build_root_dyadic_hexa_forest(
        ((0.0, 0.0, 0.0, 1.0, 1.0, 1.0),),
        (1,),
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    root = DyadicHexKey(0, 0, 0, 0, 0)
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        (root,),
        maximum_level=PRODUCTION_MAXIMUM_LEVEL,
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        (DyadicHexKey(0, 1, 0, 0, 0),),
        maximum_level=PRODUCTION_MAXIMUM_LEVEL,
    )
    degrees = {cell.key: 4 for cell in forest.leaves}
    return build_initial_hp_transition_state(
        forest,
        degrees,
        source_sha=_SOURCE_SHA,
        algorithm_sha256=_ALGORITHM_SHA,
    )


@pytest.fixture(scope="module")
def shadow_patch(multilevel_state):
    catalog = build_level3_h_saturation_catalog(multilevel_state)
    periodic = next(
        orbit
        for orbit in catalog.periodic_orbits
        if len(orbit.leaf_keys) > 1
    )
    return build_level3_h_saturation_patch(
        multilevel_state,
        catalog,
        orbit_id=periodic.orbit_id,
    )


def test_level_two_leaves_are_partitioned_into_periodic_orbits(
    multilevel_state,
) -> None:
    catalog = build_level3_h_saturation_catalog(multilevel_state)
    flattened = tuple(
        key
        for orbit in catalog.periodic_orbits
        for key in orbit.leaf_keys
    )

    assert set(flattened) == set(catalog.level_two_leaf_keys)
    assert len(flattened) == len(set(flattened))
    assert any(len(orbit.leaf_keys) == 4 for orbit in catalog.periodic_orbits)
    assert catalog.audit["structural_catalog_pass"] is True
    assert catalog.audit["formal_h_saturation_status"] == "unknown"
    assert catalog.audit["measured_pass"] is False
    assert catalog.audit["production_level_three_selectable"] is False
    assert catalog.audit["production_level_three_rows_numbered"] is False


def test_selected_orbit_builds_true_level_three_shadow_only_geometry(
    multilevel_state,
    shadow_patch,
) -> None:
    assert all(
        key.level == PRODUCTION_MAXIMUM_LEVEL
        for key in shadow_patch.requested_split_keys
    )
    assert shadow_patch.level_three_leaf_keys
    assert max(
        cell.key.level for cell in shadow_patch.forest.leaves
    ) == SHADOW_MAXIMUM_LEVEL
    assert shadow_patch.audit["true_dyadic_level_three_children"] is True
    assert shadow_patch.audit["strong_2_to_1_balance"] is True
    assert all(
        row["matching"]
        for row in shadow_patch.audit["periodic_boundary_audit"].values()
    )
    assert shadow_patch.audit["production_plan_mutated"] is False
    assert shadow_patch.audit["production_level_three_selectable"] is False
    assert shadow_patch.audit["production_level_three_rows_numbered"] is False
    assert shadow_patch.audit["formal_h_saturation_status"] == "unknown"
    assert shadow_patch.audit["measured_pass"] is False
    assert set(shadow_patch.cell_degree_by_key.values()) == {4}
    assert multilevel_state.forest.audit["leaf_catalog_sha256"] == (
        shadow_patch.audit["production_leaf_catalog_sha256"]
    )
    assert max(
        cell.key.level for cell in multilevel_state.forest.leaves
    ) == PRODUCTION_MAXIMUM_LEVEL


@pytest.fixture(scope="module")
def constraint_evidence(shadow_patch):
    return materialize_level3_h_saturation_constraints(
        shadow_patch,
        phase_x=np.exp(0.17j),
        phase_y=np.exp(-0.23j),
        comm=MPI.COMM_SELF,
    )


def test_level_three_patch_materializes_actual_shadow_constraints(
    shadow_patch,
    constraint_evidence,
) -> None:
    audit = constraint_evidence.audit
    assert audit["structural_constraint_pass"] is True
    assert audit["hanging_constraints_complete"] is True
    assert audit["periodic_cycle_closure"] is True
    assert audit["variable_trace_opt_in"] is True
    assert audit["shadow_only"] is True
    assert audit["production_rows_numbered"] is False
    assert audit["formal_h_saturation_status"] == "unknown"
    assert audit["measured_pass"] is False
    assert audit["patch_sha256"] == shadow_patch.audit["patch_sha256"]


def test_local_schur_and_59_goal_dwr_is_only_a_lower_bound(
    shadow_patch,
    constraint_evidence,
) -> None:
    rng = np.random.default_rng(274)
    size = 8
    raw = rng.normal(size=(size, size)) + 1j * rng.normal(
        size=(size, size)
    )
    matrix = raw.conj().T @ raw + 2.0 * np.eye(size)
    rhs = rng.normal(size=size) + 1j * rng.normal(size=size)
    embedding = rng.normal(size=(size, 3)) + 1j * rng.normal(
        size=(size, 3)
    )
    coefficients = rng.normal(size=3) + 1j * rng.normal(size=3)
    gradients = rng.normal(size=(FORMAL_GOAL_COUNT, size)) + 1j * (
        rng.normal(size=(FORMAL_GOAL_COUNT, size))
    )
    result = evaluate_level3_h_saturation_local_lower_bound(
        shadow_patch,
        constraint_evidence,
        goal_ids=tuple(
            f"task035e.goal.{index:02d}"
            for index in range(FORMAL_GOAL_COUNT)
        ),
        shadow_matrix=matrix,
        shadow_rhs=rhs,
        production_embedding=embedding,
        production_coefficients=coefficients,
        goal_gradients=gradients,
        trace_dofs=(0, 2, 4, 6),
        interior_dofs=(1, 3, 5, 7),
    )

    assert len(result.goals) == FORMAL_GOAL_COUNT
    assert result.trace_schur.shape == (4, 4)
    assert result.audit["local_algebra_pass"] is True
    assert result.audit["actual_patch_local_tensor_consumed"] is True
    assert result.audit["actual_patch_local_adjoints_solved"] is True
    assert result.audit["global_shadow_coupling_included"] is False
    assert result.audit["formal_h_saturation_status"] == "unknown"
    assert result.audit["measured_pass"] is False
    assert result.audit["freezing_credit"] is False
    assert result.audit["maximum_dwr_endpoint_difference"] <= 5.0e-10


def test_saturation_rejects_an_incomplete_degree_map(
    multilevel_state,
) -> None:
    degrees = dict(multilevel_state.cell_degree_by_key)
    degrees.pop(next(iter(degrees)))
    broken = type(multilevel_state)(
        forest=multilevel_state.forest,
        cell_degree_by_key=degrees,
        source_sha=multilevel_state.source_sha,
        algorithm_sha256=multilevel_state.algorithm_sha256,
        cycle_index=multilevel_state.cycle_index,
        stage_action_sha256s=multilevel_state.stage_action_sha256s,
        audit=multilevel_state.audit,
    )

    with pytest.raises(ValueError, match="one degree for every leaf"):
        build_level3_h_saturation_catalog(broken)


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035E_H_SATURATION_MPI8") != "1",
    reason="set the Task035e h-saturation MPI8 component opt-in",
)
def test_level_three_shadow_constraint_identity_is_mpi8_stable(
    shadow_patch,
) -> None:
    if MPI.COMM_WORLD.size != 8:
        pytest.skip("Task035e h-saturation MPI component requires MPI8")
    evidence = materialize_level3_h_saturation_constraints(
        shadow_patch,
        phase_x=np.exp(0.17j),
        phase_y=np.exp(-0.23j),
        comm=MPI.COMM_WORLD,
    )
    packets = MPI.COMM_WORLD.allgather(
        evidence.audit["constraint_evidence_sha256"]
    )

    assert len(set(packets)) == 1
