"""Bounded affine entity/orientation witness, no volume assembly or solve."""

from src.geometry.fixed_phase_plan import fixture_design
from src.solvers.topological_port_trace import trace_qualification


def test_all_six_faces_p3_p4_p6_have_structural_zero_trace():
    record = trace_qualification(fixture_design())
    assert record["passed"]
    assert record["actual_557_558_562_are_interior"]
    assert not record["entry_magnitude_used_for_selection"]
