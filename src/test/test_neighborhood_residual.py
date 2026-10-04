"""Focused V43 regressions use no real matrix, mesh, factor or closed ledger."""

import json

import numpy as np
import pytest
import torch
from scipy.sparse import csr_matrix, eye

from src.solvers.neighborhood_residual_core import (
    OriginalCSR,
    fixed_cleanup,
    manufactured,
)
from src.solvers.neighborhood_residual_models import (
    NeighborhoodCorrector,
    original_loss,
)


def toy():
    graph = {
        "sizes": np.array([6, 60, 450]),
        "src": np.array([0, 1, 2, 2]),
        "dst": np.array([2, 2, 0, 1]),
        "degree": np.array([1, 1, 2]),
        "offsets": np.array([0, 6, 66, 516]),
        "centers": np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.5, 0.5, 0.5]]),
    }
    a = eye(516, dtype=complex, format="csr") * (2 + 0.3j)
    a += csr_matrix(
        (np.full(515, 0.2 - 0.1j), (np.arange(515), np.arange(1, 516))), shape=a.shape
    )
    action = OriginalCSR(
        {"data": a.data, "indices": a.indices, "indptr": a.indptr, "shape": a.shape}
    )
    return graph, action


@pytest.mark.parametrize("linear", [False, True])
def test_full_decoder_zero_parameter_capacity_and_original_gradient(linear):
    graph, action = toy()
    model = NeighborhoodCorrector(
        eye(516, dtype=complex, format="csr"), graph, action.scale, linear=linear
    )
    assert model.real_parameters <= 100000
    assert (
        torch.count_nonzero(model(torch.zeros((2, 516), dtype=torch.complex128))) == 0
    )
    rng = np.random.default_rng(1)
    r = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    loss, delta, _ = original_loss(model, r, action)
    direct = np.mean(
        np.linalg.norm(r.numpy() - (action.matrix @ delta.detach().numpy().T).T, axis=1)
        ** 2
        / (2 * np.linalg.norm(r.numpy(), axis=1) ** 2)
    )
    assert abs(float(loss) - direct) < 1e-14
    loss.backward()
    assert all(
        p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()
    )
    assert sum(float(p.grad.abs().sum()) for p in model.parameters()) > 0


def test_complex_linear_control_and_nonlinear_phase_counterexample():
    graph, action = toy()
    rng = np.random.default_rng(2)
    r = torch.from_numpy(rng.normal(size=(1, 516)) + 1j * rng.normal(size=(1, 516)))
    q = torch.from_numpy(rng.normal(size=(1, 516)) + 1j * rng.normal(size=(1, 516)))
    alpha, beta = 0.7 - 0.3j, -0.2 + 0.6j
    linear = NeighborhoodCorrector(
        eye(516, dtype=complex), graph, action.scale, linear=True
    )
    actual, expected = (
        linear(alpha * r + beta * q),
        alpha * linear(r) + beta * linear(q),
    )
    assert (
        torch.linalg.vector_norm(actual - expected) / torch.linalg.vector_norm(expected)
        < 1e-13
    )
    nn = NeighborhoodCorrector(eye(516, dtype=complex), graph, action.scale)
    assert torch.linalg.vector_norm(nn(1j * r) - 1j * nn(r)) > 1e-6


def test_right_diagonal_gmres_and_128_inner_step_semantics():
    _, action = toy()
    r = np.sin(np.arange(516)) + 1j * np.cos(np.arange(516))
    z, row = fixed_cleanup(action, r, np.zeros_like(r), max_steps=3, tol=1e-14)
    assert row["steps"] <= 3
    assert np.isclose(
        row["rho"], np.linalg.norm(r - action.matrix @ z) / np.linalg.norm(r)
    )
    assert row["rho"] < 1.0
    z, row = fixed_cleanup(action, np.zeros(516, complex), r)
    assert not np.any(z) and row["steps"] == 0


def test_directional_complex_parameter_chain_nonhermitian_ports():
    rng = np.random.default_rng(3)
    a = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    c = rng.normal(size=(7, 12)) + 1j * rng.normal(size=(7, 12))
    d = rng.normal(size=(12, 7)) + 1j * rng.normal(size=(12, 7))
    h = np.diag(2 + rng.random(12) + 1j * rng.random(12))
    r, g = rng.normal(size=7) + 1j * rng.normal(size=7), np.ones(12) * (0.4 + 0.7j)
    u, alpha = (
        rng.normal(size=7) + 1j * rng.normal(size=7),
        rng.normal(size=12) + 1j * rng.normal(size=12),
    )
    du, da = (
        rng.normal(size=7) + 1j * rng.normal(size=7),
        rng.normal(size=12) + 1j * rng.normal(size=12),
    )
    residual = np.r_[a @ u + c @ alpha - r, d @ u + h @ alpha - g]
    tangent = np.r_[a @ du + c @ da, d @ du + h @ da]
    vjp_u = a.conj().T @ residual[:7] + d.conj().T @ residual[7:]
    vjp_a = c.conj().T @ residual[:7] + h.conj().T @ residual[7:]
    left, right = np.vdot(tangent, residual), np.vdot(du, vjp_u) + np.vdot(da, vjp_a)
    assert (
        abs(left - right) / (np.linalg.norm(tangent) * np.linalg.norm(residual)) < 1e-13
    )
    assert not np.allclose(d, c.conj().T)


