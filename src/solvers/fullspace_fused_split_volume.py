"""Opt-in owner-local fusion of the physical curl and mass volume actions."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
import hashlib
import time
from typing import Any

import numpy as np

from .fullspace_mpc_action import FullspaceMpcFormAction


class FusedIsotropicSplitKernel:
    """Evaluate original curl/mass rules with one gather and coefficient map."""

    def __init__(self, curl_kernel: Any, mass_kernel: Any) -> None:
        if curl_kernel.space is not mass_kernel.space:
            raise ValueError("fused volume kernels must use the same space")
        if curl_kernel.component != "curl" or mass_kernel.component != "mass":
            raise ValueError("fused volume kernels must be curl then mass")
        if not curl_kernel.sum_factorized_work or not mass_kernel.sum_factorized_work:
            raise ValueError("fused volume requires the explicit sum-factorized kernels")
        if curl_kernel.cell_count != mass_kernel.cell_count:
            raise ValueError("fused volume cell counts differ")
        for name in ("dofs", "permutations", "material_indices"):
            if not np.array_equal(getattr(curl_kernel, name), getattr(mass_kernel, name)):
                raise ValueError(f"fused volume {name} identities differ")
        metric_difference = float(
            np.max(np.abs(curl_kernel.metrics - mass_kernel.metrics), initial=0.0)
        )
        metric_scale = max(
            1.0,
            float(np.max(np.abs(curl_kernel.metrics), initial=0.0)),
            float(np.max(np.abs(mass_kernel.metrics), initial=0.0)),
        )
        metric_tolerance = 64 * np.finfo(np.float64).eps * metric_scale
        if not np.isfinite(metric_difference) or metric_difference > metric_tolerance:
            raise ValueError(
                "fused volume geometry metrics differ beyond roundoff: "
                f"{metric_difference:.3e} > {metric_tolerance:.3e}"
            )
        if (
            curl_kernel.basis.mu is not mass_kernel.basis.mu
            or curl_kernel.basis.mass is not mass_kernel.basis.mass
        ):
            raise ValueError("fused volume material owners differ")

        curl_sf = curl_kernel._sum_factorized
        mass_sf = mass_kernel._sum_factorized
        if (
            curl_sf.degree != mass_sf.degree
            or curl_sf.coefficient_matrix.shape != mass_sf.coefficient_matrix.shape
            or hashlib.sha256(curl_sf.coefficient_matrix.tobytes()).digest()
            != hashlib.sha256(mass_sf.coefficient_matrix.tobytes()).digest()
        ):
            raise ValueError("fused volume coefficient transforms differ")

        self.space = curl_kernel.space
        self.curl_kernel = curl_kernel
        self.mass_kernel = mass_kernel
        self.batch_size = min(curl_kernel.batch_size, mass_kernel.batch_size)
        self._local_work = curl_kernel._local_work
        self._materials_work = np.empty((self.batch_size, 2), dtype=np.complex128)

        # These arrays depend only on the common local coefficient transform.
        # The two integral branches retain their own point, weight, metric
        # and field workspaces, even when their quadrature rules differ.
        for name in (
            "_poly",
            "_result",
            "_coefficient_real_work",
            "_coefficient_imag_work",
            "_polynomial_real_work",
            "_polynomial_imag_work",
        ):
            setattr(mass_sf, name, getattr(curl_sf, name))
        mass_kernel._local_work = self._local_work

        metadata_arrays = {}
        for kernel in (curl_kernel, mass_kernel):
            for name in (
                "dofs",
                "permutations",
                "metrics",
                "material_indices",
            ):
                array = getattr(kernel, name, None)
                if isinstance(array, np.ndarray):
                    metadata_arrays[id(array)] = array
        batch_arrays = {id(self._local_work): self._local_work,
                        id(self._materials_work): self._materials_work}
        for sf in (curl_sf, mass_sf):
            for name in (
                "_poly",
                "_values",
                "_curls",
                "_flux",
                "_curl_flux",
                "_derivatives",
                "_poly_result",
                "_result",
                "_projection_first",
                "_projection_second",
                "_projection_result",
                "_coefficient_real_work",
                "_coefficient_imag_work",
                "_polynomial_real_work",
                "_polynomial_imag_work",
                "_x_values",
                "_x_derivatives",
                "_y_values",
                "_y_derivatives",
                "_y_from_x_derivatives",
                "_tensor_evaluation",
            ):
                array = getattr(sf, name, None)
                if isinstance(array, np.ndarray):
                    batch_arrays[id(array)] = array
        unique_batch_bytes = int(sum(array.nbytes for array in batch_arrays.values()))
        unique_metadata_bytes = int(
            sum(array.nbytes for array in metadata_arrays.values())
        )
        self.audit = {
            "schema": "task039extra.fused-isotropic-split-kernel.v1",
            "backend": "sum_factorized_original_component_quadratures",
            "component_count": 2,
            "cell_count": int(curl_kernel.cell_count),
            "batch_size": int(self.batch_size),
            "component_quadrature_identities": {
                "curl": {
                    "degree": curl_kernel.audit["quadrature_degree"],
                    "rule": curl_kernel.audit["quadrature_rule"],
                    "points_sha256": curl_kernel.audit["points_sha256"],
                    "weights_sha256": curl_kernel.audit["weights_sha256"],
                },
                "mass": {
                    "degree": mass_kernel.audit["quadrature_degree"],
                    "rule": mass_kernel.audit["quadrature_rule"],
                    "points_sha256": mass_kernel.audit["points_sha256"],
                    "weights_sha256": mass_kernel.audit["weights_sha256"],
                },
            },
            "distinct_integral_rules_preserved": True,
            "shared_affine_metric_max_difference": metric_difference,
            "shared_affine_metric_roundoff_tolerance": metric_tolerance,
            "shared_coefficient_transform": True,
            "gather_count": 0,
            "direction_forward_count": 0,
            "coefficient_forward_count": 0,
            "curl_integral_count": 0,
            "mass_integral_count": 0,
            "coefficient_backward_count": 0,
            "direction_backward_count": 0,
            "scatter_count": 0,
            "apply_count": 0,
            "full_apply_count": 0,
            "component_apply_count": 0,
            "curl_component_apply_count": 0,
            "mass_component_apply_count": 0,
            "timing_cumulative_seconds": {
                "gather": 0.0,
                "direction_forward": 0.0,
                "coefficient_forward": 0.0,
                "curl_integral": 0.0,
                "mass_integral": 0.0,
                "coefficient_backward": 0.0,
                "direction_backward": 0.0,
                "scatter": 0.0,
                "apply": 0.0,
            },
            "unique_scratch_and_cell_metadata_bytes_not_rss": (
                unique_batch_bytes + unique_metadata_bytes
            ),
            "unique_batch_workspace_bytes": unique_batch_bytes,
            "reference_table_bytes": int(
                curl_kernel.audit["reference_table_bytes"]
                + mass_kernel.audit["reference_table_bytes"]
            ),
            "reference_table_bytes_accounting": (
                "component upper bound; may overlap read-only shared geometry"
            ),
            "cell_metadata_bytes": unique_metadata_bytes,
            "cell_metadata_is_subset_of_reported_unique_array_bytes": True,
            "reported_array_scope": (
                "fixed batch and cell metadata arrays only; reference tables, "
                "material functions and allocator overhead reported separately"
            ),
            "preallocated_batch_workspace_bytes": unique_batch_bytes,
            "temporary_budget_bytes": int(
                curl_kernel.audit["temporary_budget_bytes"]
                + mass_kernel.audit["temporary_budget_bytes"]
            ),
            "ordinary_default_changed": False,
        }
        self._refresh_tensor_contraction_audit()

    def _refresh_tensor_contraction_audit(self) -> None:
        contractions = {}
        for name, kernel in (
            ("curl", self.curl_kernel),
            ("mass", self.mass_kernel),
        ):
            sf = kernel._sum_factorized
            contractions[name] = {
                "shared_contractions_opt_in": bool(sf.shared_contractions),
                "forward_tensor_contraction_counts": dict(
                    sf.audit["forward_tensor_contraction_counts"]
                ),
                "forward_tensor_contraction_count": int(
                    sf.audit["forward_tensor_contraction_count"]
                ),
                "backward_projection_count": int(
                    sf.audit["backward_projection_count"]
                ),
                "backward_tensor_contraction_count": int(
                    sf.audit["backward_tensor_contraction_count"]
                ),
                "timing_cumulative_seconds": dict(sf.timing),
                "timing_scope": (
                    "same-input local tensor evaluation/projection cumulative "
                    "wall time; coefficient transforms and metric products are "
                    "separate"
                ),
            }
        self.audit["tensor_contractions"] = contractions

    def _apply(self, coefficients: np.ndarray, output: np.ndarray, component: str | None) -> None:
        started = time.perf_counter()
        output.fill(0.0)
        curl_kernel, mass_kernel = self.curl_kernel, self.mass_kernel
        element = self.space.element
        for start in range(0, curl_kernel.cell_count, self.batch_size):
            stop = min(start + self.batch_size, curl_kernel.cell_count)
            count = stop - start
            dofs = curl_kernel.dofs[start:stop]
            local = self._local_work[:count]
            phase = time.perf_counter()
            local[...] = coefficients[dofs]
            self.audit["timing_cumulative_seconds"]["gather"] += (
                time.perf_counter() - phase
            )
            self.audit["gather_count"] += 1

            phase = time.perf_counter()
            for row, cell in enumerate(range(start, stop)):
                if element.needs_dof_transformations:
                    element.Tt_apply(
                        local[row].view(np.float64),
                        curl_kernel.permutations[cell : cell + 1],
                        2,
                    )
            self.audit["timing_cumulative_seconds"]["direction_forward"] += (
                time.perf_counter() - phase
            )
            self.audit["direction_forward_count"] += 1

            materials = self._materials_work[:count]
            indices = curl_kernel.material_indices[start:stop]
            materials[:, 0] = curl_kernel.basis.mass.x.array[indices[:, 0]]
            materials[:, 1] = curl_kernel.basis.mu.x.array[indices[:, 1]]
            phase = time.perf_counter()
            polynomial = curl_kernel._sum_factorized._coefficients_to_polynomial(local)
            self.audit["timing_cumulative_seconds"]["coefficient_forward"] += (
                time.perf_counter() - phase
            )
            self.audit["coefficient_forward_count"] += 1

            combined = None
            if component in (None, "curl"):
                phase = time.perf_counter()
                combined = curl_kernel._sum_factorized._integrate_polynomial(
                    polynomial,
                    curl_kernel.metrics[start:stop],
                    materials,
                    component="curl",
                )
                self.audit["timing_cumulative_seconds"]["curl_integral"] += (
                    time.perf_counter() - phase
                )
                self.audit["curl_integral_count"] += 1
            if component in (None, "mass"):
                phase = time.perf_counter()
                mass_result = mass_kernel._sum_factorized._integrate_polynomial(
                    polynomial,
                    mass_kernel.metrics[start:stop],
                    materials,
                    component="mass",
                )
                self.audit["timing_cumulative_seconds"]["mass_integral"] += (
                    time.perf_counter() - phase
                )
                self.audit["mass_integral_count"] += 1
                if combined is None:
                    combined = mass_result
                else:
                    np.add(combined, mass_result, out=combined)

            phase = time.perf_counter()
            result = curl_kernel._sum_factorized._polynomial_to_coefficients(combined)
            self.audit["timing_cumulative_seconds"]["coefficient_backward"] += (
                time.perf_counter() - phase
            )
            self.audit["coefficient_backward_count"] += 1

            phase = time.perf_counter()
            for row, cell in enumerate(range(start, stop)):
                if element.needs_dof_transformations:
                    element.T_apply(
                        result[row].view(np.float64),
                        curl_kernel.permutations[cell : cell + 1],
                        2,
                    )
            self.audit["timing_cumulative_seconds"]["direction_backward"] += (
                time.perf_counter() - phase
            )
            self.audit["direction_backward_count"] += 1

            phase = time.perf_counter()
            np.add.at(output, dofs.ravel(), result.ravel())
            self.audit["timing_cumulative_seconds"]["scatter"] += (
                time.perf_counter() - phase
            )
            self.audit["scatter_count"] += 1
        self.audit["apply_count"] += 1
        if component is None:
            self.audit["full_apply_count"] += 1
        else:
            self.audit["component_apply_count"] += 1
            key = (
                "curl_component_apply_count"
                if component == "curl"
                else "mass_component_apply_count"
            )
            self.audit[key] += 1
        self.audit["timing_cumulative_seconds"]["apply"] += time.perf_counter() - started
        self._refresh_tensor_contraction_audit()

    def apply(self, coefficients: np.ndarray, output: np.ndarray) -> None:
        self._apply(coefficients, output, None)

    def apply_component(
        self, coefficients: np.ndarray, output: np.ndarray, *, component: str
    ) -> None:
        if component not in ("curl", "mass"):
            raise ValueError("fused split component must be curl or mass")
        self._apply(coefficients, output, component)


class _ComponentView:
    def __init__(
        self, owner: FullspaceMpcFormAction, kernel: FusedIsotropicSplitKernel,
        component: str, form: Any,
    ) -> None:
        self._owner = owner
        self._kernel = kernel
        self._component = component
        self._bilinear_form = form
        self._local_kernel = (
            kernel.curl_kernel if component == "curl" else kernel.mass_kernel
        )

    @property
    def matrix(self):
        if self._owner is None:
            raise RuntimeError("fused split component view has been destroyed")
        return self._owner.matrix

    @property
    def audit(self):
        if self._local_kernel is None:
            return MappingProxyType({
                "component": self._component,
                "destroyed": True,
            })
        return MappingProxyType({
            "component": self._component,
            "local_kernel": self._local_kernel.audit,
            "shared_owner_action": True,
        })

    def apply(self, source):
        if self._owner is None:
            raise RuntimeError("fused split component view has been destroyed")
        return self._owner.apply(
            source,
            local_component=self._component,
            slave_row_identity=self._component == "curl",
        )

    def destroy(self):
        # The parent fused volume owns the shared MPC action and both kernels.
        return None


class FullspaceFusedSplitVolumeAction:
    """A6 volume action sharing local work, MPC preparation and output path."""

    def __init__(
        self,
        curl_curl_form: Any,
        material_mass_form: Any,
        function_space: Any,
        *,
        mpc: Any,
        local_kernels: tuple[Any, Any],
        jit_options=None,
    ) -> None:
        if len(local_kernels) != 2:
            raise ValueError("fused volume requires exactly two local kernels")
        self._forms = (curl_curl_form, material_mass_form)
        self._kernel = FusedIsotropicSplitKernel(*local_kernels)
        self._action = FullspaceMpcFormAction(
            curl_curl_form + material_mass_form,
            function_space,
            mpc=mpc,
            slave_row_identity=True,
            jit_options=jit_options,
            local_kernel=self._kernel,
        )
        self._components = MappingProxyType({
            "curl": _ComponentView(
                self._action, self._kernel, "curl", curl_curl_form
            ),
            "material_mass": _ComponentView(
                self._action, self._kernel, "mass", material_mass_form
            ),
        })
        self._apply_count = 0
        self._destroyed = False

    def apply(self, source):
        if self._destroyed:
            raise RuntimeError("fused split volume action has been destroyed")
        result = self._action.apply(source)
        self._apply_count += 1
        return result

    @property
    def component_actions(self) -> Mapping[str, Any]:
        if self._destroyed:
            raise RuntimeError("fused split volume action has been destroyed")
        return self._components

    @property
    def bilinear_form(self):
        if self._destroyed:
            raise RuntimeError("fused split volume action has been destroyed")
        return self._forms[0] + self._forms[1]

    @property
    def audit(self) -> Mapping[str, Any]:
        if self._destroyed:
            return MappingProxyType({
                "schema": "task039extra.fused-split-volume-action.v1",
                "destroyed": True,
                "apply_count": int(self._apply_count),
            })
        return MappingProxyType({
            "schema": "task039extra.fused-split-volume-action.v1",
            "operator": "A_curl_curl_plus_A_complex_material_mass",
            "component_count": 2,
            "components": {
                "curl_curl": dict(self._kernel.curl_kernel.audit),
                "complex_material_mass": dict(self._kernel.mass_kernel.audit),
            },
            "fused_local_kernel": dict(self._kernel.audit),
            "shared_fullspace_mpc_action": dict(self._action.audit),
            "constraint_identity_rows_exactly_once": True,
            "slave_row_identity_owner": "curl_curl",
            "phase_application": "finalized_floquet_mpc_once",
            "apply_count": int(self._apply_count),
            "destroyed": self._destroyed,
        })

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._action.destroy()
        for view in self._components.values():
            view._owner = None
            view._kernel = None
            view._local_kernel = None
        self._components = MappingProxyType({})
        self._kernel = None
        self._action = None
        self._forms = None


__all__ = ("FullspaceFusedSplitVolumeAction", "FusedIsotropicSplitKernel")
