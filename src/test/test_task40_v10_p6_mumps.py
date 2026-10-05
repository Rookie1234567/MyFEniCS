from __future__ import annotations

import ctypes
import ctypes.util
import os

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE
from src.solvers.task40_v10_p6_mumps import AllQExactMumps


def test_task40_v10_p6_profile_inventory_arithmetic():
    p = TASK40_V10_P6_PROFILE
    assert p.global_independent_rows == p.global_interior_rows + p.global_trace_rows
    assert p.global_independent_rows == p.q_count * p.rows_per_q
    assert p.global_trace_rows == p.q_count * p.trace_rows_per_q
    assert p.local_independent_rows == p.local_interior_rows + p.local_trace_rows
    assert p.local_independent_rows == p.replication_count * p.local_width_per_q
    assert p.augmented_rows_per_q == (4324, 4400, 4400, 4400)
    good = {"degree": 6, "global_cell_count": 80, "global_storage_rows": 55950,
            "global_independent_rows": 52992, "global_interior_rows": 36000,
            "global_trace_rows": 16992, "q_count": 4, "rows_per_q": 13248,
            "trace_rows_per_q": 4248, "local_cell_count": 40,
            "local_storage_rows": 28722, "local_independent_rows": 26496,
            "local_interior_rows": 18000, "local_trace_rows": 8496,
            "local_width_per_q": 13248, "q_port_count_0": 76,
            "q_port_count_1": 152, "q_port_count_2": 152, "q_port_count_3": 152}
    assert p.validate_runtime_inventory(good)["status"] == "RUNTIME_INVENTORY_MATCH"
    bad = dict(good, degree=4)
    with pytest.raises(ValueError, match="inventory mismatch"):
        p.validate_runtime_inventory(bad)


def test_petsc_api_binds_loaded_petsc4py_runtime_even_if_system_discovery_is_wrong(monkeypatch):
    from petsc4py import PETSc
    from src.solvers.fullspace_v17_p3_oracle import _load_petsc_api

    monkeypatch.setattr(ctypes.util, "find_library", lambda _name: "libpetsc_complex.so.3.19")
    api = _load_petsc_api()
    assert api._task40_petsc_api_binding_path == os.path.realpath(PETSc.__file__)
    assert api._task40_petsc_api_runtime_version == tuple(PETSc.Sys.getVersion())
    get_version = api.PetscGetVersion
    get_version.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    buffer = ctypes.create_string_buffer(512)
    assert get_version(buffer, len(buffer)) == 0
    assert str(PETSc.Sys.getVersion()[0]) in buffer.value.decode("ascii")


def test_all_four_exact_mumps_factors_and_repeated_solve():
    matrices = {
        q: sparse.csr_matrix(np.array([
            [4.0+0.2j, 1.0-0.1j, 0.0],
            [0.5+0.3j, 3.5+0.4j, 0.2-0.1j],
            [0.0, 0.7+0.2j, 2.5-0.3j],
        ], dtype=np.complex128) + q*np.eye(3))
        for q in range(4)
    }
    before = {q: (m.data.copy(), m.indices.copy(), m.indptr.copy()) for q, m in matrices.items()}
    gates = []
    with AllQExactMumps(matrices, allocation_gate=lambda name, facts: gates.append((name, facts)),
                        expected_shapes=(3, 3, 3, 3)) as factors:
        assert factors.audit["all_four_factors_retained_simultaneously"] is True
        assert factors.audit["all_four_numeric_factors_true_residual_passed"] is True
        assert factors.audit["all_four_factor_objects_live_simultaneously"] is True
        assert factors.audit["factors_live_count_current"] == 4
        assert factors.audit["max_simultaneous_factors"] == 4
        rhs = np.array([1+0.5j, -0.2+0.8j, 0.7-0.1j], dtype=np.complex128)
        for q in range(4):
            x = factors.solve(q, rhs)
            assert np.linalg.norm(matrices[q]@x-rhs)/np.linalg.norm(rhs) < 1e-10
        assert factors.calls == 4
    assert factors.audit["all_four_factors_retained_simultaneously"] is True
    assert factors.audit["factors_live_count_current"] == 0
    assert factors.audit["max_simultaneous_factors"] == 4
    assert len(gates) == 13
    symbolic_gates = [facts for name, facts in gates if name == "after_mumps_symbolic_before_numeric"]
    assert [facts["retained_factor_count"] for facts in symbolic_gates] == [1, 2, 3, 4]
    assert all("current_symbolic_mumps_info_raw" in facts for facts in symbolic_gates)
    numeric_admission = [
        (index, facts)
        for index, (name, facts) in enumerate(gates)
        if name == "all_q_symbolic_before_any_numeric"
    ]
    numeric_observations = [
        index for index, (name, _facts) in enumerate(gates)
        if name == "after_mumps_numeric_true_residual"
    ]
    assert len(numeric_admission) == 1
    assert numeric_admission[0][1]["all_four_symbolic_q_completed"] is True
    assert len(numeric_admission[0][1]["q_symbolic_estimates_bytes"]) == 4
    assert max(index for index, (name, _facts) in enumerate(gates)
               if name == "after_mumps_symbolic_before_numeric") < min(numeric_observations)
    assert all(index > numeric_admission[0][0] for index in numeric_observations)
    assert all(facts["csr_to_petsc_conversion_workspace_peak_bytes"] > 0 for facts in symbolic_gates)
    for q, matrix in matrices.items():
        assert np.array_equal(matrix.data, before[q][0])
        assert np.array_equal(matrix.indices, before[q][1])
        assert np.array_equal(matrix.indptr, before[q][2])
    for record in factors.audit["factor_inputs"]:
        assert record["input_identity_unchanged"] is True
        assert record["process_tree_rss_bytes"] is None
        assert record["native_memory_observation"] is not None
        assert record["native_factor_entries_raw_infog_9"] is not None
