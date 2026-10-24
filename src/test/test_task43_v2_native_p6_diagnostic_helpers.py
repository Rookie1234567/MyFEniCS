import hashlib
import json

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic import (
    _A2_NATIVE_CONTRACT_REL,
    _A2_NATIVE_CONTRACT_SHA256,
    _A2_Q_RETRY_REL,
    _A2_Q_RETRY_SHA256,
    _CONTRACT_REL,
    _CONTRACT_SHA256,
    _PLAN_REL,
    _PLAN_SHA256,
    _REPO_ROOT,
    _a2_attempt_run_directory,
    _read_a2_residual_vectors,
    _recompute_a2_extra_lu_helper_integrity,
    _recompute_a2_normal_correction_gate,
    _recompute_a2_q_raw_hard_gates,
    _require_a2_budget_frozen_before_attempt,
    _require_a2_q_r13_same_source_identity,
    _validate_a2_native_contract_copy,
    _validate_a2_q_retry_record,
    _validate_y6_recovered_bundle_binding,
)
from src.io.native_capacity_profile import TASK40_PHI90_D15_PROFILES
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task43_v2_active_explicit_residual_facts,
    _task43_v2_actual_form_integral_metadata,
    _task43_v2_array_identity,
    _task43_v2_extra_lu_status,
    _task43_v2_native_p6_route,
    _task43_v2_normal_correction_audit,
    _task43_v2_one_extra_same_factor_correction,
    _task43_v2_volume_quadrature_metadata,
)


class _Vec:
    def __init__(self, values):
        self.array = np.asarray(values, dtype=np.complex128).copy()

    def duplicate(self):
        return _Vec(np.zeros_like(self.array))

    def getArray(self, readonly=False):
        return self.array

    def set(self, value):
        self.array.fill(value)

    def copy(self, other):
        other.array[:] = self.array

    def axpy(self, alpha, other):
        self.array[:] += alpha * other.array

    def norm(self):
        return float(np.linalg.norm(self.array))

    def destroy(self):
        pass


class _Matrix:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128).copy()

    def mult(self, vector, output):
        output.array[:] = self.values @ vector.array


class _Factor:
    def __init__(self, matrix, correction_scale=1.0):
        self.matrix = matrix
        self.correction_scale = correction_scale
        self.symbolic_calls = 1
        self.numeric_calls = 1
        self.solve_calls = 1

    def solve_repeated(self, rhs, solution):
        solution.array[:] = self.correction_scale * np.linalg.solve(
            self.matrix.values, rhs.array
        )
        self.solve_calls += 1


class _Integral:
    def __init__(self, metadata):
        self._metadata = metadata

    def metadata(self):
        return self._metadata


class _Form:
    def __init__(self, metadata):
        self._metadata = metadata

    def integrals(self):
        return tuple(_Integral(item) for item in self._metadata)


def _a2_diagnostic(phase):
    return {
        "schema": "task43.v2.native_p6_diagnostic.v1",
        "phase": phase,
        "volume_quadrature_degree": 19,
        "surface_quadrature_degree": 32,
        "normal_correction_limit": 2,
        "extra_correction_limit": 1,
    }


def _y6_1_route():
    profile_identity = next(
        identity
        for identity, case in TASK40_PHI90_D15_PROFILES.items()
        if case == "Y6_1"
    )
    from src.io.native_capacity_profile import native_profile_facts

    profile_facts = native_profile_facts(profile_identity)
    return profile_facts, _direct_run_contract(profile_identity)


def test_task43_a2_route_binds_y6_1_q_and_r_without_changing_scale_policy():
    profile_facts, route = _y6_1_route()

    r13 = _task43_v2_native_p6_route(profile_facts, route, _a2_diagnostic("A2_q"))
    r14 = _task43_v2_native_p6_route(profile_facts, route, _a2_diagnostic("A2_R"))

    assert route["reference_mode_label"] == "R13"
    assert route["surface_quadrature_degree"] == 28
    assert route["parent_count"] == 612
    assert r13["reference_mode_label"] == "R13"
    assert r13["parent_rectangle_max_abs_m_n"] == [4, 8]
    assert r13["parent_count"] == r13["active_count"] == 612
    assert r13["surface_quadrature_degree"] == 32
    assert r14["reference_mode_label"] == "R14"
    assert r14["parent_rectangle_max_abs_m_n"] == [5, 9]
    assert r14["surface_quadrature_envelope_max_abs_m_n"] == [5, 9]
    assert r14["parent_count"] == r14["active_count"] == 836
    assert r14["surface_quadrature_degree"] == 32
    assert r13["mode_basis_scale_policy"] is None
    assert r14["mode_basis_scale_policy"] is None
    assert r13["max_same_factor_corrections"] == 2
    assert r14["max_same_factor_corrections"] == 2


def test_task43_a2_route_rejects_wrong_profile_or_relaxed_settings():
    profile_facts, route = _y6_1_route()
    wrong_profile = {**profile_facts, "identity": "not_Y6_1"}
    with pytest.raises(ValueError, match="only to the native Task40 Y6_1"):
        _task43_v2_native_p6_route(wrong_profile, route, _a2_diagnostic("A2_q"))

    wrong_quadrature = _a2_diagnostic("A2_q")
    wrong_quadrature["volume_quadrature_degree"] = 15
    with pytest.raises(ValueError, match="quadrature/correction settings"):
        _task43_v2_native_p6_route(profile_facts, route, wrong_quadrature)


