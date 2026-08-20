"""Factor-free source schedules and owner-row basis construction for V6.

This module deliberately knows no packet or exact-response path.  Training
sources are described by a frozen, hashable schedule; the caller supplies the
actual factor-free vectors.  The QR helper keeps only owned rows and combines
small inner products with MPI reductions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI


V6_PORT_MODAL_CHECKPOINTS = (64, 128, 256, 512)
V6_PORT_MODAL_TRAINING_SEED = 6039071
V6_PORT_MODAL_SOURCE_FAMILIES = (
    "positive_modal_traction",
    "negative_modal_traction",
    "external_c",
    "hcurl_near_null_gradient",
    # fixed_random is holdout-only; it is intentionally absent from the
    # factor-free training schedule below.
    "fixed_random",
    "physical_rhs",
    "projection_dual",
    "positive_modal_dual",
    "negative_modal_dual",
    "external_dual",
)
V6_PORT_MODAL_HOLDOUT_SPECS = (
    {
        "label": "physical_side_rhs",
        "family": "physical_rhs",
        "seed": None,
        "resolved_column": None,
        "absent_degenerate": True,
    },
    {
        "label": "modal_traction_positive",
        "family": "positive_modal_traction",
        "seed": 761,
        "resolved_column": 281,
    },
    {
        "label": "modal_traction_negative",
        "family": "negative_modal_traction",
        "seed": 763,
        "resolved_column": 283,
    },
    {
        "label": "external_dtn_coupling",
        "family": "external_c",
        "seed": 769,
        "resolved_column": 177,
    },
    {
        "label": "fixed_random_repeat_0",
        "family": "fixed_random",
        "seed": 773,
    },
    {
        "label": "fixed_random_repeat_1",
        "family": "fixed_random",
        "seed": 779,
    },
)

__all__ = (
    "V6_PORT_MODAL_CHECKPOINTS",
    "V6_PORT_MODAL_HOLDOUT_SPECS",
    "V6_PORT_MODAL_SOURCE_FAMILIES",
    "V6_PORT_MODAL_TRAINING_SEED",
    "build_v6_discrete_gradient_source_provider",
    "build_v6_factor_free_source_vector",
    "build_v6_owner_row_basis_checkpoint",
    "v6_single_interface_modal_provider",
    "v6_port_modal_source_contract",
    "v6_port_modal_training_schedule",
    "v6_source_identity",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def v6_port_modal_training_schedule(
    *, mode_count: int = 480, external_count: int = 296, source_count: int = 512
) -> list[dict[str, Any]]:
    """Return the fixed factor-free train schedule; no data files are touched."""

    if (
        mode_count <= 0
        or external_count <= 0
        or source_count < max(V6_PORT_MODAL_CHECKPOINTS)
    ):
        raise ValueError("V6 source schedule has invalid mode or source count")
    right_families = (
        "positive_modal_traction",
        "negative_modal_traction",
        "external_c",
        "hcurl_near_null_gradient",
    )
    left_families = (
        "projection_dual",
        "positive_modal_dual",
        "negative_modal_dual",
        "external_dual",
    )
    schedule: list[dict[str, Any]] = []
    right_occurrences = {family: 0 for family in right_families}
    left_occurrences = {family: 0 for family in left_families}
    for index in range(source_count):
        if index == 0:
            right_family = "physical_rhs"
            right_selector = {
                "selector": "system_rhs",
                "absent_if_zero": True,
                "instance": "single_frozen_physical_source",
                "fallback": {
                    "selector": "cross_section_discrete_gradient_potential",
                    "potential_ordinal": 127,
                },
            }
        else:
            right_family = right_families[(index - 1) % len(right_families)]
            right_ordinal = right_occurrences[right_family]
            right_occurrences[right_family] += 1
            right_selector = _training_selector(
                right_family,
                right_ordinal,
                mode_count,
                external_count,
                side="right",
            )
        left_family = left_families[index % len(left_families)]
        left_ordinal = left_occurrences[left_family]
        left_occurrences[left_family] += 1
        left_selector = _training_selector(
            left_family,
            left_ordinal,
            mode_count,
            external_count,
            side="left",
        )
        schedule.append(
            {
                "index": index,
                "right_family": right_family,
                "right_selector": right_selector,
                "left_family": left_family,
                "left_selector": left_selector,
                "seed": V6_PORT_MODAL_TRAINING_SEED,
                "holdout": False,
                "factor_free": True,
            }
        )
    return schedule


def _training_selector(
    family: str,
    ordinal: int,
    mode_count: int,
    external_count: int,
    *,
    side: str,
) -> dict[str, Any]:
    if family in {"positive_modal_traction", "positive_modal_dual"}:
        return {
            "selector": "positive_mode_key_sequence",
            "mode_key": _non_holdout_mode_key(2 * ordinal + 1),
            "column": _non_holdout_column(
                (17 * ordinal + 13) % mode_count, mode_count, 281
            ),
            "occurrence": int(ordinal),
            "side": side,
        }
    if family in {"negative_modal_traction", "negative_modal_dual"}:
        return {
            "selector": "negative_mode_key_sequence",
            "mode_key": _non_holdout_mode_key(2 * ordinal + 2),
            "column": _non_holdout_column(
                (19 * ordinal + 23) % mode_count, mode_count, 283
            ),
            "occurrence": int(ordinal),
            "side": side,
        }
    if family in {"external_c", "external_dual"}:
        return {
            "selector": "component_column_sequence",
            "column": _non_holdout_column(
                (23 * ordinal + 29) % external_count, external_count, 177
            ),
            "occurrence": int(ordinal),
            "side": side,
        }
    if family == "hcurl_near_null_gradient":
        return {
            "selector": "cross_section_discrete_gradient_potential",
            "potential_ordinal": int(ordinal),
            "occurrence": int(ordinal),
            "side": side,
        }
    if family == "fixed_random":
        return {
            "selector": "owned_range_random_sketch",
            "seed": int(V6_PORT_MODAL_TRAINING_SEED + 101 * ordinal),
            "occurrence": int(ordinal),
            "side": side,
        }
    if family == "projection_dual":
        return {
            "selector": "projection_adjoint",
            "sketch_index": int(ordinal),
            "seed": int(V6_PORT_MODAL_TRAINING_SEED + 131 * ordinal),
            "occurrence": int(ordinal),
            "side": side,
        }
    raise ValueError(f"Unsupported V6 source family: {family}")


def _non_holdout_column(candidate: int, mode_count: int, forbidden: int) -> int:
    column = int(candidate)
    while column == int(forbidden):
        column = (column + 1) % int(mode_count)
    return column


def _non_holdout_mode_key(candidate: int) -> int:
    key = int(candidate)
    while key in {761, 763, 769}:
        key += 1
    return key


def v6_port_modal_source_contract(
    *, mode_count: int = 480, external_count: int = 296, source_count: int = 512
) -> dict[str, Any]:
    """Describe train/holdout separation with one reproducible contract hash."""

    training = v6_port_modal_training_schedule(
        mode_count=mode_count,
        external_count=external_count,
        source_count=source_count,
    )
    holdout = [
        {
            **spec,
            "holdout": True,
            "factor_free": False,
            "source": "existing_exact_response_spool_after_basis_sealed",
        }
        for spec in V6_PORT_MODAL_HOLDOUT_SPECS
    ]
    forbidden_by_family = {
        "positive_modal_traction": 281,
        "positive_modal_dual": 281,
        "negative_modal_traction": 283,
        "negative_modal_dual": 283,
        "external_c": 177,
        "external_dual": 177,
    }
    for item in training:
        for key in ("right_selector", "left_selector"):
            family = (
                item["right_family"] if key == "right_selector" else item["left_family"]
            )
            if "column" in item[key] and int(
                item[key]["column"]
            ) == forbidden_by_family.get(family, -1):
                raise ValueError("V6 training and holdout column overlap")
    training_seeds = {
        int(item[key]["seed"])
        for item in training
        for key in ("right_selector", "left_selector")
        if "seed" in item[key]
    }
    holdout_seeds = {int(spec["seed"]) for spec in holdout if spec["seed"] is not None}
    if training_seeds & holdout_seeds:
        raise ValueError("V6 training and holdout seeds overlap")
    payload = {
        "mode_count": int(mode_count),
        "external_count": int(external_count),
        "checkpoints": list(V6_PORT_MODAL_CHECKPOINTS),
        "training_seed": V6_PORT_MODAL_TRAINING_SEED,
        "training": training,
        "holdout": holdout,
        "training_reads_holdout_files": False,
    }
    payload["sha256"] = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return payload


def v6_source_identity(
    local_values: np.ndarray,
    *,
    label: str,
    seed: int,
    global_rows: int,
    ownership_range: tuple[int, int],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Hash owned source rows and reduce only scalar metadata, never values."""

    values = np.asarray(local_values, dtype=np.complex128)
    if values.ndim != 1:
        raise ValueError("V6 source identity expects one owner-row vector")
    first, last = (int(value) for value in ownership_range)
    if (
        first < 0
        or last < first
        or last > int(global_rows)
        or last - first != values.size
    ):
        raise ValueError("V6 source ownership range does not match local values")
    local_hash = hashlib.sha256(values.tobytes(order="C")).hexdigest()
    local_norm_sq = float(np.vdot(values, values).real)
    global_norm = float(np.sqrt(comm.allreduce(local_norm_sq, op=MPI.SUM)))
    hash_parts = comm.allgather({"range": [first, last], "sha256": local_hash})
    expected_first = 0
    for part in hash_parts:
        part_first, part_last = (int(value) for value in part["range"])
        if part_first != expected_first or part_last < part_first:
            raise ValueError("V6 source ownership ranges have a gap or overlap")
        expected_first = part_last
    if expected_first != int(global_rows):
        raise ValueError("V6 source ownership ranges do not cover global rows")
    return {
        "label": str(label),
        "seed": int(seed),
        "global_rows": int(global_rows),
        "dtype": "complex128",
        "ownership_range": [first, last],
        "global_l2_norm": global_norm,
        "owner_hashes": hash_parts,
    }


