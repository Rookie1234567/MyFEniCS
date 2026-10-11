"""One parent import and bounded actual-coordinate witnesses, no reference."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch

from src.io.neural_wave_campaign import ROOT
from src.solvers.ftt_feature_coordinates import FeatureCoordinateCache
from src.solvers.ftt_core_continuation import validate_parent
from src.solvers.ftt_core_training import CoreBoundary
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction, DirectionField, relative_pair,
    output_coefficients, set_output_coefficients,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.optimization_checkpoint import load_checkpoint, restore


def qualify_coordinates(action, packet, design, marker, deadline):
    from src.runners.ftt_width_worker import model_factory
    began = monotonic()
    parent = design["parent_checkpoint"]
    path = ROOT/parent["path"]
    if path.stat().st_size != parent["bytes"]:
        raise ValueError("COORDINATE_PARENT_BYTES_CHANGED")
    state = load_checkpoint(path, parent["sha256"])
    model = model_factory(design, dict(hidden_width=32))
    inherited = validate_parent(state, parent,
        dict(parent["binding"], phase_definition=design["phase_definition"]), model)
    restore(model, CoreBoundary({}), state)
    mapping = FactoredMomentMap(packet)
    raw = StreamingMomentMap(packet)
    c = mapping.forward(model)
    r = action.apply(c)-action.f
    pair = dict(c=relative_pair(c,state["c"]), r=relative_pair(r,state["r"]))
    if max(p["relative"] for p in pair.values()) > 1e-10:
        raise ValueError("COORDINATE_PARENT_FULL_FIELD_MISMATCH")
    saved = deepcopy(model.state_dict())
    rng = np.random.default_rng(design["qualification_seed"])
    witnesses, spectra, failures = [], [], []
    selected_tau = None
    for tau in (1e-6, 1e-4):
        rng = np.random.default_rng(design["qualification_seed"])
        cache = FeatureCoordinateCache(tau)
        trial_witnesses, trial_spectra = [], []
        try:
            for axis in range(3):
                op = ConditionalCoreAction(model,mapping,action,axis,deadline=deadline)
                coordinates = cache.get(model,mapping,axis,op.shape)
                trial_spectra.append(coordinates.record)
                for kind in ("complex_three_components", "pure_imaginary", "bias_three_components"):
                    y = (rng.normal(size=op.shape)+1j*rng.normal(size=op.shape)).astype(complex)
                    if kind == "pure_imaginary":
                        y = 1j*y.imag
                    if kind == "bias_three_components":
                        y[:-1] = 0
                    delta = coordinates.forward(y)
                    scale = np.linalg.norm(delta)
                    y, delta = y.ravel()/scale, delta/scale
                    internal = relative_pair(coordinates.inverse(delta),y)
                    if internal["relative"] > 1e-8:
                        raise ValueError("FEATURE_NUMERICAL_INVERSE_STABILITY_FAILED")
                    dual = (rng.normal(size=action.size)+1j*rng.normal(size=action.size)).astype(complex)
                    kd = op.K(delta)
                    kh = coordinates.adjoint(op.KH(dual))
                    lhs, rhs = np.vdot(kd,dual),np.vdot(y,kh)
                    adj = abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-30)
                    point = raw.forward(DirectionField(model,axis,delta.reshape(op.shape)))
                    independent = relative_pair(kd,point)
                    before = output_coefficients(model,axis)
                    set_output_coefficients(model,axis,before+delta.reshape(op.shape))
                    mapping.invalidate()
                    actual = mapping.forward(model)
                    writeback = relative_pair(actual,c+kd)
                    model.load_state_dict(saved)
                    mapping.invalidate()
                    if max(adj, independent["relative"], writeback["relative"]) > 1e-10:
                        raise ValueError("FEATURE_NUMERICAL_ACTUAL_WRITEBACK_STABILITY_FAILED")
                    trial_witnesses.append(dict(axis=axis,kind=kind,complex_adjoint_relative=float(adj),
                        inverse_pair=internal,independent_point_K_pair=independent,actual_writeback=writeback,
                        coordinate_transform_sha256=coordinates.sha256, delta_norm=float(np.linalg.norm(delta))))
        except ValueError as error:
            model.load_state_dict(saved)
            mapping.invalidate()
            if not str(error).startswith("FEATURE_NUMERICAL_"):
                raise
            failures.append(dict(tau=tau,error=str(error), purpose="stability_only_not_final_field_or_speed_selection",
                                 retained_witnesses=trial_witnesses, spectra=trial_spectra))
            continue
        selected_tau, witnesses, spectra = tau,trial_witnesses,trial_spectra
        break
    if selected_tau is None:
        marker("feature_coordinate_stability_not_qualified",dict(failures=failures))
        raise ValueError("FEATURE_COORDINATES_BOTH_FIXED_STABILITY_STRATEGIES_FAILED")
    dual = (rng.normal(size=action.size)+1j*rng.normal(size=action.size)).astype(complex)
    mapping.vjp(model,dual)
    fd = []
    for axis in range(3):
        p = model.cores[axis][0].bias
        direction = torch.from_numpy(rng.normal(size=p.shape)).to(dtype=torch.float64)
        direction /= torch.linalg.vector_norm(direction)
        analytic = float(torch.dot(p.grad,direction))
        rows = []
        for h in (1e-4,1e-5,1e-6):
            vals=[]
            for sign in (1,-1):
                model.load_state_dict(saved)
                with torch.no_grad():
                    p.add_(sign*h*direction)
                mapping.invalidate()
                vals.append(float(np.vdot(dual,mapping.forward(model)).real))
            numeric=(vals[0]-vals[1])/(2*h)
            rows.append(dict(h=h,analytic=analytic,numeric=numeric,
                relative=abs(analytic-numeric)/max(abs(analytic),abs(numeric),1e-30)))
        if analytic == 0 or min(x["relative"] for x in rows)>1e-5:
            raise ValueError("COORDINATE_NONZERO_HIDDEN_FD_FAILED")
        fd.append(dict(axis=axis, rows=rows))
    model.load_state_dict(saved)
    mapping.invalidate()
    result=dict(qualified=True, selected_tau=selected_tau, failed_stability_attempts=failures,
        parent_checkpoint=parent, parent_import=inherited, parent_c_r_pair=pair,
        parent_model_hash=model_identity(model), all_1377_or_old_wave_columns_used=False,
        feature_spectra=spectra, nonzero_core_witnesses=witnesses, hidden_nonzero_FD=fd,
        original_equation=action.audit(c), reference_read=False, new_training_calls=0,
        global_Maxwell_factor_count=0, global_Gram_factor_count=0, Gsolve_count=0,
        seconds=monotonic()-began, models={"fttnn":dict(qualified=True)})
    marker("feature_coordinates_actual_qualified",result)
    return result
