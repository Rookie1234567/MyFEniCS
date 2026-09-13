"""Review V16 S0 contracts; no p4/p6 or full PDE run is performed here."""

from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import pytest

from src.solvers.fullspace_p4_blr import (
    augmented_residual_identity,
    native_a4_residual_from_augmented,
)
from src.solvers.physical_map_identity import compare_native_map_identity


def _map_fixture() -> dict[str, np.ndarray]:
    return {
        "dofmap": np.array([[0, 1, 2]], dtype=np.int32),
        "geometry": np.arange(12, dtype=np.float64).reshape(4, 3),
        "geometry_dofmap": np.array([[0, 1, 2, 3]], dtype=np.int32),
        "permutations": np.array([0], dtype=np.uint32),
        "slaves": np.array([2], dtype=np.int32),
        "masters": np.array([0, 1], dtype=np.int32),
        "coefficients": np.array([1.0 + 2.0j, -0.25 + 0.5j], dtype=np.complex128),
        "offsets": np.array([0, 0, 0, 2, 2, 2, 2], dtype=np.int32),
        "independent_indices": np.array([0, 1, 3, 4, 5], dtype=np.int64),
    }


def test_map_guard_ignores_packet_metadata_but_hashes_all_root_arrays():
    current = _map_fixture()
    saved = {
        **{key: value.copy() for key, value in current.items()},
        "arrays": {"path": "frozen.npz", "sha256": "archive-hash"},
        "provenance": "older packet metadata",
    }
    facts = compare_native_map_identity(current, saved, context="synthetic map")
    assert facts["status"] == "PASS"
    assert facts["master_slave_layout_checked"]
    assert facts["metadata_keys_ignored"] == ["arrays", "provenance"]
    assert facts["array_facts"]["coefficients"]["current"]["dtype"] == "complex128"
    assert len(facts["array_facts"]["coefficients"]["current"]["sha256"]) == 64


@pytest.mark.parametrize(
    "field,mutator,match",
    [
        ("coefficients", lambda value: value.astype(np.complex64), "coefficients"),
        ("masters", lambda value: value[:-1], "masters"),
        ("slaves", lambda value: np.array([1], dtype=np.int32), "slaves"),
        ("independent_indices", lambda value: np.array([0, 1, 2, 4, 5], dtype=np.int64), "independent_indices"),
    ],
)
def test_map_guard_rejects_dtype_shape_and_master_slave_semantic_changes(field, mutator, match):
    current = _map_fixture()
    saved = {key: value.copy() for key, value in current.items()}
    saved[field] = mutator(saved[field])
    with pytest.raises(ValueError, match=match):
        compare_native_map_identity(current, saved, context="synthetic map")


def test_map_guard_rejects_unverified_numeric_arrays():
    current = _map_fixture()
    saved = {key: value.copy() for key, value in current.items()}
    saved["unrelated_numeric_array"] = np.array([1], dtype=np.int64)
    with pytest.raises(ValueError, match="unverified numeric"):
        compare_native_map_identity(current, saved)


def test_complex_primal_map_has_the_checked_conjugate_transpose_dual():
    from src.solvers.condensed_fine_reference import project_unconstrained_mpc_dual

    mapping = _map_fixture()
    primal = np.array([0.5 - 0.25j, -1.0 + 0.75j, 0, 2.0 + 0.5j, -0.2j, 0.9], dtype=np.complex128)
    primal[mapping["slaves"]] = sum(
        coefficient * primal[master]
        for coefficient, master in zip(
            mapping["coefficients"], mapping["masters"], strict=True
        )
    )
    dual = np.array([1.0 + 0.5j, -0.4 + 1.2j, 0.75 - 0.1j, 0.2j, -0.5, 0.9 + 0.3j], dtype=np.complex128)
    projected = project_unconstrained_mpc_dual(dual, mapping)
    independent = primal.copy()
    independent[mapping["slaves"]] = 0
    np.testing.assert_allclose(np.vdot(projected, independent), np.vdot(dual, primal))