def test_task43_q19_metadata_changes_both_volume_form_metadata_records_only_in_optin():
    analyzed = (
        {"quadrature_degree": 15, "quadrature_rule": "default"},
        {"quadrature_degree": 15, "quadrature_rule": "default"},
    )
    records = [
        {"component": name, "quadrature_degree": 15, "quadrature_rule": "default"}
        for name in ("curl", "material_mass")
    ]

    legacy_metadata, legacy_records = _task43_v2_volume_quadrature_metadata(
        analyzed, records, diagnostic=None
    )
    v2_metadata, v2_records = _task43_v2_volume_quadrature_metadata(
        analyzed, records, diagnostic=_a2_diagnostic("A2_q")
    )

    assert legacy_metadata == analyzed
    assert legacy_records == records
    assert [item["quadrature_degree"] for item in v2_metadata] == [19, 19]
    assert [item["quadrature_degree"] for item in v2_records] == [19, 19]
    assert [item["analyzed_quadrature_degree"] for item in v2_records] == [15, 15]
    assert all(
        item["quadrature_override"] == "task43_v2_explicit_volume_q19"
        for item in v2_records
    )

    with pytest.raises(ValueError, match="no longer match the q15 baseline"):
        _task43_v2_volume_quadrature_metadata(
            ({"quadrature_degree": 16, "quadrature_rule": "default"}, analyzed[1]),
            records,
            diagnostic=_a2_diagnostic("A2_q"),
        )


def test_task43_reads_q19_from_actual_ufl_integral_metadata():
    metadata = [
        {"quadrature_degree": 19, "quadrature_rule": "default"},
        {"quadrature_degree": 19, "quadrature_rule": "default"},
    ]

    assert (
        _task43_v2_actual_form_integral_metadata(_Form(metadata), expected_degree=19)
        == metadata
    )
    with pytest.raises(ValueError, match="metadata differs from q19"):
        _task43_v2_actual_form_integral_metadata(
            _Form([{**metadata[0], "quadrature_degree": 15}]),
            expected_degree=19,
        )


def test_task43_full_active_explicit_residual_combines_carrier_and_port_with_same_rhs():
    facts = _task43_v2_active_explicit_residual_facts(
        {
            "augmented_fe_residual": np.asarray([3.0, 4.0]),
            "augmented_port_residual": np.asarray([12.0]),
            "native_effective_rhs": np.asarray([5.0, 12.0]),
            "rhs_is_mpc_dual": True,
        },
        expected_carrier_rows=2,
        expected_port_rows=1,
    )

    assert facts["zero_slave_carrier_residual_norm"] == 5.0
    assert facts["port_residual_norm"] == 12.0
    assert facts["combined_residual_norm"] == 13.0
    assert facts["native_effective_rhs_norm"] == 13.0
    assert facts["combined_relative"] == 1.0
    assert facts["rhs_is_mpc_dual"] is True
    assert facts["finite"] is True

    with pytest.raises(ValueError, match="nonempty vectors"):
        _task43_v2_active_explicit_residual_facts(
            {
                "augmented_fe_residual": np.ones((1, 2)),
                "augmented_port_residual": np.ones(1),
                "native_effective_rhs": np.ones(2),
                "rhs_is_mpc_dual": True,
            },
            expected_carrier_rows=2,
            expected_port_rows=1,
        )


def test_task43_extra_lu_correction_uses_a_copy_and_performs_exactly_one_finite_decrease():
    matrix = _Matrix([[2.0, 0.5], [0.5, 3.0]])
    exact = np.asarray([1.25, -0.75], dtype=np.complex128)
    rhs = _Vec(matrix.values @ exact)
    primary = _Vec(exact + np.asarray([1.0e-3, -2.0e-3]))
    original_matrix = matrix.values.copy()
    original_rhs = rhs.array.copy()
    original_primary = primary.array.copy()
    factor = _Factor(matrix)

    corrected, facts = _task43_v2_one_extra_same_factor_correction(
        factor, matrix, rhs, primary
    )

    assert facts["status"] == "PASS"
    assert facts["extra_correction_count"] == 1
    assert facts["strict_decrease"] is True
    assert facts["finite"] is True
    assert facts["primary_solution_preserved"] is True
    assert facts["rhs_preserved"] is True
    assert facts["matrix_object_identity_same"] is True
    assert facts["factorization_calls_unchanged"] is True
    assert facts["exactly_one_extra_solve"] is True
    assert factor.solve_calls == 2
    np.testing.assert_array_equal(primary.array, original_primary)
    np.testing.assert_array_equal(rhs.array, original_rhs)
    np.testing.assert_array_equal(matrix.values, original_matrix)
    np.testing.assert_allclose(corrected.array, exact, rtol=0.0, atol=1.0e-14)


def test_task43_a2_raw_extra_lu_audit_rechecks_factor_counts_and_primary_identity():
    matrix = _Matrix([[2.0, 0.5], [0.5, 3.0]])
    exact = np.asarray([1.25, -0.75], dtype=np.complex128)
    rhs = _Vec(matrix.values @ exact)
    primary = _Vec(exact + np.asarray([1.0e-3, -2.0e-3]))
    factor = _Factor(matrix)
    corrected, linear = _task43_v2_one_extra_same_factor_correction(
        factor, matrix, rhs, primary
    )
    status = _task43_v2_extra_lu_status(
        linear, condensed_strict_decrease=True, full_active_strict_decrease=True
    )
    linear.update(
        original_helper_status=status["original_helper_status"],
        original_helper_gates=status["original_helper_gates"],
    )
    summary = {
        "task43_v2_extra_lu_diagnostic": {"linear_correction": linear},
        "factor": {
            "solve_calls_after_extra_lu": factor.solve_calls,
            "symbolic_calls_after_extra_lu": factor.symbolic_calls,
            "numeric_calls_after_extra_lu": factor.numeric_calls,
        },
    }
    arrays = {
        "primary_condensed_solution": primary.array.copy(),
        "extra_lu_condensed_solution": corrected.array.copy(),
        "primary_condensed_rhs": rhs.array.copy(),
    }
    result = _recompute_a2_extra_lu_helper_integrity(summary, arrays)
    assert result["passed"] is True
    assert result["gates"]["exactly_one_extra_solve"] is True
    assert result["gates"]["primary_solution_preserved"] is True

    wrong_counts = json.loads(json.dumps(summary))
    wrong_counts["factor"]["solve_calls_after_extra_lu"] += 1
    result = _recompute_a2_extra_lu_helper_integrity(wrong_counts, arrays)
    assert result["passed"] is False
    assert result["gates"]["exactly_one_extra_solve"] is False

    wrong_primary = dict(arrays)
    wrong_primary["primary_condensed_solution"] = arrays[
        "primary_condensed_solution"
    ].copy()
    wrong_primary["primary_condensed_solution"][0] += 1.0e-3
    wrong_primary["extra_lu_condensed_solution"] = arrays[
        "extra_lu_condensed_solution"
    ].copy()
    wrong_primary["extra_lu_condensed_solution"][0] += 1.0e-3
    result = _recompute_a2_extra_lu_helper_integrity(summary, wrong_primary)
    assert result["passed"] is False
    assert result["gates"]["primary_solution_preserved"] is False


