# Broad catches synchronize rank-local third-party failures before the next MPI collective.
# ruff: noqa: BLE001
"""Exact per-cell H(curl) tangential mass blocks for the adaptive pilot.

The form is deliberately assembled as an untagged exterior-facet UFCx kernel.
The caller invokes that kernel on all six local facets and later adds the cell
blocks into a skeleton matrix.  No global mass matrix is owned here.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _orient_cell_tensor,
)

__all__ = (
    "ActualHcurlCellTangentialMassProvider",
    "build_actual_hcurl_cell_tangential_mass_provider",
)


def _key_sha256(key: Any) -> str:
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()


class ActualHcurlCellTangentialMassProvider:
    """Return one oriented raw-trace mass block for each owned cell.

    The provider borrows ``function_space`` and ``condensed``.  Returned
    arrays are caller-owned; cached tensors are released explicitly by
    :meth:`release_numeric_cache` and never become PETSc global matrices.
    """

    def __init__(self, function_space: Any, condensed: Any, quadrature_degree: int):
        if isinstance(quadrature_degree, bool) or not isinstance(
            quadrature_degree, (int, np.integer)
        ) or int(quadrature_degree) <= 0:
            raise ValueError("quadrature_degree must be a positive integer")
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise TypeError("the exact H(curl) mass provider requires complex128")
        self._V = function_space
        self._condensed = condensed
        self._mesh = function_space.mesh
        self._comm = self._mesh.comm
        self._quadrature_degree = int(quadrature_degree)
        self._raw_cache: dict[Any, tuple[np.ndarray, tuple[float, ...]]] = {}
        self._oriented_cache: dict[Any, np.ndarray] = {}
        self._class_audits: dict[str, dict[str, Any]] = {}
        self._class_usage: dict[str, int] = {}
        self._served_cells: set[int] = set()
        self._released = False
        self._destroyed = False
        self._form = None
        self._kernel = None
        self._ffi = None
        self._build_kernel()
        self._build_layout_identity()

    def _build_kernel(self) -> None:
        mesh = self._mesh
        trial = ufl.TrialFunction(self._V)
        test = ufl.TestFunction(self._V)
        normal = ufl.FacetNormal(mesh)
        ds = ufl.Measure("ds", domain=mesh)
        self._form = fem.form(
            ufl.inner(ufl.cross(normal, trial), ufl.cross(normal, test)) * ds,
            dtype=np.complex128,
            form_compiler_options={"quadrature_degree": self._quadrature_degree},
        )
        ufcx_form = self._form.ufcx_form
        integral_count = int(
            self._form.num_integrals(fem.IntegralType.exterior_facet, 0)
        )
        offsets = ufcx_form.form_integral_offsets
        exterior_start = int(offsets[1])
        exterior_stop = int(offsets[2])
        if exterior_stop - exterior_start != 1 or integral_count != 1:
            raise ValueError(
                "exact H(curl) mass requires one untagged exterior integral kernel"
            )
        if int(getattr(ufcx_form, "num_coefficients", 0)) != 0:
            raise ValueError("exact H(curl) mass form must have no coefficients")
        if int(getattr(ufcx_form, "num_constants", 0)) != 0:
            raise ValueError("exact H(curl) mass form must have no constants")
        integral = ufcx_form.form_integrals[exterior_start]
        kernel = integral.tabulate_tensor_complex128
        self._ffi = self._form.module.ffi
        if kernel == self._ffi.NULL:
            raise TypeError("exterior form does not expose a complex128 UFCx kernel")
        self._kernel = kernel
        self._needs_facet_permutations = bool(
            self._form._cpp_object.needs_facet_permutations
        )
        self._audit_kernel = {
            "kernel_source": "inner(cross(n,u),cross(n,v))*ds",
            "kernel_precision": "complex128",
            "kernel_nonnull": True,
            "exterior_integral_count": 1,
            "exterior_kernel_offsets": [exterior_start, exterior_stop],
            "num_coefficients": 0,
            "num_constants": 0,
            "quadrature_degree": self._quadrature_degree,
            "needs_facet_permutations": self._needs_facet_permutations,
        }

    def _build_layout_identity(self) -> None:
        mesh = self._mesh
        tdim = int(mesh.topology.dim)
        owned_cells = int(mesh.topology.index_map(tdim).size_local)
        mesh.topology.create_entities(tdim - 1)
        mesh.topology.create_connectivity(tdim, tdim - 1)
        mesh.topology.create_entity_permutations()
        connectivity = mesh.topology.connectivity(tdim, tdim - 1)
        for cell in range(owned_cells):
            if len(connectivity.links(cell)) != 6:
                raise ValueError(f"cell {cell} does not have exactly six facets")
        self._owned_cells = owned_cells
        self._cell_permutations = np.asarray(
            mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        if self._cell_permutations.size < owned_cells:
            raise ValueError("DOLFINx cell permutation metadata is incomplete")
        if self._needs_facet_permutations:
            facet_permutations = np.asarray(
                mesh.topology.get_facet_permutations(), dtype=np.uint8
            ).reshape(-1)
            if facet_permutations.size < 6 * owned_cells:
                raise ValueError("DOLFINx facet permutation metadata is incomplete")
            self._facet_permutations = facet_permutations[: 6 * owned_cells].copy()
            permutation_mode = "dolfinx_uint8_facet_permutations"
        else:
            self._facet_permutations = np.zeros(6 * owned_cells, dtype=np.uint8)
            permutation_mode = "zero_uint8_no_facet_permutations_required"

        dofmap = self._V.dofmap
        if int(dofmap.index_map_bs) != 1:
            raise ValueError("exact H(curl) mass requires scalar-blocked DoFs")
        element = self._V.element
        dimension = int(element.space_dimension)
        entity_dofs = np.asarray(
            element.basix_element.entity_dofs[tdim][0], dtype=np.int32
        )
        if entity_dofs.size == 0:
            raise ValueError("exact H(curl) mass requires cell-interior entity DoFs")
        self._trace_positions = np.setdiff1d(
            np.arange(dimension, dtype=np.int32),
            entity_dofs,
            assume_unique=True,
        )
        self._interior_positions = entity_dofs.copy()
        if len(self._condensed.cell_recovery_maps) != owned_cells:
            raise ValueError("condensed recovery map count differs from owned cells")
        local_trace_identity = True
        index_map = dofmap.index_map
        for cell in range(owned_cells):
            local_dofs = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
            if local_dofs.size != dimension:
                raise ValueError(
                    f"cell {cell} DoF count {local_dofs.size} differs from "
                    f"element space dimension {dimension}"
                )
            original = np.asarray(
                index_map.local_to_global(local_dofs), dtype=PETSc.IntType
            )
            expected = np.asarray(
                self._condensed.cell_recovery_maps[cell].trace_original_dofs,
                dtype=PETSc.IntType,
            )
            if not np.array_equal(original[self._trace_positions], expected):
                local_trace_identity = False
                raise ValueError(
                    f"cell {cell} trace positions differ from condensed recovery map"
                )
        self._audit_layout = {
            "owned_cell_count_local": owned_cells,
            "facet_count_local": 6 * owned_cells,
            "facets_per_cell": 6,
            "interior_positions": self._interior_positions.tolist(),
            "trace_dof_count_local_reference": len(self._trace_positions),
            "trace_original_dofs_identity": local_trace_identity,
            "facet_permutation_mode": permutation_mode,
        }

    def _kernel_facet(self, coordinates: np.ndarray, facet: int, permutation: int):
        dimension = int(self._V.element.space_dimension)
        tensor = np.zeros((dimension, dimension), dtype=np.complex128)
        facet_index = np.asarray([int(facet)], dtype=np.int32)
        facet_permutation = np.asarray([int(permutation)], dtype=np.uint8)
        self._kernel(
            self._ffi.cast("double _Complex *", self._ffi.from_buffer(tensor)),
            self._ffi.NULL,
            self._ffi.NULL,
            self._ffi.cast(
                "double *", self._ffi.from_buffer(np.ascontiguousarray(coordinates))
            ),
            self._ffi.cast("int *", self._ffi.from_buffer(facet_index)),
            self._ffi.cast(
                "uint8_t *", self._ffi.from_buffer(facet_permutation)
            ),
            self._ffi.NULL,
        )
        return tensor

    def _audit_oriented_class(
        self,
        key: Any,
        tensor: np.ndarray,
        facet_norms: tuple[float, ...],
    ) -> str:
        token = _key_sha256(key)
        if token in self._class_audits:
            return token
        trace = tensor[np.ix_(self._trace_positions, self._trace_positions)]
        scale = max(float(np.linalg.norm(trace)), 1.0e-300)
        hermitian_defect = float(np.linalg.norm(trace - trace.conj().T) / scale)
        eigenvalues = np.linalg.eigvalsh((trace + trace.conj().T) * 0.5)
        minimum_eigenvalue = float(np.min(eigenvalues, initial=0.0))
        support = np.any(np.abs(trace) > 1.0e-14, axis=1)
        interior_mask = np.ones(tensor.shape, dtype=bool)
        interior_mask[np.ix_(self._trace_positions, self._trace_positions)] = False
        interior_leakage = float(np.linalg.norm(tensor[interior_mask]) / scale)
        if not np.all(np.isfinite(tensor)) or not np.all(np.isfinite(trace)):
            raise ValueError("exact H(curl) mass class is non-finite")
        if hermitian_defect > 1.0e-10:
            raise ValueError(
                "exact H(curl) mass class is not Hermitian: "
                f"defect={hermitian_defect:.3e}"
            )
        if minimum_eigenvalue < -1.0e-10 * scale:
            raise ValueError(
                "exact H(curl) mass class is not positive semidefinite: "
                f"minimum_eigenvalue={minimum_eigenvalue:.3e}"
            )
        if interior_leakage > 1.0e-10:
            raise ValueError(
                "exact H(curl) mass has interior leakage: "
                f"relative={interior_leakage:.3e}"
            )
        if not np.all(support) or not any(value > 1.0e-14 for value in facet_norms):
            raise ValueError("exact H(curl) mass class has incomplete support")
        self._class_audits[token] = {
            "key_sha256": token,
            "finite": True,
            "hermitian": True,
            "positive_semidefinite": True,
            "hermitian_relative_defect": hermitian_defect,
            "minimum_eigenvalue": minimum_eigenvalue,
            "interior_leakage_relative": interior_leakage,
            "interior_leakage_gate": 1.0e-10,
            "support_complete": True,
            "nonzero": True,
            "canonical_coordinate_sha256": str(key[0][2]),
            "six_facet_norms": list(facet_norms),
            "trace_block_rows": len(self._trace_positions),
        }
        self._class_usage[token] = 0
        return token

    def __call__(self, cell: int) -> np.ndarray:
        if self._destroyed or self._released:
            raise RuntimeError("exact H(curl) mass provider numeric cache is released")
        cell = int(cell)
        if cell < 0 or cell >= self._owned_cells:
            raise IndexError(f"cell {cell} is not locally owned")
        coordinates, widths = _canonical_axis_aligned_coordinates(
            self._mesh, cell, tolerance=1.0e-11
        )
        facet_slice = self._facet_permutations[6 * cell : 6 * cell + 6]
        coordinate_hash = hashlib.sha256(
            np.ascontiguousarray(coordinates, dtype="<f8").tobytes()
        ).hexdigest()
        raw_key = (
            tuple(widths),
            tuple(int(value) for value in facet_slice),
            coordinate_hash,
        )
        cached = self._raw_cache.get(raw_key)
        if cached is None:
            facet_tensors = tuple(
                self._kernel_facet(coordinates, facet, int(facet_slice[facet]))
                for facet in range(6)
            )
            raw_tensor = np.asarray(sum(facet_tensors), dtype=np.complex128)
            facet_norms = tuple(float(np.linalg.norm(item)) for item in facet_tensors)
            self._raw_cache[raw_key] = (raw_tensor, facet_norms)
        else:
            raw_tensor, facet_norms = cached
        cell_info = np.asarray(
            self._cell_permutations[cell : cell + 1], dtype=np.uint32
        )
        oriented_key = (raw_key, tuple(int(value) for value in cell_info))
        oriented = self._oriented_cache.get(oriented_key)
        if oriented is None:
            oriented = np.asarray(raw_tensor, dtype=np.complex128).copy()
            _orient_cell_tensor(self._V.element, oriented, cell_info)
            self._audit_oriented_class(oriented_key, oriented, facet_norms)
            self._oriented_cache[oriented_key] = oriented
        token = _key_sha256(oriented_key)
        self._class_usage[token] = self._class_usage.get(token, 0) + 1
        trace = oriented[np.ix_(self._trace_positions, self._trace_positions)]
        self._served_cells.add(cell)
        return np.ascontiguousarray(trace.copy())

    @property
    def audit(self) -> dict[str, Any]:
        classes = {
            key: {
                **value,
                "usage_count_local": int(self._class_usage.get(key, 0)),
            }
            for key, value in self._class_audits.items()
        }
        return {
            "schema": "task040.v8.actual_hcurl_cell_tangential_mass.v1",
            "status": (
                "local_complete"
                if len(self._served_cells) == self._owned_cells
                else "local_incomplete"
            ),
            "actual_hcurl_facet_form_assembler": True,
            **self._audit_kernel,
            **self._audit_layout,
            "served_cells_local": sorted(self._served_cells),
            "raw_cache_size_local": len(self._raw_cache),
            "evaluated_oriented_class_count_local": len(self._class_audits),
            "oriented_numeric_cache_size_local": len(self._oriented_cache),
            "oriented_class_audits_local": classes,
            "all_evaluated_classes_verified": all(
                item["finite"]
                and item["hermitian"]
                and item["positive_semidefinite"]
                and item["support_complete"]
                and item["nonzero"]
                for item in classes.values()
            ),
            "full_vector_numeric_allgather": False,
            "trace_blocks_caller_owned": True,
            "numeric_cache_released": bool(self._released),
            "destroyed": bool(self._destroyed),
        }

    def collective_audit(self) -> dict[str, Any]:
        local = None
        local_error: str | None = None
        try:
            local = self.audit
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        if any(error is not None for error in errors):
            raise RuntimeError(
                "exact H(curl) provider audit failed: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(errors)
                    if error is not None
                )
            )
        assert local is not None
        packets = self._comm.allgather(
            {
                "owned_cell_count_local": local["owned_cell_count_local"],
                "facet_count_local": local["facet_count_local"],
                "served_cells_local": len(local["served_cells_local"]),
                "trace_original_dofs_identity": local["trace_original_dofs_identity"],
                "all_classes_finite": all(
                    item["finite"] for item in local["oriented_class_audits_local"].values()
                ),
                "all_classes_verified": local["all_evaluated_classes_verified"],
                "evaluated_oriented_class_count_local": local[
                    "evaluated_oriented_class_count_local"
                ],
            }
        )
        global_owned = sum(int(packet["owned_cell_count_local"]) for packet in packets)
        global_served = sum(int(packet["served_cells_local"]) for packet in packets)
        verified = bool(
            global_owned > 0
            and global_served == global_owned
            and all(
                int(packet["owned_cell_count_local"]) == 0
                or int(packet["evaluated_oriented_class_count_local"]) > 0
                for packet in packets
            )
            and all(packet["trace_original_dofs_identity"] for packet in packets)
            and all(packet["all_classes_finite"] for packet in packets)
            and all(packet["all_classes_verified"] for packet in packets)
        )
        return {
            **local,
            "status": "verified_exact_provider" if verified else "ready_unexercised",
            "owned_cell_count_global": int(global_owned),
            "served_cell_count_global": int(global_served),
            "facet_count_global": int(
                sum(int(packet["facet_count_local"]) for packet in packets)
            ),
            "trace_original_dofs_identity_global": bool(
                all(packet["trace_original_dofs_identity"] for packet in packets)
            ),
            "all_classes_finite_global": bool(
                all(packet["all_classes_finite"] for packet in packets)
            ),
            "all_evaluated_classes_verified_global": bool(
                all(packet["all_classes_verified"] for packet in packets)
            ),
            "oriented_class_count_global": int(
                sum(
                    int(packet["evaluated_oriented_class_count_local"])
                    for packet in packets
                )
            ),
            "metadata_collective": "allgather_compact_audit",
            "empty_local_allowed": True,
        }

    def release_numeric_cache(self) -> None:
        if self._destroyed:
            return
        states = self._comm.allgather(bool(self._released))
        if any(state != states[0] for state in states):
            raise RuntimeError("exact H(curl) provider release state differs across ranks")
        if self._released:
            return
        local_error: str | None = None
        try:
            self._raw_cache.clear()
            self._oriented_cache.clear()
            self._released = True
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        if any(error is not None for error in errors):
            raise RuntimeError(
                "exact H(curl) provider numeric-cache release failed: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(errors)
                    if error is not None
                )
            )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._raw_cache.clear()
        self._oriented_cache.clear()
        self._class_audits.clear()
        self._class_usage.clear()
        self._form = None
        self._kernel = None
        self._ffi = None
        self._V = None
        self._condensed = None
        self._mesh = None
        self._destroyed = True


def build_actual_hcurl_cell_tangential_mass_provider(
    function_space: Any,
    condensed: Any,
    *,
    quadrature_degree: int,
) -> ActualHcurlCellTangentialMassProvider:
    """Build and collectively validate the exact exterior-kernel provider."""

    comm = function_space.mesh.comm
    provider = None
    local_error: str | None = None
    try:
        provider = ActualHcurlCellTangentialMassProvider(
            function_space, condensed, quadrature_degree
        )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        if provider is not None:
            provider.destroy()
        raise RuntimeError(
            "exact H(curl) mass provider construction failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(errors)
                if error is not None
            )
        )
    assert provider is not None
    provider.collective_audit()
    return provider