def test_smooth_cross_cell_data_is_not_independent_random_node_noise():
    graph, _ = toy()
    out = manufactured(graph, "cross_mixed_smooth", 424601)
    assert np.isfinite(out).all() and np.isclose(np.linalg.norm(out), 1)
    assert np.count_nonzero(out) == 516
    assert np.array_equal(out, manufactured(graph, "cross_mixed_smooth", 424601))


@pytest.mark.parametrize(
    "stage",
    [
        "SETUP",
        "RECOVERY",
        "DATA",
        "GRADIENT",
        "TRAIN_NN",
        "TRAIN_LIN",
        "EVALUATE",
        "CHECK",
    ],
)
def test_real_one_run_stage_registration(stage, tmp_path):
    from src.io.port_preparation import load_preparation

    path = tmp_path / "v43.dat"
    path.write_text(
        'schema_version=1\n[task042_v43]\nstage="'
        + stage
        + '"\nrun_id="task042_v43_test"\n'
    )
    spec = load_preparation(path)
    assert spec.derived["stage"] == stage and spec.derived["preparation_scope"] == "v43"
    assert (
        spec.execution["mpi_size"] == 1 and spec.execution["terminate_memory_gib"] == 8
    )


def test_wrong_namespace_and_unknown_stage_fail_closed(tmp_path):
    from src.io.input_loader import InputError
    from src.io.port_preparation import load_preparation

    p = tmp_path / "v43.dat"
    p.write_text(
        'schema_version=1\n[task042_v43]\nstage="TARGET"\nrun_id="task042_v42_wrong"\n'
    )
    with pytest.raises(InputError):
        load_preparation(p)


def test_checker_requires_all_24_frozen_final_states():
    from benchmarks.check_neighborhood_residual import require_inventory

    rows = [
        {"split": "heldout", "sample": i, "route": r}
        for i in range(8)
        for r in ("R0", "R-LIN", "R-NN")
    ]
    assert require_inventory(rows)
    with pytest.raises(ValueError):
        require_inventory(rows[:-1])
    with pytest.raises(ValueError):
        require_inventory(rows + [dict(rows[0])])


def test_no_reference_training_reader_contract():
    # Reader takes only the committed RHS inventory, never the sealed-error packet.
    import inspect

    from src.solvers.neighborhood_residual_study import read_training_split

    source = inspect.getsource(read_training_split)
    assert "sealed" not in source and "reference" not in source


def test_new_window_never_reopens_old_ledger():
    from src.solvers.neighborhood_residual_scope import window

    assert window.label == "V43" and window.TMP.name == "v43" and window.total == 7200
    assert (
        json.loads(window.WINDOW_PATH.read_text())["review_commit"]
        == "84c38b882795c56fead54d75cd56389262c86e31"
    )


def test_full_parameter_JVP_and_original_VJP_on_nonzero_loss():
    from torch.func import functional_call

    graph, action = toy()
    model = NeighborhoodCorrector(eye(516, dtype=complex), graph, action.scale)
    rng = np.random.default_rng(44)
    rhs = torch.from_numpy(rng.normal(size=(2, 516)) + 1j * rng.normal(size=(2, 516)))
    loss, delta, _ = original_loss(model, rhs, action)
    gradients = torch.autograd.grad(loss, tuple(model.parameters()))
    weights = tuple(p.detach().clone().requires_grad_() for p in model.parameters())
    names = [n for n, _ in model.named_parameters()]
    torch.manual_seed(44)
    d = tuple(torch.randn_like(p) for p in weights)
    norm = torch.sqrt(sum(torch.sum(v * v) for v in d))
    d = tuple(v / norm for v in d)

    def output(*p):
        return functional_call(model, dict(zip(names, p, strict=True)), (rhs,))

    _, jvp = torch.autograd.functional.jvp(output, weights, d, strict=True)
    h = 3e-5
    fd = (
        output(*(p + h * v for p, v in zip(weights, d, strict=True)))
        - output(*(p - h * v for p, v in zip(weights, d, strict=True)))
    ) / (2 * h)
    assert torch.linalg.vector_norm(fd - jvp) / torch.linalg.vector_norm(jvp) < 1e-5
    residual = rhs.numpy() - (action.matrix @ delta.detach().numpy().T).T
    dual = (
        -(action.adjoint @ residual.T).T
        / (np.linalg.norm(rhs.numpy(), axis=1) ** 2)[:, None]
        / 2
    )
    left = float(np.vdot(jvp.numpy(), dual).real)
    right = float(sum(torch.sum(g * v) for g, v in zip(gradients, d, strict=True)))
    assert (
        abs(left - right) / (np.linalg.norm(jvp.numpy()) * np.linalg.norm(dual)) < 1e-10
    )


def test_actual_ML_runtime_math_pools_without_optional_threadpoolctl():
    import sys

    from src.solvers.isolated_ml_sparse import loaded_math_threads

    pools = loaded_math_threads()
    assert pools and all(p["threads"] == 1 for p in pools)
    assert not any(n in sys.modules for n in ("dolfinx", "mpi4py", "petsc4py"))


def test_actual_dat_run_case_validate_registration():
    import subprocess
    import sys

    from src.solvers.neighborhood_residual_scope import ROOT, STAGES

    for s in STAGES:
        p = ROOT / "input/task042_neural_coarse_inverse" / ("v43_" + s.lower() + ".dat")
        r = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/run_case.py"),
                str(p),
                "--validate-only",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["stage"] == s
