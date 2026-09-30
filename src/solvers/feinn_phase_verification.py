"""Independent ML reconstruction of V8 frozen states; no reference or solve."""

from pathlib import Path

import numpy as np
import torch

from src.solvers.feinn_phase import make_model
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import assign, parameters, load_moments, paired
from src.solvers.feinn_phase_training import configure, policy
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    atomic_write,
    load_checkpoint,
    parameter_order,
)


def restore_network(design, entry, durable_entry, *, phase, supervised):
    model = make_model(design, phase)
    with np.load(entry["path"], allow_pickle=False) as saved:
        p, c = np.array(saved["parameters"]), np.array(saved["c"])
        if bool(saved["phase"]) != phase:
            raise ValueError("FROZEN_PHASE_IDENTITY_FAILED")
        for key, value in policy(supervised).items():
            if bool(saved[key]) != value:
                raise ValueError("FROZEN_LABEL_BOUNDARY_FAILED")
        assign(model, p)
        for name, buffer in model.named_buffers():
            value = np.array(saved[name])
            if not np.array_equal(value, buffer.detach().numpy()):
                raise ValueError("FIXED_COORDINATE_OR_PHASE_BUFFER_CHANGED")
        if str(saved["durable_checkpoint_sha256"]) != durable_entry["sha256"]:
            raise ValueError("FROZEN_DURABLE_BINDING_FAILED")
    durable = load_checkpoint(durable_entry["path"], durable_entry["sha256"])
    if durable["parameter_order"] != parameter_order(model):
        raise ValueError("DURABLE_PARAMETER_ORDER_CHANGED")
    for name, value in model.state_dict().items():
        if not torch.equal(value, durable["model"][name]):
            raise ValueError("DURABLE_AND_FROZEN_NETWORK_DIFFER")
    if not np.array_equal(c, durable["complete_c"]):
        raise ValueError("DURABLE_AND_FROZEN_FULL_COEFFICIENTS_DIFFER")
    return model, c, durable


def reconstruct(design, qualification, routes, artifact, marker, manifest):
    configure()
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    higher = CompleteMomentMap(
        load_moments(qualification["files"]["moments_next"]["path"])
    )
    rows, files = {}, {}
    for stage, index in routes.items():
        phase = stage.startswith("v8_phase_")
        supervised = stage.endswith("reference_fit")
        model, saved, durable = restore_network(
            design,
            index["files"]["checkpoint"],
            index["files"]["durable_final"],
            phase=phase,
            supervised=supervised,
        )
        c = mapping.forward(model)
        next_c = higher.forward(model)
        reconstruction, quadrature = paired(c, saved), paired(next_c, c)
        if reconstruction["relative"] > 1e-12:
            raise ValueError("PARAMETERS_DO_NOT_GENERATE_FROZEN_FULL_FE_COEFFICIENTS")
        fixed = {}
        adam = next(
            (
                row
                for row in index["result"]["audits"]
                if row["tag"] == "committed_outer" and row["complete_closures"] == 500
            ),
            None,
        )
        if adam is not None:
            checkpoint = adam["checkpoint"]
            path = (
                Path(index["files"]["durable_final"]["path"]).parent
                / checkpoint["name"]
            )
            state = load_checkpoint(path, checkpoint["sha256"])
            if state["metadata"]["counts"]["Adam_updates"] != 500:
                raise ValueError("ADAM500_SHARED_WORK_POINT_CHANGED")
            model.load_state_dict(state["model"], strict=True)
            adam_c = mapping.forward(model)
            identity = paired(adam_c, state["complete_c"])
            if identity["relative"] > 1e-12:
                raise ValueError("ADAM500_PARAMETERS_DO_NOT_GENERATE_FULL_FE")
            fixed["c_Adam500"] = adam_c
        path = Path(artifact) / (stage + "_reconstructed.npz")
        atomic_write(
            path,
            lambda stream: np.savez(
                stream, c=c, c_next=next_c, **fixed, **policy(supervised)
            ),
        )
        files[stage] = path
        rows[stage] = dict(
            parameter_to_saved_c=reconstruction,
            next_quadrature_to_selected=quadrature,
            network_quadrature_degree=qualification["result"][
                "network_quadrature_degree"
            ],
            quadrature_pass=quadrature["relative"] <= 1e-8,
            coefficient_count=len(c),
            frozen_checkpoint=index["files"]["checkpoint"],
            durable_checkpoint=index["files"]["durable_final"],
            final_c_sha256=array_hash(c),
            final_parameters_sha256=array_hash(
                parameters(make_loaded_model(design, durable, phase))
            ),
            Adam500_retained=bool(fixed),
            **policy(supervised),
        )
        marker(
            "independent_parameter_reconstruction",
            dict(
                stage=stage,
                saved_relative=reconstruction["relative"],
                next_q_relative=quadrature["relative"],
                Adam500_retained=bool(fixed),
            ),
        )
    return dict(
        status="V8_FROZEN_NETWORKS_RECONSTRUCTED",
        routes=rows,
        reference_loaded=False,
        Gsolve_count=0,
        A_count=0,
        AH_count=0,
        Gram_factor_created=False,
        Maxwell_factor_created=False,
        source_sha=manifest["source_sha"],
    ), files


def make_loaded_model(design, state, phase):
    model = make_model(design, phase)
    model.load_state_dict(state["model"], strict=True)
    return model
