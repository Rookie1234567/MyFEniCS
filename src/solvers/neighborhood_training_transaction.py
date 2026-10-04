"""Restore one consistent Adam boundary; consumption counters never roll back."""

from src.solvers.neighborhood_residual_models import parameters_hash
from src.solvers.neighborhood_residual_study import assign_model


def restore(model, optimizer, record):
    state = assign_model(model, record["checkpoint"])
    update = state["extra"]["update"]
    if update != record["completed_update"] or not 0 < update < 16:
        raise ValueError("bounded early-Adam repair boundary identity")
    if parameters_hash(model) != record["last_parameter_hash"]:
        raise ValueError("saved complete parameter transaction hash")
    if state["optimizer"] is None:
        raise ValueError("parameters alone cannot resume Adam")
    optimizer.load_state_dict(state["optimizer"])
    if not optimizer.state or any(
        float(s["step"]) != update for s in optimizer.state.values()
    ):
        raise ValueError("Adam parameters and optimizer step boundary mismatch")
    return update


def restore_complete(model, optimizer, record, *, maximum):
    """V45 opt-in: any complete Adam boundary, including late checkpoints.

    The historical early V44 reader above is deliberately unchanged. Calling
    this method requires a new scope's validated code/plan/checkpoint manifest.
    """
    state = assign_model(model, record["checkpoint"])
    update = state["extra"]["update"]
    if update != record["completed_update"] or not 0 < update <= maximum:
        raise ValueError("complete Adam boundary update identity")
    if parameters_hash(model) != record["last_parameter_hash"]:
        raise ValueError("complete Adam parameter hash")
    if state["optimizer"] is None:
        raise ValueError("parameters alone cannot resume Adam")
    optimizer.load_state_dict(state["optimizer"])
    if not optimizer.state or any(
        float(s["step"]) != update for s in optimizer.state.values()
    ):
        raise ValueError("complete Adam optimizer/parameter step mismatch")
    return update
