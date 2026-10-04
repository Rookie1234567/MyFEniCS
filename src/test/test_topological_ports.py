"""Bounded affine entity/orientation witness, no volume assembly or solve."""

from src.geometry.fixed_phase_plan import fixture_design
from src.solvers.topological_port_trace import trace_qualification


def test_all_six_faces_p3_p4_p6_have_structural_zero_trace():
    record = trace_qualification(fixture_design())
    assert record["passed"]
    assert record["actual_557_558_562_are_interior"]
    assert not record["entry_magnitude_used_for_selection"]


def test_manufactured_p6_fixture_background_is_complete_reproducible_and_not_a_role_input():
    import numpy as np
    import pytest
    from src.solvers.fixed_phase_fem import build_model
    from src.solvers.fixed_phase_port_qualification import nonzero_fixture_background

    model = build_model(fixture_design(), 6, False, operators=False)
    field = nonzero_fixture_background(model).x.array
    assert np.array_equal(field, nonzero_fixture_background(model).x.array)
    mpc = model["floquet"].mpc
    coef, offsets = mpc.coefficients()
    for s in mpc.slaves:
        expected = np.dot(
            coef[offsets[s] : offsets[s + 1]], field[mpc.masters.links(int(s))]
        )
        assert abs(field[s] - expected) <= 1e-12
    assert (
        np.linalg.norm(
            field[
                model["space"].dofmap.list[
                    :, model["space"].element.basix_element.entity_dofs[3][0]
                ]
            ]
        )
        > 0
    )
    model["design"]["fixture"] = False
    with pytest.raises(ValueError, match="ONLY_FOR_ORDINARY_P6_FIXTURE"):
        nonzero_fixture_background(model)
