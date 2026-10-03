"""Fixed saved-state local real-parameter projections, never training.

Reference-derived directions remain inside this opt-in diagnostic. Every
forward witness restores theta; no optimizer/update/checkpoint is exported.
"""

from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from src.runners.feinn_workflow import write_json
from src.solvers.feinn_diagnostic_algebra import energy, quadratic_change, project_real
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_error_geometry import reference_label
from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import SparseRiesz
from src.solvers.feinn_saved_attribution import DiagnosticActions, frozen_fields
from src.solvers.feinn_saved_state import checked_entry, model_state
from src.solvers.neural_fe_action_packet import array_hash, operation_relative


def parameter_groups(model):
    offset = 0
    groups = []
    for name, p in model.named_parameters():
        groups.append((name, slice(offset, offset + p.numel())))
        offset += p.numel()
    if len(groups) != 8 or offset != 8966:
        raise ValueError("FIXED_EIGHT_PARAMETER_GROUPS_REQUIRED")
    return groups


def grouped_directions(groups, gradients):
    vectors, descriptions = [], []
    for kind, g in gradients.items():
        for name, sl in groups:
            n = float(np.linalg.norm(g[sl]))
            row = dict(
                kind=kind,
                group=name,
                gradient_norm=n,
                gradient_RMS=n / np.sqrt(sl.stop - sl.start),
            )
            if n == 0:
                row["status"] = "ZERO_DIRECTION_REMOVED"
            else:
                v = np.zeros_like(g)
                v[sl] = -g[sl] / n
                row.update(status="UNIT_REAL_GROUP_DIRECTION", column=len(vectors))
                vectors.append(v)
            descriptions.append(row)
    return np.column_stack(vectors), descriptions


def seam_and_owner(model, mapping, cache, packet, c):
    import torch

    seam = {}
    box = np.array(
        [
            [
                float(model.center[i] - model.half_width[i]),
                float(model.center[i] + model.half_width[i]),
            ]
            for i in range(3)
        ]
    )
    for axis in (0, 1):
        other = [j for j in range(3) if j != axis]
        a, b = np.meshgrid(*[np.linspace(*box[j], 5) for j in other], indexing="ij")
        left = np.zeros((25, 3))
        left[:, axis] = box[axis, 0]
        left[:, other[0]] = a.ravel()
        left[:, other[1]] = b.ravel()
        right = left.copy()
        right[:, axis] = box[axis, 1]
        phase = np.exp(
            1j * float(model.phase_k_inc[axis]) * (box[axis, 1] - box[axis, 0])
        )
        with torch.no_grad():
            L = model(torch.as_tensor(left)).numpy()
            R = model(torch.as_tensor(right)).numpy()
        seam["xy"[axis]] = dict(
            raw_value_absolute=float(np.linalg.norm(R - phase * L)),
            raw_value_operation_relative=operation_relative(
                np.linalg.norm(R - phase * L), np.linalg.norm(R) + np.linalg.norm(L)
            ),
            phase=[phase.real, phase.imag],
            points_per_face=25,
        )
    expected = packet.expand(c)
    owner_squared, slave_squared, slave_scale = 0.0, 0.0, 0.0
    owners = mapping.packet["owner_rows"]
    slave_set = set(map(int, packet.a["slaves"]))
    slave_mask = np.array(
        [[int(x) in slave_set for x in row] for row in packet.a["cell_dofs"]]
    )
    with torch.no_grad():
        for first, stop, xs, _, phase in cache.chunks(model, 8):
            w, b = cache.weights[-1]
            value = torch.nn.functional.linear(xs[-1], w, b).reshape(-1, 3, 2)
            value = torch.complex(value[..., 0], value[..., 1]) * phase[:, None]
            local = cache.moments(
                value.numpy().reshape(stop - first, -1, 3), first, stop
            )
            selected = owners[first:stop] >= 0
            owner_squared += float(
                np.linalg.norm(local[selected] - expected[first:stop][selected]) ** 2
            )
            mask = slave_mask[first:stop]
            slave_squared += float(
                np.linalg.norm(local[mask] - expected[first:stop][mask]) ** 2
            )
            slave_scale += float(
                np.linalg.norm(local[mask]) ** 2
                + np.linalg.norm(expected[first:stop][mask]) ** 2
            )
    return dict(
        raw_periodic_faces=seam,
        independent_owner_moment_absolute=np.sqrt(owner_squared),
        independent_owner_moment_relative=np.sqrt(owner_squared) / np.linalg.norm(c),
        raw_slave_moments_vs_MPC_absolute=np.sqrt(slave_squared),
        raw_slave_moments_vs_MPC_relative=np.sqrt(
            slave_squared / max(slave_scale, np.finfo(float).tiny)
        ),
        actual_FE_MPC_test="independent FE restoration in v12_saved_field_integrals",
        raw_seam_is_not_FE_constraint_failure=True,
    )


