"""Full real parameter JVP/VJP via bounded 1-D AD and three exact products."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch
from scipy.sparse.linalg import LinearOperator
from src.solvers.ftt_factored_moments import model_identity
from src.solvers.joint_least_squares import realify, complexify
from src.solvers.neural_fe_action_packet import array_hash


class TangentBudgetStop(Exception):
    pass


class ParameterLayout:
    """Parent-frozen per-tensor RMS scales; masks project real parameters."""

    def __init__(self, model, *, scales=None, output_only=False):
        self.parameters = list(model.named_parameters())
        self.names = [n for n, _ in self.parameters]
        self.slices = {}
        cursor = 0
        scale_values = []
        hidden = []
        for name, p in self.parameters:
            self.slices[name] = slice(cursor, cursor + p.numel())
            cursor += p.numel()
            scale_values.extend(
                [max(1.0, float(torch.sqrt(torch.mean(p.detach() ** 2))))] * p.numel()
            )
            hidden.extend([name.split(".")[2] != "4"] * p.numel())
        self.full_size = cursor
        self.hidden = np.asarray(hidden, dtype=bool)
        self.scales = (
            np.asarray(scale_values, dtype=np.float64)
            if scales is None
            else np.asarray(scales, dtype=np.float64).copy()
        )
        if (
            self.scales.shape != (cursor,)
            or not np.isfinite(self.scales).all()
            or np.min(self.scales) <= 0
        ):
            raise ValueError("JOINT_PARENT_FIXED_PARAMETER_SCALES")
        self.mask = ~self.hidden if output_only else np.ones(cursor, dtype=bool)
        self.size = int(self.mask.sum())
        self.binding = dict(
            names=self.names,
            shapes=[list(p.shape) for _, p in self.parameters],
            scale_sha256=array_hash(self.scales),
            mask_sha256=array_hash(self.mask),
            full_size=cursor,
            active_size=self.size,
            output_only=output_only,
        )
        self.scales.setflags(write=False)
        self.mask.setflags(write=False)

    def theta(self):
        return (
            torch.cat([p.detach().ravel() for _, p in self.parameters]).numpy().copy()
        )

    def set_theta(self, full):
        full = np.asarray(full, dtype=np.float64)
        if full.shape != (self.full_size,) or not np.isfinite(full).all():
            raise ValueError("JOINT_FINITE_REAL_PARAMETER_VECTOR")
        with torch.no_grad():
            for name, p in self.parameters:
                p.copy_(
                    torch.from_numpy(full[self.slices[name]].copy()).reshape(p.shape)
                )

    def expand(self, v):
        v = np.asarray(v, dtype=np.float64).reshape(-1)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError("JOINT_REAL_ACTIVE_DIRECTION")
        out = np.zeros(self.full_size)
        out[self.mask] = self.scales[self.mask] * v
        return out

    def pullback(self, full_gradient):
        return np.asarray(full_gradient)[self.mask] * self.scales[self.mask]


def core_jvp(model, axis, normalized, full_delta, layout):
    """Forward AD only on a bounded 1-D node chunk, with fixed phase."""
    named = list(model.cores[axis].named_parameters())
    primal = tuple(p.detach() for _, p in named)
    tangent = tuple(
        torch.from_numpy(full_delta[layout.slices[f"cores.{axis}.{n}"]].copy()).reshape(
            p.shape
        )
        for n, p in named
    )

    def evaluate(*parameters):
        return torch.func.functional_call(
            model.cores[axis],
            dict(zip([n for n, _ in named], parameters)),
            (normalized.reshape(-1, 1),),
        )

    _, delta = torch.func.jvp(evaluate, primal, tangent)
    delta = delta.reshape(-1, *model.shapes[axis])
    value = torch.complex(delta[..., 0], delta[..., 1])
    if hasattr(model, "core_phase"):
        value = value * model.core_phase(axis, normalized)[:, None, None, None]
    return value.detach()


class TangentTermField:
    """Exact point fallback for one of the three product-derivative terms."""

    def __init__(self, model, axis, delta, layout):
        self.model, self.axis, self.delta, self.layout = model, axis, delta, layout

    def __call__(self, coordinates):
        normalized = (coordinates - self.model.center) / self.model.half_width
        with torch.no_grad():
            values = [self.model.core(a, normalized[:, a]) for a in range(3)]
        values[self.axis] = core_jvp(
            self.model, self.axis, normalized[:, self.axis], self.delta, self.layout
        )
        return torch.einsum("nsij,nsjk,nskl->nsil", *values)[:, :, 0, 0]


class JointTangent:
    def __init__(
        self, model, mapping, action, layout, *, deadline=float("inf"), marker=None
    ):
        self.model, self.mapping, self.action, self.layout = (
            model,
            mapping,
            action,
            layout,
        )
        self.deadline, self.marker = deadline, marker or (lambda *_: None)
        self.identity = model_identity(model)
        self.values = [v.copy() for v in mapping._cores(model)]
        self.counts = dict(JVP=0, VJP=0)
        self.costs = dict(JVP=0.0, VJP=0.0)
        self.cache_planned_bytes = (
            mapping.static_bytes + 6 * mapping.dynamic_bytes + layout.scales.nbytes * 8
        )
        if self.cache_planned_bytes > 2**30:
            raise MemoryError("JOINT_ONE_GIB_CACHE_AD_PLAN")

    def check(self):
        if monotonic() >= self.deadline:
            raise TangentBudgetStop("JOINT_SAVE_RESERVE_REACHED")
        if model_identity(self.model) != self.identity:
            raise ValueError("JOINT_LINEARIZATION_PARAMETER_OR_BUFFER_VERSION_CHANGED")

    def moment_jvp(self, v):
        self.check()
        delta = self.layout.expand(v)
        total = np.zeros(self.mapping.size, dtype=np.complex128)
        for a, nodes in enumerate(self.mapping.nodes):
            chunks = []
            for start in range(0, len(nodes), self.mapping.point_batch):
                x = (
                    torch.from_numpy(nodes[start : start + self.mapping.point_batch])
                    - self.model.center[a]
                ) / self.model.half_width[a]
                chunks.append(core_jvp(self.model, a, x, delta, self.layout).numpy())
            values = list(self.values)
            values[a] = np.concatenate(chunks)
            total += self.mapping.forward_with_core_values(
                TangentTermField(self.model, a, delta, self.layout), values
            )
        return total

    def jvp(self, v):
        began = monotonic()
        result = realify(self.action.apply(self.moment_jvp(v)) / self.action.bnorm)
        self.counts["JVP"] += 1
        self.costs["JVP"] += monotonic() - began
        return result

    def vjp(self, u):
        self.check()
        began = monotonic()
        dual = self.action.apply(complexify(u), adjoint=True) / self.action.bnorm
        try:
            gradient = self.mapping.vjp(self.model, dual)
            result = self.layout.pullback(gradient).copy()
        finally:
            self.model.zero_grad(set_to_none=True)
        self.counts["VJP"] += 1
        self.costs["VJP"] += monotonic() - began
        if self.counts["VJP"] % 25 == 0:
            self.marker("joint_inner_progress", dict(counts=self.counts.copy()))
        return result

    def operator(self):
        return LinearOperator(
            (2 * self.action.size, self.layout.size),
            matvec=self.jvp,
            rmatvec=self.vjp,
            dtype=np.float64,
        )


class ModelTransaction:
    """Restore all model/buffer and cache state on rejection or interruption."""

    def __init__(self, model, mapping):
        self.model, self.mapping = model, mapping
        self.state = deepcopy(model.state_dict())

    def restore(self):
        self.model.load_state_dict(self.state, strict=True)
        self.model.zero_grad(set_to_none=True)
        self.mapping.invalidate()
