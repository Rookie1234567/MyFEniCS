"""Bounded, unlabelled phase75 probes and fixed-metric qualification."""

from pathlib import Path
from time import perf_counter
import numpy as np
from scipy import sparse

from src.solvers.feinn_phase_training import configure, policy, install_data_guard
from src.solvers.feinn_phase_verification import restore_network
from src.solvers.feinn_cached_derivatives import CachedMomentJacobian, model_key
from src.solvers.feinn_parameter_jvp import MomentJacobian
from src.solvers.feinn_parameter_metric import (
    GROUP_SIZES,
    ParameterMetric,
    grouped_metric,
)
from src.solvers.feinn_gn_training import GNProblem, GNStop
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import load_moments, parameters, paired, assign
from src.solvers.feinn_native import load_native, ResidualMetric
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    atomic_write,
    digest,
    load_checkpoint,
    parameter_order,
)


def load_anchor(design, entry):
    for key in ("checkpoint", "durable_final", "checkpoint_index"):
        if digest(entry[key]["path"]) != entry[key]["sha256"]:
            raise ValueError("PHASE75_FROZEN_FILE_IDENTITY_FAILED:" + key)
    if (
        entry["durable_final"]["sha256"]
        != "cf6919a8ee86e32ad7f0f4b0d4ef8411061b149c564dd289237334f90b7d9e86"
        or entry["checkpoint"]["sha256"]
        != "4b538b3f785902de369d5a0602b5d3267a08cc34fa8e68ab509ebc51c2652917"
    ):
        raise ValueError("NOT_AUTHORIZED_PHASE75_STATE")
    model, c, saved = restore_network(
        design,
        entry["checkpoint"],
        entry["durable_final"],
        phase=True,
        supervised=False,
    )
    meta, gn = saved["metadata"], saved["optimizer"]
    if (
        saved["optimizer_class"] != "DampedGNState"
        or gn["accepted"] != 75
        or gn["pc_builds"]
        or gn["V"] is not None
        or gn["lam"] is not None
        or meta["source_sha"] != entry["source_sha"]
    ):
        raise ValueError("PHASE75_SOURCE_GN_OR_NO_PC_IDENTITY_FAILED")
    if (
        array_hash(c) != meta["complete_c_sha256"]
        or array_hash(parameters(model)) != meta["parameter_sha256"]
        or any(gn[k] != meta[k] for k in ("mu", "h0"))
    ):
        raise ValueError("PHASE75_PARAMETER_FIELD_GN_MISMATCH")
    for k, value in policy(False).items():
        if meta[k] is not value:
            raise ValueError("PHASE75_LABEL_POLICY_MISMATCH:" + k)
    for k in ("torch_rng", "numpy_rng", "python_rng", "complete_c"):
        if k not in saved:
            raise ValueError("PHASE75_RECOVERY_STATE_NOT_RETAINED:" + k)
    return model, c, saved


def load_metric_recovery(design, entry, recovery):
    model, _, anchor_state = load_anchor(design, entry)
    for k in (
        "checkpoint_pointer",
        "durable_final",
        "history",
        "prior_manifest",
        "prior_summary",
    ):
        if digest(recovery[k]["path"]) != recovery[k]["sha256"]:
            raise ValueError("METRIC_RECOVERY_BYTES_CHANGED:" + k)
    state = load_checkpoint(
        recovery["durable_final"]["path"], recovery["durable_final"]["sha256"]
    )
    meta = state["metadata"]
    if (
        state["optimizer_class"] != "MetricDampedGNState"
        or state["parameter_order"] != parameter_order(model)
        or meta != recovery["committed_metadata"]
        or meta["prefix_sha256"] != entry["durable_final"]["sha256"]
    ):
        raise ValueError("NOT_SAME_OWN_METRIC_FORK_BOUNDARY")
    if (
        state["optimizer"]["parameter_metric"]["sha256"]
        != meta["parameter_metric_sha256"]
    ):
        raise ValueError("METRIC_RECOVERY_SCALE_CHANGED")
    for k in ("native_sha256", "Gram_sha256", "moments_sha256", "buffers_sha256"):
        if meta[k] != anchor_state["metadata"][k]:
            raise ValueError("METRIC_RECOVERY_PHYSICAL_IDENTITY_CHANGED:" + k)
    for k, v in policy(False).items():
        if meta[k] is not v:
            raise ValueError("METRIC_RECOVERY_LABEL_CHANGED")
    if (
        state["optimizer"]["pc_builds"]
        or state["optimizer"]["V"] is not None
        or state["optimizer"]["h0"] != anchor_state["optimizer"]["h0"]
    ):
        raise ValueError("METRIC_RECOVERY_PC_OR_H0_CHANGED")
    model.load_state_dict(state["model"], strict=True)
    if (
        array_hash(parameters(model)) != meta["parameter_sha256"]
        or array_hash(state["complete_c"]) != meta["complete_c_sha256"]
    ):
        raise ValueError("METRIC_RECOVERY_PARAMETER_OR_C_CHANGED")
    return model, state["complete_c"], state


