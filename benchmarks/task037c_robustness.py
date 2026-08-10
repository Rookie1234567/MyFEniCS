"""Pure contracts for the explicit Task37c robustness profiles.

This module contains no solver, PETSc, MPI launcher, or artifact reader.  It
only validates the small set of profile, mode-identity, comparison, and
resource records consumed by the later Task37c formal stages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import cmath
import math
from typing import Any, Mapping, Sequence


TASK37C_ONLINE_RECORD_SCHEMA = "task037c.hybrid-iterative-online.v1"
TASK37C_QUALIFICATION_SCHEMA = "task037c.robustness-qualification.v1"
TASK37C_PROFILE_ID = "task037c.robustness.grazing1.v1"
TASK37C_GRAZING_DEG = 1.0
TASK37C_THETA_DEG = 89.0
TASK37C_PHI_VALUES = (-5.0, 0.0, 5.0)
TASK37C_POLARIZATION = "s"
TASK37C_FORMAL_MPI = (1, 8)
TASK37C_REQUESTED_MODES = (120, 160)
TASK37C_MAX_IT = 1600
TASK37C_RTOL = 5.0e-9
TASK37C_TRACTION_TOL = 1.0e-8
TASK37C_RSS_PREFERRED_MIB = 6144.0
TASK37C_MPI1_HARD_STOP_MIB = 6144.0
TASK37C_MPI1_PREFERRED_MIB = 1536.0
TASK37C_MPI1_ENGINEERING_MIB = 2048.0


@dataclass(frozen=True)
class Task37cProfile:
    """One of the finite, explicit Task37c configurations."""

    profile_id: str = TASK37C_PROFILE_ID
    record_schema: str = TASK37C_ONLINE_RECORD_SCHEMA
    qualification_schema: str = TASK37C_QUALIFICATION_SCHEMA
    target: str = "hybrid"
    degree: int = 6
    h_nm: float = 10.0
    modal_degree: int = 6
    modal_h_nm: float = 10.0
    wavelength_nm: float = 13.5
    polarization_kind: str = TASK37C_POLARIZATION
    incident_grazing_deg: float = TASK37C_GRAZING_DEG
    incident_phi_deg: float = 0.0
    bottom_interface_nm: float = 10.0
    top_interface_nm: float = 110.0
    requested_modes: int = 120
    candidate_modes: int = 240
    internal_propagation_model: str = "full3d_uniform_cg"
    internal_traction_model: str = "scalar_cg_discrete_derivative"
    operator_identity: str = "exact_monolithic_hybrid_operator"
    solver_path: str = "block-ldu-action-full-solve"
    preconditioner_identity: str = "fixed_whole_endcap_ilu0_plus_dynamic_dtn_woodbury"
    subdomain_count: int = 1
    overlap: float = 0.0
    ilu_level: int = 0
    shift: float = 0.1
    near_degenerate_tolerance: float = 1.0e-6
    block_rotation_tolerance: float = 1.0e-6
    restart: int = 90
    max_it: int = TASK37C_MAX_IT
    rtol: float = TASK37C_RTOL
    initial_guess: str = "zero"
    mpi_size: int = 8
    assembly_backend: str = "assembly_time_static_condensed"


def make_task37c_profile(
    phi_deg: float,
    requested_modes: int,
    mpi_size: int,
) -> Task37cProfile:
    """Build a profile only for the frozen Task37c choice set."""

    phi = float(phi_deg)
    modes = int(requested_modes)
    mpi = int(mpi_size)
    if phi not in TASK37C_PHI_VALUES:
        raise ValueError(f"Task37c phi must be one of {TASK37C_PHI_VALUES}.")
    if modes not in TASK37C_REQUESTED_MODES:
        raise ValueError(
            f"Task37c requested modes must be one of {TASK37C_REQUESTED_MODES}."
        )
    if mpi not in TASK37C_FORMAL_MPI:
        raise ValueError(f"Task37c MPI size must be one of {TASK37C_FORMAL_MPI}.")
    return Task37cProfile(
        incident_phi_deg=phi,
        requested_modes=modes,
        candidate_modes=2 * modes,
        mpi_size=mpi,
    )


def direction_s_phase_audit(
    phi_deg: float,
    *,
    wavelength_nm: float = 13.5,
    period_x_nm: float = 50.0,
    period_y_nm: float = 25.0,
) -> dict[str, Any]:
    """Return the normalized grazing direction, S basis, and Floquet audit."""

    phi = float(phi_deg)
    if phi not in TASK37C_PHI_VALUES:
        raise ValueError("direction audit received an unsupported phi")
    theta = math.radians(TASK37C_THETA_DEG)
    azimuth = math.radians(phi)
    direction = (
        math.sin(theta) * math.cos(azimuth),
        math.sin(theta) * math.sin(azimuth),
        -math.cos(theta),
    )
    s_basis = (-math.sin(azimuth), math.cos(azimuth), 0.0)
    k0 = 2.0 * math.pi / float(wavelength_nm)
    kx = k0 * direction[0]
    ky = k0 * direction[1]
    phase_x = cmath.exp(1j * kx * float(period_x_nm))
    phase_y = cmath.exp(1j * ky * float(period_y_nm))
    direction_norm = math.sqrt(sum(value * value for value in direction))
    basis_norm = math.sqrt(sum(value * value for value in s_basis))
    dot = sum(a * b for a, b in zip(direction, s_basis, strict=True))
    return {
        "theta_deg": TASK37C_THETA_DEG,
        "phi_deg": phi,
        "grazing_deg": TASK37C_GRAZING_DEG,
        "direction": direction,
        "s_basis": s_basis,
        "kx": kx,
        "ky": ky,
        "floquet_phase_x": phase_x,
        "floquet_phase_y": phase_y,
        "direction_unit": math.isclose(direction_norm, 1.0, abs_tol=1.0e-13),
        "s_unit": math.isclose(basis_norm, 1.0, abs_tol=1.0e-13),
        "orthogonal": math.isclose(dot, 0.0, abs_tol=1.0e-13),
        "pass": (
            math.isclose(direction_norm, 1.0, abs_tol=1.0e-13)
            and math.isclose(basis_norm, 1.0, abs_tol=1.0e-13)
            and math.isclose(dot, 0.0, abs_tol=1.0e-13)
        ),
    }


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name not in value:
            raise ValueError(f"mode is missing {name}")
        return value[name]
    if not hasattr(value, name):
        raise ValueError(f"mode is missing {name}")
    return getattr(value, name)


def canonical_mode_key(mode: Any) -> tuple[str, int, int, str]:
    """Return the exact side/order/polarization identity used in records."""

    side = str(_field(mode, "side"))
    m = _field(mode, "m")
    n = _field(mode, "n")
    polarization = str(_field(mode, "polarization"))
    if side not in {"bottom", "top"}:
        raise ValueError("mode side must be bottom or top")
    if isinstance(m, bool) or not isinstance(m, int):
        raise ValueError("mode m must be a Python int")
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("mode n must be a Python int")
    if polarization not in {"s", "p"}:
        raise ValueError("mode polarization must be s or p")
    return side, m, n, polarization


def mode_identity_audit(
    modes: Sequence[Any],
    *,
    expected_count: int | None = None,
) -> dict[str, Any]:
    """Audit dynamic mode count, keys, beta finiteness, and classification."""

    keys = [canonical_mode_key(mode) for mode in modes]
    betas: list[complex] = []
    propagating = 0
    rayleigh = 0
    for mode in modes:
        beta = complex(_field(mode, "beta"))
        betas.append(beta)
        propagating += int(bool(_field(mode, "propagating")))
        rayleigh += int(bool(_field(mode, "rayleigh_warning")))
    beta_finite = all(
        math.isfinite(beta.real) and math.isfinite(beta.imag) for beta in betas
    )
    count = len(keys)
    return {
        "count": count,
        "expected_count": expected_count,
        "keys": keys,
        "keys_unique": len(set(keys)) == count,
        "beta_finite": beta_finite,
        "propagating_count": propagating,
        "rayleigh_warning_count": rayleigh,
        "pass": (
            count > 0
            and (expected_count is None or count == int(expected_count))
            and len(set(keys)) == count
            and beta_finite
        ),
    }


def choose_m_robust(
    m120_results: Sequence[Mapping[str, Any]],
    m160_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the finite M120/M160 selection rule without inventing a score."""

    expected_phi = set(TASK37C_PHI_VALUES)
    m120_by_phi = {float(row.get("phi_deg")): row for row in m120_results}
    m160_by_phi = {float(row.get("phi_deg")): row for row in m160_results}
    m120_pass = (
        set(m120_by_phi) == expected_phi
        and len(m120_by_phi) == len(m120_results)
        and all(
            row.get("direct_pass") is True
            and row.get("m120_vs_m160_pass") is True
            and row.get("full3d_pass") is True
            for row in m120_by_phi.values()
        )
    )
    m160_pass = (
        set(m160_by_phi) == expected_phi
        and len(m160_by_phi) == len(m160_results)
        and all(
            row.get("direct_pass") is True and row.get("full3d_pass") is True
            for row in m160_by_phi.values()
        )
    )
    if m120_pass:
        selected = 120
    elif m160_pass:
        selected = 160
    else:
        selected = None
    return {
        "m120_pass": m120_pass,
        "m160_pass": m160_pass,
        "selected_m_robust": selected,
        "pass": selected is not None,
    }


