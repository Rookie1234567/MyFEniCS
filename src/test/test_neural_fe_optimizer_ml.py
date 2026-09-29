"""CPU ML test; uses no physical target, FE runtime, or reference solution."""

from src.solvers.neural_fe_optimization import optimize_route
from src.test.test_neural_fe_action_packet import witness


def test_frozen_optimizer_budget_has_no_gradient_success_exit(tmp_path):
    packet = witness()[0]
    result = optimize_route({}, packet, None, "FREE-FE-OPT", tmp_path)
    assert result["counts"]["closures"] == 2000
    assert result["counts"]["adam_updates"] == 500
    assert result["stop_reason"] == "CLOSURE_BUDGET"
    assert result["reference_loaded"] is False
    assert result["global_FE_matrix"] is False
    assert (
        abs(
            sum(result["costs_exclusive_seconds"].values())
            - result["route_wall_seconds"]
        )
        < 1e-6
    )
