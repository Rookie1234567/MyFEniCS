"""Opt-in exact-class local block factors for the Task037 H2A probe.

The cache is deliberately smaller in scope than an assembler or smoother.  A
caller supplies the two local tensors of the frozen coercive proxy
``B0 = K_curl + k0**2 M_|epsilon|``.  The cache owns one LU/pivot pair for
each exact numeric tensor, while an owned cell retains only a class id and
its gather/scatter row indices.  No global matrix, Schur complement, or
per-cell factor is created.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from scipy.linalg import lu_factor, lu_solve

from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _orient_cell_tensor,
    _tabulate_raw_tensor_class,
)

__all__ = (
    "H2AClassBlockSpec",
    "H2AClassFactor",
    "H2ACellReference",
    "H2ACellRecord",
    "HcurlExactClassBlockCache",
    "build_b0_proxy_tensor",
    "build_task037_extra_h2a_block_cache",
    "make_task037_extra_h2a_class_key",
    "make_task037_extra_h2a_constraint_pattern",
    "tabulate_task037_extra_h2a_cell_tensor",
)

H2A_UNIQUE_CLASS_LIMIT = 32
H2A_FACTOR_PAYLOAD_LIMIT_BYTES = 400_000_000


def _freeze_key(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _freeze_key(value.item())
    if isinstance(value, np.ndarray):
        return (
            "ndarray",
            tuple(int(size) for size in value.shape),
            tuple(_freeze_key(item) for item in value.reshape(-1)),
        )
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (
                    _freeze_key(key),
                    _freeze_key(item),
                )
                for key, item in value.items()
            )
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_key(item) for item in value)
    if isinstance(value, complex):
        return (float(value.real), float(value.imag))
    return value


def _key_json(key: tuple[Any, ...]) -> str:
    return json.dumps(
        _freeze_key(key),
        sort_keys=True,
        separators=(",", ":"),
    )


def _complex_pair(value: Any) -> tuple[float, float]:
    number = complex(value)
    if not np.isfinite(number.real) or not np.isfinite(number.imag):
        raise ValueError("H2A constraint coefficients must be finite")
    return float(number.real), float(number.imag)


def _normalize_constraint_pattern(
    pattern: Sequence[Mapping[str, Any]],
) -> tuple[Any, ...]:
    """Freeze local topology and complex expansion semantics in a class key."""

    normalized = []
    for entry in pattern:
        if not isinstance(entry, Mapping):
            raise TypeError("H2A constraint pattern entries must be mappings")
        columns = tuple(
            sorted(
                (
                    int(local_master),
                    _complex_pair(coefficient),
                )
                for local_master, coefficient in entry["columns"]
            )
        )
        normalized.append(
            (
                _freeze_key(entry["topology"]),
                int(entry["local_slave"]),
                ("phase", _complex_pair(entry["phase"])),
                ("columns", columns),
            )
        )
    return tuple(sorted(normalized, key=lambda item: (item[0], item[1])))


def make_task037_extra_h2a_constraint_pattern(
    blocks: Iterable[Any],
    *,
    cell_local_dofs: Sequence[int],
    phase_x: complex,
    phase_y: complex,
    phase_corner: complex | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return the normalized local Floquet expansion for one cell.

    ``blocks`` are the already selected phase-independent topology blocks that
    touch this cell.  The result uses the cell's canonical local DoF ordinals
    and transform-column ordinals only.  It intentionally excludes absolute
    local/global rows, entity IDs, geometry keys, and any owner information;
    those belong to :class:`H2ACellReference`, not an exact class key.
    The actual phase is recorded separately from the phase-independent Basix
    transform so it is not multiplied twice.
    """

    local_rows = tuple(int(value) for value in cell_local_dofs)
    if not local_rows or len(set(local_rows)) != len(local_rows):
        raise ValueError("H2A cell local DoF rows must be unique and nonempty")
    ordinal_by_row = {row: ordinal for ordinal, row in enumerate(local_rows)}
    phases = {
        "x": complex(phase_x),
        "y": complex(phase_y),
        "corner": (
            complex(phase_corner)
            if phase_corner is not None
            else complex(phase_x) * complex(phase_y)
        ),
    }
    result: list[dict[str, Any]] = []
    for block in blocks:
        slave_rows = tuple(int(value) for value in block.slave_local_dofs)
        if not slave_rows:
            continue
        if not all(row in ordinal_by_row for row in slave_rows):
            continue
        transform = np.asarray(block.coefficient_transform, dtype=np.complex128)
        if transform.shape[0] != len(slave_rows):
            raise ValueError("H2A Floquet transform rows do not match local slaves")
        if str(block.kind) not in phases:
            raise ValueError(f"Unsupported H2A Floquet phase kind {block.kind!r}")
        topology = (
            ("entity_kind", str(block.entity_kind)),
            ("direction", str(block.kind)),
            ("vertex_permutation", tuple(int(value) for value in block.entity_vertex_permutation)),
            ("cell_type", str(block.cell_type)),
        )
        for row_index, slave_row in enumerate(slave_rows):
            columns = tuple(
                (column, complex(value))
                for column, value in enumerate(transform[row_index])
                if complex(value) != 0.0 + 0.0j
            )
            result.append(
                {
                    "topology": topology,
                    "local_slave": ordinal_by_row[slave_row],
                    "phase": phases[str(block.kind)],
                    "columns": columns,
                }
            )
    return tuple(result)


