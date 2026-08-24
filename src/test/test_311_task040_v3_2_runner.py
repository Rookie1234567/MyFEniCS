"""Focused V3-2 hydration and zero-start screen contracts."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task040_level_a import (
    TASK040_V3_2_COUPLED_INTERFACE_FLAG,
    build_task040_level_a_plan,
)
from benchmarks.task040_level_a_watchdog import (
    _worker_command,
    build_task040_level_a_watchdog_plan,
)
from src.solvers.hybrid_interface_fgmres import (
    _checkpoint_gate,
    _phase1_trend_gate,
    _phase2_trend_gate,
    audit_v3_full_side_one_apply,
    decide_v3_continuation,
    run_v3_full_span_right_fgmres_batch,
)
from src.solvers.hybrid_interface_basis import build_group_basis_columns
from src.solvers.hybrid_interface_packet import (
    recover_owner_local_y_from_packet_v,
    transfer_right_basis_to_packet_gram,
)
from src.solvers.hybrid_side_impedance import _petsc_matrix_hash
from src.test.test_310_task040_petsc_full_side_coupled import (
    _carrier,
    _fixture,
    _petsc_matrix,
    _petsc_vector,
)


def _dense_operator(size: int = 20) -> PETSc.Mat:
    rows = np.arange(size, dtype=float)[:, None]
    cols = np.arange(size, dtype=float)[None, :]
    values = (0.013 * (rows + 1.0) + 0.021j * (cols + 1.0)).astype(np.complex128)
    values += np.diag(1.7 + 0.03j * np.arange(size))
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


def _global_vector(matrix: PETSc.Mat, seed: int) -> PETSc.Vec:
    vector = matrix.createVecRight()
    first, last = map(int, vector.getOwnershipRange())
    values = (0.4 + 0.07j) * (np.arange(vector.getSize()) + seed + 1)
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


class _TinyRightAction:
    def __init__(self, scale: complex = 0.65 + 0.08j) -> None:
        self.scale = scale
        self.apply_count = 0

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.set(0.0)
        target.axpy(PETSc.ScalarType(self.scale), source)
        target.assemble()
        self.apply_count += 1


def test_packet_v_recovers_y_and_rejects_u_semantics() -> None:
    rng = np.random.default_rng(11)
    gram = np.asarray(
        [[1.2 + 0.2j, 0.3 - 0.1j], [0.1 + 0.4j, 1.7 - 0.3j]],
        dtype=np.complex128,
    )
    y = rng.normal(size=(5, 2)) + 1j * rng.normal(size=(5, 2))
    v = y @ np.linalg.inv(gram.conj().T)
    observed = recover_owner_local_y_from_packet_v(v, gram)
    assert np.linalg.norm(observed - y) / np.linalg.norm(y) <= 1.0e-12
    with pytest.raises(ValueError, match="complex128"):
        recover_owner_local_y_from_packet_v(v.real, gram)
    with pytest.raises(ValueError, match="complex128"):
        recover_owner_local_y_from_packet_v(np.asarray(v, dtype=np.complex64), gram)
    u = rng.normal(size=(5, 2)) + 1j * rng.normal(size=(5, 2))
    false_y = recover_owner_local_y_from_packet_v(u, gram)
    assert np.linalg.norm(false_y - y) / np.linalg.norm(y) > 1.0e-3


def test_packet_v_conditioning_diagnostic_and_direct_group_y_authority() -> None:
    rng = np.random.default_rng(31)
    gram = np.diag(np.asarray([1.0, 1.0e-6, 0.4 + 0.2j, 0.7 - 0.1j])).astype(
        np.complex128
    )
    y = rng.normal(size=(9, 4)) + 1j * rng.normal(size=(9, 4))
    u, singular_values, vh = np.linalg.svd(gram)
    x = vh.conj().T @ ((u.conj().T @ y.conj().T) / singular_values[:, None])
    packet_v = x.conj().T
    recovered = recover_owner_local_y_from_packet_v(packet_v, gram)
    relative = np.linalg.norm(recovered - y) / np.linalg.norm(y)
    assert np.isfinite(relative)
    assert relative < 1.0e-8
    assert singular_values[0] / singular_values[-1] >= 1.0e6

    lower_rows = np.asarray([10, 12])
    upper_rows = np.asarray([11, 13])
    group_rows = np.asarray([12, 11, 13, 10])
    lower_y = np.asarray(
        [[1.0 + 0.2j, 2.0 - 0.1j], [3.0 + 0.4j, 4.0 + 0.3j]],
        dtype=np.complex128,
    )
    upper_y = np.asarray(
        [[5.0 - 0.2j, 6.0 + 0.1j], [7.0 + 0.5j, 8.0 - 0.4j]],
        dtype=np.complex128,
    )
    direct = build_group_basis_columns(
        1, group_rows, lower_rows, lower_y, upper_rows, upper_y
    )
    expected = np.zeros((4, 4), dtype=np.complex128)
    expected[0, :2] = lower_y[1]
    expected[1, 2:] = upper_y[0]
    expected[2, 2:] = upper_y[1]
    expected[3, :2] = lower_y[0]
    assert np.array_equal(direct, expected)


def test_packet_dual_right_transfer_nonunitary_complex_and_rank_gate() -> None:
    rng = np.random.default_rng(47)
    lower = np.asarray(
        [[1.4 + 0.2j, 0.3 - 0.1j], [0.1 + 0.4j, 1.8 - 0.3j]],
        dtype=np.complex128,
    )
    upper = np.asarray(
        [
            [1.2 - 0.1j, 0.2 + 0.3j, 0.1 - 0.2j],
            [0.4 + 0.1j, 1.6 + 0.2j, 0.3 + 0.4j],
            [0.2 - 0.3j, 0.1 + 0.2j, 1.1 + 0.5j],
        ],
        dtype=np.complex128,
    )
    gram = np.zeros((5, 5), dtype=np.complex128)
    gram[:2, :2] = lower
    gram[2:, 2:] = upper
    transfer = np.zeros_like(gram)
    transfer[:2, :2] = np.asarray(
        [[1.1 + 0.2j, 0.4 - 0.1j], [0.0 + 0.3j, 0.9 - 0.2j]],
        dtype=np.complex128,
    )
    transfer[2:, 2:] = np.asarray(
        [
            [1.0 + 0.1j, 0.2, 0.0],
            [0.1 - 0.2j, 0.8 + 0.2j, 0.3],
            [0.0 + 0.1j, 0.0, 1.2 - 0.1j],
        ],
        dtype=np.complex128,
    )
    cross = gram @ np.linalg.inv(transfer)
    current_z = rng.normal(size=(7, 5)) + 1j * rng.normal(size=(7, 5))
    aligned, diagnostics = transfer_right_basis_to_packet_gram(
        gram,
        cross,
        np.asarray(current_z, dtype=np.complex128),
        lower_span=2,
        upper_span=3,
    )
    assert (
        np.linalg.norm(aligned - current_z @ transfer) / np.linalg.norm(aligned)
        <= 1e-12
    )
    assert diagnostics["schema"] == "task040.v3.packet_dual_right_transfer.v1"
    assert diagnostics["post_gram_relative_error"] <= 1e-12
    assert diagnostics["post_block_relative_errors"]["LU"] <= 1e-12
    assert diagnostics["right_transfer"]["offdiagonal_norm"] == {"LU": 0.0, "UL": 0.0}
    singular_cross = cross.copy()
    singular_cross[:2, :2] = 0.0
    with pytest.raises(ValueError, match="right-transfer LL rank"):
        transfer_right_basis_to_packet_gram(
            gram,
            singular_cross,
            np.asarray(current_z, dtype=np.complex128),
            lower_span=2,
            upper_span=3,
        )


def test_v3_fgmres_has_zero_start_and_frozen_checkpoint_shape() -> None:
    matrix = _dense_operator()
    rhs = {f"source_{index}": _global_vector(matrix, index) for index in range(5)}
    action = _TinyRightAction()
    try:
        result = run_v3_full_span_right_fgmres_batch(
            matrix,
            rhs,
            action,
            labels=tuple(rhs),
            resource_callback=lambda: {"pass": True, "rss_bytes": 1},
        )
        assert result["schema"] == "task040.v3_2.full_span_right_fgmres.v1"
        assert result["ksp_setup_count"] == 1
        assert result["ksp_destroy_count"] == 1
        assert result["zero_initial_guess_all_rhs"] is True
        for phase_name in ("phase1", "phase2", "phase3"):
            for row in result[phase_name].values():
                assert (
                    row["max_it"] == row["iterations"] or row["happy_breakdown"] is True
                )
                assert row["postsolve_true_residual_finite"] is True
                assert row["elapsed_seconds"] >= 0.0
                assert row["final_iteration"] == row["iterations"]
                assert (
                    row["missing_checkpoints"] == [] or row["happy_breakdown"] is True
                )
        for row in result["phase1"].values():
            assert set(row["checkpoints"]) >= {"0", "4", "8", "16"}
            assert row["checkpoints"]["0"]["true_residual_relative"] == pytest.approx(
                1.0
            )
            assert row["zero_initial_guess"] is True
    finally:
        for vector in rhs.values():
            vector.destroy()
        matrix.destroy()


def test_v3_checkpoint_decisions_are_independent_of_worker_status() -> None:
    labels = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "random0",
        "random1",
    )

    def rows(r4: float, r8: float, r16: float) -> dict[str, object]:
        return {
            "checkpoints": {
                str(index): {"finite": True, "true_residual_relative": value}
                for index, value in ((4, r4), (8, r8), (16, r16))
            },
            "ksp_breakdown": False,
        }

    phase = {label: rows(0.5, 0.2, 0.1) for label in labels}
    assert _phase1_trend_gate(phase, labels) == {label: True for label in labels}
    assert _checkpoint_gate(phase, labels, "16") is False
    for label in labels[:3]:
        phase[label]["checkpoints"]["16"]["true_residual_relative"] = 1.0e-3
    for label in labels[3:]:
        phase[label]["checkpoints"]["16"]["true_residual_relative"] = 5.0e-3
    assert _checkpoint_gate(phase, labels, "16") is True


@pytest.mark.parametrize("checkpoint", ("4", "8", "16"))
def test_v3_early_preferred_checkpoint_is_derived(checkpoint: str) -> None:
    labels = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "random0",
        "random1",
    )
    phase = {}
    for label in labels:
        phase[label] = {
            "ksp_breakdown": False,
            "checkpoints": {
                index: {
                    "finite": True,
                    "true_residual_relative": (
                        5.0e-4 if label in labels[:3] else 5.0e-3
                    )
                    if index == checkpoint
                    else 0.2,
                }
                for index in ("4", "8", "16")
            },
        }
    decision = decide_v3_continuation(
        phase,
        {},
        {},
        labels=labels,
        resource1={"pass": True},
        resource2=None,
    )
    assert decision["first_preferred_checkpoint"] == int(checkpoint)
    assert decision["conditional_32_authorized"] is False


def test_v3_phase2_pass_stops_before_64_and_nonfinite_last16_fails() -> None:
    labels = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "random0",
        "random1",
    )

    def phase1_row(label: str) -> dict[str, object]:
        return {
            "ksp_breakdown": False,
            "checkpoints": {
                str(index): {
                    "finite": True,
                    "true_residual_relative": 0.6 / (index + 1),
                }
                for index in (4, 8, 16)
            },
        }

    phase1 = {label: phase1_row(label) for label in labels}

    def phase2_row(value: float, bad: int | None = None) -> dict[str, object]:
        history = [
            {"iteration": index, "relative_residual": 0.8 - 0.01 * index}
            for index in range(16, 33)
        ]
        if bad is not None:
            history[bad - 16]["relative_residual"] = float("nan")
        return {
            "ksp_breakdown": False,
            "reported_residual_history": history,
            "checkpoints": {
                "32": {
                    "finite": True,
                    "true_residual_relative": value,
                }
            },
        }

    phase2_pass = {
        label: phase2_row(5.0e-4 if index < 3 else 5.0e-3)
        for index, label in enumerate(labels)
    }
    decision = decide_v3_continuation(
        phase1,
        phase2_pass,
        {},
        labels=labels,
        resource1={"pass": True},
        resource2={"pass": True},
    )
    assert decision["phase2_pass"] is True
    assert decision["conditional_64_authorized"] is False
    assert decision["first_preferred_checkpoint"] == 32

    phase2_64 = {label: phase2_row(0.02) for label in labels}
    decision = decide_v3_continuation(
        phase1,
        phase2_64,
        {},
        labels=labels,
        resource1={"pass": True},
        resource2={"pass": True},
    )
    assert decision["phase2_pass"] is False
    assert decision["conditional_64_authorized"] is True
    assert all(_phase2_trend_gate(phase2_64, labels).values())

    phase3_pass = {
        label: {
            "checkpoints": {
                "64": {
                    "finite": True,
                    "true_residual_relative": (5.0e-4 if index < 3 else 5.0e-3),
                }
            }
        }
        for index, label in enumerate(labels)
    }
    decision = decide_v3_continuation(
        phase1,
        phase2_64,
        phase3_pass,
        labels=labels,
        resource1={"pass": True},
        resource2={"pass": True},
    )
    assert decision["phase3_pass"] is True
    assert decision["first_preferred_checkpoint"] == 64

    phase3_fail = {
        label: {"checkpoints": {"64": {"finite": True, "true_residual_relative": 0.02}}}
        for label in labels
    }
    decision = decide_v3_continuation(
        phase1,
        phase2_64,
        phase3_fail,
        labels=labels,
        resource1={"pass": True},
        resource2={"pass": True},
    )
    assert decision["phase3_pass"] is False

    broken = {label: phase2_row(0.2, bad=20) for label in labels}
    assert not any(_phase2_trend_gate(broken, labels).values())


def test_v3_route_is_opt_in_and_mutually_exclusive(tmp_path) -> None:
    kwargs = {
        "input_path": tmp_path / "input.dat",
        "exact_spool_root": tmp_path / "spool",
        "run_directory": tmp_path / "run",
        "source_sha": "a" * 40,
        "coupled_interface": True,
        "interface_packet_root": tmp_path / "packet",
    }
    plan = build_task040_level_a_plan(**kwargs)
    assert plan["coupled_interface"] is True
    assert plan["qep_calls"] == 0
    assert plan["pde_solve"] == "not_run"
    assert plan["interface_packet_manifest_sha256"]
    assert "outer_ksp" not in plan["forbidden"]
    assert "global_hybrid_outer_ksp" in plan["forbidden"]
    assert TASK040_V3_2_COUPLED_INTERFACE_FLAG == "--v3-2-coupled-interface"
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_plan(**{**kwargs, "packet_consumer": True})


def test_v3_carrier_records_small_coarse_residual_per_apply() -> None:
    data = _fixture()
    matrix = _petsc_matrix(np.asarray(data["full"]))
    action = _carrier(data, matrix, np.asarray(data["joint"]))
    source = _petsc_vector(matrix, np.asarray(data["source"]))
    target = matrix.createVecRight()
    try:
        bare_hash_before = _petsc_matrix_hash(matrix)
        zero = matrix.createVecRight()
        zero_target = matrix.createVecRight()
        zero.set(0.0)
        action.apply(zero, zero_target)
        assert zero.norm() <= 1.0e-13
        assert zero_target.norm() <= 1.0e-13
        action.apply(source, target)
        action.apply(source, target)
        diagnostics = action.diagnostics
        history = diagnostics["coarse_residual_history"]
        assert len(history) == 3
        assert history[0]["rhs_norm"] == pytest.approx(0.0)
        assert [row["apply"] for row in history[-2:]] == [2, 3]
        assert diagnostics["coarse_residual_last_apply"] == pytest.approx(
            history[-1]["relative"]
        )
        assert all(row["finite"] is True for row in history)
        assert _petsc_matrix_hash(matrix) == bare_hash_before
        one_apply = audit_v3_full_side_one_apply(
            action,
            matrix,
            {"source_a": source, "source_b": source},
            labels=("source_a", "source_b"),
            factor_inventory={
                "cross_section_group_factor_count": 3,
                "reduced_dense_factor_count": 1,
                "exact_interface_schur_oracle_object_count": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        )
        assert one_apply["factor_inventory_pass"] is True
        assert one_apply["repeat_pass"] is True
        assert one_apply["linearity_pass"] is True
        assert all(
            row["coarse_residual_finite"] is True
            and row["first_coarse_residual_finite"] is True
            and row["second_coarse_residual_finite"] is True
            and np.isfinite(row["coarse_residual_repeat_relative"])
            and row["coarse_residual_repeat_relative"] <= 1.0e-12
            for row in one_apply["reports"]
        )
    finally:
        zero_target.destroy()
        zero.destroy()
        target.destroy()
        source.destroy()
        action.destroy()
        matrix.destroy()


def test_v3_watchdog_uses_only_the_v3_worker_flag(tmp_path) -> None:
    plan = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "input.dat",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "run",
        source_sha="b" * 40,
        coupled_interface=True,
        interface_packet_root=tmp_path / "packet",
    )
    command = _worker_command(plan)
    assert TASK040_V3_2_COUPLED_INTERFACE_FLAG in command
    assert "--v2-interface-packet-consumer" not in command
    assert plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert plan["coupled_interface"] is True
    assert plan["packet_dependent"] is True
    assert "global_hybrid_outer_ksp" in plan["forbidden"]
