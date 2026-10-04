"""One V43 stage per run; neural arithmetic lives in reusable solver modules."""

import json
import os
from pathlib import Path
from time import monotonic, perf_counter

import numpy as np

from benchmarks.check_boundary_witness import read_arrays
from src.runners.task042_shared import write_json
from src.solvers.isolated_ml_sparse import csr_matrix
from src.solvers.native_recovery_packets import sha
from src.solvers.neighborhood_residual_core import (
    OriginalCSR,
    entity_graph,
    fixed_cleanup,
    manufactured,
    ratio,
)
from src.solvers.neighborhood_residual_scope import (
    ROOT,
    ActionBudget,
    implementation_hashes,
    parent,
    plan_record,
    stage,
)
from src.solvers.port_component_study import array_file


def dereference(label):
    p = parent(label)
    return json.loads(Path(p["path"]).read_text()) if "path" in p else p


def save(folder, name, **arrays):
    return array_file(
        folder / (name + ".npz"), compressed=True, deduplicate=False, **arrays
    )


def load_action(budget):
    began = perf_counter()
    action = OriginalCSR(read_arrays(parent("csr")["arrays"]), budget)
    action.load_seconds = perf_counter() - began
    return action


def graph_packet():
    row, _ = stage("SETUP")
    if not row["passed"]:
        raise ValueError("original action / canonical bridge gate")
    a = read_arrays(row["graph"])
    b = csr_matrix(
        (a.pop("bridge_data"), a.pop("bridge_indices"), a.pop("bridge_indptr")),
        shape=tuple(a["shape"]),
    )
    return b, a


def read_training_split(label):
    if label not in ("train", "validation"):
        raise ValueError("training reader accepts train/validation only")
    row, _ = stage("DATA")
    return read_arrays(row["RHS"][label])["rhs"]


