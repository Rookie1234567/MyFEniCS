from __future__ import annotations

import numpy as np
import pytest

from src.solvers.dtn_port_3d import (
    Stage4ExternalLinearSolverSnapshot,
    Stage4PstddmP6DiagnosticPort,
    _dispatch_external_linear_solver,
)
from src.solvers.pstddm_stage4_hook import (
    PstddmRawPortColumn,
    combine_exact_components,
    diagnostic_port_metrics,
    exact_sparse_entries,
    official_rta_allowed,
    should_run_diagnostic_postprocess,
)


def test_raw_complex_components_keep_tiny_entries_and_sum_shared_rows():
    rows, values = combine_exact_components(
        (
            (np.asarray([0, 2]), np.asarray([1 + 2j, 1e-16j])),
            (np.asarray([2, 3]), np.asarray([-3j, 2 - 1j])),
        ),
        (-(1 + 1j), 2j),
    )

    assert rows.tolist() == [0, 2, 3]
    assert values[0] == -(1 + 1j) * (1 + 2j)
    assert values[1] != 0.0
    assert values[2] == 2j * (2 - 1j)


def test_exact_sparse_entries_sort_and_merge_without_thresholding():
    rows, values = exact_sparse_entries([4, 1, 4, 2], [1j, 2, -1j, 1e-30])

    assert rows.tolist() == [1, 2]
    assert values.tolist() == [2 + 0j, 1e-30 + 0j]


def test_diagnostic_profile_never_publishes_official_rta():
    assert not official_rta_allowed(diagnostic_only=True, full_residual_passed=False)
    assert not official_rta_allowed(diagnostic_only=True, full_residual_passed=True)
    assert official_rta_allowed(diagnostic_only=False, full_residual_passed=True)
    assert not official_rta_allowed(diagnostic_only=False, full_residual_passed=False)


def test_diagnostic_port_output_keeps_rta_values_and_reports_actual_gate():
    metrics = diagnostic_port_metrics(
        {"R_total": 0.23, "T_total": 0.61, "A_balance": 0.16},
        full_residual=2e-8,
        residual_limit=1e-8,
    )

    assert metrics["R_total"] == 0.23
    assert metrics["T_total"] == 0.61
    assert metrics["A_balance"] == 0.16
    assert metrics["diagnostic_only"] is True
    assert metrics["official_result"] is False
    assert metrics["full_augmented_true_residual_gate_pass"] is False


def test_pstddm_nonofficial_finite_field_still_runs_diagnostic_postprocess():
    assert should_run_diagnostic_postprocess(
        pstddm_diagnostic=True,
        field_finite=True,
    )
    assert not should_run_diagnostic_postprocess(
        pstddm_diagnostic=True,
        field_finite=False,
    )
    assert not should_run_diagnostic_postprocess(
        pstddm_diagnostic=False,
        field_finite=True,
    )


class _FakeMatrix:
    def __init__(self, size):
        self.size = size

    def getSize(self):
        return self.size, self.size

    def getOwnershipRange(self):
        return 0, self.size


class _FakeVector:
    def __init__(self, size):
        self.size = size

    def getSize(self):
        return self.size

    def getOwnershipRange(self):
        return 0, self.size


def _empty_port_columns(count):
    return tuple(
        PstddmRawPortColumn(
            index=index,
            side="top" if index % 2 else "bottom",
            m=index,
            n=0,
            polarization="s",
            normalization=1.0,
            raw_C_rows=np.empty(0, dtype=np.int64),
            raw_C_values=np.empty(0, dtype=np.complex128),
            raw_D_rows=np.empty(0, dtype=np.int64),
            raw_D_values=np.empty(0, dtype=np.complex128),
            reduced_C_rows=np.empty(0, dtype=np.int64),
            reduced_C_values=np.empty(0, dtype=np.complex128),
            reduced_D_rows=np.empty(0, dtype=np.int64),
            reduced_D_values=np.empty(0, dtype=np.complex128),
        )
        for index in range(count)
    )


def _diagnostic_snapshot(size, *, no_global_factor=False):
    return Stage4ExternalLinearSolverSnapshot(
        x=_FakeVector(size),
        converged_reason=1,
        iterations=2,
        reported_relative_residual=2e-8,
        condensed_true_residual=2e-8,
        full_augmented_true_residual=None,
        ksp_type="FGMRES",
        pc_type="PSTDDM_source_transfer",
        residual_limit=1e-8,
        no_global_factor=no_global_factor,
        solver_profile="pstddm_p6_h10_source_transfer_diagnostic_v1",
        no_global_target_maxwell_factor=True,
        global_mass_factor_count=1,
        local_auxiliary_factor_count=3,
        diagnostic_only=True,
    )


def test_dispatch_accepts_typed_diagnostic_factor_inventory_and_raw_columns():
    columns = _empty_port_columns(612)
    seen = {}

    def callback(request):
        seen["request"] = request
        return _diagnostic_snapshot(613)

    snapshot = _dispatch_external_linear_solver(
        _FakeMatrix(613),
        object(),
        n_fe=1,
        n_aux=612,
        static_condensed_system=None,
        function_space=None,
        config=None,
        floquet_data=None,
        pstddm_raw_port_columns=columns,
        port=Stage4PstddmP6DiagnosticPort(callback),
    )

    assert snapshot.diagnostic_only is True
    assert seen["request"].pstddm_raw_port_columns is columns


def test_dispatch_rejects_inaccurate_no_global_factor_declaration():
    columns = _empty_port_columns(612)
    port = Stage4PstddmP6DiagnosticPort(
        lambda _request: _diagnostic_snapshot(613, no_global_factor=True)
    )

    with pytest.raises(ValueError, match="zero global Maxwell"):
        _dispatch_external_linear_solver(
            _FakeMatrix(613),
            object(),
            n_fe=1,
            n_aux=612,
            static_condensed_system=None,
            function_space=None,
            config=None,
            floquet_data=None,
            pstddm_raw_port_columns=columns,
            port=port,
        )
