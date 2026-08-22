"""Opt-in affine/isotropic Maxwell cell tensors from reference H(curl) Grams.

The Task035b rectangular block uses axis-aligned affine hexahedra, scalar
isotropic materials, no PML, and no divergence penalty.  For that deliberately
narrow operator the physical cell tensor is an exact linear combination of
six reference matrices:

```
M(h) = sum_a det(J) / h_a**2 M_a
K(h) = sum_a h_a**2 / det(J) K_a
A(h, tag) = curl_coefficient K(h) + mass_coefficient[tag] M(h)
```

This path is research-only and fail-closed.  General UFL forms continue to use
their compiled FFCx kernels.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

import basix
import numpy as np


def _finite_complex(value: complex, *, label: str) -> complex:
    scalar = complex(value)
    if not np.isfinite(scalar.real) or not np.isfinite(scalar.imag):
        raise ValueError(f"{label} must be finite")
    return scalar


def _complex_pair(value: complex) -> list[float]:
    scalar = complex(value)
    return [float(scalar.real), float(scalar.imag)]


@dataclass(frozen=True)
class AffineIsotropicMaxwellTensorSpec:
    """Explicit coefficients for the qualified affine Maxwell bilinear form."""

    curl_coefficient: complex
    mass_coefficient_by_tag: Mapping[int, complex]
    quadrature_degree: int | None = None

    def __post_init__(self) -> None:
        curl = _finite_complex(
            self.curl_coefficient,
            label="curl coefficient",
        )
        coefficients: dict[int, complex] = {}
        for raw_tag, raw_value in self.mass_coefficient_by_tag.items():
            tag = int(raw_tag)
            if tag < 0:
                raise ValueError("material tags must be nonnegative")
            if tag in coefficients:
                raise ValueError(f"duplicate material tag {tag}")
            coefficients[tag] = _finite_complex(
                raw_value,
                label=f"mass coefficient for tag {tag}",
            )
        if not coefficients:
            raise ValueError("at least one material coefficient is required")
        degree = (
            None
            if self.quadrature_degree is None
            else int(self.quadrature_degree)
        )
        if degree is not None and degree <= 0:
            raise ValueError("quadrature degree must be positive")
        object.__setattr__(self, "curl_coefficient", curl)
        object.__setattr__(
            self,
            "mass_coefficient_by_tag",
            MappingProxyType(dict(sorted(coefficients.items()))),
        )
        object.__setattr__(self, "quadrature_degree", degree)

    def identity(self, element) -> dict[str, Any]:
        """Return a JSON-safe cache identity bound to the Basix element."""

        quadrature_degree = (
            2 * int(element.embedded_superdegree)
            if self.quadrature_degree is None
            else int(self.quadrature_degree)
        )
        return {
            "schema_version": (
                "task035b.affine-isotropic-maxwell-tensor-spec.v1"
            ),
            "operator": (
                "curl_coefficient*curlcurl_plus_"
                "tag_mass_coefficient*vector_mass"
            ),
            "cell_type": str(element.cell_type.name),
            "map_type": str(element.map_type.name),
            "value_shape": list(element.value_shape),
            "dimension": int(element.dim),
            "element_hash": int(element.hash()),
            "embedded_superdegree": int(
                element.embedded_superdegree
            ),
            "quadrature_degree": quadrature_degree,
            "curl_coefficient": _complex_pair(
                self.curl_coefficient
            ),
            "mass_coefficient_by_tag": {
                str(tag): _complex_pair(value)
                for tag, value in self.mass_coefficient_by_tag.items()
            },
            "axis_aligned_affine_only": True,
            "scalar_isotropic_only": True,
            "pml_supported": False,
            "divergence_penalty_supported": False,
        }


class AffineIsotropicMaxwellTensorFactory:
    """Build six reference Grams once, then combine physical cell classes."""

    def __init__(
        self,
        element,
        spec: AffineIsotropicMaxwellTensorSpec,
    ) -> None:
        started = perf_counter()
        if "hexahedron" not in str(element.cell_type.name).lower():
            raise NotImplementedError(
                "affine reference Grams support hexahedra only"
            )
        if element.map_type != basix.MapType.covariantPiola:
            raise ValueError(
                "affine Maxwell tensor requires covariant Piola H(curl)"
            )
        if tuple(element.value_shape) != (3,):
            raise ValueError(
                "affine Maxwell tensor requires a three-component element"
            )
        if bool(element.discontinuous):
            raise ValueError(
                "affine Maxwell tensor requires a conforming element"
            )
        if np.dtype(element.dtype) != np.dtype(np.float64):
            raise TypeError(
                "affine Maxwell tensor requires a float64 Basix basis"
            )
        identity = spec.identity(element)
        quadrature_degree = int(identity["quadrature_degree"])
        points, weights = basix.make_quadrature(
            element.cell_type,
            quadrature_degree,
            polyset_type=element.polyset_type,
        )
        points = np.asarray(points, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3:
            raise RuntimeError("Basix returned invalid hexahedron quadrature")
        if (
            weights.shape != (len(points),)
            or not np.all(np.isfinite(weights))
        ):
            raise RuntimeError("Basix returned invalid quadrature weights")

        tabulation_started = perf_counter()
        values = np.asarray(element.tabulate(1, points))
        tabulation_seconds = perf_counter() - tabulation_started
        expected = (4, len(points), int(element.dim), 3)
        if values.shape != expected:
            raise RuntimeError(
                "unexpected Basix derivative tabulation shape: "
                f"{values.shape} != {expected}"
            )
        value = values[0]
        derivative_x = values[1]
        derivative_y = values[2]
        derivative_z = values[3]
        curl = np.stack(
            (
                derivative_y[:, :, 2] - derivative_z[:, :, 1],
                derivative_z[:, :, 0] - derivative_x[:, :, 2],
                derivative_x[:, :, 1] - derivative_y[:, :, 0],
            ),
            axis=2,
        )

        gram_started = perf_counter()
        mass_components = tuple(
            np.ascontiguousarray(
                value[:, :, component].T
                @ (
                    weights[:, None]
                    * value[:, :, component]
                )
            )
            for component in range(3)
        )
        curl_components = tuple(
            np.ascontiguousarray(
                curl[:, :, component].T
                @ (
                    weights[:, None]
                    * curl[:, :, component]
                )
            )
            for component in range(3)
        )
        gram_seconds = perf_counter() - gram_started
        for matrix in (*mass_components, *curl_components):
            if (
                matrix.shape != (int(element.dim), int(element.dim))
                or not np.all(np.isfinite(matrix))
            ):
                raise RuntimeError(
                    "reference Gram construction produced invalid data"
                )
            matrix.setflags(write=False)

        identity_bytes = json.dumps(
            identity,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        self.element = element
        self.spec = spec
        self.mass_components = mass_components
        self.curl_components = curl_components
        self.build_seconds = perf_counter() - started
        self.audit = MappingProxyType(
            {
                **identity,
                "status": "affine_isotropic_reference_grams_built",
                "pass": True,
                "identity_sha256": hashlib.sha256(
                    identity_bytes
                ).hexdigest(),
                "quadrature_point_count": int(len(points)),
                "quadrature_weight_sum": float(weights.sum()),
                "tabulation_seconds": float(tabulation_seconds),
                "gram_seconds": float(gram_seconds),
                "total_build_seconds": float(self.build_seconds),
                "reference_component_count": 6,
                "reference_component_bytes": int(
                    sum(
                        matrix.nbytes
                        for matrix in (
                            *mass_components,
                            *curl_components,
                        )
                    )
                ),
                "ordinary_default_changed": False,
            }
        )

    def tensor(
        self,
        *,
        tag: int,
        widths: tuple[float, float, float],
    ) -> np.ndarray:
        """Return one physical axis-aligned affine cell tensor."""

        material_tag = int(tag)
        if material_tag not in self.spec.mass_coefficient_by_tag:
            raise ValueError(
                "affine tensor spec has no mass coefficient for "
                f"material tag {material_tag}"
            )
        h = np.asarray(widths, dtype=np.float64)
        if (
            h.shape != (3,)
            or not np.all(np.isfinite(h))
            or np.any(h <= 0.0)
        ):
            raise ValueError(
                "axis-aligned cell widths must be three positive values"
            )
        determinant = float(np.prod(h))
        curl_weights = h**2 / determinant
        mass_weights = determinant / h**2
        tensor = np.zeros(
            (int(self.element.dim), int(self.element.dim)),
            dtype=np.complex128,
        )
        for component in range(3):
            tensor += (
                self.spec.curl_coefficient
                * float(curl_weights[component])
                * self.curl_components[component]
            )
            tensor += (
                self.spec.mass_coefficient_by_tag[material_tag]
                * float(mass_weights[component])
                * self.mass_components[component]
            )
        return np.ascontiguousarray(tensor)

    def mass_tensor(
        self,
        *,
        tag: int,
        widths: tuple[float, float, float],
    ) -> np.ndarray:
        """Return only the volumetric mass part using this factory's Grams.

        This deliberately reuses the same reference ``mass_components`` as
        :meth:`tensor`; callers do not construct a second six-Gram factory.
        """

        material_tag = int(tag)
        if material_tag not in self.spec.mass_coefficient_by_tag:
            raise ValueError(
                "affine tensor spec has no mass coefficient for "
                f"material tag {material_tag}"
            )
        h = np.asarray(widths, dtype=np.float64)
        if (
            h.shape != (3,)
            or not np.all(np.isfinite(h))
            or np.any(h <= 0.0)
        ):
            raise ValueError(
                "axis-aligned cell widths must be three positive values"
            )
        determinant = float(np.prod(h))
        mass_weights = determinant / h**2
        tensor = np.zeros(
            (int(self.element.dim), int(self.element.dim)),
            dtype=np.complex128,
        )
        for component in range(3):
            tensor += (
                self.spec.mass_coefficient_by_tag[material_tag]
                * float(mass_weights[component])
                * self.mass_components[component]
            )
        return np.ascontiguousarray(tensor)


__all__ = [
    "AffineIsotropicMaxwellTensorFactory",
    "AffineIsotropicMaxwellTensorSpec",
]