def setup(
    design, native, qualification, artifact, marker, manifest, cap, extra_allowed=()
):
    configure()
    from src.runners.feinn_metric_campaign import anchor

    entry = anchor()
    allowed = (
        [native["files"][k]["path"] for k in ("native", "gram")]
        + [qualification["files"]["moments"]["path"]]
        + [
            entry[k]["path"]
            for k in ("checkpoint", "durable_final", "checkpoint_index")
        ]
    )
    allowed.extend(extra_allowed)
    reads = install_data_guard(allowed, artifact, supervised=False)
    model, saved_c, saved = load_anchor(design, entry)
    expected = {
        "native_sha256": native["files"]["native"]["sha256"],
        "Gram_sha256": native["files"]["gram"]["sha256"],
        "moments_sha256": qualification["files"]["moments"]["sha256"],
    }
    if any(saved["metadata"][k] != v for k, v in expected.items()):
        raise ValueError("PHASE75_ORIGINAL_A_G_MOMENTS_IDENTITY_FAILED")
    sizes = tuple(parameter.numel() for _, parameter in model.named_parameters())
    if sizes != GROUP_SIZES:
        raise ValueError("EIGHT_W_B_GROUP_ORDER_CHANGED")
    packet = load_native(native["files"]["native"]["path"])
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    factor = SparseRiesz(
        sparse.load_npz(native["files"]["gram"]["path"]), design, marker
    )
    metric = ResidualMetric(packet, factor)
    if abs(metric.denominator - saved["metadata"]["d_G"]) > 1e-10 * metric.denominator:
        factor.close()
        raise ValueError("PHASE75_ORIGINAL_RIESZ_DENOMINATOR_CHANGED")
    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )
    problem = None

    def guard(kind):
        if perf_counter() + 15 >= cutoff:
            raise GNStop("METRIC_DIAGNOSTIC_SAVE_RESERVE")
        if problem is not None and kind == "K" and problem.counts["K"] >= cap:
            raise GNStop("METRIC_K_ACTION_CAP")

    problem = GNProblem(model, mapping, packet, metric, supervised=False, guard=guard)
    problem.jac = CachedMomentJacobian(mapping)
    actual = mapping.forward(model)
    identity = paired(actual, saved_c)
    audit = packet.audit(actual)
    if (
        identity["relative"] > 1e-12
        or abs(audit["native_relative"] - 0.9788211986315143) > 1e-10
    ):
        factor.close()
        raise ValueError("PHASE75_FORWARD_OR_NATIVE_IDENTITY_FAILED")
    proof = dict(
        frozen=entry,
        parameter_to_saved_c=identity,
        original_audit=audit,
        parameter_sha256=array_hash(parameters(model)),
        complete_c_sha256=array_hash(actual),
        GN={
            k: saved["optimizer"][k]
            for k in (
                "h0",
                "mu",
                "accepted",
                "slow_streak",
                "last_pc_outer",
                "pc_max_builds",
            )
        },
        PC_present=False,
        RNG_retained=True,
        parameter_only=False,
        d_G=metric.denominator,
        actual_artifact_reads=reads,
        allowed_artifact_paths=allowed,
        source_sha=manifest["source_sha"],
        parameter_source_sha=saved["metadata"]["source_sha"],
    )
    return problem, factor, saved, proof