def _nonhermitian_residual_case():
    """Build an independent dense [V B; -D H] residual identity witness."""

    volume = np.array(
        [
            [2.0 + 0.4j, -0.3 + 0.2j, 0.15j],
            [0.1 - 0.5j, 1.7 + 0.1j, -0.2 + 0.3j],
            [0.25 + 0.2j, 0.05j, 2.4 - 0.6j],
        ],
        dtype=np.complex128,
    )
    coupling = np.array(
        [
            [0.4 + 0.7j, -0.2 + 0.1j],
            [0.3 - 0.15j, 0.5 + 0.25j],
            [-0.6 + 0.05j, 0.2 - 0.45j],
        ],
        dtype=np.complex128,
    )
    projection = np.array(
        [
            [0.8 - 0.2j, 0.1 + 0.35j, -0.25 + 0.4j],
            [-0.3 + 0.5j, 0.6 - 0.1j, 0.2 + 0.75j],
        ],
        dtype=np.complex128,
    )
    diagonal = np.diag(np.array([1.3 + 0.2j, 0.75 - 0.4j], dtype=np.complex128))
    c = np.array([0.2 - 0.8j, 1.1 + 0.3j, -0.45 + 0.6j], dtype=np.complex128)
    alpha = np.array([0.35 + 0.2j, -0.7 + 0.1j], dtype=np.complex128)
    rhs = np.array([1.0 - 0.4j, -0.3 + 0.8j, 0.25 + 0.15j], dtype=np.complex128)
    top = rhs - (volume @ c + coupling @ alpha)
    port = projection @ c - diagonal @ alpha

    carrier = SimpleNamespace(
        entries=tuple(
            SimpleNamespace(
                coupling_rows=np.arange(3, dtype=np.int64),
                coupling_values=coupling[:, index],
                normalization_h=diagonal[index, index],
            )
            for index in range(2)
        )
    )
    native_operator = volume + coupling @ np.linalg.solve(diagonal, projection)
    native_action = native_operator @ c
    native = rhs - native_action
    return (
        volume,
        coupling,
        projection,
        diagonal,
        c,
        alpha,
        top,
        port,
        native,
        carrier,
        rhs,
        native_action,
    )


def test_augmented_residual_identity_uses_independent_nonhermitian_dense_algebra():
    (
        _,
        coupling,
        projection,
        diagonal,
        c,
        alpha,
        top,
        port,
        native,
        carrier,
        rhs,
        native_action,
    ) = _nonhermitian_residual_case()
    assert not np.allclose(projection, coupling.conj().T)
    facts = augmented_residual_identity(
        native,
        top,
        port,
        carrier,
        rhs_norm=np.linalg.norm(rhs),
        native_action_norm=np.linalg.norm(native_action),
    )
    assert facts["passed"]
    assert facts["uses_conjugate_transpose_for_D"] is False
    np.testing.assert_allclose(
        native,
        top - coupling @ np.linalg.solve(diagonal, port),
        rtol=1e-13,
        atol=1e-13,
    )
    # V14 stores the same residual with the opposite sign:
    # [A4*c-g, -D*c+H*alpha].  The identity is linear, so both orientations
    # must agree when the native residual uses the matching sign.
    np.testing.assert_allclose(
        native_a4_residual_from_augmented(-top, -port, carrier),
        -native,
        rtol=1e-13,
        atol=1e-13,
    )

    # These are deliberately wrong alternatives.  D is not B^H, and the
    # lower block is -D, so either mistake must fail the independent witness.
    wrong_conjugated_d = top - coupling @ np.linalg.solve(
        diagonal, projection.conj() @ c - diagonal @ alpha
    )
    wrong_port_sign = top + coupling @ np.linalg.solve(diagonal, port)
    with pytest.raises(AssertionError):
        np.testing.assert_allclose(wrong_conjugated_d, native, rtol=1e-13, atol=1e-13)
    with pytest.raises(AssertionError):
        np.testing.assert_allclose(wrong_port_sign, native, rtol=1e-13, atol=1e-13)


