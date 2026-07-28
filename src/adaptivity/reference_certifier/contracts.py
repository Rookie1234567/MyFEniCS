"""Immutable contracts for the Task035e hidden-reference campaign.

This package belongs to the evaluator side of Task035e.  The blind controller
must not import it or receive any object defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral, Real
import re


REFERENCE_POINT_H_NM = (10.0, 7.5, 5.0)
FIXED_ORDER_PORTS = ("top", "bottom")
FIXED_ORDER_M = (0, -1, -2, -3, -4, -5, -6, -7)
FIXED_ORDER_N = 0
FIXED_ORDER_COUNT = len(FIXED_ORDER_PORTS) * len(FIXED_ORDER_M)

REQUIRED_TOTAL_SCALARS = frozenset(
    {
        "R00_s",
        "R00_p",
        "R00_total",
        "R_total",
        "T_total",
        "A_closure",
        "A_volume",
        "energy_closure",
    }
)

SCALAR_CATEGORIES = frozenset(
    {
        "total",
        "diagnostic",
        "interface_field",
        "volume_field",
    }
)
COMPLEX_CATEGORIES = frozenset(
    {
        "diagnostic",
        "interface_field",
        "volume_field",
    }
)

ELEMENT_FAMILY = "Nedelec first-family"
ASSEMBLY_MODE = "full3d_assembly_time_static_condensation"
LINEAR_SOLVER = "direct_mumps"
INCIDENT_POLARIZATION = "S"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class ReferenceContractError(ValueError):
    """Raised when evaluator evidence violates a structural contract."""


def _finite_real(value: Real, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ReferenceContractError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ReferenceContractError(f"{label} must be finite")
    return result


def _nonnegative_real(value: Real, *, label: str) -> float:
    result = _finite_real(value, label=label)
    if result < 0.0:
        raise ReferenceContractError(f"{label} must be nonnegative")
    return result


def _sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ReferenceContractError(
            f"{label} must contain 64 lowercase hexadecimal characters"
        )
    return value


def _source_sha(value: str) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise ReferenceContractError(
            "source_sha must contain 40 or 64 lowercase hexadecimal characters"
        )
    return value


@dataclass(frozen=True, slots=True)
class ComplexValue:
    """JSON-safe immutable representation of one complex value."""

    real: float
    imag: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "real",
            _finite_real(self.real, label="complex.real"),
        )
        object.__setattr__(
            self,
            "imag",
            _finite_real(self.imag, label="complex.imag"),
        )

    @classmethod
    def from_complex(cls, value: complex) -> ComplexValue:
        return cls(real=float(value.real), imag=float(value.imag))

    def as_complex(self) -> complex:
        return complex(self.real, self.imag)


@dataclass(frozen=True, slots=True)
class ScalarObservation:
    """One named real-valued output from an official postprocessor."""

    name: str
    value: float
    category: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ReferenceContractError("scalar observation name must be nonempty")
        if self.category not in SCALAR_CATEGORIES:
            raise ReferenceContractError(
                f"unsupported scalar observation category: {self.category!r}"
            )
        object.__setattr__(
            self,
            "value",
            _finite_real(self.value, label=f"scalar[{self.name}]"),
        )


@dataclass(frozen=True, slots=True)
class ComplexObservation:
    """One named complex-valued output from an official postprocessor."""

    name: str
    value: ComplexValue
    category: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ReferenceContractError("complex observation name must be nonempty")
        if not isinstance(self.value, ComplexValue):
            raise ReferenceContractError(f"complex[{self.name}] must use ComplexValue")
        if self.category not in COMPLEX_CATEGORIES:
            raise ReferenceContractError(
                f"unsupported complex observation category: {self.category!r}"
            )


@dataclass(frozen=True, slots=True)
class DiffractionOrderObservation:
    """One frozen physical diffraction order on one DtN port."""

    port: str
    m: int
    n: int
    propagating: bool
    kz: ComplexValue
    admittance: ComplexValue
    normalization_identity: str
    total_power: float | None
    co_polarized_amplitude: ComplexValue
    cross_polarized_power: float | None
    cross_polarized_amplitude: ComplexValue

    def __post_init__(self) -> None:
        if self.port not in FIXED_ORDER_PORTS:
            raise ReferenceContractError(
                f"unsupported diffraction-order port: {self.port!r}"
            )
        if isinstance(self.m, bool) or not isinstance(self.m, Integral):
            raise ReferenceContractError("diffraction-order m must be integral")
        if isinstance(self.n, bool) or not isinstance(self.n, Integral):
            raise ReferenceContractError("diffraction-order n must be integral")
        object.__setattr__(self, "m", int(self.m))
        object.__setattr__(self, "n", int(self.n))
        if not isinstance(self.propagating, bool):
            raise ReferenceContractError(
                "diffraction-order propagating must be boolean"
            )
        for label, value in (
            ("kz", self.kz),
            ("admittance", self.admittance),
            ("co_polarized_amplitude", self.co_polarized_amplitude),
            ("cross_polarized_amplitude", self.cross_polarized_amplitude),
        ):
            if not isinstance(value, ComplexValue):
                raise ReferenceContractError(
                    f"diffraction-order {label} must use ComplexValue"
                )
        if (
            not isinstance(self.normalization_identity, str)
            or not self.normalization_identity.strip()
        ):
            raise ReferenceContractError("normalization_identity must be nonempty")
        if self.propagating:
            if self.total_power is None or self.cross_polarized_power is None:
                raise ReferenceContractError(
                    "propagating orders require total and cross-polarized power"
                )
            object.__setattr__(
                self,
                "total_power",
                _nonnegative_real(
                    self.total_power,
                    label="diffraction-order total_power",
                ),
            )
            object.__setattr__(
                self,
                "cross_polarized_power",
                _nonnegative_real(
                    self.cross_polarized_power,
                    label="diffraction-order cross_polarized_power",
                ),
            )
        elif self.total_power is not None or self.cross_polarized_power is not None:
            raise ReferenceContractError(
                "evanescent orders cannot be represented as far-field power"
            )

    @property
    def identity(self) -> tuple[str, int, int]:
        return self.port, self.m, self.n


@dataclass(frozen=True, slots=True)
class PhysicalRunIdentity:
    """Identity fields that must agree across all three p6 references."""

    geometry_sha256: str
    material_sha256: str
    incident_sha256: str
    dtn_definition_sha256: str
    postprocessing_sha256: str
    source_sha: str
    element_family: str = ELEMENT_FAMILY
    degree: int = 6
    assembly_mode: str = ASSEMBLY_MODE
    linear_solver: str = LINEAR_SOLVER
    mpi_size: int = 8
    incident_polarization: str = INCIDENT_POLARIZATION

    def __post_init__(self) -> None:
        for field_name in (
            "geometry_sha256",
            "material_sha256",
            "incident_sha256",
            "dtn_definition_sha256",
            "postprocessing_sha256",
        ):
            _sha256(getattr(self, field_name), label=field_name)
        _source_sha(self.source_sha)
        if self.element_family != ELEMENT_FAMILY:
            raise ReferenceContractError(f"element_family must be {ELEMENT_FAMILY!r}")
        if self.degree != 6:
            raise ReferenceContractError("reference degree must be p6")
        if self.assembly_mode != ASSEMBLY_MODE:
            raise ReferenceContractError(f"assembly_mode must be {ASSEMBLY_MODE!r}")
        if self.linear_solver != LINEAR_SOLVER:
            raise ReferenceContractError(f"linear_solver must be {LINEAR_SOLVER!r}")
        if self.mpi_size != 8:
            raise ReferenceContractError("formal reference identity must use MPI8")
        if self.incident_polarization != INCIDENT_POLARIZATION:
            raise ReferenceContractError(
                "formal reference identity must use S polarization"
            )


@dataclass(frozen=True, slots=True)
class RunGateEvidence:
    """Numerical and resource gates for one reference point."""

    completed: bool
    full_explicit_true_residual: float | None
    energy_balance_error: float | None
    closure_volume_error: float | None
    official_postprocessing_passed: bool
    swap_peak_bytes: int
    minimum_memory_headroom_fraction: float | None
    controlled_resource_stop: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.completed, bool):
            raise ReferenceContractError("completed must be boolean")
        if not isinstance(self.official_postprocessing_passed, bool):
            raise ReferenceContractError(
                "official_postprocessing_passed must be boolean"
            )
        if not isinstance(self.controlled_resource_stop, bool):
            raise ReferenceContractError("controlled_resource_stop must be boolean")
        if (
            isinstance(self.swap_peak_bytes, bool)
            or not isinstance(self.swap_peak_bytes, Integral)
            or self.swap_peak_bytes < 0
        ):
            raise ReferenceContractError(
                "swap_peak_bytes must be a nonnegative integer"
            )
        object.__setattr__(self, "swap_peak_bytes", int(self.swap_peak_bytes))
        if self.minimum_memory_headroom_fraction is not None:
            headroom = _finite_real(
                self.minimum_memory_headroom_fraction,
                label="minimum_memory_headroom_fraction",
            )
            if headroom < 0.0 or headroom > 1.0:
                raise ReferenceContractError(
                    "minimum_memory_headroom_fraction must be in [0, 1]"
                )
            object.__setattr__(
                self,
                "minimum_memory_headroom_fraction",
                headroom,
            )
        if self.completed:
            for label, value in (
                (
                    "full_explicit_true_residual",
                    self.full_explicit_true_residual,
                ),
                ("energy_balance_error", self.energy_balance_error),
                ("closure_volume_error", self.closure_volume_error),
            ):
                if value is None:
                    raise ReferenceContractError(f"completed run requires {label}")
                object.__setattr__(
                    self,
                    label,
                    _nonnegative_real(value, label=label),
                )
            if self.controlled_resource_stop:
                raise ReferenceContractError(
                    "a completed run cannot be a controlled resource stop"
                )
        else:
            if self.official_postprocessing_passed:
                raise ReferenceContractError(
                    "incomplete run cannot pass official postprocessing"
                )
            if (
                not isinstance(self.failure_reason, str)
                or not self.failure_reason.strip()
            ):
                raise ReferenceContractError("incomplete run requires a failure_reason")


@dataclass(frozen=True, slots=True)
class ReferenceRunResult:
    """One p6 reference-point result or controlled stop."""

    h_nm: float
    identity: PhysicalRunIdentity
    gate: RunGateEvidence
    evidence_sha256: str
    scalar_observations: tuple[ScalarObservation, ...] = ()
    complex_observations: tuple[ComplexObservation, ...] = ()
    diffraction_orders: tuple[DiffractionOrderObservation, ...] = ()

    def __post_init__(self) -> None:
        h_nm = _finite_real(self.h_nm, label="h_nm")
        if h_nm not in REFERENCE_POINT_H_NM:
            raise ReferenceContractError(f"h_nm must be one of {REFERENCE_POINT_H_NM}")
        object.__setattr__(self, "h_nm", h_nm)
        if not isinstance(self.identity, PhysicalRunIdentity):
            raise ReferenceContractError("identity must use PhysicalRunIdentity")
        if not isinstance(self.gate, RunGateEvidence):
            raise ReferenceContractError("gate must use RunGateEvidence")
        _sha256(self.evidence_sha256, label="evidence_sha256")
        for label, values, expected_type in (
            (
                "scalar_observations",
                self.scalar_observations,
                ScalarObservation,
            ),
            (
                "complex_observations",
                self.complex_observations,
                ComplexObservation,
            ),
            (
                "diffraction_orders",
                self.diffraction_orders,
                DiffractionOrderObservation,
            ),
        ):
            if not isinstance(values, tuple):
                raise ReferenceContractError(f"{label} must be a tuple")
            if not all(isinstance(value, expected_type) for value in values):
                raise ReferenceContractError(f"{label} contains an invalid value")
        scalar_names = [row.name for row in self.scalar_observations]
        complex_names = [row.name for row in self.complex_observations]
        if len(set(scalar_names)) != len(scalar_names):
            raise ReferenceContractError("scalar observation names must be unique")
        if len(set(complex_names)) != len(complex_names):
            raise ReferenceContractError("complex observation names must be unique")
        order_ids = [row.identity for row in self.diffraction_orders]
        if len(set(order_ids)) != len(order_ids):
            raise ReferenceContractError("diffraction-order identities must be unique")


@dataclass(frozen=True, slots=True)
class ReferenceCampaign:
    """The fixed h10/h7.5/h5 evaluator campaign."""

    h10: ReferenceRunResult
    h7p5: ReferenceRunResult
    h5: ReferenceRunResult

    def __post_init__(self) -> None:
        for label, run, expected_h in (
            ("h10", self.h10, 10.0),
            ("h7p5", self.h7p5, 7.5),
            ("h5", self.h5, 5.0),
        ):
            if not isinstance(run, ReferenceRunResult):
                raise ReferenceContractError(f"{label} must use ReferenceRunResult")
            if run.h_nm != expected_h:
                raise ReferenceContractError(f"{label} must carry h_nm={expected_h}")

    @property
    def runs(self) -> tuple[ReferenceRunResult, ...]:
        return self.h10, self.h7p5, self.h5


def fixed_order_inventory() -> tuple[tuple[str, int, int], ...]:
    """Return the immutable N=8 top/bottom order inventory."""

    return tuple(
        (port, m, FIXED_ORDER_N) for port in FIXED_ORDER_PORTS for m in FIXED_ORDER_M
    )


__all__ = [
    "ASSEMBLY_MODE",
    "COMPLEX_CATEGORIES",
    "ComplexObservation",
    "ComplexValue",
    "DiffractionOrderObservation",
    "ELEMENT_FAMILY",
    "FIXED_ORDER_COUNT",
    "FIXED_ORDER_M",
    "FIXED_ORDER_N",
    "FIXED_ORDER_PORTS",
    "INCIDENT_POLARIZATION",
    "LINEAR_SOLVER",
    "PhysicalRunIdentity",
    "REFERENCE_POINT_H_NM",
    "REQUIRED_TOTAL_SCALARS",
    "ReferenceCampaign",
    "ReferenceContractError",
    "ReferenceRunResult",
    "RunGateEvidence",
    "SCALAR_CATEGORIES",
    "ScalarObservation",
    "fixed_order_inventory",
]