def test_task43_extra_lu_records_no_decrease_without_claiming_qualification():
    matrix = _Matrix([[2.0, 0.5], [0.5, 3.0]])
    exact = np.asarray([1.25, -0.75], dtype=np.complex128)
    rhs = _Vec(matrix.values @ exact)
    primary = _Vec(exact + np.asarray([1.0e-3, -2.0e-3]))
    factor = _Factor(matrix, correction_scale=0.0)

    corrected, facts = _task43_v2_one_extra_same_factor_correction(
        factor, matrix, rhs, primary
    )

    assert facts["extra_correction_count"] == 1
    assert facts["finite"] is True
    assert facts["strict_decrease"] is False
    assert facts["status"] == "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
    np.testing.assert_array_equal(corrected.array, primary.array)


def test_task43_extra_lu_allows_exact_zero_residual_and_records_no_decrease():
    matrix = _Matrix([[2.0, 0.5], [0.5, 3.0]])
    exact = np.asarray([1.25, -0.75], dtype=np.complex128)
    rhs = _Vec(matrix.values @ exact)
    primary = _Vec(exact)
    factor = _Factor(matrix)

    corrected, facts = _task43_v2_one_extra_same_factor_correction(
        factor, matrix, rhs, primary
    )

    assert facts["initial_explicit_residual_norm"] == 0.0
    assert facts["extra_correction_count"] == 1
    assert facts["strict_decrease"] is False
    assert facts["status"] == "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
    assert factor.solve_calls == 2
    np.testing.assert_array_equal(corrected.array, primary.array)


def test_task43_extra_lu_rejects_nonfinite_primary_before_factor_solve():
    matrix = _Matrix([[2.0, 0.5], [0.5, 3.0]])
    rhs = _Vec([1.0, 2.0])
    primary = _Vec([np.nan, 1.0])
    factor = _Factor(matrix)

    with pytest.raises(FloatingPointError, match="refuses a non-finite"):
        _task43_v2_one_extra_same_factor_correction(factor, matrix, rhs, primary)

    assert factor.solve_calls == 1


def test_task43_a2_array_identity_binds_dtype_shape_and_bytes():
    values = np.arange(6, dtype=np.float64).reshape(2, 3)
    identity = _task43_v2_array_identity(values)
    expected = hashlib.sha256()
    expected.update(values.dtype.str.encode("ascii"))
    expected.update(json.dumps(list(values.shape)).encode("ascii"))
    expected.update(values.view(np.uint8))

    assert identity == {
        "dtype": values.dtype.str,
        "shape": [2, 3],
        "sha256": expected.hexdigest(),
    }
    assert _task43_v2_array_identity(values.reshape(6))["sha256"] != identity["sha256"]


def test_task43_a2_output_directory_must_be_fresh_run_child(tmp_path):
    attempt_root = tmp_path / "A2_q_attempt1"
    attempt_root.mkdir()
    expected = attempt_root / "run"

    assert _a2_attempt_run_directory(attempt_root) == expected.resolve()
    with pytest.raises(ValueError, match="attempt-root/run child"):
        _a2_attempt_run_directory(attempt_root, tmp_path / "elsewhere")

    expected.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        _a2_attempt_run_directory(attempt_root)


