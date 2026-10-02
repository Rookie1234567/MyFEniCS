"""Opt-in fixed real parameter metric; physical PDE and ordinary GN unchanged."""

from copy import deepcopy
import hashlib
import numpy as np

from src.solvers.damped_gauss_newton import DampedGNState, damped_cg

GROUP_SIZES = (192, 64, 4096, 64, 4096, 64, 384, 6)


class ParameterMetric:
    def __init__(self, diagonal):
        self.diagonal = np.array(diagonal, dtype=np.float64, copy=True)
        if (
            self.diagonal.ndim != 1
            or not np.isfinite(self.diagonal).all()
            or np.any(self.diagonal <= 0)
        ):
            raise ValueError("FIXED_PARAMETER_METRIC_NOT_POSITIVE")
        self.inverse = 1 / self.diagonal
        self.S = np.sqrt(self.inverse)
        self.sha256 = hashlib.sha256(self.diagonal.tobytes()).hexdigest()

    def curvature(self, K, v):
        return self.S * K(self.S * v)

    def solve(self, K, gradient, mu, **kwargs):
        y, cg = damped_cg(
            lambda v: self.curvature(K, v),
            self.S * gradient,
            mu,
            residual_to_original=lambda r: r / self.S,
            **kwargs,
        )
        return self.S * y, dict(cg, metric_sha256=self.sha256)

    def record(self):
        return dict(
            schema="fixed-parameter-metric.v1",
            sha256=self.sha256,
            diagonal=self.diagonal.tolist(),
            damping="mu*M",
            fixed=True,
        )


class MetricDampedGNState(DampedGNState):
    """Same acceptance rules, checkpointed fixed metric, both pilots forbid PC."""

    def __init__(self, h0, metric):
        super().__init__(h0, pc_max_builds=0)
        self.metric = metric

    def state_dict(self):
        state = super().state_dict()
        state.pop("metric")
        state["parameter_metric"] = self.metric.record()
        return state

    def load_state_dict(self, state):
        state = deepcopy(state)
        retained = state.pop("parameter_metric", None)
        if retained is not None and retained != self.metric.record():
            raise ValueError("RECOVERY_FIXED_PARAMETER_METRIC_CHANGED")
        if (
            state.get("pc_builds")
            or state.get("V") is not None
            or state.get("lam") is not None
        ):
            raise ValueError("PHASE75_NO_PC_IDENTITY_CONFLICT")
        metric = self.metric
        super().load_state_dict(state)
        self.metric = metric
        self.pc_max_builds = 0

    def propose(self, *args, **kwargs):
        return super().propose(*args, parameter_metric=self.metric, **kwargs)


def grouped_metric(curvatures):
    q = np.asarray(curvatures, float)
    if q.shape != (8, 3) or np.any(q < 0) or not np.isfinite(q).all():
        raise ValueError("GROUP_CURVATURE_INVALID")
    h = q.mean(axis=1)
    mean = float(np.dot(GROUP_SIZES, h) / sum(GROUP_SIZES))
    if not np.isfinite(mean) or mean <= 0:
        raise ValueError("MEAN_GROUP_CURVATURE_NOT_POSITIVE")
    raw = h / mean
    m = np.clip(raw, 1e-4, 1e4)
    return ParameterMetric(np.repeat(m, GROUP_SIZES)), dict(
        seed=4211101,
        sizes=list(GROUP_SIZES),
        curvatures=q.tolist(),
        group_mean=h.tolist(),
        weighted_mean=mean,
        raw_ratios=raw.tolist(),
        values=m.tolist(),
        clipping_count=int(np.count_nonzero(m != raw)),
        clipping_delta=(m - raw).tolist(),
        curvature_span=float(h.max() / max(h.min(), 1e-4 * mean)),
        interpretation="three random directions/group; not a condition number or exact diagonal",
    )
