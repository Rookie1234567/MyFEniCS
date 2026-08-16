"""Focused pure contracts for the W18A nested auxiliary action."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from src.solvers import hcurl_m6b_w16_global_shifted_inner_pc as w16
from src.solvers import hcurl_m6b_w18_nested_auxiliary_pc as w18


def _outer_audit() -> dict[str, object]:
    return {
        "algorithm": "right_flexible_gmres",
        "max_steps": 2,
        "iterations": 2,
        "checkpoint_iterations": [1, 2],
        "checkpoint_count": 2,
        "observer_count": 2,
        "action_count": 4,
        "pc_count": 2,
        "initial_action_count": 0,
        "mmap": False,
        "basis_in_memory": False,
        "checkpoint_set_complete": True,
    }


def _checkpoint(iteration: int, solution: str, action: str) -> dict[str, object]:
    return {
        "iteration": iteration,
        "finite": True,
        "solution_sha256": solution * 64,
        "action_sha256": action * 64,
        "true_relative_residual": 0.008,
        "solution_relative_difference": 0.0,
        "action_relative_difference": 0.0,
    }


def _measurement(iteration: int, rho: float) -> dict[str, object]:
    return {
        "schema": w18.W18A_SCHEMA,
        "checkpoint": iteration,
        "finite": True,
        "rho": rho,
        "normal_closure": 0.0,
        "projection_orthogonality": 0.0,
    }


def _repeat(index: int) -> dict[str, object]:
    return {
        "repeat_index": index,
        "outer_audit": _outer_audit(),
        "inner_records": [
            {
                "schema": w18.W18A_INNER_SCHEMA,
                "algorithm": (
                    "fgmres_right_shifted_beta1_composed_fixed20_plus20"
                ),
                "finite": True,
                "final_relative_residual": 0.008,
            },
            {
                "schema": w18.W18A_INNER_SCHEMA,
                "algorithm": (
                    "fgmres_right_shifted_beta1_composed_fixed20_plus20"
                ),
                "finite": True,
                "final_relative_residual": 0.009,
            },
        ],
        "checkpoints": {
            "1": _checkpoint(1, "1", "3"),
            "2": _checkpoint(2, "2", "4"),
        },
        "measurements": {
            "1": _measurement(1, w18.W18A_RHO1_ANCHOR),
            "2": _measurement(2, 0.80),
        },
    }


def _summary() -> dict[str, object]:
    return {
        "schema": w18.W18A_SCHEMA,
        "fixed_identity": deepcopy(w18.W18A_FIXED_IDENTITY),
        "repeats": [_repeat(1), _repeat(2)],
        "action_counts": deepcopy(w18.W18A_ACTION_COUNTS),
        "architecture": deepcopy(w18.W18A_ARCHITECTURE),
        "lifecycle": deepcopy(w18.W18A_LIFECYCLE),
        "prediction": {
            "bytes": w18.W18A_PREDICTED_LIVE_SET_BYTES,
            "limit_bytes": w18.W18A_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "watchdog_limit_bytes": w18.W18A_WATCHDOG_LIMIT_BYTES,
            "derived_not_measured": True,
            "swap_bytes": 0,
        },
    }


def test_wrapper_binds_outer_b_and_inner_s(monkeypatch, tmp_path: Path) -> None:
    shifted = lambda values: 2.0 * np.asarray(values)
    dtn = lambda values: 0.25 * np.asarray(values)
    local_pc = lambda values: np.asarray(values).copy()
    captured: dict[str, object] = {}

    def fake_outer(
        outer_action,
        auxiliary_action,
        pc,
        rhs,
        scratch_dir,
        observer=None,
    ):
        captured.update(
            {
                "outer": outer_action,
                "inner": auxiliary_action,
                "pc": pc,
                "rhs": rhs,
                "scratch_dir": scratch_dir,
                "observer": observer,
            }
        )
        probe = np.ones(3, dtype=np.complex128)
        assert np.array_equal(outer_action(probe), shifted(probe) + dtn(probe))
        return "result", "composed"

    monkeypatch.setattr(w16, "run_w16b_outer2", fake_outer)
    rhs = np.ones(3, dtype=np.complex128)
    assert w18.run_w18a_outer2(shifted, dtn, local_pc, rhs, tmp_path) == (
        "result",
        "composed",
    )
    assert captured["inner"] is shifted
    assert captured["pc"] is local_pc
    assert captured["rhs"] is rhs
    assert captured["scratch_dir"] == tmp_path


def test_wrapper_inherits_fixed_outer2_contract(tmp_path: Path) -> None:
    shifted_matrix = np.array(
        [
            [2 + 0.1j, 0.4 - 0.1j, 0, 0],
            [0.1 + 0.2j, 2.3 + 0.2j, 0.3, 0],
            [0, -0.2j, 1.8 + 0.3j, 0.5],
            [0.2, 0, 0.1 + 0.1j, 2.1 - 0.2j],
        ],
        dtype=np.complex128,
    )
    dtn_matrix = np.array(
        [
            [0.2, 0.1j, 0, 0],
            [0, 0.15, -0.05j, 0],
            [0, 0, 0.1, 0.08],
            [0.03j, 0, 0, 0.12],
        ],
        dtype=np.complex128,
    )
    shifted = lambda values: shifted_matrix @ np.asarray(values)
    dtn = lambda values: dtn_matrix @ np.asarray(values)
    local_pc = lambda values: np.asarray(values).copy()
    rhs = np.array([1 + 0.2j, 0.3 - 0.1j, 1.2 + 0.4j, -0.2 + 0.5j])
    result, composed = w18.run_w18a_outer2(
        shifted, dtn, local_pc, rhs, tmp_path / "screen"
    )

    assert result.audit["max_steps"] == 2
    assert result.audit["checkpoint_iterations"] == [1, 2]
    assert result.audit["action_count"] == 4
    assert result.audit["pc_count"] == 2
    assert composed.apply_count == 2
    assert len(composed.records) == 2


def test_w18a_action_gate_passes_complete_fixture() -> None:
    report = w18.evaluate_w18a_action_gate(_summary())
    assert report["pass"] is True
    assert all(type(value) is bool and value for value in report["checks"].values())


@pytest.mark.parametrize(
    "tamper, expected_check",
    [
        (
            lambda value: value["repeats"][0]["inner_records"][1].update(
                {"final_relative_residual": 0.010001}
            ),
            "inner_residual",
        ),
        (
            lambda value: value["repeats"][0]["measurements"]["2"].update(
                {"rho": 0.850001}
            ),
            "measurements",
        ),
        (
            lambda value: value["repeats"][1]["checkpoints"]["2"].update(
                {"true_relative_residual": 0.010001}
            ),
            "outer_auxiliary_residual",
        ),
        (
            lambda value: value["repeats"][1]["checkpoints"]["2"].update(
                {"solution_sha256": "f" * 64}
            ),
            "repeat_identity",
        ),
        (
            lambda value: value["action_counts"].update(
                {"shifted_action_total_count": 339}
            ),
            "action_counts",
        ),
        (
            lambda value: value["fixed_identity"].update(
                {"auxiliary_dtn_used": False}
            ),
            "fixed_identity",
        ),
        (
            lambda value: value["lifecycle"].update(
                {"shared_dtn_instance_count": 2}
            ),
            "lifecycle",
        ),
        (
            lambda value: value["prediction"].update(
                {"bytes": w18.W18A_PREDICTED_LIVE_SET_LIMIT_BYTES + 1}
            ),
            "prediction",
        ),
    ],
    ids=(
        "inner-residual",
        "rho",
        "outer-residual",
        "repeat-hash",
        "counts",
        "identity",
        "lifecycle",
        "prediction",
    ),
)
def test_w18a_action_gate_fails_closed_on_key_tamper(tamper, expected_check) -> None:
    summary = _summary()
    tamper(summary)
    report = w18.evaluate_w18a_action_gate(summary)
    assert report["pass"] is False
    assert report["checks"][expected_check] is False
    assert expected_check in report["problems"]


def test_w16b_contract_constants_remain_unchanged() -> None:
    assert w16.W16B_MAX_STEPS == 2
    assert w16.W16B_CHECKPOINTS == (1, 2)
    assert w16.W16B_RHO1_ANCHOR == w18.W18A_RHO1_ANCHOR
    assert w16.W16B_RHO2_LIMIT == pytest.approx(np.sqrt(0.75))
