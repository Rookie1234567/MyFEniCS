"""Focused PETSc tests for the V4 exact-authority compatibility audit."""

from __future__ import annotations

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
from src.solvers.hybrid_exact_authority_compat import (
    V4_EXACT_AUTHORITY_FAILURE,
    V4_EXACT_AUTHORITY_LABELS,
    audit_exact_authority_petsc,
)


def test_v4_probe_identity_check_allows_random_without_resolved_column() -> None:
    expected = {
        "seed": 773,
        "source": "fixed_owner_range_formula",
        "rhs_identity_sha256": "a" * 64,
    }
    observed = {
        "label": "fixed_random_repeat_0",
        "seed": 773,
        "source": "fixed_owner_range_formula",
        "identity": {"global_sha256": "a" * 64},
    }
    check = level_a._v4_probe_identity_check(
        "fixed_random_repeat_0", expected, observed
    )
    assert check["pass"] is True
    assert "resolved_column" not in check["checks"]


def test_v4_canonical_active_row_identity_streams_keys_and_rejects_duplicate(
    monkeypatch,
) -> None:
    class FakeVec:
        def __init__(self):
            self.destroyed = False

        def set(self, _value):
            return None

        def assemble(self):
            return None

        def getOwnershipRange(self):
            return (0, 2)

        def destroy(self):
            self.destroyed = True

    class FakeCondensed:
        def __init__(self):
            self.vector = FakeVec()

        def create_active_vector(self):
            return self.vector

    class FakeSystem:
        def __init__(self):
            self.static_condensation = type(
                "Static", (), {"condensed": FakeCondensed()}
            )()
            self.V = object()
            self.floquet_data = object()

    class FakeMat:
        def getSize(self):
            return (2, 2)

    system = FakeSystem()
    keys = [("active_trace", 1), ("active_trace", 2)]
    monkeypatch.setattr(
        level_a,
        "iter_canonical_active_trace_packets",
        lambda *_args: ((key, 0.0j) for key in keys),
    )
    first = level_a._v4_canonical_active_key_identity(system, FakeMat(), MPI.COMM_SELF)
    second = level_a._v4_canonical_active_key_identity(system, FakeMat(), MPI.COMM_SELF)
    assert first["pass"] is True
    assert first["global_identity_sha256"] == second["global_identity_sha256"]
    assert first["summed_local_duplicate_count"] == 0
    assert first["numeric_allgather"] is False
    assert first["full_values_retained"] is False
    assert system.static_condensation.condensed.vector.destroyed is True

    monkeypatch.setattr(
        level_a,
        "iter_canonical_active_trace_packets",
        lambda *_args: ((keys[0], 0.0j), (keys[0], 0.0j)),
    )
    duplicate = level_a._v4_canonical_active_key_identity(
        system, FakeMat(), MPI.COMM_SELF
    )
    assert duplicate["pass"] is False
    assert duplicate["summed_local_duplicate_count"] == 1


def test_v4_canonical_active_row_identity_is_collective_for_uneven_ownership(
    monkeypatch,
) -> None:
    comm = MPI.COMM_WORLD
    rank = int(comm.rank)
    size = int(comm.size)
    local_count = 1 + int(rank == size - 1)
    local_start = sum(
        1 + int(previous_rank == size - 1) for previous_rank in range(rank)
    )
    local_end = local_start + local_count
    global_rows = size + 1

    class FakeVec:
        def set(self, _value):
            return None

        def assemble(self):
            return None

        def getOwnershipRange(self):
            return (local_start, local_end)

        def destroy(self):
            return None

    class FakeCondensed:
        def create_active_vector(self):
            return FakeVec()

    class FakeSystem:
        static_condensation = type("Static", (), {"condensed": FakeCondensed()})()
        V = object()
        floquet_data = object()

    class FakeMat:
        def getSize(self):
            return (global_rows, global_rows)

    local_keys = [("active_trace", index) for index in range(local_start, local_end)]
    monkeypatch.setattr(
        level_a,
        "iter_canonical_active_trace_packets",
        lambda *_args: ((key, 0.0j) for key in local_keys),
    )
    audit = level_a._v4_canonical_active_key_identity(FakeSystem(), FakeMat(), comm)
    ownership_counts = comm.allgather(local_count)
    assert audit["pass"] is True
    assert audit["global_key_count"] == global_rows
    assert sum(ownership_counts) == global_rows
    assert audit["global_duplicate_count"] == 0
    assert audit["ownership_contiguous"] is True
    assert audit["ownership_counts_match"] is None
    assert (
        audit["ownership_count_comparison"]
        == "not_applicable_canonical_packet_expansion"
    )
    assert audit["numeric_allgather"] is False
    assert audit["canonical_key_exchange"]["metadata_only"] is True
    assert all(
        record["local_key_count"]
        == record["ownership_range"][1] - record["ownership_range"][0]
        for record in audit["rank_records"]
    )

    if size > 1:
        duplicate_keys = list(local_keys)
        if rank == size - 1:
            duplicate_keys[0] = ("active_trace", 0)
        monkeypatch.setattr(
            level_a,
            "iter_canonical_active_trace_packets",
            lambda *_args: ((key, 0.0j) for key in duplicate_keys),
        )
        duplicate = level_a._v4_canonical_active_key_identity(
            FakeSystem(), FakeMat(), comm
        )
        assert duplicate["global_key_count"] == global_rows
        assert duplicate["global_duplicate_count"] > 0
        assert duplicate["pass"] is False


