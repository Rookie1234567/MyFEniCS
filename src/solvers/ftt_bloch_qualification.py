"""Independent physical chi, all moment families, and opt-in core qualification."""

from copy import deepcopy
from time import monotonic
import numpy as np
import torch

from src.solvers.ftt_field import FTTField
from src.solvers.ftt_bloch_field import BlochFTTField, IndependentPointPhase, make_bloch_field
from src.solvers.ftt_core_qualification import actual_checks
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_conditional_core import ConditionalCoreAction, relative_pair


class WrongPointPhase:
    def __init__(self, model, error):
        self.exact = IndependentPointPhase(model)
        self.model, self.error = model, error

    def __call__(self, coordinates):
        k, origin = self.exact.wavevector, self.exact.origin
        if self.error == "wrong_sign":
            angle = -(coordinates - origin) @ k
        elif self.error == "wrong_units":
            angle = ((coordinates - origin) / self.model.half_width) @ k
        elif self.error == "folded_kx":
            folded = k.clone()
            period = 2 * float(self.model.half_width[0])
            folded[0] -= round(float(k[0]) * period / (2 * np.pi)) * (2 * np.pi / period)
            angle = (coordinates - origin) @ folded
        else:
            raise ValueError("UNREGISTERED_PHASE_NEGATIVE_CONTROL")
        return self.exact.plain(coordinates) * torch.exp(1j * angle)[:, None]


def actual_bloch_checks(action, packet, design, marker, deadline):
    high_path = design["files"]["moments_q60"]
    from src.io.neural_wave_campaign import ROOT, digest
    from src.runners.ftt_worker import load_arrays

    if digest(ROOT / high_path["path"]) != high_path["sha256"]:
        raise ValueError("BLOCH_QUALIFICATION_HIGH_MOMENTS_HASH")
    high = load_arrays(ROOT / high_path["path"])

    def persist_work(kind, axis, model, c, r):
        from src.solvers.optimization_checkpoint import atomic_write, parameter_order
        target = ROOT / "benchmarks/artifacts/task42extra/v42/v42_bloch_ftt_checks" / f"qualification_work_{kind}_axis{axis}.pt"
        atomic_write(target, lambda stream: torch.save(dict(model=deepcopy(model.state_dict()),
            parameter_order=parameter_order(model), c=c, r=r, kind=kind, axis=axis,
            phase_definition=design["phase_definition"], qualification_only=True,
            production_initialization_allowed=False, reference_used_for_training=False), stream))
        return dict(path=str(target.relative_to(ROOT)), sha256=digest(target))

    core = actual_checks(action, packet, design, marker, deadline,
        model_factory=make_bloch_field, independent_field=IndependentPointPhase, work_persist=persist_work)
    rng = np.random.default_rng(design["qualification_seed"])
    extra = {}
    for kind in ("fttnn", "chebtt"):
        began = monotonic()
        model = make_bloch_field(design, kind)
        model.nonzero_qualification_state(seed=design["qualification_seed"])
        mapping = FactoredMomentMap(packet)
        c = mapping.forward(model)
        old = StreamingMomentMap(packet)
        independent = old.forward(IndependentPointPhase(model))
        c60 = StreamingMomentMap(high).forward(IndependentPointPhase(model))
        complete_batch_pair = relative_pair(c, mapping.forward(model, batch=1))
        qp = relative_pair(c, c60)
        aq = float(np.linalg.norm(action.apply(c60 - c)) / action.bnorm)
        families = {}
        for family in ("edge", "face", "interior"):
            rows = packet["owner_rows"][:, packet[family + "_positions"]]
            rows = rows[rows >= 0]
            families[family] = dict(count=len(rows), norm=float(np.linalg.norm(c[rows])), **relative_pair(c[rows], independent[rows]))
        zero_phase = deepcopy(design["phase_definition"])
        zero_phase["wavevector_nm_inverse"] = [0.0, 0.0, 0.0]
        zero = BlochFTTField(design["model"]["geometry"]["bounds_nm"], kind, zero_phase)
        plain = FTTField(design["model"]["geometry"]["bounds_nm"], kind)
        for m in (zero, plain):
            m.nonzero_qualification_state(seed=design["qualification_seed"])
        cz, cp = mapping.forward(zero), mapping.forward(plain)
        dual = (rng.normal(size=action.size) + 1j * rng.normal(size=action.size)).astype(np.complex128)
        zero_pairs = dict(c=relative_pair(cz, cp),
            original_action=relative_pair(action.apply(cz), action.apply(cp)),
            VJP=relative_pair(mapping.vjp(zero, dual), mapping.vjp(plain, dual)))
        for axis in range(3):
            oz = ConditionalCoreAction(zero, mapping, action, axis, deadline=deadline - 120)
            op = ConditionalCoreAction(plain, mapping, action, axis, deadline=deadline - 120)
            delta = (rng.normal(size=oz.size) + 1j * rng.normal(size=oz.size)).astype(np.complex128)
            zero_pairs[f"K_axis{axis}"] = relative_pair(oz.K(delta), op.K(delta))
            zero_pairs[f"KH_axis{axis}"] = relative_pair(oz.KH(dual), op.KH(dual))
        negatives = {error: relative_pair(c, old.forward(WrongPointPhase(model, error))) for error in ("wrong_sign", "wrong_units", "folded_kx")}
        # The original expanded map supplies every phase, without magnitude cuts.
        a = action.a
        once = action.expand(c).ravel()
        twice = np.zeros_like(once)
        np.add.at(twice, a["erows"], a["evals"] ** 2 * c[a["eids"]])
        negatives["duplicate_MPC"] = relative_pair(once, twice)
        base = deepcopy(model.state_dict())
        before = mapping.forward(model)
        old_identity = model_identity(model)
        with torch.no_grad():
            model.phase_wavevector[0].add_(0.03)
        changed = mapping.forward(model)
        invalidated = model_identity(model) != old_identity and np.linalg.norm(changed - before) > 0
        model.load_state_dict(base)
        restored = relative_pair(before, mapping.forward(model))
        maxima = [v["relative"] for v in families.values()] + [v["relative"] for v in zero_pairs.values()] + [restored["relative"], complete_batch_pair["relative"]]
        good = max(maxima) <= 1e-10 and max(qp["relative"], aq) <= 1e-8 and invalidated and all(v["relative"] > 1e-10 for v in negatives.values())
        extra[kind] = dict(moment_families=families, zero_phase_regression=zero_pairs,
            q30_q60=qp, q30_q60_original_A_load_relative=aq,
            negative_controls=negatives, phase_cache_invalidated=invalidated,
            complete_state_restored=restored, qualified=bool(good),
            complete_batch1_batch8_pair=complete_batch_pair,
            additional_phase_checks_elapsed_seconds=monotonic() - began,
            reference_loaded=False, qualification_not_used_as_initialization=True)
        core["models"][kind]["qualified"] &= bool(good)
        marker("actual_physical_bloch_phase_qualified", dict(kind=kind, **extra[kind]))
    core.update(physical_phase=extra, phase_definition=design["phase_definition"],
        qualified=all(v["qualified"] for v in core["models"].values()),
        production_initialization_allowed=False)
    return core
