"""Small non-Hermitian V44 opt-in regression; never loads real action or old errors."""

import numpy as np
import pytest
import torch
from scipy.sparse import csr_matrix, eye

from benchmarks.check_neighborhood_late_error import require_inventory
from src.solvers.neighborhood_late_error import (
    choose_checkpoint,
    frozen_reader,
    label_identity,
    late_loss,
)
from src.solvers.neighborhood_residual_core import OriginalCSR, fixed_cleanup
from src.solvers.neighborhood_residual_models import NeighborhoodCorrector
from src.test.test_neighborhood_residual import toy


@pytest.mark.parametrize(
    "complex_linear,real_linear", [(False, False), (False, True), (True, False)]
)
def test_zero_decoder_groups_gradient_and_both_losses(complex_linear, real_linear):
    graph, action = toy()
    model = NeighborhoodCorrector(
        eye(516, dtype=complex),
        graph,
        action.scale,
        linear=complex_linear,
        real_linear=real_linear,
        zero_decoder=True,
    )
    rng = np.random.default_rng(5)
    s = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    d = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    loss, delta, qr, qe = late_loss(
        model, s, d, action, mixed=True, independent=np.arange(516)
    )
    assert torch.count_nonzero(delta) == 0 and torch.all(qr == 1) and torch.all(qe == 1)
    loss.backward()
    assert all(
        torch.count_nonzero(p.grad) == 0
        for n, p in model.named_parameters()
        if not n.startswith("decoder")
    )
    assert (
        sum(
            float(abs(p.grad).sum())
            for n, p in model.named_parameters()
            if n.startswith("decoder")
        )
        > 0
    )
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    opt.step()
    opt.zero_grad()
    loss, _, _, _ = late_loss(
        model, s, d, action, mixed=True, independent=np.arange(516)
    )
    loss.backward()
    assert (
        sum(
            float(abs(p.grad).sum())
            for n, p in model.named_parameters()
            if n.startswith("message")
        )
        > 0
    )
    assert torch.count_nonzero(model(torch.zeros_like(s))) == 0


def test_nonzero_mixed_loss_finite_difference_and_batch():
    graph, action = toy()
    rng = np.random.default_rng(7)
    model = NeighborhoodCorrector(eye(516, dtype=complex), graph, action.scale)
    s = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    d = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    loss, delta, _qr, _qe = late_loss(
        model, s, d, action, mixed=True, independent=np.arange(516)
    )
    explicit = (
        np.mean(
            np.linalg.norm(
                s.numpy() - (action.matrix @ delta.detach().numpy().T).T, axis=1
            )
            ** 2
            / np.linalg.norm(s.numpy(), axis=1) ** 2
            + np.linalg.norm(delta.detach().numpy() - d.numpy(), axis=1) ** 2
            / np.linalg.norm(d.numpy(), axis=1) ** 2
        )
        / 2
    )
    assert abs(float(loss.detach()) - explicit) < 1e-13
    serial = [
        late_loss(
            model,
            si[None, :],
            di[None, :],
            action,
            mixed=True,
            independent=np.arange(516),
        )[0]
        for si, di in zip(s, d)
    ]
    assert abs(float(loss.detach()) - float(sum(serial).detach()) / 2) < 1e-13
    loss.backward()
    param = model.message_self[0].weight
    direction = torch.randn_like(param)
    direction /= torch.linalg.vector_norm(direction)
    derivative = float(torch.sum(param.grad * direction))
    initial = param.detach().clone()
    h = 1e-5
    vals = []
    for sign in (1, -1):
        with torch.no_grad():
            param.copy_(initial + sign * h * direction)
        vals.append(
            float(
                late_loss(model, s, d, action, mixed=True, independent=np.arange(516))[
                    0
                ].detach()
            )
        )
    assert abs((vals[0] - vals[1]) / (2 * h) - derivative) < 1e-8


