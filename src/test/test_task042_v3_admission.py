"""V3 spare-core admission must distinguish reservations from idle last PSR."""

from src.io import load_and_resolve
from src.runners.task042_shared import spare_cores


def test_sleeping_wide_threads_do_not_reserve_every_last_core():
    topology = [{"cpu": i, "siblings": [i]} for i in range(24)]
    neighbors = [
        {
            "threads": [
                {"tid": i + 100, "cpu": i, "affinity": list(range(24))}
                for i in range(24)
            ]
        }
    ]
    assert spare_cores(
        topology, neighbors, {}, {i + 100: 0 for i in range(24)}
    ) == list(range(24))
    assert (
        spare_cores(topology, neighbors, {}, {}) == []
    )  # unknown activity fails closed


def test_reserved_loader_affinity_busy_cpu_and_smt_sibling_excluded():
    topology = [{"cpu": i, "siblings": [i, i ^ 1]} for i in range(6)]
    neighbors = [{"threads": [{"tid": 1, "cpu": 0, "affinity": [0]}]}]
    assert spare_cores(topology, neighbors, {2: 0.8, 4: 0.0}, {1: 0}) == [4, 5]


def test_v3_inputs_are_distinct_optins_with_frozen_physics():
    original = load_and_resolve("input/task042_neural_coarse_inverse/f4_b0_shared.dat")
    for name in ("v3_reuse", "v3_overlap"):
        case = load_and_resolve(
            f"input/task042_neural_coarse_inverse/{name}_shared.dat"
        )
        assert case.physical_model_sha256 == original.physical_model_sha256
        assert case.solver["preconditioner"] != original.solver["preconditioner"]
        assert case.execution["terminate_memory_gib"] == 16.0
