"""Opt-in physical Bloch carrier; the original FTT and FE equation are unchanged."""

import numpy as np
import torch

from src.solvers.ftt_field import FTTField


from src.common.ftt_bloch_phase import phase_definition

class BlochFTTField(FTTField):
    """Multiply axis cores, including linear increments, by a fixed unit phase."""

    phase_buffer_names = (
        "phase_wavevector", "phase_origin", "phase_sign", "phase_units",
        "phase_mode_identity",
    )

    def __init__(self, bounds, model_kind, phase, seed=4213701):
        super().__init__(bounds, model_kind, seed=seed)
        if (
            phase["coordinate_unit"] != "physical_nm"
            or phase["sign"] != 1
            or not phase["unfolded_incident_wavevector"]
            or phase["wavevector_nm_inverse"][2] != 0
        ):
            raise ValueError("BLOCH_PHYSICAL_PHASE_IDENTITY")
        self.register_buffer("phase_wavevector", torch.tensor(phase["wavevector_nm_inverse"], dtype=torch.float64))
        self.register_buffer("phase_origin", torch.tensor(phase["origin_nm"], dtype=torch.float64))
        # Exact small integer codes stored in FP64 retain the qualified mapping's
        # all-FP64 buffer contract; these immutable identities are not parameters.
        self.register_buffer("phase_sign", torch.tensor(1, dtype=torch.float64))
        self.register_buffer("phase_units", torch.tensor(list(b"physical_nm"), dtype=torch.float64))
        self.register_buffer("phase_mode_identity", torch.tensor(list(bytes.fromhex(phase["mode_manifest_sha256"])), dtype=torch.float64))

    def core_phase(self, axis, normalized):
        physical = normalized.reshape(-1) * self.half_width[axis] + self.center[axis]
        angle = self.phase_wavevector[axis] * (physical - self.phase_origin[axis])
        return torch.exp(1j * angle)

    def core(self, axis, normalized):
        return super().core(axis, normalized) * self.core_phase(axis, normalized)[:, None, None, None]


def make_bloch_field(design, kind):
    phase = phase_definition(design)
    if phase != design["phase_definition"]:
        raise ValueError("BLOCH_FROZEN_PHASE_CONFIG_CHANGED")
    return BlochFTTField(design["model"]["geometry"]["bounds_nm"], kind, phase, seed=design["seed"])


class IndependentPointPhase(torch.nn.Module):
    """Unmodified old FTT point evaluation, followed by explicit physical chi.

    This deliberately does not call BlochFTTField.core or core_phase.
    """

    def __init__(self, model):
        super().__init__()
        bounds = torch.stack((model.center - model.half_width, model.center + model.half_width), 1).numpy()
        self.plain = FTTField(bounds, model.model_kind)
        self.plain.load_state_dict({k: v for k, v in model.state_dict().items() if k not in model.phase_buffer_names}, strict=True)
        self.register_buffer("wavevector", model.phase_wavevector.detach().clone())
        self.register_buffer("origin", model.phase_origin.detach().clone())

    def forward(self, physical_coordinates):
        angle = (physical_coordinates - self.origin) @ self.wavevector
        return self.plain(physical_coordinates) * torch.exp(1j * angle)[:, None]


def scalar_continuation(round_number, native, E, H, previous_native=None):
    """Predeclared research stopping rule, never an accuracy qualification."""
    if not np.isfinite([native, E, H]).all() or min(native, E, H) < 0:
        raise ValueError("BLOCH_VALIDATION_SCALARS_INVALID")
    if round_number == 2:
        return not (native > 0.5 and E > 0.5 and H > 0.5)
    if round_number == 4:
        if previous_native is None or previous_native < 0:
            raise ValueError("BLOCH_TWO_ROUND_HISTORY_REQUIRED")
        return (max(native, E, H) <= 0.1) or (
            native <= previous_native / 2 and max(E, H) <= 0.2
        )
    raise ValueError("BLOCH_UNREGISTERED_SCALAR_CHECKPOINT")


def scalar_checkpoint_pending(position, rounds):
    """A saved round must not skip its unfinished validation after recovery."""
    number = position["complete_rounds"]
    return number in (2, 4) and bool(rounds) and "isolated_validation_scalars" not in rounds[-1]