def test_augmented_residual_identity_zero_linearity_repeat_and_input_immutability():
    _, _, _, _, _, _, top, port, _, carrier, _, _ = _nonhermitian_residual_case()
    top_before, port_before = top.copy(), port.copy()
    zero = augmented_residual_identity(
        np.zeros_like(top),
        np.zeros_like(top),
        np.zeros_like(port),
        carrier,
        rhs_norm=0.0,
        native_action_norm=0.0,
    )
    assert zero["passed"]
    assert zero["absolute_difference"] == 0.0
    assert zero["relative"] == 0.0

    top2 = np.array([-0.4 + 0.3j, 0.5 - 0.2j, 0.15 + 0.6j], dtype=np.complex128)
    port2 = np.array([0.25 - 0.1j, -0.2 + 0.4j], dtype=np.complex128)
    first = native_a4_residual_from_augmented(top, port, carrier)
    second = native_a4_residual_from_augmented(top2, port2, carrier)
    combined = native_a4_residual_from_augmented(top + top2, port + port2, carrier)
    np.testing.assert_allclose(combined, first + second)
    np.testing.assert_array_equal(top, top_before)
    np.testing.assert_array_equal(port, port_before)
    np.testing.assert_array_equal(
        native_a4_residual_from_augmented(top, port, carrier), first
    )


def test_augmented_residual_identity_roundoff_uses_rhs_and_action_scale():
    case = _nonhermitian_residual_case()
    native, carrier, rhs, native_action = case[8], case[9], case[10], case[11]
    perturbed = native.copy()
    perturbed[0] += 2.0e-12j
    facts = augmented_residual_identity(
        perturbed,
        case[6],
        case[7],
        carrier,
        rhs_norm=np.linalg.norm(rhs),
        native_action_norm=np.linalg.norm(native_action),
    )
    assert facts["operation_scale"] >= np.linalg.norm(rhs) + np.linalg.norm(native_action)
    assert facts["passed"]
    assert facts["relative"] < 1.0e-10


@pytest.mark.parametrize("level", (4, 6))
def test_saved_real_native_map_packet_is_checked_when_available(level):
    from src.runners.physical_diagnostic_completion import load_packet

    path = Path(
        "benchmarks/artifacts/task39extra/v5_balanced/"
        "c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/"
        f"native_constraint_map_p{level}.json"
    )
    if not path.is_file():
        pytest.skip("frozen V5 map artifact is not present in this checkout")
    packet = load_packet(path)
    current = {key: packet[key].copy() for key in _map_fixture()}
    facts = compare_native_map_identity(current, packet, context=f"saved p{level} map")
    assert facts["status"] == "PASS"


def test_configured_blr_factory_destroys_factor_on_control_error(monkeypatch):
    import src.solvers.fullspace_v17_p3_oracle as oracle

    state = {}

    class FailingFactor:
        def __init__(self, matrix):
            state["matrix"] = matrix
            state["destroyed"] = False

        def configure_blr(self):
            raise RuntimeError("synthetic public-control failure")

        def destroy(self):
            state["destroyed"] = True

    monkeypatch.setattr(oracle, "MumpsBLRFactor", FailingFactor)
    with pytest.raises(RuntimeError, match="synthetic public-control failure"):
        oracle.configured_mumps_blr_factor(object())
    assert state["destroyed"] is True


def test_configured_blr_factory_uses_existing_prepare_factor_hook():
    """The S1/S2 adapter reuses one generic factor lifecycle and ledger."""

    from petsc4py import PETSc
    from src.solvers.fullspace_v17_p3_oracle import configured_mumps_blr_factor
    from src.solvers.physical_interface_schur import _prepare_factor

    matrix = PETSc.Mat().createAIJ((3, 3), nnz=1, comm=PETSc.COMM_SELF)
    factor = None
    try:
        for index, value in enumerate((2.0 + 1.0j, 3.0 - 0.5j, 4.0 + 0.25j)):
            matrix.setValue(index, index, value)
        matrix.assemble()
        factor, facts = _prepare_factor(
            matrix,
            configured_mumps_blr_factor,
            label="tiny_v16_blr",
        )
        assert factor.symbolic_calls == 1
        assert factor.numeric_calls == 1
        assert factor.solve_calls == 0
        assert facts["backend_control_facts"]["profile"] == (
            "physical_p4_blr_bal_h_v16"
        )
        assert facts["backend_statistics"]["compression_ratio"] is None
        assert facts["backend_statistics"]["compression_stats_status"] in {
            "RAW_NATIVE_FIELDS_AVAILABLE",
            "COMPRESSION_STATS_UNAVAILABLE",
        }
    finally:
        if factor is not None:
            factor.destroy()
        matrix.destroy()