def test_zero_denominator_is_absolute_not_floor():
    graph, action = toy()
    model = NeighborhoodCorrector(
        eye(516, dtype=complex), graph, action.scale, zero_decoder=True
    )
    z = torch.zeros((2, 516), dtype=torch.complex128)
    loss, _, qr, qe = late_loss(
        model, z, z, action, mixed=True, independent=np.arange(516)
    )
    assert float(loss) == 0 and torch.all(qr == 0) and torch.all(qe == 0)


def test_label_reader_whitelist_and_selection():
    with pytest.raises(ValueError, match="train/validation"):
        frozen_reader({}, "heldout", lambda _: {}, labels=True)
    points = [
        {"update": i, "median_qr": r, "median_qe": e, "max_qe": e}
        for i, r, e in [(0, 1, 1), (16, 0.5, 0.9), (32, 0.6, 0.4)]
    ]
    assert choose_checkpoint(points, residual_only=True)["update"] == 16
    assert choose_checkpoint(points, residual_only=False)["update"] == 32


def test_original_rhs_scale_prefix_and_label_identity():
    _, action = toy()
    e = np.sin(np.arange(516)) + 1j * np.cos(np.arange(516))
    r = action.matrix @ e
    z, record = fixed_cleanup(action, r, np.zeros_like(r), max_steps=2, tol=1e-10)
    s, check = label_identity(action, r, z, e - z)
    assert check["passed"] and np.allclose(s, r - action.matrix @ z)
    _, second = fixed_cleanup(action, r, z, max_steps=126, tol=1e-10)
    assert second["rhs_norm"] == np.linalg.norm(r)
    assert record["steps"] + second["steps"] <= 128


def test_restart_boundary_prefix_no_penalty_to_R0():
    rng = np.random.default_rng(19)
    a = csr_matrix(
        rng.normal(size=(96, 96)) + 1j * rng.normal(size=(96, 96)) + 2 * np.eye(96)
    )
    action = OriginalCSR(
        {"data": a.data, "indices": a.indices, "indptr": a.indptr, "shape": a.shape}
    )
    r = rng.normal(size=96) + 1j * rng.normal(size=96)
    whole, _w = fixed_cleanup(action, r, np.zeros_like(r), max_steps=128, tol=1e-10)
    half, h = fixed_cleanup(action, r, np.zeros_like(r), max_steps=64, tol=1e-10)
    split, t = fixed_cleanup(action, r, half, max_steps=128 - h["steps"], tol=1e-10)
    assert h["steps"] == 64 and t["steps"] == 64
    assert np.linalg.norm(a @ split - a @ whole) / np.linalg.norm(r) < 1e-9


def test_complete_checker_rejects_missing_duplicate_wrong_split():
    rows = [
        {"split": "heldout", "sample": i, "route": r}
        for i in range(8)
        for r in ("R0", "NN-R", "NN-E", "RL-E", "CL-E")
    ]
    assert require_inventory(rows)
    for bad in (
        rows[:-1],
        rows[:-1] + [rows[0]],
        [dict(r, split="train") for r in rows],
    ):
        with pytest.raises(ValueError):
            require_inventory(bad)


@pytest.mark.parametrize(
    "stage",
    [
        "SETUP",
        "DATA",
        "GRADIENT",
        "TRAIN_NR",
        "TRAIN_NE",
        "TRAIN_RL",
        "TRAIN_CL",
        "EVAL_R0",
        "EVAL_NR",
        "EVAL_NE",
        "EVAL_RL",
        "EVAL_CL",
        "CHECK",
        "DIAGNOSTIC",
    ],
)
def test_actual_stage_schema(stage, tmp_path):
    from src.io.port_preparation import load_preparation

    path = tmp_path / "v44.dat"
    path.write_text(
        f'schema_version = 1\n[task042_v44]\nstage = "{stage}"\nrun_id = "task042_v44_fixture"\n'
    )
    spec = load_preparation(path)
    assert (
        spec.derived["stage"] == stage
        and spec.derived["environment_mode"] == "ml"
        and spec.derived["preparation_scope"] == "v44"
    )
