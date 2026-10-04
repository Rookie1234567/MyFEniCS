"""V45 mechanism/calibration and controls on the reusable post-prefix workflow."""

import json
import time
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers import full_moment_scope as scope
from src.solvers.full_moment_hierarchy import FullMomentCorrector
from src.solvers.neighborhood_late_error import late_loss
from src.solvers.neighborhood_pilot_workflow import LateErrorStudy
from src.solvers.neighborhood_residual_core import ratio
from src.solvers.neighborhood_residual_study import save, save_model


class FullMomentStudy(LateErrorStudy):
    def __init__(self, context=scope):
        super().__init__(context)
        self.routes = {
            "R0": "R0",
            "CL44": "CL44",
            "LH": "LIN-H",
            "NL": "NN-L",
            "NH": "NN-H",
        }
        self.training_codes = ("LH", "NL", "NH")
        self.neural_routes = ("NN-L", "NN-H")
        self.control_routes = ("R0", "CL44", "LIN-H")
        self.gradient_model_code = "NH"
        self.linear_codes = ("LH",)
        self.real_linear_codes = ("LH",)
        self.decoder_direction = True

    def model_for(self, code, action, *, diagnostic=False):
        bridge, graph, _ = self.graph_packet()
        if code == "CL44":
            from src.solvers.neighborhood_residual_models import NeighborhoodCorrector

            return NeighborhoodCorrector(
                bridge, graph, action.scale, seed=424701, linear=True, zero_decoder=True
            )
        return FullMomentCorrector(
            bridge,
            graph,
            action.scale,
            seed=self.scope.plan_record()["seed"],
            linear=code == "LH",
            local=code == "NL",
            zero_decoder=not diagnostic,
        )

    def frozen_models(self):
        models = super().frozen_models()
        frozen = self.scope.plan_record()["parents"]["CL44"]
        models["CL44"] = {
            "status": "WEIGHTS_FROZEN",
            "selected": {"update": 128, "receipt": {**frozen, "committed": True}},
            "legacy_cost_parent": self.scope.plan_record()["parents"]["CL44_cost"],
        }
        return models

    def timing(self, folder, budget, kind):
        from src.solvers.neural_deployment_cost import consume_timing

        return consume_timing(self, folder, budget, kind)

    def group_changes(self, model, initial):
        names = ("encoder", "message", "decoder", "mix_local", "mix_context")
        return {
            group: float(
                np.sqrt(
                    sum(
                        float(((p.detach() - initial[n]) ** 2).sum())
                        for n, p in model.named_parameters()
                        if n.startswith(group)
                    )
                )
            )
            for group in names
        }

    def restore_training(self, model, opt, code, resume):
        from src.solvers.neighborhood_training_transaction import restore_complete

        if (
            code not in self.training_codes
            or self.scope.sha(resume["path"]) != resume["sha256"]
        ):
            raise ValueError("V45 explicit repair transaction")
        record = json.loads(Path(resume["path"]).read_text())
        if record["code"] != code or record["plan_sha256"] != self.scope.sha(
            self.scope.PLAN
        ):
            raise ValueError("V45 repair code/plan identity")
        return restore_complete(model, opt, record, maximum=128)

    def prior_checkpoints(self, resume):
        record = json.loads(Path(resume["path"]).read_text())
        rows = [r for r in record["all_checkpoints"] if r["update"] > 0]
        if any(
            self.scope.sha(r["receipt"]["path"]) != r["receipt"]["sha256"] for r in rows
        ):
            raise ValueError("immutable prior validation checkpoint bytes")
        return rows

    def commit_update(self, folder, model, opt, step, row, checkpoints, code):
        from src.solvers.neighborhood_residual_models import parameters_hash

        receipt = save_model(
            folder, "committed_slot_" + str(step % 2), model, opt, {"update": step}
        )
        record = {
            "checkpoint": receipt,
            "completed_update": step,
            "last_parameter_hash": parameters_hash(model),
            "code": code,
            "plan_sha256": self.scope.sha(self.scope.PLAN),
            "all_checkpoints": checkpoints,
            "prior_history": {
                "path": str(folder / "training_history.jsonl"),
                "sha256": self.scope.sha(folder / "training_history.jsonl"),
            },
            "source_sha": __import__("os").environ.get("TASK042_RUN_SOURCE"),
        }
        write_json(folder / "adam_committed.json", record)

    def validation(self, model, values, action, graph, mixed):
        model.activation_records.clear()
        model.record_activations = True
        result = super().validation(model, values, action, graph, mixed)
        model.record_activations = False
        result["activation_statistics"] = list(model.activation_records)
        return result

    def setup(self, folder, budget):
        import torch

        from src.runners.diagnostic_storage import inventory_paths
        from src.solvers.neighborhood_residual_models import parameters_hash

        action = self.load_action(budget)
        bridge, graph, _ = self.graph_packet()
        rng = np.random.default_rng(425131)
        canonical = rng.normal(size=(2, bridge.shape[1])) + 1j * rng.normal(
            size=(2, bridge.shape[1])
        )
        x = (bridge @ canonical.T).T
        applied = action.apply(x.T).T
        rhs_norm = np.linalg.norm(applied, axis=1)
        s, d = (
            torch.from_numpy(applied / rhs_norm[:, None]),
            torch.from_numpy(x / rhs_norm[:, None]),
        )
        checks = []
        ah = action.apply(x[1], adjoint=True)
        left, right = np.vdot(x[1], applied[0]), np.vdot(ah, x[0])
        denominator = np.linalg.norm(x[1]) * np.linalg.norm(
            applied[0]
        ) + np.linalg.norm(ah) * np.linalg.norm(x[0])
        checks.append(
            {
                "kind": "actual_original_A_AH",
                "numerator": float(abs(left - right)),
                "operation_denominator": float(denominator),
                "passed": bool(abs(left - right) <= 1e-10 * denominator),
            }
        )
        checks.append(
            dict(
                kind="original_J_roundtrip",
                **ratio(bridge.conjugate().T @ x[0], canonical[0]),
            )
        )
        init_hashes = {}
        model = self.model_for("NH", action, diagnostic=True)
        layout = save(
            folder,
            "canonical_bucket_inventory",
            **model.layout.arrays(),
            keys=graph["keys"],
            independent=graph["independent"],
            slaves=graph["slaves"],
        )
        transpose = []
        for g, m in enumerate(model.layout.moments):
            n = len(model.layout.indices[g])
            a = torch.from_numpy(rng.normal(size=(2, n, 2 * m)))
            for level, row in enumerate(model.layout.levels):
                b = torch.from_numpy(rng.normal(size=(2, len(row["keys"]), 2 * m)))
                for kind, l, r, ld, rd in (
                    (
                        "mean",
                        model.aggregate(a, g, level),
                        model.aggregate_transpose(b, g, level),
                        b,
                        a,
                    ),
                    (
                        "broadcast",
                        model.broadcast(b, g, level),
                        model.broadcast_transpose(a, g, level),
                        a,
                        b,
                    ),
                ):
                    lval, rval = float((l * ld).sum()), float((r * rd).sum())
                    op = float(
                        torch.linalg.vector_norm(l) * torch.linalg.vector_norm(ld)
                        + torch.linalg.vector_norm(r) * torch.linalg.vector_norm(rd)
                    )
                    record = {
                        "kind": kind,
                        "group": g,
                        "level": level,
                        "left": lval,
                        "right": rval,
                        "operation_denominator": op,
                        "numerator": abs(lval - rval),
                        "passed": abs(lval - rval) <= 1e-10 * op,
                    }
                    checks.append(record)
                    transpose.append(record)
        distant = []
        cell_nodes = model.layout.indices[6]
        src = int(cell_nodes[0])
        candidates = [
            int(i)
            for i in cell_nodes
            if model.layout.levels[0]["ids"][i] != model.layout.levels[0]["ids"][src]
        ]
        target = max(
            candidates,
            key=lambda i: float(
                np.linalg.norm(graph["keys"][i, 2:] - graph["keys"][src, 2:])
            ),
        )
        v = torch.zeros((1, bridge.shape[1]), dtype=torch.complex128)
        v[0, graph["offsets"][src] : graph["offsets"][src + 1]] = 0.1 + 0.07j
        for code in self.training_codes:
            witness = self.model_for(code, action, diagnostic=True)
            with torch.no_grad():
                response = witness.canonical(v, fixed_gamma=1.0)
                piece = response[
                    :, graph["offsets"][target] : graph["offsets"][target + 1]
                ]
                norm = float(torch.linalg.vector_norm(piece))
            item = {
                "kind": "fixed_gamma_distant_content",
                "code": code,
                "source_node": src,
                "target_node": target,
                "fixed_gamma": 1.0,
                "response_norm": norm,
                "passed": norm == 0 if code == "NL" else norm > 1e-12,
            }
            checks.append(item)
            distant.append(item)
            init = self.model_for(code, action)
            init_hashes[code] = parameters_hash(init)
            with torch.no_grad():
                checks.append(
                    {
                        "kind": code + "_zero_decoder",
                        "passed": bool(torch.count_nonzero(init(s)) == 0),
                    }
                )
            del witness, init
        checks.append(
            {
                "kind": "same_initial_parameter_bytes",
                "passed": len(set(init_hashes.values())) == 1,
            }
        )
        # A real identity local branch retains all 900 channels, independent of message width64.
        identity = self.model_for("LH", action)
        with torch.no_grad():
            for e, dec, b in zip(
                identity.encoder, identity.decoder, identity.mix_context, strict=True
            ):
                e.weight.copy_(torch.eye(e.weight.shape[0]))
                dec.weight.copy_(torch.eye(dec.weight.shape[0]))
                b.zero_()
            for p in identity.message.parameters():
                p.zero_()
            recovered = identity.canonical(torch.from_numpy(canonical), fixed_gamma=1.0)
        checks.append(
            dict(
                kind="full_900_channel_identity_branch",
                **ratio(recovered.numpy(), canonical),
            )
        )
        del identity
        # Complete network/A/AH/Adam/transaction calibration on throwaway parameters.
        # Candidate training always recreates the zero-decoder frozen initialization.
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        timing = []
        model.record_activations = True
        for i in range(3):
            before = dict(action.seconds)
            phase_before = dict(model.phase_seconds)
            began = time.perf_counter()
            opt.zero_grad(set_to_none=True)
            loss, _, _, _ = late_loss(
                model, s, d, action, mixed=True, independent=graph["independent"]
            )
            loss.backward()
            opt.step()
            computational = time.perf_counter() - began
            io = time.perf_counter()
            cp = save_model(
                folder,
                "calibration_transaction",
                model,
                opt,
                {"diagnostic_only": True, "calibration_update": i + 1},
            )
            io = time.perf_counter() - io
            a_seconds = sum(action.seconds[k] - before[k] for k in before)
            timing.append(
                {
                    "batch": 2,
                    "step_seconds": computational,
                    "original_action_seconds": a_seconds,
                    "network_Adam_seconds": computational - a_seconds,
                    "checkpoint_IO_seconds": io,
                    "checkpoint_bytes": Path(cp["path"]).stat().st_size,
                    "total_seconds": computational + io,
                    "model_forward_subcomponents_seconds": {
                        k: v - phase_before.get(k, 0.0)
                        for k, v in model.phase_seconds.items()
                    },
                }
            )
        model.record_activations = False
        per_action = max(r["original_action_seconds"] / 4 for r in timing)
        net = max(
            r["network_Adam_seconds"] + 2 * r["checkpoint_IO_seconds"] for r in timing
        )
        non_actions = 384 * net + 120 * net + 14 * action.load_seconds
        forecast = 12000 * per_action + non_actions
        available = self.scope.window.worker_learning_remaining()
        storage_prediction = (
            3 * 7 * max(r["checkpoint_bytes"] for r in timing) + 350 * 2**20
        )
        inventory = inventory_paths(
            [self.scope.ROOT / "benchmarks/artifacts/task042"], self.scope.ROOT
        )
        frozen_plan = self.scope.plan_record()
        storage_ok = storage_prediction + frozen_plan["evidence_reserve_bytes"] <= min(
            frozen_plan["new_storage_bytes"],
            frozen_plan["task_storage_bytes"] - inventory["bytes"],
        )
        forecast_row = {
            "kind": "predicted_from_actual_complete_new_architecture",
            "seconds": forecast,
            "available_seconds": available,
            "verification_reserve_fraction": 0.25,
            "passed": forecast <= 0.75 * available and storage_ok,
            "calibration": timing,
            "per_RHS_original_action_seconds": per_action,
            "training_updates": 384,
            "heldout_states": 40,
            "action_forecast_cap": 12000,
            "model_non_action_IO_and_load_seconds": non_actions,
            "new_storage_prediction_bytes": storage_prediction,
            "task_artifacts_current_bytes": inventory["bytes"],
            "storage_passed": storage_ok,
            "resident_prediction_bytes": 5 * 2**30,
        }
        return {
            "status": "V45_FULL_MOMENT_CALIBRATED",
            "passed": all(c["passed"] for c in checks) and forecast_row["passed"],
            "checks": checks,
            "bucket_inventory": layout,
            "bucket_transpose": transpose,
            "distant_content": distant,
            "initial_parameter_hashes": init_hashes,
            "real_parameters": model.real_parameters,
            "levels": [
                {"buckets": len(row["keys"]), "counts": row["counts"].tolist()}
                for row in model.layout.levels
            ],
            "activation_calibration": model.activation_records,
            "calibration_cost_semantics": "CPU perf_counter inclusive forward/backward; model forward subcomponents are contained, not additive to elapsed. Bucket backward belongs to backward and is not separately instrumented.",
            "budget_forecast": forecast_row,
            "B_chain_reused_unchanged": True,
            "target_allocations": 0,
        }

    def diagnostic(self, folder, budget):
        from benchmarks.check_boundary_witness import read_arrays

        gate, _ = self.scope.stage("CHECK")
        ds, _ = self.scope.stage("DATA")
        bridge, graph, _ = self.graph_packet()
        errors = read_arrays(ds["sealed"]["heldout"])["error"]
        inputs = read_arrays(ds["prefix"]["heldout"])
        from src.solvers.full_moment_hierarchy import BucketLayout

        layout = BucketLayout(graph)
        rows = []
        for code in self.training_codes:
            route = self.scope.stage("EVAL_" + code)[0]
            for row in route["rows"]:
                i = row["sample"]
                values = read_arrays(row["state"])
                canonical_error = bridge.conjugate().T @ (
                    errors[i] - inputs["prefix"][i]
                )
                canonical_delta = bridge.conjugate().T @ values["delta"]
                energies = []
                for level, b in enumerate(layout.levels):
                    for group, indices in enumerate(layout.indices):
                        for bucket in np.unique(b["ids"][indices]):
                            nodes = indices[b["ids"][indices] == bucket]
                            mask = np.concatenate(
                                [
                                    np.arange(layout.offsets[j], layout.offsets[j + 1])
                                    for j in nodes
                                ]
                            )
                            e, d = canonical_error[mask], canonical_delta[mask]
                            inner = np.vdot(e, d)
                            energies.append(
                                {
                                    "level": level,
                                    "group": group,
                                    "bucket": int(bucket),
                                    "moments": len(mask),
                                    "error_energy": float(np.vdot(e, e).real),
                                    "delta_energy": float(np.vdot(d, d).real),
                                    "remaining_energy": float(
                                        np.vdot(e - d, e - d).real
                                    ),
                                    "complex_alignment": [
                                        float(inner.real),
                                        float(inner.imag),
                                    ],
                                }
                            )
                rows.append(
                    {
                        "route": row["route"],
                        "sample": i,
                        "energy_by_complete_moment_bucket": energies,
                    }
                )
        return {
            "status": "FULL_MOMENT_FROZEN_ERROR_DIAGNOSTIC",
            "rows": rows,
            "conclusion": "CLOSE_FIXED_A_FULL_MOMENT_HIERARCHY_QUALIFICATION"
            if all(v == 0 for v in gate["full_pass_by_route"].values())
            else "FINITE_PILOT_ONLY",
            "global_Jacobian_QR_SVD": 0,
            "memory_formula": {
                "complete_real_activation_bytes": "16*batch*(6*Nedge+60*Nface+450*Ncell)",
                "encoder_decoder_flops_per_entity": "proportional to (2*m)^2",
                "parameters": 1817040,
                "parameter_gradient_Adam_bytes_at_least": 4 * 1817040 * 8,
                "target_allocations": 0,
            },
            "reference_scope": "frozen V45 heldout manufacturing e only, no training after CHECK",
        }


study = FullMomentStudy()


def execute(role, folder, state):
    return study.execute(role, folder, state)
