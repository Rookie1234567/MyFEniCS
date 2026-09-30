"""Synchronous CPU optimizer transactions and two-generation durable storage.

This ML-only module is never imported by the FE postprocessing process.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile

import numpy as np
import torch


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(2**20):
            value.update(block)
    return value.hexdigest()


def atomic_write(path, writer, *, before_replace=None):
    """An interrupted temporary write cannot replace the previous file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace(Path(temporary))
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()
    atomic_write(path, lambda stream: stream.write(data))


def parameter_order(model):
    return [
        dict(name=name, shape=list(p.shape), dtype=str(p.dtype))
        for name, p in model.named_parameters()
    ]


def capture(model, optimizer, metadata):
    return dict(
        schema="durable-optimizer.cpu.v1",
        model=deepcopy(model.state_dict()),
        parameter_order=parameter_order(model),
        optimizer=deepcopy(optimizer.state_dict()),
        optimizer_class=type(optimizer).__name__,
        gradients=[
            None if p.grad is None else p.grad.detach().clone()
            for p in model.parameters()
        ],
        torch_rng=torch.get_rng_state().clone(),
        numpy_rng=deepcopy(np.random.get_state()),
        python_rng=random.getstate(),
        metadata=deepcopy(metadata),
    )


def restore(model, optimizer, state):
    if (
        parameter_order(model) != state["parameter_order"]
        or type(optimizer).__name__ != state["optimizer_class"]
    ):
        raise ValueError("CHECKPOINT_PARAMETER_ORDER_OR_OPTIMIZER_MISMATCH")
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(deepcopy(state["optimizer"]))
    for parameter, gradient in zip(model.parameters(), state["gradients"], strict=True):
        parameter.grad = None if gradient is None else gradient.detach().clone()
    torch.set_rng_state(state["torch_rng"])
    np.random.set_state(state["numpy_rng"])
    random.setstate(state["python_rng"])


def optimizer_step(model, optimizer, closure, persist):
    """Rollback both parameters and optimizer; publish only after durable save."""
    before = capture(model, optimizer, {})
    p0 = torch.cat([p.detach().ravel() for p in model.parameters()]).clone()
    try:
        result = optimizer.step(closure)
        p1 = torch.cat([p.detach().ravel() for p in model.parameters()])
        norm = float(torch.linalg.vector_norm(p1 - p0))
        relative = norm / max(float(torch.linalg.vector_norm(p0)), 1e-30)
        persisted = persist(
            dict(accepted_update_norm=norm, accepted_relative_update=relative)
        )
        return result, persisted
    except BaseException:
        restore(model, optimizer, before)
        raise


class CheckpointStore:
    """Immutable generations, atomic pointer; latest two plus pinned audit states."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pointer = self.directory / "current.json"
        self.records = []
        if self.pointer.exists():
            raise ValueError("CHECKPOINT_STORE_ALREADY_EXISTS")

    def save(self, state, *, pin=False):
        generation = len(self.records)
        name = f"committed_{generation:06d}.pt"
        path = self.directory / name
        atomic_write(path, lambda stream: torch.save(state, stream))
        record = dict(
            generation=generation,
            name=name,
            sha256=digest(path),
            bytes=path.stat().st_size,
            pinned=bool(pin),
            metadata=deepcopy(state["metadata"]),
            model_keys=list(state["model"]),
            parameter_order=state["parameter_order"],
            optimizer_class=state["optimizer_class"],
        )
        previous = self.records[-1] if self.records else None
        # Only the pointer publishes a complete generation. No mutable tensor references.
        atomic_json(
            self.pointer,
            dict(
                schema="durable-checkpoint-pointer.v1",
                current=record,
                previous=previous,
            ),
        )
        self.records.append(record)
        retained = {x["name"] for x in self.records if x["pinned"]} | {
            x["name"] for x in self.records[-2:]
        }
        for old in self.records[:-2]:
            if old["name"] not in retained:
                try:
                    (self.directory / old["name"]).unlink(missing_ok=True)
                except OSError:
                    # Published state stays complete even if bounded cleanup fails.
                    old["cleanup_pending"] = True
        return record

    def index(self):
        return [
            dict(x, retained=(self.directory / x["name"]).exists())
            for x in self.records
        ]


def load_checkpoint(path, expected_sha256):
    path = Path(path)
    if digest(path) != expected_sha256:
        raise ValueError("DURABLE_CHECKPOINT_DIGEST_MISMATCH")
    # Only private, hash-bound artifacts created by this task are accepted here.
    return torch.load(path, map_location="cpu", weights_only=False)
