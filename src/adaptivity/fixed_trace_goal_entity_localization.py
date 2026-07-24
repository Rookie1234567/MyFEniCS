"""Fail-closed entity localization for recovered fixed-trace goal duals.

The assembly-time fixed p5-trace/p6-interior solve can recover an exact full
discrete Hermitian dual, including DtN auxiliary-to-cell-interior coupling.
It does not, by itself, retain a strict enriched p6-trace operator or the
residual of a lifted fixed-trace primal state in that enriched space.

Consequently this module deliberately reports only a normalized algebraic
dual-coefficient sensitivity proxy.  It must not be used or renamed as a DWR
indicator, and it cannot authorize Lane-B trace-mode selection.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import fem, mesh

from src.geometry.tetra_mesh_audit import (
    canonical_entity_key,
    canonical_owned_cell_ids,
    geometry_key_sha256,
    mesh_coordinate_tolerance,
)


_QUANTITY_TO_REFERENCE_BAND = {
    "power": "power",
    "amplitude_real": "amplitude_real",
    "amplitude_imag": "amplitude_imag",
}
_AXIS_BY_NAME = {"x": 0, "y": 1, "z": 2}


def _goal_record(goal: Any) -> dict[str, Any]:
    if isinstance(goal, Mapping):
        record = dict(goal)
    elif hasattr(goal, "as_dict"):
        record = dict(goal.as_dict())
    else:
        record = {
            name: getattr(goal, name)
            for name in (
                "side",
                "m",
                "n",
                "polarization",
                "quantity",
            )
        }
    required = {"side", "m", "n", "polarization", "quantity"}
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"goal identity is incomplete: {missing}")
    side = str(record["side"])
    if side not in {"top", "bottom"}:
        raise ValueError("goal side must be top or bottom")
    quantity = str(record["quantity"])
    if quantity not in _QUANTITY_TO_REFERENCE_BAND:
        raise ValueError(f"unsupported goal quantity: {quantity!r}")
    polarization = str(record["polarization"])
    if not polarization:
        raise ValueError("goal polarization must be nonempty")
    prefix = "R" if side == "top" else "T"
    label = (
        f"{prefix}_m{int(record['m'])}_n{int(record['n'])}_"
        f"{polarization}_{quantity}"
    )
    return {
        "side": side,
        "m": int(record["m"]),
        "n": int(record["n"]),
        "polarization": polarization,
        "quantity": quantity,
        "label": label,
    }


def reference_v1_goal_band(
    reference: Mapping[str, Any],
    goal: Any,
) -> dict[str, Any]:
    """Resolve one independent goal's frozen reference-v1 component band."""

    if (
        reference.get("status")
        != "significant_channel_reference_v1_frozen"
        or not isinstance(reference.get("channels"), list)
    ):
        raise ValueError("significant-channel reference v1 is not frozen")
    identity = _goal_record(goal)
    matches = [
        channel
        for channel in reference["channels"]
        if (
            str(channel.get("channel", {}).get("side"))
            == identity["side"]
            and int(channel.get("channel", {}).get("m", 10**9))
            == identity["m"]
            and int(channel.get("channel", {}).get("n", 10**9))
            == identity["n"]
            and str(
                channel.get("channel", {}).get("polarization")
            )
            == identity["polarization"]
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            "goal channel does not resolve uniquely in reference v1"
        )
    component = _QUANTITY_TO_REFERENCE_BAND[identity["quantity"]]
    try:
        band = float(
            matches[0]["numerical_convergence_band"]["absolute"][
                component
            ]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "reference v1 does not provide the requested component band"
        ) from error
    if not np.isfinite(band) or band <= 0.0:
        raise ValueError(
            "reference-v1 component band must be finite and positive"
        )
    return {
        "schema_version": (
            "task035b.reference-v1-goal-normalization.v1"
        ),
        "goal": identity,
        "reference_channel_label": str(
            matches[0]["channel"].get("label")
        ),
        "band_component": component,
        "absolute_band": band,
        "band_definition": str(
            matches[0]["numerical_convergence_band"].get(
                "definition"
            )
        ),
        "reference_payload_sha256": reference.get(
            "reference_payload_sha256"
        ),
        "semantics": (
            "reference-v1 per-channel numerical convergence band used "
            "only to normalize sensitivity; never an acceptance threshold"
        ),
    }


def _copy_dual_to_ghosted_function(
    space,
    recovered_full_dual: PETSc.Vec,
) -> fem.Function:
    dofmap = space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "entity localization requires scalar-blocked H(curl)"
        )
    index_map = dofmap.index_map
    if int(recovered_full_dual.getSize()) != int(index_map.size_global):
        raise ValueError(
            "recovered full dual does not match the function space"
        )
    if tuple(map(int, recovered_full_dual.getOwnershipRange())) != tuple(
        map(int, index_map.local_range)
    ):
        raise ValueError(
            "recovered full dual ownership differs from the function space"
        )
    field = fem.Function(space, name="recovered_goal_dual_for_proxy")
    owned = int(index_map.size_local)
    field.x.array[:owned] = np.asarray(
        recovered_full_dual.getArray(readonly=True),
        dtype=PETSc.ScalarType,
    )
    field.x.scatter_forward()
    return field