def test_mumps_blr_tiny_factor_controls_and_one_solve_per_action():
    """A tiny live factor is S0 API coverage, not model qualification."""

    from petsc4py import PETSc
    from src.solvers.fullspace_v17_p3_oracle import MumpsBLRFactor

    matrix = PETSc.Mat().createAIJ((3, 3), nnz=1, comm=PETSc.COMM_SELF)
    factor = ordinary = None
    rhs = solution = None
    try:
        for index, value in enumerate((2.0 + 1.0j, 3.0 - 0.5j, 4.0 + 0.25j)):
            matrix.setValue(index, index, value)
        matrix.assemble()
        from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

        ordinary = _MumpsFactor(matrix)
        assert ordinary.get_icntl(35) == 0
        assert ordinary.get_icntl(10) == 0
        ordinary.destroy()
        ordinary = None

        factor = MumpsBLRFactor(matrix)
        with pytest.raises(RuntimeError, match="pre-symbolic"):
            factor.symbolic(matrix)
        controls = factor.configure_blr()
        assert controls["configured_before_symbolic"] is True
        assert controls["effective_after"]["35"]["value"] == 2
        assert controls["effective_after"]["10"]["value"] == 0
        assert controls["cntl_after"]["7"]["value"] == pytest.approx(1.0e-5)
        assert controls["default_controls_frozen"]["36"]["value"] == 0
        with pytest.raises(RuntimeError, match="only once"):
            factor.configure_blr()
        factor.symbolic(matrix)
        assert factor.get_icntl(35) == 2
        assert factor.get_icntl(10) == 0
        assert factor.get_cntl(7) == pytest.approx(1.0e-5)
        assert factor.blr_control_facts["default_controls_frozen"]["36"]["value"] == 0
        assert factor.blr_control_facts["default_controls_frozen"]["38"]["value"] == 600
        factor.numeric(matrix)
        assert factor.get_icntl(35) == 2
        assert factor.get_icntl(10) == 0
        assert factor.get_cntl(7) == pytest.approx(1.0e-5)
        numeric_after = factor.blr_control_facts["effective_after_numeric"]
        assert numeric_after["stage"] == "numeric_after"
        assert numeric_after["icntl"]["35"]["value"] == 2
        assert numeric_after["icntl"]["10"]["value"] == 0
        assert numeric_after["cntl"]["7"]["value"] == pytest.approx(1.0e-5)
        statistics = factor.blr_statistics()
        assert statistics["compression_ratio"] is None
        assert statistics["compression_stats_status"] in {
            "RAW_NATIVE_FIELDS_AVAILABLE",
            "COMPRESSION_STATS_UNAVAILABLE",
        }
        owned_vectors = []

        def solve_action(values):
            local_rhs = matrix.createVecRight()
            local_solution = matrix.createVecRight()
            owned_vectors.extend((local_rhs, local_solution))
            local_rhs.array[:] = values
            before_values = local_rhs.array.copy()
            facts = factor.solve_once(local_rhs, local_solution)
            assert facts["factor_solve_call_delta"] == 1
            assert facts["controls_after_solve"]["stage"] == (
                f"solve_{factor.solve_calls}_after"
            )
            assert facts["controls_after_solve"]["icntl"]["35"]["value"] == 2
            assert facts["controls_after_solve"]["icntl"]["10"]["value"] == 0
            assert facts["controls_after_solve"]["cntl"]["7"]["value"] == pytest.approx(
                1.0e-5
            )
            np.testing.assert_array_equal(local_rhs.array, before_values)
            return local_rhs, local_solution, facts

        values_a = np.asarray(
            (1.0 + 2.0j, -0.25j, 0.5 - 0.75j), dtype=np.complex128
        )
        values_b = np.asarray(
            (-0.5 + 0.25j, 1.5 - 0.3j, 0.1 + 0.4j), dtype=np.complex128
        )
        rhs_a, solution_a, facts_a = solve_action(values_a)
        _rhs_zero, solution_zero, _facts_zero = solve_action(np.zeros(3, dtype=complex))
        np.testing.assert_allclose(solution_zero.array, 0.0, atol=1.0e-14, rtol=0.0)
        _rhs_repeat, solution_repeat, _facts_repeat = solve_action(values_a)
        np.testing.assert_allclose(solution_repeat.array, solution_a.array, atol=1.0e-14, rtol=0.0)
        _rhs_b, solution_b, facts_b = solve_action(values_b)
        _rhs_combo, solution_combo, _facts_combo = solve_action(values_a + 2.0 * values_b)
        np.testing.assert_allclose(
            solution_combo.array,
            solution_a.array + 2.0 * solution_b.array,
            atol=1.0e-14,
            rtol=0.0,
        )
        checked = matrix.createVecLeft()
        owned_vectors.append(checked)
        matrix.mult(solution_combo, checked)
        checked.axpy(-1.0, _rhs_combo)
        assert checked.norm() / _rhs_combo.norm() < 1.0e-14
        assert factor.solve_calls == 5
        assert factor.blr_control_facts["solve_control_readback_latest"]["stage"] == (
            "solve_5_after"
        )
        assert factor.blr_control_facts["solve_control_readback_latest"]["icntl"]["35"][
            "value"
        ] == 2
        assert facts_a["factor_solve_call_delta"] == facts_b["factor_solve_call_delta"] == 1
        assert factor.symbolic_calls == 1
        assert factor.numeric_calls == 1
        factor.destroy()
        for value in owned_vectors:
            if getattr(value, "handle", 0):
                value.destroy()
        owned_vectors.clear()
        with pytest.raises(RuntimeError, match="live factor"):
            factor.get_icntl(35)
    finally:
        for value in locals().get("owned_vectors", []):
            if value is not None and getattr(value, "handle", 0):
                value.destroy()
        if ordinary is not None:
            ordinary.destroy()
        if factor is not None:
            factor.destroy()
        matrix.destroy()


