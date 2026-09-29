"""Read-only diagnostics of frozen FE errors; no optimizer, PC or solve loop.

Recovery is affine. Only an explicit zero interior particular solution may be
used to recover an error. Original production packet behavior is unchanged.
"""

from time import perf_counter

import numpy as np

from src.solvers.neural_fe_action_packet import operation_relative


def defect(left, right):
    absolute = float(np.linalg.norm(left - right))
    scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)))
    return dict(
        absolute=absolute,
        scale=scale,
        operation_relative=operation_relative(absolute, scale),
    )


def sum_components(left, right):
    """Norms and complex cross term in ONE common assembled row space."""
    nl, nr = float(np.linalg.norm(left)), float(np.linalg.norm(right))
    total = float(np.linalg.norm(left + right))
    cross = np.vdot(left, right)
    squared = nl**2 + nr**2 + 2 * cross.real
    return dict(
        left_norm=nl,
        right_norm=nr,
        sum_norm=total,
        cross_real=float(cross.real),
        cross_imag=float(cross.imag),
        sum_squared=total**2,
        expanded_squared=float(squared),
        squared_identity_absolute=float(abs(total**2 - squared)),
        cancellation_fraction=total / (nl + nr) if nl + nr > 1e-12 else None,
    )


def complex_correlation(
    inner_reference_candidate, reference_squared, candidate_squared
):
    """First argument conjugate convention, with no phase/amplitude fitting."""
    norm_ref, norm_candidate = np.sqrt(reference_squared), np.sqrt(candidate_squared)
    defined = norm_ref > 1e-12 and norm_candidate > 1e-12
    return dict(
        amplitude_norm_ratio=float(norm_candidate / norm_ref)
        if norm_ref > 1e-12
        else None,
        correlation=complex(inner_reference_candidate / (norm_ref * norm_candidate))
        if defined
        else None,
        correlation_defined=bool(defined),
    )


class FrozenActions:
    """Count ALL pilot actions and small Hp audit solves, including checks."""

    def __init__(self, packet, limit=128):
        self.packet = packet
        self.limit = limit
        self.counts = dict(S=0, SH=0, recover=0, uncondensed=0, Hp_audit=0)
        self.seconds = dict.fromkeys(self.counts, 0.0)
        self.zero_field = np.zeros(packet.full_rows, dtype=np.complex128)
        self.zero_port = np.zeros(packet.np, dtype=np.complex128)
        self.zero_internal = np.zeros_like(packet.a["i_rhs"])

    def _call(self, key, function, *args, **kwargs):
        used = (
            self.counts["S"] + self.counts["SH"]
            if key in ("S", "SH")
            else self.counts[key]
        )
        if used >= self.limit:
            raise RuntimeError(f"frozen diagnostic {key} action budget exhausted")
        self.counts[key] += 1
        began = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            self.seconds[key] += perf_counter() - began

    def apply(self, z):
        return self._call("S", self.packet.apply, z)

    def recover(self, z, *, homogeneous=False):
        if homogeneous:
            return self._call(
                "recover", self.packet.recover, z, rhs_i=self.zero_internal
            )
        return self._call("recover", self.packet.recover, z)

    def uncondensed(self, field, alpha):
        return self._call("uncondensed", self.packet.uncondensed, field, alpha)

    def hp_audit(self, rhs):
        return self._call("Hp_audit", np.linalg.solve, self.packet.a["Hp"], rhs)

    def B(self, alpha):
        return self.uncondensed(self.zero_field, alpha)[0]


def state_audits(actions, states):
    """Recompute each frozen state once, caching vectors for later identities."""
    p, a = actions.packet, actions.packet.a
    native_rhs = a["g"] - actions.B(actions.hp_audit(a["gp"]))
    rhs_norm = float(np.linalg.norm(np.r_[a["g"], a["gp"]]))
    cache, records = {}, {}
    for name, z in states.items():
        field = actions.recover(z)
        alpha = z[p.nt :]
        Sz = actions.apply(z)
        body, port_raw, Dfield = actions.uncondensed(field, alpha)
        rfe, rp = a["g"] - body, a["gp"] + port_raw
        native = rfe - actions.B(actions.hp_audit(rp))
        r = a["b"] - Sz
        injected = np.zeros_like(field)
        injected[a["masters"]] = r[: p.nt]
        total_body, total_port, _ = actions.uncondensed(
            a["background"] + field, a["background_alpha"] + alpha
        )
        total_residual = np.r_[a["total_g"] - total_body, total_port]
        port_scale = float(
            np.linalg.norm(a["gp"])
            + np.linalg.norm(Dfield)
            + np.linalg.norm(a["Hp"] @ alpha)
        )
        records[name] = dict(
            schur_absolute=float(np.linalg.norm(r)),
            schur_rhs_norm=p.bnorm,
            schur_relative=float(np.linalg.norm(r) / p.bnorm),
            augmented_absolute=float(np.linalg.norm(np.r_[rfe, rp])),
            augmented_rhs_norm=rhs_norm,
            augmented_relative=float(np.linalg.norm(np.r_[rfe, rp]) / rhs_norm),
            native_absolute=float(np.linalg.norm(native)),
            native_rhs_norm=float(np.linalg.norm(native_rhs)),
            native_relative=float(np.linalg.norm(native) / np.linalg.norm(native_rhs)),
            total_augmented_absolute=float(np.linalg.norm(total_residual)),
            total_rhs_norm=float(np.linalg.norm(a["total_g"])),
            total_augmented_relative=float(
                np.linalg.norm(total_residual) / np.linalg.norm(a["total_g"])
            ),
            port_absolute=float(np.linalg.norm(rp)),
            port_full_rhs_relative=float(np.linalg.norm(rp) / rhs_norm),
            port_operation_scale=port_scale,
            port_operation_relative=operation_relative(np.linalg.norm(rp), port_scale),
            recovery_relative=float(np.linalg.norm(rfe[a["idofs"]]) / rhs_norm),
            slave_storage_max=float(np.max(np.abs(field[a["slaves"]]), initial=0)),
            schur_body_identity=defect(rfe, injected),
            schur_port_identity=defect(rp, r[p.nt :]),
        )
        cache[name] = dict(
            z=z,
            field=field,
            Sz=Sz,
            r=r,
            rfe=rfe,
            rp=rp,
            native=native,
            total_residual=total_residual,
        )
    return cache, records