def _entity_dofs_by_local_index(
    space,
    entity_dimension: int,
) -> dict[int, np.ndarray]:
    msh = space.mesh
    tdim = msh.topology.dim
    msh.topology.create_entities(entity_dimension)
    msh.topology.create_connectivity(tdim, entity_dimension)
    msh.topology.create_connectivity(entity_dimension, tdim)
    cell_to_entity = msh.topology.connectivity(
        tdim,
        entity_dimension,
    )
    if cell_to_entity is None:
        raise RuntimeError("cell-to-entity connectivity is unavailable")
    cell_map = msh.topology.index_map(tdim)
    cells = int(cell_map.size_local + cell_map.num_ghosts)
    result: dict[int, np.ndarray] = {}
    layout = space.dofmap.dof_layout
    for cell in range(cells):
        cell_dofs = np.asarray(
            space.dofmap.cell_dofs(cell),
            dtype=np.int32,
        )
        for reference_entity, local_entity in enumerate(
            cell_to_entity.links(cell)
        ):
            if int(local_entity) in result:
                continue
            positions = np.asarray(
                layout.entity_dofs(
                    entity_dimension,
                    reference_entity,
                ),
                dtype=np.int32,
            )
            result[int(local_entity)] = cell_dofs[positions]
    return result


def _owned_entity_proxy_rows(
    space,
    field: fem.Function,
    *,
    entity_dimension: int,
    normalization_band: float,
    tolerance: float,
) -> list[tuple[tuple[tuple[int, int, int], ...], float]]:
    msh = space.mesh
    entity_map = msh.topology.index_map(entity_dimension)
    entity_dofs = _entity_dofs_by_local_index(
        space,
        entity_dimension,
    )
    owned_entities = np.arange(entity_map.size_local, dtype=np.int32)
    geometry = mesh.entities_to_geometry(
        msh,
        entity_dimension,
        owned_entities,
        False,
    )
    rows = []
    for local_entity, geometry_dofs in zip(
        owned_entities,
        geometry,
        strict=True,
    ):
        dofs = entity_dofs.get(int(local_entity))
        if dofs is None:
            raise RuntimeError("owned entity is not incident on a local cell")
        value = float(
            np.sum(np.abs(field.x.array[dofs]))
            / normalization_band
        )
        rows.append(
            (
                canonical_entity_key(
                    space.mesh.geometry.x[geometry_dofs],
                    tolerance,
                ),
                value,
            )
        )
    return rows


def _canonical_global_entity_rows(
    comm: MPI.Intracomm,
    local_rows: list[
        tuple[tuple[tuple[int, int, int], ...], float]
    ],
    *,
    label: str,
) -> list[dict[str, Any]]:
    combined = [
        row for packet in comm.allgather(local_rows) for row in packet
    ]
    keys = [key for key, _value in combined]
    if len(keys) != len(set(keys)):
        raise RuntimeError(
            f"owned canonical {label} geometry is not globally unique"
        )
    ordered = sorted(combined, key=lambda row: row[0])
    return [
        {
            "canonical_entity_id": index,
            "geometry_key": [
                list(point) for point in key
            ],
            "normalized_sensitivity_proxy": float(value),
        }
        for index, (key, value) in enumerate(ordered)
    ]


