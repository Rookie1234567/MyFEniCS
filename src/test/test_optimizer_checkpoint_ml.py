"""Meaningful failure/reload tests for complete optimizer boundaries."""

from copy import deepcopy
import multiprocessing
import os
from pathlib import Path
import signal
import time

import numpy as np
import pytest
import torch

from src.solvers.optimization_checkpoint import (
    CheckpointStore,
    atomic_write,
    capture,
    digest,
    load_checkpoint,
    optimizer_step,
    restore,
)


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.p = torch.nn.Parameter(torch.tensor([-1.2, 1.0], dtype=torch.float64))
        self.register_buffer("scale", torch.tensor(1.0, dtype=torch.float64))


def closure(model, optimizer):
    optimizer.zero_grad()
    x, y = model.p
    # Two real channels of a small complex residual.
    residual = torch.complex(10 * (y - x * x), 1 - x)
    value = (residual.conj() * residual).real / 2
    value.backward()
    return value


def equal(left, right):
    if isinstance(left, torch.Tensor):
        torch.testing.assert_close(left, right, rtol=0, atol=1e-12)
    elif isinstance(left, np.ndarray):
        np.testing.assert_array_equal(left, right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            equal(left[key], right[key])
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right)
        for x, y in zip(left, right, strict=True):
            equal(x, y)
    else:
        assert left == right


@pytest.mark.parametrize("kind", ["Adam", "LBFGS"])
def test_complete_model_buffers_optimizer_reload_matches_continuous(kind, tmp_path):
    torch.set_num_threads(1)
    model = Tiny()
    options = (
        dict(lr=0.01)
        if kind == "Adam"
        else dict(lr=1, max_iter=2, line_search_fn="strong_wolfe", history_size=3)
    )
    make = getattr(torch.optim, kind)
    optimizer = make(model.parameters(), **options)
    for _ in range(3):
        optimizer.step(lambda: closure(model, optimizer))
    store = CheckpointStore(tmp_path)
    record = store.save(capture(model, optimizer, {"phase": kind}), pin=True)
    clone = Tiny()
    other = make(clone.parameters(), **options)
    restore(clone, other, load_checkpoint(tmp_path / record["name"], record["sha256"]))
    for _ in range(3):
        optimizer.step(lambda: closure(model, optimizer))
        other.step(lambda: closure(clone, other))
        equal(model.state_dict(), clone.state_dict())
        equal(optimizer.state_dict(), other.state_dict())
        torch.testing.assert_close(
            closure(model, optimizer), closure(clone, other), rtol=0, atol=1e-12
        )


def test_adam_boundary_to_fresh_lbfgs_has_same_path(tmp_path):
    model = Tiny()
    adam = torch.optim.Adam(model.parameters(), lr=0.01)
    for _ in range(5):
        adam.step(lambda: closure(model, adam))
    saved = tmp_path / "boundary.pt"
    atomic_write(saved, lambda stream: torch.save(deepcopy(model.state_dict()), stream))
    clone = Tiny()
    clone.load_state_dict(torch.load(saved, weights_only=True))
    a = torch.optim.LBFGS(
        model.parameters(), lr=1, max_iter=3, line_search_fn="strong_wolfe"
    )
    b = torch.optim.LBFGS(
        clone.parameters(), lr=1, max_iter=3, line_search_fn="strong_wolfe"
    )
    assert not a.state and not b.state
    for _ in range(3):
        a.step(lambda: closure(model, a))
        b.step(lambda: closure(clone, b))
        equal(model.state_dict(), clone.state_dict())
        equal(a.state_dict(), b.state_dict())


@pytest.mark.parametrize("exception", [RuntimeError, TimeoutError])
def test_actual_nonzero_strong_wolfe_trial_restores_matching_optimizer(exception):
    model = Tiny()
    optimizer = torch.optim.LBFGS(
        model.parameters(), lr=1, max_iter=20, line_search_fn="strong_wolfe"
    )
    before = capture(model, optimizer, {})
    attempts, displacement = [], []

    def failing():
        value = closure(model, optimizer)
        attempts.append(float(value.detach()))
        displacement.append(
            float(torch.linalg.vector_norm(model.p.detach() - before["model"]["p"]))
        )
        if len(attempts) == 2:
            raise exception("injected during actual nonzero line-search trial")
        return value

    with pytest.raises(exception):
        optimizer_step(
            model,
            optimizer,
            failing,
            lambda update: pytest.fail("trial must not commit"),
        )
    assert len(attempts) == 2 and displacement[-1] > 0
    equal(capture(model, optimizer, {}), before)


def test_accepted_update_measured_after_step_and_persisted(tmp_path):
    model = Tiny()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    before = model.p.detach().clone()
    store = CheckpointStore(tmp_path)

    def persist(update):
        return store.save(capture(model, optimizer, update))

    _, record = optimizer_step(
        model, optimizer, lambda: closure(model, optimizer), persist
    )
    assert record["metadata"]["accepted_update_norm"] > 0
    assert record["metadata"]["accepted_update_norm"] == float(
        torch.linalg.vector_norm(model.p.detach() - before)
    )


def test_interrupted_atomic_temporary_write_preserves_previous_file(tmp_path):
    target, ready = tmp_path / "complete", tmp_path / "ready"
    target.write_bytes(b"previous complete checkpoint")
    previous = digest(target)

    def child():
        def suspend(temporary):
            ready.write_text(str(temporary))
            time.sleep(60)

        atomic_write(
            target,
            lambda stream: stream.write(b"partial future version"),
            before_replace=suspend,
        )

    process = multiprocessing.get_context("fork").Process(target=child)
    process.start()
    deadline = time.monotonic() + 5
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()
    os.kill(process.pid, signal.SIGKILL)
    process.join(5)
    assert process.exitcode == -signal.SIGKILL
    assert digest(target) == previous
    assert target.read_bytes() == b"previous complete checkpoint"
    assert Path(ready.read_text()).exists()  # unpublished temporary is never loaded
