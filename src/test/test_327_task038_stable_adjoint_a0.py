"""Pure A0 stable-adjoint, shard-merge, and checker contract tests."""

from __future__ import annotations

import math

import numpy as np

from benchmarks import run_task038_full3d_interlevel_spectral as runner
from benchmarks import task038_full3d_interlevel_spectral_checker as checker
from src.solvers import fullspace_lor_interlevel_spectral_dolfinx as adapter
from src.solvers.fullspace_lor_stable_adjoint import audit_stable_adjoint


def _probe_arrays(
    name: str, indices: np.ndarray | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    roles = checker._a0_roles(name)
    indices = np.arange(3, dtype=np.int64) if indices is None else indices
    source_full = np.asarray([1.0 + 1.0j, 2.0 - 1.0j, 3.0 + 0.0j], dtype=np.complex128)
    source2_full = np.asarray([2.0 - 1.0j, -1.0 + 2.0j, 1.0 + 3.0j], dtype=np.complex128)
    source = source_full[indices].copy()
    source2 = source2_full[indices].copy()
    projected_combo = (0.37 + 0.19j) * source + (-0.23 + 0.41j) * source2
    fine_ids = np.asarray([10, 20, 30], dtype=np.uint32)[indices]
    coarse_ids = np.asarray([1, 2, 3], dtype=np.uint32)[indices]
    values: dict[str, np.ndarray] = {}
    for role, value in {
        "source_before": source, "source_after": source, "source2": source2,
        "projected": source, "projected_repeat": source, "projected2": source2,
        "projected_combo": projected_combo, "fine_dual": source, "adjoint": source,
        "b3": source, "b6p": source,
        "fine_primal_local": source, "fine_dual_local": source,
        "coarse_source_local": source, "explicit_adjoint_local": source,
        "implemented_adjoint_local": source, "implemented_adjoint_owner": source,
    }.items():
        values[roles[role]] = np.asarray(value, dtype=np.complex128)
    for role in (
        "fine_primal_local_ids", "fine_dual_local_ids",
        "coarse_source_local_ids", "explicit_adjoint_local_ids",
        "implemented_adjoint_local_ids", "implemented_adjoint_owner_ids",
    ):
        values[roles[role]] = (fine_ids if role.startswith("fine") else coarse_ids).copy()
    terms = np.conjugate(source) * source
    gamma = float(3 * np.finfo(float).eps / (1.0 - 3 * np.finfo(float).eps))
    facts = {
        "name": name, "raw_roles": roles,
        "source_generation": checker.SOURCE_GENERATION[name],
        "source_before_digest": checker._digest(source),
        "source_after_digest": checker._digest(source),
        "source_norm": float(np.linalg.norm(source)),
        "source_finite": True, "source_nonzero": True,
        "q": 1.0, "q_imag_defect": 0.0, "energy_imag_defect": 0.0,
        "energy_coarse": [float(np.vdot(source, source).real), 0.0],
        "energy_fine": [float(np.vdot(source, source).real), 0.0],
        "adjoint_work_relative": 0.0, "linearity_relative": 0.0,
        "repeat_relative": 0.0, "finite": True, "input_unchanged": True,
        "phase_once": True,
        "stable_adjoint": {
            "schema": "task038.full3d.interlevel-stable-adjoint.a0.v1",
            "scope": "per_rank_canonical_packets; checker_global_authority",
            "vector_norm_reduction": "checker_global_sum_of_squares_by_key",
            "pairwise_vs_compensated_relative": 0.0,
            "compensated_work_relative": 0.0,
            "vector_adjoint_relative": 0.0,
            "ordinary_abs_work_defect": 0.0,
            "forward_error_bound_abs": (
                gamma * math.fsum(abs(value) for value in terms)
                + gamma * math.fsum(abs(value) for value in terms)
            ),
            "canonical_owner_count": int(source.size),
        },
    }
    return values, facts


def _probe_shards(
    name: str, mpi_size: int,
) -> tuple[dict[str, object], list[tuple[int, dict[str, np.ndarray]]]]:
    shards: list[tuple[int, dict[str, np.ndarray]]] = []
    facts: dict[str, object] | None = None
    for rank in range(mpi_size):
        indices = np.arange(3, dtype=np.int64) if mpi_size == 1 else (
            np.asarray([0, 1], dtype=np.int64) if rank == 0
            else np.asarray([2], dtype=np.int64)
        )
        arrays, rank_facts = _probe_arrays(name, indices)
        if facts is None:
            facts = rank_facts
        shards.append((rank, arrays))
    assert facts is not None
    return facts, shards


def test_stable_core_and_independent_local_adjoint() -> None:
    source = np.asarray([1.0 + 0.0j, 2.0 + 0.0j, 3.0 + 0.0j], dtype=np.complex128)
    ids = np.asarray([1, 2, 3], dtype=np.uint32)
    facts = audit_stable_adjoint(
        coarse_source=source, fine_primal=source, fine_dual=source,
        implemented_adjoint=source, explicit_adjoint=None,
        lhs_owner=(ids, source, source),
        rhs_owner=(ids, source, source, source),
    )
    assert facts["vector_adjoint_relative"] == 0.0
    assert facts["ordinary_abs_work_defect"] == 0.0
    assert facts["finite"] is True
    assert facts["lhs_term_count"] == 3
    assert facts["rhs_term_count"] == 3
    assert "lhs" not in facts and "rhs" not in facts

    class Topology:
        unique_edge_ids = np.asarray([10, 20], dtype=np.uint32)
        cell_edge_ids = np.asarray([[20, 10]], dtype=np.uint32)
        cell_orientation = np.asarray([[1.0 + 0.0j, -1.0 + 0.0j]])
        cell_phase_codes = np.asarray([[0, 1]], dtype=np.int32)
        phase_values = np.asarray(
            [1.0 + 0.0j, 0.5 + 0.5j], dtype=np.complex128
        )

    class Level:
        parent_block_count = 1
        parent_topology = Topology()

        def dual_to_owner(self, _source):
            return self.parent_topology.unique_edge_ids, np.asarray([2.0 + 0.0j, 3.0 + 0.0j])

        def expand_dual(self, packet, _start, _stop):
            return [np.asarray([packet[1][1], packet[1][0]], dtype=np.complex128)]

    class Transfer:
        class Local:
            edge_transfer = np.asarray(
                [[1.0 + 1.0j, 2.0 - 0.5j],
                 [0.5 + 2.0j, -1.0 + 0.25j]],
                dtype=np.complex128,
            )

        local_transfer = Local()

    class Extension:
        levels = (Level(), Level())
        _transfer = Transfer()

        def route_dual_blocks(self, *_args):
            raise AssertionError("independent audit called production route")

        def apply_adjoint(self, *_args):
            raise AssertionError("independent audit called production apply")

    ids_out, values_out = adapter._apply_local_adjoint_audit_only(
        Extension(), (6, 3), np.asarray([4.0 + 0.0j, 5.0 + 0.0j])
    )
    expected_local = np.asarray([3.0 + 0.0j, 2.0 + 0.0j]) @ np.conjugate(
        Transfer.Local.edge_transfer
    )
    expected_by_key = np.asarray(
        [expected_local[1] * (-1.0 + 0.0j) / (0.5 + 0.5j), expected_local[0]],
        dtype=np.complex128,
    )
    assert np.array_equal(ids_out, np.asarray([10, 20], dtype=np.uint32))
    np.testing.assert_array_equal(values_out, expected_by_key)


def test_a0_shard_merge_cross_mpi_and_runner_authority_shape() -> None:
    assert "_jsonable" in runner.run_a0_worker.__code__.co_cellvars
    assert tuple(checker.PROBE_NAMES) == (
        "random", "gradient", "curl", "checkerboard",
        "physical_component_derived", "r3_long_tail_derived",
    )
    for name in checker.PROBE_NAMES:
        facts1, shards1 = _probe_shards(name, 1)
        facts2, shards2 = _probe_shards(name, 2)
        errors1: list[str] = []
        gates1: list[str] = []
        errors2: list[str] = []
        gates2: list[str] = []
        result1 = checker._a0_check_probe(name, facts1, shards1, errors1, gates1, 1)
        result2 = checker._a0_check_probe(name, facts2, shards2, errors2, gates2, 2)
        assert errors1 == [] and gates1 == []
        assert errors2 == [] and gates2 == []
        assert checker._a0_key_relative(
            result1["_canonical_ids"], result1["_implemented_values"],
            result2["_canonical_ids"], result2["_implemented_values"],
        ) <= 1.0e-11
        assert checker._a0_key_relative(
            result1["_canonical_ids"], result1["_explicit_values"],
            result2["_canonical_ids"], result2["_explicit_values"],
        ) <= 1.0e-11
    large = 1.0e6 + 2.0e6j
    assert checker._a0_relative(large, large * (1.0 + 5.0e-13)) <= 1.0e-11
    command = ["/qualified/bin/python", "-m", "benchmarks.run_task038_full3d_interlevel_spectral"]
    assert checker._watchdog_command_validation(command, command, 1, a0=True) == (True, "direct")
    mpi2_command = ["/usr/bin/mpiexec", "-n", "2", *command]
    assert checker._watchdog_command_validation(mpi2_command, command, 2, a0=True) == (True, "mpiexec_n2")
    assert checker._watchdog_command_validation(
        ["/usr/bin/mpirun", "-n", "2", *command], command, 2, a0=True
    ) == (False, "invalid")
    assert checker._watchdog_command_validation(
        ["mpiexec", "-n", "2", *command], command, 2, a0=True
    ) == (False, "invalid")
    assert checker._watchdog_command_validation(
        ["/usr/bin/mpiexec", "-n", "3", *command], command, 2, a0=True
    ) == (False, "invalid")

    case_names = (
        "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
        "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
        "pcgamg_hierarchy_built", "physical_solve", "recovery",
    )
    extension_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "p1_built", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    case_audit = {
        name: False for name in case_names if name not in ("physical_solve", "recovery")
    }
    case_audit.update({
        "physical_action": {"pde_solved": False},
        "recovery_field_arrays_built": False,
        "global_transfer_matrix": False,
    })
    normalized_case = runner._a0_case_architecture(case_audit)
    assert normalized_case["physical_solve"] is False
    assert normalized_case["recovery"] is False
    forbidden = runner._forbidden_architecture(
        normalized_case,
        {name: False for name in extension_names},
    )
    assert all(value is False for value in forbidden.values())
    assert "case.global_dense_transfer" in forbidden and "extension.p1_built" in forbidden
    groups = [
        {
            "schema": "inventory", "exact_float64_identity": True,
            "numeric_allgather": False, "cell_count_global": 2,
            "cell_count_local": 1, "class_inventory_by_rank": [["a"], ["b"]],
            "classes": [{"class_digest": "a", "class_identity": {}, "tag": 1,
                         "material_role": "air", "cell_count_local": 1}],
        },
        {
            "schema": "inventory", "exact_float64_identity": True,
            "numeric_allgather": False, "cell_count_global": 2,
            "cell_count_local": 1, "class_inventory_by_rank": [["a"], ["b"]],
            "classes": [{"class_digest": "b", "class_identity": {}, "tag": 2,
                         "material_role": "substrate", "cell_count_local": 1}],
        },
    ]
    inventory = runner._a0_merge_inventory_groups(groups)
    assert inventory["class_inventory_by_rank"] == [["a"], ["b"]]
    assert all(isinstance(items, list) and all(isinstance(item, str) for item in items)
               for items in inventory["class_inventory_by_rank"])


def test_a0_raw_mutation_is_a_gate_not_a_contract_mismatch() -> None:
    facts, shards = _probe_shards("random", 1)
    _rank, original = shards[0]
    mutated = {key: value.copy() for key, value in original.items()}
    owner_key = checker._a0_roles("random")["implemented_adjoint_owner"]
    mutated[owner_key][0] += 1.0
    audit_facts = {
        "name": "random", "raw_roles": checker._a0_roles("random"),
        "source_generation": checker.SOURCE_GENERATION["random"],
    }
    errors: list[str] = []
    gates: list[str] = []
    checker._a0_check_probe("random", audit_facts, [(0, mutated)], errors, gates, 2)
    assert errors == []
    assert any("vector_adjoint" in item or "compensated_work" in item for item in gates)
