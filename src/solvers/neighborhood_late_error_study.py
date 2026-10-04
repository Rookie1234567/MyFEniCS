"""V44 parameterized stage implementation; isolated route actors and frozen labels."""

import itertools
import json
import os
from pathlib import Path
from time import monotonic, perf_counter

import numpy as np

from benchmarks.check_boundary_witness import read_arrays
from src.runners.task042_shared import write_json
from src.solvers.isolated_ml_sparse import csr_matrix
from src.solvers.native_recovery_packets import sha
from src.solvers.neighborhood_late_error import (
    choose_checkpoint,
    frozen_reader,
    label_identity,
    late_loss,
)
from src.solvers.neighborhood_late_error_scope import (
    ActionBudget,
    implementation_hashes,
    parent,
    plan_record,
    stage,
    window,
)
from src.solvers.neighborhood_residual_core import (
    OriginalCSR,
    fixed_cleanup,
    manufactured,
    ratio,
)
from src.solvers.neighborhood_residual_study import assign_model, save, save_model

ROUTES = {"NR": "NN-R", "NE": "NN-E", "RL": "RL-E", "CL": "CL-E", "R0": "R0"}


def graph_packet():
    pointer = parent("qualified_graph")
    if sha(pointer["path"]) != pointer["sha256"]:
        raise ValueError("old qualified graph result identity")
    row = json.loads(Path(pointer["path"]).read_text())
    if not row["passed"]:
        raise ValueError("original independent graph unqualified")
    a = read_arrays(row["graph"])
    bridge = csr_matrix(
        (a.pop("bridge_data"), a.pop("bridge_indices"), a.pop("bridge_indptr")),
        shape=tuple(a["shape"]),
    )
    return bridge, a, row


def load_action(budget):
    began = perf_counter()
    action = OriginalCSR(read_arrays(parent("csr")["arrays"]), budget)
    action.load_seconds = perf_counter() - began
    return action


def model_for(code, action, *, diagnostic=False):
    from src.solvers.neighborhood_residual_models import NeighborhoodCorrector

    bridge, graph, _ = graph_packet()
    return NeighborhoodCorrector(
        bridge,
        graph,
        action.scale,
        seed=plan_record()["seed"],
        linear=code == "CL",
        real_linear=code == "RL",
        zero_decoder=not diagnostic,
    )


def setup(folder, budget):
    bridge, _graph, old = graph_packet()
    action = load_action(budget)
    rng = np.random.default_rng(424731)
    x = bridge @ (
        rng.normal(size=bridge.shape[1]) + 1j * rng.normal(size=bridge.shape[1])
    )
    y = bridge @ (
        rng.normal(size=bridge.shape[1]) + 1j * rng.normal(size=bridge.shape[1])
    )
    ax, ahy = action.apply(x), action.apply(y, adjoint=True)
    denominator = float(
        np.linalg.norm(ax) * np.linalg.norm(y) + np.linalg.norm(x) * np.linalg.norm(ahy)
    )
    dual = float(abs(np.vdot(y, ax) - np.vdot(ahy, x)))
    checks = [
        {
            "kind": "actual_original_A_AH",
            "numerator": dual,
            "denominator": denominator,
            "passed": dual <= 1e-10 * denominator,
        },
        dict(
            kind="full_canonical_native_roundtrip",
            **ratio(bridge @ (bridge.conjugate().T @ x), x),
        ),
    ]
    # Forecast conservative full quota and four model non-action costs from V43,
    # including measured CSR reloads, and a 25% verification margin.
    old_gate = json.loads(
        Path(
            json.loads(
                (Path(old["graph"]["path"]).parents[1] / "GRADIENT.json").read_text()
            )["path"]
        ).read_text()
    )
    seconds = max(r["CSR_seconds"] for r in old["action_measurement"])
    net = old_gate["budget_forecast"]["measured_network_seconds_inside_step"]
    forecast = 12000 * seconds + 512 * net + 14 * action.load_seconds
    available = window.worker_learning_remaining()
    forecast_row = {
        "kind": "predicted",
        "seconds": forecast,
        "available_seconds": available,
        "old_action_seconds": seconds,
        "old_non_action_gradient_seconds": net,
        "measured_load_seconds": action.load_seconds,
        "verification_reserve_fraction": 0.25,
        "passed": forecast <= 0.75 * available,
    }
    return {
        "status": "V44_GRAPH_ACTION_FORECAST_READY",
        "passed": all(r["passed"] for r in checks) and forecast_row["passed"],
        "checks": checks,
        "budget_forecast": forecast_row,
        "qualified_graph_parent": plan_record()["parents"]["qualified_graph"],
        "canonical_rows": bridge.shape[1],
        "native_rows": bridge.shape[0],
        "capacity": {
            "predicted_peak_bytes": 5 * 2**30,
            "CSR_and_conjugate_AH_present": True,
            "model_count_resident": 1,
            "new_mesh_JIT_LU_QR": 0,
        },
        "B_chain_reused_unchanged": True,
    }