def _matrix(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=np.complex128)
    size = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for column in range(size):
            matrix.setValue(row, column, PETSc.ScalarType(values[row, column]))
    matrix.assemble()
    return matrix


def _vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


def _authority_data(matrix: PETSc.Mat, exact_values: np.ndarray):
    exact = _vector(matrix, exact_values)
    rhs = matrix.createVecLeft()
    matrix.mult(exact, rhs)
    rhs_vectors = {label: rhs.duplicate() for label in V4_EXACT_AUTHORITY_LABELS}
    exact_vectors = {label: exact.duplicate() for label in V4_EXACT_AUTHORITY_LABELS}
    for vector in rhs_vectors.values():
        rhs.copy(vector)
    for vector in exact_vectors.values():
        exact.copy(vector)
    metadata = {
        label: {"label": label, "kind": "tiny", "seed": index}
        for index, label in enumerate(V4_EXACT_AUTHORITY_LABELS)
    }
    identities = {
        label: f"{index:064x}" for index, label in enumerate(V4_EXACT_AUTHORITY_LABELS)
    }
    return exact, rhs, rhs_vectors, exact_vectors, metadata, identities


def _destroy_vectors(*groups) -> None:
    seen = set()
    for group in groups:
        for vector in group.values() if isinstance(group, dict) else group:
            if id(vector) not in seen:
                vector.destroy()
                seen.add(id(vector))


def test_exact_authority_bare_f_pass_and_identity_is_explicit_aij() -> None:
    values = np.asarray(
        [[2.0 + 0.2j, 0.3 - 0.1j], [0.4 + 0.5j, 1.7 - 0.3j]],
        dtype=np.complex128,
    )
    matrix = _matrix(values)
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        matrix, np.asarray([0.7 + 0.2j, -0.4 + 0.6j])
    )
    try:
        audit = audit_exact_authority_petsc(
            matrix,
            matrix,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "a" * 40},
            bare_matrix_hash=lambda _matrix: "f" * 64,
        )
        assert audit["gate_pass"] is True
        assert audit["classification"] != V4_EXACT_AUTHORITY_FAILURE
        assert all(
            row["bare_f"]["residual_relative"] <= 1.0e-12 for row in audit["reports"]
        )
        assert audit["operator_identity"]["bare_f"]["matrix_free"] is False
        assert audit["operator_identity"]["a_side"]["matrix_free"] is False
        assert audit["operator_identity"]["a_side"]["action_identity"] == (
            "system.A = F - C H^-1 D"
        )
        assert audit["operator_identity"]["bare_f"]["global_size"] == [2, 2]
        local_size = audit["operator_identity"]["bare_f"]["local_size"]
        ownership = audit["operator_identity"]["bare_f"]["ownership_range"]
        assert local_size[0] == ownership[1] - ownership[0]
        assert all(size >= 0 for size in local_size)
        assert audit["operator_identity"]["bare_f"]["block_size"] == 1
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        matrix.destroy()


def test_a_side_only_exact_is_not_bare_f_compatible() -> None:
    side_values = np.asarray(
        [[1.8 + 0.1j, 0.2], [0.1 - 0.3j, 1.4 + 0.2j]], dtype=np.complex128
    )
    bare_values = side_values + np.diag([0.4, -0.25]).astype(np.complex128)
    side = _matrix(side_values)
    bare = _matrix(bare_values)
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        side, np.asarray([0.2 + 0.5j, 1.1 - 0.4j])
    )
    try:
        audit = audit_exact_authority_petsc(
            bare,
            side,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "b" * 40},
            bare_matrix_hash=lambda matrix: "0" * 64 if matrix is bare else "1" * 64,
        )
        assert audit["classification"] == V4_EXACT_AUTHORITY_FAILURE
        assert audit["gate_pass"] is False
        assert (
            max(row["bare_f"]["residual_relative"] for row in audit["reports"]) > 1.0e-2
        )
        assert (
            max(
                row["a_side_explanatory"]["residual_relative"]
                for row in audit["reports"]
            )
            <= 1.0e-12
        )
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        bare.destroy()
        side.destroy()


