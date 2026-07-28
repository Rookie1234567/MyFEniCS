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
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import ufl

from dolfinx import fem, geometry
from dolfinx.fem import petsc as fem_petsc

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


GRADIENT_SCHEMA = "task035e.formal-59-goal-live-gradients.v1"
_FIELD_GOAL_IDS = (
    "scalar/interface_probe_l2",
    "scalar/volume_probe_l2",
    "complex/interface_probe_complex/real",
    "complex/interface_probe_complex/imag",
    "complex/volume_probe_complex/real",
    "complex/volume_probe_complex/imag",
)


class Task035eGoalGradientError(RuntimeError):
    """Fail-closed formal-gradient construction error."""


@dataclass(slots=True)
class Task035eFormalGoalGradients:
    """Owned PETSc gradients with an explicit collective lifecycle."""

    gradients: Mapping[str, PETSc.Vec]
    audit: Mapping[str, Any]
    _destroyed: bool = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        vectors = tuple(self.gradients.values())
        self.gradients = MappingProxyType({})
        self._destroyed = True
        errors: list[str] = []
        for vector in vectors:
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
    field = view.field
    space = field.function_space
    mesh_data = view.mesh_data
    config = view.config
    incident_power = float(
        view.port_metrics["incident_power_code_units"]
    )
    if not math.isfinite(incident_power) or incident_power <= 0.0:
        raise ValueError("A_volume gradient requires positive incident power")
    test = ufl.TestFunction(space)
    measure = ufl.Measure(
        "dx",
        domain=mesh_data.mesh,
        subdomain_data=mesh_data.cell_tags,
    )
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
    linear_form = PETSc.ScalarType(0.0) * ufl.inner(field, test) * measure
    value_form = PETSc.ScalarType(0.0) * ufl.inner(field, field) * measure
    for tag, coefficient in coefficients:
        if coefficient > 0.0:
            linear_form += (
                PETSc.ScalarType(2.0 * coefficient)
                * ufl.inner(field, test)
                * measure(tag)
            )
            value_form += (
                PETSc.ScalarType(coefficient)
                * ufl.real(ufl.inner(field, field))
                * measure(tag)
            )
    gradient = fem_petsc.assemble_vector(fem.form(linear_form))
    gradient.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    local_value = fem.assemble_scalar(fem.form(value_form))
    goal_value = float(
        np.real(
            mesh_data.mesh.comm.allreduce(local_value, op=MPI.SUM)
        )
    )
    if (
        not np.all(
            np.isfinite(
                gradient.getArray(readonly=True)
            )
        )
        or not math.isfinite(goal_value)
        or goal_value < 0.0
    ):
        gradient.destroy()
        raise RuntimeError("A_volume gradient/value is invalid")

    direction = gradient.duplicate()
    try:
        start, end = map(int, direction.getOwnershipRange())
        rows = np.arange(start, end, dtype=np.float64)
        direction.getArray()[:] = (
            np.cos(0.017 * (rows + 1.0))
            + 1j * np.sin(0.023 * (rows + 1.0))
        ) / math.sqrt(max(direction.getSize(), 1))
        direction.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        tangent = float(np.real(gradient.dot(direction)))
        epsilon = 1.0e-7
        plus = fem.Function(space)
        minus = fem.Function(space)
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
        plus.x.array[:] = field.x.array + epsilon * direction_values
        minus.x.array[:] = field.x.array - epsilon * direction_values
        plus.x.scatter_forward()
        minus.x.scatter_forward()

        def functional(candidate: fem.Function) -> float:
            form = PETSc.ScalarType(0.0) * ufl.inner(
                candidate, candidate
            ) * measure
            for tag, coefficient in coefficients:
                if coefficient > 0.0:
                    form += (
                        PETSc.ScalarType(coefficient)
                        * ufl.real(ufl.inner(candidate, candidate))
                        * measure(tag)
                    )
            local = fem.assemble_scalar(fem.form(form))
            return float(
                np.real(
                    mesh_data.mesh.comm.allreduce(local, op=MPI.SUM)
                )
            )

        finite_difference = (
            functional(plus) - functional(minus)
        ) / (2.0 * epsilon)
        relative = abs(tangent - finite_difference) / max(
            abs(tangent),
            abs(finite_difference),
            1.0e-13,
        )
        if (
            relative > 2.0e-7
            and abs(tangent - finite_difference) > 1.0e-9
        ):
            raise RuntimeError(
                "A_volume gradient finite-difference closure failed: "
                f"relative={relative:.6e}"
            )
    except Exception:
        gradient.destroy()
        raise
    finally:
        direction.destroy()
    return gradient, {
        "construction": (
            "exact derivative of official material "
            "0.5*k0*Im(epsilon_r)*|E|^2 / incident_power"
        ),
        "goal_value": goal_value,
        "gradient_norm": float(gradient.norm()),
        "finite_difference_tangent": finite_difference,
        "adjoint_convention_tangent": tangent,
        "finite_difference_relative_error": relative,
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
) -> tuple[dict[str, PETSc.Vec], dict[str, Any]]:
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

    reduced: dict[str, PETSc.Vec] = {}
    try:
        for goal_id, p6_gradient in p6_gradients.items():
            reduced[goal_id] = view.reduction.reduce_p6_vector(
                p6_gradient,
                side="left",
            )
    except Exception:
        for vector in reduced.values():
            vector.destroy()
        raise
    finally:
        for vector in p6_gradients.values():
            vector.destroy()
    return reduced, {
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
    volume_p6 = None
    volume_reduced = None
    try:
        auxiliary, auxiliary_metadata = _auxiliary_gradients(view)
        volume_p6, volume_metadata = _assemble_volume_p6_gradient(view)
        volume_reduced = view.reduction.reduce_p6_vector(
            volume_p6,
            side="left",
        )
        auxiliary["scalar/A_volume"] = volume_reduced
        field, field_metadata = _field_p6_gradients(view)
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
            audit=MappingProxyType(audit),
        )
    except Exception:
        _destroy_vectors_once((*auxiliary.values(), *field.values()))
        raise
    finally:
        if volume_p6 is not None:
            volume_p6.destroy()


__all__ = [
    "GRADIENT_SCHEMA",
    "Task035eFormalGoalGradients",
    "Task035eGoalGradientError",
    "build_task035e_formal_goal_gradients",
]
