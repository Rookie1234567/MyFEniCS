"""After freeze, retain actual common-time model views for independent audit."""

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


def time_routes(design, routes, artifact):
    result = deepcopy(routes)
    stages = ("v11_phase_identity_metric", "v11_phase_block_metric")
    if all(s in routes for s in stages):
        for t in (1800, 3600, 5400):
            selected = [
                routes[s]["result"]["fixed_time_boundaries"][str(t)] for s in stages
            ]
            if not all(r["status"] == "RETAINED" for r in selected):
                continue
            for stage, point in zip(stages, selected):
                original = routes[stage]
                checkpoint = point["audit"]["checkpoint"]
                pt = (
                    Path(original["files"]["durable_final"]["path"]).parent
                    / checkpoint["name"]
                )
                saved = load_checkpoint(pt, checkpoint["sha256"])
                for k, v in policy(False).items():
                    if saved["metadata"][k] is not v:
                        raise ValueError("COMMON_TIME_LABEL_BOUNDARY_CHANGED")
                model = make_model(design, True)
                model.load_state_dict(saved["model"], strict=True)
                key = stage + "_time_" + str(t)
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
                    route=original["result"]["route"] + "-TIME-" + str(t),
                    counts=saved["metadata"]["counts"],
                    audits=[],
                    fixed_time_selection=point,
                    failure=None,
                )
                view["files"]["checkpoint"] = dict(path=str(npz), sha256=digest(npz))
                view["files"]["durable_final"] = dict(
                    path=str(pt), sha256=checkpoint["sha256"]
                )
                result[key] = view
    path = Path(artifact) / "time_route_index.json"
    # Views carry only required identity, not duplicated full histories.
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
                )
            },
            files={n: r["files"][n] for n in ("checkpoint", "durable_final")},
        )
        for k, r in result.items()
    }
    atomic_json(path, compact)
    return compact, path
