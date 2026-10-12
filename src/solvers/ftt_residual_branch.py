"""One additive neural correction, with distinct training and physical RHS."""

from copy import deepcopy
import numpy as np

from src.solvers.neural_fe_action_packet import array_hash


def residual_policy(learned):
    return dict(
        schema="ftt.one-residual-policy.v1",
        inherited_rounds=0,
        total_round_limit=6,
        new_round_limit=6,
        new_visit_limit=18,
        new_iteration_limit=21600,
        new_hidden_call_limit=120 if learned else 0,
        scalar_rounds=[2, 4],
        disable_historical_slow_streak=True,
        native_target=1e-8,
        validation_feedback="scalars_only",
        inner_refinement=True,
    )


def residual_trend(number, scalars, policy):
    keys = (
        "native_relative",
        "augmented_relative",
        "scattered_E_relative",
        "scattered_H_relative",
        "scattered_curl_relative",
    )
    valid = all(np.isfinite(scalars[k]) and scalars[k] >= 0 for k in keys)
    return dict(
        allowed=bool(valid and number < policy["total_round_limit"]),
        reason="RESIDUAL_ROUND_DIAGNOSTIC_ONLY"
        if valid
        else "NONFINITE_OR_NEGATIVE_SCALAR",
    )


def same_saved_state(left, right):
    """Compare nested RNG state without changing it or relying on serialization."""
    if type(left) is not type(right):
        return False
    if isinstance(left, np.ndarray):
        return left.dtype == right.dtype and np.array_equal(left, right)
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            same_saved_state(left[k], right[k]) for k in left
        )
    if isinstance(left, (tuple, list)):
        return len(left) == len(right) and all(
            same_saved_state(a, b) for a, b in zip(left, right)
        )
    if hasattr(left, "equal"):
        return left.dtype == right.dtype and left.equal(right)
    return left == right


class ResidualTrainingAction:
    """Borrow A unchanged; audit only the combined field using original f."""

    def __init__(self, physical, c_base, g=None, *, expected=None):
        self.physical = physical
        self.c_base = np.asarray(c_base, dtype=np.complex128).copy()
        self.f = (
            physical.f - physical.apply(self.c_base)
            if g is None
            else np.asarray(g, dtype=np.complex128).copy()
        )
        if self.c_base.shape != (physical.size,) or self.f.shape != self.c_base.shape:
            raise ValueError("RESIDUAL_BASE_AND_TRAINING_RHS_LAYOUT")
        if not np.isfinite(self.c_base).all() or not np.isfinite(self.f).all():
            raise ValueError("RESIDUAL_NONFINITE_FIXED_FIELDS")
        self.bnorm = float(np.linalg.norm(self.f))
        self.original_bnorm = physical.bnorm
        if not self.bnorm > 0:
            raise ValueError("RESIDUAL_ZERO_RHS_REQUIRES_ORIGINAL_FULL_VALIDATION")
        self.identity = dict(
            c_base_sha256=array_hash(self.c_base),
            training_rhs_sha256=array_hash(self.f),
            original_rhs_sha256=array_hash(physical.f),
            bnorm_train=self.bnorm,
            bnorm_original=self.original_bnorm,
        )
        if expected is not None and self.identity != expected:
            raise ValueError("RESIDUAL_BASE_G_OR_DENOMINATOR_IDENTITY_CHANGED")
        self.c_base.setflags(write=False)
        self.f.setflags(write=False)
        self.size, self.nc, self.np = physical.size, physical.nc, physical.np
        self.counts, self.costs = physical.counts, physical.costs

    def apply(self, vector, *, adjoint=False):
        return self.physical.apply(vector, adjoint=adjoint)

    def combined(self, c_delta):
        return self.c_base + np.asarray(c_delta, dtype=np.complex128)

    def original_relative(self, r_training):
        return float(np.linalg.norm(r_training) / self.original_bnorm)

    def audit(self, c_delta):
        return self.physical.audit(self.combined(c_delta))

    def fields(self, c_delta, r_training):
        if array_hash(self.physical.f) != self.identity["original_rhs_sha256"]:
            raise ValueError("RESIDUAL_ORIGINAL_ACTION_RHS_MUTATED")
        combined = self.combined(c_delta)
        original = self.physical.apply(combined) - self.physical.f
        if np.linalg.norm(original - r_training) / self.original_bnorm > 1e-10:
            raise ValueError("RESIDUAL_ORIGINAL_AND_TRAINING_EQUATION_MISMATCH")
        return dict(
            c_base=self.c_base.copy(),
            c_delta=np.array(c_delta, copy=True),
            c_combined=combined,
            r_original=original,
            g=self.f.copy(),
        )


