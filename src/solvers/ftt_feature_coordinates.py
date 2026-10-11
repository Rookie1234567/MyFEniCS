"""Bounded invertible feature coordinates for conditional neural core solves.

This is a right coordinate change only. The original residual, core map and
physical model remain the authorities, including in both refinement segments.
"""

import hashlib
import json
from time import monotonic

import numpy as np
from scipy.sparse.linalg import LinearOperator


def array_identity(value):
    value = np.ascontiguousarray(value)
    h = hashlib.sha256(str((value.shape, value.dtype.str)).encode())
    h.update(value.tobytes())
    return h.hexdigest()


class FeatureCoordinates:
    """A small feature transform, never a full output or FE matrix."""

    def __init__(self, features, shape, *, tau=1e-6, dependency=None, identity=False):
        began = monotonic()
        f = np.asarray(features, dtype=np.complex128)
        self.shape = tuple(shape)
        self.size = int(np.prod(shape))
        if (f.ndim != 2 or not f.shape[0] or f.shape[1] != shape[0]
                or not np.isfinite(f).all() or tau not in (1e-6, 1e-4)):
            raise ValueError("FEATURE_COORDINATES_INPUT_OR_TAU_INVALID")
        f = f / np.sqrt(f.shape[0])
        # full_matrices only for the small-node case: complete RIGHT basis;
        # otherwise no large/full left Q is constructed.
        u, singular, vh = np.linalg.svd(f, full_matrices=f.shape[0] < f.shape[1])
        values = np.zeros(f.shape[1], dtype=float)
        values[:len(singular)] = singular
        if values[0] <= 0:
            raise ValueError("FEATURE_COORDINATES_ZERO_LEADING_SINGULAR")
        reconstruction = (u[:, :len(singular)] * singular) @ vh[:len(singular)]
        backward = float(np.linalg.norm(f-reconstruction) / np.linalg.norm(f))
        if backward > 1e-12:
            raise ValueError("FEATURE_SVD_BACKWARD_ERROR")
        gains = np.ones_like(values) if identity else 1 / np.maximum(values/values[0], tau)
        self.vh, self.gains = vh, gains
        self.matrix = np.eye(f.shape[1], dtype=complex) if identity else (vh.conj().T*gains) @ vh
        self.inverse_matrix = np.eye(f.shape[1], dtype=complex) if identity else (vh.conj().T/gains) @ vh
        self.last_solve_y = None
        after = np.linalg.svd(f @ self.matrix, compute_uv=False)
        payload = dict(feature_sha256=array_identity(f), dependency=dependency,
                       tau=tau, identity=identity, shape=list(shape),
                       matrix_sha256=array_identity(self.matrix))
        self.sha256 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.record = dict(payload, coordinate_transform_sha256=self.sha256,
            singular_values=values.tolist(), gains=gains.tolist(),
            singular_values_after=after.tolist(), retained_feature_directions=len(values),
            truncated_directions=0, gain_cap_count=int(np.count_nonzero(values/values[0] <= tau)) if not identity else 0,
            original_feature_condition=float(values[0]/values[-1]) if values[-1] else None,
            transformed_feature_condition=float(after[0]/after[-1]) if after[-1] else None,
            feature_condition_is_not_B_condition=True, svd_backward_relative=backward,
            matrix_bytes=self.matrix.nbytes, construction_seconds=monotonic()-began,
            transform_kind="identity" if identity else "bounded_invertible_right_feature_coordinates",
            all_directions_retained=True, reference_read=False)

    def _apply(self, matrix, value):
        value = np.asarray(value, dtype=np.complex128)
        if value.size != self.size or not np.isfinite(value).all():
            raise ValueError("FEATURE_COORDINATE_LAYOUT_OR_NONFINITE")
        return np.einsum("st,t...->s...", matrix, value.reshape(self.shape)).ravel()

    def forward(self, y):
        return self._apply(self.matrix, y)

    def adjoint(self, original_adjoint):
        return self._apply(self.matrix.conj().T, original_adjoint)

    def inverse(self, delta):
        return self._apply(self.inverse_matrix, delta)

    def operator(self, original):
        return LinearOperator(original.operator().shape,
            matvec=lambda y: original.B(self.forward(y)),
            rmatvec=lambda e: self.adjoint(original.BH(e)), dtype=np.complex128)

    def verify_retained(self, delta, y, sha256):
        if sha256 != self.sha256:
            raise ValueError("RETAINED_FEATURE_TRANSFORM_IDENTITY_MISMATCH")
        error = np.linalg.norm(self.forward(y)-delta) / max(np.linalg.norm(delta), 1e-30)
        if error > 1e-10:
            raise ValueError("RETAINED_SOLVE_Y_IS_NOT_ORIGINAL_DELTA")
        return float(error)