def test_hash_change_or_nonrepeatable_operator_fails_gate() -> None:
    matrix = _matrix(np.asarray([[1.5 + 0.1j, 0.2], [0.0, 1.2 - 0.2j]]))
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        matrix, np.asarray([1.0 + 0.1j, 0.5 - 0.2j])
    )
    calls = {"count": 0}

    def changing_hash(_matrix: PETSc.Mat) -> str:
        calls["count"] += 1
        return f"{calls['count']:064x}"

    try:
        audit = audit_exact_authority_petsc(
            matrix,
            matrix,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "c" * 40},
            bare_matrix_hash=changing_hash,
        )
        assert audit["bare_f_hash_unchanged_pass"] is False
        assert audit["gate_pass"] is False
        assert audit["classification"] == V4_EXACT_AUTHORITY_FAILURE
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        matrix.destroy()


def test_v4_runner_returns_before_interface_mass_and_cleans_up(monkeypatch, tmp_path):
    class FakeSystem:
        inventory = {
            "matrix_free": True,
            "global_A_materialized": False,
            "direct_factor_count": 0,
        }

        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class FakeComponents:
        F = object()

    system = FakeSystem()
    components = FakeComponents()
    cleanup = {"components": False}

    def resource_callback():
        return {"pass": True}

    def fake_route(**kwargs):
        assert kwargs["system"] is system
        assert kwargs["bare_f"] is components.F
        assert kwargs["resource_callback"] is resource_callback
        return {
            "action": None,
            "owner": None,
            "result": {
                "schema": "task040.v4.exact_authority_compatibility.v1",
                "factor_inventory": {
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "cross_section_group_factor_count": 0,
                    "reduced_dense_factor_count": 0,
                },
            },
        }

    def fail_mass(*_args, **_kwargs):
        raise AssertionError("V4 compatibility route must precede interface mass")

    monkeypatch.setattr(
        level_a, "_build_research_explicit_side_components", lambda _system: components
    )
    monkeypatch.setattr(level_a, "_run_v4_exact_authority_compatibility", fake_route)
    monkeypatch.setattr(level_a, "audit_artificial_z_interface_support", fail_mass)
    monkeypatch.setattr(
        level_a, "assemble_reduced_artificial_interface_tangential_mass", fail_mass
    )
    monkeypatch.setattr(
        level_a,
        "_destroy_explicit_components",
        lambda _components: cleanup.__setitem__("components", True) or cleanup,
    )
    result = level_a.run_task040_level_a(
        object(),
        object(),
        exact_spool_root=tmp_path / "spool",
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        side_system_builder=lambda **_kwargs: system,
        v4_exact_authority_compatibility=True,
        resource_callback=resource_callback,
    )
    assert result["factor_inventory"]["full_side_exact_factor_count"] == 0
    assert result["factor_inventory"]["global_direct_factor_count"] == 0
    assert cleanup["components"] is True
    assert system.destroyed is True


def test_v4_plan_and_watchdog_contract(tmp_path):
    input_path = tmp_path / "input.dat"
    spool_path = tmp_path / "spool"
    run_path = tmp_path / "run"
    plan = level_a.build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=spool_path,
        run_directory=run_path,
        source_sha="a" * 40,
        v4_exact_authority_compatibility=True,
    )
    assert plan["schema"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA
    assert plan["method"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD
    assert (
        plan["profile"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID
    )
    assert plan["v4_exact_authority_compatibility"] is True
    assert plan["research_only"] is True
    assert plan["bare_f_compatibility"] is True
    assert plan["read_only_exact_outputs"] is True
    assert plan["qep_calls"] == 0
    assert plan["pde_solve"] == "not_run"
    assert "outer_ksp" in plan["forbidden"]
    assert len(plan["forbidden"]) == len(set(plan["forbidden"]))

    watchdog_plan = watchdog.build_task040_level_a_watchdog_plan(
        input_path=input_path,
        exact_spool_root=spool_path,
        run_directory=tmp_path / "watchdog-run",
        source_sha="b" * 40,
        v4_exact_authority_compatibility=True,
    )
    argv = watchdog_plan["worker_argv"]
    assert argv.count(level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG) == 1
    assert level_a.TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG not in argv
    assert level_a.TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG not in argv
    assert watchdog_plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert watchdog_plan["watchdog"]["swap_limit_bytes"] == 0
