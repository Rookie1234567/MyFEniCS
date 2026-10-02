"""Frozen actual common-time/work views. No error-based state selection."""

from copy import deepcopy
from pathlib import Path

import numpy as np

from src.solvers.feinn_phase import make_model
from src.solvers.feinn_phase_training import policy
from src.solvers.feinn_validation import parameters
from src.solvers.optimization_checkpoint import (
    atomic_write,
    atomic_json,
    load_checkpoint,
    digest,
)

PILOTS = ("v11_phase_identity_metric", "v11_phase_block_metric")


def selections(routes):
    """Select only predeclared clocks or a shared accepted-update count."""
    pairs = []
    if not all(s in routes for s in PILOTS):
        return pairs
    for t in (1800, 3600, 5400):
        points = [routes[s]["result"]["fixed_time_boundaries"][str(t)] for s in PILOTS]
        if all(p["status"] == "RETAINED" for p in points):
            pairs.append(("TIME", t, points))
    n = min(routes[s]["result"]["new_accepted_outer"] for s in PILOTS)
    if n > 0:
        points = []
        for s in PILOTS:
            r = routes[s]["result"]
            target = r["inherited_accepted_outer"] + n
            row = next(
                (x for x in r["accepted_history"] if x["accepted_outer"] == target),
                None,
            )
            if row is None:
                # Missing earlier recovery history is not replayed.
                return pairs
            audit = next(
                (
                    a
                    for a in r["audits"]
                    if a["checkpoint"]["sha256"] == row["checkpoint"]["sha256"]
                ),
                None,
            )
            if audit is None:
                raise ValueError("COMMON_WORK_PERSISTED_AUDIT_NOT_RETAINED")
            points.append(
                dict(
                    status="RETAINED",
                    new_accepted_updates=n,
                    accepted_outer=target,
                    actual_seconds=row["committed_elapsed_seconds"],
                    audit=audit,
                    state_origin="fsynced complete accepted boundary; selected by count, never reference error",
                )
            )
        pairs.append(("WORK", n, points))
    return pairs


def time_routes(design, routes, artifact):
    result = deepcopy(routes)
    for kind, target, points in selections(routes):
        for stage, point in zip(PILOTS, points):
            original = routes[stage]
            checkpoint = point["audit"]["checkpoint"]
            pt = (
                Path(original["files"]["durable_final"]["path"]).parent
                / checkpoint["name"]
            )
            saved = load_checkpoint(pt, checkpoint["sha256"])
            for k, v in policy(False).items():
                if saved["metadata"][k] is not v:
                    raise ValueError("COMMON_POINT_LABEL_BOUNDARY_CHANGED")
            if (
                kind == "WORK"
                and saved["metadata"]["accepted_outer"] != point["accepted_outer"]
            ):
                raise ValueError("COMMON_WORK_COUNTER_CHANGED")
            model = make_model(design, True)
            model.load_state_dict(saved["model"], strict=True)
            key = stage + "_" + kind.lower() + "_" + str(target)
            npz = Path(artifact) / (key + ".npz")
            atomic_write(
                npz,
                lambda stream: np.savez(
                    stream,
                    parameters=parameters(model),
                    c=saved["complete_c"],
                    phase=True,
                    durable_checkpoint_sha256=checkpoint["sha256"],
                    **{n: b.detach().numpy() for n, b in model.named_buffers()},
                    **policy(False),
                ),
            )
            view = deepcopy(original)
            view["source_sha"] = saved["metadata"]["source_sha"]
            view["result"].update(
                route=original["result"]["route"] + "-" + kind + "-" + str(target),
                counts=saved["metadata"]["counts"],
                audits=[],
                failure=None,
            )
            view["result"][
                "fixed_time_selection" if kind == "TIME" else "fixed_work_selection"
            ] = point
            view["files"]["checkpoint"] = dict(path=str(npz), sha256=digest(npz))
            view["files"]["durable_final"] = dict(
                path=str(pt), sha256=checkpoint["sha256"]
            )
            result[key] = view
    path = Path(artifact) / "time_route_index.json"
    compact = {
        k: dict(
            source_sha=r["source_sha"],
            result={
                n: r["result"].get(n)
                for n in (
                    "route",
                    "phase",
                    "supervised",
                    "counts",
                    "failure",
                    "audits",
                    "fixed_time_selection",
                    "fixed_work_selection",
                )
            },
            files={n: r["files"][n] for n in ("checkpoint", "durable_final")},
        )
        for k, r in result.items()
    }
    atomic_json(path, compact)
    return compact, path