def run(stage, design, pre, artifact, marker, manifest, load_index):
    from src.solvers.feinn_phase_training import configure
    from src.solvers.feinn_torch import CompleteMomentMap
    from src.solvers.feinn_cached_derivatives import CachedMomentJacobian, model_key
    from src.solvers.feinn_parameter_jvp import MomentJacobian
    from src.solvers.feinn_validation import parameters, assign, load_moments

    configure()
    qualification = load_index("v12_saved_field_attribution")["result"]
    if not qualification.get("C_admitted"):
        raise ValueError("SAVED_FIELD_IDENTITIES_REQUIRED_FOR_LOCAL_DIAGNOSTIC")
    native = load_index("e1_fe")
    packet = load_native(checked_entry(native["files"]["native"]))
    reference, identity = reference_label(native, load_index("e3_reference"), packet)
    fields = frozen_fields(load_index("v12_saved_state_freeze"))
    mapping = CompleteMomentMap(
        load_moments(checked_entry(load_index("v8_phase_checks")["files"]["moments"]))
    )
    G = sparse.load_npz(checked_entry(native["files"]["gram"]))
    factor = None
    cache = None
    rows = {}
    arrays = {}
    totals = dict(JVP=0, VJP=0, forward_witnesses=0, FD_forward=0)
    result = dict(
        status="LOCAL_REACHABILITY_PARTIAL",
        states=rows,
        source_sha=manifest["source_sha"],
        reference=identity,
        reference_used_for_training=False,
        reference_used_for_diagnostic=True,
        data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        no_parameter_updates=True,
        optimizer_steps=0,
        weights_exported=False,
        official_candidate_results=False,
        production_initialization_allowed=False,
        Maxwell_factor_created=False,
    )
    try:
        factor = SparseRiesz(G, design, marker)
        ops = DiagnosticActions(packet, G, factor, pre["C1"], manifest)
        qf = ops.solve(packet.f)
        dG = energy(packet.f, qf)
        Gref = ops.gm(reference)
        dref = energy(reference, Gref)
        result.update(d_G=dG, d_ref=dref)
        for name in pre["C1"]["states"]:
            ops.guard()
            entry = pre["states"][name]
            model, saved = model_state(
                design,
                {**entry["durable_final"], "phase": True, "reference_exposed": False},
            )
            theta = parameters(model)
            key = model_key(model)
            cache = CachedMomentJacobian(mapping)
            old = MomentJacobian(mapping)
            started = perf_counter()
            cache.ensure(model)
            c = cache.forward(model)
            forward_seconds = perf_counter() - started
            defect = operation_relative(
                np.linalg.norm(c - fields[name]),
                np.linalg.norm(c) + np.linalg.norm(fields[name]),
            )
            if defect > 1e-10:
                raise ValueError("FIXED_LOCAL_STATE_FORWARD_MISMATCH")
            e = c - reference
            Ge = ops.gm(e)
            r = ops.A(c) - packet.f
            qr = ops.solve(r)
            gP = cache.vjp(model, ops.A(qr, adjoint=True) / dG)
            gF = cache.vjp(model, Ge / dref)
            P, desc = grouped_directions(
                parameter_groups(model), dict(PDE=gP, reference_G=gF)
            )
            if P.shape[1] > 16:
                raise ValueError("LOCAL_DIRECTION_CAP")
            X = []
            GX = []
            Y = []
            WY = []
            for j in range(P.shape[1]):
                ops.guard()
                x = cache.jvp(model, P[:, j])
                a = ops.A(x)
                X.append(x)
                GX.append(ops.gm(x))
                Y.append(a)
                WY.append(ops.solve(a))
                marker(
                    "local_group_direction",
                    dict(state=name, column=j, kind=desc[j]["kind"]),
                )
            X, GX, Y, WY = [np.column_stack(z) for z in (X, GX, Y, WY)]
            state = dict(
                parameter_norm=float(np.linalg.norm(theta)),
                parameter_sha256=array_hash(theta),
                complete_c_sha256=array_hash(c),
                forward_identity=defect,
                independent_forward_and_cache_build_seconds=forward_seconds,
                directions=desc,
                projections={},
                witnesses=[],
                periodic_parameterization=seam_and_owner(
                    model, mapping, cache, packet, c
                ),
            )
            arrays.update(
                {
                    name + "_" + k: v
                    for k, v in dict(
                        theta=theta,
                        c=c,
                        e=e,
                        Ge=Ge,
                        r=r,
                        qr=qr,
                        P=P,
                        X=X,
                        GX=GX,
                        Y=Y,
                        WY=WY,
                        gP=gP,
                        gF=gF,
                    ).items()
                }
            )
            for kind, cols, wcols, target, wtarget in [
                ("field", X, GX, -e, -Ge),
                ("residual", Y, WY, -r, -qr),
            ]:
                alpha, _, record = project_real(
                    cols, wcols, target, wtarget, rcond=pre["C1"]["main_rcond"]
                )
                _, _, sensitivity = project_real(
                    cols, wcols, target, wtarget, rcond=pre["C1"]["sensitivity_rcond"]
                )
                step = P @ alpha
                dx, dgx, dy, dwy = X @ alpha, GX @ alpha, Y @ alpha, WY @ alpha
                record.update(
                    parameter_step_norm=float(np.linalg.norm(step)),
                    relative_parameter_step=float(
                        np.linalg.norm(step) / max(np.linalg.norm(theta), 1)
                    ),
                    field_cross_effect=quadratic_change(e, dx, Ge, dgx),
                    residual_cross_effect=quadratic_change(r, dy, qr, dwy),
                    native_after_linear=float(np.linalg.norm(r + dy) / packet.bnorm),
                    E_G_after_linear=float(np.sqrt(energy(e + dx, Ge + dgx) / dref)),
                    dual_loss_after_linear=energy(r + dy, qr + dwy) / (2 * dG),
                    sensitivity_1e_12=sensitivity,
                )
                if (
                    not record["nonincrease"]
                    or max(
                        record["G_orthogonality"], record["normalized_reconstruction"]
                    )
                    > 1e-8
                ):
                    raise ValueError("LOCAL_PROJECTION_STABILITY_FAILED")
                state["projections"][kind] = record
                arrays[name + "_" + kind + "_alpha"] = alpha
                arrays[name + "_" + kind + "_step"] = step
                for cap in pre["C1"]["parameter_step_caps"]:
                    ops.guard()
                    scale = min(
                        1.0,
                        cap
                        * max(np.linalg.norm(theta), 1)
                        / max(np.linalg.norm(step), np.finfo(float).tiny),
                    )
                    try:
                        assign(model, theta + scale * step)
                        actual = mapping.forward(model)
                    finally:
                        assign(model, theta)
                    totals["forward_witnesses"] += 1
                    ea = actual - reference
                    ga = ops.gm(ea)
                    ra = ops.A(actual) - packet.f
                    qa = ops.solve(ra)
                    nonlinear = actual - c - scale * dx
                    witness = dict(
                        projection=kind,
                        cap=cap,
                        scale=scale,
                        parameter_step_norm=scale * np.linalg.norm(step),
                        nonlinear_absolute=float(np.linalg.norm(nonlinear)),
                        nonlinear_relative_to_predicted_change=float(
                            np.linalg.norm(nonlinear)
                            / max(np.linalg.norm(scale * dx), np.finfo(float).tiny)
                        ),
                        native_relative=float(np.linalg.norm(ra) / packet.bnorm),
                        E_G=float(np.sqrt(energy(ea, ga) / dref)),
                        dual_loss=energy(ra, qa) / (2 * dG),
                        parameter_restored=bool(
                            np.array_equal(parameters(model), theta)
                        ),
                    )
                    state["witnesses"].append(witness)
                    arrays[f"{name}_{kind}_{cap}_actual"] = actual
                    arrays[f"{name}_{kind}_{cap}_Ge"] = ga
                    arrays[f"{name}_{kind}_{cap}_r"] = ra
                    arrays[f"{name}_{kind}_{cap}_qr"] = qa
            # Exactly one new nonzero direction per prescribed state (two total).
            rng = np.random.default_rng(4211201 + len(rows))
            v = rng.normal(size=len(theta))
            v /= np.linalg.norm(v)
            z = (
                rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
            ).astype(np.complex128)
            jv = cache.jvp(model, v)
            independent = old.jvp(model, v)
            adj = cache.vjp(model, z)
            ad = old.vjp(model, z)
            dotdef = operation_relative(
                abs(np.vdot(jv, z).real - np.dot(v, adj)),
                np.linalg.norm(jv) * np.linalg.norm(z)
                + np.linalg.norm(v) * np.linalg.norm(adj),
            )
            checks = dict(
                JVP=operation_relative(
                    np.linalg.norm(jv - independent),
                    np.linalg.norm(jv) + np.linalg.norm(independent),
                ),
                VJP=operation_relative(
                    np.linalg.norm(adj - ad), np.linalg.norm(adj) + np.linalg.norm(ad)
                ),
                real_adjoint=dotdef,
                FD=[],
            )
            for h in pre["C1"]["FD_steps"]:
                ops.guard()
                try:
                    assign(model, theta + h * v)
                    plus = mapping.forward(model)
                    assign(model, theta - h * v)
                    minus = mapping.forward(model)
                finally:
                    assign(model, theta)
                totals["FD_forward"] += 2
                fd = (plus - minus) / (2 * h)
                checks["FD"].append(
                    dict(
                        h=h,
                        relative=float(np.linalg.norm(fd - jv) / np.linalg.norm(jv)),
                    )
                )
            if (
                max(checks["JVP"], checks["VJP"], dotdef) > 1e-9
                or max(x["relative"] for x in checks["FD"]) > 1e-5
            ):
                raise ValueError("LOCAL_NONZERO_DERIVATIVE_WITNESS_FAILED")
            state["nonzero_direction_check"] = checks
            state["parameter_buffers_unchanged"] = model_key(model) == key
            if not state["parameter_buffers_unchanged"]:
                raise ValueError("LOCAL_WITNESS_PARAMETER_RESTORE_FAILED")
            state["cache"] = cache.record()
            totals["JVP"] += cache.counts["JVP"] + old.counts["JVP"]
            totals["VJP"] += cache.counts["VJP"] + old.counts["VJP"]
            cache.invalidate()
            cache = None
            rows[name] = state
            marker(
                "local_reachability_complete",
                dict(
                    state=name,
                    field_removed=state["projections"]["field"][
                        "removed_energy_fraction"
                    ],
                    residual_removed=state["projections"]["residual"][
                        "removed_energy_fraction"
                    ],
                ),
            )
        if totals["JVP"] > 64 or totals["VJP"] > 16 or totals["forward_witnesses"] > 8:
            raise RuntimeError("LOCAL_DIAGNOSTIC_ACTION_BUDGET_EXCEEDED")
        result.update(status="FIXED_LOCAL_REACHABILITY_COMPLETE", counts=totals)
    finally:
        if cache is not None:
            cache.invalidate()
        if factor is not None:
            result.update(
                actions=ops.record() if "ops" in locals() else {},
                Gram_factor=factor.record,
            )
            factor.close()
        result["counts"] = totals
        path = Path(artifact) / "local_diagnostic_vectors.npz"
        atomic_npz(path, **arrays)
        write_json(Path(artifact) / "partial_local_diagnostic.json", result)
    return result, dict(vectors=path)