def make_task037_extra_h2a_class_key(
    *,
    cell_widths: Sequence[float],
    material_tag: int,
    material_identity: Sequence[Any],
    orientation: Sequence[Any],
    constraint_pattern: Sequence[Mapping[str, Any]],
    canonical_local_basis_signature: Sequence[Any],
    proxy_identity: Sequence[Any] = (
        "B0",
        "K_curl+k0^2*M_abs_epsilon",
    ),
) -> tuple[Any, ...]:
    """Build an exact key from local physical/class identity only.

    ``constraint_pattern`` is a normalized local topology/phase/column
    expansion description.  ``canonical_local_basis_signature`` is the
    basis/order/permutation signature, never cell row numbers.  Absolute
    global master rows are intentionally not accepted as key components.
    """

    widths = tuple(float(value) for value in cell_widths)
    if len(widths) != 3 or not all(
        np.isfinite(width) and width > 0.0 for width in widths
    ):
        raise ValueError("H2A cell widths must be three finite positive values")
    ordering = _freeze_key(canonical_local_basis_signature)
    if not ordering:
        raise ValueError("H2A canonical local DoF signature cannot be empty")
    normalized_constraints = _normalize_constraint_pattern(constraint_pattern)
    return (
        "task037-extra-h2a-exact-class-v1",
        ("cell_widths", widths),
        ("material_tag", int(material_tag)),
        ("material_identity", _freeze_key(material_identity)),
        ("orientation", _freeze_key(orientation)),
        ("constraint_pattern", normalized_constraints),
        ("local_dof_ordering", ordering),
        ("proxy_identity", _freeze_key(proxy_identity)),
    )


def build_b0_proxy_tensor(
    curl_tensor: np.ndarray,
    mass_tensor: np.ndarray,
    *,
    k0: float,
    abs_epsilon: float,
) -> np.ndarray:
    """Form one temporary local tensor of ``B0`` in complex128."""

    curl = np.asarray(curl_tensor, dtype=np.complex128)
    mass = np.asarray(mass_tensor, dtype=np.complex128)
    if curl.ndim != 2 or curl.shape[0] != curl.shape[1] or mass.shape != curl.shape:
        raise ValueError("H2A proxy tensors must be matching square matrices")
    if (
        not np.isfinite(k0)
        or k0 <= 0.0
        or not np.isfinite(abs_epsilon)
        or abs_epsilon <= 0.0
    ):
        raise ValueError("H2A proxy coefficients must be finite and positive")
    proxy = np.array(curl, dtype=np.complex128, copy=True, order="C")
    proxy += (float(k0) ** 2 * float(abs_epsilon)) * mass
    if not np.all(np.isfinite(proxy)):
        raise ValueError("H2A proxy tensor is not finite")
    return proxy