def test_task43_y6_restore_identity_binding_schema_with_fixture(tmp_path):
    bundle_path = tmp_path / "recovered_reference_bundle.npz"
    bundle_path.write_bytes(b"small identity fixture; no mesh or field data")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    identity = {
        "label": "Y6_1",
        "recovered_bundle": {
            "path": str(bundle_path.resolve()),
            "sha256": bundle_sha256,
        },
    }

    _validate_y6_recovered_bundle_binding(identity, bundle_path, bundle_sha256)

    wrong_path = json.loads(json.dumps(identity))
    wrong_path["recovered_bundle"]["path"] = str(tmp_path / "different-bundle.npz")
    with pytest.raises(ValueError, match="does not bind"):
        _validate_y6_recovered_bundle_binding(wrong_path, bundle_path, bundle_sha256)

    wrong_hash = json.loads(json.dumps(identity))
    wrong_hash["recovered_bundle"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not bind"):
        _validate_y6_recovered_bundle_binding(wrong_hash, bundle_path, bundle_sha256)


def test_task43_a2_native_contract_is_only_scoped_interface_amendment():
    original_path = _REPO_ROOT / _CONTRACT_REL
    a2_path = _REPO_ROOT / _A2_NATIVE_CONTRACT_REL
    plan_path = _REPO_ROOT / _PLAN_REL
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == _CONTRACT_SHA256
    assert (
        hashlib.sha256(a2_path.read_bytes()).hexdigest() == _A2_NATIVE_CONTRACT_SHA256
    )
    assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == _PLAN_SHA256
    original = json.loads(original_path.read_text(encoding="utf-8"))
    a2_contract = json.loads(a2_path.read_text(encoding="utf-8"))

    _validate_a2_native_contract_copy(original, a2_contract)

    changed_physics = json.loads(json.dumps(a2_contract))
    changed_physics["physical_problem"]["wavelength_nm"] += 0.01
    with pytest.raises(ValueError, match="outside its scoped interface"):
        _validate_a2_native_contract_copy(original, changed_physics)


def test_task43_a2_budget_is_frozen_to_actual_closed_a1_pair():
    a2_contract = json.loads(
        (_REPO_ROOT / _A2_NATIVE_CONTRACT_REL).read_text(encoding="utf-8")
    )
    budget = a2_contract["a2_native_applicability"][
        "actual_attempt_budget_at_A2_freeze"
    ]
    counts = budget["counts_at_A2_freeze"]
    assert counts == {
        "A1_q_started": 1,
        "A1_R_started": 0,
        "A2_q_started": 0,
        "A2_R_started": 0,
        "B_started": 0,
        "C_started": 0,
        "total_started": 1,
        "total_max": 6,
        "remaining": 5,
        "A1_quota_max": 2,
    }
    assert budget["A1_pair_closed"] is True
    assert budget["attempt_budget_is_not_redistributed"] is True
    _require_a2_budget_frozen_before_attempt(a2_contract)

    proposal = json.loads(json.dumps(a2_contract))
    proposal["a2_native_applicability"]["actual_attempt_budget_at_A2_freeze"][
        "status"
    ] = "proposal"
    with pytest.raises(ValueError, match="locked until the actual attempt budget"):
        _require_a2_budget_frozen_before_attempt(proposal)

    bad_counts = json.loads(json.dumps(a2_contract))
    bad_counts["a2_native_applicability"]["actual_attempt_budget_at_A2_freeze"][
        "counts_at_A2_freeze"
    ]["remaining"] = 4
    with pytest.raises(ValueError, match="attempt budget is inconsistent"):
        _require_a2_budget_frozen_before_attempt(bad_counts)

    over_a1_quota = json.loads(json.dumps(a2_contract))
    over_a1_quota_counts = over_a1_quota["a2_native_applicability"][
        "actual_attempt_budget_at_A2_freeze"
    ]["counts_at_A2_freeze"]
    over_a1_quota_counts.update(A1_R_started=2, total_started=3, remaining=3)
    with pytest.raises(ValueError, match="over A1 quota"):
        _require_a2_budget_frozen_before_attempt(over_a1_quota)

    missing_terminal = json.loads(json.dumps(a2_contract))
    missing_terminal["a2_native_applicability"]["actual_attempt_budget_at_A2_freeze"][
        "latest_A1_q_attempt_binding"
    ]["terminal_summary_sha256"] = None
    with pytest.raises(ValueError, match="lacks terminal A1_q evidence"):
        _require_a2_budget_frozen_before_attempt(missing_terminal)


def test_task43_a2_q_retry_binds_attempt1_terminal_and_fixed_budget(tmp_path):
    retry_path = _REPO_ROOT / _A2_Q_RETRY_REL
    assert hashlib.sha256(retry_path.read_bytes()).hexdigest() == _A2_Q_RETRY_SHA256
    record = json.loads(retry_path.read_text(encoding="utf-8"))
    assert record["attempt_budget"]["counts_before_retry"]["total_started"] == 2
    assert record["attempt_budget"]["counts_after_retry_dispatch"]["total_started"] == 3
    assert record["authorization"]["A2_R_status"] == "cancelled_not_run"

    terminal = record["consumed_attempt_1"]
    summary = {
        "classification": "WORKER_FAILED",
        "leader_exit_code": 1,
        "descendants_cleared": True,
    }
    summary_path = tmp_path / "watchdog-summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    summary_bytes = summary_path.read_bytes()
    summary_sha256 = hashlib.sha256(summary_bytes).hexdigest()
    root_audit = {
        "summary_sha256": summary_sha256,
        "classification": "FAILED_NATIVE_WATCHDOG_PHASE_PATH_WIRING_BEFORE_MESH_NO_NUMERICAL_RESULT",
        "formal_attempt_consumed": True,
    }
    root_audit_path = tmp_path / "root-terminal-audit.json"
    root_audit_path.write_text(json.dumps(root_audit, sort_keys=True), encoding="utf-8")
    root_audit_sha256 = hashlib.sha256(root_audit_path.read_bytes()).hexdigest()
    launch_identity = {
        "HEAD": terminal["source_head"],
        "phase": "A2_q",
        "attempt": 1,
    }
    launch_path = tmp_path / "launch-identity.json"
    launch_path.write_text(
        json.dumps(launch_identity, sort_keys=True), encoding="utf-8"
    )
    launch_sha256 = hashlib.sha256(launch_path.read_bytes()).hexdigest()
    worker_log = (
        b"RuntimeError: p6 condensed-direct route requires the native-capacity watchdog"
    )
    worker_log_path = tmp_path / "worker.log"
    worker_log_path.write_bytes(worker_log)
    worker_log_sha256 = hashlib.sha256(worker_log_path.read_bytes()).hexdigest()
    terminal.update(
        watchdog_summary_sha256=summary_sha256,
        root_terminal_audit_sha256=root_audit_sha256,
        launch_identity_sha256=launch_sha256,
        worker_log_sha256=worker_log_sha256,
    )
    evidence = {
        "actual_summary_sha256": summary_sha256,
        "actual_root_audit_sha256": root_audit_sha256,
        "actual_launch_identity_sha256": launch_sha256,
        "actual_worker_log_sha256": worker_log_sha256,
        "summary": summary,
        "root_audit": root_audit,
        "launch_identity": launch_identity,
        "watchdog_exit_code": 2,
        "launcher_exit_code": 2,
        "numerical_output_files": [],
    }
    _validate_a2_q_retry_record(record, **evidence)

    changed_terminal = json.loads(json.dumps(record))
    changed_terminal["consumed_attempt_1"]["watchdog_summary_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="terminal evidence"):
        _validate_a2_q_retry_record(changed_terminal, **evidence)

    changed_budget = json.loads(json.dumps(record))
    changed_budget["attempt_budget"]["counts_after_retry_dispatch"]["total_started"] = 4
    with pytest.raises(ValueError, match="invalid actual attempt budget"):
        _validate_a2_q_retry_record(changed_budget, **evidence)


def test_task43_a2_r_requires_same_committed_q19_q32_r13_native_identity():
    q19 = {"quadrature_degree": 19, "quadrature_rule": "default"}
    summary = {
        "source_sha": "a" * 40,
        "task43_v2_diagnostic_identity": {
            "phase": "A2_q",
            "volume_quadrature_degree": 19,
            "incident_quadrature_degree": 32,
            "port_quadrature_degree": 32,
            "modal_rectangle_max_abs_m_n": [4, 8],
            "mode_basis_scale_policy": None,
            "normal_correction_max": 2,
            "extra_correction_max": 1,
            "a2_native_contract_sha256": _A2_NATIVE_CONTRACT_SHA256,
            "frozen_plan_sha256": "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc",
            "frozen_plan_markdown_sha256": "864330a9a8d7efeeb1e9e48c73cf48331a9a4963a1bcea1ae061c00c769b455e",
        },
        "task43_v2_input_bindings": {
            "contract_sha256": "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc",
            "a2_native_contract_path": str(
                (_REPO_ROOT / _A2_NATIVE_CONTRACT_REL).resolve()
            ),
            "a2_native_contract_sha256": _A2_NATIVE_CONTRACT_SHA256,
            "plan_markdown_sha256": "864330a9a8d7efeeb1e9e48c73cf48331a9a4963a1bcea1ae061c00c769b455e",
        },
        "operator_identity": {
            "operator_scope": "task43_v2_A2_R13_native_Y6_1_finite_rectangle",
            "parent_quadrature_degree": 32,
            "active_mode_count": 612,
            "parent_mode_count": 612,
            "volume_quadrature_metadata_used_by_condensation_form": [q19, q19],
            "volume_quadrature_metadata_used_by_independent_physical_action": [
                q19,
                q19,
            ],
        },
        "task43_v2_actual_quadrature_route": {
            "incident_and_port_rhs": {
                "cfg_incident_degree": 32,
                "bundle_dtn_degree": 32,
            },
            "volume_action_and_condensation": {
                "quadrature_degree": 19,
                "same_bundle_form_drives_physical_action_and_condensation": True,
                "actual_component_integral_metadata": {
                    "curl": [q19],
                    "material_mass": [q19],
                },
                "actual_combined_form_integral_metadata": [q19],
            },
        },
    }

    _require_a2_q_r13_same_source_identity(summary, "a" * 40)
    with pytest.raises(ValueError, match="same committed q19/q32/R13"):
        _require_a2_q_r13_same_source_identity(summary, "b" * 40)

    wrong_surface = json.loads(json.dumps(summary))
    wrong_surface["task43_v2_diagnostic_identity"]["port_quadrature_degree"] = 28
    with pytest.raises(ValueError, match="same committed q19/q32/R13"):
        _require_a2_q_r13_same_source_identity(wrong_surface, "a" * 40)


def test_task43_a2_residual_reader_requires_raw_rhs_and_residual_arrays(tmp_path):
    names = (
        "primary_condensed_b_minus_Ax",
        "primary_condensed_rhs",
        "primary_condensed_solution",
        "primary_independent_A6_residual",
        "primary_native_A6_effective_rhs",
        "primary_zero_slave_carrier_residual",
        "primary_augmented_port_residual",
        "extra_lu_condensed_b_minus_Ax",
        "extra_lu_condensed_rhs",
        "extra_lu_condensed_solution",
        "extra_lu_independent_A6_residual",
        "extra_lu_native_A6_effective_rhs",
        "extra_lu_zero_slave_carrier_residual",
        "extra_lu_augmented_port_residual",
        "normal_correction_residual_0",
        "normal_correction_residual_1",
    )
    summary = {
        "matrix": {
            "shape": [615, 615],
            "full_p6_storage_rows": 7,
            "active_trace_rows": 3,
            "appended_port_rows": 612,
        },
        "operator_identity": {"active_mode_count": 612},
        "task43_v2_normal_correction_audit": {
            "correction_count": 1,
            "history": [
                {"correction": 0, "relative_residual": 0.5},
                {"correction": 1, "relative_residual": 0.25},
            ],
        },
    }
    expected_lengths = {
        name: 615
        for name in (
            "primary_condensed_b_minus_Ax",
            "primary_condensed_rhs",
            "primary_condensed_solution",
            "extra_lu_condensed_b_minus_Ax",
            "extra_lu_condensed_rhs",
            "extra_lu_condensed_solution",
            "normal_correction_residual_0",
            "normal_correction_residual_1",
        )
    }
    expected_lengths.update(
        {
            name: 7
            for name in (
                "primary_independent_A6_residual",
                "primary_native_A6_effective_rhs",
                "primary_zero_slave_carrier_residual",
                "extra_lu_independent_A6_residual",
                "extra_lu_native_A6_effective_rhs",
                "extra_lu_zero_slave_carrier_residual",
            )
        }
    )
    expected_lengths.update(
        {
            "primary_augmented_port_residual": 612,
            "extra_lu_augmented_port_residual": 612,
        }
    )
    expected = {
        name: np.full(
            expected_lengths[name], complex(index + 1, -index), dtype=np.complex128
        )
        for index, name in enumerate(names)
    }
    complete = tmp_path / "complete.npz"
    np.savez(complete, **expected)
    loaded = _read_a2_residual_vectors(complete, summary)
    assert set(loaded) == set(names)
    for name in names:
        np.testing.assert_array_equal(loaded[name], expected[name])

    missing_rhs = tmp_path / "missing_rhs.npz"
    np.savez(
        missing_rhs,
        **{
            name: value
            for name, value in expected.items()
            if name != "primary_native_A6_effective_rhs"
        },
    )
    with pytest.raises(ValueError, match="lacks raw RHS/residual arrays"):
        _read_a2_residual_vectors(missing_rhs, summary)

    truncated = tmp_path / "truncated.npz"
    truncated_values = dict(expected)
    truncated_values["primary_zero_slave_carrier_residual"] = expected[
        "primary_zero_slave_carrier_residual"
    ][:-1]
    np.savez(truncated, **truncated_values)
    with pytest.raises(ValueError, match="unexpected shape"):
        _read_a2_residual_vectors(truncated, summary)


def test_task43_a2_raw_gate_roundtrips_native_writer_active_facts(tmp_path):
    from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import R13_MODE_KEYS

    def writer_facts(carrier, port, effective_rhs):
        return _task43_v2_active_explicit_residual_facts(
            {
                "augmented_fe_residual": carrier,
                "augmented_port_residual": port,
                "native_effective_rhs": effective_rhs,
                "rhs_is_mpc_dual": True,
            },
            expected_carrier_rows=3,
            expected_port_rows=612,
        )

    def file_sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    modal_path = tmp_path / "modal_r13.json"
    modal_rows = [
        {
            "side": side,
            "m": m,
            "n": n,
            "polarization": polarization,
            "outgoing_amplitude_at_boundary": [0.0, 0.0],
            "power_ratio": 0.0,
            "power_carrying": True,
            "R": 0.0,
            "T": 0.0,
        }
        for side, m, n, polarization in sorted(R13_MODE_KEYS)
    ]
    modal_payload = {
        "orders": modal_rows,
        "metrics": {
            "R_total": 0.0,
            "T_total": 0.0,
            "R00_s": 0.0,
            "R00_p": 0.0,
            "R00_total": 0.0,
            "dtn_port_mode_count": 612,
        },
    }
    modal_path.write_text(json.dumps(modal_payload), encoding="utf-8")
    volume_path = tmp_path / "volume_absorption.json"
    volume_path.write_text(
        json.dumps(
            {
                "A_volume_total": 1.0,
                "energy_closure_error_port_volume": 0.0,
            }
        ),
        encoding="utf-8",
    )

    condensed_rhs = np.ones(614, dtype=np.complex128)
    condensed_zero = np.zeros(614, dtype=np.complex128)
    active_rhs = np.ones(3, dtype=np.complex128)
    active_zero = np.zeros(3, dtype=np.complex128)
    port_zero = np.zeros(612, dtype=np.complex128)
    arrays = {
        "primary_condensed_b_minus_Ax": condensed_zero.copy(),
        "primary_condensed_rhs": condensed_rhs.copy(),
        "primary_condensed_solution": condensed_zero.copy(),
        "primary_independent_A6_residual": active_zero.copy(),
        "primary_native_A6_effective_rhs": active_rhs.copy(),
        "primary_zero_slave_carrier_residual": active_zero.copy(),
        "primary_augmented_port_residual": port_zero.copy(),
        "extra_lu_condensed_b_minus_Ax": condensed_zero.copy(),
        "extra_lu_condensed_rhs": condensed_rhs.copy(),
        "extra_lu_condensed_solution": condensed_zero.copy(),
        "extra_lu_independent_A6_residual": active_zero.copy(),
        "extra_lu_native_A6_effective_rhs": active_rhs.copy(),
        "extra_lu_zero_slave_carrier_residual": active_zero.copy(),
        "extra_lu_augmented_port_residual": port_zero.copy(),
        "normal_correction_residual_0": condensed_zero.copy(),
    }
    residual_path = tmp_path / "residual_vectors.npz"
    np.savez(residual_path, **arrays)
    residual_sha = file_sha(residual_path)

    primary_active = writer_facts(active_zero, port_zero, active_rhs)
    extra_active = writer_facts(active_zero, port_zero, active_rhs)
    mumps_info = {"infog": {"1": 0}, "rinfog": {"1": 0.0}}
    normal_audit = _task43_v2_normal_correction_audit(
        [
            {
                "correction": 0,
                "relative_residual": 0.0,
                "solution_updated": False,
                "solver_method": "initial_native_direct_solve",
                "petsc_matsolve_completed_without_exception": None,
                "ksp_converged_reason": "not_applicable_native_MatSolve",
            }
        ],
        correction_count=0,
        correction_limit=2,
        rhs_norm=float(np.linalg.norm(condensed_rhs)),
        mumps_info_after_last_solve=mumps_info,
    )
    zero_identity = _task43_v2_array_identity(condensed_zero)
    rhs_identity = _task43_v2_array_identity(condensed_rhs)
    original_helper_gates = {
        "original_helper_status_passed": True,
        "exactly_one_extra_solve": True,
        "factorization_calls_unchanged": True,
        "finite": True,
        "primary_solution_preserved": True,
        "rhs_preserved": True,
        "matrix_object_identity_same": True,
    }
    linear_correction = {
        "status": "PASS",
        "original_helper_status": "PASS",
        "original_helper_gates": original_helper_gates,
        "exactly_one_extra_solve": True,
        "factorization_calls_unchanged": True,
        "finite": True,
        "primary_solution_preserved": True,
        "primary_solution_before_identity": zero_identity,
        "primary_solution_after_identity": zero_identity,
        "rhs_preserved": True,
        "rhs_before_identity": rhs_identity,
        "rhs_after_identity": rhs_identity,
        "matrix_object_identity_same": True,
        "initial_factor_solve_calls": 1,
        "final_factor_solve_calls": 2,
        "initial_factor_symbolic_calls": 1,
        "final_factor_symbolic_calls": 1,
        "initial_factor_numeric_calls": 1,
        "final_factor_numeric_calls": 1,
        "extra_correction_count": 1,
        "correction_norm": 0.0,
        "initial_explicit_residual_norm": 0.0,
        "initial_explicit_residual_relative": 0.0,
        "rhs_norm": float(np.linalg.norm(condensed_rhs)),
        "corrected_explicit_residual_norm": 0.0,
        "corrected_explicit_residual_relative": 0.0,
        "condensed_b_minus_ax_strict_decrease": False,
    }
    primary_metrics = {
        "R_total": 0.0,
        "T_total": 0.0,
        "R00_s": 0.0,
        "R00_p": 0.0,
        "R00_total": 0.0,
    }
    primary_output = {
        "electric_finite": True,
        "auxiliary_finite": True,
        "port_metrics": primary_metrics,
        "volume_metrics": {"A_volume_total": 1.0},
        "energy_closure_error_port_volume": 0.0,
    }
    primary = {
        "modal_rows_path": str(modal_path),
        "modal_rows_sha256": file_sha(modal_path),
        "volume_absorption_path": str(volume_path),
        "volume_absorption_sha256": file_sha(volume_path),
        "same_lu_residual_vectors_path": str(residual_path),
        "same_lu_residual_vectors_sha256": residual_sha,
        "condensed_rhs_norm": float(np.linalg.norm(condensed_rhs)),
        "native_A6_effective_rhs_norm": float(np.linalg.norm(active_rhs)),
        "full_active_space_explicit": primary_active,
    }
    extra = {
        "status": "FAIL_UNCONTROLLED_EXTRA_CORRECTION",
        "linear_correction": linear_correction,
        "condensed_residual_relative": 0.0,
        "independent_A6_relative": 0.0,
        "native_A6_effective_rhs_norm": float(np.linalg.norm(active_rhs)),
        "full_active_space_explicit": {
            "before": primary_active,
            "after": extra_active,
            "same_rhs": True,
            "strict_decrease": False,
        },
        "hard_solver_gates": {"complete_modal_output_finite": True},
        "physical_output": {
            **primary_metrics,
            "A_volume_total": 1.0,
            "mode_count": 612,
        },
        "energy_closure_error_port_volume": 0.0,
        "field_samples": {
            "residual_vectors_path": str(residual_path),
            "residual_vectors_sha256": residual_sha,
            "extra_modal_rows_path": str(modal_path),
            "extra_modal_rows_sha256": file_sha(modal_path),
            "extra_volume_absorption_path": str(volume_path),
            "extra_volume_absorption_sha256": file_sha(volume_path),
        },
    }
    rhs_norm = float(np.linalg.norm(active_rhs))
    summary = {
        "passed": True,
        "matrix": {
            "shape": [614, 614],
            "full_p6_storage_rows": 3,
            "active_trace_rows": 2,
            "appended_port_rows": 612,
        },
        "operator_identity": {"active_mode_count": 612},
        "task43_v2_endpoint_identity": {
            "phase": "A2_q",
            "physical_configuration_sha256": "a" * 64,
            "discretization_sha256": "b" * 64,
        },
        "task43_v2_primary_endpoint_output": primary,
        "task43_v2_extra_lu_diagnostic": extra,
        "task43_v2_normal_correction_audit": normal_audit,
        "official_result": primary_output,
        "factor": {
            "solve_calls": 1,
            "symbolic_calls": 1,
            "numeric_calls": 1,
            "solve_calls_after_extra_lu": 2,
            "symbolic_calls_after_extra_lu": 1,
            "numeric_calls_after_extra_lu": 1,
            "mumps_info_after_last_solve": mumps_info,
        },
        "residuals": {
            "condensed_direct_relative": 0.0,
            "original_A6_active_rectangle_relative": 0.0,
            "rhs_norm": rhs_norm,
            "native_A6_effective_rhs_norm": rhs_norm,
            "full_active_space_explicit_relative": primary_active["combined_relative"],
            "full_active_space_explicit_residual_norm": primary_active[
                "combined_residual_norm"
            ],
            "full_active_space_explicit_rhs_norm": primary_active[
                "native_effective_rhs_norm"
            ],
        },
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    recomputed = _recompute_a2_q_raw_hard_gates(summary_path, summary)
    assert recomputed["passed"] is True
    assert (
        recomputed["primary"]["full_active_space_explicit"]["native_effective_rhs_norm"]
        == rhs_norm
    )

    # The full-active writer uses norm / max(rhs_norm, tiny), so the raw reader
    # must preserve that exact convention even when the effective RHS is zero.
    zero_rhs_arrays = {name: values.copy() for name, values in arrays.items()}
    zero_rhs_arrays["primary_native_A6_effective_rhs"] = np.zeros(3, np.complex128)
    zero_rhs_arrays["extra_lu_native_A6_effective_rhs"] = np.zeros(3, np.complex128)
    nonzero_carrier = np.ones(3, np.complex128)
    zero_rhs_arrays["primary_zero_slave_carrier_residual"] = nonzero_carrier.copy()
    zero_rhs_arrays["extra_lu_zero_slave_carrier_residual"] = nonzero_carrier.copy()
    np.savez(residual_path, **zero_rhs_arrays)
    zero_rhs_sha = file_sha(residual_path)
    zero_rhs_primary = writer_facts(
        nonzero_carrier, port_zero, np.zeros(3, np.complex128)
    )
    zero_rhs_extra = writer_facts(
        nonzero_carrier, port_zero, np.zeros(3, np.complex128)
    )
    zero_rhs_summary = json.loads(json.dumps(summary))
    zero_rhs_summary["task43_v2_primary_endpoint_output"][
        "same_lu_residual_vectors_sha256"
    ] = zero_rhs_sha
    zero_rhs_summary["task43_v2_extra_lu_diagnostic"]["field_samples"][
        "residual_vectors_sha256"
    ] = zero_rhs_sha
    zero_rhs_summary["task43_v2_primary_endpoint_output"][
        "native_A6_effective_rhs_norm"
    ] = 0.0
    zero_rhs_summary["task43_v2_primary_endpoint_output"][
        "full_active_space_explicit"
    ] = zero_rhs_primary
    zero_rhs_summary["task43_v2_extra_lu_diagnostic"][
        "native_A6_effective_rhs_norm"
    ] = 0.0
    zero_rhs_summary["task43_v2_extra_lu_diagnostic"]["full_active_space_explicit"] = {
        "before": zero_rhs_primary,
        "after": zero_rhs_extra,
        "same_rhs": True,
        "strict_decrease": False,
    }
    zero_rhs_summary["residuals"].update(
        rhs_norm=0.0,
        native_A6_effective_rhs_norm=0.0,
        full_active_space_explicit_relative=zero_rhs_primary["combined_relative"],
        full_active_space_explicit_residual_norm=zero_rhs_primary[
            "combined_residual_norm"
        ],
        full_active_space_explicit_rhs_norm=0.0,
    )
    zero_rhs_summary_path = tmp_path / "zero_rhs_summary.json"
    zero_rhs_summary_path.write_text(json.dumps(zero_rhs_summary), encoding="utf-8")
    zero_rhs_recomputed = _recompute_a2_q_raw_hard_gates(
        zero_rhs_summary_path, zero_rhs_summary
    )
    assert zero_rhs_recomputed["passed"] is False
    assert (
        zero_rhs_recomputed["primary"]["full_active_space_explicit"][
            "combined_relative"
        ]
        == zero_rhs_primary["combined_relative"]
    )


def test_task43_v2_normal_correction_audit_distinguishes_initial_solve():
    history = [
        {
            "correction": 0,
            "relative_residual": 0.5,
            "solution_updated": False,
            "solver_method": "initial_native_direct_solve",
        },
        {
            "correction": 1,
            "relative_residual": 0.25,
            "solve_calls": 2,
            "symbolic_calls": 1,
            "numeric_calls": 1,
            "petsc_matsolve_completed_without_exception": True,
            "solution_updated": True,
            "solver_method": "native_PETSc_MatSolve_with_MUMPS_factor",
            "ksp_converged_reason": "not_applicable_native_MatSolve",
        },
    ]
    mumps_info = {"infog": {"1": 0}, "rinfog": {"1": 0.0}}
    audit = _task43_v2_normal_correction_audit(
        history,
        correction_count=1,
        correction_limit=2,
        rhs_norm=4.0,
        mumps_info_after_last_solve=mumps_info,
    )
    assert audit["passed"] is True
    assert audit["history"][0]["solution_updated"] is False
    assert audit["history"][0].get("petsc_matsolve_completed_without_exception") is None
    assert audit["history"][1]["solution_updated"] is True
    assert audit["history"][1]["petsc_matsolve_completed_without_exception"] is True
    assert (
        audit["history"][1]["ksp_converged_reason"] == "not_applicable_native_MatSolve"
    )
    assert (
        audit["history"][1]["residual_norm_derived_from_recorded_ratio_and_denominator"]
        == 1.0
    )

    nondecreasing = [history[0], {**history[1], "relative_residual": 0.6}]
    limited = _task43_v2_normal_correction_audit(
        nondecreasing,
        correction_count=1,
        correction_limit=2,
        rhs_norm=4.0,
        mumps_info_after_last_solve=mumps_info,
    )
    assert limited["passed"] is False
    assert limited["every_executed_correction_strictly_decreased"] is False


def test_task43_extra_lu_status_keeps_original_helper_failure():
    helper_facts = {
        "status": "FAIL_UNCONTROLLED_EXTRA_CORRECTION",
        "exactly_one_extra_solve": True,
        "factorization_calls_unchanged": True,
        "finite": True,
        "primary_solution_preserved": True,
        "rhs_preserved": True,
        "matrix_object_identity_same": True,
    }
    result = _task43_v2_extra_lu_status(
        helper_facts,
        condensed_strict_decrease=True,
        full_active_strict_decrease=True,
    )
    assert result["status"] == "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
    assert result["original_helper_status"] == "FAIL_UNCONTROLLED_EXTRA_CORRECTION"
    assert result["original_helper_gates"]["original_helper_status_passed"] is False


def test_task43_normal_correction_raw_gate_recomputes_each_vector():
    rhs = np.asarray([3.0, 4.0], dtype=np.complex128)
    history = [
        {
            "correction": 0,
            "relative_residual": 0.2,
            "solution_updated": False,
            "solver_method": "initial_native_direct_solve",
        },
        {
            "correction": 1,
            "relative_residual": 0.02,
            "solve_calls": 2,
            "symbolic_calls": 1,
            "numeric_calls": 1,
            "solver_method": "native_PETSc_MatSolve_with_MUMPS_factor",
            "petsc_matsolve_completed_without_exception": True,
            "solution_updated": True,
            "ksp_converged_reason": "not_applicable_native_MatSolve",
        },
    ]
    info = {"infog": {"1": 0, "2": 0}, "rinfog": {"1": 0.0}}
    audit = _task43_v2_normal_correction_audit(
        history,
        correction_count=1,
        correction_limit=2,
        rhs_norm=5.0,
        mumps_info_after_last_solve=info,
    )
    summary = {
        "task43_v2_normal_correction_audit": audit,
        "factor": {
            "solve_calls": 2,
            "symbolic_calls": 1,
            "numeric_calls": 1,
            "mumps_info_after_last_solve": info,
        },
    }
    arrays = {
        "primary_condensed_rhs": rhs,
        "normal_correction_residual_0": np.asarray([1.0, 0.0]),
        "normal_correction_residual_1": np.asarray([0.1, 0.0]),
    }
    result = _recompute_a2_normal_correction_gate(summary, arrays)
    assert result["passed"] is True
    assert result["relative_residuals_from_raw_vectors"] == [0.2, 0.02]

    arrays["normal_correction_residual_1"] = np.asarray([1.1, 0.0])
    increasing_history = [
        {**history[0], "relative_residual": 0.2},
        {**history[1], "relative_residual": 0.22},
    ]
    limited_audit = _task43_v2_normal_correction_audit(
        increasing_history,
        correction_count=1,
        correction_limit=2,
        rhs_norm=5.0,
        mumps_info_after_last_solve=info,
    )
    summary["task43_v2_normal_correction_audit"] = limited_audit
    result = _recompute_a2_normal_correction_gate(summary, arrays)
    assert result["passed"] is False
    assert result["gates"]["every_executed_correction_strictly_decreased"] is False

    arrays["normal_correction_residual_1"] = np.asarray([0.1, 0.0])
    error_info = {"infog": {"1": -6, "2": 1}, "rinfog": {"1": 0.0}}
    failed_info_audit = _task43_v2_normal_correction_audit(
        history,
        correction_count=1,
        correction_limit=2,
        rhs_norm=5.0,
        mumps_info_after_last_solve=error_info,
    )
    failed_info_summary = {
        "task43_v2_normal_correction_audit": failed_info_audit,
        "factor": {
            "solve_calls": 2,
            "symbolic_calls": 1,
            "numeric_calls": 1,
            "mumps_info_after_last_solve": error_info,
        },
    }
    result = _recompute_a2_normal_correction_gate(failed_info_summary, arrays)
    assert result["passed"] is False
    assert result["gates"]["mumps_infog1_zero_and_bound_to_pre_extra_solve"] is False