def setup(folder, budget):
    from mpi4py import MPI

    from src.solvers.distributed_entity_volume import NativeDistributedAction
    from src.solvers.distributed_volume_study import element
    from src.solvers.native_entity_adapter import entity_transform
    from src.solvers.native_entity_protocol import canonical_values

    p = dereference("bridge")["results"][0]["packets"][0]
    literal = read_arrays(p["numeric"])
    metadata = p["metadata"]
    el = element()
    b, graph = entity_graph(
        literal, metadata, np.asarray(el.entity_dofs[3][0]), entity_transform
    )
    classes = dereference("classes")
    matrices = [
        read_arrays(
            json.loads(
                (
                    ROOT
                    / "benchmarks/artifacts/task042/v42/checkpoints"
                    / (n + "_tensor.json")
                ).read_text()
            )["arrays"]
        )["raw"]
        for n in classes["class_names"]
    ]
    table = {
        (r["tag"], *r["width_hex"]): i for i, r in enumerate(classes["class_keys"])
    }
    ids = np.array(
        [
            table[
                int(literal["cell_tags"][c]),
                *[float(v).hex() for v in np.ptp(literal["coordinates"][cell], axis=0)],
            ]
            for c, cell in enumerate(literal["cell_vertices"])
        ]
    )
    production = NativeDistributedAction(
        MPI.COMM_SELF, literal, matrices, ids, el, metadata["owned_dofs"], 64
    )
    action = load_action(budget)
    saved = read_arrays(dereference("volume")["packets"][0]["numeric"])
    checks, benchmark = [], []
    q = np.concatenate(
        [
            canonical_values(key[None, :], int(m), 424201)[0]
            for key, m in zip(graph["keys"], graph["sizes"], strict=True)
        ]
    )
    x = b @ q
    checks.append(
        dict(kind="complete_literal_canonical_to_saved_native", **ratio(x, saved["x"]))
    )
    checks.append(dict(kind="complete_roundtrip", **ratio(b.conjugate().T @ x, q)))
    rng = np.random.default_rng(424331)
    v = rng.normal(size=b.shape[0]) + 1j * rng.normal(size=b.shape[0])
    left, right = np.vdot(v, x), np.vdot(b.conjugate().T @ v, q)
    den = np.linalg.norm(v) * np.linalg.norm(x)
    checks.append(
        {
            "kind": "full_primal_dual",
            "numerator": float(abs(left - right)),
            "denominator": float(den),
            "relative": float(abs(left - right) / den),
            "passed": bool(abs(left - right) <= 1e-10 * den),
        }
    )
    for adjoint, inp in ((False, x), (True, saved["y"])):
        began = perf_counter()
        expected = budget.call(
            lambda u, adjoint=adjoint: production.apply_original(u, adjoint=adjoint),
            inp,
            kind="production_AH" if adjoint else "production_A",
        )
        production_seconds = perf_counter() - began
        began = perf_counter()
        actual = action.apply(inp, adjoint=adjoint)
        benchmark.append(
            {
                "kind": "AH" if adjoint else "A",
                "production_seconds": production_seconds,
                "CSR_seconds": perf_counter() - began,
            }
        )
        checks.append(
            dict(
                kind="ML_CSR_original_" + ("adjoint" if adjoint else "forward"),
                **ratio(actual, expected),
            )
        )
    # Current output MPC expansion, rather than a frozen producer-u stand-in.
    current = b @ (rng.normal(size=b.shape[1]) + 1j * rng.normal(size=b.shape[1]))
    expanded = production.expand(current)
    expected = current.copy()
    for row in literal["slave_local_dofs"]:
        lo, hi = literal["MPC_offsets"][row : row + 2]
        expected[row] = (
            literal["MPC_coefficients"][lo:hi] @ current[literal["MPC_masters"][lo:hi]]
        )
    checks.append(dict(kind="current_output_literal_MPC", **ratio(expanded, expected)))
    receipt = save(
        folder,
        "graph",
        **graph,
        bridge_indptr=b.indptr,
        bridge_indices=b.indices,
        bridge_data=b.data,
        diagonal_scale=action.scale,
    )
    # Worst-case accounting includes both resident sparse A/AH, loader arrays,
    # model/autograd/output/GK and runtime. Not the array size alone.
    predicted = 5 * 2**30
    per_action = max(r["CSR_seconds"] for r in benchmark)
    return {
        "status": "ORIGINAL_ACTION_AND_COMPLETE_NEURAL_DECODER_READY"
        if all(c["passed"] for c in checks)
        else "NEURAL_INTERFACE_NOT_QUALIFIED",
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "graph": receipt,
        "nodes_by_moments": {
            str(m): int(np.count_nonzero(graph["sizes"] == m)) for m in (6, 60, 450)
        },
        "independent_rows": b.shape[1],
        "native_rows": b.shape[0],
        "slave_rows": len(graph["slaves"]),
        "current_output_MPC": True,
        "zero_diagonal_rows": action.zero_diagonal.tolist(),
        "capacity": {
            "predicted_simultaneous_peak_bytes": predicted,
            "resident_CSR_payload_bytes": 971189560,
            "adjoint_conjugate_copy_included": True,
            "new_factor_QR_JIT_mesh": 0,
        },
        "action_measurement": benchmark,
        "predicted_6000_action_seconds": per_action * 6000,
        "reserve_fraction": 0.25,
        "matrix_identity": parent("csr"),
        "neural_live_core_hashes": implementation_hashes(),
    }