def _cell_and_incidence_rows(
    space,
    field: fem.Function,
    *,
    normalization_band: float,
    tolerance: float,
) -> tuple[
    list[tuple[int, tuple[tuple[int, int, int], ...], float]],
    dict[
        int,
        list[
            tuple[
                tuple[tuple[int, int, int], ...],
                int,
            ]
        ],
    ],
    list[tuple[tuple[int, int, int], ...]],
]:
    msh = space.mesh
    tdim = msh.topology.dim
    canonical_ids, records, ordered_cell_keys = (
        canonical_owned_cell_ids(msh, tolerance=tolerance)
    )
    cell_dofs = np.asarray(
        space.dofmap.dof_layout.entity_dofs(tdim, 0),
        dtype=np.int32,
    )
    cells = []
    incidence: dict[
        int,
        list[
            tuple[
                tuple[tuple[int, int, int], ...],
                int,
            ]
        ],
    ] = {1: [], 2: []}
    connectivity = {}
    for dimension in (1, 2):
        msh.topology.create_entities(dimension)
        msh.topology.create_connectivity(tdim, dimension)
        msh.topology.create_connectivity(dimension, tdim)
        connectivity[dimension] = msh.topology.connectivity(
            tdim,
            dimension,
        )
    for canonical_id, record in zip(
        canonical_ids,
        records,
        strict=True,
    ):
        local_cell_dofs = np.asarray(
            space.dofmap.cell_dofs(record.local_index),
            dtype=np.int32,
        )
        interior_value = float(
            np.sum(
                np.abs(
                    field.x.array[local_cell_dofs[cell_dofs]]
                )
            )
            / normalization_band
        )
        cells.append(
            (
                int(canonical_id),
                record.key,
                interior_value,
            )
        )
        for dimension in (1, 2):
            cell_to_entity = connectivity[dimension]
            if cell_to_entity is None:
                raise RuntimeError(
                    "cell-to-trace-entity connectivity is unavailable"
                )
            local_entities = np.asarray(
                cell_to_entity.links(record.local_index),
                dtype=np.int32,
            )
            geometry = mesh.entities_to_geometry(
                msh,
                dimension,
                local_entities,
                False,
            )
            for geometry_dofs in geometry:
                incidence[dimension].append(
                    (
                        canonical_entity_key(
                            msh.geometry.x[geometry_dofs],
                            tolerance,
                        ),
                        int(canonical_id),
                    )
                )
    return cells, incidence, ordered_cell_keys


