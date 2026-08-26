"""Bounded same-mesh Basix N1E transfer and local positive-cell audit.

This module is the local structural core for the C1 fallback.  A transfer is
the Basix interpolation map between two N1E polynomial spaces on one
reference hexahedron, with the selected Basix cell transformation applied on
the two sides.  The corresponding scalar-gradient and RT-curl maps are
constructed independently from their DOF functionals.  Only bounded
single-cell arrays are retained; no mesh, MPI, PETSc, global matrix, or
solver is involved here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

import basix
import numpy as np
from scipy.linalg import eigvalsh

from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)


SAME_MESH_METHOD = "same_mesh_hcurl_pmg_v1"
# Public pair convention is (fine_degree, coarse_degree); prolongation runs
# from the second entry to the first.
SAME_MESH_TRANSFER_PAIRS = ((3, 1), (6, 3))
EDGE_LIMIT = 1.0e-11
GRADIENT_LIMIT = 1.0e-11
CURL_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
MATERIAL_HERMITIAN_LIMIT = 1.0e-12
MATERIAL_ENERGY_LIMIT = 1.0e-9


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(np.float64).tiny)
    )


def _n1e(degree: int):
    return basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.legendre,
    )


def _scalar(degree: int):
    return basix.create_element(
        basix.ElementFamily.P,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _rt(degree: int):
    return basix.create_element(
        basix.ElementFamily.RT,
        basix.CellType.hexahedron,
        int(degree),
        basix.LagrangeVariant.equispaced,
    )


def _dof_transform(element: Any, cell_info: int) -> np.ndarray:
    """Materialise Basix's cell transformation without assuming a permutation."""

    cell_info = int(cell_info)
    if cell_info < 0:
        raise ValueError("Basix cell information must be non-negative")
    dimension = int(element.dim)
    data = np.eye(dimension, dtype=np.float64).reshape(-1).copy()
    # With an identity block, ``block_size=dimension`` materialises one
    # transformed column per right-hand side; block_size=1 would only test a
    # single coefficient vector and cannot be reshaped into the operator.
    element.T_apply(data, dimension, cell_info)
    transform = np.ascontiguousarray(data.reshape(dimension, dimension))
    if not np.all(np.isfinite(transform)):
        raise ValueError("Basix cell transformation is non-finite")
    if abs(np.linalg.det(transform)) <= np.finfo(np.float64).tiny:
        raise ValueError("Basix cell transformation is singular")
    transform.setflags(write=False)
    return transform


def _inverse(transform: np.ndarray) -> np.ndarray:
    return np.linalg.inv(np.asarray(transform, dtype=np.float64))


def _dof_functional_interpolation(source: Any, target: Any) -> np.ndarray:
    """Independently apply target DOF functionals to source basis values."""

    if source.map_type != target.map_type:
        raise ValueError("same-mesh N1E maps must have the same Basix map type")
    if tuple(source.value_shape) != tuple(target.value_shape):
        raise ValueError("same-mesh interpolation requires equal value shapes")
    points = np.asarray(target.points, dtype=np.float64)
    values = np.asarray(source.tabulate(0, points))[0]
    value_size = int(np.prod(source.value_shape, dtype=np.int64))
    expected_values = (len(points), int(source.dim), value_size)
    if values.shape != expected_values:
        raise RuntimeError(
            "Basix source tabulation shape changed: "
            f"{values.shape} != {expected_values}"
        )
    function_values = values.transpose(2, 0, 1).reshape(
        len(points) * value_size, int(source.dim)
    )
    interpolation = np.asarray(target.interpolation_matrix)
    expected_interpolation = (int(target.dim), len(points) * value_size)
    if interpolation.shape != expected_interpolation:
        raise RuntimeError(
            "Basix target interpolation shape changed: "
            f"{interpolation.shape} != {expected_interpolation}"
        )
    return np.ascontiguousarray(
        interpolation @ function_values,
        dtype=np.complex128,
    )