def tabulate_task037_extra_h2a_cell_tensor(
    compiled_form: Any,
    function_space: Any,
    cell_tags: Any,
    cell: int,
    *,
    geometry_tolerance: float = 1.0e-11,
) -> tuple[np.ndarray, tuple[float, float, float], int]:
    """Tabulate one supplied bilinear cell form with the inherited FFCx path.

    The caller compiles the form.  This helper only performs one cell-kernel
    tabulation and Basix/DOLFINx orientation; it never assembles a global
    matrix and returns the tensor for immediate class setup.
    """

    mesh = function_space.mesh
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    cell = int(cell)
    if cell < 0 or cell >= owned_cells:
        raise IndexError("H2A cell is not locally owned")
    kernels = _cell_integral_kernels(compiled_form)
    tags = _cell_tag_array(cell_tags, owned_cells)
    coordinates, widths = _canonical_axis_aligned_coordinates(
        mesh,
        cell,
        tolerance=float(geometry_tolerance),
    )
    dimension = int(function_space.element.space_dimension)
    tensor = _tabulate_raw_tensor_class(
        compiled_form,
        kernels,
        coordinates,
        tag=int(tags[cell]),
        dimension=dimension,
    )
    mesh.topology.create_entity_permutations()
    cell_infos = np.asarray(
        mesh.topology.get_cell_permutation_info(),
        dtype=np.uint32,
    )
    _orient_cell_tensor(
        function_space.element,
        tensor,
        np.asarray([cell_infos[cell]], dtype=np.uint32),
    )
    return tensor, widths, int(cell_infos[cell])


@dataclass(frozen=True)
class H2AClassBlockSpec:
    """One unique class/operator description; tensors are borrowed during setup."""

    class_key: tuple[Any, ...]
    curl_tensor: np.ndarray
    mass_tensor: np.ndarray
    k0: float
    abs_epsilon: float


@dataclass(frozen=True)
class H2ACellReference:
    """A cell's class identity and actual gather/scatter rows only."""

    class_key: tuple[Any, ...]
    local_dofs: np.ndarray


@dataclass(frozen=True)
class H2ACellRecord:
    class_id: int
    factor_id: int
    local_dofs: np.ndarray


@dataclass(frozen=True)
class H2AClassFactor:
    factor_id: int
    numeric_hash: str
    values: np.ndarray
    pivots: np.ndarray

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        rhs = np.asarray(right_hand_side, dtype=np.complex128)
        if rhs.ndim not in (1, 2) or rhs.shape[0] != self.values.shape[0]:
            raise ValueError("H2A RHS does not match the local factor")
        return np.asarray(
            lu_solve((self.values, self.pivots), rhs),
            dtype=np.complex128,
        )


def _cell_reference_from_value(
    value: H2ACellReference | Mapping[str, Any],
) -> H2ACellReference:
    if isinstance(value, H2ACellReference):
        return value
    return H2ACellReference(
        class_key=value["class_key"],
        local_dofs=value["local_dofs"],
    )


def _proxy_with_descriptor(
    spec: H2AClassBlockSpec,
) -> tuple[np.ndarray, tuple[tuple[int, int], str]]:
    proxy = build_b0_proxy_tensor(
        spec.curl_tensor,
        spec.mass_tensor,
        k0=spec.k0,
        abs_epsilon=spec.abs_epsilon,
    )
    digest = hashlib.sha256(
        np.ascontiguousarray(proxy).view(np.uint8)
    ).hexdigest()
    shape = (int(proxy.shape[0]), int(proxy.shape[1]))
    return proxy, (shape, digest)


