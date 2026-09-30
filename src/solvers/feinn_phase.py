"""Fixed known incident phase before full Nedelec moments (ML only)."""

import numpy as np
import torch

from src.solvers.feinn_torch import CoordinateField

K_INC = np.array([1.2564456695248023, 0.0, -0.02193134074032823])
XC = np.array([0.0, 0.0, 3.75])


class PhaseCoordinateField(CoordinateField):
    """Identical trainable parameters; carrier/physical origin are buffers."""

    def __init__(self, bounds, seed=421001, *, k_inc=K_INC, origin=XC):
        super().__init__(bounds, seed)
        self.register_buffer(
            "phase_k_inc", torch.as_tensor(np.array(k_inc), dtype=torch.float64)
        )
        self.register_buffer(
            "phase_origin", torch.as_tensor(np.array(origin), dtype=torch.float64)
        )

    def forward(self, coordinates):
        envelope = super().forward(coordinates)
        argument = (coordinates - self.phase_origin) @ self.phase_k_inc
        phase = torch.complex(torch.cos(argument), torch.sin(argument))
        return phase[:, None] * envelope


def make_model(design, phase):
    kind = PhaseCoordinateField if phase else CoordinateField
    return kind(design["geometry"]["bounds_nm"], design["network"]["seed"])