def _gradient_functional_map(vector_element: Any, scalar_element: Any) -> np.ndarray:
    points = np.asarray(vector_element.points, dtype=np.float64)
    derivatives = np.asarray(scalar_element.tabulate(1, points))
    gradient_values = np.stack(
        (
            derivatives[1, :, :, 0],
            derivatives[2, :, :, 0],
            derivatives[3, :, :, 0],
        ),
        axis=2,
    )
    values = gradient_values.transpose(2, 0, 1).reshape(
        3 * len(points), int(scalar_element.dim)
    )
    interpolation = np.asarray(vector_element.interpolation_matrix)
    if interpolation.shape != (int(vector_element.dim), 3 * len(points)):
        raise RuntimeError("Basix N1E gradient functional shape is not closed")
    return np.ascontiguousarray(interpolation @ values, dtype=np.complex128)


def _curl_functional_map(vector_element: Any, rt_element: Any) -> np.ndarray:
    points = np.asarray(rt_element.points, dtype=np.float64)
    derivatives = np.asarray(vector_element.tabulate(1, points))
    curls = np.stack(
        (
            derivatives[2, :, :, 2] - derivatives[3, :, :, 1],
            derivatives[3, :, :, 0] - derivatives[1, :, :, 2],
            derivatives[1, :, :, 1] - derivatives[2, :, :, 0],
        ),
        axis=2,
    )
    values = curls.transpose(2, 0, 1).reshape(
        3 * len(points), int(vector_element.dim)
    )
    interpolation = np.asarray(rt_element.interpolation_matrix)
    if interpolation.shape != (int(rt_element.dim), 3 * len(points)):
        raise RuntimeError("Basix RT curl functional shape is not closed")
    return np.ascontiguousarray(interpolation @ values, dtype=np.complex128)


def _element_metadata(element: Any) -> dict[str, object]:
    return {
        "dimension": int(element.dim),
        "map_type": str(element.map_type.name),
        "value_shape": [int(value) for value in element.value_shape],
        "points": int(len(element.points)),
        "dof_ordering": [int(value) for value in element.dof_ordering],
        "entity_dof_counts": [
            [int(len(entity)) for entity in dimension]
            for dimension in element.entity_dofs
        ],
        "dof_transformations_are_identity": bool(
            element.dof_transformations_are_identity
        ),
        "dof_transformations_are_permutations": bool(
            element.dof_transformations_are_permutations
        ),
    }


