"""Independent old-point qualifications and complete-cost admission, no labels."""

from copy import deepcopy
from pathlib import Path
from time import perf_counter
import numpy as np
import torch
from src.solvers.ftt_field import FTTField
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_factored_moments import FactoredMomentMap
from src.solvers.ftt_optimization import make_metric
from src.solvers.ftt_qualification import flat, assign
from src.solvers.optimization_checkpoint import (
    load_checkpoint,
    capture,
    restore,
    atomic_write,
    digest,
    optimizer_step,
)
from src.io.ftt_structure_campaign import parent
from src.io.neural_wave_campaign import ROOT


def pairing(x, y):
    numerator = float(np.linalg.norm(np.asarray(x) - np.asarray(y)))
    denominator = float(np.linalg.norm(y))
    if denominator == 0:
        return dict(
            numerator=numerator, denominator=0.0, relative=None, passed=numerator == 0
        )
    return dict(
        numerator=numerator,
        denominator=denominator,
        relative=numerator / denominator,
        passed=numerator / denominator <= 1e-10,
    )


def load_parent_model(design, kind, fit=False):
    from src.postprocessing.ftt_verification import validate_checkpoint_identity

    entry, candidate = parent(design, kind, fit)
    model = FTTField(design["model"]["geometry"]["bounds_nm"], kind, design["seed"])
    state = load_checkpoint(
        ROOT / entry["checkpoint"]["path"], entry["checkpoint"]["sha256"]
    )
    validate_checkpoint_identity(state, candidate, model, fit)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    restore(model, optimizer, state)
    if any(
        int(x["step"]) != entry["counts"]["Adam_updates"]
        for x in optimizer.state.values()
    ):
        raise ValueError("FTT_PARENT_ADAM_STATE_NOT_MATCHED")
    return model, optimizer, state, candidate


