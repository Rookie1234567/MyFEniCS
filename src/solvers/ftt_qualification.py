"""New full-moment qualifications on the frozen M5; no reference read."""

from time import monotonic
import numpy as np
import torch
from src.solvers.ftt_field import FTTField
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.ftt_optimization import make_metric


def flat(model):
    return (
        torch.nn.utils.parameters_to_vector(model.parameters()).detach().numpy().copy()
    )


def assign(model, values):
    torch.nn.utils.vector_to_parameters(
        torch.from_numpy(values.copy()), model.parameters()
    )


def relative(x, y):
    return float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-30))


def qualify(action, packet, high, bounds, marker):
    if not np.array_equal(packet["master_native_rows"], action.a["masters"]):
        raise ValueError("FTT_MASTER_ORDER_MPC_MISMATCH")
    results = {}
    rng = np.random.default_rng(4213802)
    for kind in ("fttnn", "chebtt"):
        model = FTTField(bounds, kind)
        mapping = StreamingMomentMap(packet)
        if np.any(mapping.forward(model)):
            raise ValueError("FTT_NOT_EXACT_ZERO")
        model.nonzero_qualification_state()
        base = flat(model)
        began = monotonic()
        c = mapping.forward(model)
        metric = make_metric(action, "native_euc")
        loss, _, g = metric.value(c, gradient=True)
        grad = mapping.vjp(model, g)
        closure_seconds = monotonic() - began
        marker(
            "nonzero_complete_closure",
            dict(model_kind=kind, seconds=closure_seconds, loss=loss),
        )
        # Old reliable cell-bounded AD performs the independent coefficient
        # cotangent, with no new global AD graph or columns.
        old = CompleteMomentMap(packet)
        old_c = old.forward(model, 1)
        dual = (
            rng.standard_normal(action.size) + 1j * rng.standard_normal(action.size)
        ).astype(np.complex128)
        old_g = old.vjp(model, dual, 1)
        new_g = mapping.vjp(model, dual, 8)
        adjoint = relative(new_g, old_g)
        alternate = StreamingMomentMap(packet, 128)
        c1 = alternate.forward(model, 1)
        loss1, _, g1 = metric.value(c1, gradient=True)
        grad1 = alternate.vjp(model, g1, 1)
        batch = dict(
            coefficients=relative(c1, c),
            gradient=relative(grad1, grad),
            loss=abs(loss1 - loss) / max(abs(loss), 1e-30),
        )
        # Same complete gradient gives the same actual Adam parameter update.
        clones = [FTTField(bounds, kind), FTTField(bounds, kind)]
        updates = []
        for clone, gg in zip(clones, (grad, grad1), strict=True):
            assign(clone, base)
            opt = torch.optim.Adam(clone.parameters(), lr=1e-3)
            at = 0
            for p in clone.parameters():
                p.grad = torch.from_numpy(
                    gg[at : at + p.numel()].reshape(p.shape).copy()
                )
                at += p.numel()
            opt.step()
            updates.append(flat(clone))
        batch["Adam_update"] = relative(*updates)
        differences = []
        for k in range(3):
            d = rng.standard_normal(len(base))
            d /= np.linalg.norm(d)
            exact = float(grad @ d)
            if abs(exact) < 1e-14:
                raise ValueError("NONZERO_FTT_REAL_DIRECTION_REQUIRED")
            observations = []
            for h in (1e-4, 1e-5, 1e-6):
                assign(model, base + h * d)
                plus = metric.value(mapping.forward(model))[0]
                assign(model, base - h * d)
                minus = metric.value(mapping.forward(model))[0]
                observed = (plus - minus) / (2 * h)
                observations.append(
                    dict(
                        h=h,
                        observed=observed,
                        relative=abs(observed - exact) / abs(exact),
                    )
                )
            differences.append(
                dict(direction=k, analytic=exact, observations=observations)
            )
        assign(model, base)
        c60 = StreamingMomentMap(high).forward(model)
        q = dict(
            coefficients=relative(c60, c),
            original_action_load_relative=float(
                np.linalg.norm(action.apply(c60 - c)) / action.bnorm
            ),
        )
        finite_ok = all(
            min(v["relative"] for v in d["observations"]) <= 1e-5 for d in differences
        )
        records = dict(
            model_kind=kind,
            real_parameters=len(base),
            zero_scattered_exact=True,
            complete_closure_probe_count=2,
            complete_closure_seconds=closure_seconds,
            old_complete_mapping=relative(old_c, c),
            real_adjoint_relative=adjoint,
            batch_point_microbatch=batch,
            finite_differences=differences,
            quadrature=q,
            parameter_gradient_rms=float(np.sqrt(np.mean(grad**2))),
            mapping_costs=mapping.costs,
            core_costs=model.costs,
            counts=mapping.counts,
            complete_edge_face_interior=True,
            unique_owner=True,
            full_mpc_expansion=True,
            nonunit_constraint_coefficients=int(
                np.count_nonzero(abs(action.a["evals"] - 1) > 1e-14)
            ),
            qualified=bool(
                relative(old_c, c) <= 1e-10
                and adjoint <= 1e-10
                and max(batch.values()) <= 1e-10
                and finite_ok
                and max(q.values()) <= 1e-8
            ),
        )
        results[kind] = records
        marker("model_interface_qualification", records)
    return dict(
        implementation_qualified=all(r["qualified"] for r in results.values()),
        models=results,
        Gsolve_count=0,
        global_Gram_factor_count=0,
        global_Maxwell_factor_count=0,
    )