def _probe_facts(matrix: np.ndarray) -> dict[str, object]:
    columns = int(matrix.shape[1])
    rows = int(matrix.shape[0])
    first = (
        np.arange(1, columns + 1, dtype=np.float64)
        + 1j * np.arange(columns, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    second = (
        np.arange(columns, 2 * columns, dtype=np.float64)
        - 0.5j * np.arange(1, columns + 1, dtype=np.float64)
    ).astype(np.complex128)
    fine = (
        np.arange(1, rows + 1, dtype=np.float64)
        + 0.25j * np.arange(rows, 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    before = first.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = matrix @ first
    repeated = matrix @ first
    second_observed = matrix @ second
    combined = matrix @ (alpha * first + beta * second)
    expected = alpha * observed + beta * second_observed
    adjoint_left = np.vdot(observed, fine)
    adjoint_right = np.vdot(first, matrix.conj().T @ fine)
    return {
        "adjoint_work_relative": float(
            abs(adjoint_left - adjoint_right)
            / max(abs(adjoint_right), np.finfo(np.float64).tiny)
        ),
        "linearity_relative": _relative(combined, expected),
        "repeat_relative": _relative(repeated, observed),
        "input_unchanged": bool(np.array_equal(first, before)),
        "finite": bool(
            np.all(np.isfinite(observed))
            and np.all(np.isfinite(repeated))
            and np.all(np.isfinite(combined))
        ),
    }


def same_mesh_transfer_gate(facts: Mapping[str, Any]) -> dict[str, object]:
    """Apply the fixed local structural gates without defaulting missing facts."""

    failures: list[str] = []
    numeric_names = (
        "edge_functional_relative",
        "gradient_commuting_relative",
        "curl_commuting_relative",
        "adjoint_work_relative",
        "linearity_relative",
        "repeat_relative",
    )
    values: dict[str, float] = {}
    for name in numeric_names:
        value = facts.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name} missing or non-numeric")
        elif not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
        else:
            values[name] = float(value)
    if facts.get("full_column_rank") is not True:
        failures.append("full column rank")
    if facts.get("rank") != facts.get("expected_rank"):
        failures.append("rank")
    if values.get("edge_functional_relative", math.inf) > EDGE_LIMIT:
        failures.append("edge functional")
    if values.get("gradient_commuting_relative", math.inf) > GRADIENT_LIMIT:
        failures.append("gradient commuting")
    if values.get("curl_commuting_relative", math.inf) > CURL_LIMIT:
        failures.append("curl commuting")
    if values.get("adjoint_work_relative", math.inf) > ADJOINT_LIMIT:
        failures.append("adjoint work")
    if values.get("linearity_relative", math.inf) > LINEARITY_LIMIT:
        failures.append("linearity")
    if values.get("repeat_relative", math.inf) > REPEAT_LIMIT:
        failures.append("repeat")
    if facts.get("input_unchanged") is not True:
        failures.append("input unchanged")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


@dataclass(frozen=True)
class SameMeshHcurlTransfer:
    """Immutable bounded transfer between two same-cell Basix N1E spaces."""

    fine_degree: int
    coarse_degree: int
    matrix: np.ndarray
    coarse_cell_info: int
    fine_cell_info: int
    audit: MappingProxyType

    def apply(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[1],):
            raise ValueError("coarse N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix @ vector)

    def apply_adjoint(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self.matrix.shape[0],):
            raise ValueError("fine N1E vector has an unexpected local shape")
        return np.ascontiguousarray(self.matrix.conj().T @ vector)

    def apply_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if vectors.ndim != 2 or vectors.shape[1] != self.matrix.shape[1]:
            raise ValueError("coarse N1E batch has an unexpected local shape")
        return np.ascontiguousarray(vectors @ self.matrix.T)

    def apply_adjoint_many(self, values: np.ndarray) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.complex128)
        if vectors.ndim != 2 or vectors.shape[1] != self.matrix.shape[0]:
            raise ValueError("fine N1E batch has an unexpected local shape")
        return np.ascontiguousarray(vectors @ self.matrix.conj())

    apply_primal = apply


def build_same_mesh_hcurl_transfer(
    fine_degree: int,
    coarse_degree: int,
    *,
    coarse_cell_info: int = 0,
    fine_cell_info: int = 0,
) -> SameMeshHcurlTransfer:
    """Build and independently audit one fixed same-mesh N1E transfer."""

    pair = (int(fine_degree), int(coarse_degree))
    if pair not in SAME_MESH_TRANSFER_PAIRS:
        raise ValueError(
            "same-mesh transfer supports only fine/coarse pairs "
            f"{SAME_MESH_TRANSFER_PAIRS}"
        )
    coarse_element = _n1e(coarse_degree)
    fine_element = _n1e(fine_degree)
    if coarse_element.map_type != fine_element.map_type:
        raise ValueError("same-mesh N1E elements have incompatible map types")
    coarse_transform = _dof_transform(coarse_element, coarse_cell_info)
    fine_transform = _dof_transform(fine_element, fine_cell_info)
    coarse_inverse = _inverse(coarse_transform)
    fine_inverse = _inverse(fine_transform)

    basix_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_element, fine_element),
        dtype=np.complex128,
    )
    expected_shape = (int(fine_element.dim), int(coarse_element.dim))
    if basix_interpolation.shape != expected_shape:
        raise RuntimeError(
            "Basix N1E interpolation shape is not closed: "
            f"{basix_interpolation.shape} != {expected_shape}"
        )
    matrix = np.ascontiguousarray(
        fine_transform @ basix_interpolation @ coarse_inverse,
        dtype=np.complex128,
    )

    direct_reference = _dof_functional_interpolation(
        coarse_element, fine_element
    )
    direct_matrix = np.ascontiguousarray(
        fine_transform @ direct_reference @ coarse_inverse,
        dtype=np.complex128,
    )

    coarse_scalar = _scalar(coarse_degree)
    fine_scalar = _scalar(fine_degree)
    scalar_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_scalar, fine_scalar),
        dtype=np.complex128,
    )
    coarse_scalar_transform = _dof_transform(coarse_scalar, coarse_cell_info)
    fine_scalar_transform = _dof_transform(fine_scalar, fine_cell_info)
    scalar_map = np.ascontiguousarray(
        fine_scalar_transform
        @ scalar_interpolation
        @ _inverse(coarse_scalar_transform),
        dtype=np.complex128,
    )
    coarse_gradient = _gradient_functional_map(coarse_element, coarse_scalar)
    fine_gradient = _gradient_functional_map(fine_element, fine_scalar)
    coarse_gradient = np.ascontiguousarray(
        coarse_transform @ coarse_gradient @ _inverse(coarse_scalar_transform)
    )
    fine_gradient = np.ascontiguousarray(
        fine_transform @ fine_gradient @ _inverse(fine_scalar_transform)
    )

    coarse_rt = _rt(coarse_degree)
    fine_rt = _rt(fine_degree)
    rt_interpolation = np.asarray(
        basix.compute_interpolation_operator(coarse_rt, fine_rt),
        dtype=np.complex128,
    )
    coarse_rt_transform = _dof_transform(coarse_rt, coarse_cell_info)
    fine_rt_transform = _dof_transform(fine_rt, fine_cell_info)
    rt_map = np.ascontiguousarray(
        fine_rt_transform @ rt_interpolation @ _inverse(coarse_rt_transform),
        dtype=np.complex128,
    )
    coarse_curl = _curl_functional_map(coarse_element, coarse_rt)
    fine_curl = _curl_functional_map(fine_element, fine_rt)
    coarse_curl = np.ascontiguousarray(
        coarse_rt_transform @ coarse_curl @ coarse_inverse
    )
    fine_curl = np.ascontiguousarray(
        fine_rt_transform @ fine_curl @ fine_inverse
    )

    singular_values = np.linalg.svd(matrix, compute_uv=False)
    sigma_max = float(singular_values[0])
    sigma_min = float(singular_values[-1])
    rank_threshold = max(matrix.shape) * np.finfo(np.float64).eps * sigma_max
    rank = int(np.count_nonzero(singular_values > rank_threshold))
    probe = _probe_facts(matrix)
    audit: dict[str, object] = {
        "schema": "task038.same_mesh_hcurl_transfer.v1",
        "method": SAME_MESH_METHOD,
        "pair_fine_to_coarse": [int(fine_degree), int(coarse_degree)],
        "fine_degree": int(fine_degree),
        "coarse_degree": int(coarse_degree),
        "shape": [int(value) for value in matrix.shape],
        "rows": int(matrix.shape[0]),
        "cols": int(matrix.shape[1]),
        "rank": rank,
        "expected_rank": int(coarse_element.dim),
        "rank_threshold": float(rank_threshold),
        "sigma_min": sigma_min,
        "sigma_max": sigma_max,
        "full_column_rank": bool(rank == int(coarse_element.dim)),
        "basix_interpolation": True,
        "dof_functional_independent_audit": True,
        "map_type": str(coarse_element.map_type.name),
        "coarse_lagrange_variant": str(coarse_element.lagrange_variant.name),
        "fine_lagrange_variant": str(fine_element.lagrange_variant.name),
        "coarse_cell_info": int(coarse_cell_info),
        "fine_cell_info": int(fine_cell_info),
        "orientation_transform": "basix_FiniteElement_T_apply",
        "coarse_orientation_relative_identity": _relative(
            coarse_transform, np.eye(int(coarse_element.dim))
        ),
        "fine_orientation_relative_identity": _relative(
            fine_transform, np.eye(int(fine_element.dim))
        ),
        "coarse_element": _element_metadata(coarse_element),
        "fine_element": _element_metadata(fine_element),
        "edge_functional_relative": _relative(matrix, direct_matrix),
        "gradient_commuting_relative": _relative(
            matrix @ coarse_gradient, fine_gradient @ scalar_map
        ),
        "curl_commuting_relative": _relative(
            rt_map @ coarse_curl, fine_curl @ matrix
        ),
        **probe,
        "finite": bool(
            np.all(np.isfinite(matrix))
            and np.all(np.isfinite(direct_matrix))
            and np.all(np.isfinite(coarse_gradient))
            and np.all(np.isfinite(fine_gradient))
            and np.all(np.isfinite(coarse_curl))
            and np.all(np.isfinite(fine_curl))
        ),
        "global_dense_transfer": False,
        "numeric_allgather": False,
    }
    gate = same_mesh_transfer_gate(audit)
    audit["gate_passed"] = bool(gate["passed"])
    audit["gate_failures"] = list(gate["failures"])
    if not gate["passed"]:
        raise RuntimeError(
            "same-mesh H(curl) transfer structural gate failed: "
            + ", ".join(str(value) for value in gate["failures"])
        )
    matrix.setflags(write=False)
    return SameMeshHcurlTransfer(
        int(fine_degree),
        int(coarse_degree),
        matrix,
        int(coarse_cell_info),
        int(fine_cell_info),
        MappingProxyType(audit),
    )


