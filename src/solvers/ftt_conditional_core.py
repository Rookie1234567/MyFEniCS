"""Opt-in matrix-free, complex output-core least squares for the actual FTT.

Only the selected axis output coefficients are linear. No FE column library,
normal matrix, inverse, reference, or capacity tensor is constructed here.
"""

from time import monotonic
import numpy as np
import torch
from scipy.sparse.linalg import LinearOperator, lsmr

from src.solvers.ftt_factored_moments import model_identity


class CoreBudgetStop(Exception):
    pass


def axis_features(model, axis, normalized):
    """Output features including bias; opt-in physical phase also covers K.

    Ordinary features stay real. The Bloch adapter makes them complex, so an
    active replacement never bypasses the phase attached to model.core.
    """
    with torch.no_grad():
        x = torch.as_tensor(normalized, dtype=torch.float64).reshape(-1)
        if model.model_kind == "fttnn":
            h = model.cores[axis][:-1](x[:, None])
            features = torch.cat((h, torch.ones_like(h[:, :1])), 1)
        else:
            terms = [torch.ones_like(x), x]
            for _ in range(2, 19):
                terms.append(2 * x * terms[-1] - terms[-2])
            features = torch.stack(terms, 1)
        if hasattr(model, "core_phase"):
            features = features * model.core_phase(axis, x)[:, None]
        return features.numpy()


def output_coefficients(model, axis, *, gradient=False):
    """Complex layout [feature, component, left rank, right rank]."""
    shape = model.shapes[axis]
    if model.model_kind == "fttnn":
        layer = model.cores[axis][-1]
        w = layer.weight.grad if gradient else layer.weight.detach()
        b = layer.bias.grad if gradient else layer.bias.detach()
        packed = torch.cat((w, b[:, None]), 1).reshape(*shape, 17)
        real = packed[..., 0, :].movedim(-1, 0)
        imag = packed[..., 1, :].movedim(-1, 0)
    else:
        packed = model.cores[axis].grad if gradient else model.cores[axis].detach()
        real, imag = packed[..., 0], packed[..., 1]
    return torch.complex(real, imag).detach().numpy().copy()


def set_output_coefficients(model, axis, coefficients):
    expected = (17 if model.model_kind == "fttnn" else 19, *model.shapes[axis][:-1])
    coefficients = np.asarray(coefficients)
    if (
        coefficients.shape != expected
        or coefficients.dtype != np.complex128
        or not np.isfinite(coefficients).all()
    ):
        raise ValueError("CORE_COMPLEX_OUTPUT_LAYOUT_MISMATCH")
    real = torch.from_numpy(np.stack((coefficients.real, coefficients.imag), -1).copy())
    with torch.no_grad():
        if model.model_kind == "fttnn":
            layer = model.cores[axis][-1]
            packed = real.movedim(0, -1).reshape(-1, 17)
            layer.weight.copy_(packed[:, :16])
            layer.bias.copy_(packed[:, 16])
        else:
            model.cores[axis].copy_(real)


def hidden_parameters(model):
    if model.model_kind != "fttnn":
        return []
    return [
        p
        for core in model.cores
        for layer in (core[0], core[2])
        for p in layer.parameters()
    ]


class DirectionField:
    """Exact point fallback with one axis replaced by a linear increment."""

    def __init__(self, model, axis, coefficients):
        self.model, self.axis, self.coefficients = model, axis, coefficients

    def __call__(self, coordinates):
        normalized = (coordinates - self.model.center) / self.model.half_width
        with torch.no_grad():
            cores = [self.model.core(a, normalized[:, a]) for a in range(3)]
            features = axis_features(self.model, self.axis, normalized[:, self.axis])
            cores[self.axis] = torch.from_numpy(
                np.einsum("nt,tsij->nsij", features, self.coefficients)
            )
            return torch.einsum("nsij,nsjk,nskl->nsil", *cores)[:, :, 0, 0]


