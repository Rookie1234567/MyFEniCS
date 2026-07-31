"""Task003 target contracts and training-only channel selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


AGGREGATE_NAMES = ("R_total", "T_total", "A_balance", "A_volume")
COMPONENT_NAMES = ("s", "p")


@dataclass(frozen=True)
class Channel:
    order_index: int
    side: str
    m: int
    component: str
    maximum_training_power: float
    active_training_count: int

    def key(self) -> str:
        return f"{self.side}:m{self.m}:{self.component}"


def channel_table(order_identity: dict[str, Any], powers: np.ndarray,
                  mask: np.ndarray, *, threshold: float = 1.0e-6) -> list[Channel]:
    """Select primary power channels using training rows only."""

    channels: list[Channel] = []
    for index, order in enumerate(order_identity["axis"]):
        for component_index, component in enumerate(COMPONENT_NAMES):
            active = mask[:, index, component_index]
            values = powers[:, index, component_index]
            maximum = float(np.nanmax(values)) if np.any(active) else 0.0
            if maximum >= threshold:
                channels.append(Channel(
                    order_index=index, side=str(order["side"]), m=int(order["m"]),
                    component=component, maximum_training_power=maximum,
                    active_training_count=int(np.sum(active)),
                ))
    return channels


def aggregate_composition(y: np.ndarray, *, epsilon: float = 1.0e-8) -> np.ndarray:
    """Convert aggregate logits or raw values into R/T/A composition."""

    values = np.asarray(y, dtype=np.float64)
    if values.shape[-1] == 4:
        values = values[..., :3]
    if values.shape[-1] != 3:
        raise ValueError("aggregate composition requires R/T/A columns")
    safe = np.maximum(values, epsilon)
    normalized = safe / np.sum(safe, axis=-1, keepdims=True)
    return normalized


def aggregate_contract() -> dict[str, Any]:
    return {
        "schema_version": "task003.aggregate-target.v1",
        "primary": ["R_total", "T_total", "A_balance"],
        "diagnostic": ["A_volume"],
        "representation": "composition_softmax_with_fixed_epsilon",
        "epsilon": 1.0e-8,
        "reconstruction": "R,T,A nonnegative and R+T+A=1",
    }


def power_contract() -> dict[str, Any]:
    return {
        "schema_version": "task003.fixed-order-power-target.v1",
        "representation": "independent_log1p_power_then_sidewise_renormalization",
        "primary_threshold_training_max": 1.0e-6,
        "inactive_semantics": "null_not_zero",
        "analytic_mask": {
            "wavelength_nm": 13.5,
            "period_x_nm": 50.0,
            "period_y_nm": 25.0,
            "medium_index": 1.0,
            "criterion": "(kx+m*lambda/period_x)^2+(ky+n*lambda/period_y)^2<=n^2",
        },
    }