def finish(problem, factor, proof):
    cache = problem.jac.record()
    problem.jac.invalidate()
    factor.close()
    return dict(
        identity=proof,
        counts=problem.counts,
        JVP_VJP_counts=problem.jac.counts,
        native_action_counts=problem.packet.counts,
        native_action_costs=problem.packet.costs,
        G_factor=factor.record,
        Gsolve_count=factor.solves,
        derivative_cache=cache,
        Maxwell_factor_created=False,
        global_Maxwell_matrix_created=False,
        **policy(False),
    )


def diagnose(design, native, qualification, artifact, marker, manifest):
    p, factor, saved, proof = setup(
        design, native, qualification, artifact, marker, manifest, 32
    )
    theta0 = parameters(p.model).copy()
    key0 = model_key(p.model)
    rows, trials, negative_roundoff = [], [], []
    try:
        loss, g, c = p.value_gradient()
        r = p.packet.apply(c) - p.packet.f
        f2 = float(np.vdot(p.packet.f, p.packet.f).real)
        gE = p.jac.vjp(p.model, p.packet.apply(r, adjoint=True) / f2)
        euclidean_loss = float(np.vdot(r, r).real / (2 * f2))
        ng, ne = np.linalg.norm(g), np.linalg.norm(gE)
        cosine = float(g @ gE / (ng * ne)) if ng and ne else None
        rng = np.random.default_rng(4211101)
        q, offset = [], 0
        for name, size in zip([n for n, _ in p.model.named_parameters()], GROUP_SIZES):
            curve, norms, damp = [], [], []
            for _ in range(3):
                v = np.zeros(len(theta0))
                v[offset : offset + size] = rng.choice(
                    [-1.0, 1.0], size=size
                ) / np.sqrt(size)
                Kv = p.K(v)
                value = float(v @ Kv)
                tolerance = (
                    256 * np.finfo(float).eps * np.linalg.norm(v) * np.linalg.norm(Kv)
                )
                if value < -tolerance or not np.isfinite(value):
                    raise ValueError("GROUP_SIGNIFICANT_NEGATIVE_CURVATURE")
                if value < 0:
                    negative_roundoff.append(
                        dict(group=name, raw=value, tolerance=tolerance)
                    )
                    value = 0.0
                curve.append(value)
                norms.append(float(np.linalg.norm(Kv)))
                damp.append(
                    saved["optimizer"]["mu"] / (value + saved["optimizer"]["mu"])
                )
            sl = slice(offset, offset + size)
            rows.append(
                dict(
                    name=name,
                    size=size,
                    q=curve,
                    K_norm=norms,
                    damping_fraction=damp,
                    parameter_RMS=float(np.linalg.norm(theta0[sl]) / np.sqrt(size)),
                    gradient_RMS=float(np.linalg.norm(g[sl]) / np.sqrt(size)),
                    dispersion_std=float(np.std(curve)),
                    peak_to_mean=float(
                        max(curve) / max(np.mean(curve), np.finfo(float).tiny)
                    ),
                )
            )
            q.append(curve)
            offset += size
            marker("metric_group_probe", rows[-1])
        if offset != 8966:
            raise ValueError("EIGHT_PARAMETER_GROUP_LAYOUT_CHANGED")
        metric, estimate = grouped_metric(q)
        mu = saved["optimizer"]["mu"]
        for name, d, diagonal in (
            ("I", g, np.ones(len(g))),
            ("M", metric.inverse * g, metric.diagonal),
        ):
            Kd = p.K(d)
            denominator = float(d @ Kd + mu * np.dot(d * diagonal, d))
            if denominator <= 0 or g @ d <= 0:
                trials.append(
                    dict(
                        metric=name,
                        valid=False,
                        reason="NON_DESCENT_DIAGNOSTIC_DIRECTION",
                    )
                )
                continue
            alpha = float(g @ d / denominator)
            base = -alpha * d
            for scale in (1.0, 0.1):
                p.guard("trial")
                if len([r for r in trials if r.get("valid")]) >= 4:
                    raise ValueError("A_TRUE_TRIAL_CAP")
                try:
                    value = p.value(theta0 + scale * base)
                    actual = p.mapping.forward(p.model)
                    audit = p.packet.audit(actual)
                finally:
                    p.value(theta0, restore_only=True)
                s = scale * base
                pred = float(-g @ s - 0.5 * scale**2 * alpha**2 * (d @ Kd))
                slices = np.cumsum((0,) + GROUP_SIZES)
                trials.append(
                    dict(
                        metric=name,
                        scale=scale,
                        valid=True,
                        alpha=alpha,
                        loss=value,
                        pred=pred,
                        ared=float(loss - value),
                        euclidean_first_order=float(gE @ s),
                        group_step_norms=[
                            float(np.linalg.norm(s[slices[i] : slices[i + 1]]))
                            for i in range(8)
                        ],
                        **audit,
                    )
                )
                marker("metric_diagnostic_trial", trials[-1])
        if (
            not np.array_equal(parameters(p.model), theta0)
            or model_key(p.model) != key0
        ):
            raise ValueError("DIAGNOSTIC_TRIAL_DID_NOT_RESTORE_THETA0")
        p.jac.ensure(p.model)
        cached_restore = p.jac.key == key0
        saturation = [
            dict(
                layer=i,
                tanh_abs_ge_099_fraction=sum(
                    np.count_nonzero(np.abs(b[2][i + 1].numpy()) >= 0.99)
                    for b in p.jac.blocks
                )
                / sum(b[2][i + 1].numel() for b in p.jac.blocks),
            )
            for i in range(3)
        ]
        signal = estimate["curvature_span"] >= 10 and any(
            t.get("metric") == "M"
            and t.get("valid")
            and t["loss"] < loss
            and t["native_relative"]
            <= 1.01 * proof["original_audit"]["native_relative"]
            for t in trials
        )
        path = Path(artifact) / "fixed_parameter_metric.npz"
        atomic_write(
            path,
            lambda stream: np.savez(
                stream,
                M=metric.diagonal,
                S=metric.S,
                theta0_sha256=array_hash(theta0),
                metric_sha256=metric.sha256,
            ),
        )
        result = dict(
            status="BLOCK_METRIC_PILOT_ADMITTED"
            if signal
            else "BLOCK_METRIC_PILOT_NOT_ADMITTED",
            C_start_signal=bool(signal),
            gradient_cosine=cosine,
            Riesz_gradient_norm=float(ng),
            euclidean_gradient_norm=float(ne),
            original_loss=loss,
            euclidean_loss=euclidean_loss,
            groups=rows,
            estimate=estimate,
            metric_sha256=metric.sha256,
            trials=trials,
            negative_roundoff=negative_roundoff,
            saturation=saturation,
            committed_updates=0,
            theta0_restored=True,
            cache_restored=cached_restore,
            **finish(p, factor, proof),
        )
        return result, dict(metric=path)
    finally:
        assign(p.model, theta0)
        p.jac.invalidate()
        factor.close()