class ConditionalCoreAction:
    def __init__(
        self, model, mapping, action, axis, *, deadline=float("inf"), marker=None
    ):
        self.model, self.mapping, self.action, self.axis = model, mapping, action, axis
        self.deadline, self.marker = deadline, marker or (lambda *_: None)
        self.identity = model_identity(model)
        self.coefficients = output_coefficients(model, axis)
        self.shape, self.size = self.coefficients.shape, self.coefficients.size
        self.base_values = [v.copy() for v in mapping._cores(model)]
        normalized = (mapping.nodes[axis] - float(model.center[axis])) / float(
            model.half_width[axis]
        )
        self.features = axis_features(model, axis, normalized)
        self.counts = dict(K=0, KH=0, B=0, BH=0)
        self.costs = {name: 0.0 for name in self.counts}
        self.cache_bytes = self.features.nbytes + sum(
            v.nbytes for v in self.base_values
        )
        if self.cache_bytes + mapping.static_bytes + 2 * mapping.dynamic_bytes > 2**30:
            raise MemoryError("CORE_CACHE_AD_ONE_GIB_PLANNING_LIMIT")

    def _check(self):
        if monotonic() >= self.deadline:
            raise CoreBudgetStop("CORE_OPERATION_SAVE_RESERVE_REACHED")
        if model_identity(self.model) != self.identity:
            raise ValueError("CORE_BASE_PARAMETER_VERSION_CHANGED")

    def K(self, delta):
        self._check()
        began = monotonic()
        d = np.asarray(delta, dtype=np.complex128).reshape(self.shape)
        values = list(self.base_values)
        values[self.axis] = np.einsum("nt,tsij->nsij", self.features, d)
        result = self.mapping.forward_with_core_values(
            DirectionField(self.model, self.axis, d), values
        )
        self.counts["K"] += 1
        self.costs["K"] += monotonic() - began
        return result

    def KH(self, dual):
        self._check()
        began = monotonic()
        # The qualified real VJP gives Re/Im of K^H dual in paired storage.
        self.mapping.vjp(self.model, np.asarray(dual, dtype=np.complex128))
        result = output_coefficients(self.model, self.axis, gradient=True).ravel()
        self.counts["KH"] += 1
        self.costs["KH"] += monotonic() - began
        return result

    def B(self, delta):
        began = monotonic()
        result = self.action.apply(self.K(delta)) / self.action.bnorm
        self.counts["B"] += 1
        self.costs["B"] += monotonic() - began
        return result

    def BH(self, dual):
        began = monotonic()
        result = (
            self.KH(
                self.action.apply(np.asarray(dual, dtype=np.complex128), adjoint=True)
            )
            / self.action.bnorm
        )
        self.counts["BH"] += 1
        self.costs["BH"] += monotonic() - began
        if self.counts["BH"] % 25 == 0:
            self.marker(
                "core_inner_progress", dict(axis=self.axis, counts=self.counts.copy())
            )
        return result

    def operator(self):
        return LinearOperator(
            (self.action.size, self.size),
            matvec=self.B,
            rmatvec=self.BH,
            dtype=np.complex128,
        )


def relative_pair(first, second):
    numerator = float(np.linalg.norm(first - second))
    denominator = max(
        float(np.linalg.norm(first)), float(np.linalg.norm(second)), 1e-30
    )
    return dict(
        numerator=numerator, denominator=denominator, relative=numerator / denominator
    )


def solve_core(operator, b, maxiter=300):
    """Fixed LSMR contract; independent true residual and adjoint afterwards."""
    began = monotonic()
    solved = lsmr(
        operator.operator(),
        b,
        damp=0,
        atol=1e-8,
        btol=1e-8,
        conlim=1e12,
        maxiter=maxiter,
        x0=np.zeros(operator.size, dtype=np.complex128),
    )
    delta, stop, iters, normr, normar, norma, conda, normx = solved
    residual = b - operator.B(delta)
    adjoint = operator.BH(residual)
    initial_adjoint = operator.BH(b)
    return delta, dict(
        stop_code=int(stop),
        iterations=int(iters),
        reported_normr=float(normr),
        reported_normar=float(normar),
        reported_normA=float(norma),
        reported_condA=float(conda),
        reported_normx=float(normx),
        true_linear_residual_norm=float(np.linalg.norm(residual)),
        true_linear_rhs_norm=float(np.linalg.norm(b)),
        true_adjoint_residual_norm=float(np.linalg.norm(adjoint)),
        true_adjoint_initial_norm=float(np.linalg.norm(initial_adjoint)),
        true_adjoint_residual_relative=float(
            np.linalg.norm(adjoint) / max(np.linalg.norm(initial_adjoint), 1e-30)
        ),
        counts=operator.counts.copy(),
        costs_including_nested_actions=operator.costs.copy(),
        solve_and_independent_check_seconds=monotonic() - began,
        inexact_at_iteration_limit=bool(iters == maxiter and stop == 7),
        original_PDE_pass_from_stop_code=False,
    )


def verify_and_apply_core(model, mapping, action, operator, delta, before_c):
    """Real model update, conditional pairing, full objective, transactional rollback."""
    predicted = before_c + operator.K(delta)
    before = output_coefficients(model, operator.axis)
    old_r = action.apply(before_c) - action.f
    old_loss = float(np.vdot(old_r, old_r).real / (2 * action.bnorm**2))
    try:
        set_output_coefficients(
            model, operator.axis, before + delta.reshape(before.shape)
        )
        mapping.invalidate()
        actual = mapping.forward(model)
        new_r = action.apply(actual) - action.f
        new_loss = float(np.vdot(new_r, new_r).real / (2 * action.bnorm**2))
        pair = relative_pair(predicted, actual)
        accepted = bool(
            pair["relative"] <= 1e-10
            and new_loss <= old_loss + 1e-12 * max(1, old_loss)
        )
        evidence = dict(
            linearity_pairing=pair,
            old_loss=old_loss,
            trial_loss=new_loss,
            native_trial=float(np.linalg.norm(new_r) / action.bnorm),
            accepted=accepted,
            effective_decrease=bool(
                accepted and old_loss - new_loss > 1e-12 * max(1, old_loss)
            ),
            delta_complex_norm=float(np.linalg.norm(delta)),
        )
        if accepted:
            return actual, new_r, evidence
    except BaseException:
        set_output_coefficients(model, operator.axis, before)
        mapping.invalidate()
        raise
    set_output_coefficients(model, operator.axis, before)
    mapping.invalidate()
    return before_c.copy(), old_r, evidence
