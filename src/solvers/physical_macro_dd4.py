"""Review V10 multi-cell physical p4 additive correction.

This module owns the one new numerical ingredient admitted by Review V10:
fixed, overlapping algebraic p4 blocks assembled from the current cell
integrals and the current owner-local Fourier-DtN functionals.  It deliberately
does not create a global p4 matrix.  The existing p2 ``complete_pq`` path is
kept as ``C_U`` and is composed with the new additive inverse as

``C_U + (I - C_U A4) M_D (I - A4 C_U)``.

The builder is MPI1-only because the reviewed pilot is MPI1-only.  The small
pure-array helpers near the top are also used by focused unit tests; keeping
them independent of PETSc makes the algebraic contracts testable without
constructing a PDE mesh.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

MACRO_PROFILE = "physical_macro_dd4_v10"
MACRO_SCHEMA = "task039.physical-macro-dd4.v10"
LOCAL_ROWS_CAP = 2600
LOCAL_RESIDENT_CAP = 2 * 1024**3
LOCAL_TEMP_RESERVE = 1 * 1024**3
LOCAL_SOLVE_LIMIT = 1.0e-10
MACRO_I4_TARGET = 1.0e-4
MACRO_I4_RESTART = 4
MACRO_I4_MAX_IT = 4


def output_partition_weights(block_indices: list[np.ndarray], size: int) -> np.ndarray:
    """Return the fixed ``1/multiplicity`` output weights.

    The input to an additive Schwarz action is *not* weighted.  This helper
    intentionally makes that distinction explicit and rejects incomplete
    coverage rather than silently filling uncovered coordinates with zero.
    """

    size = int(size)
    if size <= 0:
        raise ValueError("partition size must be positive")
    multiplicity = np.zeros(size, dtype=np.int32)
    for indices in block_indices:
        values = np.asarray(indices, dtype=np.int64)
        if values.ndim != 1 or values.size == 0:
            raise ValueError("each macro block must have one non-empty index vector")
        if np.any(values < 0) or np.any(values >= size) or np.unique(values).size != values.size:
            raise ValueError("macro block indices are invalid or duplicated")
        multiplicity[values] += 1
    if np.any(multiplicity == 0):
        missing = np.flatnonzero(multiplicity == 0)
        raise ValueError(f"macro blocks do not cover all independent rows: {missing[:8].tolist()}")
    return 1.0 / multiplicity.astype(np.float64)


def _readonly(array: np.ndarray) -> np.ndarray:
    value = np.ascontiguousarray(array)
    value.flags.writeable = False
    return value


def _identity_hash_arrays(named_arrays: Mapping[str, Any]) -> str:
    """Hash fixed array identity, including names, dtype, and shape."""
    digest = hashlib.sha256()
    for name in sorted(named_arrays):
        value = np.ascontiguousarray(np.asarray(named_arrays[name]))
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(json.dumps(list(value.shape)).encode("ascii"))
        digest.update(value.tobytes())
    return digest.hexdigest()


def _checked_local_factor(matrix: np.ndarray) -> tuple[tuple[np.ndarray, np.ndarray], dict[str, Any]]:
    """Factor one physical block without a shift, pseudo-inverse, or L@U test.

    Review V10 asks for two deterministic physical right-hand-side
    backsolves.  Forming a dense ``L@U`` witness for every 2k block is both
    unnecessary and materially more expensive, so the actual qualification is
    the requested solve residual on two fixed finite vectors.
    """

    matrix = np.asarray(matrix, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise ValueError("local physical block must be a non-empty square matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("local physical block contains non-finite entries")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LinAlgWarning)
        factor = lu_factor(matrix)
    if not np.isfinite(factor[0]).all():
        raise ValueError("local physical factor contains non-finite entries")

    n = matrix.shape[0]
    probes = (
        np.arange(1, n + 1, dtype=np.float64) + 1j * np.arange(n, 0, -1, dtype=np.float64),
        np.arange(n, 2 * n, dtype=np.float64) - 0.5j * np.arange(1, n + 1, dtype=np.float64),
    )
    defects = []
    for probe in probes:
        rhs = matrix @ probe
        solution = lu_solve(factor, rhs)
        defect = float(np.linalg.norm(matrix @ solution - rhs) / max(np.linalg.norm(rhs), np.finfo(float).tiny))
        if not np.isfinite(defect) or defect > LOCAL_SOLVE_LIMIT:
            raise ValueError(f"local physical backsolve residual {defect} exceeds {LOCAL_SOLVE_LIMIT}")
        defects.append(defect)
    facts = {
        "rows": int(n),
        "factorization": "complex_pivoted_LU",
        "shift": 0.0,
        "pseudoinverse": False,
        "test_rhs_count": 2,
        "test_relative_residuals": defects,
        "test_residual_limit": LOCAL_SOLVE_LIMIT,
    }
    return (np.ascontiguousarray(factor[0]), np.asarray(factor[1], dtype=np.int32)), facts


def _save(save: Callable[[str, Mapping[str, Any]], Any] | None, name: str, facts: Mapping[str, Any]) -> None:
    if save is not None:
        save(name, dict(facts))


@dataclass
class MacroClass:
    key: str
    A: np.ndarray
    Q: np.ndarray
    P: np.ndarray
    W: np.ndarray
    delta: np.ndarray
    D: np.ndarray
    factor: tuple[np.ndarray, np.ndarray]
    identity: dict[str, Any]


class MacroLocalVolume:
    """Current p4 cell-volume action plus the retained interior response."""

    memory_policy = "LEGACY_LOCAL_MUMPS_MEMORY_POLICY"

    def __init__(
        self,
        levels: Mapping[str, Any],
        cfg: Any,
        actions: Mapping[str, Any],
        *,
        sample: Callable[[], Any],
        marker: Callable[[str, Mapping[str, Any]], Any],
        save: Callable[[str, Mapping[str, Any]], Any] | None = None,
        memory_policy: str = "LEGACY_LOCAL_MUMPS_MEMORY_POLICY",
        local_inventory_cap_bytes: int = LOCAL_RESIDENT_CAP,
    ) -> None:
        from .condensed_fine_reference import (
            native_map_arrays,
            project_unconstrained_mpc_dual,
        )
        from .fullspace_same_mesh_hcurl_pmg import _dof_transform, _n1e
        from .fullspace_v17_p3_oracle import compile_physical_diagnostic_volume
        from .hcurl_assembly_time_condensation import (
            _cell_integral_kernels,
            _tabulate_raw_tensor_class,
        )
        from .physical_bubble_local import fixed_bubble_basis

        self.levels = levels
        self.cfg = cfg
        self.sample = sample
        self.marker = marker
        self.save = save
        self.memory_policy = memory_policy
        self.local_inventory_cap_bytes = int(local_inventory_cap_bytes)
        if self.local_inventory_cap_bytes <= 0:
            raise ValueError("local inventory cap must be positive")
        self.mapping = native_map_arrays(levels["spaces"][4], levels["floquets"][4])
        self.project_dual = project_unconstrained_mpc_dual
        mesh = levels["mesh"]
        if mesh.comm.size != 1:
            raise ValueError("Review V10 macro blocks are qualified only for MPI1")
        self.element = _n1e(4)
        self.coarse_element = _n1e(2)
        if int(self.element.dim) != 300 or int(self.coarse_element.dim) != 54:
            raise ValueError("frozen p4/p2 element dimensions changed")
        self.dofmap = np.asarray(self.mapping["dofmap"], dtype=np.int32)
        if self.dofmap.shape != (252, 300):
            raise ValueError(f"frozen local topology changed: {self.dofmap.shape}")
        self.mapping_identity_sha256 = _identity_hash_arrays({
            key: self.mapping[key]
            for key in ("dofmap", "slaves", "masters", "coefficients",
                        "offsets", "independent_indices")
        })

        marker("macro_local_volume_started", {"cells": len(self.dofmap), "local_dimension": 300})
        quadrature = actions["volume_quadrature_metadata"]
        compiled = compile_physical_diagnostic_volume(
            levels, cfg, 4, volume_quadrature_metadata=quadrature
        )
        kernels = _cell_integral_kernels(compiled)
        mesh.topology.create_entity_permutations()
        permutation_info = np.asarray(mesh.topology.get_cell_permutation_info())
        geometry = np.asarray(mesh.geometry.x)
        geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int32)
        tags = np.full(252, -1, dtype=np.int32)
        cell_tags = levels["mesh_data"].cell_tags
        tags[np.asarray(cell_tags.indices, dtype=np.int32)] = np.asarray(cell_tags.values, dtype=np.int32)
        if np.any(tags < 0):
            raise ValueError("each macro cell needs a current material tag")
        # Retain the actual material/geometry metadata used to choose the
        # fixed witness blocks.  The witness selection must be tied to the
        # current DtN/material support, not to arbitrary block ordinals.
        self.cell_tags = np.ascontiguousarray(tags)

        P0 = np.asarray(
            __import__("basix").compute_interpolation_operator(self.coarse_element, self.element),
            dtype=np.complex128,
        )
        R0 = np.asarray(
            __import__("basix").compute_interpolation_operator(self.element, self.coarse_element),
            dtype=np.complex128,
        )
        interior = np.asarray(self.element.entity_dofs[3][0], dtype=np.int32)
        self.classes: dict[str, MacroClass] = {}
        self.cell_classes: list[str] = []
        orientation_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
        class_count = 0
        for cell in range(252):
            coords = np.ascontiguousarray(geometry[geometry_dofmap[cell]], dtype=np.float64)
            widths = coords.max(axis=0) - coords.min(axis=0)
            J = np.column_stack((coords[1] - coords[0], coords[2] - coords[0], coords[4] - coords[0]))
            if not np.allclose(J, np.diag(widths), rtol=0.0, atol=1.0e-12) or np.any(widths <= 0):
                raise ValueError("macro local builder requires positive axis-aligned affine cells")
            info = int(permutation_info[cell])
            tag = int(tags[cell])
            material = {
                int(cfg.tags.air): complex(cfg.eps_r),
                int(cfg.tags.substrate): complex(cfg.substrate_index**2),
                int(cfg.tags.grating): complex(cfg.grating_index**2),
            }
            if tag not in material:
                raise ValueError(f"unknown current material tag {tag}")
            eps = material[tag]
            identity = {
                "J": [float(v).hex() for v in J.ravel()],
                "widths": [float(v).hex() for v in widths],
                "material_tag": tag,
                "eps_r": [eps.real.hex(), eps.imag.hex()],
                "mu_r": [complex(cfg.mu_r).real.hex(), complex(cfg.mu_r).imag.hex()],
                "k0": float(cfg.k0).hex(),
                "quadrature": quadrature,
                "orientation": info,
                "element_hashes": [int(self.element.hash()), int(self.coarse_element.hash())],
            }
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
            self.cell_classes.append(key)
            if key in self.classes:
                continue
            if info not in orientation_cache:
                tf = _dof_transform(self.element, info)
                tc = _dof_transform(self.coarse_element, info)
                P = tf @ P0 @ tc.T
                R = tc @ R0 @ tf.T
                Q, basis = fixed_bubble_basis(P, R, interior)
                if (
                    basis["RP_relative"] > 1.0e-12
                    or basis["RQ_norm"] > 1.0e-12
                    or basis["Q_orthogonality"] > 1.0e-12
                    or not basis["rank_gap_pass"]
                ):
                    raise ValueError("fixed macro bubble basis failed trace/rank gate")
                orientation_cache[info] = (tf, P, Q, basis)
                _save(save, f"macro_orientation_{info}", {"P": P, "R": R, "Q": Q, "basis": basis})
            tf, P, Q, basis = orientation_cache[info]
            raw = _tabulate_raw_tensor_class(
                compiled, kernels, np.ascontiguousarray(coords.ravel()), tag=tag, dimension=300
            )
            A = np.ascontiguousarray(tf @ raw @ tf.T, dtype=np.complex128)
            D = np.ascontiguousarray(Q.conj().T @ A @ Q, dtype=np.complex128)
            factor, factor_facts = _checked_local_factor(D)
            T = lu_solve(factor, Q.conj().T @ A @ P)
            W = np.ascontiguousarray(P - Q @ T, dtype=np.complex128)
            delta = np.ascontiguousarray(W.conj().T @ A @ W - P.conj().T @ A @ P, dtype=np.complex128)
            item = MacroClass(key, _readonly(A), _readonly(Q), _readonly(P), _readonly(W),
                              _readonly(delta), _readonly(D), factor, identity)
            self.classes[key] = item
            class_count += 1
            _save(save, f"macro_class_{class_count - 1:03d}", {
                "key": key,
                "identity": identity,
                "cell": cell,
                "local_rows": 300,
                "bubble_columns": int(Q.shape[1]),
                "W_storage_bytes": int(W.nbytes),
                "delta_storage_bytes": int(delta.nbytes),
                "factor": factor_facts,
                "A_storage_bytes": int(A.nbytes),
                "D_storage_bytes": int(D.nbytes),
            })
            marker("macro_local_class_complete", {"cell": cell, "class_count": class_count, "key": key})
        del compiled, kernels, orientation_cache
        self.cell_classes = tuple(self.cell_classes)
        self.cell_class_identity_sha256 = hashlib.sha256(
            json.dumps(list(self.cell_classes), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if len(self.classes) == 0:
            raise ValueError("macro builder produced no local physical classes")
        self._build_cell_groups(levels, geometry, geometry_dofmap)
        self.resident_bytes = self._resident_bytes()
        if self.resident_bytes > self.local_inventory_cap_bytes:
            raise MemoryError("macro local resident policy exceeds its explicit cap")
        _save(save, "macro_local_volume_complete", {
            "schema": MACRO_SCHEMA,
            "cell_count": 252,
            "class_count": len(self.classes),
            "local_factor_count": len(self.classes),
            "retained_resident_bytes": self.resident_bytes,
            "resident_cap_bytes": self.local_inventory_cap_bytes,
            "temporary_workspace_reserve_bytes": LOCAL_TEMP_RESERVE,
            "p4_global_matrix": False,
            "p4_global_factor": False,
            "global_column_probes": False,
        })
        marker("macro_local_volume_complete", {"classes": len(self.classes), "resident_bytes": self.resident_bytes})

    def _resident_bytes(self) -> int:
        """Count retained cache storage once, including shared MPC views.

        ``cell_expansions`` contains slices into the MPC arrays for slave
        rows.  Counting every view as an independent array understated the
        relationship between the cache and its source arrays, while counting
        both the view and its base would overstate the resident policy.  The
        small root-storage ledger below charges each ndarray backing store
        once and separately charges the Python container metadata retained by
        the 252-cell/42-block cache.
        """

        seen_arrays: set[int] = set()

        def add_array(value: Any) -> int:
            if not isinstance(value, np.ndarray):
                return 0
            root = value
            while isinstance(getattr(root, "base", None), np.ndarray):
                root = root.base
            key = id(root)
            if key in seen_arrays:
                return 0
            seen_arrays.add(key)
            return int(root.nbytes)

        total = add_array(self.dofmap)
        for value in self.mapping.values():
            total += add_array(value)
        for item in self.classes.values():
            total += sum(add_array(value) for value in (
                item.A, item.Q, item.P, item.W, item.delta, item.D,
                item.factor[0], item.factor[1],
            ))
        total += int(sum(add_array(active) for active in getattr(self, "cell_active", ())))
        total += int(sum(
            add_array(ids) + add_array(values)
            for expansions in getattr(self, "cell_expansions", ())
            for ids, values in expansions
        ))
        total += add_array(getattr(self, "cell_tags", None))
        total += add_array(getattr(self, "cell_min_points", None))
        total += add_array(getattr(self, "cell_max_points", None))
        total += add_array(getattr(self, "cell_coordinates_array", None))
        total += add_array(getattr(self, "output_weights", None))
        for block in getattr(self, "blocks", ()):
            total += add_array(np.asarray(block["indices"]))
            total += add_array(np.asarray(block.get("support_cells", ())))
            total += int(block.get("matrix_storage_bytes", 0))
            total += int(block.get("factor_reported_bytes", 0))
            factor = block.get("factor", ())
            if isinstance(factor, tuple):
                total += int(sum(add_array(np.asarray(value)) for value in factor))
        total += int(sys.getsizeof(getattr(self, "mapping", {})))
        total += int(sys.getsizeof(getattr(self, "classes", {})))
        total += int(sys.getsizeof(getattr(self, "cell_classes", ())))
        total += int(sys.getsizeof(getattr(self, "cell_expansions", ())))
        total += int(sys.getsizeof(getattr(self, "cell_active", ())))
        total += int(sys.getsizeof(getattr(self, "blocks", ())))
        total += int(sum(sys.getsizeof(value) for value in getattr(self, "cell_coordinates", ())))
        total += int(sum(sys.getsizeof(value) for value in getattr(self, "cell_expansions", ())))

        # W/P is an owner-local runtime cache created after coverage.  Its
        # arrays are not aliases of the p4 class arrays in general, and the
        # PETSc work fields plus the fixed owner packets remain alive while
        # C_U and the outer PC are used.  Count this post-coverage inventory
        # explicitly so a coverage-only snapshot cannot silently understate
        # the profile cap.
        def add_retained(value: Any, seen_containers: set[int]) -> int:
            if isinstance(value, np.ndarray):
                return add_array(value)
            if isinstance(value, dict):
                key = id(value)
                if key in seen_containers:
                    return 0
                seen_containers.add(key)
                return int(sys.getsizeof(value)) + sum(
                    add_retained(item, seen_containers) for item in value.values()
                )
            if isinstance(value, (tuple, list, set, frozenset)):
                key = id(value)
                if key in seen_containers:
                    return 0
                seen_containers.add(key)
                return int(sys.getsizeof(value)) + sum(
                    add_retained(item, seen_containers) for item in value
                )
            return int(sys.getsizeof(value)) if value is not None else 0

        container_ids: set[int] = set()
        owner = getattr(self, "owner", None)
        if owner is not None:
            total += int(sys.getsizeof(owner))
            for name in (
                "_records", "_serial_owner_plan", "_dual_flat_slaves",
                "_dual_flat_masters", "_dual_conjugated_coefficients",
                "_dual_reduction_work", "_coarse_slaves", "_authority",
            ):
                total += add_retained(getattr(owner, name, None), container_ids)
            for name in ("_coarse_work", "_fine_work"):
                work = getattr(owner, name, None)
                if work is not None:
                    total += add_array(np.asarray(work.x.array))
            for _key, transfer in getattr(owner, "_map_cache", ()):
                total += int(sys.getsizeof(transfer))
                total += add_array(getattr(transfer, "matrix", None))
            local_transfer = getattr(owner, "local_transfer", None)
            if local_transfer is not None:
                total += int(sys.getsizeof(local_transfer))
                total += add_array(getattr(local_transfer, "matrix", None))
        transfer = getattr(self, "transfer", None)
        if transfer is not None:
            total += int(sys.getsizeof(transfer))
            total += add_array(getattr(transfer, "fine_slaves", None))
            total += add_array(getattr(transfer, "coarse_slaves", None))
        cached_classes = getattr(self, "cached_classes", None)
        if cached_classes is not None:
            total += add_retained(cached_classes, container_ids)
        cached_action = getattr(self, "cached_action", None)
        if cached_action is not None:
            total += int(sys.getsizeof(cached_action))
        return total

    def _check_resident_gate(self, stage: str) -> dict[str, Any]:
        """Recompute the complete retained inventory at a lifecycle boundary."""
        self.resident_bytes = int(self._resident_bytes())
        facts = {
            "stage": str(stage),
            "retained_inventory_bytes": self.resident_bytes,
            "resident_cap_bytes": int(self.local_inventory_cap_bytes),
            "memory_policy": self.memory_policy,
            "classification": "derived_complete_local_inventory_gate",
        }
        _save(self.save, f"macro_local_inventory_{stage}", facts)
        if self.resident_bytes > self.local_inventory_cap_bytes:
            raise MemoryError(
                f"macro local resident policy exceeds cap at {stage}: "
                f"{self.resident_bytes} > {self.local_inventory_cap_bytes}"
            )
        return facts

    def _build_cell_groups(self, levels: Mapping[str, Any], geometry: np.ndarray, geometry_dofmap: np.ndarray) -> None:
        mapping = self.mapping
        slaves = set(np.asarray(mapping["slaves"], dtype=np.int64).tolist())
        masters = np.asarray(mapping["masters"], dtype=np.int64)
        coeffs = np.asarray(mapping["coefficients"], dtype=np.complex128)
        offsets = np.asarray(mapping["offsets"], dtype=np.int64)
        if np.intersect1d(mapping["slaves"], mapping["masters"]).size:
            raise ValueError("nested p4 MPC links are not supported by macro builder")

        self.cell_expansions: list[list[tuple[np.ndarray, np.ndarray]]] = []
        self.cell_active: list[np.ndarray] = []
        for rows in self.dofmap:
            expansions = []
            active: set[int] = set()
            for row in rows:
                row = int(row)
                if row not in slaves:
                    ids = np.asarray([row], dtype=np.int64)
                    values = np.asarray([1.0 + 0.0j], dtype=np.complex128)
                else:
                    start, stop = offsets[row:row + 2]
                    ids = masters[start:stop]
                    values = coeffs[start:stop]
                if ids.size == 0:
                    raise ValueError("p4 slave has no master links")
                active.update(int(v) for v in ids)
                expansions.append((ids, values))
            self.cell_expansions.append(expansions)
            self.cell_active.append(np.asarray(sorted(active), dtype=np.int64))

        mins = np.asarray([geometry[geometry_dofmap[cell]].min(axis=0) for cell in range(252)])
        x = np.unique(mins[:, 0]); y = np.unique(mins[:, 1]); z = np.unique(mins[:, 2])
        if (len(x), len(y), len(z)) != (6, 3, 14):
            raise ValueError(f"macro topology expected 6x3x14 cell starts, got {(len(x), len(y), len(z))}")
        self.cell_min_points = np.ascontiguousarray(mins, dtype=np.float64)
        maxs = np.asarray([geometry[geometry_dofmap[cell]].max(axis=0) for cell in range(252)])
        self.cell_max_points = np.ascontiguousarray(maxs, dtype=np.float64)
        self.cell_coordinates = []
        seed_groups: dict[tuple[int, int, int], list[int]] = {}
        for cell, point in enumerate(mins):
            coordinate = (int(np.flatnonzero(x == point[0])[0]), int(np.flatnonzero(y == point[1])[0]), int(np.flatnonzero(z == point[2])[0]))
            self.cell_coordinates.append(coordinate)
            seed_groups.setdefault(tuple(v // 2 for v in coordinate), []).append(cell)
        if len(seed_groups) != 42:
            raise ValueError(f"macro seed group count expected 42, got {len(seed_groups)}")

        blocks = []
        for seed, seed_cells in sorted(seed_groups.items()):
            selected = np.unique(np.concatenate([self.cell_active[cell] for cell in seed_cells])).astype(np.int64)
            support = np.asarray([cell for cell, active in enumerate(self.cell_active) if np.intersect1d(active, selected).size], dtype=np.int32)
            if selected.size > LOCAL_ROWS_CAP:
                raise MemoryError(f"macro block {seed} has {selected.size} rows > {LOCAL_ROWS_CAP}")
            carrier = levels.get("__macro_dtn_carrier")
            blocks.append({"seed": seed, "seed_cells": tuple(seed_cells), "indices": selected,
                           "support_cells": support, "volume_terms": len(support),
                           "dtn_terms": 0, "carrier": carrier})
        self.blocks = blocks
        self.cell_coordinates_array = np.ascontiguousarray(self.cell_coordinates, dtype=np.int32)

    def _mumps_backsolve_gate(
        self, matrix: Any, factor: Any, *, save=None, block_index=None,
        identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check two fixed ``D_i w`` solves through the retained MUMPS factor."""

        defects = []
        probes_facts = []
        n = int(matrix.getSize()[0])
        probes = (
            np.arange(1, n + 1, dtype=np.float64) + 1j * np.arange(n, 0, -1, dtype=np.float64),
            np.arange(n, 2 * n, dtype=np.float64) - 0.5j * np.arange(1, n + 1, dtype=np.float64),
        )
        for probe in probes:
            vector = matrix.createVecRight()
            rhs = matrix.createVecRight()
            solution = checked = None
            probe_fact: dict[str, Any] = {
                "probe_index": len(probes_facts),
                "probe_norm": float(np.linalg.norm(probe)),
            }
            try:
                vector.array[:] = probe
                matrix.mult(vector, rhs)
                probe_fact["rhs_norm"] = float(np.linalg.norm(rhs.array))
                solve_started = time.perf_counter()
                solution, solve_facts = factor.solve_lean(rhs)
                probe_fact["solve_seconds"] = time.perf_counter() - solve_started
                probe_fact["solve_facts"] = dict(solve_facts)
                checked = matrix.createVecRight()
                matrix.mult(solution, checked)
                difference_norm = float(np.linalg.norm(checked.array - rhs.array))
                rhs_norm = float(np.linalg.norm(rhs.array))
                defect = difference_norm / max(rhs_norm, np.finfo(float).tiny)
                probe_fact.update(
                    solution_norm=float(np.linalg.norm(solution.array)),
                    checked_norm=float(np.linalg.norm(checked.array)),
                    difference_norm=difference_norm,
                    relative_residual=defect,
                    rhs_sha256=hashlib.sha256(
                        np.ascontiguousarray(rhs.array).tobytes()).hexdigest(),
                    residual_sha256=hashlib.sha256(
                        np.ascontiguousarray(checked.array - rhs.array).tobytes()).hexdigest(),
                )
                if not np.isfinite(defect) or defect > LOCAL_SOLVE_LIMIT:
                    raise ValueError(f"local MUMPS backsolve residual {defect} exceeds {LOCAL_SOLVE_LIMIT}")
                defects.append(defect)
                probes_facts.append(probe_fact)
            except BaseException as exc:
                _save(save, f"macro_block_{block_index:02d}_backsolve_failure"
                      if block_index is not None else "macro_backsolve_failure", {
                    "identity": dict(identity or {}),
                    "probe": probe.copy(),
                    "rhs": rhs.array.copy(),
                    "solution": solution.array.copy() if solution is not None else None,
                    "checked": checked.array.copy() if checked is not None else None,
                    "probe_facts": probe_fact,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                })
                raise
            finally:
                vector.destroy()
                rhs.destroy()
                if solution is not None:
                    solution.destroy()
                if checked is not None:
                    checked.destroy()
        return {
            "test_rhs_count": len(defects),
            "test_relative_residuals": defects,
            "probe_facts": probes_facts,
            "first_backsolve_seconds": probes_facts[0].get("solve_seconds"),
            "first_backsolve_facts": probes_facts[0].get("solve_facts"),
            "test_residual_limit": LOCAL_SOLVE_LIMIT,
        }

    def _select_representative_blocks(self, carrier: Any) -> dict[str, int]:
        """Select one canonical block for each actual support category.

        The three witnesses are intentionally tied to the retained local
        metadata: a material-interface support, a block touched by at least
        one current DtN functional, and an interior support without a
        nonzero current DtN functional.
        Choosing the lexicographically smallest seed in each category makes
        the choice deterministic without probing a global operator or
        assuming that ordinal block 0/middle/last has a physical meaning.
        """

        # Focused fixtures deliberately omit the full mesh metadata.  Their
        # small path still exercises the production SeqAIJ/MUMPS assembly;
        # witness every fixture block rather than inventing physical labels.
        if not hasattr(self, "cell_tags"):
            return {f"fixture_{index}": index for index in range(len(self.blocks))}

        def active_rows(rows: Any, values: Any) -> set[int]:
            row_array = np.asarray(rows, dtype=np.int64)
            value_array = np.asarray(values)
            if row_array.shape != value_array.shape:
                raise ValueError("DtN rows and values must have matching shapes")
            return set(row_array[np.abs(value_array) > 0.0].tolist())

        active_port_rows: set[int] = set()
        for entry in carrier.entries:
            active_port_rows.update(active_rows(entry.coupling_rows, entry.coupling_values))
            active_port_rows.update(active_rows(entry.projection_rows, entry.projection_values))

        port_blocks: list[int] = []
        material_blocks: list[int] = []
        internal_blocks: list[int] = []
        for index, block in enumerate(self.blocks):
            selected = set(np.asarray(block["indices"], dtype=np.int64).tolist())
            has_dtn = bool(selected.intersection(active_port_rows))
            tags = np.unique(self.cell_tags[np.asarray(block["support_cells"], dtype=np.int64)])
            has_material_interface = tags.size >= 2
            if has_dtn:
                port_blocks.append(index)
            if has_material_interface:
                material_blocks.append(index)
            if not has_dtn:
                internal_blocks.append(index)

        self.representative_selection_notes = {
            "active_port_row_count": len(active_port_rows),
            "interior_category": "no_nonzero_current_DtN_support; material_tags_reported_separately",
        }

        def canonical(category: str, candidates: list[int]) -> int:
            if not candidates:
                raise ValueError(f"no canonical {category} macro block in current metadata")
            return min(candidates, key=lambda index: tuple(self.blocks[index]["seed"]))

        return {
            "material_interface": canonical("material_interface", material_blocks),
            "port_DtN": canonical("port_DtN", port_blocks),
            "interior_no_DtN": canonical("interior_no_DtN", internal_blocks),
        }

    def _native_block_witness(
        self, block: Mapping[str, Any], selected: np.ndarray, matrix: Any, native_a4: Any,
        *, save=None, block_index=None, identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compare three fixed embedded block vectors against native A4."""

        from .fullspace_physical_intermediate import apply_owned
        from .fullspace_physical_intermediate_runtime import level_vector

        if native_a4 is None:
            raise ValueError("native A4 is required for the macro block witness")
        make_vector = getattr(self, "_new_p4_vector", None)
        if make_vector is None:
            make_vector = lambda: level_vector(self.levels, 4)
        slave_indices = np.asarray(self.mapping["slaves"], dtype=np.int64)
        defects = []
        operation_scales = []
        probe_facts = []
        for seed in range(3):
            local = np.arange(selected.size, dtype=np.float64) + 1.0 + seed
            w = local + 1j * (local[::-1] + 0.25 * seed)
            block_vector = matrix.createVecRight()
            block_rhs = matrix.createVecRight()
            global_vector = native_value = None
            probe_fact: dict[str, Any] = {"probe_index": seed}
            try:
                block_vector.array[:] = w
                matrix.mult(block_vector, block_rhs)
                global_vector = make_vector()
                global_vector.set(0)
                global_vector.array[selected] = w
                if slave_indices.size:
                    global_vector.array[slave_indices] = 0.0
                source_before = np.array(global_vector.array, copy=True)
                native_value = apply_owned(native_a4, global_vector)
                if not np.array_equal(global_vector.array, source_before):
                    raise ValueError("native A4 modified a block-witness input")
                native_norm = float(np.linalg.norm(native_value.array[selected]))
                block_norm = float(np.linalg.norm(block_rhs.array))
                operation_scale = max(native_norm + block_norm, np.finfo(float).tiny)
                difference_norm = float(np.linalg.norm(native_value.array[selected] - block_rhs.array))
                defect = float(difference_norm / operation_scale)
                probe_fact.update(
                    native_norm=native_norm,
                    block_norm=block_norm,
                    difference_norm=difference_norm,
                    operation_scale=operation_scale,
                    relative_residual=defect,
                    block_rhs_sha256=hashlib.sha256(
                        np.ascontiguousarray(block_rhs.array).tobytes()).hexdigest(),
                    residual_sha256=hashlib.sha256(
                        np.ascontiguousarray(
                            native_value.array[selected] - block_rhs.array
                        ).tobytes()).hexdigest(),
                )
                if not np.isfinite(defect) or defect > 1.0e-10:
                    raise ValueError(f"native A4 block witness residual {defect} exceeds 1e-10")
                defects.append(defect)
                operation_scales.append(operation_scale)
                probe_facts.append(probe_fact)
            except BaseException as exc:
                _save(save, f"macro_block_{block_index:02d}_native_witness_failure"
                      if block_index is not None else "macro_native_witness_failure", {
                    "identity": dict(identity or {}),
                    "probe": w.copy(),
                    "block_rhs": block_rhs.array.copy(),
                    "native_values": native_value.array.copy() if native_value is not None else None,
                    "probe_facts": probe_fact,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                })
                raise
            finally:
                block_vector.destroy()
                block_rhs.destroy()
                if global_vector is not None:
                    global_vector.destroy()
                if native_value is not None:
                    native_value.destroy()
        return {
            "fixed_vectors": 3,
            "relative_residuals": defects,
            "operation_scales": operation_scales,
            "probe_facts": probe_facts,
            "limit": 1.0e-10,
            "restriction": "R_i",
            "embedding": "R_i^H",
            "global_matrix": False,
            "global_column_probe": False,
        }

    def add_dtn_terms(
        self, carrier: Any, *, native_a4: Any,
        save: Callable[[str, Mapping[str, Any]], Any] | None = None,
        block_indices: Any | None = None,
        memory_policy: str | None = None,
        skip_existing: bool = True,
    ) -> None:
        """Assemble and retain one qualified sparse MUMPS factor per block.

        ``block_indices`` is the bounded V11 calibration path.  It assembles
        the same production block from the same local metadata while leaving
        the other 39 blocks unfactored; the normal call still assembles all
        42 blocks and therefore retains the original V10 behavior.
        """

        from petsc4py import PETSc

        from .fullspace_bounded_mumps import BoundedP1Factor

        all_indices = set(range(len(self.blocks)))
        if block_indices is None:
            selected_block_indices = all_indices
        else:
            selected_block_indices = {int(index) for index in block_indices}
            if not selected_block_indices or not selected_block_indices <= all_indices:
                raise ValueError("calibration block selection is empty or out of range")
        active_memory_policy = self.memory_policy if memory_policy is None else memory_policy
        self._last_factor_selection = tuple(sorted(selected_block_indices))

        dtn_identity_arrays: dict[str, Any] = {}
        for entry_index, entry in enumerate(carrier.entries):
            dtn_identity_arrays.update({
                f"{entry_index}:coupling_rows": entry.coupling_rows,
                f"{entry_index}:coupling_values": entry.coupling_values,
                f"{entry_index}:projection_rows": entry.projection_rows,
                f"{entry_index}:projection_values": entry.projection_values,
                f"{entry_index}:normalization": np.asarray(
                    [entry.normalization_h], dtype=np.float64),
            })
        dtn_identity_sha256 = _identity_hash_arrays(dtn_identity_arrays)
        self.dtn_identity_sha256 = dtn_identity_sha256
        representative_by_category = self._select_representative_blocks(carrier)
        self.representative_block_indices = dict(representative_by_category)
        representative_blocks = set(representative_by_category.values())
        representative_categories: dict[int, list[str]] = {}
        for category, block_index in representative_by_category.items():
            representative_categories.setdefault(block_index, []).append(category)
        _save(save, "macro_representative_blocks", {
            "selection": "canonical_seed_by_current_material_and_DtN_support",
            "categories": {
                category: {
                    "block_index": int(block_index),
                    "canonical_seed_key": list(self.blocks[block_index]["seed"]),
                }
                for category, block_index in representative_by_category.items()
            },
            "selection_notes": dict(getattr(self, "representative_selection_notes", {})),
            "native_global_matrix": False,
            "global_column_probe": False,
        })
        for index, block in enumerate(self.blocks):
            if index not in selected_block_indices:
                continue
            existing_factor = block.get("factor")
            existing_matrix = block.get("matrix")
            if existing_factor is not None or existing_matrix is not None:
                if not skip_existing:
                    raise RuntimeError(f"macro block {index} already owns a factor or matrix")
                if existing_factor is None or existing_matrix is None:
                    raise RuntimeError(f"macro block {index} has incomplete factor ownership")
                existing_policy = getattr(existing_factor, "audit", {}).get("memory_policy")
                if existing_policy != active_memory_policy:
                    raise RuntimeError(
                        f"macro block {index} already uses memory policy {existing_policy!r}"
                    )
                continue
            selected = np.asarray(block["indices"], dtype=np.int64)
            if selected.size == 0 or selected.size > LOCAL_ROWS_CAP:
                raise MemoryError(f"macro block {index} has an invalid row count")
            position = {int(row): i for i, row in enumerate(selected.tolist())}
            cell_terms = []
            row_pattern = [{row} for row in range(selected.size)]
            for cell in block["support_cells"]:
                local_rows, block_positions, local_values = [], [], []
                for local, (ids, values) in enumerate(self.cell_expansions[int(cell)]):
                    for row, value in zip(ids, values, strict=True):
                        position_index = position.get(int(row))
                        if position_index is not None:
                            local_rows.append(local)
                            block_positions.append(position_index)
                            local_values.append(value)
                if not block_positions:
                    continue
                cell_positions = np.unique(np.asarray(block_positions, dtype=np.int64))
                for row in cell_positions:
                    row_pattern[int(row)].update(int(value) for value in cell_positions)
                cell_terms.append((int(cell), local_rows, block_positions, local_values, cell_positions))
            dtn_terms = []
            for entry in carrier.entries:
                c_indices, c_values, p_indices, p_values = [], [], [], []
                for row, value in zip(entry.coupling_rows, entry.coupling_values, strict=True):
                    if int(row) in position and value != 0:
                        c_indices.append(position[int(row)]); c_values.append(value)
                for row, value in zip(entry.projection_rows, entry.projection_values, strict=True):
                    if int(row) in position and value != 0:
                        p_indices.append(position[int(row)]); p_values.append(value)
                if c_indices and p_indices:
                    for row in c_indices:
                        row_pattern[row].update(p_indices)
                    dtn_terms.append((
                        np.asarray(c_indices, dtype=np.int64), np.asarray(c_values, dtype=np.complex128),
                        np.asarray(p_indices, dtype=np.int64), np.asarray(p_values, dtype=np.complex128),
                        float(entry.normalization_h),
                    ))
            index_bytes = np.dtype(PETSc.IntType).itemsize
            scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
            estimated_matrix_bytes = int(sum(len(row) for row in row_pattern) * (index_bytes + scalar_bytes)
                                         + (selected.size + 1) * index_bytes)
            resource = self.sample()
            base_resident = self._resident_bytes()
            # The retained-resident gate charges the matrix once.  PETSc's
            # allocation workspace and the explicit temporary copy are
            # transient and belong to the RSS/launch-cap gate below, not to
            # the 2 GiB retained-cache policy.
            if base_resident + estimated_matrix_bytes > self.local_inventory_cap_bytes:
                raise MemoryError("macro block resident policy rejects sparse allocation")
            if not isinstance(resource, Mapping):
                raise TypeError("macro block resource sample is not a mapping")
            required = ("rss_bytes", "launch_cap_bytes", "all_status_readable", "swap_bytes")
            if any(key not in resource for key in required):
                raise RuntimeError("macro block resource sample is missing an authoritative field")
            if (not resource["all_status_readable"] or int(resource["swap_bytes"]) != 0
                    or int(resource["rss_bytes"]) + 2 * estimated_matrix_bytes + LOCAL_TEMP_RESERVE
                    >= int(resource["launch_cap_bytes"])):
                raise MemoryError("macro block temporary reserve exceeds the measured workflow cap")

            matrix = factor = None
            try:
                nnz = np.asarray([max(1, len(row)) for row in row_pattern], dtype=PETSc.IntType)
                matrix = PETSc.Mat().createAIJ([selected.size, selected.size], nnz=nnz,
                                               comm=self.levels["mesh"].comm)
                matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
                for cell, local_rows, block_positions, local_values, cell_positions in cell_terms:
                    item = self.classes[self.cell_classes[cell]]
                    local_dimension = int(item.A.shape[0])
                    if local_dimension != len(self.cell_expansions[cell]):
                        raise ValueError("macro cell expansion and current cell matrix dimensions differ")
                    compact = {int(value): i for i, value in enumerate(cell_positions.tolist())}
                    E = np.zeros((local_dimension, cell_positions.size), dtype=np.complex128)
                    for local, block_position, value in zip(local_rows, block_positions, local_values, strict=True):
                        E[local, compact[int(block_position)]] += value
                    local_contribution = E.conj().T @ item.A @ E
                    pet_cell_positions = np.asarray(cell_positions, dtype=PETSc.IntType)
                    matrix.setValues(pet_cell_positions, pet_cell_positions, local_contribution,
                                     addv=PETSc.InsertMode.ADD_VALUES)
                for c_indices, c_values, p_indices, p_values, normalization in dtn_terms:
                    contribution = np.outer(c_values, p_values) / normalization
                    matrix.setValues(np.asarray(c_indices, dtype=PETSc.IntType),
                                     np.asarray(p_indices, dtype=PETSc.IntType), contribution,
                                     addv=PETSc.InsertMode.ADD_VALUES)
                matrix.assemble()
                csr_indptr, csr_indices, csr_values = matrix.getValuesCSR()
                csr_structure_sha256 = _identity_hash_arrays({
                    "indptr": csr_indptr, "indices": csr_indices,
                })
                csr_values_sha256 = _identity_hash_arrays({
                    "indptr": csr_indptr, "indices": csr_indices, "values": csr_values,
                })
                block_identity = {
                    "block_index": int(index),
                    "seed": list(block["seed"]),
                    "block_indices_sha256": _identity_hash_arrays({"indices": selected}),
                    "support_cells_sha256": _identity_hash_arrays({
                        "support_cells": np.asarray(block["support_cells"], dtype=np.int32),
                    }),
                    "mapping_identity_sha256": self.mapping_identity_sha256,
                    "cell_class_identity_sha256": self.cell_class_identity_sha256,
                    "dtn_identity_sha256": dtn_identity_sha256,
                    "csr_structure_sha256": csr_structure_sha256,
                    "csr_values_sha256": csr_values_sha256,
                }
                block["identity"] = block_identity
                block["csr_structure_sha256"] = csr_structure_sha256
                block["csr_values_sha256"] = csr_values_sha256
                matrix_info = matrix.getInfo()
                block["matrix_storage_bytes"] = int(matrix_info["nz_allocated"] *
                                                     (np.dtype(PETSc.IntType).itemsize + np.dtype(PETSc.ScalarType).itemsize)
                                                     + (selected.size + 1) * np.dtype(PETSc.IntType).itemsize)
                resident_before_factor = self._resident_bytes()
                def pre_numeric_gate(
                    facts: dict[str, Any], *, block_index=index,
                    resident_before_factor_bytes=resident_before_factor,
                    block_ref=block,
                ) -> None:
                    estimated = int(facts["factor_estimated_padded_bytes"])
                    predicted = int(facts.get(
                        "factor_requested_padded_bytes", estimated,
                    ))
                    current = self.sample()
                    gate_facts = {
                        "block": block_index,
                        "resident_before_factor_bytes": resident_before_factor_bytes,
                        "matrix_storage_bytes": block_ref["matrix_storage_bytes"],
                        "factor_estimated_padded_bytes": estimated,
                        "factor_requested_padded_bytes": facts.get(
                            "factor_requested_padded_bytes", predicted),
                        "resident_cap_bytes": self.local_inventory_cap_bytes,
                        "temporary_workspace_reserve_bytes": LOCAL_TEMP_RESERVE,
                        "resource": current,
                        "classification": "derived_local_factor_pre_numeric_gate",
                    }
                    _save(save, f"macro_block_{block_index:02d}_symbolic_gate", gate_facts)
                    if (resident_before_factor_bytes + predicted > self.local_inventory_cap_bytes
                            or not current.get("all_status_readable", False)
                            or int(current.get("swap_bytes", 1)) != 0
                            or int(current.get("rss_bytes", 0)) + predicted + LOCAL_TEMP_RESERVE
                            >= int(current.get("launch_cap_bytes", 0))):
                        raise MemoryError("macro symbolic factor exceeds the local or workflow gate")
                factor = BoundedP1Factor(
                    matrix, label=f"macro_block_{index:02d}", resource_sample=self.sample,
                    marker=lambda name, facts, block_index=index:
                        self.marker(name, dict(block=block_index, **facts)),
                    physical_p2_pilot=False, extra_local_bytes=0,
                    pre_numeric_gate=pre_numeric_gate,
                    memory_policy=active_memory_policy,
                )
                factor_facts = dict(backend="petsc_mumps", **factor.audit)
                _save(save, f"macro_block_{index:02d}_numeric", {
                    "block_index": int(index),
                    "identity": block_identity,
                    "factor": factor_facts,
                    "memory_policy": active_memory_policy,
                })
                block["factor_reported_bytes"] = int(max(
                    factor.audit.get("factor_reported_allocated_padded_bytes", 0),
                    factor.audit.get("factor_reported_used_padded_bytes", 0),
                ))
                block["backsolve"] = self._mumps_backsolve_gate(
                    matrix, factor, save=save, block_index=index, identity=block_identity,
                )
                factor_facts.update(block["backsolve"])
                _save(save, f"macro_block_{index:02d}_backsolve", {
                    "block_index": int(index),
                    "identity": block_identity,
                    "backsolve": block["backsolve"],
                    "factor": factor_facts,
                })
                post_backsolve_raw = factor.factor.info(
                    extra_indices=(21, 22, 29),
                    include_local=active_memory_policy == "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
                )
                post_allocated = BoundedP1Factor._mb_upper(post_backsolve_raw, "19")
                post_used = BoundedP1Factor._mb_upper(post_backsolve_raw, "22")
                post_reported = max(post_allocated, post_used)
                post_conservative = int(factor.audit["matrix_storage_budget_bytes"] + post_reported)
                post_resource = self.sample()
                block["factor_reported_bytes"] = max(
                    int(block.get("factor_reported_bytes", 0)), post_reported
                )
                post_inventory = int(self._resident_bytes())
                post_inventory_gate = {
                    "matrix_plus_reported_factor_bytes": post_conservative,
                    "retained_inventory_bytes": post_inventory,
                    "local_factor_cap_bytes": self.local_inventory_cap_bytes,
                    "factor_hard_cap_bytes": 512 * 1024**2,
                    "resource": post_resource,
                    "allocated_padded_bytes": post_allocated,
                    "used_padded_bytes": post_used,
                    "offset_policy": "none; allocated/used are both preserved",
                    "stage": "after_first_backsolve_before_next_gate",
                }
                _save(save, f"macro_block_{index:02d}_post_backsolve_inventory", {
                    "block_index": int(index),
                    "resident_bytes": post_inventory,
                    "numeric_raw": factor.audit.get("numeric_raw"),
                    "post_backsolve_raw": post_backsolve_raw,
                    "post_backsolve_gate": post_inventory_gate,
                })
                if (post_conservative > 512 * 1024**2
                        or post_inventory > self.local_inventory_cap_bytes
                        or not post_resource.get("all_status_readable", False)
                        or int(post_resource.get("swap_bytes", 1)) != 0
                        or int(post_resource.get("rss_bytes", 0)) + LOCAL_TEMP_RESERVE
                        >= int(post_resource.get("launch_cap_bytes", 0))):
                    raise MemoryError(
                        "macro post-backsolve conservative inventory/resource gate failed"
                    )
                block["matrix"] = matrix
                block["factor"] = factor
                block["factor_backend"] = factor_facts["backend"]
                block["dtn_terms"] = len(dtn_terms)
                block["resident_bytes"] = int(
                    block["matrix_storage_bytes"] + block["factor_reported_bytes"] + selected.nbytes
                )
                retained_after_factor = self._resident_bytes()
                if retained_after_factor > self.local_inventory_cap_bytes:
                    raise MemoryError(
                        "macro retained resident policy exceeded after block factorization"
                    )
                self.resident_bytes = retained_after_factor
                if index in representative_blocks:
                    block["representative_categories"] = tuple(representative_categories[index])
                    block["native_witness"] = self._native_block_witness(
                        block, selected, matrix, native_a4, save=save,
                        block_index=index, identity=block_identity,
                    )
                    _save(save, f"macro_block_{index:02d}_native", {
                        "block_index": int(index),
                        "identity": block_identity,
                        "native_witness": block["native_witness"],
                    })
            except BaseException:
                # The block dictionary becomes the sole owner as soon as the
                # handles are attached.  Clear those references before
                # destruction so the outer stack cleanup cannot destroy the
                # same PETSc object a second time.
                if block.get("factor") is factor:
                    block["factor"] = None
                if block.get("matrix") is matrix:
                    block["matrix"] = None
                if factor is not None:
                    factor.destroy()
                    factor = None
                if matrix is not None:
                    matrix.destroy()
                    matrix = None
                raise
            post_resource = self.sample()
            if (not isinstance(post_resource, Mapping)
                    or not post_resource.get("all_status_readable", False)
                    or int(post_resource.get("swap_bytes", 1)) != 0
                    or int(post_resource.get("rss_bytes", 0)) + LOCAL_TEMP_RESERVE
                    >= int(post_resource.get("launch_cap_bytes", 0))):
                if factor is not None:
                    if block.get("factor") is factor:
                        block["factor"] = None
                    factor.destroy()
                    factor = None
                if matrix is not None:
                    if block.get("matrix") is matrix:
                        block["matrix"] = None
                    matrix.destroy()
                    matrix = None
                raise MemoryError("macro block post-factor resource gate failed")
            _save(save, f"macro_block_{index:02d}", {
                "seed_group": list(block["seed"]),
                "seed_cells": list(block["seed_cells"]),
                "support_cell_count": len(block["support_cells"]),
                "rows": int(selected.size),
                "volume_terms": int(block["volume_terms"]),
                "dtn_terms": len(dtn_terms),
                "factor": factor_facts,
                "identity": block.get("identity"),
                "csr_structure_sha256": block.get("csr_structure_sha256"),
                "csr_values_sha256": block.get("csr_values_sha256"),
                "factor_backend": factor_facts["backend"],
                "full_support": True,
                "representative_categories": list(block.get("representative_categories", ())),
                "canonical_seed_key": list(block["seed"]),
                "native_witness": block.get("native_witness"),
            })
        if selected_block_indices != all_indices:
            self.calibration_coverage = {
                "block_count": len(selected_block_indices),
                "selected_blocks": sorted(selected_block_indices),
                "complete_production_coverage": False,
                "resident_bytes": int(self._resident_bytes()),
                "memory_policy": active_memory_policy,
            }
            _save(save, "macro_calibration_coverage", self.calibration_coverage)
            return

        # Independent coordinates are not necessarily numbered 0..Nind-1.
        # Keep a global-row weight array for direct p4 indexing instead of
        # applying a second input-side weight.
        n = len(self.mapping["offsets"]) - 1
        multiplicity = np.zeros(n, dtype=np.int32)
        for block in self.blocks:
            multiplicity[block["indices"]] += 1
        independent = np.asarray(self.mapping["independent_indices"], dtype=np.int64)
        if np.any(multiplicity[independent] == 0):
            raise ValueError("macro block coverage omitted an independent p4 row")
        self.output_weights = np.zeros(n, dtype=np.float64)
        self.output_weights[independent] = 1.0 / multiplicity[independent].astype(np.float64)
        self.resident_bytes = self._resident_bytes()
        if self.resident_bytes > self.local_inventory_cap_bytes:
            raise MemoryError("macro local block resident policy exceeds its explicit cap")
        self.coverage = {
            "block_count": len(self.blocks),
            "independent_rows": int(independent.size),
            "covered_rows": int(np.count_nonzero(multiplicity[independent])),
            "multiplicity_min": int(multiplicity[independent].min()),
            "multiplicity_max": int(multiplicity[independent].max()),
            "support_cell_total": int(sum(len(block["support_cells"]) for block in self.blocks)),
            "rows_max": int(max(len(block["indices"]) for block in self.blocks)),
            "resident_bytes": int(self.resident_bytes),
            "dtn_mode_count": len(carrier.entries),
            "input_weighting": "none",
            "output_weighting": "1/multiplicity",
        }
        _save(save, "macro_coverage", self.coverage)

    def release_block_factors(self, block_indices: Any | None = None) -> None:
        """Release selected block matrices/factors exactly once.

        Calibration runs call this between the old and V11 policies.  The
        compact lifecycle facts remain on the block, while all PETSc handles
        are removed before their destroy calls.
        """
        if block_indices is None:
            selected = range(len(self.blocks))
        else:
            selected = [int(index) for index in block_indices]
        for index in selected:
            block = self.blocks[index]
            factor = block.pop("factor", None)
            matrix = block.pop("matrix", None)
            if factor is not None:
                factor.destroy()
            if matrix is not None:
                matrix.destroy()
            block.pop("factor_backend", None)
            block.pop("factor_reported_bytes", None)
            block.pop("matrix_storage_bytes", None)
            block.pop("resident_bytes", None)
        self.resident_bytes = self._resident_bytes()

    def build_w_transfer(self) -> Any:
        """Build the current-material W/P transfer used by the real C_U."""

        from .fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
        from .fullspace_same_mesh_hcurl_pmg import build_same_mesh_hcurl_transfer
        from .fullspace_same_mesh_hcurl_pmg_runtime import SameMeshHcurlOwnerTransfer

        def provider(cell: int, info: int, base: np.ndarray) -> np.ndarray:
            item = self.classes[self.cell_classes[int(cell)]]
            if int(info) != int(item.identity["orientation"]):
                raise ValueError("current W transfer cell orientation differs")
            # Nedelec vertex dofs are empty.  Convert every entity list to a
            # typed integer array before concatenating so the empty vertex
            # list cannot promote the edge/face indices to float64.
            boundary_parts = [
                np.asarray(entity, dtype=np.int64).reshape(-1)
                for dimension in (0, 1, 2)
                for entity in self.element.entity_dofs[dimension]
            ]
            boundary = (
                np.unique(np.concatenate(boundary_parts))
                if boundary_parts else np.empty(0, dtype=np.int64)
            )
            if np.linalg.norm((item.W - base)[boundary]) > 1.0e-12 * max(np.linalg.norm(base), 1.0):
                raise ValueError("macro W changed the p4 trace rows")
            return item.W

        owner = SameMeshHcurlOwnerTransfer(
            self.levels["spaces"][4], self.levels["floquets"][4],
            self.levels["spaces"][2], self.levels["floquets"][2],
            build_same_mesh_hcurl_transfer(4, 2), cell_matrix_provider=provider,
            fixed_serial_owner_route=True,
        )
        self.owner = owner
        self.transfer = AlgebraicOwnerTransfer(owner)
        self._check_resident_gate("after_w_transfer")
        return self.transfer

    def build_cached_action(self, dtn: Any, *, sample: Callable[[], Any]) -> Any:
        """Attach the qualified cached cell-volume plus current-DtN action."""

        from .physical_trace_entity import CachedPhysicalTraceAction

        # The dictionaries are only a mapping view; their ``A`` values point
        # at the retained class arrays and do not copy the matrices.
        self.cached_classes = {key: {"A": item.A} for key, item in self.classes.items()}
        self.cached_action = CachedPhysicalTraceAction(
            self.mapping,
            self.cell_classes,
            self.cached_classes,
            dtn,
            lifecycle="formal",
            safe_checkpoint=sample,
        )
        self._check_resident_gate("after_cached_action")
        return self.cached_action

    def insert_volume(self, volume: Any, space: Any, mpc: Any) -> None:
        """Insert the current ``delta = W^H A W - P^H A P`` into p2 volume."""

        from petsc4py import PETSc

        from .fullspace_same_mesh_hcurl_pmg_p6 import (
            _cell_expansion_workspace,
            _fill_cell_expansion,
        )
        from .physical_bubble_global import constrained_cell_correction

        imap = mpc.function_space.dofmap.index_map
        storage = imap.size_local + imap.num_ghosts
        _, mask, targets, coefficients = _cell_expansion_workspace(mpc, storage, 54)
        self.sample()
        for cell, key in enumerate(self.cell_classes):
            dofs = space.dofmap.cell_dofs(cell)
            _fill_cell_expansion(dofs, mpc, storage, mask, targets, coefficients)
            rows, local_delta = constrained_cell_correction(
                self.classes[key].delta, targets, coefficients
            )
            global_rows = imap.local_to_global(rows.astype(np.int32)).astype(PETSc.IntType)
            volume.setValues(global_rows, global_rows, local_delta, addv=PETSc.InsertMode.ADD_VALUES)
        volume.assemble()
        self.sample()

    def build_s_action(self, a4: Any, levels: Mapping[str, Any]) -> MacroSchurAction:
        if not hasattr(self, "transfer"):
            raise RuntimeError("W transfer must be built before the Schur action")
        return MacroSchurAction(self.transfer, a4, levels)

    def coarse_restriction(self, value: Any) -> np.ndarray:
        """Return the existing ``W^H`` restriction plus all ``Q^H`` responses.

        The p2 part is the already-qualified owner restriction.  The appended
        cell responses are the same local interior ``Q^H value`` quantities
        used by the existing bounded runtime; they close the C_U balance
        without introducing a second projection space.
        """

        coarse = self.transfer.apply_adjoint(value)
        try:
            expanded = self._expanded(value.array)
            internal = np.concatenate([
                item.Q.conj().T @ expanded[rows]
                for rows, item in zip(
                    self.dofmap,
                    (self.classes[key] for key in self.cell_classes),
                    strict=True,
                )
            ])
            result = np.concatenate([np.array(coarse.array, copy=True), internal])
            if not np.isfinite(result).all():
                raise ValueError("macro coarse restriction returned non-finite values")
            return result
        finally:
            coarse.destroy()

    def _expanded(self, array: np.ndarray) -> np.ndarray:
        from .physical_bubble_particular import expand_primal

        return expand_primal(np.asarray(array, dtype=np.complex128), self.mapping)

    def internal_array(self, array: np.ndarray) -> np.ndarray:
        self.sample()
        expanded = self._expanded(array)
        out = np.zeros_like(expanded)
        for cell, rows in enumerate(self.dofmap):
            item = self.classes[self.cell_classes[cell]]
            rhs = item.Q.conj().T @ expanded[rows]
            alpha = lu_solve(item.factor, rhs)
            np.add.at(out, rows, item.Q @ alpha)
        result = self.project_dual(out, self.mapping)
        self.sample()
        return result

    def volume_array(self, array: np.ndarray) -> np.ndarray:
        self.sample()
        expanded = self._expanded(array)
        out = np.zeros_like(expanded)
        for cell, rows in enumerate(self.dofmap):
            item = self.classes[self.cell_classes[cell]]
            np.add.at(out, rows, item.A @ expanded[rows])
        result = self.project_dual(out, self.mapping)
        self.sample()
        return result

    def md_array(self, array: np.ndarray) -> np.ndarray:
        if not hasattr(self, "output_weights"):
            raise RuntimeError("macro DtN blocks have not been finalized")
        array = np.asarray(array, dtype=np.complex128)
        if array.shape != (len(self.mapping["offsets"]) - 1,) or not np.isfinite(array).all():
            raise ValueError("M_D input has incompatible shape or non-finite values")
        out = np.zeros_like(array)
        for block in self.blocks:
            self.sample()
            indices = np.asarray(block["indices"], dtype=np.int64)
            factor = block["factor"]
            if hasattr(factor, "solve_lean"):
                rhs = block["matrix"].createVecRight()
                rhs.array[:] = array[indices]
                solution = None
                try:
                    solution, _ = factor.solve_lean(rhs)
                    np.add.at(out, indices, self.output_weights[indices] * solution.array)
                finally:
                    rhs.destroy()
                    if solution is not None:
                        solution.destroy()
            else:
                raise RuntimeError(
                    "formal M_D requires the qualified PETSc/MUMPS block factor"
                )
        out[np.asarray(self.mapping["slaves"], dtype=np.int64)] = 0.0
        return out

    def destroy(self) -> None:
        owner = getattr(self, "owner", None)
        if owner is not None:
            owner.destroy()
            self.owner = None
        for block in getattr(self, "blocks", ()):
            factor = block.get("factor")
            if hasattr(factor, "destroy"):
                factor.destroy()
            matrix = block.get("matrix")
            if hasattr(matrix, "destroy"):
                matrix.destroy()
            block["factor"] = None
            block["matrix"] = None
        cached_action = getattr(self, "cached_action", None)
        if cached_action is not None:
            cached_action.dtn = None
            self.cached_action = None
        if hasattr(self, "cached_classes"):
            self.cached_classes.clear()
        self.classes.clear()
        self.blocks.clear()
        self.cell_classes = ()
        self.cell_expansions = []
        self.cell_active = []
        self.cell_coordinates = []
        self.cell_coordinates_array = np.empty((0, 3), dtype=np.int32)
        self.cell_tags = np.empty(0, dtype=np.int32)
        self.cell_min_points = np.empty((0, 3), dtype=np.float64)
        self.cell_max_points = np.empty((0, 3), dtype=np.float64)
        self.representative_block_indices = {}
        self.representative_selection_notes = {}
        self.output_weights = np.empty(0, dtype=np.float64)


class MacroInternalResponse:
    def __init__(self, local: MacroLocalVolume, levels: Mapping[str, Any]):
        from .fullspace_physical_intermediate_runtime import level_vector

        self.local = local
        self.levels = levels
        self.calls = 0
        self._make = lambda: level_vector(levels, 4)

    def apply(self, source: Any) -> Any:
        target = self._make()
        try:
            target.array[:] = self.local.internal_array(source.array)
            self.calls += 1
            result = target
            target = None
            return result
        finally:
            if target is not None:
                target.destroy()


class MacroVolume:
    def __init__(self, local: MacroLocalVolume, levels: Mapping[str, Any]):
        from .fullspace_physical_intermediate_runtime import level_vector

        self.local = local
        self._make = lambda: level_vector(levels, 4)
        self.calls = 0

    def apply(self, source: Any) -> Any:
        target = self._make()
        try:
            target.array[:] = self.local.volume_array(source.array)
            self.calls += 1
            result = target
            target = None
            return result
        finally:
            if target is not None:
                target.destroy()


class MacroAdditiveInverse:
    """Matrix-free ``M_D`` wrapper with visible local-solve accounting."""

    def __init__(self, local: MacroLocalVolume, levels: Mapping[str, Any]):
        from .fullspace_physical_intermediate_runtime import level_vector

        self.local = local
        self._make = lambda: level_vector(levels, 4)
        self.calls = 0
        self.local_solves = 0
        self.seconds = 0.0

    def apply(self, source: Any) -> Any:
        started = time.perf_counter()
        target = self._make()
        try:
            target.array[:] = self.local.md_array(source.array)
            self.calls += 1
            self.local_solves += len(self.local.blocks)
            result = target
            target = None
            return result
        finally:
            if target is not None:
                target.destroy()
            self.seconds += time.perf_counter() - started


class MacroSchurAction:
    """Current ``W^H A4 W`` action used by the S/p2 C_U factor."""

    def __init__(self, transfer: Any, a4: Any, levels: Mapping[str, Any]):
        from .fullspace_physical_intermediate_runtime import level_vector

        self.transfer = transfer
        self.a4 = a4
        self._make = lambda: level_vector(levels, 2)
        self.calls = 0

    def apply(self, source: Any) -> Any:
        fine = image = None
        try:
            fine = self.transfer.apply_primal(source)
            image = _apply_owned(self.a4, fine)
            target = self.transfer.apply_adjoint(image)
            self.calls += 1
            return target
        finally:
            if fine is not None:
                fine.destroy()
            if image is not None:
                image.destroy()

    def apply_into(self, source: Any, target: Any) -> None:
        value = self.apply(source)
        try:
            value.copy(target)
        finally:
            value.destroy()


class MacroCoarse:
    """The existing actual ``complete_pq`` action, kept separate from DD4."""

    def __init__(self, local: MacroLocalVolume, internal: MacroInternalResponse, volume: MacroVolume,
                 levels: Mapping[str, Any], transfer: Any, p2_inverse: Any):
        self.local = local
        self.internal = internal
        self.volume = volume
        self.levels = levels
        self.transfer = transfer
        self.p2_inverse = p2_inverse
        self.calls = 0

    def apply(self, source: Any) -> Any:
        internal = value = residual = rhs = coarse = None
        correction = None
        try:
            internal = self.internal.apply(source)
            value = self.volume.apply(internal)
            residual = source.copy()
            residual.axpy(-1.0, value)
            rhs = self.transfer.apply_adjoint(residual)
            coarse = self.p2_inverse.apply(rhs)
            correction = self.transfer.apply_primal(coarse)
            correction.axpy(1.0, internal)
            self.calls += 1
            result = correction
            correction = None
            return result
        finally:
            for item in (internal, value, residual, rhs, coarse):
                if item is not None:
                    item.destroy()
            if correction is not None:
                correction.destroy()


def _apply_owned(action: Any, source: Any) -> Any:
    from .fullspace_physical_intermediate import apply_owned

    value = apply_owned(action, source)
    return value


class MacroI4:
    """One zero-start right FGMRES(4) action using the new B4."""

    def __init__(
        self,
        cached_a4: Any,
        native_a4: Any,
        b4: Any,
        *,
        sample: Callable[[], Any],
        save: Callable[[str, Mapping[str, Any]], Any] | None = None,
        stop_requested: Callable[[], bool] = lambda: False,
    ):
        from .physical_bounded_policy import BoundedI4Admission

        self.cached_a4 = cached_a4
        self.native_a4 = native_a4
        self.b4 = b4
        self.sample = sample
        self.save = save
        self.stop_requested = stop_requested
        self.calls = 0
        self.records: list[dict[str, Any]] = []
        self.admission = BoundedI4Admission(
            lambda value: _apply_owned(self.cached_a4, value),
            self.b4.apply,
            sample=sample,
            save=save or (lambda _name, _facts: None),
            stop_requested=stop_requested,
            residual_action=lambda value: _apply_owned(self.native_a4, value),
            macro_policy=True,
        )

    def apply(self, rhs: Any) -> dict[str, Any]:
        self.calls += 1
        result = self.admission(rhs)
        self.records.append(dict(result["facts"]))
        return result


def destroy_macro_stack(stack: dict[str, Any]) -> None:
    """Release every owned object from a partial or completed macro build."""

    ledger = stack.pop("outer_ledger", None)
    if ledger is not None:
        ledger.destroy()
    bottom = stack.pop("p2_inverse", None)
    if bottom is not None:
        bottom.destroy()
    matrix = stack.pop("p2_matrix", None)
    if matrix is not None:
        matrix.destroy()
    local = stack.pop("local", None)
    if local is not None:
        local.destroy()
    actions = stack.pop("actions", None)
    if actions is not None:
        from .fullspace_physical_intermediate_runtime import (
            destroy_physical_intermediate_actions,
        )
        destroy_physical_intermediate_actions(actions)
    fine = stack.pop("fine", None)
    if fine is not None:
        from .fullspace_same_mesh_hcurl_pmg_physical import (
            destroy_same_mesh_physical_action,
        )
        destroy_same_mesh_physical_action(fine)
    positive = stack.pop("positive", None)
    if positive is not None:
        h6 = positive.pop("h6", None)
        if h6 is not None:
            h6.destroy()
        shell = positive.pop("p6_shell", None)
        if shell is not None:
            shell.destroy()
    stack.clear()


def release_macro_auxiliary_for_recovery(stack: dict[str, Any]) -> dict[str, Any]:
    """Release DD4/outer storage while retaining only the p6 recovery bundle.

    Official output recovery evaluates the already-solved p6 field and does
    not need the local factors, C_U, p4 actions, positive hierarchy, or outer
    bookkeeping.  Keeping those objects live during post-processing would
    turn a valid solve into an avoidable simultaneous-memory violation.
    """

    ledger = stack.pop("outer_ledger", None)
    if ledger is not None:
        ledger.destroy()
    bottom = stack.pop("p2_inverse", None)
    if bottom is not None:
        bottom.destroy()
    matrix = stack.pop("p2_matrix", None)
    if matrix is not None:
        matrix.destroy()
    local = stack.pop("local", None)
    if local is not None:
        local.destroy()
    actions = stack.pop("actions", None)
    if actions is not None:
        from .fullspace_physical_intermediate_runtime import (
            destroy_physical_intermediate_actions,
        )
        quadrature = actions.get("volume_quadrature_metadata")
        stack["recovery_quadrature_metadata"] = quadrature
        destroy_physical_intermediate_actions(actions)
    positive = stack.pop("positive", None)
    if positive is not None:
        h6 = positive.pop("h6", None)
        if h6 is not None:
            h6.destroy()
        shell = positive.pop("p6_shell", None)
        if shell is not None:
            shell.destroy()
    for key in (
        "B4", "a4", "a4_native", "a4_bridge", "internal", "volume",
        "additive", "coarse", "I4", "outer_pc",
    ):
        stack.pop(key, None)
    return stack


def build_macro_stack(
    cfg: Any,
    comm: Any,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Mapping[str, Any]], Any],
    save: Callable[[str, Mapping[str, Any]], Any] | None = None,
    memory_policy: str = "LEGACY_LOCAL_MUMPS_MEMORY_POLICY",
    local_inventory_cap_bytes: int = LOCAL_RESIDENT_CAP,
) -> dict[str, Any]:
    """Build the actual 6/4/2 candidate without an old entity route."""

    owned: dict[str, Any] = {}
    try:
        return _build_macro_stack_impl(
            cfg, comm, sample=sample, marker=marker, save=save, owned=owned,
            memory_policy=memory_policy,
            local_inventory_cap_bytes=local_inventory_cap_bytes,
        )
    except BaseException:
        destroy_macro_stack(owned)
        raise


def _build_macro_stack_impl(
    cfg: Any,
    comm: Any,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Mapping[str, Any]], Any],
    save: Callable[[str, Mapping[str, Any]], Any] | None = None,
    owned: dict[str, Any],
    memory_policy: str = "LEGACY_LOCAL_MUMPS_MEMORY_POLICY",
    local_inventory_cap_bytes: int = LOCAL_RESIDENT_CAP,
) -> dict[str, Any]:
    """Internal builder whose partial ownership is visible to the wrapper."""

    from .fullspace_p4_reference import build_reference_matrix
    from .fullspace_physical_intermediate_runtime import (
        build_physical_intermediate_actions,
        level_vector,
    )
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .physical_balanced_coupling import PhysicalBalancedCoupling
    from .physical_light_setup import build_light_h6_setup
    from .physical_recursive_coarse import PhysicalP2Inverse

    if comm.size != 1:
        raise ValueError("macro stack is MPI1-only")
    levels = _build_same_mesh_levels(cfg, comm, (6, 4, 2))
    owned["levels"] = levels
    positive = build_light_h6_setup(levels, cfg, marker)
    owned["positive"] = positive
    fine = build_same_mesh_physical_action(levels, cfg, 6)
    owned["fine"] = fine
    actions = build_physical_intermediate_actions(
        levels, cfg, fine_bundle=fine, stage_callback=marker, physical_only_degrees=(6, 4, 2)
    )
    owned["actions"] = actions
    local = MacroLocalVolume(
        levels, cfg, actions, sample=sample, marker=marker, save=save,
        memory_policy=memory_policy,
        local_inventory_cap_bytes=local_inventory_cap_bytes,
    )
    owned["local"] = local
    native_a4 = actions["physical"][4]["physical_action"]
    dtn4 = actions["physical"][4]["dtn_action"]
    local.add_dtn_terms(dtn4.carrier, native_a4=native_a4, save=save)
    local.build_w_transfer()
    cached_a4 = local.build_cached_action(dtn4, sample=sample)
    # The cached action borrows the current cell A and the current streaming
    # DtN.  Bind it once to the native FFCx action before it enters B4/I4.
    bridge = level_vector(levels, 4)
    native_value = cached_value = None
    try:
        bridge.array[:] = (
            np.arange(bridge.array.size, dtype=np.float64) + 1.0
            + 1j * (np.arange(bridge.array.size, dtype=np.float64) + 0.5)
        )
        slaves = np.asarray(levels["floquets"][4].mpc.slaves, dtype=np.int64)
        bridge.array[slaves] = 0.0
        bridge_input = np.array(bridge.array, copy=True)
        native_value = _apply_owned(native_a4, bridge)
        cached_value = _apply_owned(cached_a4, bridge)
        difference = float(np.linalg.norm(native_value.array - cached_value.array))
        scale = max(float(np.linalg.norm(native_value.array)), np.finfo(float).tiny)
        bridge_relative = difference / scale
        bridge_facts = {
            "native_operator": "current_ffcx_volume_plus_current_DtN",
            "cached_operator": "cached_current_cell_volume_plus_current_DtN",
            "relative": bridge_relative,
            "absolute": difference,
            "limit": 1.0e-11,
            "source_modified": bool(np.any(bridge.array != bridge_input)),
        }
        _save(save, "macro_cached_native_bridge", bridge_facts)
        if bridge_facts["source_modified"]:
            raise ValueError("cached/native A4 bridge modified its input vector")
        if not np.isfinite(bridge_relative) or bridge_relative > 1.0e-11:
            raise ValueError("cached current A4 does not match native FFCx A4")
    finally:
        bridge.destroy()
        if native_value is not None:
            native_value.destroy()
        if cached_value is not None:
            cached_value.destroy()
    schur_action = local.build_s_action(cached_a4, levels)
    matrix, matrix_facts = build_reference_matrix(
        levels, cfg, actions["physical"][2], actions["volume_quadrature_metadata"],
        marker=marker, sample=sample, degree=2, row_cap=8192,
        cell_volume_correction=local.insert_volume,
        # ``extra_local_bytes`` is part of the p2 512 MiB derived matrix
        # budget.  The DD4 resident policy is independent and already bound
        # by MacroLocalVolume; do not charge it to the bottom factor twice.
        extra_local_bytes=0,
    )
    owned["p2_matrix"] = matrix
    bottom = PhysicalP2Inverse(
        matrix,
        schur_action,
        local.transfer.coarse_slaves,
        sample=sample, marker=marker, save=save,
        action_identity="composed_WHA4W_cached_current_A4", extra_local_bytes=0,
    )
    owned["p2_inverse"] = bottom
    local._check_resident_gate("after_cu")
    internal = MacroInternalResponse(local, levels)
    volume = MacroVolume(local, levels)
    additive = MacroAdditiveInverse(local, levels)
    coarse = MacroCoarse(local, internal, volume, levels, local.transfer, bottom)
    a6 = fine["physical_action"]
    b4 = PhysicalBalancedCoupling(
        lambda value: _apply_owned(cached_a4, value),
        coarse.apply,
        additive.apply,
        local.coarse_restriction,
        route="BAL_H",
        checkpoint=sample,
        level_identity="V10_cached_current_A4_CU_MD",
    )
    owned.update({
        "levels": levels,
        "positive": positive,
        "fine": fine,
        "actions": actions,
        "local": local,
        "p2_matrix": matrix,
        "p2_matrix_facts": matrix_facts,
        "p2_inverse": bottom,
        "internal": internal,
        "volume": volume,
        "additive": additive,
        "coarse": coarse,
        "B4": b4,
        "a4": cached_a4,
        "a4_native": native_a4,
        "a4_bridge": bridge_facts,
        "a6": a6,
        "mode_sha256": fine["mode_sha256"],
    })
    return owned


def build_macro_calibration_context(
    cfg: Any,
    comm: Any,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, Mapping[str, Any]], Any],
    save: Callable[[str, Mapping[str, Any]], Any] | None = None,
    memory_policy: str = "SYMBOLIC_SIZED_LOCAL_MUMPS_V11",
    local_inventory_cap_bytes: int = LOCAL_RESIDENT_CAP,
) -> dict[str, Any]:
    """Build only the shared physical data needed for V11 block calibration.

    The calibration deliberately omits the p2 reference matrix, p2 factor,
    cached/native bridge, and outer framework.  It owns the same mesh, mode
    inventory, local material classes, and DtN carrier used by the production
    macro builder, so old/new factors see byte-identical matrices.
    """
    from .fullspace_physical_intermediate_runtime import build_physical_intermediate_actions
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action

    if comm.size != 1:
        raise ValueError("macro calibration is MPI1-only")
    owned: dict[str, Any] = {}
    try:
        levels = _build_same_mesh_levels(cfg, comm, (6, 4, 2))
        owned["levels"] = levels
        fine = build_same_mesh_physical_action(levels, cfg, 6)
        owned["fine"] = fine
        actions = build_physical_intermediate_actions(
            levels, cfg, fine_bundle=fine, stage_callback=marker,
            physical_only_degrees=(6, 4, 2),
        )
        owned["actions"] = actions
        local = MacroLocalVolume(
            levels, cfg, actions, sample=sample, marker=marker, save=save,
            memory_policy=memory_policy,
            local_inventory_cap_bytes=local_inventory_cap_bytes,
        )
        owned["local"] = local
        native_a4 = actions["physical"][4]["physical_action"]
        dtn4 = actions["physical"][4]["dtn_action"]
        owned.update(native_a4=native_a4, dtn4=dtn4)
        return owned
    except BaseException:
        destroy_macro_stack(owned)
        raise


def make_macro_pc(
    stack: Mapping[str, Any], *, framework: str, sample: Callable[[], Any],
    save: Callable[[str, Mapping[str, Any]], Any] | None = None,
    stop_requested: Callable[[], bool] = lambda: False,
) -> Any:
    """Reuse the common owned BAL_H/ONE_C composition for the outer level."""

    from .physical_balanced_coupling import PhysicalBalancedCoupling
    from .physical_inexact_balance import InexactBalanceLedger

    if framework not in ("BAL_H", "ONE_C"):
        raise ValueError("macro framework must be BAL_H or ONE_C")
    transfer = stack["actions"]["transfers"][(6, 4)]
    i4 = MacroI4(
        stack["a4"], stack["a4_native"], stack["B4"], sample=sample, save=save,
        stop_requested=stop_requested,
    )
    ledger = InexactBalanceLedger(
        lambda value: _apply_owned(stack["a6"], value),
        transfer.apply_adjoint,
        save=save or (lambda _name, _facts: None),
        checkpoint=sample,
        every=32,
        mode="BAL_H" if framework == "BAL_H" else "ONE_C",
    )

    def coarse(source: Any) -> Any:
        rhs = transfer.apply_adjoint(source)
        result = None
        try:
            result = i4.apply(rhs)
            ledger.record(rhs, result["applied"], result["residual"], result["facts"])
            return transfer.apply_primal(result["solution"])
        finally:
            rhs.destroy()
            if result is not None:
                for key in ("solution", "applied", "residual"):
                    result[key].destroy()

    pc = PhysicalBalancedCoupling(
        lambda value: _apply_owned(stack["a6"], value),
        coarse,
        stack["positive"]["h6"].apply,
        transfer.apply_adjoint,
        route=framework,
        checkpoint=sample,
        inexact_ledger=ledger,
        level_identity="V10_outer_cached_i4_with_native_A6_residual",
    )
    stack["I4"] = i4
    stack["outer_ledger"] = ledger
    return pc


__all__ = [
    "MACRO_PROFILE",
    "MACRO_SCHEMA",
    "MacroAdditiveInverse",
    "MacroCoarse",
    "MacroI4",
    "MacroLocalVolume",
    "build_macro_stack",
    "destroy_macro_stack",
    "release_macro_auxiliary_for_recovery",
    "make_macro_pc",
    "output_partition_weights",
]