def test_q1_bridge_recomputes_parent_watchdog_and_summary_scope_without_pde(monkeypatch, tmp_path):
    """The historical S1 bridge uses raw Q1 evidence and does not rerun it."""

    from src.runners import physical_p4_blr_v16 as worker

    monkeypatch.setattr(worker, "_save_packet", lambda *args, **kwargs: {})
    runtime = SimpleNamespace(
        source_sha="a" * 40,
        directory=tmp_path,
        marker=lambda *_args, **_kwargs: None,
    )
    result = worker.bridge_q1_baseline(Path(__file__).parents[2], runtime)
    assert result["passed"]
    assert result["checks"]["raw_rhs_packets"]
    resources = result["checks"]["raw_resource_window"]
    assert resources["scope"] == "parent_watchdog_process_tree"
    assert resources["full"]["rss_peak_bytes"] == 2825973760
    assert resources["window"]["sample_count"] == 75
    assert result["checks"]["summary_rhs_order"]


def test_v16_ledger_is_independent_and_preserves_v14_unknown_accounting(tmp_path):
    from src.runners.task038_launcher import (
        V16_PREDECESSOR_V14_LEDGER_SHA256,
        _reserve_blr_v16_shared_budget,
    )

    repository = tmp_path / "repo"
    predecessor = (
        repository
        / "benchmarks"
        / "artifacts"
        / "task39extra"
        / "p4_schur_v14"
        / "review_v14"
        / "shared_workflow_ledger.json"
    )
    predecessor.parent.mkdir(parents=True)
    source_predecessor = (
        Path(__file__).parents[2]
        / "benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json"
    )
    predecessor.write_bytes(source_predecessor.read_bytes())
    lease = _reserve_blr_v16_shared_budget(
        repository,
        tmp_path / "run",
        source_sha="b" * 40,
        stage="S2_BLR_CONTROL",
        stage_budget={"workflow_seconds": 14400},
        workflow_clock_start={"monotonic": 1.0, "boottime": 1.0, "utc_ns": 1},
        time_policy="observe_only",
    )
    ledger_path = Path(lease["path"])
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["batch_identity"] == "review_v16_p4_blr"
    assert ledger["elapsed_seconds"] == 0.0
    assert ledger["predecessor_v14_ledger"]["read_only"] is True
    assert ledger["predecessor_v14_ledger"]["sha256"] == V16_PREDECESSOR_V14_LEDGER_SHA256
    assert ledger["predecessor_v14_ledger"]["unknown_elapsed_is_not_new_measurement"] is True
    assert ledger["predecessor_v14_ledger"]["unknown_elapsed_attempts"]