def frozen_base_and_zero_correction(base):
    """Copy all functions; only the z output is zero, with no writable alias."""
    if base.model_kind != "fttnn" or base.hidden_width != 32:
        raise ValueError("RESIDUAL_FIXED_W32_R8_BASE_REQUIRED")
    base.requires_grad_(False)
    for p in base.parameters():
        p.grad = None
    correction = deepcopy(base).requires_grad_(True)
    import torch

    with torch.no_grad():
        correction.cores[2][-1].weight.zero_()
        correction.cores[2][-1].bias.zero_()
    for p in correction.parameters():
        p.grad = None
    base_tensors = dict(base.named_parameters()) | dict(base.named_buffers())
    correction_tensors = dict(correction.named_parameters()) | dict(
        correction.named_buffers()
    )
    if any(
        base_tensors[k].data_ptr() == value.data_ptr()
        for k, value in correction_tensors.items()
    ):
        raise ValueError("RESIDUAL_WRITABLE_BASE_CORRECTION_ALIAS")
    return correction


class ResidualBranchContext:
    def __init__(self, base, view, binding):
        from src.solvers.ftt_factored_moments import model_identity

        self.base, self.view, self.binding = base, view, deepcopy(binding)
        self.base_state = deepcopy(base.state_dict())
        self.base_hash = model_identity(base)

    def check_base(self):
        if any(p.requires_grad for p in self.base.parameters()) or any(
            not value.equal(self.base_state[key])
            for key, value in self.base.state_dict().items()
        ):
            raise ValueError("RESIDUAL_FROZEN_BASE_OR_BUFFERS_CHANGED")

    def checkpoint_fields(self, c_delta, r_training):
        self.check_base()
        return dict(
            self.view.fields(c_delta, r_training),
            base_model=deepcopy(self.base_state),
            residual_branch_identity=deepcopy(self.binding),
            base_model_hash=self.base_hash,
            base_RNG=deepcopy(getattr(self, "base_RNG", None)),
        )

    def verify_saved(self, state):
        self.check_base()
        if not same_saved_state(state.get("base_RNG"), getattr(self, "base_RNG", None)):
            raise ValueError("RESIDUAL_SAVED_FROZEN_BASE_RNG_CHANGED")
        if (
            state.get("residual_branch_identity") != self.binding
            or state.get("base_model_hash") != self.base_hash
        ):
            raise ValueError("RESIDUAL_SAVED_BASE_G_OR_BRANCH_IDENTITY_CHANGED")
        if not all(
            value.equal(state["base_model"][key])
            for key, value in self.base_state.items()
        ):
            raise ValueError("RESIDUAL_SAVED_FROZEN_BASE_CHANGED")
        for key in ("center", "half_width", "initial_core_scales") + getattr(
            self.base, "phase_buffer_names", ()
        ):
            if key in state.get("model", {}) and not state["model"][key].equal(
                self.base_state[key]
            ):
                raise ValueError("RESIDUAL_SAVED_CORRECTION_PHASE_OR_BUFFERS_CHANGED")
        if not np.array_equal(state["g"], self.view.f) or not np.array_equal(
            state["c_base"], self.view.c_base
        ):
            raise ValueError("RESIDUAL_SAVED_FIXED_ARRAYS_CHANGED")
        if not np.array_equal(state["c_delta"], state["c"]) or not np.array_equal(
            state["c_combined"], self.view.combined(state["c_delta"])
        ):
            raise ValueError("RESIDUAL_PARTIAL_OR_REPEATED_CORRECTION_RECOVERY")
        if (
            np.linalg.norm(state["r_original"] - state["r"]) / self.view.original_bnorm
            > 1e-10
        ):
            raise ValueError("RESIDUAL_SAVED_ORIGINAL_RESIDUAL_CHANGED")


def independent_sum_field(base, correction):
    """Old pointwise MLP+chi for each branch, then add before interpolation."""
    import torch
    from src.solvers.ftt_bloch_field import IndependentPointPhase

    class AdditivePoints(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.base_points = IndependentPointPhase(base)
            self.correction_points = IndependentPointPhase(correction)

        def forward(self, coordinates):
            return self.base_points(coordinates) + self.correction_points(coordinates)

    return AdditivePoints()