def _factor_from_proxy(
    proxy: np.ndarray,
    factor_id: int,
    digest: str,
) -> tuple[H2AClassFactor, bool, int, int]:
    lu_values, pivots = lu_factor(
        proxy,
        overwrite_a=True,
        check_finite=False,
    )
    shares_proxy = bool(np.shares_memory(lu_values, proxy))
    pivots = np.asarray(pivots, dtype=np.int32).copy()
    lu_values = np.asarray(lu_values, dtype=np.complex128)
    lu_values.flags.writeable = False
    pivots.flags.writeable = False
    return (
        H2AClassFactor(
            factor_id=int(factor_id),
            numeric_hash=digest,
            values=lu_values,
            pivots=pivots,
        ),
        shares_proxy,
        int(lu_values.nbytes),
        int(pivots.nbytes),
    )


class HcurlExactClassBlockCache:
    """Owned exact-class LU inventory for the H2A local proxy."""

    def __init__(
        self,
        class_specs: Iterable[H2AClassBlockSpec],
        cell_references: Sequence[H2ACellReference],
        *,
        comm: MPI.Intracomm,
    ) -> None:
        self._comm = comm
        local_references = tuple(cell_references)
        local_descriptors: dict[tuple[Any, ...], tuple[tuple[int, int], str]] = {}
        setup_temporary_proxy_bytes_peak = 0
        setup_borrowed_curl_mass_bytes_peak = 0
        setup_lu_output_bytes_peak = 0
        setup_lu_output_extra_bytes_peak = 0
        setup_cache_visible_local_numeric_live_peak_bytes = 0
        setup_retained_factor_bytes_before_peak = 0
        setup_lu_shared_proxy: list[bool] = []
        local_factors_by_signature: dict[
            tuple[str, tuple[int, int]], H2AClassFactor
        ] = {}
        retained_factor_bytes = 0
        local_spec_count = 0
        for spec in class_specs:
            local_spec_count += 1
            if not isinstance(spec.class_key, tuple):
                raise TypeError("H2A class_key must be the tuple from the key builder")
            if spec.class_key in local_descriptors:
                raise ValueError("H2A class specs must contain one entry per class key")
            proxy, descriptor = _proxy_with_descriptor(spec)
            local_descriptors[spec.class_key] = descriptor
            borrowed_curl_mass_bytes = int(
                np.asarray(spec.curl_tensor).nbytes
                + np.asarray(spec.mass_tensor).nbytes
            )
            setup_temporary_proxy_bytes_peak = max(
                setup_temporary_proxy_bytes_peak,
                int(proxy.nbytes),
            )
            setup_borrowed_curl_mass_bytes_peak = max(
                setup_borrowed_curl_mass_bytes_peak,
                borrowed_curl_mass_bytes,
            )
            signature = (descriptor[1], descriptor[0])
            setup_retained_factor_bytes_before_peak = max(
                setup_retained_factor_bytes_before_peak,
                retained_factor_bytes,
            )
            cache_visible_transient_base = (
                retained_factor_bytes
                + borrowed_curl_mass_bytes
                + int(proxy.nbytes)
            )
            if signature not in local_factors_by_signature:
                (
                    factor,
                    shares_proxy,
                    lu_values_bytes,
                    lu_pivot_bytes,
                ) = _factor_from_proxy(
                    proxy,
                    -1,
                    signature[0],
                )
                local_factors_by_signature[signature] = factor
                setup_lu_shared_proxy.append(shares_proxy)
                setup_lu_output_bytes_peak = max(
                    setup_lu_output_bytes_peak,
                    lu_values_bytes + lu_pivot_bytes,
                )
                additional_bytes = (
                    lu_pivot_bytes
                    if shares_proxy
                    else lu_values_bytes + lu_pivot_bytes
                )
                setup_lu_output_extra_bytes_peak = max(
                    setup_lu_output_extra_bytes_peak,
                    additional_bytes,
                )
                setup_cache_visible_local_numeric_live_peak_bytes = max(
                    setup_cache_visible_local_numeric_live_peak_bytes,
                    cache_visible_transient_base + additional_bytes,
                )
                retained_factor_bytes += lu_values_bytes + lu_pivot_bytes
            else:
                setup_cache_visible_local_numeric_live_peak_bytes = max(
                    setup_cache_visible_local_numeric_live_peak_bytes,
                    cache_visible_transient_base,
                )
            del proxy
            del spec
        local_cells: list[tuple[tuple[Any, ...], np.ndarray]] = []
        for reference in local_references:
            if not isinstance(reference.class_key, tuple):
                raise TypeError("H2A cell reference class_key must be a tuple")
            local_dofs = np.asarray(reference.local_dofs, dtype=np.int64)
            if local_dofs.ndim != 1:
                raise ValueError(
                    "H2A cell gather/scatter identity must be one-dimensional"
                )
            local_cells.append(
                (
                    reference.class_key,
                    np.array(local_dofs, dtype=np.int64, copy=True),
                )
            )
            if reference.class_key not in local_descriptors:
                raise ValueError("H2A cell reference has no local class spec")

        packets = comm.allgather(
            tuple(
                (key, descriptor[0], descriptor[1])
                for key, descriptor in local_descriptors.items()
            )
        )
        global_descriptors: dict[tuple[Any, ...], tuple[tuple[int, int], str]] = {}
        for packet in packets:
            for key, shape, digest in packet:
                descriptor = (tuple(int(value) for value in shape), str(digest))
                previous = global_descriptors.get(key)
                if previous is not None and previous != descriptor:
                    raise RuntimeError("H2A exact class differs across MPI ranks")
                global_descriptors[key] = descriptor
        ordered_keys = tuple(
            sorted(global_descriptors, key=_key_json)
        )
        if len(ordered_keys) > H2A_UNIQUE_CLASS_LIMIT:
            raise ValueError("H2A exact class count exceeds the fixed 32-class gate")
        class_id_by_key = {key: index for index, key in enumerate(ordered_keys)}
        global_signatures = tuple(
            sorted(
                {
                    (descriptor[1], descriptor[0])
                    for descriptor in global_descriptors.values()
                }
            )
        )
        factor_id_by_signature = {
            signature: index for index, signature in enumerate(global_signatures)
        }
        local_factors: dict[int, H2AClassFactor] = {}
        for signature, factor in sorted(local_factors_by_signature.items()):
            factor_id = factor_id_by_signature[signature]
            local_factors[factor_id] = H2AClassFactor(
                factor_id=factor_id,
                numeric_hash=factor.numeric_hash,
                values=factor.values,
                pivots=factor.pivots,
            )

        cell_class_ids = np.empty(len(local_cells), dtype=np.int32)
        cell_factor_ids = np.empty(len(local_cells), dtype=np.int32)
        cell_records: list[H2ACellRecord] = []
        for index, (key, local_dofs) in enumerate(local_cells):
            class_id = int(class_id_by_key[key])
            descriptor = global_descriptors[key]
            factor_id = int(factor_id_by_signature[(descriptor[1], descriptor[0])])
            if local_dofs.size != descriptor[0][0]:
                raise ValueError("H2A local DoF identity does not match proxy width")
            local_dofs.flags.writeable = False
            cell_class_ids[index] = class_id
            cell_factor_ids[index] = factor_id
            cell_records.append(
                H2ACellRecord(
                    class_id=class_id,
                    factor_id=factor_id,
                    local_dofs=local_dofs,
                )
            )
        cell_class_ids.flags.writeable = False
        cell_factor_ids.flags.writeable = False
        self._class_keys = ordered_keys
        self._class_id_by_key = MappingProxyType(class_id_by_key)
        self._factors = local_factors
        self._cells = tuple(cell_records)
        self._cell_class_ids = cell_class_ids
        self._cell_factor_ids = cell_factor_ids
        local_factor_values_bytes = sum(
            int(factor.values.nbytes) for factor in local_factors.values()
        )
        local_pivot_bytes = sum(
            int(factor.pivots.nbytes) for factor in local_factors.values()
        )
        local_cell_dof_bytes = sum(
            int(cell.local_dofs.nbytes) for cell in self._cells
        )
        components = {
            "factor_values_bytes": local_factor_values_bytes,
            "factor_pivot_indices_bytes": local_pivot_bytes,
            "cell_gather_scatter_indices_bytes": local_cell_dof_bytes,
            "cell_class_ids_bytes": int(cell_class_ids.nbytes),
            "cell_factor_ids_bytes": int(cell_factor_ids.nbytes),
        }
        local_payload = int(sum(components.values()))
        local_factor_payload = int(local_factor_values_bytes + local_pivot_bytes)
        resident_factor_payload_global_sum = int(
            comm.allreduce(local_factor_payload, op=MPI.SUM)
        )
        global_unique_factor_sizes = comm.allgather(
            tuple(
                (
                    factor.numeric_hash,
                    tuple(int(size) for size in factor.values.shape),
                    int(factor.values.nbytes),
                    int(factor.pivots.nbytes),
                )
                for factor in local_factors.values()
            )
        )
        unique_factor_sizes = {
            (digest, shape): (int(value_bytes), int(pivot_bytes))
            for packet in global_unique_factor_sizes
            for digest, shape, value_bytes, pivot_bytes in packet
        }
        unique_factor_payload = int(
            sum(
                value_bytes + pivot_bytes
                for value_bytes, pivot_bytes in unique_factor_sizes.values()
            )
        )
        class_inventory = tuple(
            {
                "class_id": int(class_id_by_key[key]),
                "class_key_sha256": hashlib.sha256(
                    _key_json(key).encode("utf-8")
                ).hexdigest(),
                "numeric_tensor_sha256": global_descriptors[key][1],
                "factor_id": int(
                    factor_id_by_signature[
                        (global_descriptors[key][1], global_descriptors[key][0])
                    ]
                ),
            }
            for key in ordered_keys
        )
        local_factor_values_finite = all(
            bool(np.all(np.isfinite(factor.values)))
            for factor in local_factors.values()
        )
        local_factor_pivots_finite = all(
            bool(np.all(np.isfinite(factor.pivots)))
            for factor in local_factors.values()
        )
        factor_values_finite = bool(
            comm.allreduce(local_factor_values_finite, op=MPI.LAND)
        )
        factor_pivots_finite = bool(
            comm.allreduce(local_factor_pivots_finite, op=MPI.LAND)
        )
        class_factor_ids = tuple(
            int(item["factor_id"]) for item in class_inventory
        )
        cell_factor_relation_closed = (
            len(cell_class_ids) == len(cell_factor_ids)
            and all(
                int(cell_factor_ids[index])
                == class_factor_ids[int(cell_class_ids[index])]
                for index in range(len(cell_class_ids))
            )
        )
        deterministic_inventory_local_closed = (
            tuple(item["class_id"] for item in class_inventory)
            == tuple(range(len(class_inventory)))
            and all(
                0 <= int(value) < len(ordered_keys)
                for value in cell_class_ids
            )
            and all(
                0 <= int(value) < len(global_signatures)
                for value in cell_factor_ids
            )
            and set(class_factor_ids) == set(range(len(global_signatures)))
            and cell_factor_relation_closed
        )
        deterministic_inventory_closed = bool(
            comm.allreduce(deterministic_inventory_local_closed, op=MPI.LAND)
        )
        deterministic_inventory_sha256 = hashlib.sha256(
            _key_json(
                (
                    class_inventory,
                    tuple(int(value) for value in cell_class_ids),
                    tuple(int(value) for value in cell_factor_ids),
                )
            ).encode("utf-8")
        ).hexdigest()
        class_metadata_bytes = len(
            json.dumps(
                _freeze_key((ordered_keys, class_inventory)),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        class_metadata_global_sum_bytes = int(
            comm.allreduce(class_metadata_bytes, op=MPI.SUM)
        )
        resident_factor_and_metadata_global_sum = (
            resident_factor_payload_global_sum + class_metadata_global_sum_bytes
        )
        self._destroyed = False
        self._audit: dict[str, Any] = {
            "schema": "task037.extra.h2a.exact_class_block_cache.v1",
            "task037_extra_h2a": True,
            "proxy": "B0=K_curl+k0^2*M_abs_epsilon",
            "unique_class_count": len(ordered_keys),
            "unique_class_count_limit": H2A_UNIQUE_CLASS_LIMIT,
            "unique_class_gate_pass": len(ordered_keys) <= H2A_UNIQUE_CLASS_LIMIT,
            "local_cell_count": len(self._cells),
            "global_cell_count": int(comm.allreduce(len(self._cells), op=MPI.SUM)),
            "local_factor_count": len(local_factors),
            "global_factor_count_sum": int(
                comm.allreduce(len(local_factors), op=MPI.SUM)
            ),
            "global_unique_factor_count": len(unique_factor_sizes),
            "numeric_hash_dedup_count": len(ordered_keys) - len(unique_factor_sizes),
            "class_operator_spec_count": local_spec_count,
            "class_operator_specs_retained": False,
            "cell_reference_count": len(local_references),
            "setup_temporary_dense_proxy_matrix_peak_per_class_count": (
                1 if local_spec_count else 0
            ),
            "setup_temporary_dense_proxy_matrix_peak_bytes": (
                int(setup_temporary_proxy_bytes_peak)
            ),
            "setup_borrowed_curl_mass_bytes_peak": int(
                setup_borrowed_curl_mass_bytes_peak
            ),
            "setup_lu_output_values_pivots_bytes_peak": int(
                setup_lu_output_bytes_peak
            ),
            "setup_lu_output_extra_bytes_peak": int(
                setup_lu_output_extra_bytes_peak
            ),
            "setup_lu_output_shares_proxy_all": (
                all(setup_lu_shared_proxy) if setup_lu_shared_proxy else None
            ),
            "setup_lu_output_shares_proxy_any": (
                any(setup_lu_shared_proxy) if setup_lu_shared_proxy else None
            ),
            "setup_cache_visible_local_numeric_live_peak_bytes": int(
                setup_cache_visible_local_numeric_live_peak_bytes
            ),
            "setup_cache_visible_local_retained_factor_bytes_before_peak": int(
                setup_retained_factor_bytes_before_peak
            ),
            "setup_temporary_dense_proxy_matrix_retained": False,
            "per_cell_factor_count": 0,
            "cell_factor_reference_count": len(self._cells),
            "retained_numeric_payload_components": MappingProxyType(components),
            "retained_numeric_payload_local_bytes": local_payload,
            "retained_numeric_payload_global_sum_bytes": int(
                comm.allreduce(local_payload, op=MPI.SUM)
            ),
            "retained_numeric_payload_global_max_bytes": int(
                comm.allreduce(local_payload, op=MPI.MAX)
            ),
            "retained_block_factor_payload_local_bytes": local_factor_payload,
            "retained_block_factor_payload_global_sum_bytes": (
                resident_factor_payload_global_sum
            ),
            "retained_block_factor_payload_global_unique_bytes": unique_factor_payload,
            "retained_block_factor_metadata_local_bytes": int(class_metadata_bytes),
            "retained_block_factor_metadata_global_sum_bytes": (
                class_metadata_global_sum_bytes
            ),
            "retained_block_factor_payload_with_metadata_local_bytes": int(
                local_factor_payload + class_metadata_bytes
            ),
            "retained_block_factor_payload_with_metadata_global_sum_bytes": (
                resident_factor_and_metadata_global_sum
            ),
            "retained_block_factor_payload_limit_bytes": (
                H2A_FACTOR_PAYLOAD_LIMIT_BYTES
            ),
            "factor_payload_gate_pass": resident_factor_and_metadata_global_sum
            <= H2A_FACTOR_PAYLOAD_LIMIT_BYTES,
            "factor_payload_gate_basis": (
                "resident_factor_values_plus_pivots_plus_class_metadata_global_sum"
            ),
            "class_metadata_serialized_bytes": int(class_metadata_bytes),
            "class_metadata_serialized_global_sum_bytes": (
                class_metadata_global_sum_bytes
            ),
            "class_metadata_python_headers_excluded": True,
            "inventory_only": True,
            "constrained_smoother_implemented": False,
            "Bc_inverse_implemented": False,
            "constraint_pattern_semantics": (
                "normalized local topology/slave/phase/column expansion; "
                "no constrained inverse applied"
            ),
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "slab_factor_count": 0,
            "retained_dense_cell_matrix_count": 0,
            "retained_original_dense_matrix_count": 0,
            "original_dense_matrix_released_after_factorization": True,
            "ordinary_default_changed": False,
            "ksp_created": False,
            "dtn_used": False,
            "class_inventory": class_inventory,
            "cell_class_ids": tuple(int(value) for value in cell_class_ids),
            "cell_factor_ids": tuple(int(value) for value in cell_factor_ids),
            "factor_values_finite": factor_values_finite,
            "factor_pivots_finite": factor_pivots_finite,
            "deterministic_class_inventory_closed": deterministic_inventory_closed,
            "deterministic_class_inventory_sha256": deterministic_inventory_sha256,
            "destroyed": False,
        }

    @property
    def audit(self) -> MappingProxyType:
        return MappingProxyType(self._audit)

    @property
    def class_keys(self) -> tuple[tuple[Any, ...], ...]:
        return self._class_keys

    @property
    def cells(self) -> tuple[H2ACellRecord, ...]:
        if self._destroyed:
            raise RuntimeError("H2A block cache has been destroyed")
        return self._cells

    def factor_for_class(self, class_key: tuple[Any, ...]) -> H2AClassFactor:
        if self._destroyed:
            raise RuntimeError("H2A block cache has been destroyed")
        class_id = self._class_id_by_key[class_key]
        factor_id = int(self._audit["class_inventory"][class_id]["factor_id"])
        return self._factors[factor_id]

    def solve_cell(self, cell: int, right_hand_side: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("H2A block cache has been destroyed")
        record = self._cells[int(cell)]
        return self._factors[record.factor_id].solve(right_hand_side)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._factors.clear()
        self._cells = tuple()
        self._class_keys = tuple()
        self._class_id_by_key = MappingProxyType({})
        self._cell_class_ids = np.empty(0, dtype=np.int32)
        self._cell_factor_ids = np.empty(0, dtype=np.int32)
        self._audit["destroyed"] = True
        self._destroyed = True


def build_task037_extra_h2a_block_cache(
    class_specs: Iterable[H2AClassBlockSpec],
    cell_references: Sequence[H2ACellReference] | Sequence[Mapping[str, Any]],
    *,
    comm: MPI.Intracomm = MPI.COMM_SELF,
    task037_extra_h2a: bool = False,
) -> HcurlExactClassBlockCache:
    """Build the explicitly opted-in H2A exact-class factor inventory."""

    if not bool(task037_extra_h2a):
        raise ValueError("H2A block cache requires explicit task037 opt-in")
    return HcurlExactClassBlockCache(
        class_specs,
        tuple(_cell_reference_from_value(value) for value in cell_references),
        comm=comm,
    )
