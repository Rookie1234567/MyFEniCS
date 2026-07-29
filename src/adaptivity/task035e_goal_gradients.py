"""Construct the complete 59-goal live gradient inventory for Task035e.

All gradients use the convention

``dJ(x)[dx] = Re(g.conjugate().T @ dx)``.

Diffraction-order and total-power gradients act directly on the auxiliary DtN
coordinates.  Material absorption and the six frozen field-probe goals are
first differentiated in the recovered p6 Nedelec carrier and are then mapped
through the qualified variable-p Hermitian reduction.  No hidden reference,
endpoint difference, or finite-difference surrogate enters the construction.
"""

from __future__ import annotations

from dataclasses import dataclass
import gc
import hashlib
import json
import math
import tempfile
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping

import basix
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from dolfinx import geometry

from src.postprocessing.full3d_reference import (
    periodic_plane_sample_grid,
    reference_plane_sides,
)

from .blind_controller.contracts import (
    FIXED_M,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from .dtn_goal_adjoint import (
    DtnChannelGoal,
    build_dtn_channel_goal_gradient,
    build_dtn_power_goal_gradient,
)


GRADIENT_SCHEMA = "task035e.formal-59-goal-live-gradients.v2"
_FIELD_GOAL_IDS = (
    "scalar/interface_probe_l2",
    "scalar/volume_probe_l2",
    "complex/interface_probe_complex/real",
    "complex/interface_probe_complex/imag",
    "complex/volume_probe_complex/real",
    "complex/volume_probe_complex/imag",
)
INTERIOR_SENSITIVE_GOAL_IDS = (
    "scalar/A_volume",
    *_FIELD_GOAL_IDS,
)


class Task035eGoalGradientError(RuntimeError):
    """Fail-closed formal-gradient construction error."""


@dataclass(slots=True)
class Task035eFormalGoalGradients:
    """Owned PETSc gradients with an explicit collective lifecycle."""

    gradients: Mapping[str, PETSc.Vec]
    active_full_gradients: Mapping[str, PETSc.Vec]
    audit: Mapping[str, Any]
    _destroyed: bool = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        vectors = (
            *self.gradients.values(),
            *self.active_full_gradients.values(),
        )
        self.gradients = MappingProxyType({})
        self.active_full_gradients = MappingProxyType({})
        self._destroyed = True
        errors: list[str] = []
        seen: set[int] = set()
        for vector in vectors:
            if id(vector) in seen:
                continue
            seen.add(id(vector))
            try:
                vector.destroy()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError(
                "Task035e goal-gradient cleanup failed: "
                + "; ".join(errors)
            )

    def __enter__(self) -> Task035eFormalGoalGradients:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("goal-gradient audit contains a non-finite value")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(
        "goal-gradient audit contains an unsupported object: "
        f"{type(value).__name__}"
    )


def _json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _vector_identity(
    vector: PETSc.Vec,
    *,
    namespace: str,
) -> dict[str, Any]:
    comm = vector.getComm().tompi4py()
    start, end = map(int, vector.getOwnershipRange())
    values = np.ascontiguousarray(
        vector.getArray(readonly=True),
        dtype=np.dtype("<c16"),
    )
    if values.shape != (end - start,) or not np.all(np.isfinite(values)):
        raise ValueError(f"{namespace} vector content is invalid")
    local_digest = hashlib.sha256()
    local_digest.update(namespace.encode("ascii"))
    local_digest.update(b"\0")
    local_digest.update(
        np.asarray(
            [comm.rank, start, end],
            dtype=np.dtype("<i8"),
        ).tobytes()
    )
    local_digest.update(values.tobytes())
    send_hash = np.zeros((comm.size, 32), dtype=np.uint8)
    send_hash[comm.rank] = np.frombuffer(
        local_digest.digest(),
        dtype=np.uint8,
    )
    hashes = np.zeros_like(send_hash)
    comm.Allreduce(send_hash, hashes, op=MPI.SUM)
    send_range = np.full((comm.size, 2), -1, dtype=np.int64)
    send_range[comm.rank] = (start, end)
    ranges = np.full_like(send_range, -1)
    comm.Allreduce(send_range, ranges, op=MPI.MAX)
    cursor = 0
    for rank, (row_start, row_end) in enumerate(ranges):
        if int(row_start) != cursor or int(row_end) < int(row_start):
            raise RuntimeError(
                f"{namespace} ownership is invalid at rank {rank}"
            )
        cursor = int(row_end)
    if cursor != int(vector.getSize()):
        raise RuntimeError(f"{namespace} ownership does not close")
    payload = {
        "global_size": int(vector.getSize()),
        "ownership_ranges": ranges.tolist(),
        "rank_local_content_sha256": [
            bytes(row).hex() for row in hashes
        ],
        "norm_l2": float(vector.norm(PETSc.NormType.NORM_2)),
    }
    payload["partition_bound_sha256"] = _json_sha256(
        payload,
        namespace=f"{namespace}.partition.v1",
    )
    return payload


def _sum_vectors(
    vectors: tuple[PETSc.Vec, ...],
    *,
    coefficients: tuple[complex, ...] | None = None,
) -> PETSc.Vec:
    if not vectors:
        raise ValueError("cannot sum an empty gradient tuple")
    weights = (
        tuple(1.0 + 0.0j for _ in vectors)
        if coefficients is None
        else coefficients
    )
    if len(weights) != len(vectors):
        raise ValueError("gradient sum coefficient count differs")
    result = vectors[0].duplicate()
    try:
        result.set(PETSc.ScalarType(0.0))
        for weight, vector in zip(weights, vectors, strict=True):
            result.axpy(PETSc.ScalarType(weight), vector)
    except Exception:
        result.destroy()
        raise
    return result


def _destroy_vectors_once(vectors: tuple[PETSc.Vec, ...]) -> None:
    """Best-effort cleanup without relying on PETSc wrapper hashability."""

    seen: set[int] = set()
    for vector in vectors:
        identity = id(vector)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            vector.destroy()
        except Exception:
            pass


def _spool_owned_vectors(
    stream: BinaryIO,
    vectors: Mapping[str, PETSc.Vec],
    goal_ids: tuple[str, ...],
) -> tuple[dict[str, tuple[int, int]], int]:
    """Write rank-owned vector entries without a Python full-vector gather."""

    offsets: dict[str, tuple[int, int]] = {}
    byte_count = 0
    for goal_id in goal_ids:
        vector = vectors[goal_id]
        start, end = map(int, vector.getOwnershipRange())
        values = np.ascontiguousarray(
            vector.getArray(readonly=True),
            dtype=np.dtype("<c16"),
        )
        if values.shape != (end - start,) or not np.all(
            np.isfinite(values)
        ):
            raise ValueError(
                f"spooled endpoint gradient {goal_id} is invalid"
            )
        offset = int(stream.tell())
        written = int(stream.write(memoryview(values).cast("B")))
        if written != int(values.nbytes):
            raise OSError(
                f"short endpoint-gradient spool write for {goal_id}"
            )
        offsets[goal_id] = (offset, len(values))
        byte_count += written
    return offsets, byte_count


def _weighted_sum_from_spool_into_second(
    stream: BinaryIO,
    *,
    offset: int,
    owned_count: int,
    second: PETSc.Vec,
    coefficients: tuple[complex, complex],
) -> PETSc.Vec:
    """Replace ``second`` by a spooled-first weighted endpoint sum."""

    start, end = map(int, second.getOwnershipRange())
    if owned_count != end - start:
        raise ValueError("spooled endpoint gradient layout differs")
    stream.seek(offset)
    first_values = np.fromfile(
        stream,
        dtype=np.dtype("<c16"),
        count=owned_count,
    )
    if first_values.shape != (owned_count,) or not np.all(
        np.isfinite(first_values)
    ):
        raise OSError("endpoint-gradient spool read is incomplete")
    second_values = second.getArray()
    if second_values.shape != first_values.shape:
        raise ValueError("spooled endpoint local vector layout differs")
    second_values *= PETSc.ScalarType(coefficients[1])
    second_values += PETSc.ScalarType(coefficients[0]) * first_values
    second.assemble()
    return second


def _release_spooled_endpoint(
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Collect and trim one destroyed endpoint inventory before the next."""

    from src.solvers.common_3d_utils import _trim_process_heap

    gc.collect()
    PETSc.garbage_cleanup(comm)
    gc.collect()
    local = _trim_process_heap()
    rank_rows = comm.allgather(
        {
            "rank": int(comm.rank),
            **local,
        }
    )
    if [int(row["rank"]) for row in rank_rows] != list(range(comm.size)):
        raise RuntimeError("endpoint heap-trim audit lost an MPI rank")
    before = [
        float(row["rss_before_mb"])
        for row in rank_rows
        if row["rss_before_mb"] is not None
    ]
    after = [
        float(row["rss_after_mb"])
        for row in rank_rows
        if row["rss_after_mb"] is not None
    ]
    released = [
        float(row["rss_released_mb"])
        for row in rank_rows
        if row["rss_released_mb"] is not None
    ]
    return {
        "schema_version": (
            "task035e.endpoint-gradient-spool-release.v1"
        ),
        "pass": (
            len(rank_rows) == comm.size
            and all(row["supported"] is True for row in rank_rows)
            and all(row["succeeded"] is True for row in rank_rows)
        ),
        "all_rank_return_codes": [
            row["return_code"] for row in rank_rows
        ],
        "sum_rank_rss_before_mb": sum(before),
        "sum_rank_rss_after_mb": sum(after),
        "sum_rank_rss_released_mb": sum(released),
        "rank_local_audits": rank_rows,
    }


def _auxiliary_gradients(
    view: Any,
) -> tuple[dict[str, PETSc.Vec], dict[str, Any]]:
    context = dict(view.goal_context)
    gradients: dict[str, PETSc.Vec] = {}
    metadata: dict[str, Any] = {}
    temporary: list[PETSc.Vec] = []
    try:
        for side in ("top", "bottom"):
            for m in FIXED_M:
                prefix = f"{side}:m{m}:n0"
                power_components: list[PETSc.Vec] = []
                power_metadata: list[dict[str, Any]] = []
                for polarization in ("s", "p"):
                    vector, row = build_dtn_channel_goal_gradient(
                        view.x,
                        view.config,
                        context,
                        goal=DtnChannelGoal(
                            side,
                            m,
                            0,
                            polarization,
                            "power",
                        ),
                    )
                    temporary.append(vector)
                    power_components.append(vector)
                    power_metadata.append(row)
                gradients[f"{prefix}:power"] = _sum_vectors(
                    tuple(power_components)
                )
                metadata[f"{prefix}:power"] = {
                    "construction": "co_plus_cross_power_gradient",
                    "components": power_metadata,
                }
                for component, quantity in (
                    ("co_amp_real", "amplitude_real"),
                    ("co_amp_imag", "amplitude_imag"),
                ):
                    vector, row = build_dtn_channel_goal_gradient(
                        view.x,
                        view.config,
                        context,
                        goal=DtnChannelGoal(
                            side,
                            m,
                            0,
                            "s",
                            quantity,
                        ),
                    )
                    gradients[f"{prefix}:{component}"] = vector
                    metadata[f"{prefix}:{component}"] = row
        total_vectors: dict[str, PETSc.Vec] = {}
        for name in ("R00_total", "R_total", "T_total"):
            vector, row = build_dtn_power_goal_gradient(
                view.x,
                view.config,
                context,
                goal=name,
            )
            total_vectors[name] = vector
            gradients[f"scalar/{name}"] = vector
            metadata[f"scalar/{name}"] = row
        gradients["scalar/A_closure"] = _sum_vectors(
            (total_vectors["R_total"], total_vectors["T_total"]),
            coefficients=(-1.0 + 0.0j, -1.0 + 0.0j),
        )
        metadata["scalar/A_closure"] = {
            "construction": "d(1-R_total-T_total)",
            "constant_derivative": 0.0,
        }
    except Exception:
        _destroy_vectors_once((*temporary, *gradients.values()))
        raise
    _destroy_vectors_once(tuple(temporary))
    return gradients, metadata


def _assemble_volume_p6_gradient(
    view: Any,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Assemble the lossy-volume derivative without a giant p6 JIT module.

    Task035e is restricted to the fixed rectangular-block hexahedral geometry.
    Every leaf, including a locally refined leaf, therefore has an affine
    coordinate map.  A degree-12 tensor Gauss rule integrates the p6
    first-family Nedelec mass product exactly on those affine cells.  The
    explicit affine gate below fails closed before this path could be credited
    on a curved or otherwise non-affine cell.
    """

    field = view.field
    space = field.function_space
    mesh_data = view.mesh_data
    config = view.config
    comm = mesh_data.mesh.comm
    incident_power = float(view.port_metrics["incident_power_code_units"])
    if not math.isfinite(incident_power) or incident_power <= 0.0:
        raise ValueError("A_volume gradient requires positive incident power")
    coefficients = (
        (
            int(config.tags.grating),
            0.5
            * float(config.k0)
            * float(complex(config.eps_grating).imag)
            / incident_power,
        ),
        (
            int(config.tags.substrate),
            0.5
            * float(config.k0)
            * float(complex(config.eps_substrate).imag)
            / incident_power,
        ),
    )
    active_coefficients = {
        tag: coefficient for tag, coefficient in coefficients if coefficient > 0.0
    }
    quadrature_degree = 12
    quadrature_points, quadrature_weights = basix.make_quadrature(
        basix.CellType.hexahedron,
        quadrature_degree,
    )
    quadrature_points = np.asarray(quadrature_points, dtype=np.float64)
    quadrature_weights = np.asarray(quadrature_weights, dtype=np.float64)
    reference_basis = np.asarray(
        space.element.basix_element.tabulate(
            0,
            quadrature_points,
        )[0],
        dtype=np.float64,
    )
    reference_vertices = np.asarray(
        basix.geometry(basix.CellType.hexahedron),
        dtype=np.float64,
    )
    domain = space.mesh
    domain.topology.create_entity_permutations()
    permutation_info = domain.topology.get_cell_permutation_info()
    cell_map = domain.topology.index_map(domain.topology.dim)
    owned_cell_count = int(cell_map.size_local)
    lossy_cells: list[tuple[int, float, int]] = []
    tag_counts_local: dict[int, int] = {tag: 0 for tag in active_coefficients}
    for tag, coefficient in active_coefficients.items():
        for cell_raw in mesh_data.cell_tags.find(tag):
            cell = int(cell_raw)
            if cell >= owned_cell_count:
                continue
            lossy_cells.append((cell, coefficient, tag))
            tag_counts_local[tag] += 1
    tag_counts_global = {
        tag: int(comm.allreduce(count, op=MPI.SUM))
        for tag, count in tag_counts_local.items()
    }
    missing_tags = [tag for tag, count in tag_counts_global.items() if count <= 0]
    if missing_tags:
        raise RuntimeError(
            f"A_volume lossy material tag has no owned cells: {missing_tags}"
        )
    cell_geometry: list[tuple[int, float, int, np.ndarray, float, float, float]] = []
    geometry_error = None
    try:
        for cell, coefficient, tag in lossy_cells:
            geometry_rows = domain.geometry.dofmap[cell]
            coordinates = np.asarray(
                domain.geometry.x[geometry_rows],
                dtype=np.float64,
            )
            physical_vertices = np.asarray(
                domain.geometry.cmap.push_forward(
                    reference_vertices,
                    coordinates,
                ),
                dtype=np.float64,
            )
            origin = physical_vertices[0]
            jacobian = np.column_stack(
                (
                    physical_vertices[1] - origin,
                    physical_vertices[2] - origin,
                    physical_vertices[4] - origin,
                )
            )
            affine_prediction = origin[None, :] + reference_vertices @ jacobian.T
            affine_error = float(
                np.max(
                    np.abs(physical_vertices - affine_prediction),
                    initial=0.0,
                )
            )
            affine_scale = float(
                np.max(
                    np.abs(physical_vertices - origin[None, :]),
                    initial=0.0,
                )
            )
            affine_relative_error = affine_error / max(
                affine_scale,
                np.finfo(np.float64).tiny,
            )
            determinant = float(np.linalg.det(jacobian))
            if (
                not math.isfinite(determinant)
                or determinant <= np.finfo(np.float64).tiny
                or affine_relative_error > 5.0e-12
            ):
                raise RuntimeError(
                    "A_volume explicit quadrature requires an affine, "
                    "positively oriented hexahedral leaf: "
                    f"cell={cell}, detJ={determinant:.6e}, "
                    f"affine_relative_error={affine_relative_error:.6e}"
                )
            cell_geometry.append(
                (
                    cell,
                    coefficient,
                    tag,
                    jacobian,
                    determinant,
                    affine_error,
                    affine_relative_error,
                )
            )
    except Exception as exc:
        geometry_error = f"{type(exc).__name__}: {exc}"
    geometry_errors = comm.allgather(geometry_error)
    if any(error is not None for error in geometry_errors):
        raise RuntimeError(
            "collective A_volume affine-hexahedron gate failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(geometry_errors)
                if error is not None
            )
        )

    gradient = field.x.petsc_vec.duplicate()
    gradient.set(PETSc.ScalarType(0.0))
    direction = gradient.duplicate()
    maximum_affine_error = 0.0
    maximum_affine_relative_error = 0.0
    maximum_live_basis_bytes = 0
    local_value = 0.0
    local_plus = 0.0
    local_minus = 0.0
    try:
        start, end = map(int, direction.getOwnershipRange())
        rows = np.arange(start, end, dtype=np.float64)
        direction.getArray()[:] = (
            np.cos(0.017 * (rows + 1.0)) + 1j * np.sin(0.023 * (rows + 1.0))
        ) / math.sqrt(max(direction.getSize(), 1))
        direction.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        field_norm = float(field.x.petsc_vec.norm())
        direction_norm = float(direction.norm())
        if (
            not math.isfinite(field_norm)
            or not math.isfinite(direction_norm)
            or field_norm <= np.finfo(float).tiny
            or direction_norm <= np.finfo(float).tiny
        ):
            raise RuntimeError(
                "A_volume finite-difference field/direction norm is invalid"
            )
        # The absorption functional is exactly quadratic in the field, so a
        # central difference has no truncation term.  Scale the perturbation
        # to the distributed field norm instead of using a fixed 1e-7
        # coefficient step: the latter makes J(E+h d)-J(E-h d) comparable to
        # roundoff for the formal p6 field and spuriously destabilizes the
        # derivative Gate.
        finite_difference_relative_step = 1.0e-5
        epsilon = finite_difference_relative_step * field_norm / direction_norm
        with direction.localForm() as local_direction:
            direction_values = np.asarray(
                local_direction.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
        if direction_values.shape != field.x.array.shape:
            raise RuntimeError(
                "A_volume finite-difference direction does not match the "
                "ghosted p6 field layout"
            )
        index_map = space.dofmap.index_map
        for (
            cell,
            coefficient,
            _tag,
            jacobian,
            determinant,
            affine_error,
            affine_relative_error,
        ) in cell_geometry:
            maximum_affine_error = max(
                maximum_affine_error,
                affine_error,
            )
            maximum_affine_relative_error = max(
                maximum_affine_relative_error,
                affine_relative_error,
            )
            jacobians = np.repeat(
                jacobian[None, :, :],
                len(quadrature_points),
                axis=0,
            )
            determinants = np.full(
                len(quadrature_points),
                determinant,
                dtype=np.float64,
            )
            inverses = np.repeat(
                np.linalg.inv(jacobian)[None, :, :],
                len(quadrature_points),
                axis=0,
            )
            physical_basis = np.asarray(
                space.element.basix_element.push_forward(
                    reference_basis,
                    jacobians,
                    determinants,
                    inverses,
                ),
                dtype=np.float64,
            )
            oriented_basis = np.ascontiguousarray(
                np.transpose(physical_basis, (1, 0, 2))
            )
            cell_info = np.asarray(
                [permutation_info[cell]],
                dtype=np.uint32,
            )
            space.element.T_apply(
                oriented_basis.reshape(-1),
                cell_info,
                int(len(quadrature_points) * 3),
            )
            oriented_basis = np.transpose(
                oriented_basis,
                (1, 0, 2),
            )
            maximum_live_basis_bytes = max(
                maximum_live_basis_bytes,
                int(
                    reference_basis.nbytes
                    + physical_basis.nbytes
                    + oriented_basis.nbytes
                    + jacobians.nbytes
                    + determinants.nbytes
                    + inverses.nbytes
                ),
            )
            local_dofs = np.asarray(
                space.dofmap.cell_dofs(cell),
                dtype=np.int32,
            )
            global_dofs = np.asarray(
                index_map.local_to_global(local_dofs),
                dtype=PETSc.IntType,
            )
            field_values = np.einsum(
                "i,pic->pc",
                field.x.array[local_dofs],
                oriented_basis,
                optimize=True,
            )
            perturbation_values = np.einsum(
                "i,pic->pc",
                direction_values[local_dofs],
                oriented_basis,
                optimize=True,
            )
            physical_weights = quadrature_weights * determinant
            local_gradient = (
                2.0
                * coefficient
                * np.einsum(
                    "p,pc,pic->i",
                    physical_weights,
                    field_values,
                    oriented_basis,
                    optimize=True,
                )
            )
            gradient.setValues(
                global_dofs,
                np.asarray(local_gradient, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            local_value += coefficient * float(
                np.einsum(
                    "p,pc,pc->",
                    physical_weights,
                    np.conj(field_values),
                    field_values,
                    optimize=True,
                ).real
            )
            plus_values = field_values + epsilon * perturbation_values
            minus_values = field_values - epsilon * perturbation_values
            local_plus += coefficient * float(
                np.einsum(
                    "p,pc,pc->",
                    physical_weights,
                    np.conj(plus_values),
                    plus_values,
                    optimize=True,
                ).real
            )
            local_minus += coefficient * float(
                np.einsum(
                    "p,pc,pc->",
                    physical_weights,
                    np.conj(minus_values),
                    minus_values,
                    optimize=True,
                ).real
            )
        gradient.assemble()
        gradient.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        tangent = float(np.real(gradient.dot(direction)))
        goal_value = float(comm.allreduce(local_value, op=MPI.SUM))
        plus_value = float(comm.allreduce(local_plus, op=MPI.SUM))
        minus_value = float(comm.allreduce(local_minus, op=MPI.SUM))
        finite_difference = (plus_value - minus_value) / (2.0 * epsilon)
        relative = abs(tangent - finite_difference) / max(
            abs(tangent),
            abs(finite_difference),
            1.0e-13,
        )
        if relative > 2.0e-7 and abs(tangent - finite_difference) > 1.0e-9:
            raise RuntimeError(
                "A_volume gradient finite-difference closure failed: "
                f"relative={relative:.6e}, "
                f"absolute={abs(tangent - finite_difference):.6e}, "
                f"tangent={tangent:.6e}, "
                f"finite_difference={finite_difference:.6e}, "
                f"epsilon={epsilon:.6e}"
            )
    except Exception:
        gradient.destroy()
        raise
    finally:
        direction.destroy()
    maximum_affine_error = float(comm.allreduce(maximum_affine_error, op=MPI.MAX))
    maximum_affine_relative_error = float(
        comm.allreduce(maximum_affine_relative_error, op=MPI.MAX)
    )
    maximum_live_basis_bytes = int(comm.allreduce(maximum_live_basis_bytes, op=MPI.MAX))
    global_lossy_cell_count = int(comm.allreduce(len(lossy_cells), op=MPI.SUM))
    if (
        not np.all(np.isfinite(gradient.getArray(readonly=True)))
        or not math.isfinite(goal_value)
        or goal_value < 0.0
    ):
        gradient.destroy()
        raise RuntimeError("A_volume gradient/value is invalid")
    return gradient, {
        "construction": (
            "exact derivative of official material "
            "0.5*k0*Im(epsilon_r)*|E|^2 / incident_power"
        ),
        "assembly_backend": (
            "explicit_affine_hexahedron_tensor_gauss_without_ffcx_jit"
        ),
        "ffcx_jit_form_loaded": False,
        "affine_geometry_gate_pass": True,
        "affine_geometry_relative_tolerance": 5.0e-12,
        "affine_geometry_max_abs_error": maximum_affine_error,
        "affine_geometry_max_relative_error": (maximum_affine_relative_error),
        "quadrature_degree": quadrature_degree,
        "quadrature_point_count": len(quadrature_points),
        "quadrature_exactness": (
            "degree-12 tensor rule for affine p6 N1curl mass products"
        ),
        "lossy_owned_cell_count_global": global_lossy_cell_count,
        "lossy_material_owned_cell_counts_global": {
            str(tag): count for tag, count in sorted(tag_counts_global.items())
        },
        "maximum_live_basis_workspace_bytes_per_rank": (maximum_live_basis_bytes),
        "goal_value": goal_value,
        "gradient_norm": float(gradient.norm()),
        "finite_difference_tangent": finite_difference,
        "adjoint_convention_tangent": tangent,
        "finite_difference_relative_error": relative,
        "finite_difference_relative_step": (finite_difference_relative_step),
        "finite_difference_absolute_step": epsilon,
        "field_l2_norm": field_norm,
        "direction_l2_norm": direction_norm,
        "material_coefficients": [
            {"tag": tag, "normalized_coefficient": coefficient}
            for tag, coefficient in coefficients
        ],
    }


def _point_owners(
    space: Any,
    points: np.ndarray,
    z_sides: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    domain = space.mesh
    comm = domain.comm
    tree = geometry.bb_tree(domain, domain.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(
        domain,
        candidates,
        points,
    )
    cell_map = domain.topology.index_map(domain.topology.dim)
    cell_count = cell_map.size_local + cell_map.num_ghosts
    cell_midpoints = np.zeros((cell_count, 3), dtype=np.float64)
    if cell_count:
        from dolfinx import mesh as dmesh

        cell_midpoints = dmesh.compute_midpoints(
            domain,
            domain.topology.dim,
            np.arange(cell_count, dtype=np.int32),
        )
    local_scores = np.full(len(points), -np.inf, dtype=np.float64)
    local_cells = np.full(len(points), -1, dtype=np.int64)
    for point_index in range(len(points)):
        links = collisions.links(point_index)
        if not len(links):
            continue
        scores = z_sides[point_index] * (
            cell_midpoints[links, 2] - points[point_index, 2]
        )
        best = int(np.argmax(scores))
        local_scores[point_index] = float(scores[best])
        local_cells[point_index] = int(links[best])
    all_scores = np.empty(
        (comm.size, len(points)), dtype=np.float64
    )
    all_cells = np.empty(
        (comm.size, len(points)), dtype=np.int64
    )
    comm.Allgather(local_scores, all_scores)
    comm.Allgather(local_cells, all_cells)
    owners = np.argmax(all_scores, axis=0).astype(np.int32)
    selected_scores = all_scores[
        owners,
        np.arange(len(points), dtype=np.int64),
    ]
    if np.any(~np.isfinite(selected_scores)):
        missing = np.flatnonzero(~np.isfinite(selected_scores))
        raise RuntimeError(
            "field-gradient point ownership is incomplete; "
            f"first={int(missing[0])}"
        )
    selected_cells = all_cells[
        owners,
        np.arange(len(points), dtype=np.int64),
    ].astype(np.int32)
    if np.any(selected_cells < 0):
        raise RuntimeError("field-gradient selected a missing local cell")
    return owners, selected_cells, {
        "point_count": len(points),
        "small_point_owner_metadata_bytes_per_rank": int(
            all_scores.nbytes + all_cells.nbytes
        ),
        "full_vector_python_allgather_used": False,
        "selection": (
            "maximum requested z-side midpoint score; lowest rank on tie"
        ),
    }


def _oriented_physical_basis(
    space: Any,
    *,
    cell: int,
    points: np.ndarray,
) -> np.ndarray:
    domain = space.mesh
    geometry_rows = domain.geometry.dofmap[int(cell)]
    coordinates = np.asarray(
        domain.geometry.x[geometry_rows],
        dtype=np.float64,
    )
    reference_points = domain.geometry.cmap.pull_back(
        np.asarray(points, dtype=np.float64),
        coordinates,
    )
    reference = np.asarray(
        space.element.basix_element.tabulate(
            0,
            reference_points,
        )[0],
        dtype=np.float64,
    )
    axes = np.asarray(
        domain.geometry.cmap.push_forward(
            np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            ),
            coordinates,
        ),
        dtype=np.float64,
    )
    jacobian = np.column_stack(
        (
            axes[1] - axes[0],
            axes[2] - axes[0],
            axes[3] - axes[0],
        )
    )
    determinants = np.full(
        len(points),
        np.linalg.det(jacobian),
        dtype=np.float64,
    )
    jacobians = np.repeat(
        jacobian[None, :, :],
        len(points),
        axis=0,
    )
    inverses = np.repeat(
        np.linalg.inv(jacobian)[None, :, :],
        len(points),
        axis=0,
    )
    physical = np.asarray(
        space.element.basix_element.push_forward(
            reference,
            jacobians,
            determinants,
            inverses,
        ),
        dtype=np.float64,
    )
    domain.topology.create_entity_permutations()
    cell_info = np.asarray(
        [domain.topology.get_cell_permutation_info()[int(cell)]],
        dtype=np.uint32,
    )
    transformed = np.ascontiguousarray(
        np.transpose(physical, (1, 0, 2))
    )
    space.element.T_apply(
        transformed.reshape(-1),
        cell_info,
        int(len(points) * 3),
    )
    return np.transpose(transformed, (1, 0, 2))


def _field_p6_gradients(
    view: Any,
) -> tuple[
    dict[str, PETSc.Vec],
    dict[str, PETSc.Vec],
    dict[str, Any],
]:
    field = view.field
    space = field.function_space
    comm = space.mesh.comm
    x_nm, y_nm, z_nm, points = periodic_plane_sample_grid(view.config)
    points_per_plane = len(x_nm) * len(y_nm)
    sides = reference_plane_sides(len(z_nm), points_per_plane)
    if len(z_nm) < 3:
        raise ValueError(
            "Task035e field goals require interface and middle planes"
        )
    owners, selected_cells, ownership_audit = _point_owners(
        space,
        points,
        sides,
    )
    local_indices = np.flatnonzero(owners == comm.rank)
    rows_by_cell: dict[int, list[int]] = {}
    for point_index in local_indices:
        rows_by_cell.setdefault(
            int(selected_cells[point_index]),
            [],
        ).append(int(point_index))
    index_map = space.dofmap.index_map
    if int(space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("Task035e N1curl carrier expects bs=1")
    cell_info: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    evaluation_max_error = 0.0
    for cell, point_indices in rows_by_cell.items():
        point_rows = np.asarray(point_indices, dtype=np.int64)
        basis = _oriented_physical_basis(
            space,
            cell=cell,
            points=points[point_rows],
        )
        local_dofs = np.asarray(
            space.dofmap.cell_dofs(cell),
            dtype=np.int32,
        )
        global_dofs = np.asarray(
            index_map.local_to_global(local_dofs),
            dtype=np.int64,
        )
        coefficients = np.asarray(
            field.x.array[local_dofs],
            dtype=np.complex128,
        )
        predicted = np.einsum(
            "i,pic->pc",
            coefficients,
            basis,
            optimize=True,
        )
        observed = np.asarray(
            field.eval(
                points[point_rows],
                np.full(len(point_rows), cell, dtype=np.int32),
            ),
            dtype=np.complex128,
        ).reshape((-1, 3))
        evaluation_max_error = max(
            evaluation_max_error,
            float(
                np.max(
                    np.abs(predicted - observed),
                    initial=0.0,
                )
            ),
        )
        cell_info[cell] = (point_rows, global_dofs, basis)
    evaluation_max_error = float(
        comm.allreduce(evaluation_max_error, op=MPI.MAX)
    )
    if evaluation_max_error > 5.0e-11:
        raise RuntimeError(
            "oriented point basis differs from DOLFINx Function.eval: "
            f"{evaluation_max_error:.6e}"
        )

    scale = float(view.config.electric_field_scale_V_per_m)
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("electric field export scale must be positive")
    interface_planes = {0, len(z_nm) - 1}
    middle_planes = set(range(1, len(z_nm) - 1))
    interface_count = 2 * points_per_plane * 2
    volume_count = len(middle_planes) * points_per_plane * 3
    local_norms = np.zeros(2, dtype=np.float64)
    for _cell, (point_rows, global_dofs, basis) in cell_info.items():
        coefficients = field.x.array[
            space.dofmap.cell_dofs(_cell)
        ]
        values = (
            scale
            * np.einsum(
                "i,pic->pc",
                coefficients,
                basis,
                optimize=True,
            )
        )
        for local_point, point_index in enumerate(point_rows):
            plane = int(point_index // points_per_plane)
            if plane in interface_planes:
                local_norms[0] += float(
                    np.vdot(
                        values[local_point, :2],
                        values[local_point, :2],
                    ).real
                )
            if plane in middle_planes:
                local_norms[1] += float(
                    np.vdot(
                        values[local_point],
                        values[local_point],
                    ).real
                )
    global_norms = np.zeros(2, dtype=np.float64)
    comm.Allreduce(local_norms, global_norms, op=MPI.SUM)
    norms = np.sqrt(global_norms)
    if np.any(~np.isfinite(norms)) or np.any(norms <= 0.0):
        raise RuntimeError("Task035e field-probe norm is zero or invalid")

    p6_gradients = {
        goal_id: field.x.petsc_vec.duplicate()
        for goal_id in _FIELD_GOAL_IDS
    }
    for vector in p6_gradients.values():
        vector.set(PETSc.ScalarType(0.0))
    try:
        for cell, (point_rows, global_dofs, basis) in cell_info.items():
            coefficients = field.x.array[
                space.dofmap.cell_dofs(cell)
            ]
            values = (
                scale
                * np.einsum(
                    "i,pic->pc",
                    coefficients,
                    basis,
                    optimize=True,
                )
            )
            for local_point, point_index in enumerate(point_rows):
                plane = int(point_index // points_per_plane)
                if plane in interface_planes:
                    for component in range(2):
                        linear = scale * basis[
                            local_point, :, component
                        ]
                        p6_gradients[
                            "scalar/interface_probe_l2"
                        ].setValues(
                            np.asarray(
                                global_dofs,
                                dtype=PETSc.IntType,
                            ),
                            np.asarray(
                                values[local_point, component]
                                * np.conj(linear)
                                / norms[0],
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
                        mean_gradient = np.conj(linear) / interface_count
                        p6_gradients[
                            "complex/interface_probe_complex/real"
                        ].setValues(
                            np.asarray(global_dofs, dtype=PETSc.IntType),
                            np.asarray(
                                mean_gradient,
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
                        p6_gradients[
                            "complex/interface_probe_complex/imag"
                        ].setValues(
                            np.asarray(global_dofs, dtype=PETSc.IntType),
                            np.asarray(
                                1j * mean_gradient,
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
                if plane in middle_planes:
                    for component in range(3):
                        linear = scale * basis[
                            local_point, :, component
                        ]
                        p6_gradients[
                            "scalar/volume_probe_l2"
                        ].setValues(
                            np.asarray(global_dofs, dtype=PETSc.IntType),
                            np.asarray(
                                values[local_point, component]
                                * np.conj(linear)
                                / norms[1],
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
                        mean_gradient = np.conj(linear) / volume_count
                        p6_gradients[
                            "complex/volume_probe_complex/real"
                        ].setValues(
                            np.asarray(global_dofs, dtype=PETSc.IntType),
                            np.asarray(
                                mean_gradient,
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
                        p6_gradients[
                            "complex/volume_probe_complex/imag"
                        ].setValues(
                            np.asarray(global_dofs, dtype=PETSc.IntType),
                            np.asarray(
                                1j * mean_gradient,
                                dtype=PETSc.ScalarType,
                            ),
                            addv=PETSc.InsertMode.ADD_VALUES,
                        )
        for vector in p6_gradients.values():
            vector.assemble()
    except Exception:
        for vector in p6_gradients.values():
            vector.destroy()
        raise

    active_full: dict[str, PETSc.Vec] = {}
    reduced: dict[str, PETSc.Vec] = {}
    try:
        for goal_id, p6_gradient in p6_gradients.items():
            active_full[goal_id] = view.reduction.project_p6_vector(
                p6_gradient
            )
            reduced[goal_id] = view.reduction.reduce_active_vector(
                active_full[goal_id],
                side="left",
            )
    except Exception:
        for vector in reduced.values():
            vector.destroy()
        for vector in active_full.values():
            vector.destroy()
        raise
    finally:
        for vector in p6_gradients.values():
            vector.destroy()
    return reduced, active_full, {
        "construction": (
            "transpose of exact oriented p6 point-evaluation rows; "
            "same grid and z-side convention as official field archive"
        ),
        "x_count": len(x_nm),
        "y_count": len(y_nm),
        "z_count": len(z_nm),
        "interface_sample_component_count": interface_count,
        "volume_sample_component_count": volume_count,
        "interface_probe_l2": float(norms[0]),
        "volume_probe_l2": float(norms[1]),
        "oriented_basis_vs_dolfinx_eval_max_abs": evaluation_max_error,
        "ownership": ownership_audit,
        "p6_gradient_reduced_through_exact_variable_p_adjoint_map": True,
    }


def build_task035e_formal_goal_gradients(
    view: Any,
) -> Task035eFormalGoalGradients:
    """Build and audit the exact ordered 59-gradient shadow inventory."""

    comm = view.mesh_data.mesh.comm
    auxiliary: dict[str, PETSc.Vec] = {}
    field: dict[str, PETSc.Vec] = {}
    active_full: dict[str, PETSc.Vec] = {}
    volume_p6 = None
    try:
        auxiliary, auxiliary_metadata = _auxiliary_gradients(view)
        volume_p6, volume_metadata = _assemble_volume_p6_gradient(view)
        volume_active = view.reduction.project_p6_vector(volume_p6)
        active_full["scalar/A_volume"] = volume_active
        volume_reduced = view.reduction.reduce_active_vector(
            volume_active,
            side="left",
        )
        auxiliary["scalar/A_volume"] = volume_reduced
        field, field_active, field_metadata = _field_p6_gradients(view)
        active_full.update(field_active)
        gradients = {**auxiliary, **field}
        if tuple(gradients) != FORMAL_GOAL_IDS:
            gradients = {
                goal_id: gradients[goal_id]
                for goal_id in FORMAL_GOAL_IDS
            }
        if set(gradients) != set(FORMAL_GOAL_IDS):
            raise RuntimeError(
                "constructed formal gradient inventory is incomplete"
            )
        if tuple(active_full) != INTERIOR_SENSITIVE_GOAL_IDS:
            active_full = {
                goal_id: active_full[goal_id]
                for goal_id in INTERIOR_SENSITIVE_GOAL_IDS
            }
        identities = {
            goal_id: _vector_identity(
                gradients[goal_id],
                namespace=(
                    "task035e.goal-gradient."
                    + hashlib.sha256(goal_id.encode("utf-8")).hexdigest()
                ),
            )
            for goal_id in FORMAL_GOAL_IDS
        }
        active_identities = {
            goal_id: _vector_identity(
                active_full[goal_id],
                namespace=(
                    "task035e.active-full-goal-gradient."
                    + hashlib.sha256(goal_id.encode("utf-8")).hexdigest()
                ),
            )
            for goal_id in INTERIOR_SENSITIVE_GOAL_IDS
        }
        nonzero = {
            goal_id: identities[goal_id]["norm_l2"] > 0.0
            for goal_id in FORMAL_GOAL_IDS
        }
        zero_power_ids = {
            goal_id
            for goal_id, is_nonzero in nonzero.items()
            if not is_nonzero and goal_id.endswith(":power")
        }
        evanescent_power_ids = {
            goal_id
            for goal_id in zero_power_ids
            if all(
                float(component["power_weight"]) == 0.0
                for component in auxiliary_metadata[goal_id][
                    "components"
                ]
            )
        }
        propagating_zero_power_ids = (
            zero_power_ids - evanescent_power_ids
        )
        invalid_zero = {
            goal_id
            for goal_id, is_nonzero in nonzero.items()
            if not is_nonzero and not goal_id.endswith(":power")
        } | propagating_zero_power_ids
        if invalid_zero:
            raise RuntimeError(
                "formal goal has a zero gradient without a verified "
                "evanescent-power explanation: "
                f"{sorted(invalid_zero)}"
            )
        unsigned = {
            "schema_version": GRADIENT_SCHEMA,
            "status": "formal_59_goal_live_gradients_pass",
            "pass": True,
            "mpi_size": int(comm.size),
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "gradient_convention": "dJ=Re(g^H dx)",
            "auxiliary_goal_metadata": auxiliary_metadata,
            "volume_goal_metadata": volume_metadata,
            "field_goal_metadata": field_metadata,
            "gradient_identities": identities,
            "active_full_gradient_identities": active_identities,
            "active_full_gradient_goal_ids": list(
                INTERIOR_SENSITIVE_GOAL_IDS
            ),
            "active_full_gradient_role": (
                "cell-interior affine-complement pairing only"
            ),
            "structural_zero_evanescent_power_goal_ids": sorted(
                evanescent_power_ids
            ),
            "propagating_zero_amplitude_power_goal_ids": [],
            "hidden_reference_consumed": False,
            "endpoint_difference_used_as_gradient": False,
            "full_vector_python_allgather_used": False,
            "ordinary_default_changed": False,
        }
        audit = {
            **unsigned,
            "gradient_inventory_sha256": _json_sha256(
                unsigned,
                namespace="task035e.formal-gradient-inventory.v1",
            ),
        }
        return Task035eFormalGoalGradients(
            gradients=MappingProxyType(gradients),
            active_full_gradients=MappingProxyType(active_full),
            audit=MappingProxyType(audit),
        )
    except Exception:
        _destroy_vectors_once(
            (
                *auxiliary.values(),
                *field.values(),
                *active_full.values(),
            )
        )
        raise
    finally:
        if volume_p6 is not None:
            volume_p6.destroy()


def _secant_weights(
    goal_id: str,
    *,
    current_audit: Mapping[str, Any],
    shadow_audit: Mapping[str, Any],
) -> tuple[float, float, str]:
    """Return exact analytic path-average weights for one real goal."""

    if goal_id == "scalar/interface_probe_l2":
        metadata_key = "interface_probe_l2"
    elif goal_id == "scalar/volume_probe_l2":
        metadata_key = "volume_probe_l2"
    else:
        return 0.5, 0.5, "arithmetic_endpoint_gradient_average"
    current_norm = float(
        current_audit["field_goal_metadata"][metadata_key]
    )
    shadow_norm = float(
        shadow_audit["field_goal_metadata"][metadata_key]
    )
    denominator = current_norm + shadow_norm
    if (
        not math.isfinite(current_norm)
        or not math.isfinite(shadow_norm)
        or current_norm <= 0.0
        or shadow_norm <= 0.0
        or not math.isfinite(denominator)
        or denominator <= 0.0
    ):
        raise RuntimeError(
            f"{goal_id} endpoint norms cannot define a secant gradient"
        )
    return (
        current_norm / denominator,
        shadow_norm / denominator,
        "exact_l2_secant_endpoint_norm_weighting",
    )


def build_task035e_formal_secant_goal_gradients(
    current_view: Any,
    shadow_view: Any,
) -> Task035eFormalGoalGradients:
    """Build exact analytic current-to-shadow averaged goal derivatives.

    No endpoint difference is supplied or evaluated here.  Quadratic power
    and absorption goals use the arithmetic mean of their endpoint
    derivatives, linear complex-amplitude goals are unchanged by that mean,
    and the two Euclidean-norm goals use their exact analytic secant weights.
    """

    comm = current_view.mesh_data.mesh.comm
    current_bundle: Task035eFormalGoalGradients | None = None
    shadow_bundle: Task035eFormalGoalGradients | None = None
    result: Task035eFormalGoalGradients | None = None
    weight_audit: dict[str, Any] = {}
    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as spool:
        try:
            current_bundle = build_task035e_formal_goal_gradients(
                current_view
            )
            if (
                set(current_bundle.gradients) != set(FORMAL_GOAL_IDS)
                or tuple(current_bundle.active_full_gradients)
                != INTERIOR_SENSITIVE_GOAL_IDS
            ):
                raise RuntimeError(
                    "current endpoint gradient inventory differs"
                )
            current_audit = dict(current_bundle.audit)
            reduced_offsets, reduced_bytes = _spool_owned_vectors(
                spool,
                current_bundle.gradients,
                FORMAL_GOAL_IDS,
            )
            active_offsets, active_bytes = _spool_owned_vectors(
                spool,
                current_bundle.active_full_gradients,
                INTERIOR_SENSITIVE_GOAL_IDS,
            )
            spool.flush()
            local_spool_bytes = reduced_bytes + active_bytes
            rank_local_spool_bytes = [
                int(value)
                for value in comm.allgather(local_spool_bytes)
            ]
            total_spool_bytes = sum(rank_local_spool_bytes)
            current_bundle.destroy()
            current_bundle = None
            release_audit = _release_spooled_endpoint(comm)

            shadow_bundle = build_task035e_formal_goal_gradients(
                shadow_view
            )
            if (
                set(shadow_bundle.gradients) != set(FORMAL_GOAL_IDS)
                or tuple(shadow_bundle.active_full_gradients)
                != INTERIOR_SENSITIVE_GOAL_IDS
            ):
                raise RuntimeError(
                    "shadow endpoint gradient inventory differs"
                )
            shadow_audit = dict(shadow_bundle.audit)
            maximum_live_spool_read_bytes = 0
            for goal_id in FORMAL_GOAL_IDS:
                current_weight, shadow_weight, rule = _secant_weights(
                    goal_id,
                    current_audit=current_audit,
                    shadow_audit=shadow_audit,
                )
                weights = (
                    complex(current_weight),
                    complex(shadow_weight),
                )
                offset, owned_count = reduced_offsets[goal_id]
                _weighted_sum_from_spool_into_second(
                    spool,
                    offset=offset,
                    owned_count=owned_count,
                    second=shadow_bundle.gradients[goal_id],
                    coefficients=weights,
                )
                maximum_live_spool_read_bytes = max(
                    maximum_live_spool_read_bytes,
                    owned_count * np.dtype("<c16").itemsize,
                )
                if goal_id in INTERIOR_SENSITIVE_GOAL_IDS:
                    active_offset, active_owned_count = active_offsets[
                        goal_id
                    ]
                    _weighted_sum_from_spool_into_second(
                        spool,
                        offset=active_offset,
                        owned_count=active_owned_count,
                        second=shadow_bundle.active_full_gradients[
                            goal_id
                        ],
                        coefficients=weights,
                    )
                    maximum_live_spool_read_bytes = max(
                        maximum_live_spool_read_bytes,
                        active_owned_count
                        * np.dtype("<c16").itemsize,
                    )
                weight_audit[goal_id] = {
                    "current_endpoint_weight": current_weight,
                    "shadow_endpoint_weight": shadow_weight,
                    "sum": current_weight + shadow_weight,
                    "rule": rule,
                }

            reduced_identities = {
                goal_id: _vector_identity(
                    shadow_bundle.gradients[goal_id],
                    namespace=(
                        "task035e.secant-goal-gradient."
                        + hashlib.sha256(
                            goal_id.encode("utf-8")
                        ).hexdigest()
                    ),
                )
                for goal_id in FORMAL_GOAL_IDS
            }
            active_identities = {
                goal_id: _vector_identity(
                    shadow_bundle.active_full_gradients[goal_id],
                    namespace=(
                        "task035e.secant-active-full-gradient."
                        + hashlib.sha256(
                            goal_id.encode("utf-8")
                        ).hexdigest()
                    ),
                )
                for goal_id in INTERIOR_SENSITIVE_GOAL_IDS
            }
            maximum_live_spool_read_bytes_by_rank = [
                int(value)
                for value in comm.allgather(
                    maximum_live_spool_read_bytes
                )
            ]
            unsigned = {
                "schema_version": (
                    "task035e.formal-59-goal-analytic-secant-gradients.v1"
                ),
                "status": (
                    "formal_59_goal_analytic_secant_gradients_pass"
                ),
                "pass": True,
                "mpi_size": int(comm.size),
                "formal_goal_count": len(FORMAL_GOAL_IDS),
                "formal_goal_inventory_sha256": (
                    FORMAL_GOAL_INVENTORY_SHA256
                ),
                "gradient_convention": "dJ=Re(g_secant^H dx)",
                "path_derivative": (
                    "analytic current-to-shadow averaged derivative"
                ),
                "current_endpoint_gradient_inventory_sha256": (
                    current_audit["gradient_inventory_sha256"]
                ),
                "shadow_endpoint_gradient_inventory_sha256": (
                    shadow_audit["gradient_inventory_sha256"]
                ),
                "secant_weight_audit": weight_audit,
                "gradient_identities": reduced_identities,
                "active_full_gradient_identities": active_identities,
                "active_full_gradient_goal_ids": list(
                    INTERIOR_SENSITIVE_GOAL_IDS
                ),
                "quadratic_goal_rule": (
                    "one-half current gradient plus one-half shadow gradient"
                ),
                "l2_goal_rule": (
                    "(norm_current*g_current+norm_shadow*g_shadow)"
                    "/(norm_current+norm_shadow)"
                ),
                "linear_goal_rule": (
                    "endpoint gradients are state-independent; their average "
                    "retains the same derivative"
                ),
                "secant_vector_allocation_strategy": (
                    "rank_local_current_endpoint_spool_then_"
                    "destructive_shadow_reuse"
                ),
                "endpoint_spool": {
                    "storage": "anonymous_linux_tmp_stream",
                    "rank_local_owned_values_only": True,
                    "python_full_vector_gather_used": False,
                    "mpi_full_vector_gather_used": False,
                    "current_endpoint_vectors_destroyed_before_shadow_build": (
                        True
                    ),
                    "maximum_simultaneous_endpoint_vector_inventories": 1,
                    "rank_local_spool_bytes": (
                        rank_local_spool_bytes
                    ),
                    "total_spool_bytes": total_spool_bytes,
                    "maximum_live_spool_read_bytes": (
                        max(maximum_live_spool_read_bytes_by_rank)
                    ),
                    "maximum_live_spool_read_bytes_by_rank": (
                        maximum_live_spool_read_bytes_by_rank
                    ),
                    "release_audit": release_audit,
                    "hidden_reference_content": False,
                },
                "third_full_gradient_inventory_allocated": False,
                "endpoint_vectors_combined_in_formal_goal_order": True,
                "hidden_reference_consumed": False,
                "endpoint_difference_used_as_gradient": False,
                "endpoint_goal_delta_consumed": False,
                "full_vector_python_allgather_used": False,
                "ordinary_default_changed": False,
            }
            audit = {
                **unsigned,
                "gradient_inventory_sha256": _json_sha256(
                    unsigned,
                    namespace=(
                        "task035e.formal-secant-gradient-inventory.v1"
                    ),
                ),
            }
            shadow_bundle.audit = MappingProxyType(audit)
            result = shadow_bundle
            return result
        finally:
            if current_bundle is not None:
                current_bundle.destroy()
            if shadow_bundle is not None and result is None:
                shadow_bundle.destroy()


__all__ = [
    "GRADIENT_SCHEMA",
    "INTERIOR_SENSITIVE_GOAL_IDS",
    "Task035eFormalGoalGradients",
    "Task035eGoalGradientError",
    "build_task035e_formal_goal_gradients",
    "build_task035e_formal_secant_goal_gradients",
]