class FeatureCoordinateCache:
    """Only axis hidden/buffer/exact-node dependencies; outputs do not change F."""

    def __init__(self, tau=1e-6, *, identity=False):
        self.tau, self.identity, self.cache = tau, identity, {}

    def get(self, model, mapping, axis, shape):
        from src.solvers.ftt_conditional_core import axis_features

        nodes = mapping.nodes[axis]
        if np.any(np.diff(nodes) <= 0):
            raise ValueError("EXACT_FEATURE_NODES_NOT_UNIQUE_SORTED")
        h = hashlib.sha256(array_identity(nodes).encode())
        for layer in (model.cores[axis][0], model.cores[axis][2]):
            for p in layer.parameters():
                h.update(p.detach().numpy().tobytes())
        for name, buffer in model.named_buffers():
            h.update(name.encode())
            h.update(buffer.detach().numpy().tobytes())
        dependency = dict(axis=axis, exact_node_sha256=array_identity(nodes),
                          hidden_phase_geometry_sha256=h.hexdigest())
        key = (axis, h.hexdigest(), tuple(shape))
        if key not in self.cache:
            normalized = (nodes-float(model.center[axis]))/float(model.half_width[axis])
            features = axis_features(model, axis, normalized)
            self.cache[key] = FeatureCoordinates(features, shape, tau=self.tau,
                                               dependency=dependency, identity=self.identity)
        return self.cache[key]


def coordinate_policy(learned):
    return dict(schema="ftt.feature-coordinate-policy.v1", inherited_rounds=12,
        total_round_limit=16 if learned else 14, new_round_limit=4 if learned else 2,
        new_visit_limit=12 if learned else 6, new_iteration_limit=14400 if learned else 7200,
        new_hidden_call_limit=80 if learned else 0, scalar_rounds=[14,16] if learned else [14],
        disable_historical_slow_streak=True, native_target=1e-8,
        validation_feedback="scalars_only", inner_refinement=True,
        conditional_extra_rounds_only=True, initial_new_visit_limit=6,
        initial_new_iteration_limit=7200, initial_new_hidden_call_limit=40)


def coordinate_trend(number, scalar, parent_scalar, policy):
    keys = ("native_relative", "scattered_E_relative", "scattered_H_relative")
    if not all(np.isfinite(s[k]) and s[k] > 0 for s in (scalar, parent_scalar) for k in keys):
        return dict(allowed=False, reason="NONFINITE_OR_NEGATIVE_SCALAR")
    ratios = {k: scalar[k]/parent_scalar[k] for k in keys}
    ordinary = max(ratios.values()) <= 0.8
    near = scalar[keys[0]] <= 1e-5 and max(scalar[k] for k in keys[1:]) <= 1e-3
    allowed = number == 14 and policy["total_round_limit"] == 16 and (ordinary or near)
    return dict(allowed=bool(allowed), reason="FIXED_FEATURE_COORDINATE_EXTRA_SIGNAL" if allowed else "AUTHORIZED_TOTAL_ROUND_LIMIT",
                ratios_R_E_H=ratios, ordinary=bool(ordinary), near_gate=bool(near), wall_reset_allowed=False)
