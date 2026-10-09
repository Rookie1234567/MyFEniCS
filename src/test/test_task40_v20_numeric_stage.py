from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import destroy_task40_v10_p6_reference_inverse
from src.solvers.task40_v20_numeric_stage import (
    run_v20_one_q_physical_rhs,
    validate_v20_one_q_numeric_audit,
    v20_factor_cleanup_facts,
)


class _Factors:
    def __init__(self, *, all_symbolic: bool = True):
        self.csr_matrices = {
            0: sparse.eye(2, dtype=np.complex128, format="csr"),
            1: sparse.eye(2, dtype=np.complex128, format="csr"),
        }
        self.factors = {}
        self.matrices = {}
        self.destroyed = False
        self.calls = []
        self.audit = {
            "all_q_symbolic_covered": all_symbolic,
            "numeric_factor_build_attempt_count": 0,
            "factor_tests": [],
            "factor_probe_mat_solve_count": 0,
            "rhs_mat_solve_count_by_category": {"startup_rhs_mat_solve_count": 0},
            "factors_live_count_current": 0,
            "matrices_live_count_current": 0,
        }

    def solve(self, q, rhs, *, category):
        self.calls.append((q, category))
        self.audit["numeric_factor_build_attempt_count"] += 1
        self.audit["factor_tests"].append({"q": q})
        self.audit["factor_probe_mat_solve_count"] += 1
        self.audit["rhs_mat_solve_count_by_category"][category] += 1
        self.factors[q] = object()
        self.matrices[q] = object()
        self.audit["factors_live_count_current"] = 1
        self.audit["matrices_live_count_current"] = 1
        return np.asarray(rhs, dtype=np.complex128).copy()

    def destroy(self):
        self.destroyed = True
        self.factors.clear()
        self.matrices.clear()
        self.audit["factors_live_count_current"] = 0
        self.audit["matrices_live_count_current"] = 0


class _Inverse:
    mode_count = 0

    def iter_q_modal_rhs(self, rhs, *, port_rhs, q_index):
        assert q_index == 0
        np.testing.assert_array_equal(port_rhs, np.zeros(0, dtype=np.complex128))
        assert np.asarray(rhs).shape == (3,)
        yield {
            "q": 0,
            "sector_index": 0,
            "twist_index": 0,
            "branch": 0,
            "mode_indices": np.asarray([], dtype=np.int64),
            "fe_rhs_norm": float(np.linalg.norm(rhs)),
            "port_rhs_norm": 0.0,
            "rhs": np.asarray(rhs[:2], dtype=np.complex128),
        }

    def destroy(self):
        self.destroyed = True


def test_v20_one_q_stage_uses_only_q0_and_requires_all_symbolics_first():
    factors = _Factors(all_symbolic=False)
    with pytest.raises(RuntimeError, match="all-q CSR and symbolic coverage"):
        run_v20_one_q_physical_rhs(
            _Inverse(),
            factors,
            np.asarray([1.0 + 1.0j, 2.0 - 1.0j, 0.5j]),
            physical_rhs_facts={"generation": "production fixture"},
            q_count=2,
        )
    assert factors.calls == []

    factors = _Factors()
    facts, arrays = run_v20_one_q_physical_rhs(
        _Inverse(),
        factors,
        np.asarray([1.0 + 1.0j, 2.0 - 1.0j, 0.5j]),
        physical_rhs_facts={"generation": "production fixture"},
        q_count=2,
    )
    assert factors.calls == [(0, "startup_rhs_mat_solve_count")]
    assert facts["selected_q_numeric_coverage"] == [0]
    assert facts["all_q_symbolic_covered"] is True
    assert facts["not_a_factor_probe"] is True
    assert facts["sector_solves"][0]["true_residual_relative"] == 0.0
    assert set(arrays) == {
        "q0_sector0_physical_rhs",
        "q0_sector0_solution",
        "q0_sector0_true_residual",
    }


def test_v20_numeric_audit_rejects_any_non_q0_or_second_numeric_factor():
    good = {
        "all_q_symbolic_covered": True,
        "numeric_factor_build_attempt_count": 1,
        "factor_tests": [{"q": 0}],
    }
    assert validate_v20_one_q_numeric_audit(good) == [0]
    with pytest.raises(RuntimeError, match="exactly the selected q factor"):
        validate_v20_one_q_numeric_audit(
            {
                **good,
                "numeric_factor_build_attempt_count": 2,
                "factor_tests": [{"q": 0}, {"q": 1}],
            }
        )


def test_v20_one_q_reference_cleanup_releases_factor_and_matrix_slot():
    factors = _Factors()
    factors.factors[0] = object()
    factors.matrices[0] = object()
    factors.audit["factors_live_count_current"] = 1
    factors.audit["matrices_live_count_current"] = 1
    inverse = _Inverse()
    owner = {"inverse": inverse, "factors": factors, "sectors": []}

    destroy_task40_v10_p6_reference_inverse(owner)

    assert owner == {}
    assert inverse.destroyed is True
    assert v20_factor_cleanup_facts(factors) == {
        "factor_backend_destroyed": True,
        "live_factor_count_after_cleanup": 0,
        "live_petsc_matrix_count_after_cleanup": 0,
        "audit_factor_count_after_cleanup": 0,
        "audit_matrix_count_after_cleanup": 0,
        "passed": True,
    }