def qualify(action, packet, high, design, artifact, marker):
    results = {}
    rng = np.random.default_rng(4213901)
    for kind in ("fttnn", "chebtt"):
        model, optimizer, state, candidate = load_parent_model(design, kind)
        old = StreamingMomentMap(packet)
        new = FactoredMomentMap(packet)
        base = flat(model)
        metric = make_metric(action, "native_euc")
        c = new.forward(model)
        cold = old.forward(model)
        loss, _, dual = metric.value(c, gradient=True)
        gold = old.vjp(model, dual)
        gnew = new.vjp(model, dual)
        witnesses = dict(
            c=pairing(c, cold),
            parent_c=pairing(c, state["c"]),
            residual=pairing(action.apply(c) - action.f, state["r"]),
            gradient=pairing(gnew, gold),
            original_action=pairing(action.apply(c), action.apply(cold)),
        )
        # Same nonzero state, genuine coefficient cotangent; new batch variants.
        alt = FactoredMomentMap(packet, 128)
        cb = alt.forward(model, 1)
        gb = alt.vjp(model, dual, 1)
        witnesses["batch_microbatch_c"] = pairing(cb, c)
        witnesses["batch_microbatch_gradient"] = pairing(gb, gnew)
        differences = []
        for k in range(3):
            direction = rng.normal(size=len(base))
            direction /= np.linalg.norm(direction)
            exact = float(gnew @ direction)
            if abs(exact) < 1e-15:
                raise ValueError("NONZERO_REAL_FTT_DIRECTION_REQUIRED")
            rows = []
            for h in (1e-4, 1e-5, 1e-6):
                assign(model, base + h * direction)
                plus = metric.value(new.forward(model))[0]
                assign(model, base - h * direction)
                minus = metric.value(new.forward(model))[0]
                observed = (plus - minus) / (2 * h)
                rows.append(
                    dict(
                        h=h,
                        observed=observed,
                        numerator=abs(observed - exact),
                        denominator=abs(exact),
                        relative=abs(observed - exact) / abs(exact),
                    )
                )
            differences.append(dict(direction=k, analytic=exact, observations=rows))
        restore(model, optimizer, state)
        chigh = FactoredMomentMap(high).forward(model)
        q = dict(
            coefficients=pairing(chigh, c),
            load_relative=float(np.linalg.norm(action.apply(chigh - c)) / action.bnorm),
        )
        # Complete Adam update, full optimizer identity; independently computed gradients.
        updated = []
        optstates = []
        for gradient in (gold, gnew):
            restore(model, optimizer, state)
            at = 0
            for p in model.parameters():
                p.grad = torch.from_numpy(
                    gradient[at : at + p.numel()].reshape(p.shape).copy()
                )
                at += p.numel()
            optimizer.step()
            updated.append(flat(model))
            optstates.append(deepcopy(optimizer.state_dict()))
        witnesses["Adam_update"] = pairing(updated[1], updated[0])
        max_moment = 0.0
        for n, s in optstates[0]["state"].items():
            for key, value in s.items():
                if key == "step":
                    if not torch.equal(value, optstates[1]["state"][n][key]):
                        raise ValueError("ADAM_STEP_DIFFERS")
                else:
                    max_moment = max(
                        max_moment,
                        pairing(optstates[1]["state"][n][key].numpy(), value.numpy())[
                            "relative"
                        ]
                        or 0.0,
                    )
        # A fresh original-config LBFGS complete outer step on a clone, and
        # old-point c/r/true objective at its returned committed state.
        restore(model, optimizer, state)
        lb = torch.optim.LBFGS(
            model.parameters(),
            lr=1,
            history_size=20,
            line_search_fn="strong_wolfe",
            max_iter=20,
            max_eval=25,
            tolerance_grad=1e-7,
            tolerance_change=1e-9,
        )
        lb_calls = 0

        def closure():
            nonlocal lb_calls
            cc = new.forward(model)
            v, _, dd = metric.value(cc, gradient=True)
            new.vjp(model, dd)
            lb_calls += 1
            return torch.tensor(v, dtype=torch.float64)

        optimizer_step(model, lb, closure, lambda update: update)
        clb = new.forward(model)
        olb = old.forward(model)
        witnesses["LBFGS_returned_c"] = pairing(clb, olb)
        witnesses["LBFGS_true_residual"] = pairing(
            action.apply(clb) - action.f, action.apply(olb) - action.f
        )
        lb_objectives = pairing(
            np.array([metric.value(clb)[0]]), np.array([metric.value(olb)[0]])
        )
        witnesses["LBFGS_true_objective"] = lb_objectives
        restore(model, optimizer, state)
        finalcache = new.forward(model)
        witnesses["restored_cache"] = pairing(finalcache, c)
        passed = (
            all(v["passed"] for v in witnesses.values())
            and max_moment <= 1e-10
            and all(
                min(v["relative"] for v in row["observations"]) <= 1e-5
                for row in differences
            )
            and q["load_relative"] <= 1e-8
            and (
                q["coefficients"]["relative"] is not None
                and q["coefficients"]["relative"] <= 1e-8
            )
        )
        record = dict(
            qualified=bool(passed),
            witnesses=witnesses,
            nonzero_FD=differences,
            Adam_moment_pairing_max=max_moment,
            original_configuration_LBFGS_outer_calls=lb_calls,
            quadrature=q,
            plan_interpolation=new.interpolation_errors,
            axis_node_counts=[len(a) for a in new.nodes],
            tensor_entities=len(new.plans),
            exact_fallback_entities=sum(p["raw"] for p in new.plans),
            aligned_cells=sum(g["aligned"] for g in new.geometry_records),
            max_affine_roundoff=max(
                g["affine_roundoff_relative"] for g in new.geometry_records
            ),
            max_coordinate_roundoff_nm=max(
                g.get("max_node_roundoff_nm", 0) for g in new.geometry_records
            ),
            cache_static_bytes=new.static_bytes,
            cache_dynamic_bytes=new.dynamic_bytes,
            model_parameters=len(base),
            parent_checkpoint_sha256=candidate["checkpoint"]["sha256"],
            costs=new.costs,
            reference_loaded=False,
        )
        results[kind] = record
        marker("factored_mapping_qualification", dict(model_kind=kind, **record))
    return dict(
        implementation_qualified=all(v["qualified"] for v in results.values()),
        models=results,
        global_Gram_factor=0,
        Gsolve=0,
        global_Maxwell_factor=0,
    )