def qualify(design, native, qualification, diagnostic, artifact, marker, manifest):
    p, factor, saved, proof = setup(
        design,
        native,
        qualification,
        artifact,
        marker,
        manifest,
        96,
        [diagnostic["files"]["metric"]["path"]],
    )
    theta0 = parameters(p.model).copy()
    try:
        with np.load(diagnostic["files"]["metric"]["path"], allow_pickle=False) as data:
            metric = ParameterMetric(data["M"])
        if metric.sha256 != diagnostic["result"]["metric_sha256"]:
            raise ValueError("FIXED_METRIC_BYTES_CHANGED")
        loss, g, _ = p.value_gradient()
        independent = MomentJacobian(p.mapping)
        rng = np.random.default_rng(4211102)
        rows = []
        for i in range(3):
            v = rng.normal(size=len(g))
            v /= np.linalg.norm(v)
            Kv = metric.curvature(p.K, v)
            j = independent.jvp(p.model, metric.S * v)
            Aj = p.packet.apply(j)
            dual = p.packet.apply(factor.solve(Aj), adjoint=True) / p.metric.denominator
            direct = metric.S * independent.vjp(p.model, dual)
            chain = paired(Kv, direct)
            # Independent parameter-direction finite difference of the actual objective.
            derivatives = []
            for eps in (1e-5, 1e-6, 1e-7):
                try:
                    plus = p.value(theta0 + eps * metric.S * v)
                    minus = p.value(theta0 - eps * metric.S * v)
                finally:
                    p.value(theta0, restore_only=True)
                actual = (plus - minus) / (2 * eps)
                expected = float(np.dot(metric.S * g, v))
                derivatives.append(
                    dict(
                        epsilon=eps,
                        actual=actual,
                        expected=expected,
                        relative=abs(actual - expected)
                        / max(abs(actual), abs(expected), 1e-12),
                    )
                )
            row = dict(
                direction=i, transformed_K_pair=chain, finite_difference=derivatives
            )
            rows.append(row)
            marker("metric_real_chain_check", row)
        # One independent original AD-VJP comparison; cached g_y must equal S*g.
        c = p.mapping.forward(p.model)
        _, _, dual = p.metric.value(c, gradient=True)
        direct_g = independent.vjp(p.model, dual)
        gradient = paired(metric.S * g, metric.S * direct_g)
        from src.solvers.damped_gauss_newton import damped_cg

        identity_metric = ParameterMetric(np.ones(len(g)))
        old_step, old_cg = damped_cg(p.K, g, saved["optimizer"]["mu"], max_iter=3)
        new_step, new_cg = identity_metric.solve(
            p.K, g, saved["optimizer"]["mu"], max_iter=3
        )
        step_pair = paired(new_step, old_step)
        old_pred = float(-g @ old_step - 0.5 * old_step @ p.K(old_step))
        new_pred = float(-g @ new_step - 0.5 * new_step @ p.K(new_step))
        try:
            old_trial = p.value(theta0 + old_step)
            new_trial = p.value(theta0 + new_step)
        finally:
            p.value(theta0, restore_only=True)
        proposal = dict(
            S_is_identity=True,
            qualification_CG_limit=3,
            old_cg=old_cg,
            new_cg=new_cg,
            step_pair=step_pair,
            pred_pair=paired(new_pred, old_pred),
            ared_pair=paired(loss - new_trial, loss - old_trial),
        )
        restored = np.array_equal(parameters(p.model), theta0)
        passed = (
            restored
            and gradient["relative"] <= 1e-9
            and all(
                proposal[k]["relative"] <= 1e-9
                for k in ("step_pair", "pred_pair", "ared_pair")
            )
            and all(
                r["transformed_K_pair"]["relative"] <= 1e-9
                and sum(d["relative"] <= 1e-5 for d in r["finite_difference"]) >= 2
                for r in rows
            )
        )
        return dict(
            status="PARAMETER_METRIC_INTERFACE_PASS"
            if passed
            else "PARAMETER_METRIC_INTERFACE_FAILED",
            passed=bool(passed),
            actual_g_y=gradient,
            directions=rows,
            reference_loaded=False,
            theta0_restored=restored,
            real_K_actions_including_independent_chains=p.counts["K"] + len(rows),
            metric_sha256=metric.sha256,
            anchor_mu=saved["optimizer"]["mu"],
            identity_short_proposal=proposal,
            **finish(p, factor, proof),
        ), {}
    finally:
        assign(p.model, theta0)
        p.jac.invalidate()
        factor.close()