def _canonical_cell_proxy_rows(
    comm: MPI.Intracomm,
    local_cells: list[
        tuple[int, tuple[tuple[int, int, int], ...], float]
    ],
    local_incidence: dict[
        int,
        list[
            tuple[
                tuple[tuple[int, int, int], ...],
                int,
            ]
        ],
    ],
    entity_rows: dict[int, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    cells = [
        row for packet in comm.allgather(local_cells) for row in packet
    ]
    cells.sort(key=lambda row: row[0])
    if [row[0] for row in cells] != list(range(len(cells))):
        raise RuntimeError("canonical cell IDs are not complete")
    values = {
        int(canonical_id): float(interior_value)
        for canonical_id, _key, interior_value in cells
    }
    interior_sum = float(sum(values.values()))
    trace_sum = 0.0
    for dimension in (1, 2):
        incidence_rows = [
            row
            for packet in comm.allgather(
                local_incidence[dimension]
            )
            for row in packet
        ]
        incident_cells: dict[
            tuple[tuple[int, int, int], ...],
            set[int],
        ] = defaultdict(set)
        for key, canonical_id in incidence_rows:
            incident_cells[key].add(int(canonical_id))
        proxy_by_key = {
            tuple(tuple(point) for point in row["geometry_key"]): float(
                row["normalized_sensitivity_proxy"]
            )
            for row in entity_rows[dimension]
        }
        if set(proxy_by_key) != set(incident_cells):
            raise RuntimeError(
                "trace entity proxy and cell incidence identities differ"
            )
        for key, proxy in proxy_by_key.items():
            members = incident_cells[key]
            if not members:
                raise RuntimeError("trace entity has no incident cell")
            share = proxy / len(members)
            trace_sum += proxy
            for canonical_id in members:
                values[canonical_id] += share
    rows = [
        {
            "canonical_cell_id": int(canonical_id),
            "geometry_key": [list(point) for point in key],
            "normalized_sensitivity_proxy": values[int(canonical_id)],
        }
        for canonical_id, key, _interior in cells
    ]
    cell_sum = float(sum(row["normalized_sensitivity_proxy"] for row in rows))
    entity_sum = interior_sum + trace_sum
    return rows, {
        "cell_interior_proxy_sum": interior_sum,
        "trace_entity_proxy_sum": trace_sum,
        "all_entity_proxy_sum": entity_sum,
        "cell_distributed_proxy_sum": cell_sum,
        "relative_closure": float(
            abs(cell_sum - entity_sum)
            / max(entity_sum, np.finfo(float).tiny)
        ),
    }


def _periodic_axis_rows(
    periodic_axes: Mapping[str | int, tuple[float, float]],
    *,
    tolerance: float,
) -> list[tuple[int, int, int]]:
    rows = []
    for axis, bounds in periodic_axes.items():
        resolved = _AXIS_BY_NAME.get(axis, axis)
        resolved = int(resolved)
        if resolved not in {0, 1, 2}:
            raise ValueError("periodic axis must be x/y/z or 0/1/2")
        if len(bounds) != 2:
            raise ValueError("periodic bounds must contain minimum/maximum")
        minimum, maximum = map(float, bounds)
        if not maximum > minimum:
            raise ValueError("periodic maximum must exceed minimum")
        rows.append(
            (
                resolved,
                int(round(minimum / tolerance)),
                int(round(maximum / tolerance)),
            )
        )
    if len({row[0] for row in rows}) != len(rows):
        raise ValueError("periodic axes must be unique")
    return sorted(rows)


def _periodic_components(
    entity_rows: list[dict[str, Any]],
    periodic_axes: list[tuple[int, int, int]],
) -> dict[str, Any]:
    groups: dict[
        tuple[tuple[int, int, int], ...],
        list[dict[str, Any]],
    ] = defaultdict(list)
    for row in entity_rows:
        points = [
            [int(value) for value in point]
            for point in row["geometry_key"]
        ]
        for axis, minimum, maximum in periodic_axes:
            if all(point[axis] == maximum for point in points):
                for point in points:
                    point[axis] = minimum
        normalized = tuple(sorted(tuple(point) for point in points))
        groups[normalized].append(row)
    components = []
    member_to_component = {}
    for component_id, (normalized, members) in enumerate(
        sorted(groups.items())
    ):
        member_ids = sorted(
            int(member["canonical_entity_id"])
            for member in members
        )
        values = [
            float(member["normalized_sensitivity_proxy"])
            for member in members
        ]
        for member_id in member_ids:
            member_to_component[member_id] = component_id
        components.append(
            {
                "periodic_component_id": component_id,
                "normalized_geometry_key": [
                    list(point) for point in normalized
                ],
                "member_canonical_entity_ids": member_ids,
                "member_count": len(member_ids),
                "component_proxy_sum": float(sum(values)),
                "component_proxy_max": float(max(values)),
            }
        )
    return {
        "component_count": len(components),
        "nontrivial_component_count": sum(
            component["member_count"] > 1
            for component in components
        ),
        "max_component_size": max(
            (
                component["member_count"]
                for component in components
            ),
            default=0,
        ),
        "aggregation": (
            "transitive normalized-coordinate components; preserve raw "
            "member values and report component sum/max"
        ),
        "member_to_component": member_to_component,
        "components": components,
    }


def localize_recovered_dual_sensitivity_proxy(
    space,
    recovered_full_dual: PETSc.Vec,
    *,
    goal: Any,
    reference_v1: Mapping[str, Any],
    periodic_axes: Mapping[str | int, tuple[float, float]],
) -> dict[str, Any]:
    """Localize one exact recovered goal dual as a fail-closed proxy.

    No residual vector is accepted by this API.  This prevents a solved-space
    residual, which is approximately zero and not enriched, from being
    mislabeled as a DWR estimator.
    """

    msh = space.mesh
    if msh.topology.dim != 3:
        raise ValueError("fixed-trace entity localization requires 3D")
    if msh.topology.cell_type != mesh.CellType.hexahedron:
        raise ValueError(
            "fixed-trace entity localization currently requires hexahedra"
        )
    vertex_dofs = space.dofmap.dof_layout.entity_dofs(0, 0)
    if len(vertex_dofs):
        raise ValueError(
            "H(curl) localization expects no vertex-associated DoFs"
        )
    normalization = reference_v1_goal_band(reference_v1, goal)
    band = float(normalization["absolute_band"])
    tolerance = mesh_coordinate_tolerance(msh)
    field = _copy_dual_to_ghosted_function(
        space,
        recovered_full_dual,
    )
    local_entity_rows = {
        dimension: _owned_entity_proxy_rows(
            space,
            field,
            entity_dimension=dimension,
            normalization_band=band,
            tolerance=tolerance,
        )
        for dimension in (1, 2)
    }
    entity_rows = {
        dimension: _canonical_global_entity_rows(
            msh.comm,
            local_entity_rows[dimension],
            label="edge" if dimension == 1 else "face",
        )
        for dimension in (1, 2)
    }
    (
        local_cells,
        local_incidence,
        ordered_cell_keys,
    ) = _cell_and_incidence_rows(
        space,
        field,
        normalization_band=band,
        tolerance=tolerance,
    )
    cell_rows, closure = _canonical_cell_proxy_rows(
        msh.comm,
        local_cells,
        local_incidence,
        entity_rows,
    )
    if (
        not np.isfinite(closure["relative_closure"])
        or closure["relative_closure"] > 5.0e-13
    ):
        raise RuntimeError(
            "cell distribution does not close to entity sensitivity"
        )
    periodic_axis_rows = _periodic_axis_rows(
        periodic_axes,
        tolerance=tolerance,
    )
    periodic = {
        "axes": [
            {
                "axis": axis,
                "minimum_quantized": minimum,
                "maximum_quantized": maximum,
            }
            for axis, minimum, maximum in periodic_axis_rows
        ],
        "edge_trace": _periodic_components(
            entity_rows[1],
            periodic_axis_rows,
        ),
        "face_trace": _periodic_components(
            entity_rows[2],
            periodic_axis_rows,
        ),
    }
    return {
        "schema_version": (
            "task035b.fixed-trace-goal-entity-sensitivity-proxy.v1"
        ),
        "status": "proxy_only_no_formal_lane_b_selection",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "goal": normalization["goal"],
        "normalization": normalization,
        "estimator": (
            "recovered_dual_coefficient_sensitivity_proxy"
        ),
        "proxy_definition": (
            "sum(abs(oriented global recovered-dual coefficients)) "
            "per Basix entity divided by the independent goal's "
            "reference-v1 component band"
        ),
        "actual_enriched_residual_available": False,
        "residual_weighted": False,
        "actual_dwr_indicator": False,
        "dwr_unavailable_reason": (
            "the fixed p5-trace/p6-interior assembly cache does not "
            "contain a strict global-p6-trace enriched operator and the "
            "residual of the lifted fixed-trace primal in that space"
        ),
        "lane_b_formal_selection_authorized": False,
        "orientation_scope": (
            "global DOLFINx-oriented coefficients; absolute aggregation "
            "is insensitive to sign/permutation but is not claimed "
            "invariant under arbitrary non-unitary basis changes"
        ),
        "mpi_size": int(msh.comm.size),
        "coordinate_tolerance": tolerance,
        "mesh_geometry_sha256": geometry_key_sha256(
            ordered_cell_keys
        ),
        "entities": {
            "edge_trace": {
                "entity_dimension": 1,
                "canonical_entity_count": len(entity_rows[1]),
                "geometry_sha256": geometry_key_sha256(
                    tuple(
                        tuple(tuple(point) for point in row["geometry_key"])
                        for row in entity_rows[1]
                    )
                ),
                "rows": entity_rows[1],
            },
            "face_trace": {
                "entity_dimension": 2,
                "canonical_entity_count": len(entity_rows[2]),
                "geometry_sha256": geometry_key_sha256(
                    tuple(
                        tuple(tuple(point) for point in row["geometry_key"])
                        for row in entity_rows[2]
                    )
                ),
                "rows": entity_rows[2],
            },
            "cell": {
                "entity_dimension": 3,
                "canonical_entity_count": len(cell_rows),
                "distribution": (
                    "cell-interior proxy plus each incident shared "
                    "edge/face proxy divided by its global cell incidence"
                ),
                "rows": cell_rows,
            },
        },
        "cell_distribution_closure": closure,
        "periodic_transitive_aggregation": periodic,
        "partition_independent_identity": (
            "sorted canonical quantized entity geometry"
        ),
    }


__all__ = [
    "localize_recovered_dual_sensitivity_proxy",
    "reference_v1_goal_band",
]