def _hermitian_defect(matrix: np.ndarray) -> float:
    return _relative(matrix, matrix.conj().T)


def same_mesh_material_gate(facts: Mapping[str, Any]) -> dict[str, object]:
    failures: list[str] = []
    for name in (
        "hermitian_defect_coarse",
        "hermitian_defect_galerkin",
        "minimum_eigenvalue_coarse",
        "minimum_eigenvalue_galerkin",
        "galerkin_matrix_relative",
        "rediscretized_energy_relative",
    ):
        value = facts.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{name} missing or non-numeric")
        elif not math.isfinite(float(value)):
            failures.append(f"{name} non-finite")
    if facts.get("strict_spd_coarse") is not True:
        failures.append("coarse strict SPD")
    if facts.get("strict_spd_galerkin") is not True:
        failures.append("Galerkin strict SPD")
    if float(facts.get("hermitian_defect_coarse", math.inf)) > MATERIAL_HERMITIAN_LIMIT:
        failures.append("coarse Hermitian")
    if float(facts.get("hermitian_defect_galerkin", math.inf)) > MATERIAL_HERMITIAN_LIMIT:
        failures.append("Galerkin Hermitian")
    if float(facts.get("minimum_eigenvalue_coarse", -math.inf)) <= 0.0:
        failures.append("coarse SPD minimum")
    if float(facts.get("minimum_eigenvalue_galerkin", -math.inf)) <= 0.0:
        failures.append("Galerkin SPD minimum")
    if float(facts.get("galerkin_matrix_relative", math.inf)) > MATERIAL_ENERGY_LIMIT:
        failures.append("Galerkin energy")
    if float(facts.get("rediscretized_energy_relative", math.inf)) > MATERIAL_ENERGY_LIMIT:
        failures.append("rediscretized energy")
    if facts.get("finite") is not True:
        failures.append("finite")
    return {"passed": not failures, "failures": tuple(failures)}