def error_diagnostics(actions, cache, reference_name="REF7"):
    """Same error in Schur, original body/port, native, and homogeneous fields."""
    p, a = actions.packet, actions.packet.a
    reference = cache[reference_name]
    particular = cache["Z0"]["field"]
    reference_gain = float(
        np.linalg.norm(reference["Sz"]) / np.linalg.norm(reference["z"])
    )
    records, errors = {}, {}
    for name, state in cache.items():
        if name == reference_name:
            continue
        e = reference["z"] - state["z"]
        Se = actions.apply(e)
        delta = reference["field"] - state["field"]
        homogeneous = actions.recover(e, homogeneous=True)
        default_error = actions.recover(e)
        total_difference = (
            a["background"] + reference["field"] - (a["background"] + state["field"])
        )
        alpha_error = e[p.nt :]
        body_v, _, d = actions.uncondensed(delta, actions.zero_port)
        body_b, minus_h, _ = actions.uncondensed(actions.zero_field, alpha_error)
        h = -minus_h
        native_port = actions.B(actions.hp_audit(d))
        augmented_difference = np.r_[
            state["rfe"] - reference["rfe"], state["rp"] - reference["rp"]
        ]
        body_cross = sum_components(body_v, body_b)
        port_cross = sum_components(-d, h)
        native_cross = sum_components(body_v, native_port)
        original_error_response = np.r_[body_v + body_b, -d + h]
        records[name] = dict(
            residual_identity=defect(Se, state["r"] - reference["r"]),
            homogeneous_recovery=defect(delta, homogeneous),
            affine_difference=defect(delta, default_error - particular),
            wrong_default_recovery_error_norm=float(
                np.linalg.norm(default_error - delta)
            ),
            particular_norm=float(np.linalg.norm(particular)),
            background_cancellation=defect(delta, total_difference),
            slave_error_max=float(np.max(np.abs(delta[a["slaves"]]), initial=0)),
            augmented_identity=defect(original_error_response, augmented_difference),
            native_identity=defect(
                body_v + native_port, state["native"] - reference["native"]
            ),
            body=body_cross,
            port=port_cross,
            native=native_cross,
            V_delta_u_norm=float(np.linalg.norm(body_v)),
            B_error_alpha_norm=float(np.linalg.norm(body_b)),
            Dp_delta_u_norm=float(np.linalg.norm(d)),
            Hp_error_alpha_norm=float(np.linalg.norm(h)),
            error_norm=float(np.linalg.norm(e)),
            Se_norm=float(np.linalg.norm(Se)),
            reference_direction_gain=reference_gain,
            direction_gain_ratio=float(
                np.linalg.norm(Se) / np.linalg.norm(e) / reference_gain
            )
            if np.linalg.norm(e) > 1e-12
            else None,
            schur_trace_residual_squared=float(np.linalg.norm(state["r"][: p.nt]) ** 2),
            schur_port_residual_squared=float(np.linalg.norm(state["r"][p.nt :]) ** 2),
            schur_residual_squared=float(np.linalg.norm(state["r"]) ** 2),
            original_trace_response_norm=float(
                np.linalg.norm((body_v + body_b)[a["masters"]])
            ),
            original_internal_response_norm=float(
                np.linalg.norm((body_v + body_b)[a["idofs"]])
            ),
        )
        errors[name] = dict(
            e=e,
            Se=Se,
            delta=delta,
            homogeneous=homogeneous,
            a=body_v,
            c=body_b,
            d=d,
            h=h,
            native_port=native_port,
            augmented=original_error_response,
            default_error=default_error,
        )
    return errors, records
