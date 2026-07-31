"""Task003 target contracts and training-only channel selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


AGGREGATE_NAMES = ("R_total", "T_total", "A_balance", "A_volume")
COMPONENT_NAMES = ("s", "p")
COMPOSITION_EPSILON = 1.0e-8


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


def aggregate_log_ratios(aggregates: np.ndarray, *, epsilon: float = COMPOSITION_EPSILON
                         ) -> np.ndarray:
    """Map training R/T/A to the frozen two-dimensional composition latent."""

    values = np.asarray(aggregates, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 3:
        raise ValueError("aggregate log-ratios require R/T/A columns")
    r, t, absorption = values[:, 0], values[:, 1], values[:, 2]
    return np.column_stack((np.log((r + epsilon) / (absorption + epsilon)),
                            np.log((t + epsilon) / (absorption + epsilon))))


def aggregate_composition(y: np.ndarray, *, epsilon: float = COMPOSITION_EPSILON
                           ) -> np.ndarray:
    """Recover R/T/A from latent ``(zR,zT)`` using softmax(zR,zT,0)."""

    values = np.asarray(y, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] not in (2, 3):
        raise ValueError("aggregate composition expects two latent log-ratios")
    logits = values[:, :2]
    logits = np.column_stack((logits, np.zeros(len(values), dtype=np.float64)))
    logits -= np.max(logits, axis=1, keepdims=True)
    weights = np.exp(logits)
    weights /= np.sum(weights, axis=1, keepdims=True)
    return np.column_stack((weights, weights[:, 2], weights[:, 2]))


def freeze_power_floor(power: np.ndarray, active: np.ndarray, *, floor_scale: float = 0.01,
                       minimum: float = 1.0e-12) -> float:
    """Freeze one log(P+floor) floor using training rows only."""

    values = np.asarray(power, dtype=np.float64)
    mask = np.asarray(active, dtype=bool)
    positive = values[mask & np.isfinite(values) & (values > 0.0)]
    if positive.size == 0:
        return float(minimum)
    return float(max(minimum, floor_scale * np.min(positive)))


def aggregate_contract() -> dict[str, Any]:
    return {
        "schema_version": "task003.aggregate-target.v1",
        "primary": ["R_total", "T_total", "A_balance"],
        "diagnostic": ["A_volume"],
        "representation": "zR_log_ratio_zT_log_ratio_softmax_zR_zT_0",
        "epsilon": COMPOSITION_EPSILON,
        "reconstruction": "R,T,A nonnegative and R+T+A=1",
    }


def power_contract() -> dict[str, Any]:
    return {
        "schema_version": "task003.fixed-order-power-target.v1",
        "representation": "independent_log_power_plus_training_frozen_floor_then_sidewise_renormalization",
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