@dataclass(frozen=True)
class SameMeshMaterialResult:
    """Local positive material audit and bounded retained matrices."""

    audit: MappingProxyType
    retained: MappingProxyType


def build_same_mesh_material_class(
    transfer: SameMeshHcurlTransfer,
    *,
    class_name: str,
    material_role: str,
    widths: tuple[float, float, float] = (1.0, 1.0, 1.0),
    curl_coefficient: float = 1.0,
    mass_coefficient: float = 1.0,
) -> SameMeshMaterialResult:
    """Build independent affine positive matrices for one frozen class."""

    if material_role not in {"air", "grating", "substrate"}:
        raise ValueError("material role must be air, grating, or substrate")
    widths = tuple(float(value) for value in widths)
    if len(widths) != 3 or not all(math.isfinite(value) and value > 0.0 for value in widths):
        raise ValueError("material widths must be three positive finite values")
    curl_coefficient = float(curl_coefficient)
    mass_coefficient = float(mass_coefficient)
    if not math.isfinite(curl_coefficient) or curl_coefficient <= 0.0:
        raise ValueError("curl coefficient must be positive and finite")
    if not math.isfinite(mass_coefficient) or mass_coefficient <= 0.0:
        raise ValueError("mass coefficient must be positive and finite")

    spec = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=curl_coefficient,
        mass_coefficient_by_tag={1: mass_coefficient},
    )
    coarse_element = _n1e(transfer.coarse_degree)
    fine_element = _n1e(transfer.fine_degree)
    coarse_reference = AffineIsotropicMaxwellTensorFactory(
        coarse_element, spec
    ).tensor(tag=1, widths=widths)
    fine_reference = AffineIsotropicMaxwellTensorFactory(
        fine_element, spec
    ).tensor(tag=1, widths=widths)
    coarse_transform = _dof_transform(coarse_element, transfer.coarse_cell_info)
    fine_transform = _dof_transform(fine_element, transfer.fine_cell_info)
    coarse_inverse = _inverse(coarse_transform)
    fine_inverse = _inverse(fine_transform)
    coarse_matrix = np.ascontiguousarray(
        coarse_inverse.conj().T @ coarse_reference @ coarse_inverse
    )
    fine_matrix = np.ascontiguousarray(
        fine_inverse.conj().T @ fine_reference @ fine_inverse
    )
    galerkin = np.ascontiguousarray(transfer.matrix.conj().T @ fine_matrix @ transfer.matrix)
    coarse_eigenvalues = eigvalsh(coarse_matrix, check_finite=True)
    galerkin_eigenvalues = eigvalsh(galerkin, check_finite=True)
    probe = (
        np.arange(coarse_matrix.shape[0], dtype=np.float64) + 1.0
        + 1j * np.arange(coarse_matrix.shape[0], 0, -1, dtype=np.float64)
    ).astype(np.complex128)
    coarse_energy = np.vdot(probe, coarse_matrix @ probe)
    galerkin_energy = np.vdot(probe, galerkin @ probe)
    energy_relative = float(
        abs(galerkin_energy - coarse_energy)
        / max(abs(coarse_energy), np.finfo(np.float64).tiny)
    )
    facts: dict[str, object] = {
        "schema": "task038.same_mesh_hcurl_material.v1",
        "method": SAME_MESH_METHOD,
        "class_name": str(class_name),
        "material_role": material_role,
        "fine_degree": int(transfer.fine_degree),
        "coarse_degree": int(transfer.coarse_degree),
        "widths": [float(value) for value in widths],
        "curl_coefficient": curl_coefficient,
        "mass_coefficient": mass_coefficient,
        "coarse_shape": [int(value) for value in coarse_matrix.shape],
        "galerkin_shape": [int(value) for value in galerkin.shape],
        "hermitian_defect_coarse": _hermitian_defect(coarse_matrix),
        "hermitian_defect_galerkin": _hermitian_defect(galerkin),
        "minimum_eigenvalue_coarse": float(coarse_eigenvalues[0]),
        "minimum_eigenvalue_galerkin": float(galerkin_eigenvalues[0]),
        "strict_spd_coarse": bool(coarse_eigenvalues[0] > 0.0),
        "strict_spd_galerkin": bool(galerkin_eigenvalues[0] > 0.0),
        "galerkin_matrix_relative": _relative(galerkin, coarse_matrix),
        "rediscretized_energy_relative": energy_relative,
        "finite": bool(
            np.all(np.isfinite(coarse_matrix))
            and np.all(np.isfinite(galerkin))
            and np.all(np.isfinite(coarse_eigenvalues))
            and np.all(np.isfinite(galerkin_eigenvalues))
            and np.isfinite(energy_relative)
        ),
        "global_matrix": False,
    }
    gate = same_mesh_material_gate(facts)
    facts["gate_passed"] = bool(gate["passed"])
    facts["gate_failures"] = list(gate["failures"])
    if not gate["passed"]:
        raise RuntimeError(
            "same-mesh material structural gate failed: "
            + ", ".join(str(value) for value in gate["failures"])
        )
    for array in (coarse_matrix, galerkin):
        array.setflags(write=False)
    retained = MappingProxyType(
        {
            "transfer": transfer.matrix,
            "coarse_matrix": coarse_matrix,
            "galerkin_matrix": galerkin,
        }
    )
    return SameMeshMaterialResult(MappingProxyType(facts), retained)


__all__ = [
    "ADJOINT_LIMIT",
    "CURL_LIMIT",
    "EDGE_LIMIT",
    "GRADIENT_LIMIT",
    "LINEARITY_LIMIT",
    "MATERIAL_ENERGY_LIMIT",
    "MATERIAL_HERMITIAN_LIMIT",
    "REPEAT_LIMIT",
    "SAME_MESH_METHOD",
    "SAME_MESH_TRANSFER_PAIRS",
    "SameMeshHcurlTransfer",
    "SameMeshMaterialResult",
    "build_same_mesh_hcurl_transfer",
    "build_same_mesh_material_class",
    "same_mesh_material_gate",
    "same_mesh_transfer_gate",
]
