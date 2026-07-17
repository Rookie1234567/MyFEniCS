"""Generic 2D cross-section QEP infrastructure for Task032 references.

The current shift-invert MUMPS path is validated at the Task032 13.5 nm scale.
Requesting all target modes this way is experimental and is not scalable to the
0.7 nm service target without distributed spectrum slicing or continuation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import ufl
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from petsc4py import PETSc
from slepc4py import SLEPc

from ..common.config_3d import SimulationConfig3D
from ..common.high_order_quadrature import high_order_quadrature_policy
from ..constraints.cross_section_floquet import (
    CrossSectionFloquetConstraints,
    DistributedConstraintTransform,
    build_cross_section_floquet_constraints,
    build_distributed_constraint_transform,
    reduce_matrix_hermitian,
)
from .cross_section_spaces import CrossSectionMesh, CrossSectionSpaces


@dataclass(frozen=True)
class QuadraticBetaOperators:
    """Distributed sparse coefficients of ``K0 + beta K1 + beta^2 K2``."""

    K0: PETSc.Mat
    K1: PETSc.Mat
    K2: PETSc.Mat
    electric_mass: PETSc.Mat
    transform: DistributedConstraintTransform
    constraints: CrossSectionFloquetConstraints
    full_shape: tuple[int, int]
    reduced_shape: tuple[int, int]
    scalar_dtype: str
    field_degree: int
    geometry_degree: int
    coefficient_degree: int
    quadrature_degree: int
    quadrature_policy: str = "2p_plus_2g_plus_c_plus_2"
    formulation: str = "mixed_transverse_N1curl_longitudinal_Lagrange_QEP"
    polynomial_order: int = 2
    leading_coefficient_singular_by_design: bool = True

    def destroy(self) -> None:
        self.K0.destroy()
        self.K1.destroy()
        self.K2.destroy()
        self.electric_mass.destroy()
        self.transform.matrix.destroy()


@dataclass(frozen=True)
class EigenvectorOwnership:
    comm_size: int
    reduced_local_size: int
    reduced_ownership_range: tuple[int, int]
    full_local_size: int
    full_ownership_range: tuple[int, int]
    gathered_to_root: bool = False


@dataclass
class QuadraticBetaMode:
    beta: complex
    right_reduced: PETSc.Vec
    right_full: PETSc.Vec
    polynomial_relative_residual: float
    slepc_relative_error: float
    normalization_kind: str
    normalization_factor: float
    electric_l2_norm_after: float
    ownership: EigenvectorOwnership

    def destroy(self) -> None:
        self.right_reduced.destroy()
        self.right_full.destroy()


@dataclass(frozen=True)
class QuadraticBetaSolveReport:
    solver: str
    problem_type: str
    spectral_transform: str
    target: complex
    requested_modes: int
    converged_modes: int
    iteration_count: int
    convergence_reason: int


def analytic_homogeneous_beta(
    cfg: SimulationConfig3D,
    refractive_index: complex,
    *,
    order_m: int = 0,
    order_n: int = 0,
) -> complex:
    """Return the principal ``+z`` branch for one homogeneous Floquet order."""

    kx_order = complex(cfg.kx) + 2.0 * np.pi * order_m / cfg.period_x
    ky_order = complex(cfg.ky) + 2.0 * np.pi * order_n / cfg.period_y
    beta = complex(
        np.sqrt(
            (cfg.k0 * complex(refractive_index)) ** 2
            - kx_order**2
            - ky_order**2
            + 0j
        )
    )
    # Principal sqrt already has Im(beta)>=0.  At the real-axis branch choose
    # positive phase propagation for the explicitly named +z reference.
    if beta.imag < -1.0e-14 or (
        abs(beta.imag) <= 1.0e-14 and beta.real < 0.0
    ):
        beta = -beta
    return beta


def qep_quadrature_degree(
    *,
    field_degree: int,
    geometry_degree: int,
    coefficient_degree: int,
) -> int:
    """Return the conservative planar high-order QEP quadrature degree.

    The extra two orders preserve the reviewed p=2 value of eight on the
    current linear-geometry, piecewise-constant-material meshes while making
    the p=3/p=4 policy explicit.  Curved production geometry remains outside
    Task033 and must be qualified separately rather than relying on this
    polynomial rule alone.
    """

    return high_order_quadrature_policy(
        field_degree=field_degree,
        geometry_degree=geometry_degree,
        coefficient_degree=coefficient_degree,
    ).selected_degree


def _assemble_unconstrained_matrix(form, *, quadrature_degree: int) -> PETSc.Mat:
    matrix = fem_petsc.assemble_matrix(
        fem.form(
            form,
            form_compiler_options={"quadrature_degree": int(quadrature_degree)},
        ),
        bcs=[],
    )
    matrix.assemble()
    return matrix


def assemble_quadratic_beta_operators(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    quadrature_degree: int | None = None,
    log=None,
) -> QuadraticBetaOperators:
    """Assemble and explicitly Floquet-reduce the mixed Maxwell QEP.

    For ``E(x,y,z) = (Et(x,y), Ez(x,y)) exp(i beta z)`` the strong
    transverse/longitudinal split gives a genuine quadratic polynomial.  The
    beta-squared block acts only on ``Et``; its zero scalar block is physical,
    so the leading matrix is intentionally singular.
    """

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("Task32 QEP requires PETSc complex128 scalar mode.")

    Et, Ez = ufl.TrialFunctions(spaces.mixed)
    Vt, Vz = ufl.TestFunctions(spaces.mixed)
    dx = ufl.Measure("dx", domain=cross_section.mesh)
    mu_inv = complex(1.0 / cfg.mu_r)
    k0_squared = float(cfg.k0**2)
    epsilon_r = cross_section.epsilon_r
    field_degree = max(
        int(spaces.transverse_degree), int(spaces.longitudinal_degree)
    )
    geometry_degree = int(getattr(cross_section.mesh.geometry.cmap, "degree", 1))
    coefficient_degree = int(
        getattr(
            cross_section.epsilon_r.function_space.element.basix_element,
            "degree",
            0,
        )
    )
    recommended_quadrature = qep_quadrature_degree(
        field_degree=field_degree,
        geometry_degree=geometry_degree,
        coefficient_degree=coefficient_degree,
    )
    selected_quadrature = (
        recommended_quadrature
        if quadrature_degree is None
        else int(quadrature_degree)
    )
    if selected_quadrature < recommended_quadrature:
        raise ValueError(
            "QEP quadrature degree cannot be lower than the Task033 policy: "
            f"requested={selected_quadrature}, recommended={recommended_quadrature}."
        )

    a0 = (
        mu_inv * ufl.inner(ufl.curl(Et), ufl.curl(Vt))
        - k0_squared * ufl.inner(epsilon_r * Et, Vt)
        + mu_inv * ufl.inner(ufl.grad(Ez), ufl.grad(Vz))
        - k0_squared * ufl.inner(epsilon_r * Ez, Vz)
    ) * dx
    a1 = (
        1j * mu_inv * ufl.inner(ufl.grad(Ez), Vt)
        - 1j * mu_inv * ufl.inner(Et, ufl.grad(Vz))
    ) * dx
    a2 = mu_inv * ufl.inner(Et, Vt) * dx
    electric_mass = (ufl.inner(Et, Vt) + ufl.inner(Ez, Vz)) * dx

    constraints = build_cross_section_floquet_constraints(
        cross_section,
        spaces,
        kx=complex(cfg.kx),
        ky=complex(cfg.ky),
    )
    if log is not None:
        log("QEP Floquet constraints built")
    transform = build_distributed_constraint_transform(spaces, constraints)
    if log is not None:
        log("QEP distributed constraint transform built")

    full_matrices = []
    for name, form in (
        ("K0", a0),
        ("K1", a1),
        ("K2", a2),
        ("electric_mass", electric_mass),
    ):
        full_matrices.append(
            _assemble_unconstrained_matrix(
                form, quadrature_degree=selected_quadrature
            )
        )
        if log is not None:
            log(f"QEP full {name} assembled")
    try:
        reduced_matrices = []
        transform_h = PETSc.Mat()
        transform.matrix.hermitianTranspose(transform_h)
        try:
            for name, matrix in zip(
                ("K0", "K1", "K2", "electric_mass"), full_matrices
            ):
                reduced_matrices.append(
                    reduce_matrix_hermitian(
                        matrix, transform.matrix, transform_h=transform_h
                    )
                )
                if log is not None:
                    log(f"QEP reduced {name} assembled")
        finally:
            transform_h.destroy()
    finally:
        for matrix in full_matrices:
            matrix.destroy()

    reduced_shape = tuple(map(int, reduced_matrices[0].getSize()))
    if reduced_shape[0] != reduced_shape[1]:
        raise RuntimeError(f"Reduced QEP matrices must be square, got {reduced_shape}.")
    if any(tuple(map(int, matrix.getSize())) != reduced_shape for matrix in reduced_matrices):
        raise RuntimeError("QEP coefficient and normalization matrix shapes differ.")

    return QuadraticBetaOperators(
        K0=reduced_matrices[0],
        K1=reduced_matrices[1],
        K2=reduced_matrices[2],
        electric_mass=reduced_matrices[3],
        transform=transform,
        constraints=constraints,
        full_shape=(transform.full_global_size, transform.full_global_size),
        reduced_shape=reduced_shape,
        scalar_dtype=str(np.dtype(PETSc.ScalarType)),
        field_degree=field_degree,
        geometry_degree=geometry_degree,
        coefficient_degree=coefficient_degree,
        quadrature_degree=selected_quadrature,
    )


def _polynomial_relative_residual(
    operators: QuadraticBetaOperators,
    beta: complex,
    vector: PETSc.Vec,
) -> float:
    residual = operators.K0.createVecLeft()
    work = operators.K0.createVecLeft()
    operators.K0.mult(vector, residual)
    operators.K1.mult(vector, work)
    residual.axpy(beta, work)
    operators.K2.mult(vector, work)
    residual.axpy(beta * beta, work)
    numerator = float(residual.norm(PETSc.NormType.NORM_2))
    vector_norm = float(vector.norm(PETSc.NormType.NORM_2))
    denominator = vector_norm * (
        float(operators.K0.norm(PETSc.NormType.FROBENIUS))
        + abs(beta) * float(operators.K1.norm(PETSc.NormType.FROBENIUS))
        + abs(beta) ** 2 * float(operators.K2.norm(PETSc.NormType.FROBENIUS))
    )
    residual.destroy()
    work.destroy()
    return numerator / max(denominator, 1.0e-30)


def solve_quadratic_beta_modes(
    operators: QuadraticBetaOperators,
    *,
    target: complex,
    requested_modes: int = 8,
    tolerance: float = 1.0e-10,
    max_iterations: int = 500,
) -> tuple[list[QuadraticBetaMode], QuadraticBetaSolveReport]:
    """Solve a target slice with native distributed SLEPc PEP/TOAR."""

    if requested_modes < 1:
        raise ValueError("requested_modes must be positive.")
    comm = operators.K0.comm
    pep = SLEPc.PEP().create(comm=comm)
    pep.setOperators([operators.K0, operators.K1, operators.K2])
    pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
    pep.setType(SLEPc.PEP.Type.TOAR)
    pep.setDimensions(nev=int(requested_modes))
    pep.setTarget(complex(target))
    pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
    pep.setTolerances(tol=float(tolerance), max_it=int(max_iterations))

    spectral_transform = pep.getST()
    spectral_transform.setType(SLEPc.ST.Type.SINVERT)
    ksp = spectral_transform.getKSP()
    ksp.setType(PETSc.KSP.Type.PREONLY)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.LU)
    pc.setFactorSolverType("mumps")
    pep.setFromOptions()
    pep.solve()

    converged = int(pep.getConverged())
    modes: list[QuadraticBetaMode] = []
    for index in range(converged):
        reduced = operators.K0.createVecRight()
        beta = complex(pep.getEigenpair(index, reduced))
        mass_action = operators.electric_mass.createVecLeft()
        operators.electric_mass.mult(reduced, mass_action)
        norm_squared = complex(reduced.dot(mass_action))
        if norm_squared.real <= 0.0 or abs(norm_squared.imag) > 1.0e-9 * max(
            abs(norm_squared.real), 1.0e-30
        ):
            mass_action.destroy()
            reduced.destroy()
            raise RuntimeError(
                f"Electric L2 normalization is not positive-real: {norm_squared!r}."
            )
        norm_before = float(np.sqrt(norm_squared.real))
        reduced.scale(1.0 / norm_before)
        operators.electric_mass.mult(reduced, mass_action)
        norm_after = float(np.sqrt(max(complex(reduced.dot(mass_action)).real, 0.0)))
        mass_action.destroy()
        full = operators.transform.matrix.createVecLeft()
        operators.transform.matrix.mult(reduced, full)
        ownership = EigenvectorOwnership(
            comm_size=comm.size,
            reduced_local_size=int(reduced.getLocalSize()),
            reduced_ownership_range=tuple(map(int, reduced.getOwnershipRange())),
            full_local_size=int(full.getLocalSize()),
            full_ownership_range=tuple(map(int, full.getOwnershipRange())),
        )
        modes.append(
            QuadraticBetaMode(
                beta=beta,
                right_reduced=reduced,
                right_full=full,
                polynomial_relative_residual=_polynomial_relative_residual(
                    operators, beta, reduced
                ),
                slepc_relative_error=float(
                    pep.computeError(index, SLEPc.PEP.ErrorType.RELATIVE)
                ),
                normalization_kind="cross_section_electric_L2",
                normalization_factor=norm_before,
                electric_l2_norm_after=norm_after,
                ownership=ownership,
            )
        )

    modes.sort(key=lambda mode: abs(mode.beta - target))
    if len(modes) > requested_modes:
        extras = modes[requested_modes:]
        modes = modes[:requested_modes]
        for mode in extras:
            mode.destroy()
    report = QuadraticBetaSolveReport(
        solver="SLEPc.PEP/TOAR",
        problem_type="general_quadratic_polynomial",
        spectral_transform="sinvert_with_MUMPS_LU",
        target=complex(target),
        requested_modes=int(requested_modes),
        converged_modes=converged,
        iteration_count=int(pep.getIterationNumber()),
        convergence_reason=int(pep.getConvergedReason()),
    )
    pep.destroy()
    return modes, report