def data(folder, budget):
    gate, _ = stage("SETUP")
    if not gate["passed"]:
        raise ValueError("forecast/action gate")
    bridge, graph, _ = graph_packet()
    action = load_action(budget)
    prefixes, labels, sealed, inventory, checks = {}, {}, {}, [], []
    for split, item in plan_record()["split"].items():
        arrays = {key: [] for key in ("rhs", "prefix", "residual")}
        errors, ds = [], []
        for i, seed in enumerate(item["seeds"]):
            family = item["families"][int(i >= len(item["seeds"]) // 2)]
            e = bridge @ manufactured(graph, family, seed)
            r = action.apply(e)
            norm = float(np.linalg.norm(r))
            e, r = e / norm, r / norm
            z64, result = fixed_cleanup(
                action, r, np.zeros_like(r), max_steps=64, tol=1e-10
            )
            d = e - z64
            residual, identity = label_identity(action, r, z64, d)
            checks.append(dict(split=split, sample=i, **identity))
            for key, value in (("rhs", r), ("prefix", z64), ("residual", residual)):
                arrays[key].append(value)
            errors.append(e)
            ds.append(d)
            row = {
                "split": split,
                "sample": i,
                "seed": seed,
                "family": family,
                "normalization": norm,
                "solver": result,
                "original_rhs_sha256": __import__("hashlib")
                .sha256(r.tobytes())
                .hexdigest(),
                "prefix_bypass": result["rho"] <= 1e-10,
            }
            inventory.append(row)
            print(
                json.dumps(
                    {
                        "event": "prefix",
                        "split": split,
                        "sample": i,
                        "steps": result["steps"],
                        "rho": result["rho"],
                    }
                ),
                flush=True,
            )
        prefixes[split] = save(
            folder, "prefix_" + split, **{k: np.asarray(v) for k, v in arrays.items()}
        )
        if split == "heldout":
            sealed[split] = save(folder, "sealed_" + split, error=np.asarray(errors))
        else:
            labels[split] = save(
                folder,
                "authorized_labels_" + split,
                error=np.asarray(errors),
                label=np.asarray(ds),
            )
    return {
        "status": "V44_POST64_DATA_FROZEN",
        "passed": all(c["passed"] for c in checks),
        "prefix": prefixes,
        "labels": labels,
        "sealed": sealed,
        "inventory": inventory,
        "identity_checks": checks,
        "teacher_solve": False,
        "labels_permission": "V44 explicit train/validation only; heldout opened only by post-freeze CHECK",
        "common_prefix_actual_once": True,
        "independent_route_cost_must_include_prefix": True,
    }


def training_values(split, *, labels=True):
    ds, _ = stage("DATA")
    if not ds["passed"]:
        raise ValueError("s/Ad identity unqualified")
    return frozen_reader(ds, split, read_arrays, labels=labels)


def gradient(folder, budget):
    import torch
    from torch.func import functional_call

    from src.solvers.neighborhood_residual_models import parameters_hash

    action = load_action(budget)
    _, graph, _ = graph_packet()
    values = training_values("train")
    s, d = (torch.from_numpy(values[k][:2].copy()) for k in ("residual", "label"))
    model = model_for("NE", action, diagnostic=True)
    loss, delta, qr, qe = late_loss(
        model, s, d, action, mixed=True, independent=graph["independent"]
    )
    grads = torch.autograd.grad(loss, tuple(model.parameters()))
    save_model(
        folder, "nonzero_gradient_witness", model, None, {"diagnostic_only": True}
    )
    names = [n for n, _ in model.named_parameters()]
    params = tuple(p.detach().clone().requires_grad_() for p in model.parameters())

    def output(*weights):
        return functional_call(model, dict(zip(names, weights, strict=True)), (s,))

    v = delta.detach().numpy()
    residual = s.numpy() - action.apply(v.T).T
    q = -action.apply(
        (residual / (np.linalg.norm(s.numpy(), axis=1) ** 2)[:, None]).T, adjoint=True
    ).T
    q += (v - d.numpy()) / (
        np.linalg.norm(d.numpy()[:, graph["independent"]], axis=1) ** 2
    )[:, None]
    q /= 2
    checks, fdrows = [], []
    single, gg = [], []
    for si, di in zip(s, d, strict=True):
        ll, _, _, _ = late_loss(
            model,
            si[None, :],
            di[None, :],
            action,
            mixed=True,
            independent=graph["independent"],
        )
        single.append(float(ll.detach()))
        gg.append(torch.autograd.grad(ll, tuple(model.parameters())))
    gn = float(torch.sqrt(sum(torch.sum(abs(g) ** 2) for g in grads)))
    err = float(
        torch.sqrt(
            sum(
                torch.sum(abs(g - sum(row[i] for row in gg) / 2) ** 2)
                for i, g in enumerate(grads)
            )
        )
    )
    checks.append(
        {
            "kind": "batch1_batch2_mixed_loss_gradient",
            "gradient_numerator": err,
            "gradient_denominator": gn,
            "loss_difference": abs(float(loss.detach()) - np.mean(single)),
            "passed": err <= 1e-10 * gn
            and abs(float(loss.detach()) - np.mean(single))
            <= 1e-10 * abs(float(loss.detach())),
        }
    )
    for i, seed in enumerate(plan_record()["FD_seeds"]):
        gen = torch.Generator().manual_seed(seed)
        dirs = [torch.randn(p.shape, generator=gen, dtype=p.dtype) for p in params]
        if i == 2:
            dirs = [
                v if n.startswith("message") else torch.zeros_like(v)
                for n, v in zip(names, dirs, strict=True)
            ]
        den = torch.sqrt(sum(torch.sum(v**2) for v in dirs))
        dirs = tuple(v / den for v in dirs)
        _, jvp = torch.autograd.functional.jvp(output, params, dirs, strict=True)
        jv = jvp.detach().numpy()
        left = float(np.vdot(jv, q).real)
        right = float(sum(torch.sum(g * v) for g, v in zip(grads, dirs, strict=True)))
        op = float(np.linalg.norm(jv) * np.linalg.norm(q))
        checks.append(
            {
                "kind": "mixed_original_VJP_" + str(i),
                "left": left,
                "right": right,
                "operation_denominator": op,
                "result_scale": max(abs(left), abs(right)),
                "relative": abs(left - right) / op if op else None,
                "passed": op > 0
                and max(abs(left), abs(right)) > 0
                and abs(left - right) <= 1e-10 * op,
            }
        )
        passed = []
        for h in plan_record()["FD_steps"]:
            plus = output(*(p + h * v for p, v in zip(params, dirs, strict=True)))
            minus = output(*(p - h * v for p, v in zip(params, dirs, strict=True)))
            fd = ((plus - minus) / (2 * h)).detach().numpy()
            check = ratio(fd, jv, tol=1e-5)
            passed.append(check["passed"])
            fdrows.append(
                dict(
                    direction=i,
                    step=h,
                    **check,
                    arrays=save(
                        folder, f"FD_{i}_{h:.0e}", finite_difference=fd, jvp=jv
                    ),
                )
            )
        checks.append(
            {
                "kind": "adjacent_vector_FD_" + str(i),
                "passed": any(a and b for a, b in itertools.pairwise(passed)),
            }
        )
    with torch.no_grad():
        for code in ("NR", "NE", "RL", "CL"):
            zero = model_for(code, action)
            out = zero(s)
            checks.append(
                {
                    "kind": code + "_zero_decoder",
                    "passed": bool(torch.count_nonzero(out) == 0),
                }
            )
            out = zero(torch.zeros_like(s))
            checks.append(
                {
                    "kind": code + "_exact_zero",
                    "passed": bool(torch.count_nonzero(out) == 0),
                }
            )
        for code in ("RL", "CL"):
            linear = model_for(code, action, diagnostic=True)
            a = 0.7 if code == "RL" else 0.7 - 0.3j
            b = -0.2 if code == "RL" else -0.2 + 0.6j
            checks.append(
                dict(
                    kind=code + "_linearity",
                    **ratio(
                        linear(a * s[:1] + b * s[1:]).numpy(),
                        (a * linear(s[:1]) + b * linear(s[1:])).numpy(),
                    ),
                )
            )
    return {
        "status": "V44_MIXED_FULL_GRADIENT_READY",
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "FD": fdrows,
        "loss": float(loss.detach()),
        "qr": qr.detach().tolist(),
        "qe": qe.detach().tolist(),
        "witness_hash": parameters_hash(model),
        "heldout_reads": 0,
    }


def validation(model, values, action, graph, mixed):
    import torch

    with torch.no_grad():
        _, _, qr, qe = late_loss(
            model,
            torch.from_numpy(values["residual"].copy()),
            torch.from_numpy(values["label"].copy()),
            action,
            mixed=mixed,
            independent=graph["independent"],
        )
    r, e = np.sqrt(qr.numpy()), np.sqrt(qe.numpy())
    return {
        "qr": r.tolist(),
        "qe": e.tolist(),
        "median_qr": float(np.median(r)),
        "median_qe": float(np.median(e)),
        "max_qe": float(max(e)),
    }


def train(folder, budget, code):
    import torch

    from src.solvers.neighborhood_residual_models import group_changes, parameters_hash

    gate, _ = stage("GRADIENT")
    if not gate["passed"]:
        raise ValueError("mixed full gradient gate")
    action = load_action(budget)
    _, graph, _ = graph_packet()
    model = model_for(code, action)
    initial = {n: p.detach().clone() for n, p in model.named_parameters()}
    init_hash = parameters_hash(model)
    tv, vv = (
        training_values("train", labels=code != "NR"),
        training_values("validation"),
    )
    s = torch.from_numpy(tv["residual"].copy())
    d = torch.from_numpy(tv["label"].copy()) if code != "NR" else None
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    checkpoints = [
        dict(
            update=0,
            **validation(model, vv, action, graph, code != "NR"),
            receipt=save_model(folder, "checkpoint_0", model, opt, {"update": 0}),
        )
    ]
    for step in range(1, 129):
        began = perf_counter()
        before = parameters_hash(model)
        committed = save_model(
            folder, "last_committed", model, opt, {"update": step - 1}
        )
        ids = [(2 * (step - 1)) % 16, (2 * (step - 1) + 1) % 16]
        opt.zero_grad(set_to_none=True)
        loss, _, qr, qe = late_loss(
            model,
            s[ids],
            d[ids] if d is not None else None,
            action,
            mixed=code != "NR",
            independent=graph["independent"],
        )
        loss.backward()
        gn = float(
            torch.sqrt(sum(torch.sum(abs(p.grad) ** 2) for p in model.parameters()))
        )
        if not np.isfinite(float(loss.detach())) or not np.isfinite(gn):
            raise ArithmeticError("nonfinite mixed original loss/gradient")
        opt.step()
        if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
            state = assign_model(model, committed)
            opt.load_state_dict(state["optimizer"])
            raise ArithmeticError(
                "nonfinite Adam step; consistent parameters/optimizer restored"
            )
        row = {
            "update": step,
            "batch_samples": ids,
            "loss_before_update": float(loss.detach()),
            "qr_before": qr.detach().tolist(),
            "qe_before": qe.detach().tolist() if d is not None else None,
            "gradient_norm": gn,
            "parameter_before_hash": before,
            "parameter_after_hash": parameters_hash(model),
            "seconds": perf_counter() - began,
            "calls": dict(action.calls),
            "group_changes": group_changes(model, initial),
            "authorized_labels_split": "train/validation V44 only",
        }
        with (folder / "training_history.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
        if step in (16, 32, 64, 128):
            cp = dict(
                update=step,
                **validation(model, vv, action, graph, code != "NR"),
                receipt=save_model(
                    folder, "checkpoint_" + str(step), model, opt, {"update": step}
                ),
            )
            checkpoints.append(cp)
            print(
                json.dumps(
                    dict(
                        route=ROUTES[code],
                        **{k: v for k, v in cp.items() if k != "receipt"},
                    )
                ),
                flush=True,
            )
    selected = choose_checkpoint(checkpoints, residual_only=code == "NR")
    result = {
        "status": "WEIGHTS_FROZEN",
        "route": ROUTES[code],
        "initial_parameter_hash": init_hash,
        "selected": selected,
        "all_checkpoints": checkpoints,
        "training_updates": 128,
        "stop_reason": "FIXED_128_UPDATES",
        "parameter_group_changes_last": group_changes(model, initial),
        "real_parameters": model.real_parameters,
        "heldout_reads": 0,
        "labels_reads": "validation diagnostics only"
        if code == "NR"
        else "train/validation only",
        "history_path": str(folder / "training_history.jsonl"),
        "history_sha256": sha(folder / "training_history.jsonl"),
        "actual_action_calls": action.calls,
    }
    write_json(folder / "weights_frozen.json", result)
    return result


def evaluate(folder, budget, code):
    import torch

    # All weights must freeze before even R0 enters new heldout evaluation.
    frozen = {c: stage("TRAIN_" + c)[0] for c in ("NR", "NE", "RL", "CL")}
    if any(r["status"] != "WEIGHTS_FROZEN" for r in frozen.values()):
        raise ValueError("weights not frozen")
    ds, _ = stage("DATA")
    values = read_arrays(ds["prefix"]["heldout"])
    action = load_action(budget)
    model = None
    if code != "R0":
        model = model_for(code, action)
        assign_model(model, frozen[code]["selected"]["receipt"])
    inventory = [r for r in ds["inventory"] if r["split"] == "heldout"]
    rows = []
    for i, (r, z64, s) in enumerate(
        zip(values["rhs"], values["prefix"], values["residual"], strict=True)
    ):
        began = monotonic()
        calls = dict(action.calls)
        ti = perf_counter()
        if code == "R0" or inventory[i]["prefix_bypass"]:
            delta = np.zeros_like(r)
        else:
            with torch.no_grad():
                delta = model(torch.from_numpy(s.copy())).numpy()[0]
        inference = perf_counter() - ti
        initial = z64 + delta
        initial_residual = r - action.apply(initial)
        remain = 128 - inventory[i]["solver"]["steps"]
        z, result = fixed_cleanup(action, r, initial, max_steps=remain, tol=1e-10)
        residual = r - action.apply(z)
        receipt = save(
            folder,
            f"heldout_{i}_{code}",
            rhs=r,
            prefix=z64,
            prefix_residual=s,
            delta=delta,
            initial=initial,
            initial_residual=initial_residual,
            z=z,
            residual=residual,
        )
        row = {
            "split": "heldout",
            "sample": i,
            "route": ROUTES[code],
            "state": receipt,
            "solver": result,
            "total_Arnoldi": inventory[i]["solver"]["steps"] + result["steps"],
            "inference_seconds": inference,
            "load_seconds": action.load_seconds,
            "actual_online_increment_seconds": monotonic() - began,
            "common_prefix_seconds": inventory[i]["solver"]["seconds"],
            "independent_online_seconds": inventory[i]["solver"]["seconds"]
            + monotonic()
            - began,
            "calls_increment": {k: action.calls[k] - calls[k] for k in calls},
            "measurement_start_monotonic": began,
            "measurement_end_monotonic": monotonic(),
            "frozen_model": frozen[code]["selected"]["receipt"]
            if code != "R0"
            else None,
            "heldout_e_reads": 0,
        }
        if row["total_Arnoldi"] > 128:
            raise RuntimeError("total Arnoldi cap")
        rows.append(row)
        print(
            json.dumps(
                {
                    "route": row["route"],
                    "sample": i,
                    "steps": row["total_Arnoldi"],
                    "rho": result["rho"],
                }
            ),
            flush=True,
        )
    return {
        "status": "ROUTE_FROZEN",
        "route": ROUTES[code],
        "rows": rows,
        "one_model_resident": True,
        "heldout_error_reads": 0,
        "actual_action_calls": action.calls,
    }


def check(folder, budget):
    from benchmarks.check_neighborhood_late_error import (
        require_inventory,
        require_model,
    )
    from benchmarks.check_neighborhood_residual import audit_state, require_frozen_input

    ds, _ = stage("DATA")
    bridge, graph, _ = graph_packet()
    action = load_action(budget)
    rows = [
        r for c in ("R0", "NR", "NE", "RL", "CL") for r in stage("EVAL_" + c)[0]["rows"]
    ]
    require_inventory(rows)
    frozen = read_arrays(ds["prefix"]["heldout"])
    error = read_arrays(ds["sealed"]["heldout"])["error"]
    if error.shape != (8, int(graph["shape"][0])) or not np.isfinite(error).all():
        raise ValueError("complete finite sealed error inventory")
    if np.count_nonzero(error[:, graph["slaves"]]):
        raise ValueError("manufactured error slave-zero identity")
    models = {
        ROUTES[c]: stage("TRAIN_" + c)[0]["selected"]["receipt"]
        for c in ("NR", "NE", "RL", "CL")
    }
    result = []
    for row in rows:
        a = read_arrays(row["state"])
        i = row["sample"]
        e = error[i]
        require_model(row["frozen_model"], models.get(row["route"]))
        require_frozen_input(a, frozen["rhs"][i], graph["independent"], graph["slaves"])
        if not np.array_equal(a["rhs"], frozen["rhs"][i]) or not np.array_equal(
            a["prefix"], frozen["prefix"][i]
        ):
            raise ValueError("frozen RHS/prefix identity")
        if (
            row["frozen_model"]
            and sha(row["frozen_model"]["path"]) != row["frozen_model"]["sha256"]
        ):
            raise ValueError("model identity")
        applied = action.apply(a["z"])
        res = a["rhs"] - applied
        ident = ratio(res, a["residual"])
        gate = audit_state(
            action.matrix,
            a["z"],
            a["rhs"],
            e,
            graph["independent"],
            graph["slaves"],
            applied=applied,
        )
        stages = {}
        for label, key in (
            ("prefix", "prefix"),
            ("corrected", "initial"),
            ("final", "z"),
        ):
            diff = e - a[key]
            groups = {}
            for name in ("trace", "interior"):
                # Use graph canonical offsets, not native row ordering.
                mask = np.concatenate(
                    [
                        np.arange(graph["offsets"][j], graph["offsets"][j + 1])
                        for j, m in enumerate(graph["sizes"])
                        if (m == 450) == (name == "interior")
                    ]
                )
                wanted = bridge.conjugate().T @ e
                got = bridge.conjugate().T @ diff
                groups[name] = float(
                    np.linalg.norm(got[mask]) / np.linalg.norm(wanted[mask])
                )
            stages[label] = dict(
                eta=float(
                    np.linalg.norm(diff[graph["independent"]])
                    / np.linalg.norm(e[graph["independent"]])
                ),
                **groups,
            )
        receipt = save(
            folder,
            f"error_{i}_{row['route'].replace('-', '_')}",
            reference_manufactured=e,
            prefix_error=e - a["prefix"],
            corrected_error=e - a["initial"],
            final_error=e - a["z"],
            recomputed_residual=res,
        )
        result.append(
            dict(
                sample=i,
                route=row["route"],
                family=[
                    r["family"] for r in ds["inventory"] if r["split"] == "heldout"
                ][i],
                **gate,
                saved_residual_identity=ident,
                stages=stages,
                arrays=receipt,
                total_Arnoldi=row["total_Arnoldi"],
                independent_online_seconds=row["independent_online_seconds"],
                qr=float(
                    np.linalg.norm(a["initial_residual"])
                    / np.linalg.norm(a["prefix_residual"])
                ),
                qe=float(
                    np.linalg.norm(a["delta"] - (e - a["prefix"]))
                    / np.linalg.norm(e - a["prefix"])
                ),
            )
        )
    counts = {
        r: sum(
            v["passed"] and v["saved_residual_identity"]["passed"]
            for v in result
            if v["route"] == r
        )
        for r in ROUTES.values()
    }
    return {
        "status": "INDEPENDENT_HELDOUT_FROZEN_AUDIT",
        "rows": result,
        "full_pass_by_route": counts,
        "frozen_count": 40,
        "reference_scope": "V44 heldout manufacturing e only, after queue exit; no REF7/dot",
        "conditional_timing_admitted": any(counts[r] == 8 for r in ("NN-R", "NN-E"))
        and any(counts[r] == 8 for r in ("R0", "RL-E", "CL-E")),
    }


def diagnostic(folder, budget):
    gate, _ = stage("CHECK")
    ds, _ = stage("DATA")
    bridge, graph, _ = graph_packet()
    values = read_arrays(ds["prefix"]["heldout"])
    e = read_arrays(ds["sealed"]["heldout"])["error"]
    # Only diagonal bytes are needed; never reload the original CSR/factor here.
    scale = graph["diagonal_scale"]
    rows = []
    for code in ("NR", "NE", "RL", "CL"):

        class Scale:
            pass

        action = Scale()
        action.scale = scale
        model = model_for(code, action)
        assign_model(model, stage("TRAIN_" + code)[0]["selected"]["receipt"])
        for index, (m, n) in enumerate(model.groups):
            w = model.decoder[index].weight.detach().numpy()
            if code == "CL":
                w = np.block([[w.real, -w.imag], [w.imag, w.real]])
            if w.shape[0] > 900 or w.shape[1] > 64:
                raise MemoryError("small decoder SVD cap")
            began = perf_counter()
            u, s, _ = np.linalg.svd(w, full_matrices=False)
            rank = (
                int(np.count_nonzero(s > max(w.shape) * np.finfo(float).eps * s[0]))
                if s[0]
                else 0
            )
            u = u[:, :rank]
            mask = np.flatnonzero(graph["sizes"] == m)
            nums = []
            dens = []
            for i in range(8):
                v = bridge.conjugate().T @ ((e[i] - values["prefix"][i]) / scale)
                pieces = np.asarray(
                    [v[graph["offsets"][j] : graph["offsets"][j + 1]] for j in mask]
                )
                a = np.concatenate((pieces.real, pieces.imag), axis=1)
                projected = (a @ u) @ u.T
                nums.append(float(np.linalg.norm(a - projected)))
                dens.append(float(np.linalg.norm(a)))
            rows.append(
                {
                    "route": ROUTES[code],
                    "moments": m,
                    "shape": list(w.shape),
                    "rank": rank,
                    "seconds": perf_counter() - began,
                    "singular_values": s.tolist(),
                    "projection_numerator": nums,
                    "projection_denominator": dens,
                    "projection_relative": [
                        a / b if b else None for a, b in zip(nums, dens, strict=True)
                    ],
                    "interpretation": "transformed canonical/right-diagonal coordinate norm; not original eta lower bound or achievable prediction",
                }
            )
        del model
    neighbors = [set() for _ in graph["sizes"]]
    for a, b in zip(graph["src"], graph["dst"], strict=True):
        neighbors[a].add(int(b))
    two_hop = [
        len({i} | n | set().union(*(neighbors[j] for j in n)))
        for i, n in enumerate(neighbors)
    ]
    return {
        "status": "FIXED_DECODER_DIAGNOSTIC",
        "rows": rows,
        "small_SVD_calls": 12,
        "two_hop_visible_nodes": {
            "min": min(two_hop),
            "max": max(two_hop),
            "median": float(np.median(two_hop)),
            "total_nodes": len(two_hop),
        },
        "conclusion": "CLOSE_FIXED_A_TWO_HOP_WIDTH32_QUALIFICATION"
        if all(v == 0 for v in gate["full_pass_by_route"].values())
        else "BOUNDED_PILOT_ONLY",
        "memory_formula": {
            "real_output_bytes_per_independent_coefficient": 16,
            "real_hidden_bytes_per_node_per_layer": 32 * 8,
            "training_batch": 2,
            "message_rounds": 2,
            "neighbor_index_bytes_per_link": 16,
        },
        "global_basis_created": False,
    }


def execute(role, folder, state):
    import sys

    import torch

    from src.solvers.isolated_ml_sparse import loaded_math_threads
    from src.solvers.neighborhood_residual_models import configure_threads

    window.guard_worker_parent()
    configure_threads()
    if any(n in sys.modules for n in ("petsc4py", "dolfinx", "mpi4py")):
        raise RuntimeError("FE ABI injection")
    budget = ActionBudget(Path(os.environ["TASK042_V36_AUX_DIRECTORY"]))
    if role.startswith("TRAIN_"):
        result = train(folder, budget, role[6:])
    elif role.startswith("EVAL_"):
        result = evaluate(folder, budget, role[5:])
    else:
        result = {
            "SETUP": setup,
            "DATA": data,
            "GRADIENT": gradient,
            "CHECK": check,
            "DIAGNOSTIC": diagnostic,
        }[role](folder, budget)
    result.update(
        environment={
            "executable": sys.executable,
            "Torch": torch.__version__,
            "NumPy": np.__version__,
            "intra": torch.get_num_threads(),
            "interop": torch.get_num_interop_threads(),
            "CUDA_available": torch.cuda.is_available(),
            "GPU": 0,
            "DataLoader": 0,
            "affinity": sorted(os.sched_getaffinity(0)),
            "loaded_threadpools": loaded_math_threads(),
        },
        numerical_counts=budget.counts,
        actual_math_hashes=implementation_hashes(),
        full_coefficients_not_trace_recovery=True,
    )
    return result