def classify_mpi_resource(
    *,
    mpi_size: int,
    numerical_pass: bool,
    rss_mib: float,
    swap_mib: float,
) -> dict[str, Any]:
    """Keep numerical qualification separate from MPI/resource classification."""

    mpi = int(mpi_size)
    rss = float(rss_mib)
    swap = float(swap_mib)
    if mpi not in TASK37C_FORMAL_MPI:
        raise ValueError("unsupported Task37c MPI size")
    finite = math.isfinite(rss) and math.isfinite(swap)
    if mpi == 1:
        hard_stop = not finite or rss >= TASK37C_MPI1_HARD_STOP_MIB or swap > 0.0
        classification = (
            "preferred"
            if finite and rss <= TASK37C_MPI1_PREFERRED_MIB and swap == 0.0
            else "engineering"
            if finite and rss <= TASK37C_MPI1_ENGINEERING_MIB and swap == 0.0
            else "hard_stop"
            if hard_stop
            else "resource_unqualified"
        )
        preferred_pass = classification == "preferred"
    else:
        hard_stop = False
        classification = (
            "preferred"
            if finite and rss <= TASK37C_RSS_PREFERRED_MIB and swap == 0.0
            else "resource_unqualified"
        )
        preferred_pass = classification == "preferred"
    return {
        "mpi_size": mpi,
        "numerical_pass": bool(numerical_pass),
        "rss_mib": rss,
        "swap_mib": swap,
        "preferred_pass": preferred_pass,
        "hard_stop": hard_stop,
        "classification": classification,
    }


def profile_record(profile: Any) -> dict[str, Any]:
    """Return a JSON-ready immutable profile snapshot."""

    return asdict(profile)