def build_v6_factor_free_source_vector(
    system: Any,
    components: Any,
    schedule_item: dict[str, Any],
    *,
    role: str,
    external_count: int = 296,
    modal_provider: Any | None = None,
    near_null_provider: Any | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Materialize one owned source vector without reading a factor or spool.

    Modal traction and near-null providers are intentionally explicit: the
    caller must provide factor-free physical constructions.  The C/D paths
    below are only the external coupling and projection-adjoint sources.
    """

    if role not in {"right", "left"}:
        raise ValueError("V6 source role must be right or left")
    selector = schedule_item[f"{role}_selector"]
    family = schedule_item[f"{role}_family"]
    target = system.A.createVecRight()
    metadata: dict[str, Any] = {
        "family": family,
        "role": role,
        "factor_free": True,
        "holdout": False,
        "source": "factor_free_action_carrier",
    }
    try:
        if family == "physical_rhs":
            system.b.copy(target)
            metadata["degenerate_uninformative"] = bool(target.norm() <= 1.0e-30)
            if metadata["degenerate_uninformative"]:
                if near_null_provider is None:
                    raise ValueError(
                        "V6 degenerate physical RHS needs near-null provider"
                    )
                fallback, fallback_metadata = near_null_provider(
                    system, selector["fallback"], role
                )
                target.destroy()
                target = _copy_owned_provider_vector(
                    fallback, system.A.createVecRight()
                )
                metadata.update(dict(fallback_metadata))
                metadata["source"] = "factor_free_near_null_provider"
                metadata["physical_rhs"] = "absent_degenerate"
                metadata["fallback_used"] = True
            else:
                metadata["physical_rhs"] = "measured_nonzero"
            return target, metadata
        if family == "hcurl_near_null_gradient":
            if near_null_provider is None:
                raise ValueError("V6 near-null source needs an explicit provider")
            source, source_metadata = near_null_provider(system, selector, role)
            target.destroy()
            target = _copy_owned_provider_vector(source, system.A.createVecRight())
            metadata.update(dict(source_metadata))
            metadata["source"] = "factor_free_near_null_provider"
            return target, metadata
        if family == "external_c":
            column = int(selector["column"])
            column_count = int(components.C.getSize()[1])
            if family == "external_c" and column_count != int(external_count):
                raise ValueError("V6 external C column count is not the frozen 296")
            if column < 0 or column >= column_count:
                raise ValueError("V6 physical source column is outside C ownership")
            coefficient = components.C.createVecRight()
            coefficient.set(0.0)
            first, last = (int(value) for value in coefficient.getOwnershipRange())
            if first <= column < last:
                coefficient.getArray()[column - first] = 1.0 + 0.0j
            coefficient.assemble()
            components.C.mult(coefficient, target)
            coefficient.destroy()
            metadata.update(
                {
                    "source": "factor_free_C_column",
                    "resolved_column": column,
                    "column_count": column_count,
                }
            )
            return target, metadata
        if family in {
            "positive_modal_traction",
            "negative_modal_traction",
            "positive_modal_dual",
            "negative_modal_dual",
        }:
            if modal_provider is None:
                raise ValueError(
                    "V6 modal source needs an explicit factor-free provider"
                )
            provider_selector = {**selector, "family": family}
            source, source_metadata = modal_provider(system, provider_selector, role)
            target.destroy()
            target = _copy_owned_provider_vector(source, system.A.createVecRight())
            metadata.update(dict(source_metadata))
            metadata["source"] = "factor_free_modal_provider"
            return target, metadata
        if family in {
            "external_dual",
        }:
            column = int(selector.get("column", selector.get("mode_key", 0)))
            row_count = int(components.D.getSize()[0])
            if column < 0 or column >= row_count:
                raise ValueError("V6 dual source column is outside D ownership")
            coefficient = components.D.createVecLeft()
            coefficient.set(0.0)
            first, last = (int(value) for value in coefficient.getOwnershipRange())
            if first <= column < last:
                coefficient.getArray()[column - first] = 1.0 + 0.0j
            coefficient.assemble()
            _mult_hermitian_transpose(components.D, coefficient, target)
            coefficient.destroy()
            metadata.update(
                {"source": "factor_free_D_adjoint", "resolved_column": column}
            )
            return target, metadata
        if family == "projection_dual":
            coefficient = components.D.createVecLeft()
            _fill_partition_independent_random(coefficient, int(selector["seed"]))
            _mult_hermitian_transpose(components.D, coefficient, target)
            coefficient.destroy()
            metadata.update(
                {
                    "source": "factor_free_D_adjoint_channel_sketch",
                    "channel_sketch_seed": int(selector["seed"]),
                }
            )
            return target, metadata
        if family == "fixed_random":
            _fill_partition_independent_random(target, int(selector["seed"]))
            metadata.update(
                {
                    "source": "owned_range_counter_random_sketch",
                    "seed": int(selector["seed"]),
                }
            )
            return target, metadata
        raise ValueError(f"V6 factor-free source family is not wired: {family}")
    except Exception:
        target.destroy()
        raise


def _fill_partition_independent_random(vector: Any, seed: int) -> None:
    """Fill an owner range from a partition-independent counter-based hash."""

    first, last = (int(value) for value in vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.uint64)
    mask = (1 << 64) - 1
    key_a = rows ^ np.uint64((int(seed) * 0xD2B74407B1CE6E93) & mask)
    key_b = rows ^ np.uint64((int(seed) * 0xCA5A826395121157) & mask)
    hash_a = _splitmix64(key_a)
    hash_b = _splitmix64(key_b + np.uint64(0x9E3779B97F4A7C15))
    real = ((hash_a >> np.uint64(11)).astype(np.float64)) / float(1 << 53)
    imag = ((hash_b >> np.uint64(11)).astype(np.float64)) / float(1 << 53)
    vector.getArray()[:] = np.asarray(
        (2.0 * real - 1.0) + 1j * (2.0 * imag - 1.0), dtype=np.complex128
    )
    vector.assemble()


def _mult_hermitian_transpose(matrix: Any, source: Any, target: Any) -> None:
    """Apply a complex adjoint through the matrix's action-only callback."""

    matrix.multHermitian(source, target)


def _splitmix64(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
    values = (values ^ (values >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    values = (values ^ (values >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return values ^ (values >> np.uint64(31))


def _copy_owned_provider_vector(source: Any, target: Any) -> Any:
    """Copy and destroy an owned provider Vec; borrowed Vecs are forbidden."""

    try:
        source.copy(target)
    finally:
        source.destroy()
    target.assemble()
    return target


def v6_single_interface_modal_provider(owner: Any):
    """Return an owned-vector provider backed by one interface block.

    Right modal sources are traction-matrix columns.  Positive duals are
    ``P^H e_j`` and negative duals are ``P^H m_j`` with ``m_j`` taken from
    the owner's canonical negative-to-positive map.  No external C/D block
    participates in these four internal modal families.
    """

    def provider(system: Any, selector: dict[str, Any], role: str):
        if system is not owner.system:
            raise ValueError("Single-interface modal provider received another system")
        family = str(selector.get("family", ""))
        if family in {"positive_modal_traction", "negative_modal_traction"}:
            if role != "right":
                raise ValueError("Modal traction sources are right-owned only")
            matrix = (
                owner.blocks.positive_traction
                if family == "positive_modal_traction"
                else owner.blocks.negative_traction
            )
            column = int(selector["column"])
            if column < 0 or column >= int(matrix.getSize()[1]):
                raise ValueError("Modal traction source column is out of range")
            vector = matrix.getColumnVector(column)
            matrix_name = (
                "positive_traction"
                if family == "positive_modal_traction"
                else "negative_traction"
            )
        elif family in {"positive_modal_dual", "negative_modal_dual"}:
            if role != "left":
                raise ValueError("Modal dual sources are left-owned only")
            projection = owner.blocks.projection
            column = int(selector["column"])
            if column < 0 or column >= int(projection.getSize()[0]):
                raise ValueError("Modal dual source column is out of range")
            coefficient = projection.createVecLeft()
            coefficient.set(0.0)
            first, last = (int(value) for value in coefficient.getOwnershipRange())
            if family == "positive_modal_dual":
                values = np.zeros(last - first, dtype=np.complex128)
                if first <= column < last:
                    values[column - first] = 1.0 + 0.0j
            else:
                mapping = np.asarray(
                    owner.blocks.negative_trace_to_positive,
                    dtype=np.complex128,
                )
                if mapping.shape[1] <= column:
                    coefficient.destroy()
                    raise ValueError("Negative modal dual map column is out of range")
                values = mapping[first:last, column]
            coefficient.getArray()[:] = values
            coefficient.assemble()
            vector = projection.createVecRight()
            try:
                _mult_hermitian_transpose(projection, coefficient, vector)
            finally:
                coefficient.destroy()
            matrix_name = "projection_hermitian_transpose"
        else:
            raise ValueError(f"Unsupported single-interface modal family: {family}")
        values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
        comm = vector.getComm().tompi4py()
        ownership = tuple(int(value) for value in vector.getOwnershipRange())
        local_hash = hashlib.sha256(values.tobytes()).hexdigest()
        owner_hashes = comm.allgather({"range": list(ownership), "sha256": local_hash})
        global_hash = hashlib.sha256(
            _canonical_json(owner_hashes).encode("utf-8")
        ).hexdigest()
        local_norm_sq = float(np.vdot(values, values).real)
        global_norm = float(np.sqrt(comm.allreduce(local_norm_sq, op=MPI.SUM)))
        return vector, {
            "source": "single_interface_modal_block",
            "matrix": matrix_name,
            "column": column,
            "family": family,
            "global_l2_norm": global_norm,
            "global_sha256": global_hash,
            "owner_hashes": owner_hashes,
            "owned_vec_return": True,
        }

    return provider


class _V6DiscreteGradientSourceProvider:
    """Reuse one scalar/vector interpolation setup for near-null sources."""

    def __init__(
        self,
        owner: Any | None = None,
        *,
        system: Any | None = None,
        spaces: Any | None = None,
        surface_source_assembler: Any | None = None,
    ) -> None:
        if owner is not None:
            if owner._destroyed or owner.surface_load is None:
                raise RuntimeError("Single interface owner is destroyed")
            system = owner.system
            spaces = owner.spaces
            surface_source_assembler = owner.assemble_surface_source
        if system is None or spaces is None or surface_source_assembler is None:
            raise ValueError(
                "Discrete-gradient provider needs system, spaces, and a surface assembler"
            )
        self.owner = owner
        self.system = system
        self.spaces = spaces
        self._surface_source_assembler = surface_source_assembler
        self.mesh = spaces.transverse.mesh
        self.degree = int(spaces.transverse_degree)
        self.scalar_space = fem.functionspace(
            self.mesh,
            element(
                "Lagrange",
                self.mesh.basix_cell(),
                self.degree + 1,
                dtype=default_real_type,
            ),
        )
        self.gradient_space = fem.functionspace(
            self.mesh,
            element(
                "DG",
                self.mesh.basix_cell(),
                self.degree,
                shape=(2,),
                dtype=default_real_type,
            ),
        )
        self.potential = fem.Function(self.scalar_space, name="v6_potential")
        self.gradient = fem.Function(self.gradient_space, name="v6_discrete_gradient")
        points = self.gradient_space.element.interpolation_points
        if callable(points):
            points = points()
        self.expression = fem.Expression(ufl.grad(self.potential), points)
        coordinates = np.asarray(self.mesh.geometry.x, dtype=np.float64)
        comm = self.mesh.comm
        self.x_min = float(comm.allreduce(float(np.min(coordinates[:, 0])), op=MPI.MIN))
        self.x_max = float(comm.allreduce(float(np.max(coordinates[:, 0])), op=MPI.MAX))
        self.y_min = float(comm.allreduce(float(np.min(coordinates[:, 1])), op=MPI.MIN))
        self.y_max = float(comm.allreduce(float(np.max(coordinates[:, 1])), op=MPI.MAX))
        self.setup_count = 1
        self.apply_count = 0
        self._destroyed = False

    def __call__(
        self, system: Any, selector: dict[str, Any], role: str
    ) -> tuple[Any, dict[str, Any]]:
        if self._destroyed or (self.owner is not None and self.owner._destroyed):
            raise RuntimeError("V6 discrete-gradient provider is destroyed")
        if system is not self.system:
            raise ValueError("V6 discrete-gradient provider received another system")
        if selector.get("selector") != "cross_section_discrete_gradient_potential":
            raise ValueError(
                "V6 near-null selector must be "
                "cross_section_discrete_gradient_potential"
            )
        ordinal = int(selector.get("potential_ordinal", -1))
        if ordinal < 0:
            raise ValueError("V6 near-null selector needs a nonnegative sketch index")
        x_span = max(self.x_max - self.x_min, 1.0e-12)
        y_span = max(self.y_max - self.y_min, 1.0e-12)
        kx = 1 + ordinal % 8
        ky = 1 + (ordinal // 8) % 8
        phase = 2.0 * np.pi * ((ordinal * 17) % 97) / 97.0

        def potential_values(points: np.ndarray) -> np.ndarray:
            return np.cos(
                2.0 * np.pi * kx * (points[0] - self.x_min) / x_span
                + 2.0 * np.pi * ky * (points[1] - self.y_min) / y_span
                + phase
            )

        self.potential.interpolate(potential_values)
        self.gradient.interpolate(self.expression)
        self.gradient.x.scatter_forward()
        source, audit = self._surface_source_assembler(
            self.gradient, role=f"v6_discrete_gradient_{ordinal}"
        )
        self.apply_count += 1
        values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        global_norm = float(
            np.sqrt(
                self.mesh.comm.allreduce(
                    float(np.vdot(values, values).real), op=MPI.SUM
                )
            )
        )
        if not np.isfinite(global_norm) or global_norm <= 1.0e-30:
            source.destroy()
            raise RuntimeError(
                "V6 discrete-gradient surface source is zero or non-finite"
            )
        audit.update(
            {
                "source": "cross_section_discrete_gradient_tangential_surface_load",
                "potential_space": f"CG({self.degree + 1})",
                "gradient_space": f"DG({self.degree})_vector",
                "surface_load_full_vector": False,
                "sketch_index": ordinal,
                "potential_wave_numbers": [int(kx), int(ky)],
                "potential_phase": float(phase),
                "global_l2_norm": global_norm,
                "setup_count": self.setup_count,
                "apply_count": self.apply_count,
                "full_volume_hcurl_nullspace": False,
            }
        )
        return source, audit

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.expression = None
        self.gradient = None
        self.potential = None
        self.gradient_space = None
        self.scalar_space = None
        self.owner = None
        self.system = None
        self.spaces = None
        self._surface_source_assembler = None
        self._destroyed = True


def build_v6_discrete_gradient_source_provider(
    owner: Any | None = None,
    *,
    system: Any | None = None,
    spaces: Any | None = None,
    surface_source_assembler: Any | None = None,
) -> _V6DiscreteGradientSourceProvider:
    """Create one reusable cross-section discrete-gradient source provider."""

    return _V6DiscreteGradientSourceProvider(
        owner,
        system=system,
        spaces=spaces,
        surface_source_assembler=surface_source_assembler,
    )


def _owner_row_tsqr(
    local_columns: np.ndarray,
    *,
    comm: MPI.Intracomm,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    columns = np.asarray(local_columns, dtype=np.complex128)
    if columns.ndim != 2:
        raise ValueError("Owner-row source columns must be two-dimensional")
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("Owner-row QR tolerance must be positive and finite")
    if columns.shape[0] == 0:
        raise ValueError("V6 TSQR requires a non-empty local owner range")
    q_local, r_local = np.linalg.qr(columns, mode="reduced")
    gathered = comm.gather(np.asarray(r_local, dtype=np.complex128), root=0)
    if comm.rank == 0:
        try:
            stacked = np.vstack(gathered)
            q2, r_global = np.linalg.qr(stacked, mode="reduced")
            singular_values = np.linalg.svd(r_global, compute_uv=False)
            scale = float(singular_values[0]) if singular_values.size else 0.0
            rank_tolerance = tolerance * max(scale, 1.0)
            rank = int(np.count_nonzero(singular_values > rank_tolerance))
            if rank != columns.shape[1]:
                raise ValueError("V6 source basis is rank deficient at fixed prefix")
            condition = float(singular_values[0] / singular_values[-1])
            split_sizes = [int(item.shape[0]) for item in gathered]
            q2_blocks = []
            offset = 0
            for size in split_sizes:
                q2_blocks.append(q2[offset : offset + size, :])
                offset += size
            root_status = {
                "ok": True,
                "r_global": np.asarray(r_global, dtype=np.complex128),
                "condition": condition,
            }
        except Exception as error:
            q2_blocks = None
            root_status = {"ok": False, "error": str(error)}
    else:
        q2_blocks = None
        root_status = None
    root_status = comm.bcast(root_status, root=0)
    if not root_status["ok"]:
        raise ValueError(root_status["error"])
    q2_local = comm.scatter(q2_blocks, root=0)
    r_global = np.asarray(root_status["r_global"], dtype=np.complex128)
    condition = float(root_status["condition"])
    q = np.asarray(q_local @ q2_local, dtype=np.complex128)
    local_orthogonality = q.conj().T @ q
    global_orthogonality = np.empty_like(local_orthogonality)
    comm.Allreduce(local_orthogonality, global_orthogonality, op=MPI.SUM)
    error = float(np.linalg.norm(global_orthogonality - np.eye(q.shape[1])))
    local_residual = np.asarray(columns - q @ r_global, dtype=np.complex128)
    residual_sq = float(np.vdot(local_residual, local_residual).real)
    source_sq = float(np.vdot(columns, columns).real)
    residual_sq = float(comm.allreduce(residual_sq, op=MPI.SUM))
    source_sq = float(comm.allreduce(source_sq, op=MPI.SUM))
    reconstruction = float(np.sqrt(max(residual_sq, 0.0))) / max(
        float(np.sqrt(max(source_sq, 0.0))), 1.0e-30
    )
    return q, r_global, error, float(condition), reconstruction


def build_v6_owner_row_basis_checkpoint(
    z_candidates: np.ndarray,
    y_candidates: np.ndarray,
    checkpoint: int,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    tolerance: float = 1.0e-13,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Build one nested prefix without ever materializing global basis rows."""

    z = np.asarray(z_candidates, dtype=np.complex128)
    y = np.asarray(y_candidates, dtype=np.complex128)
    if z.ndim != 2 or y.ndim != 2 or z.shape != y.shape:
        raise ValueError("V6 right/left owner-row candidates must have equal 2-D shape")
    if checkpoint not in V6_PORT_MODAL_CHECKPOINTS:
        raise ValueError("V6 checkpoint is not in the frozen nested sequence")
    if z.shape[1] < checkpoint:
        raise ValueError("V6 source candidates do not cover the requested checkpoint")
    z_basis, z_r, z_error, z_condition, z_reconstruction = _owner_row_tsqr(
        z[:, :checkpoint], comm=comm, tolerance=tolerance
    )
    y_basis, y_r, y_error, y_condition, y_reconstruction = _owner_row_tsqr(
        y[:, :checkpoint], comm=comm, tolerance=tolerance
    )
    local_cross = y_basis.conj().T @ z_basis
    cross = np.empty_like(local_cross)
    comm.Allreduce(local_cross, cross, op=MPI.SUM)
    cross_singular = np.linalg.svd(cross, compute_uv=False)
    cross_condition = float(
        np.inf
        if not cross_singular.size or cross_singular[-1] == 0.0
        else cross_singular[0] / cross_singular[-1]
    )
    return (
        z_basis,
        y_basis,
        {
            "checkpoint": int(checkpoint),
            "rank": int(z_basis.shape[1]),
            "owner_row_local": True,
            "global_basis_materialized": False,
            "z_qr_reconstruction_shape": list(z_r.shape),
            "y_qr_reconstruction_shape": list(y_r.shape),
            "z_orthogonality_error": z_error,
            "y_orthogonality_error": y_error,
            "z_reconstruction_relative_error": z_reconstruction,
            "y_reconstruction_relative_error": y_reconstruction,
            "z_qr_condition": z_condition,
            "y_qr_condition": y_condition,
            "cross_yh_z_singular_values": cross_singular.tolist(),
            "cross_yh_z_condition": cross_condition,
            "tolerance": float(tolerance),
        },
    )