def test_v16_replay_requires_failed_worker_summary_and_rejects_numeric_negative(tmp_path):
    from src.runners.task038_launcher import (
        _reserve_blr_v16_shared_budget,
        _settle_v14_shared_budget,
    )

    source_root = Path(__file__).parents[2]
    source_predecessor = (
        source_root
        / "benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json"
    )

    def prepare(label: str, status: str, result_classification: str):
        repository = tmp_path / label / "repo"
        predecessor = (
            repository
            / "benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json"
        )
        predecessor.parent.mkdir(parents=True)
        predecessor.write_bytes(source_predecessor.read_bytes())
        failed_directory = tmp_path / label / "failed"
        lease = _reserve_blr_v16_shared_budget(
            repository,
            failed_directory,
            source_sha="b" * 40,
            stage="S2_BLR_CONTROL",
            stage_budget={"workflow_seconds": 14400},
            workflow_clock_start={"monotonic": 1.0, "boottime": 1.0, "utc_ns": 1},
            time_policy="observe_only",
        )
        _settle_v14_shared_budget(
            lease,
            status=status,
            authority=None,
            parent_interval={"budget_seconds": 1.0},
            parent_clock_end={},
        )
        failed_directory.mkdir(parents=True, exist_ok=True)
        (failed_directory / "implementation_bug_replay.json").write_text(
            json.dumps(
                {
                    "classification": "IMPLEMENTATION_BUG",
                    "stage": "S2_BLR_CONTROL",
                    "failed_source_sha": "b" * 40,
                    "fixed_source_sha": "c" * 40,
                    "bug_and_fix": "targeted synthetic replay evidence",
                }
            ),
            encoding="utf-8",
        )
        (failed_directory / "physical_p4_blr_v16_summary.json").write_text(
            json.dumps(
                {
                    "status": "FAILED" if result_classification == "WORKER_FAILED" else status,
                    "result_classification": result_classification,
                    "source_sha": "b" * 40,
                    "error": {"type": "RuntimeError", "message": "synthetic"},
                }
            ),
            encoding="utf-8",
        )
        return repository, failed_directory

    repository, _failed = prepare("worker_exception", "WORKER_FAILED", "WORKER_FAILED")
    replay = _reserve_blr_v16_shared_budget(
        repository,
        tmp_path / "worker_exception" / "fixed",
        source_sha="c" * 40,
        stage="S2_BLR_CONTROL",
        stage_budget={"workflow_seconds": 14400},
        workflow_clock_start={"monotonic": 2.0, "boottime": 2.0, "utc_ns": 2},
        time_policy="observe_only",
    )
    assert replay["replay"] is True
    assert replay["replay_evidence"]["worker_summary_result_classification"] == "WORKER_FAILED"

    repository, _failed = prepare(
        "numeric_negative", "S2_BLR_CONTROL_REJECTED", "NUMERICAL_GATE_REJECTED"
    )
    with pytest.raises(ValueError, match="genuine worker exception"):
        _reserve_blr_v16_shared_budget(
            repository,
            tmp_path / "numeric_negative" / "fixed",
            source_sha="c" * 40,
            stage="S2_BLR_CONTROL",
            stage_budget={"workflow_seconds": 14400},
            workflow_clock_start={"monotonic": 2.0, "boottime": 2.0, "utc_ns": 2},
            time_policy="observe_only",
        )
