"""Explicit stage isolation and archive/canonical-coordinate adapters; no JIT."""

from types import SimpleNamespace

import numpy as np

from src.io import load_and_resolve
from src.io.task042_profile import TASK042_PROFILES
from src.runners.task042_localization import canonical_from_storage, teacher_row


def test_v5_profiles_keep_original_physics_and_old_default():
    ordinary = load_and_resolve(
        "input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat"
    )
    for label, stage in (
        ("d0", "V5-D0"),
        ("d1", "V5-D1"),
        ("oldpod", "V5-OLDPOD"),
        ("error", "V5-ERROR"),
    ):
        case = load_and_resolve(
            f"input/task042_neural_coarse_inverse/v5_{label}_shared.dat"
        )
        assert case.physical_model_sha256 == ordinary.physical_model_sha256
        assert TASK042_PROFILES[case.solver["preconditioner"]] == stage
        assert case.execution["mpi_size"] == 1
        assert case.execution["terminate_memory_gib"] == 16
    assert ordinary.solver["preconditioner"] == "balanced_h6_p4_v5"


def test_selected_teacher_row_does_not_load_all_answer_rows(tmp_path, monkeypatch):
    path = tmp_path / "teacher.npz"
    solution = np.arange(32 * 7).reshape(32, 7).astype(np.complex128) * (1 + 2j)
    scales = np.arange(32, dtype=float) + 1
    np.savez(path, solution=solution, normalization_scale=scales)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("do not use np.load to materialize all teacher answers")

    monkeypatch.setattr(np, "load", forbidden)
    for row in (0, 10, 11):
        np.testing.assert_array_equal(teacher_row(path, "solution", row), solution[row])
        assert float(teacher_row(path, "normalization_scale", row)) == scales[row]


def test_canonical_extraction_uses_master_map_and_all_port_rows():
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.array([4, 1, 7]),
        original_to_active={4: 2, 1: 0, 7: 1},
    )
    action = SimpleNamespace(
        reduced_size=5,
        condensed=SimpleNamespace(active_rows=3, trace_constraints=constraints),
    )
    field = np.arange(10).astype(np.complex128) * (1 + 0.2j)
    port = np.array([3j, -2 + 4j], dtype=np.complex128)
    np.testing.assert_array_equal(
        canonical_from_storage(action, field, port), np.r_[field[[1, 7, 4]], port]
    )
