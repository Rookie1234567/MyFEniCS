"""Task40 opt-in p6 builder using six shared reference integrals.

The base candidate analyzes the exact FFCx rules and material terms.  This
candidate keeps that contract, but integrates each reference curl/value axis
once and composes the six matrices with each cell's exact affine metric.
"""

from __future__ import annotations

from hashlib import sha256
from time import perf_counter
from typing import Any

import numpy as np

from .task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate


class Task40ReferenceMetricUnsupportedCell(NotImplementedError):
    """Geometry for which the exact diagonal-metric shortcut is inapplicable."""


class Task40ExtraP6ReferenceMetricCandidate(Task39ExtraP6RawTensorCandidate):
    """Exact p6 full-cell matrices from shared reference integrals and metrics."""

    identity = "task40extra_p6_reference_integrals_exact_metric_v1"

    def __init__(self, basix_element: Any, cfg: Any, full_bilinear_form: Any, **kwargs):
        started = perf_counter()
        super().__init__(basix_element, cfg, full_bilinear_form, **kwargs)
        self.form_analysis_initialization_seconds = float(perf_counter() - started)
        self.reference_rules_by_component = self._uniform_component_rules()
        self.reference_templates = {
            component: tuple(
                np.zeros((self.dimension, self.dimension), dtype=np.float64)
                for _axis in range(3)
            )
            for component in ("curl", "mass")
        }
        self.metric_composition_seconds = 0.0
        template_started = perf_counter()
        self._build_reference_templates()
        self.template_initialization_seconds = float(perf_counter() - template_started)
        self.evaluator_initialization_seconds = float(perf_counter() - started)
        self.ffcx_geometry_fallback_count = 0
        self.ffcx_geometry_fallback_seconds = 0.0
        self.ffcx_geometry_fallback_reasons: dict[str, int] = {}

        self.template_unique_backing_bytes = int(
            sum(matrix.nbytes for matrices in self.reference_templates.values() for matrix in matrices)
        )
        self.template_unique_backing_count = len(
            {
                int(matrix.__array_interface__["data"][0])
                for matrices in self.reference_templates.values()
                for matrix in matrices
            }
        )
        if self.template_unique_backing_count != 6:
            raise RuntimeError("the six p6 reference templates must have unique backing")

        max_block = min(
            self.point_block_size,
            max(len(rule.points) for rule in self.reference_rules_by_component.values()),
        )
        n = self.dimension
        itemsize = np.dtype(np.float64).itemsize
        table_bytes = 4 * max_block * n * 3 * itemsize
        curl_bytes = 3 * max_block * n * itemsize
        gram_scratch_bytes = n * n * itemsize
        flat_and_weighted_bytes = 2 * max_block * n * itemsize
        self.template_initialization_workspace_bytes_upper = int(
            table_bytes + curl_bytes + gram_scratch_bytes + flat_and_weighted_bytes
        )
        self.metric_composition_workspace_bytes_upper = int(
            2 * n * n * np.dtype(np.complex128).itemsize
            + 3 * 3 * 2 * itemsize
        )
        self.workspace_bytes_upper = int(
            self.template_unique_backing_bytes
            + max(
                self.template_initialization_workspace_bytes_upper,
                self.metric_composition_workspace_bytes_upper,
            )
        )

    def _uniform_component_rules(self) -> dict[str, Any]:
        """Require one exact point/weight rule per component across all tags."""

        result: dict[str, Any] = {}
        for component in ("curl", "mass"):
            rules = [
                self.rules_by_tag_component[(tag, component)]
                for tag in sorted(self.coefficients_by_tag)
                if (tag, component) in self.rules_by_tag_component
            ]
            if not rules:
                raise NotImplementedError(f"no analyzed p6 {component} rule")
            reference = rules[0]
            if any(
                rule.degree != reference.degree
                or rule.rule != reference.rule
                or not np.array_equal(rule.points, reference.points)
                or not np.array_equal(rule.weights, reference.weights)
                for rule in rules[1:]
            ):
                raise NotImplementedError(
                    f"Task40 reference-metric candidate requires one shared {component} rule"
                )
            result[component] = reference
        return result

    @staticmethod
    def _reference_curl(table: np.ndarray) -> np.ndarray:
        import basix

        d_x, d_y, d_z = (
            basix.index(1, 0, 0),
            basix.index(0, 1, 0),
            basix.index(0, 0, 1),
        )
        curl = np.empty_like(table[0])
        np.subtract(table[d_y, :, :, 2], table[d_z, :, :, 1], out=curl[:, :, 0])
        np.subtract(table[d_z, :, :, 0], table[d_x, :, :, 2], out=curl[:, :, 1])
        np.subtract(table[d_x, :, :, 1], table[d_y, :, :, 0], out=curl[:, :, 2])
        return curl

    def _add_reference_gram(
        self,
        component: str,
        axis: int,
        values: np.ndarray,
        weights: np.ndarray,
    ) -> None:
        flat = np.ascontiguousarray(values, dtype=np.float64)
        weighted = flat * weights[:, None]
        # All six reference tables are real; the test-side conjugation is the
        # identity, so use a nonconjugating transpose without a dense copy.
        gram = flat.T @ weighted
        target = self.reference_templates[component][axis]
        np.add(target, gram, out=target)

    def _integrate_rule(self, rule: Any, components: tuple[str, ...]) -> None:
        for start in range(0, len(rule.points), self.point_block_size):
            stop = min(start + self.point_block_size, len(rule.points))
            table = self.element.tabulate(1, rule.points[start:stop])
            weights = rule.weights[start:stop]
            for component in components:
                values = table[0] if component == "mass" else self._reference_curl(table)
                for axis in range(3):
                    self._add_reference_gram(
                        component,
                        axis,
                        values[:, :, axis],
                        weights,
                    )
                del values
            del table

    def _build_reference_templates(self) -> None:
        curl_rule = self.reference_rules_by_component["curl"]
        mass_rule = self.reference_rules_by_component["mass"]
        same_rule = (
            curl_rule.degree == mass_rule.degree
            and curl_rule.rule == mass_rule.rule
            and np.array_equal(curl_rule.points, mass_rule.points)
            and np.array_equal(curl_rule.weights, mass_rule.weights)
        )
        if same_rule:
            self._integrate_rule(curl_rule, ("curl", "mass"))
        else:
            self._integrate_rule(curl_rule, ("curl",))
            self._integrate_rule(mass_rule, ("mass",))

    @staticmethod
    def _axis_aligned_metrics(
        jacobian: np.ndarray, determinant: float
    ) -> tuple[np.ndarray, np.ndarray]:
        # The supported map is a signed/permuted diagonal map. Inspect every
        # coefficient exactly; do not discard a small nonzero cross metric.
        if not np.all(np.count_nonzero(jacobian, axis=0) == 1) or not np.all(
            np.count_nonzero(jacobian, axis=1) == 1
        ):
            raise Task40ReferenceMetricUnsupportedCell(
                "reference-metric shortcut requires exactly axis-aligned cell geometry"
            )
        reference_axis_scales = np.sqrt(np.sum(jacobian * jacobian, axis=0))
        if np.any(reference_axis_scales == 0.0):
            raise Task40ReferenceMetricUnsupportedCell(
                "reference-metric shortcut received a zero cell axis"
            )
        measure = abs(determinant)
        curl_metric = reference_axis_scales * reference_axis_scales / measure
        mass_metric = measure / (reference_axis_scales * reference_axis_scales)
        return curl_metric, mass_metric

    def build(self, coordinates: np.ndarray, *, tag: int, dimension: int) -> np.ndarray:
        if int(dimension) != self.dimension:
            raise NotImplementedError("compiled p6 dimension does not match candidate")
        tag = int(tag)
        if tag not in self.coefficients_by_tag:
            raise NotImplementedError(f"unsupported Task40 material tag {tag}")

        started = perf_counter()
        try:
            jacobian, determinant = self._affine_jacobian(coordinates)
        except NotImplementedError as error:
            raise Task40ReferenceMetricUnsupportedCell(str(error)) from error
        curl_metric, mass_metric = self._axis_aligned_metrics(jacobian, determinant)
        curl_coefficient, mass_coefficient = self.coefficients_by_tag[tag]

        # Keep the full complex result and one reusable composition buffer.
        # The complete cell matrix is returned before the existing orientation
        # transform and p6/q4 condensation run downstream.
        result = np.zeros((self.dimension, self.dimension), dtype=np.complex128)
        scaled = np.empty_like(result)
        for axis in range(3):
            np.multiply(
                self.reference_templates["curl"][axis],
                curl_coefficient * curl_metric[axis],
                out=scaled,
            )
            np.add(result, scaled, out=result)
            np.multiply(
                self.reference_templates["mass"][axis],
                mass_coefficient * mass_metric[axis],
                out=scaled,
            )
            np.add(result, scaled, out=result)

        self.metric_composition_seconds += float(perf_counter() - started)
        coordinates_digest = sha256(
            np.ascontiguousarray(coordinates, dtype=np.float64).view(np.uint8)
        ).hexdigest()[:12]
        key = f"tag={tag},coordinates_sha256={coordinates_digest}"
        self.class_seconds[key] = float(perf_counter() - started)
        self.class_count += 1
        return result

    def __call__(
        self,
        compiled_form: Any,
        kernels: dict[int, Any],
        coordinates: np.ndarray,
        *,
        tag: int,
        dimension: int,
    ) -> np.ndarray:
        self.validate_compiled_form(compiled_form, kernels)
        started = perf_counter()
        try:
            return self.build(coordinates, tag=tag, dimension=dimension)
        except Task40ReferenceMetricUnsupportedCell as error:
            # Preserve the original FFCx cell kernel for unsupported geometry;
            # a near-diagonal metric is never silently substituted.
            from .hcurl_assembly_time_condensation import _tabulate_raw_tensor_class

            tensor = _tabulate_raw_tensor_class(
                compiled_form,
                kernels,
                coordinates,
                tag=int(tag),
                dimension=int(dimension),
            )
            elapsed = float(perf_counter() - started)
            self.ffcx_geometry_fallback_seconds += elapsed
            self.ffcx_geometry_fallback_count += 1
            key = str(error)
            self.ffcx_geometry_fallback_reasons[key] = (
                self.ffcx_geometry_fallback_reasons.get(key, 0) + 1
            )
            coords_sha = sha256(
                np.ascontiguousarray(coordinates, dtype=np.float64).view(np.uint8)
            ).hexdigest()[:12]
            self.class_seconds[f"tag={int(tag)},ffcx_fallback_sha256={coords_sha}"] = elapsed
            self.class_count += 1
            return tensor

    def audit(self) -> dict[str, Any]:
        facts = super().audit()
        facts.update(
            {
                "implementation": self.identity,
                "template_strategy": "six real reference-component Gram matrices",
                "template_rule_records": {
                    component: {
                        "degree": int(rule.degree),
                        "rule": str(rule.rule),
                        "point_count": int(len(rule.points)),
                        "points_weights_sha256": rule.sha256,
                    }
                    for component, rule in self.reference_rules_by_component.items()
                },
                "template_initialization_seconds": self.template_initialization_seconds,
                "form_analysis_initialization_seconds": (
                    self.form_analysis_initialization_seconds
                ),
                "evaluator_initialization_seconds": self.evaluator_initialization_seconds,
                "metric_composition_seconds": self.metric_composition_seconds,
                "ffcx_geometry_fallback_count": self.ffcx_geometry_fallback_count,
                "ffcx_geometry_fallback_seconds": self.ffcx_geometry_fallback_seconds,
                "ffcx_geometry_fallback_reasons": dict(
                    self.ffcx_geometry_fallback_reasons
                ),
                "template_unique_backing_count": self.template_unique_backing_count,
                "template_unique_backing_bytes": self.template_unique_backing_bytes,
                "template_initialization_workspace_bytes_upper": (
                    self.template_initialization_workspace_bytes_upper
                ),
                "metric_composition_workspace_bytes_upper": (
                    self.metric_composition_workspace_bytes_upper
                ),
                "metric_contract": {
                    "curl_reference_axis": "diag(J.T @ J / abs(det(J)))",
                    "mass_reference_axis": "diag(abs(det(J)) / reference_axis_length**2)",
                    "requires_exact_signed_permutation_jacobian": True,
                    "complex_material_coefficient_conjugated": False,
                    "orientation_and_condensation": "existing downstream path, after full V build",
                },
                "workspace_bytes_upper": self.workspace_bytes_upper,
            }
        )
        return facts