def benchmark(
    action,
    packet,
    design,
    artifact,
    marker,
    *,
    previous_record=None,
    measurement_tag="",
):
    results = {}
    metric = make_metric(action, "native_euc")
    artifact = Path(artifact)
    for kind in ("fttnn", "chebtt"):
        model, opt, state, candidate = load_parent_model(design, kind)
        t = perf_counter()
        new = FactoredMomentMap(packet)
        setup = perf_counter() - t
        old = StreamingMomentMap(packet)
        rows = []
        updated = {}
        for repetition in range(3):
            for name, mapping in (("old_point", old), ("factored", new)):
                restore(model, opt, state)
                if name == "old_point" and previous_record is not None:
                    recorded = previous_record["models"][kind]
                    if (
                        recorded["parent_checkpoint_sha256"]
                        != candidate["checkpoint"]["sha256"]
                    ):
                        raise ValueError("REUSED_MEASUREMENT_PARENT_MISMATCH")
                    rows_found = [
                        r
                        for r in recorded["measurements"]
                        if r["method"] == name and r["repetition"] == repetition
                    ]
                    if len(rows_found) != 1:
                        raise ValueError("REUSED_MEASUREMENT_COVERAGE_MISMATCH")
                    row = deepcopy(rows_found[0])
                    file = artifact / f"{kind}_old_point_measure_{repetition}.pt"
                    saved = load_checkpoint(file, row["saved_sha256"])
                    if (
                        not saved["metadata"].get("measurement_only")
                        or saved["metadata"]["parent_checkpoint_sha256"]
                        != candidate["checkpoint"]["sha256"]
                    ):
                        raise ValueError("REUSED_MEASUREMENT_IDENTITY_MISMATCH")
                    theta = np.concatenate(
                        [
                            saved["model"][n].numpy().ravel()
                            for n, _ in model.named_parameters()
                        ]
                    )
                    gradient = np.concatenate(
                        [g.numpy().ravel() for g in saved["gradients"]]
                    )
                    updated[name] = (theta, saved["c"], saved["r"], gradient)
                    row.update(
                        reused=True,
                        new_seconds=0.0,
                        original_source_sha=previous_record["source_sha"],
                    )
                    rows.append(row)
                    marker("complete_old_measurement_reused", dict(kind=kind, **row))
                    continue
                start = perf_counter()
                c = mapping.forward(model)
                loss, r, d = metric.value(c, gradient=True)
                g = mapping.vjp(model, d)
                gradient_finish = perf_counter()
                opt.step()
                c1 = mapping.forward(model)
                r1 = action.apply(c1) - action.f
                updated[name] = (flat(model), c1, r1, g, loss)
                save_start = perf_counter()
                f = artifact / f"{kind}_{name}_measure_{repetition}{measurement_tag}.pt"
                snap = capture(
                    model,
                    opt,
                    dict(
                        measurement_only=True,
                        parent_checkpoint_sha256=candidate["checkpoint"]["sha256"],
                    ),
                )
                snap.update(c=c1, r=r1)
                atomic_write(f, lambda stream: torch.save(snap, stream))
                end = perf_counter()
                record = dict(
                    method=name,
                    repetition=repetition,
                    complete_gradient_seconds=gradient_finish - start,
                    update_and_post_update_c_r_seconds=save_start - gradient_finish,
                    snapshot_and_atomic_save_seconds=end - save_start,
                    complete_work_seconds=end - start,
                    saved_sha256=digest(f),
                    bytes=f.stat().st_size,
                )
                rows.append(record)
                marker("complete_work_measurement", dict(kind=kind, **record))
            for x, y in zip(updated["factored"][:4], updated["old_point"][:4]):
                if not pairing(x, y)["passed"]:
                    raise ValueError("COMPLETE_MEASURED_WORK_MISMATCH")
        # Consecutive work, including changing parameters and durable save.
        restore(model, opt, state)
        consecutive = []
        for k in range(3):
            start = perf_counter()
            cc = new.forward(model)
            _, _, d = metric.value(cc, gradient=True)
            new.vjp(model, d)
            opt.step()
            cc = new.forward(model)
            rr = action.apply(cc) - action.f
            s = capture(model, opt, dict(measurement_only=True))
            s.update(c=cc, r=rr)
            atomic_write(
                artifact / f"{kind}_consecutive_{k}{measurement_tag}.pt",
                lambda f: torch.save(s, f),
            )
            consecutive.append(perf_counter() - start)
        maximum = max(
            [r["complete_work_seconds"] for r in rows if r["method"] == "factored"]
            + consecutive
        )
        inherited = state["metadata"]["counts"]["attempted_calls"]
        estimate = setup + 1.5 * (1000 - inherited) * maximum + 600
        # Fit uses the SAME fully measured work maximum (conservative: native A/AH).
        fit_inherited = design["parents"][kind + "_fit"]["counts"]["attempted_calls"]
        fit_estimate = setup + 1.5 * (500 - fit_inherited) * maximum + 300
        record = dict(
            measurements=rows,
            new_consecutive_work_seconds=consecutive,
            setup_seconds=setup,
            max_new_complete_work_seconds=maximum,
            native_conservative_estimate_seconds=estimate,
            native_execution_cost_gate=estimate <= 7200,
            fit_conservative_estimate_seconds=fit_estimate,
            fit_execution_cost_gate=fit_estimate <= 1800,
            measured_old_mean_seconds=float(
                np.mean(
                    [
                        r["complete_work_seconds"]
                        for r in rows
                        if r["method"] == "old_point"
                    ]
                )
            ),
            measured_new_mean_seconds=float(
                np.mean(
                    [
                        r["complete_work_seconds"]
                        for r in rows
                        if r["method"] == "factored"
                    ]
                )
            ),
            cache_static_bytes=new.static_bytes,
            cache_dynamic_bytes=new.dynamic_bytes,
            breakdown=new.costs,
            inherited_calls=inherited,
            parent_checkpoint_sha256=candidate["checkpoint"]["sha256"],
            old_baseline_reused=previous_record is not None,
            shared_one_dimensional_functionals={
                str(k): [len(w) for w in value[0]]
                for k, value in new.shared_definitions.items()
            },
        )
        results[kind] = record
        marker("complete_execution_cost_gate", dict(model_kind=kind, **record))
    return dict(models=results, reference_loaded=False)