def data(folder, budget):
    b, graph = graph_packet()
    action = load_action(budget)
    inventory, rhs_receipts, error_receipts = [], {}, {}
    for split, item in plan_record()["split"].items():
        vectors, errors = [], []
        for i, seed in enumerate(item["seeds"]):
            family = item["families"][int(i >= len(item["seeds"]) // 2)]
            e = b @ manufactured(graph, family, seed)
            r = action.apply(e)
            scale = float(np.linalg.norm(r))
            r, e = r / scale, e / scale
            vectors.append(r)
            errors.append(e)
            inventory.append(
                {
                    "split": split,
                    "sample": i,
                    "seed": seed,
                    "family": family,
                    "native_rows": len(r),
                    "normalization_original_rhs_norm": scale,
                    "rhs_hash": __import__("hashlib").sha256(r.tobytes()).hexdigest(),
                    "support_coefficients": int(np.count_nonzero(e)),
                    "error_sealed": True,
                }
            )
        rhs_receipts[split] = save(folder, "rhs_" + split, rhs=np.asarray(vectors))
        # A separate package; the only reader is the post-freeze checker.
        error_receipts[split] = save(
            folder, "sealed_errors_" + split, error=np.asarray(errors)
        )
    return {
        "status": "DATASET_FROZEN",
        "RHS": rhs_receipts,
        "sealed_errors": error_receipts,
        "inventory": inventory,
        "seed_family_disjoint": True,
        "matrix_manifest_hash": sha(plan_record()["parents"]["csr"]["path"]),
        "teacher_solve": False,
        "training_e_reads": 0,
    }


def model_for(linear, action):
    from src.solvers.neighborhood_residual_models import NeighborhoodCorrector

    b, graph = graph_packet()
    return NeighborhoodCorrector(
        b, graph, action.scale, linear=linear, seed=plan_record()["seed"]
    )


def save_model(folder, name, model, optimizer, extra):
    import torch

    path = folder / (name + ".pt")
    temporary = path.with_suffix(".writing")
    torch.save(
        {
            "parameters": {n: p.detach().clone() for n, p in model.named_parameters()},
            "optimizer": optimizer.state_dict() if optimizer else None,
            "extra": extra,
        },
        temporary,
    )
    os.replace(temporary, path)
    return {"path": str(path), "sha256": sha(path), "committed": True}


def assign_model(model, receipt):
    import torch

    if sha(receipt["path"]) != receipt["sha256"]:
        raise ValueError("frozen model bytes changed")
    state = torch.load(receipt["path"], weights_only=True, map_location="cpu")
    with torch.no_grad():
        for name, p in model.named_parameters():
            p.copy_(state["parameters"][name])
    return state


def gradient(folder, budget):
    import torch
    from torch.func import functional_call

    from src.solvers.neighborhood_residual_models import original_loss, parameters_hash

    action = load_action(budget)
    model = model_for(False, action)
    rhs = torch.from_numpy(read_training_split("train")[:2].copy())
    timed_start = perf_counter()
    loss, delta, _ = original_loss(model, rhs, action)
    grads = torch.autograd.grad(loss, tuple(model.parameters()))
    whole_step_seconds = perf_counter() - timed_start
    counted_action_seconds = sum(action.seconds.values())
    network_seconds = max(0.0, whole_step_seconds - counted_action_seconds)
    save_model(
        folder,
        "gradient_origin",
        model,
        None,
        {"seed": plan_record()["seed"], "use": "gradient witness only"},
    )
    save(
        folder,
        "gradient_origin",
        rhs=rhs.numpy(),
        delta=delta.detach().numpy(),
        gradients=np.concatenate([g.detach().numpy().ravel() for g in grads]),
    )
    names = [n for n, _ in model.named_parameters()]
    weights = tuple(p.detach().clone().requires_grad_() for p in model.parameters())

    def output(*params):
        return functional_call(model, dict(zip(names, params, strict=True)), (rhs,))

    checks, fd_rows = [], []
    serial_losses, serial_grads = [], []
    for sample in rhs:
        single, _, _ = original_loss(model, sample[None, :], action)
        serial_losses.append(float(single.detach()))
        serial_grads.append(torch.autograd.grad(single, tuple(model.parameters())))
    batch_error = abs(float(loss.detach()) - float(np.mean(serial_losses)))
    grad_serial = [
        sum(g[i] for g in serial_grads) / len(rhs) for i in range(len(grads))
    ]
    grad_error = float(
        torch.sqrt(
            sum(
                torch.sum(abs(a - b) ** 2)
                for a, b in zip(grads, grad_serial, strict=True)
            )
        )
    )
    grad_den = float(torch.sqrt(sum(torch.sum(abs(g) ** 2) for g in grads)))
    checks.append(
        {
            "kind": "actual_batch1_batch2_full_loss_gradient",
            "loss_difference": batch_error,
            "gradient_numerator": grad_error,
            "gradient_denominator": grad_den,
            "passed": batch_error <= 1e-10 * abs(float(loss.detach()))
            and grad_error <= 1e-10 * grad_den,
        }
    )
    q = -action.apply(
        (rhs.numpy() - action.apply(delta.detach().numpy().T).T).T, adjoint=True
    ).T
    q /= (np.linalg.norm(rhs.numpy(), axis=1) ** 2)[:, None] * len(rhs)
    for i, seed in enumerate(plan_record()["FD_seeds"]):
        gen = torch.Generator().manual_seed(seed)
        directions = [
            torch.randn(p.shape, generator=gen, dtype=p.dtype) for p in weights
        ]
        # The third direction is only message parameters: an actual hidden witness.
        if i == 2:
            directions = [
                v if n.startswith("message") else torch.zeros_like(v)
                for n, v in zip(names, directions, strict=True)
            ]
        norm = torch.sqrt(sum(torch.sum(v**2) for v in directions))
        directions = tuple(v / norm for v in directions)
        _, jvp = torch.autograd.functional.jvp(output, weights, directions, strict=True)
        jv = jvp.detach().numpy()
        expected = float(
            sum(torch.sum(g * v) for g, v in zip(grads, directions, strict=True))
        )
        actual = float(np.vdot(jv, q).real)
        den = max(float(np.linalg.norm(jv) * np.linalg.norm(q)), 1e-30)
        checks.append(
            {
                "kind": f"full_original_VJP_direction_{i}",
                "numerator": abs(actual - expected),
                "denominator": den,
                "relative": abs(actual - expected) / den,
                "result_scale": max(abs(actual), abs(expected)),
                "left": actual,
                "right": expected,
                "passed": abs(actual - expected) / den <= 1e-10,
            }
        )
        successes = 0
        for h in plan_record()["FD_steps"]:
            plus = output(
                *(p + h * v for p, v in zip(weights, directions, strict=True))
            )
            minus = output(
                *(p - h * v for p, v in zip(weights, directions, strict=True))
            )
            fd = ((plus - minus) / (2 * h)).detach().numpy()
            row = ratio(fd, jv, tol=1e-5)
            receipt = save(
                folder, f"FD_direction_{i}_step_{h:.0e}", finite_difference=fd, jvp=jv
            )
            successes += int(row["passed"])
            fd_rows.append(
                dict(
                    direction=i,
                    step=h,
                    near_zero_rule="if norm(Jd)=0 require exact zero; otherwise relative",
                    **row,
                    arrays=receipt,
                )
            )
        checks.append(
            {
                "kind": f"full_vector_JVP_three_steps_direction_{i}",
                "passed_steps": successes,
                "passed": successes >= 2,
            }
        )
        save(folder, "direction_" + str(i), jvp=jv, vjp=np.asarray([actual, expected]))
    linear = model_for(True, action)
    with torch.no_grad():
        r, s = rhs[:1], rhs[1:]
        got, want = (
            linear((0.7 - 0.3j) * r + (-0.2 + 0.6j) * s),
            (0.7 - 0.3j) * linear(r) + (-0.2 + 0.6j) * linear(s),
        )
        checks.append(
            dict(kind="complex_linear_control", **ratio(got.numpy(), want.numpy()))
        )
        nnphase = ratio(model(1j * r).numpy(), (1j * model(r)).numpy())
        nnamp = ratio(model(3.2 * r).numpy(), (3.2 * model(r)).numpy())
        zeros = model(torch.zeros_like(r)).numpy()
        checks.append(dict(kind="NN_exact_zero", **ratio(zeros, np.zeros_like(zeros))))
    port = port_gradient(folder, budget)
    write_json(folder / "B_gradient_completed.json", port)
    passed = all(c["passed"] for c in checks) and port["passed"]
    from src.solvers.neighborhood_residual_scope import window

    setup_record, _ = stage("SETUP")
    vector_seconds = max(a["CSR_seconds"] for a in setup_record["action_measurement"])
    # Conservative full cap, plus all 256 training updates' measured non-action
    # cost and repeated sparse loads. These are predictions, not timed solves.
    forecast = 6000 * vector_seconds + 256 * network_seconds + 8 * action.load_seconds
    available = window.worker_learning_remaining()
    budget_ready = forecast <= 0.75 * available
    return {
        "status": "NEURAL_FULL_RESIDUAL_GRADIENT_QUALIFIED"
        if passed
        else "GRADIENT_NOT_QUALIFIED",
        "passed": passed,
        "checks": checks,
        "FD": fd_rows,
        "initial_parameters_hash": parameters_hash(model),
        "NN_parameters_real": model.real_parameters,
        "LIN_parameters_real": linear.real_parameters,
        "phase_behavior": nnphase,
        "positive_amplitude_behavior": nnamp,
        "loss": float(loss.detach()),
        "B_port_gradient": port,
        "budget_forecast": {
            "kind": "predicted",
            "seconds": forecast,
            "available_seconds": available,
            "verification_reserve_fraction": 0.25,
            "passed": budget_ready,
            "measured_whole_batch2_gradient_seconds": whole_step_seconds,
            "measured_action_seconds_inside_step": counted_action_seconds,
            "measured_network_seconds_inside_step": network_seconds,
            "measured_matrix_load_seconds": action.load_seconds,
        },
    }


def port_gradient(folder, budget):
    """Saved B matrices, current nonzero coefficients; no recovery or new JIT."""
    from src.solvers.neighborhood_port_gradient import saved_port_check

    return saved_port_check(folder, budget)


def validation(model, rhs, action):
    import torch

    from src.solvers.neighborhood_residual_models import original_loss

    with torch.no_grad():
        _, _, per = original_loss(model, rhs, action)
    return np.sqrt(2 * per.numpy())


def train(folder, budget, linear):
    import torch

    from src.solvers.neighborhood_residual_models import (
        group_changes,
        original_loss,
        parameters_hash,
    )

    gate, _ = stage("GRADIENT")
    if not gate["passed"] and not linear:
        raise ValueError("real neural gradient not qualified")
    if not any(
        c["kind"] == "complex_linear_control" and c["passed"] for c in gate["checks"]
    ):
        raise ValueError("linear residual-model gate")
    if not gate["budget_forecast"]["passed"]:
        raise RuntimeError(
            "measured pilot forecast cannot reserve 25 percent verification budget"
        )
    action = load_action(budget)
    model = model_for(linear, action)
    rhs = torch.from_numpy(read_training_split("train").copy())
    val = torch.from_numpy(read_training_split("validation").copy())
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    initial = {n: p.detach().clone() for n, p in model.named_parameters()}
    v0 = validation(model, val, action)
    checkpoints = [
        {
            "update": 0,
            "residuals": v0.tolist(),
            "median": float(np.median(v0)),
            "receipt": save_model(
                folder, "checkpoint_0", model, optimizer, {"update": 0}
            ),
        }
    ]
    history = []
    reason = "UPDATE_LIMIT_128"
    for step in range(1, 129):
        began = perf_counter()
        before = parameters_hash(model)
        # A complete pre-update transaction is sufficient for Adam; no closure
        # acceptance state is claimed. Counters and time are never rolled back.
        committed = save_model(
            folder, "last_committed", model, optimizer, {"update": step - 1}
        )
        ids = [(2 * (step - 1)) % 16, (2 * (step - 1) + 1) % 16]
        optimizer.zero_grad(set_to_none=True)
        loss, _, per = original_loss(model, rhs[ids], action)
        loss.backward()
        grad_norm = float(
            torch.sqrt(sum(torch.sum(abs(p.grad) ** 2) for p in model.parameters()))
        )
        if not np.isfinite(float(loss.detach())) or not np.isfinite(grad_norm):
            save_model(
                folder,
                "nonfinite_last_committed",
                model,
                optimizer,
                {"update": step - 1},
            )
            raise ArithmeticError("nonfinite full original loss/gradient")
        optimizer.step()
        if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
            assign_model(model, committed)
            optimizer.load_state_dict(
                torch.load(committed["path"], weights_only=True, map_location="cpu")[
                    "optimizer"
                ]
            )
            raise ArithmeticError(
                "nonfinite Adam update; complete parameter/optimizer transaction restored"
            )
        row = {
            "update": step,
            "batch_samples": ids,
            "loss_before_update": float(loss.detach()),
            "per_rhs_loss": per.detach().tolist(),
            "gradient_norm": grad_norm,
            "parameter_before_hash": before,
            "parameter_after_hash": parameters_hash(model),
            "seconds": perf_counter() - began,
            "calls": dict(action.calls),
            "group_changes": group_changes(model, initial),
        }
        history.append(row)
        with (folder / "training_history.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
        if step in (16, 32, 64, 128):
            residuals = validation(model, val, action)
            checkpoints.append(
                {
                    "update": step,
                    "residuals": residuals.tolist(),
                    "median": float(np.median(residuals)),
                    "receipt": save_model(
                        folder,
                        "checkpoint_" + str(step),
                        model,
                        optimizer,
                        {"update": step},
                    ),
                }
            )
            print(
                json.dumps(
                    {
                        "route": "R-LIN" if linear else "R-NN",
                        "update": step,
                        "validation": residuals.tolist(),
                        "calls": action.calls,
                    }
                ),
                flush=True,
            )
            if (
                step == 32
                and not linear
                and np.median(residuals) > 0.8 * np.median(v0)
                and max(residuals) >= max(v0)
            ):
                reason = "TRAINING_EFFICACY_NEGATIVE"
                break
    selected = min(checkpoints, key=lambda c: c["median"])
    changes = group_changes(model, initial)
    frozen = {
        "selected": selected,
        "all_checkpoints": checkpoints,
        "training_updates": len(history),
        "stop_reason": reason,
    }
    write_json(folder / "weights_frozen.json", frozen)
    return {
        "status": "WEIGHTS_FROZEN",
        **frozen,
        "route": "R-LIN" if linear else "R-NN",
        "history_path": str(folder / "training_history.jsonl"),
        "history_sha256": sha(folder / "training_history.jsonl"),
        "parameter_group_changes_last": changes,
        "real_parameters": model.real_parameters,
        "heldout_reads": 0,
        "sealed_error_reads": 0,
        "training_original_action_calls": action.calls,
        "model_family": "residual-conditioned shared entity neighborhood",
    }


def evaluate(folder, budget):
    import torch

    nnrow, _ = stage("TRAIN_NN")
    linrow, _ = stage("TRAIN_LIN")
    if nnrow["status"] != "WEIGHTS_FROZEN" or linrow["status"] != "WEIGHTS_FROZEN":
        raise ValueError("both model weights must be frozen before heldout access")
    action = load_action(budget)
    models = {"R-LIN": model_for(True, action), "R-NN": model_for(False, action)}
    for route, row in (("R-LIN", linrow), ("R-NN", nnrow)):
        assign_model(models[route], row["selected"]["receipt"])
    ds, _ = stage("DATA")
    rhs = read_arrays(ds["RHS"]["heldout"])["rhs"]
    rows = []
    for i, r in enumerate(rhs):
        for route in ("R0", "R-LIN", "R-NN"):
            began = monotonic()
            calls = dict(action.calls)
            infer_start = perf_counter()
            if route == "R0":
                initial = np.zeros_like(r)
            else:
                with torch.no_grad():
                    initial = models[route](torch.from_numpy(r.copy())).numpy()[0]
            inference = perf_counter() - infer_start
            initial_residual = r - action.apply(initial)
            z, result = fixed_cleanup(action, r, initial)
            residual = r - action.apply(z)
            # Frozen terminal behavior: these are the same original sample's
            # phase/amplitude probes, not additional solver runs or new splits.
            behaviour, probe_arrays = {}, {}
            probe_begin = perf_counter()
            if route != "R0":
                with torch.no_grad():
                    rr = torch.from_numpy(r.copy())
                    phase = models[route](1j * rr).numpy()[0]
                    amplitude = models[route](3.2 * rr).numpy()[0]
                    zero = models[route](torch.zeros_like(rr)).numpy()[0]
                behaviour = {
                    "complex_phase": ratio(phase, 1j * initial),
                    "positive_amplitude": ratio(amplitude, 3.2 * initial),
                    "exact_zero": bool(np.count_nonzero(zero) == 0),
                    "phase_original_initial_rho": float(
                        np.linalg.norm(1j * r - action.apply(phase)) / np.linalg.norm(r)
                    ),
                    "amplitude_original_initial_rho": float(
                        np.linalg.norm(3.2 * r - action.apply(amplitude))
                        / (3.2 * np.linalg.norm(r))
                    ),
                    "NN_phase_linearity_is_not_a_required_inverse_claim": route
                    == "R-NN",
                }
                probe_arrays = {
                    "phase_correction": phase,
                    "amplitude_correction": amplitude,
                    "zero_correction": zero,
                }
            behaviour_seconds = perf_counter() - probe_begin
            receipt = save(
                folder,
                f"heldout_{i}_{route.replace('-', '_')}",
                rhs=r,
                initial=initial,
                initial_residual=initial_residual,
                z=z,
                residual=residual,
                **probe_arrays,
            )
            row = {
                "split": "heldout",
                "sample": i,
                "route": route,
                "state": receipt,
                "solver": result,
                "inference_seconds": inference,
                "whole_RHS_seconds": monotonic() - began,
                "begin_monotonic": began,
                "end_monotonic": monotonic(),
                "initial_rho": float(
                    np.linalg.norm(initial_residual) / np.linalg.norm(r)
                ),
                "A_calls": action.calls["A"] - calls["A"],
                "AH_calls": action.calls["AH"] - calls["AH"],
                "initialization": "zero" if route == "R0" else "learned warm-start",
                "reference_reads": 0,
                "frozen_model_behaviour": behaviour,
                "behaviour_audit_seconds_inside_whole_RHS": behaviour_seconds,
            }
            rows.append(row)
            write_json(folder / "frozen_results.json", {"rows": rows})
            print(
                json.dumps(
                    {
                        "sample": i,
                        "route": route,
                        "steps": result["steps"],
                        "rho": result["rho"],
                        "A_calls": row["A_calls"],
                    }
                ),
                flush=True,
            )
    return {
        "status": "SOLVING_QUEUE_FROZEN",
        "rows": rows,
        "frozen_model_hashes": {
            "R-NN": nnrow["selected"]["receipt"]["sha256"],
            "R-LIN": linrow["selected"]["receipt"]["sha256"],
        },
        "sealed_error_reads": 0,
        "official_results": False,
    }


def check(folder, budget):
    from benchmarks.check_neighborhood_residual import (
        audit_state,
        require_frozen_input,
        require_inventory,
    )

    row, _ = stage("EVALUATE")
    require_inventory(row["rows"])
    ds, _ = stage("DATA")
    frozen_rhs = read_arrays(ds["RHS"]["heldout"])["rhs"]
    for route, label in (("R-NN", "TRAIN_NN"), ("R-LIN", "TRAIN_LIN")):
        training, _ = stage(label)
        receipt = training["selected"]["receipt"]
        if (
            row["frozen_model_hashes"][route] != receipt["sha256"]
            or sha(receipt["path"]) != receipt["sha256"]
        ):
            raise ValueError(
                "heldout candidate model differs from frozen validation selection"
            )
    errors = read_arrays(ds["sealed_errors"]["heldout"])["error"]
    _b, graph = graph_packet()
    if frozen_rhs.shape != errors.shape or frozen_rhs.shape != (
        8,
        int(graph["shape"][0]),
    ):
        raise ValueError("complete heldout DATA/reference/native inventory")
    action = load_action(budget)
    audited = []
    for item in row["rows"]:
        arrays = read_arrays(item["state"])
        require_frozen_input(
            arrays, frozen_rhs[item["sample"]], graph["independent"], graph["slaves"]
        )
        # Each explicit checker replay remains an original A action and is billed.
        actual = budget.call(
            action.matrix.__matmul__, arrays["z"], kind="independent_frozen_checker_A"
        )
        checks = audit_state(
            action.matrix,
            arrays["z"],
            arrays["rhs"],
            errors[item["sample"]],
            graph["independent"],
            graph["slaves"],
            applied=actual,
        )
        checks["saved_residual_consistent"] = ratio(
            arrays["residual"], arrays["rhs"] - actual
        )["passed"]
        checks["frozen_rhs_identity"] = True
        checks["complete_row_coverage"] = True
        checks["frozen_model_identity"] = True
        if item["route"] != "R0":
            phase = ratio(arrays["phase_correction"], 1j * arrays["initial"])
            amplitude = ratio(arrays["amplitude_correction"], 3.2 * arrays["initial"])
            checks["frozen_behaviour_recomputed"] = {
                "phase": phase,
                "amplitude": amplitude,
                "exact_zero": bool(np.count_nonzero(arrays["zero_correction"]) == 0),
                "complex_linearity_required": item["route"] == "R-LIN",
            }
            if (
                not amplitude["passed"]
                or np.count_nonzero(arrays["zero_correction"])
                or (item["route"] == "R-LIN" and not phase["passed"])
            ):
                checks["passed"] = False
        audited.append({"sample": item["sample"], "route": item["route"], **checks})
    qualified = {
        r: all(
            a["passed"] and a["saved_residual_consistent"]
            for a in audited
            if a["route"] == r
        )
        for r in ("R0", "R-LIN", "R-NN")
    }
    write_json(
        folder / "independent_heldout.json", {"rows": audited, "qualified": qualified}
    )
    return {
        "status": "PILOT_COMPARISON_COMPLETE",
        "rows": audited,
        "qualified": qualified,
        "NN20": "NOT_DEMONSTRATED"
        if not any(qualified[r] for r in ("R0", "R-LIN"))
        else "FULL_COST_AND_SHARED_WORKSTATION_DECISION_REQUIRED",
        "target_full_PDE": "NOT_QUALIFIED",
        "recovery_A_B": "OLD_FAIL_RETAINED",
        "training_reentry": False,
    }


def execute(role, folder, state):
    budget = ActionBudget(Path(os.environ["TASK042_V36_AUX_DIRECTORY"]))
    if role in ("DATA", "GRADIENT", "TRAIN_NN", "TRAIN_LIN", "EVALUATE", "CHECK"):
        import torch

        from src.solvers.neighborhood_residual_models import configure_threads

        configure_threads()
        if any(
            name in __import__("sys").modules
            for name in ("petsc4py", "dolfinx", "mpi4py")
        ):
            raise RuntimeError("FE ABI injected into ML process")
        environment = {
            "Torch": torch.__version__,
            "intra": torch.get_num_threads(),
            "interop": torch.get_num_interop_threads(),
            "device": "CPU",
            "DataLoader_workers": 0,
        }
        import sys

        import scipy

        from src.solvers.isolated_ml_sparse import loaded_math_threads

        pools = loaded_math_threads()
        environment.update(
            executable=sys.executable,
            NumPy=np.__version__,
            SciPy=scipy.__version__,
            NumPy_path=np.__file__,
            SciPy_path=scipy.__file__,
            Torch_path=torch.__file__,
            loaded_threadpools=pools,
            affinity=sorted(os.sched_getaffinity(0)),
            FE_modules_loaded=[],
            CUDA_available=torch.cuda.is_available(),
        )
    else:
        from src.solvers.native_entity_study import environment as fe_environment

        environment = fe_environment()
    functions = {
        "SETUP": setup,
        "DATA": data,
        "GRADIENT": gradient,
        "TRAIN_NN": lambda f, c: train(f, c, False),
        "TRAIN_LIN": lambda f, c: train(f, c, True),
        "EVALUATE": evaluate,
        "CHECK": check,
    }
    if role == "RECOVERY":
        from src.solvers.neighborhood_recovery_diagnostic import decompose

        result = decompose(folder, budget)
    else:
        result = functions[role](folder, budget)
    result.update(
        environment=environment,
        full_coefficients_not_trace_recovery=True,
        numerical_counts=budget.counts,
        actual_math_hashes=implementation_hashes(),
    )
    return result
