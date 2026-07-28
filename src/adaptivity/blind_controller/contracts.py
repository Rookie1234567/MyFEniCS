"""Typed current-cycle observables accepted by the blind controller."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping


FIXED_PORTS = ("top", "bottom")
FIXED_M = (0, -1, -2, -3, -4, -5, -6, -7)
FIXED_N = 0
FIXED_ORDER_KEYS = tuple(
    (port, m, FIXED_N)
    for port in FIXED_PORTS
    for m in FIXED_M
)

# The order inventory remains a separately named 48-real-goal contract.  Cross
# polarization stays in OrderDatum as a diagnostic and is intentionally not a
# formal stopping goal.
ORDER_GOAL_IDS = tuple(
    f"{port}:m{m}:n{n}:{quantity}"
    for port, m, n in FIXED_ORDER_KEYS
    for quantity in ("power", "co_amp_real", "co_amp_imag")
)
FIXED_GOAL_IDS = ORDER_GOAL_IDS

FORMAL_TOTAL_NAMES = (
    "R00_total",
    "R_total",
    "T_total",
    "A_closure",
    "A_volume",
)
FORMAL_TOTAL_GOAL_IDS = tuple(
    f"scalar/{name}" for name in FORMAL_TOTAL_NAMES
)

# These names are frozen at controller construction time and use values
# normalized without a hidden reference.  The scalar L2 norms and complex
# probes therefore all have dimensionless "controller-normalized field" units.
FORMAL_FIELD_SCALAR_NAMES = (
    "interface_probe_l2",
    "volume_probe_l2",
)
FORMAL_FIELD_COMPLEX_NAMES = (
    "interface_probe_complex",
    "volume_probe_complex",
)
FORMAL_FIELD_GOAL_IDS = (
    *(f"scalar/{name}" for name in FORMAL_FIELD_SCALAR_NAMES),
    *(
        f"complex/{name}/{component}"
        for name in FORMAL_FIELD_COMPLEX_NAMES
        for component in ("real", "imag")
    ),
)
FORMAL_GOAL_IDS = (
    *ORDER_GOAL_IDS,
    *FORMAL_TOTAL_GOAL_IDS,
    *FORMAL_FIELD_GOAL_IDS,
)

ORDER_GOAL_INVENTORY_SHA256 = hashlib.sha256(
    json.dumps(ORDER_GOAL_IDS, separators=(",", ":")).encode("ascii")
).hexdigest()
FORMAL_GOAL_INVENTORY_SHA256 = hashlib.sha256(
    json.dumps(FORMAL_GOAL_IDS, separators=(",", ":")).encode("ascii")
).hexdigest()
# This legacy public name now identifies the inventory used by the controller,
# namely the complete formal inventory rather than only the order subset.
GOAL_INVENTORY_SHA256 = FORMAL_GOAL_INVENTORY_SHA256

FORMAL_GOAL_UNITS = MappingProxyType(
    {
        **{goal_id: "1 (official port normalization)" for goal_id in ORDER_GOAL_IDS},
        **{goal_id: "1 (dimensionless power balance)" for goal_id in FORMAL_TOTAL_GOAL_IDS},
        **{
            goal_id: "1 (frozen reference-free controller field normalization)"
            for goal_id in FORMAL_FIELD_GOAL_IDS
        },
    }
)
FIELD_BLIND_SCALE_NOTE = (
    "Field values are normalized by a scale frozen from the blind current "
    "solve, without any evaluator target value. Interface and volume field "
    "goals use 1% and 1.5% of that normalized scale, respectively."
)


def _finite(value: float, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _sha256(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ComplexDatum:
    """JSON-safe complex datum."""

    real: float
    imag: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "real", _finite(self.real, label="real"))
        object.__setattr__(self, "imag", _finite(self.imag, label="imag"))

    @classmethod
    def from_complex(cls, value: complex) -> ComplexDatum:
        return cls(float(value.real), float(value.imag))

    def as_complex(self) -> complex:
        return complex(self.real, self.imag)


@dataclass(frozen=True, slots=True)
class OrderDatum:
    """One fixed top/bottom low-order channel from the current solve."""

    port: str
    m: int
    n: int
    propagating: bool
    power: float
    co_amplitude: ComplexDatum
    cross_power: float
    cross_amplitude: ComplexDatum
    kz: ComplexDatum
    admittance: ComplexDatum
    normalization_sha256: str

    def __post_init__(self) -> None:
        identity = (self.port, int(self.m), int(self.n))
        if identity not in FIXED_ORDER_KEYS:
            raise ValueError(f"order is outside the fixed N=8 set: {identity}")
        if not isinstance(self.propagating, bool):
            raise ValueError("propagating must be boolean")
        for name in ("power", "cross_power"):
            value = _finite(getattr(self, name), label=name)
            if value < 0.0:
                raise ValueError(f"{name} must be nonnegative")
            object.__setattr__(self, name, value)
        for name in (
            "co_amplitude",
            "cross_amplitude",
            "kz",
            "admittance",
        ):
            if not isinstance(getattr(self, name), ComplexDatum):
                raise ValueError(f"{name} must use ComplexDatum")
        object.__setattr__(
            self,
            "normalization_sha256",
            _sha256(
                self.normalization_sha256,
                label="normalization_sha256",
            ),
        )

    @property
    def identity(self) -> tuple[str, int, int]:
        return self.port, int(self.m), int(self.n)


@dataclass(frozen=True, slots=True)
class GoalValue:
    """One real goal value in the complete formal blind contract."""

    goal_id: str
    value: float

    def __post_init__(self) -> None:
        if self.goal_id not in FORMAL_GOAL_IDS:
            raise ValueError(f"goal is outside the formal inventory: {self.goal_id}")
        object.__setattr__(
            self,
            "value",
            _finite(self.value, label=f"goal[{self.goal_id}]"),
        )


@dataclass(frozen=True, slots=True)
class GoalVector:
    """Canonical formal goals derived only from the current blind solve."""

    values: tuple[GoalValue, ...]

    def __post_init__(self) -> None:
        if tuple(row.goal_id for row in self.values) != FORMAL_GOAL_IDS:
            raise ValueError(
                "goal vector must exactly match the complete formal inventory"
            )

    @classmethod
    def from_orders(
        cls,
        orders: tuple[OrderDatum, ...],
        *,
        totals: Mapping[str, float],
        field_scalars: Mapping[str, float],
        field_complex: Mapping[str, ComplexDatum | complex],
    ) -> GoalVector:
        """Build the full formal vector; cross-polarized data remain diagnostic."""

        if tuple(row.identity for row in orders) != FIXED_ORDER_KEYS:
            raise ValueError("orders must exactly match the fixed N=8 order")
        if set(totals) != set(FORMAL_TOTAL_NAMES):
            raise ValueError("totals must contain the five formal balance outputs")
        if set(field_scalars) != set(FORMAL_FIELD_SCALAR_NAMES):
            raise ValueError("field scalars do not match the frozen inventory")
        if set(field_complex) != set(FORMAL_FIELD_COMPLEX_NAMES):
            raise ValueError("field probes do not match the frozen inventory")
        values: dict[str, float] = {}
        for row in orders:
            prefix = f"{row.port}:m{row.m}:n{row.n}"
            values[f"{prefix}:power"] = row.power
            values[f"{prefix}:co_amp_real"] = row.co_amplitude.real
            values[f"{prefix}:co_amp_imag"] = row.co_amplitude.imag
        values.update(
            {f"scalar/{name}": float(totals[name]) for name in FORMAL_TOTAL_NAMES}
        )
        values.update(
            {
                f"scalar/{name}": float(field_scalars[name])
                for name in FORMAL_FIELD_SCALAR_NAMES
            }
        )
        for name in FORMAL_FIELD_COMPLEX_NAMES:
            value = field_complex[name]
            datum = (
                value
                if isinstance(value, ComplexDatum)
                else ComplexDatum.from_complex(complex(value))
            )
            values[f"complex/{name}/real"] = datum.real
            values[f"complex/{name}/imag"] = datum.imag
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, float]) -> GoalVector:
        if set(values) != set(FORMAL_GOAL_IDS):
            missing = sorted(set(FORMAL_GOAL_IDS) - set(values))
            extra = sorted(set(values) - set(FORMAL_GOAL_IDS))
            raise ValueError(
                "goal mapping must contain the complete formal inventory; "
                f"missing={missing}, extra={extra}"
            )
        return cls(
            tuple(GoalValue(goal_id, values[goal_id]) for goal_id in FORMAL_GOAL_IDS)
        )

    @property
    def by_id(self) -> Mapping[str, float]:
        return MappingProxyType(
            {row.goal_id: row.value for row in self.values}
        )

    @property
    def sha256(self) -> str:
        return _json_sha256(
            [[row.goal_id, row.value] for row in self.values]
        )


def _complex_pair_magnitude(
    goal_id: str,
    values: Mapping[str, float],
) -> float | None:
    if goal_id.endswith(":co_amp_real") or goal_id.endswith(":co_amp_imag"):
        prefix = goal_id.rsplit(":", 1)[0]
        real_id = f"{prefix}:co_amp_real"
        imag_id = f"{prefix}:co_amp_imag"
    elif goal_id.startswith("complex/") and goal_id.endswith(("/real", "/imag")):
        prefix = goal_id.rsplit("/", 1)[0]
        real_id = f"{prefix}/real"
        imag_id = f"{prefix}/imag"
    else:
        return None
    return math.hypot(float(values[real_id]), float(values[imag_id]))


def blind_tolerance(
    goal_id: str,
    current_values: Mapping[str, float],
    shadow_values: Mapping[str, float],
) -> float:
    """Scale one blind budget without any external reference value.

    Real and imaginary components of a complex quantity deliberately share one
    tolerance computed from the complex magnitude.  This avoids a near-zero
    component being assigned an artificially tiny budget.
    """

    if goal_id not in FORMAL_GOAL_IDS:
        raise ValueError("blind tolerance requires one formal goal")
    current_value = float(current_values[goal_id])
    shadow_value = float(shadow_values[goal_id])
    if goal_id.endswith(":power"):
        scale = max(abs(current_value), abs(shadow_value))
        return max(1.0e-9, 5.0e-4 * scale)
    if goal_id in ORDER_GOAL_IDS:
        current_magnitude = _complex_pair_magnitude(goal_id, current_values)
        shadow_magnitude = _complex_pair_magnitude(goal_id, shadow_values)
        assert current_magnitude is not None and shadow_magnitude is not None
        return max(
            1.0e-6,
            1.0e-3 * max(current_magnitude, shadow_magnitude),
        )
    if goal_id in FORMAL_TOTAL_GOAL_IDS:
        scale = max(abs(current_value), abs(shadow_value))
        return max(1.0e-6, 2.0e-4 * scale)
    if goal_id in FORMAL_FIELD_GOAL_IDS:
        paired_current = _complex_pair_magnitude(goal_id, current_values)
        paired_shadow = _complex_pair_magnitude(goal_id, shadow_values)
        scale = max(
            1.0,
            abs(current_value)
            if paired_current is None
            else paired_current,
            abs(shadow_value)
            if paired_shadow is None
            else paired_shadow,
        )
        relative = 0.01 if "interface_" in goal_id else 0.015
        return relative * scale
    raise AssertionError(f"unclassified formal goal: {goal_id}")


def normalized_goal_distance(
    left: GoalVector,
    right: GoalVector,
) -> Mapping[str, float]:
    """Return absolute current-vs-current distances in blind units."""

    result = {}
    left_values = left.by_id
    right_values = right.by_id
    for goal_id in FORMAL_GOAL_IDS:
        result[goal_id] = abs(left_values[goal_id] - right_values[goal_id]) / (
            blind_tolerance(goal_id, left_values, right_values)
        )
    return MappingProxyType(result)


__all__ = [
    "FIELD_BLIND_SCALE_NOTE",
    "FIXED_GOAL_IDS",
    "FIXED_M",
    "FIXED_N",
    "FIXED_ORDER_KEYS",
    "FIXED_PORTS",
    "FORMAL_FIELD_COMPLEX_NAMES",
    "FORMAL_FIELD_GOAL_IDS",
    "FORMAL_FIELD_SCALAR_NAMES",
    "FORMAL_GOAL_IDS",
    "FORMAL_GOAL_INVENTORY_SHA256",
    "FORMAL_GOAL_UNITS",
    "FORMAL_TOTAL_GOAL_IDS",
    "FORMAL_TOTAL_NAMES",
    "GOAL_INVENTORY_SHA256",
    "ORDER_GOAL_IDS",
    "ORDER_GOAL_INVENTORY_SHA256",
    "ComplexDatum",
    "GoalValue",
    "GoalVector",
    "OrderDatum",
    "blind_tolerance",
    "normalized_goal_distance",
]
