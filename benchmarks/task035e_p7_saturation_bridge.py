#!/usr/bin/env python3
"""Bind Task035e p7 shadow components to an executed multilevel plan.

This bridge is deliberately structural.  It replays the exact Stage-4
multilevel mesh and degree authority, inventories every current p6 leaf and
its physical edge/face/cell shadow orbits, closes the trace inventory over the
actual Floquet graph, and audits distributed ownership.  It never treats
those checks as a numerical p7 saturation measurement.

The existing p7 complement components qualify mixed p4/p5/p6-to-p7 edge,
face, cell, hanging-patch, orientation, and Floquet algebra.  This bridge
binds those components to every selected physical entity.  Any missing
identity remains a closed, machine-readable structural blocker instead of
constructing fictitious rows.

The Basix p7 mathematics is identical on every rank and is comparatively
expensive.  Each rank independently derives and hashes the request catalog;
rank 0 evaluates it once, broadcasts the canonical audit packet, and every
rank validates the packet digest.  Distributed mesh ownership and row
numbering are still checked independently on all ranks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np

from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    Stage4LocalHReductionAuthority,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
)
from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
)
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
)
from src.adaptivity.task035e_p7_constraint_shadow import (
    audit_mixed_p7_floquet_entity,
    build_mixed_selective_p7_shadow_space,
    build_p7_shadow_hanging_closure,
    close_mixed_p7_local_selection,
)
from src.adaptivity.task035e_p7_trace_shadow import (
    build_p7_trace_shadow_catalog,
)
from src.common.config_3d import target_stage4_config


P7_SATURATION_BRIDGE_SCHEMA = (
    "task035e.p7-saturation-structural-bridge.v1"
)
P7_SATURATION_BINDING_SCHEMA = (
    "task035e.p7-saturation-candidate-binding.v1"
)
P7_SATURATION_BRIDGE_OUTER_SCHEMA = (
    "task035e.p7-saturation-structural-evidence.v1"
)
_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FORMAL_MPI_SIZE = 8


class P7SaturationBridgeError(ValueError):
    """Raised when candidate or execution identities cannot be bound."""


def _canonical(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _canonical(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha1(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if _SHA1_RE.fullmatch(normalized) is None:
        raise P7SaturationBridgeError(
            f"{label} must be a lowercase 40-character Git SHA"
        )
    return normalized


def _sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise P7SaturationBridgeError(
            f"{label} must be a lowercase SHA-256"
        )
    return normalized


def _exact_mapping(
    value: Any,
    expected: set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P7SaturationBridgeError(f"{label} must be an object")
    observed = set(map(str, value))
    if observed != expected:
        raise P7SaturationBridgeError(
            f"{label} fields differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    return value


@dataclass(frozen=True, slots=True)
class P7SaturationCandidateBinding:
    """Minimal executed-candidate identity needed by the structural replay."""

    source_sha: str
    cycle_index: int
    output_sha256: str
    plan_path: Path
    plan_file_sha256: str
    forest_leaf_catalog_sha256: str
    carrier_connectivity_sha256: str
    mesh_cell_box_catalog_sha256: str
    cell_degree_plan_sha256: str
    geometry_canonical_entity_degree_sha256: str
    formal_mpi_size: int = _FORMAL_MPI_SIZE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_sha",
            _sha1(self.source_sha, label="source_sha"),
        )
        for name in (
            "output_sha256",
            "plan_file_sha256",
            "forest_leaf_catalog_sha256",
            "carrier_connectivity_sha256",
            "mesh_cell_box_catalog_sha256",
            "cell_degree_plan_sha256",
            "geometry_canonical_entity_degree_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _sha256(getattr(self, name), label=name),
            )
        cycle_index = int(self.cycle_index)
        if cycle_index < 0:
            raise P7SaturationBridgeError(
                "candidate cycle_index must be nonnegative"
            )
        object.__setattr__(self, "cycle_index", cycle_index)
        plan_path = Path(self.plan_path).expanduser().resolve()
        if not plan_path.is_file():
            raise P7SaturationBridgeError(
                f"candidate plan does not exist: {plan_path}"
            )
        object.__setattr__(self, "plan_path", plan_path)
        formal_mpi_size = int(self.formal_mpi_size)
        if formal_mpi_size != _FORMAL_MPI_SIZE:
            raise P7SaturationBridgeError(
                "Task035e p7 saturation qualification requires formal MPI8"
            )
        object.__setattr__(self, "formal_mpi_size", formal_mpi_size)


_BINDING_FIELDS = {
    "schema_version",
    "source_sha",
    "cycle_index",
    "output_sha256",
    "plan_path",
    "plan_file_sha256",
    "forest_leaf_catalog_sha256",
    "carrier_connectivity_sha256",
    "mesh_cell_box_catalog_sha256",
    "cell_degree_plan_sha256",
    "geometry_canonical_entity_degree_sha256",
    "formal_mpi_size",
}


def candidate_binding_payload(
    binding: P7SaturationCandidateBinding,
) -> dict[str, Any]:
    """Return the strict JSON representation of one candidate binding."""

    return {
        "schema_version": P7_SATURATION_BINDING_SCHEMA,
        "source_sha": binding.source_sha,
        "cycle_index": binding.cycle_index,
        "output_sha256": binding.output_sha256,
        "plan_path": str(binding.plan_path),
        "plan_file_sha256": binding.plan_file_sha256,
        "forest_leaf_catalog_sha256": (
            binding.forest_leaf_catalog_sha256
        ),
        "carrier_connectivity_sha256": (
            binding.carrier_connectivity_sha256
        ),
        "mesh_cell_box_catalog_sha256": (
            binding.mesh_cell_box_catalog_sha256
        ),
        "cell_degree_plan_sha256": binding.cell_degree_plan_sha256,
        "geometry_canonical_entity_degree_sha256": (
            binding.geometry_canonical_entity_degree_sha256
        ),
        "formal_mpi_size": binding.formal_mpi_size,
    }


def candidate_binding_from_payload(
    payload: Any,
) -> P7SaturationCandidateBinding:
    """Load a strict, fail-closed candidate binding payload."""

    row = _exact_mapping(
        payload,
        _BINDING_FIELDS,
        label="p7 saturation candidate binding",
    )
    if row["schema_version"] != P7_SATURATION_BINDING_SCHEMA:
        raise P7SaturationBridgeError(
            "p7 saturation candidate binding schema differs"
        )
    return P7SaturationCandidateBinding(
        source_sha=row["source_sha"],
        cycle_index=row["cycle_index"],
        output_sha256=row["output_sha256"],
        plan_path=Path(str(row["plan_path"])),
        plan_file_sha256=row["plan_file_sha256"],
        forest_leaf_catalog_sha256=row[
            "forest_leaf_catalog_sha256"
        ],
        carrier_connectivity_sha256=row[
            "carrier_connectivity_sha256"
        ],
        mesh_cell_box_catalog_sha256=row[
            "mesh_cell_box_catalog_sha256"
        ],
        cell_degree_plan_sha256=row["cell_degree_plan_sha256"],
        geometry_canonical_entity_degree_sha256=row[
            "geometry_canonical_entity_degree_sha256"
        ],
        formal_mpi_size=row["formal_mpi_size"],
    )


def candidate_binding_from_adapted(
    adapted: Any,
) -> P7SaturationCandidateBinding:
    """Copy the required fields from an ``AdaptedCandidateOutput``.

    The adapter is intentionally duck-typed so this structural module does not
    import the execution-facing candidate parser or broaden its dependency
    graph.
    """

    try:
        return P7SaturationCandidateBinding(
            source_sha=adapted.source_sha,
            cycle_index=adapted.cycle_index,
            output_sha256=adapted.output_sha256,
            plan_path=adapted.plan_path,
            plan_file_sha256=adapted.plan_file_sha256,
            forest_leaf_catalog_sha256=(
                adapted.forest_leaf_catalog_sha256
            ),
            carrier_connectivity_sha256=(
                adapted.carrier_connectivity_sha256
            ),
            mesh_cell_box_catalog_sha256=(
                adapted.mesh_cell_box_catalog_sha256
            ),
            cell_degree_plan_sha256=(
                adapted.cell_degree_plan_sha256
            ),
            geometry_canonical_entity_degree_sha256=(
                adapted.geometry_canonical_entity_degree_sha256
            ),
        )
    except AttributeError as exc:
        raise P7SaturationBridgeError(
            "adapted candidate lacks a required structural identity"
        ) from exc


def candidate_binding_from_authority(
    *,
    context: Stage4LocalHContext,
    reduction: Stage4LocalHReductionAuthority,
    source_sha: str,
    cycle_index: int,
    output_sha256: str,
) -> P7SaturationCandidateBinding:
    """Construct a binding for diagnostics from an already executed authority.

    Formal workflows should normally use :func:`candidate_binding_from_adapted`.
    This constructor exists for lightweight component fixtures and still binds
    every plan, forest, carrier, and degree-map digest.
    """

    degree = reduction.degree_plan.audit
    return P7SaturationCandidateBinding(
        source_sha=source_sha,
        cycle_index=cycle_index,
        output_sha256=output_sha256,
        plan_path=Path(context.plan_path),
        plan_file_sha256=context.plan_file_sha256,
        forest_leaf_catalog_sha256=str(
            context.forest.audit["leaf_catalog_sha256"]
        ),
        carrier_connectivity_sha256=str(
            context.carrier.audit["canonical_connectivity_sha256"]
        ),
        mesh_cell_box_catalog_sha256=str(
            degree["mesh_cell_box_catalog_sha256"]
        ),
        cell_degree_plan_sha256=str(
            degree["cell_degree_plan_sha256"]
        ),
        geometry_canonical_entity_degree_sha256=str(
            degree["geometry_canonical_entity_degree_sha256"]
        ),
    )


def _binding_audit(
    context: Stage4LocalHContext,
    reduction: Stage4LocalHReductionAuthority,
    binding: P7SaturationCandidateBinding,
) -> dict[str, Any]:
    degree = reduction.degree_plan.audit
    observed = {
        "plan_path": str(Path(context.plan_path).resolve()),
        "plan_file_sha256": context.plan_file_sha256,
        "forest_leaf_catalog_sha256": str(
            context.forest.audit["leaf_catalog_sha256"]
        ),
        "carrier_connectivity_sha256": str(
            context.carrier.audit["canonical_connectivity_sha256"]
        ),
        "mesh_cell_box_catalog_sha256": str(
            degree["mesh_cell_box_catalog_sha256"]
        ),
        "cell_degree_plan_sha256": str(
            degree["cell_degree_plan_sha256"]
        ),
        "geometry_canonical_entity_degree_sha256": str(
            degree["geometry_canonical_entity_degree_sha256"]
        ),
    }
    expected = {
        "plan_path": str(binding.plan_path),
        "plan_file_sha256": binding.plan_file_sha256,
        "forest_leaf_catalog_sha256": (
            binding.forest_leaf_catalog_sha256
        ),
        "carrier_connectivity_sha256": (
            binding.carrier_connectivity_sha256
        ),
        "mesh_cell_box_catalog_sha256": (
            binding.mesh_cell_box_catalog_sha256
        ),
        "cell_degree_plan_sha256": binding.cell_degree_plan_sha256,
        "geometry_canonical_entity_degree_sha256": (
            binding.geometry_canonical_entity_degree_sha256
        ),
    }
    checks = {
        name: observed[name] == expected[name] for name in expected
    }
    checks["plan_file_rehashed"] = (
        _file_sha256(binding.plan_path) == binding.plan_file_sha256
    )
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise P7SaturationBridgeError(
            "candidate/plan structural identity differs: "
            + ", ".join(failures)
        )
    return {
        "pass": True,
        "checks": checks,
        "expected": expected,
        "observed": observed,
        "candidate_source_sha": binding.source_sha,
        "candidate_cycle_index": binding.cycle_index,
        "candidate_output_sha256": binding.output_sha256,
    }


def _physical_node(
    dimension: int,
    geometry_key: Sequence[int],
) -> tuple[int, tuple[int, ...]]:
    return int(dimension), tuple(map(int, geometry_key))


def _physical_node_row(
    node: tuple[int, tuple[int, ...]],
) -> dict[str, Any]:
    return {
        "dimension": node[0],
        "geometry_key": list(node[1]),
    }


def _relation_node(relation: Any, *, slave: bool) -> tuple[int, tuple[int, ...]]:
    rows = relation.slave_rows if slave else relation.master_rows
    identities = {
        _physical_node(
            row.entity_dimension,
            row.entity_geometry_key,
        )
        for row in rows
    }
    if len(identities) != 1:
        raise P7SaturationBridgeError(
            "one trace relation endpoint spans multiple physical entities"
        )
    return next(iter(identities))


def _relation_nodes(
    relation: Any,
) -> set[tuple[int, tuple[int, ...]]]:
    return {
        _physical_node(
            row.entity_dimension,
            row.entity_geometry_key,
        )
        for row in (*relation.slave_rows, *relation.master_rows)
    }


def _owner_cell_packet(
    context: Stage4LocalHContext,
    reduction: Stage4LocalHReductionAuthority,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    constraints = reduction.trace_constraints
    entity_map = constraints.entity_map
    mesh = entity_map.mesh
    rank = int(mesh.comm.rank)
    cells: list[dict[str, Any]] = []
    for cell in entity_map.owned_cells:
        canonical_leaf = int(
            context.carrier.canonical_leaf_by_local_cell[cell.local_cell]
        )
        leaf = context.forest.leaves[canonical_leaf]
        trace: list[dict[str, Any]] = []
        for dimension in (1, 2):
            local_entities = np.asarray(
                cell.entity_ids[dimension],
                dtype=np.int32,
            )
            global_entities = np.asarray(
                mesh.topology.index_map(dimension).local_to_global(
                    local_entities
                ),
                dtype=np.int64,
            )
            expected_degrees = (
                cell.degree_map.edges
                if dimension == 1
                else cell.degree_map.faces
            )
            if len(global_entities) != len(expected_degrees):
                raise P7SaturationBridgeError(
                    "cell entity and degree catalogs differ"
                )
            for local_index, (global_entity, degree) in enumerate(
                zip(global_entities, expected_degrees, strict=True)
            ):
                block = constraints.entity_blocks[
                    (dimension, int(global_entity))
                ]
                physical = block.physical_entity
                if int(physical.degree) != int(degree):
                    raise P7SaturationBridgeError(
                        "cell degree differs from physical trace authority"
                    )
                trace.append(
                    {
                        "dimension": dimension,
                        "local_entity": local_index,
                        "global_entity": int(global_entity),
                        "geometry_key": list(physical.geometry_key),
                        "degree": int(degree),
                        "dolfinx_owner_rank": int(
                            block.dolfinx_owner_rank
                        ),
                        "active_vector_work_owner_rank": int(
                            block.active_vector_work_owner_rank
                        ),
                    }
                )
        cells.append(
            {
                "target_id": canonical_hp_cell_target_id(leaf.key),
                "canonical_leaf": canonical_leaf,
                "dyadic_key": leaf.key.to_dict(),
                "box": list(leaf.box),
                "material_tag": int(leaf.material_tag),
                "cell_degree": int(cell.degree_map.cell),
                "cell_info": int(cell.cell_info),
                "global_cell": int(cell.global_cell),
                "owner_rank": rank,
                "trace": trace,
            }
        )

    owner_blocks = [
        {
            "dimension": int(block.dimension),
            "global_entity": int(block.global_entity),
            "geometry_key": list(block.physical_entity.geometry_key),
            "degree": int(block.physical_entity.degree),
            "owner_rank": rank,
        }
        for block in constraints.entity_blocks.values()
        if int(block.dolfinx_owner_rank) == rank
    ]
    work_blocks = [
        {
            "dimension": int(block.dimension),
            "global_entity": int(block.global_entity),
            "geometry_key": list(block.physical_entity.geometry_key),
            "degree": int(block.physical_entity.degree),
            "work_owner_rank": rank,
        }
        for block in constraints.work_owned_entity_blocks
    ]
    return cells, owner_blocks, work_blocks


def _unique_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    keys: tuple[str, ...],
    label: str,
) -> bool:
    identities = [tuple(row[key] for key in keys) for row in rows]
    if len(identities) != len(set(identities)):
        return False
    return bool(label)


def _expected_numbered_rows(
    global_degrees: Mapping[int, np.ndarray],
) -> int:
    total = 0
    for dimension in (1, 2, 3):
        for degree in np.asarray(global_degrees[dimension], dtype=np.int32):
            p = int(degree)
            count = {
                1: p,
                2: 2 * p * (p - 1),
                3: 3 * p * (p - 1) ** 2,
            }[dimension]
            total += count
    return total


def _components(
    nodes: set[tuple[int, tuple[int, ...]]],
    edges: Sequence[
        tuple[
            tuple[int, tuple[int, ...]],
            tuple[int, tuple[int, ...]],
        ]
    ],
) -> tuple[tuple[tuple[int, tuple[int, ...]], ...], ...]:
    parent = {node: node for node in nodes}

    def find(
        node: tuple[int, tuple[int, ...]],
    ) -> tuple[int, tuple[int, ...]]:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(
        left: tuple[int, tuple[int, ...]],
        right: tuple[int, tuple[int, ...]],
    ) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in edges:
        if left not in parent or right not in parent:
            raise P7SaturationBridgeError(
                "Floquet relation names an absent physical trace entity"
            )
        union(left, right)
    groups: dict[
        tuple[int, tuple[int, ...]],
        list[tuple[int, tuple[int, ...]]],
    ] = {}
    for node in sorted(nodes):
        groups.setdefault(find(node), []).append(node)
    return tuple(
        sorted(
            (tuple(sorted(group)) for group in groups.values()),
            key=lambda group: group[0],
        )
    )


def _blocker(
    code: str,
    *,
    count: int,
    examples: Sequence[Any],
    explanation: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "qualification_gap",
        "count": int(count),
        "examples": _canonical(tuple(examples)[:8]),
        "explanation": explanation,
        "remediation": remediation,
    }


def _trace_complement_dimension(
    *,
    family: str,
    dimension: int,
    source_degree: int,
) -> int:
    degree = int(source_degree)
    if family == "hcurl":
        source = degree if dimension == 1 else 2 * degree * (degree - 1)
        target = 7 if dimension == 1 else 84
    elif family == "h1":
        source = degree - 1 if dimension == 1 else (degree - 1) ** 2
        target = 6 if dimension == 1 else 36
    else:
        raise ValueError(f"unknown shadow family {family!r}")
    return int(target - source)


def _cell_complement_dimension(
    *,
    family: str,
    source_degree: int,
) -> int:
    degree = int(source_degree)
    if family == "hcurl":
        return int(756 - 3 * degree * (degree - 1) ** 2)
    if family == "h1":
        return int(216 - (degree - 1) ** 3)
    raise ValueError(f"unknown shadow family {family!r}")


def _cell_degree_map(
    cell: Mapping[str, Any],
) -> HexaEntityDegreeMap:
    trace = cell["trace"]
    edges = tuple(
        int(row["degree"])
        for row in sorted(
            (
                row for row in trace if int(row["dimension"]) == 1
            ),
            key=lambda row: int(row["local_entity"]),
        )
    )
    faces = tuple(
        int(row["degree"])
        for row in sorted(
            (
                row for row in trace if int(row["dimension"]) == 2
            ),
            key=lambda row: int(row["local_entity"]),
        )
    )
    return HexaEntityDegreeMap(
        edges=edges,
        faces=faces,
        cell=int(cell["cell_degree"]),
    )


def _degree_map_payload(
    degree_map: HexaEntityDegreeMap,
) -> dict[str, Any]:
    return {
        "edges": list(map(int, degree_map.edges)),
        "faces": list(map(int, degree_map.faces)),
        "cell": int(degree_map.cell),
        "signature": degree_map.signature,
    }


def _degree_map_from_payload(
    payload: Mapping[str, Any],
) -> HexaEntityDegreeMap:
    degree_map = HexaEntityDegreeMap(
        edges=tuple(map(int, payload["edges"])),
        faces=tuple(map(int, payload["faces"])),
        cell=int(payload["cell"]),
    )
    if degree_map.signature != str(payload["signature"]):
        raise P7SaturationBridgeError(
            "broadcast mixed-p degree-map signature drifted"
        )
    return degree_map


def _execute_mathematical_audit_requests(
    requests: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute expensive, globally identical p7 mathematics once on rank 0."""

    mixed_component_errors: list[dict[str, Any]] = []
    mixed_component_audits: list[dict[str, Any]] = []
    for request in requests["mixed"]:
        degree_map = _degree_map_from_payload(request["degree_map"])
        requested_edges = tuple(map(int, request["requested_edges"]))
        requested_faces = tuple(map(int, request["requested_faces"]))
        try:
            component = build_mixed_selective_p7_shadow_space(
                degree_map,
                requested_edges,
                requested_faces,
                tuple(map(int, request["cell_infos"])),
            )
        except (RuntimeError, ValueError) as exc:
            mixed_component_errors.append(
                {
                    "degree_map_signature": degree_map.signature,
                    "requested_edges": list(requested_edges),
                    "requested_faces": list(requested_faces),
                    "target_ids": list(request["target_ids_preview"]),
                    "error": str(exc),
                }
            )
        else:
            mixed_component_audits.append(
                {
                    "degree_map_signature": degree_map.signature,
                    "requested_edges": list(requested_edges),
                    "requested_faces": list(requested_faces),
                    "cell_infos": list(map(int, request["cell_infos"])),
                    "cell_count": int(request["cell_count"]),
                    "target_ids_sha256": request["target_ids_sha256"],
                    "component_sha256": component.audit[
                        "component_sha256"
                    ],
                    "shadow_hcurl_dimension": component.audit[
                        "shadow_hcurl_dimension"
                    ],
                    "shadow_h1_dimension": component.audit[
                        "shadow_h1_dimension"
                    ],
                    "gradient_range_error_max": component.audit[
                        "gradient_range_error_max"
                    ],
                    "orientation_error_max": max(
                        component.audit[
                            "hcurl_orientation_commuting_error_max"
                        ],
                        component.audit[
                            "h1_orientation_commuting_error_max"
                        ],
                    ),
                }
            )

    hanging_component_errors: list[dict[str, Any]] = []
    hanging_component_audits: list[dict[str, Any]] = []
    for request in requests["hanging"]:
        patch_index = int(request["patch_index"])
        degrees = tuple(map(int, request["source_degrees"]))
        if len(degrees) != 1:
            hanging_component_errors.append(
                {
                    "patch_index": patch_index,
                    "error": "hanging patch mixes source degrees",
                    "degrees": list(degrees),
                }
            )
            continue
        degree = degrees[0]
        try:
            component = build_p7_shadow_hanging_closure(degree)
        except (RuntimeError, ValueError) as exc:
            hanging_component_errors.append(
                {
                    "patch_index": patch_index,
                    "source_degree": degree,
                    "error": str(exc),
                }
            )
        else:
            hanging_component_audits.append(
                {
                    "patch_index": patch_index,
                    "source_degree": degree,
                    "component_sha256": component.audit[
                        "component_sha256"
                    ],
                    "hcurl_hanging_injection_error_max": (
                        component.audit[
                            "hcurl_hanging_injection_error_max"
                        ]
                    ),
                    "h1_hanging_injection_error_max": (
                        component.audit[
                            "h1_hanging_injection_error_max"
                        ]
                    ),
                    "hcurl_d4_injection_error_max": component.audit[
                        "hcurl_d4_injection_error_max"
                    ],
                }
            )

    floquet_component_errors: list[dict[str, Any]] = []
    floquet_component_audits: list[dict[str, Any]] = []
    for request in requests["floquet"]:
        degree = int(request["source_degree"])
        dimension = int(request["dimension"])
        phase = complex(*map(float, request["phase"]))
        phase_identity_error = float(
            request["physical_phase_identity_error_max"]
        )
        try:
            if phase_identity_error > 5.0e-11:
                raise RuntimeError(
                    "physical Floquet transform is not scalar identity"
                )
            audit = audit_mixed_p7_floquet_entity(
                degree,
                dimension,
                phase,
            )
        except (RuntimeError, ValueError) as exc:
            floquet_component_errors.append(
                {
                    "source_degree": degree,
                    "dimension": dimension,
                    "phase": [phase.real, phase.imag],
                    "physical_phase_identity_error_max": (
                        phase_identity_error
                    ),
                    "error": str(exc),
                }
            )
        else:
            floquet_component_audits.append(dict(audit))

    try:
        p7_catalog = build_p7_trace_shadow_catalog()
    except (RuntimeError, ValueError) as exc:
        p7_catalog_audit: dict[str, Any] = {
            "schema_version": (
                "task035e.p7-trace-shadow-catalog-error.v1"
            ),
            "component_pass": False,
            "error": str(exc),
        }
        p7_catalog_sha256 = _json_sha256(
            {"catalog_error": str(exc)}
        )
        p7_component_pass = False
        p7_catalog_error = str(exc)
    else:
        p7_catalog_audit = _canonical(p7_catalog.audit)
        p7_catalog_sha256 = _json_sha256(p7_catalog_audit)
        p7_component_pass = bool(
            p7_catalog.audit["component_pass"] is True
            and p7_catalog.audit[
                "inactive_p7_modes_globally_numbered"
            ]
            is False
            and p7_catalog.audit["selectable_as_production"] is False
        )
        p7_catalog_error = None

    core = {
        "schema_version": "task035e.p7-mathematical-audit-broadcast.v1",
        "request_catalog_sha256": requests["request_catalog_sha256"],
        "execution_rank": 0,
        "mixed_component_errors": mixed_component_errors,
        "mixed_component_audits": mixed_component_audits,
        "hanging_component_errors": hanging_component_errors,
        "hanging_component_audits": hanging_component_audits,
        "floquet_component_errors": floquet_component_errors,
        "floquet_component_audits": floquet_component_audits,
        "p7_catalog_audit": p7_catalog_audit,
        "p7_catalog_sha256": p7_catalog_sha256,
        "p7_catalog_error": p7_catalog_error,
        "p7_component_pass": p7_component_pass,
    }
    return {
        **_canonical(core),
        "mathematical_audit_sha256": _json_sha256(core),
    }


def build_p7_saturation_structural_evidence(
    *,
    context: Stage4LocalHContext,
    reduction: Stage4LocalHReductionAuthority,
    binding: P7SaturationCandidateBinding,
) -> Mapping[str, Any]:
    """Build closed structural evidence without granting saturation credit."""

    if context.audit.get("pass") is not True:
        raise P7SaturationBridgeError("Stage-4 mesh context did not pass")
    if reduction.audit.get("pass") is not True:
        raise P7SaturationBridgeError(
            "Stage-4 reduction authority did not pass"
        )
    comm = reduction.trace_constraints.entity_map.mesh.comm
    if context.carrier.mesh.comm != comm:
        raise P7SaturationBridgeError(
            "mesh context and reduction use different communicators"
        )
    binding_audit = _binding_audit(context, reduction, binding)
    local_cells, local_owner_blocks, local_work_blocks = _owner_cell_packet(
        context,
        reduction,
    )
    packets = comm.allgather(
        {
            "rank": int(comm.rank),
            "cells": local_cells,
            "owner_blocks": local_owner_blocks,
            "work_blocks": local_work_blocks,
        }
    )
    if [packet["rank"] for packet in packets] != list(range(comm.size)):
        raise P7SaturationBridgeError("MPI rank packet catalog is incomplete")
    all_cells = sorted(
        (
            row
            for packet in packets
            for row in packet["cells"]
        ),
        key=lambda row: row["target_id"],
    )
    all_owner_blocks = sorted(
        (
            row
            for packet in packets
            for row in packet["owner_blocks"]
        ),
        key=lambda row: (row["dimension"], row["global_entity"]),
    )
    all_work_blocks = sorted(
        (
            row
            for packet in packets
            for row in packet["work_blocks"]
        ),
        key=lambda row: (row["dimension"], row["global_entity"]),
    )
    entity_map = reduction.trace_constraints.entity_map
    physical = reduction.trace_constraints.authority
    expected_cell_ids = tuple(
        sorted(
            canonical_hp_cell_target_id(cell.key)
            for cell in context.forest.leaves
        )
    )
    observed_cell_ids = tuple(row["target_id"] for row in all_cells)
    expected_topological_trace_entities = sum(
        int(
            entity_map.audit["global_entity_counts"][str(dimension)]
        )
        for dimension in (1, 2)
    )
    owner_unique = _unique_rows(
        all_owner_blocks,
        keys=("dimension", "global_entity"),
        label="DOLFINx owner blocks",
    )
    work_unique = _unique_rows(
        all_work_blocks,
        keys=("dimension", "global_entity"),
        label="active-vector work blocks",
    )
    ownership_checks = {
        "one_owner_per_canonical_leaf": (
            observed_cell_ids == expected_cell_ids
        ),
        "all_forest_leaves_enumerated": (
            len(all_cells) == len(context.forest.leaves)
        ),
        "dolfinx_entity_owner_unique": owner_unique,
        "dolfinx_entity_owner_catalog_complete": (
            len(all_owner_blocks) == expected_topological_trace_entities
        ),
        "active_vector_work_owner_unique": work_unique,
        "active_vector_work_owner_catalog_complete": (
            len(all_work_blocks) == expected_topological_trace_entities
        ),
    }

    global_packet = {
        "cells": all_cells,
        "owner_blocks": all_owner_blocks,
        "work_blocks": all_work_blocks,
    }
    global_digest = _json_sha256(global_packet)
    digest_packets = comm.allgather(global_digest)
    rank_packet_digests = [
        _json_sha256(packet) for packet in packets
    ]
    mpi_digest_pass = len(set(digest_packets)) == 1
    mpi8_status = (
        "pass"
        if comm.size == binding.formal_mpi_size
        and mpi_digest_pass
        and all(ownership_checks.values())
        else "not_run"
        if comm.size != binding.formal_mpi_size
        else "fail"
    )

    physical_entities = {
        _physical_node(entity.dimension, entity.geometry_key): entity
        for entity in physical.entities
    }
    adjacency: dict[
        tuple[int, tuple[int, ...]],
        set[str],
    ] = {node: set() for node in physical_entities}
    cell_trace_nodes: dict[str, tuple[tuple[int, tuple[int, ...]], ...]] = {}
    for cell in all_cells:
        nodes = tuple(
            _physical_node(row["dimension"], row["geometry_key"])
            for row in cell["trace"]
        )
        if len(nodes) != 18 or len(set(nodes)) != 18:
            raise P7SaturationBridgeError(
                "one hexahedral cell lacks 12 unique edges and 6 unique faces"
            )
        cell_trace_nodes[str(cell["target_id"])] = nodes
        for node in nodes:
            if node not in adjacency:
                raise P7SaturationBridgeError(
                    "cell trace entity is absent from physical authority"
                )
            adjacency[node].add(str(cell["target_id"]))
    trace_catalog_complete = set(adjacency) == {
        node for nodes in cell_trace_nodes.values() for node in nodes
    }

    p6_cells = tuple(
        cell for cell in all_cells if int(cell["cell_degree"]) == 6
    )
    expected_p6_target_ids = tuple(
        sorted(
            canonical_hp_cell_target_id(cell.key)
            for cell in context.forest.leaves
            if int(
                context.cell_interior_degree_by_box[cell.box]
            )
            == 6
        )
    )
    p6_target_ids = tuple(cell["target_id"] for cell in p6_cells)
    p6_inventory_complete = p6_target_ids == expected_p6_target_ids
    requested_trace_nodes = {
        node
        for cell in p6_cells
        for node in cell_trace_nodes[str(cell["target_id"])]
    }

    periodic_edges = tuple(
        (
            _relation_node(relation, slave=False),
            _relation_node(relation, slave=True),
        )
        for relation in physical.periodic_relations
    )
    periodic_components = _components(
        set(physical_entities),
        periodic_edges,
    )
    periodic_component_by_node = {
        node: component
        for component in periodic_components
        for node in component
    }
    hanging_groups: dict[
        int,
        set[tuple[int, tuple[int, ...]]],
    ] = {}
    for relation in physical.hanging_relations:
        patch_index = int(relation.provenance["patch_index"])
        hanging_groups.setdefault(patch_index, set()).update(
            _relation_nodes(relation)
        )

    selected_trace_nodes = set(requested_trace_nodes)
    closure_iterations = 0
    while True:
        previous = set(selected_trace_nodes)
        for node in tuple(selected_trace_nodes):
            selected_trace_nodes.update(
                periodic_component_by_node[node]
            )
        for group in hanging_groups.values():
            if group.intersection(selected_trace_nodes):
                selected_trace_nodes.update(group)
        for cell in all_cells:
            trace_by_node = {
                _physical_node(row["dimension"], row["geometry_key"]): row
                for row in cell["trace"]
            }
            selected_rows = [
                row
                for node, row in trace_by_node.items()
                if node in selected_trace_nodes
            ]
            if not selected_rows:
                continue
            requested_edges = tuple(
                int(row["local_entity"])
                for row in selected_rows
                if int(row["dimension"]) == 1
            )
            requested_faces = tuple(
                int(row["local_entity"])
                for row in selected_rows
                if int(row["dimension"]) == 2
            )
            _edges, closed_faces = close_mixed_p7_local_selection(
                requested_edges,
                requested_faces,
            )
            for row in cell["trace"]:
                if (
                    int(row["dimension"]) == 2
                    and int(row["local_entity"]) in closed_faces
                ):
                    selected_trace_nodes.add(
                        _physical_node(
                            row["dimension"],
                            row["geometry_key"],
                        )
                    )
        closure_iterations += 1
        if selected_trace_nodes == previous:
            break
        if closure_iterations > len(physical_entities) + 1:
            raise P7SaturationBridgeError(
                "mixed p7 trace closure did not reach a fixed point"
            )

    selected_components = tuple(
        component
        for component in periodic_components
        if set(component).intersection(selected_trace_nodes)
    )
    periodic_closure_added = selected_trace_nodes - requested_trace_nodes
    periodic_orbits = [
        {
            "root": _physical_node_row(component[0]),
            "dimension": component[0][0],
            "members": [
                _physical_node_row(node) for node in component
            ],
            "member_degrees": [
                int(physical_entities[node].degree) for node in component
            ],
            "requested_member_count": len(
                set(component).intersection(requested_trace_nodes)
            ),
            "closure_added_member_count": len(
                set(component).intersection(periodic_closure_added)
            ),
        }
        for component in selected_components
    ]
    periodic_closure_pass = all(
        set(component).issubset(selected_trace_nodes)
        for component in selected_components
    )
    hanging_nodes = {
        node
        for relation in physical.hanging_relations
        for node in _relation_nodes(relation)
    }
    selected_hanging_nodes = sorted(
        selected_trace_nodes.intersection(hanging_nodes)
    )

    mixed_component_groups: dict[
        tuple[
            HexaEntityDegreeMap,
            tuple[int, ...],
            tuple[int, ...],
        ],
        dict[str, Any],
    ] = {}
    selected_shadow_cells: list[Mapping[str, Any]] = []
    for cell in all_cells:
        selected_rows = [
            row
            for row in cell["trace"]
            if _physical_node(
                row["dimension"],
                row["geometry_key"],
            )
            in selected_trace_nodes
        ]
        if not selected_rows:
            continue
        requested_edges = tuple(
            sorted(
                int(row["local_entity"])
                for row in selected_rows
                if int(row["dimension"]) == 1
            )
        )
        requested_faces = tuple(
            sorted(
                int(row["local_entity"])
                for row in selected_rows
                if int(row["dimension"]) == 2
            )
        )
        degree_map = _cell_degree_map(cell)
        key = (degree_map, requested_edges, requested_faces)
        group = mixed_component_groups.setdefault(
            key,
            {
                "cell_infos": set(),
                "target_ids": [],
            },
        )
        group["cell_infos"].add(int(cell["cell_info"]))
        group["target_ids"].append(str(cell["target_id"]))
        selected_shadow_cells.append(cell)

    selected_hanging_patch_indices = tuple(
        sorted(
            patch_index
            for patch_index, group in hanging_groups.items()
            if group.intersection(selected_trace_nodes)
        )
    )
    floquet_requests_by_key: dict[
        tuple[int, int, float, float],
        dict[str, Any],
    ] = {}
    for relation in physical.periodic_relations:
        master = _relation_node(relation, slave=False)
        slave = _relation_node(relation, slave=True)
        if not {master, slave}.intersection(selected_trace_nodes):
            continue
        matrix = np.asarray(
            relation.slave_from_master,
            dtype=np.complex128,
        )
        phase = complex(matrix[0, 0])
        phase_identity_error = float(
            np.max(
                np.abs(
                    matrix
                    - phase
                    * np.eye(matrix.shape[0], dtype=np.complex128)
                ),
                initial=0.0,
            )
        )
        degree = int(physical_entities[master].degree)
        key = (degree, master[0], phase.real, phase.imag)
        floquet_requests_by_key.setdefault(
            key,
            {
                "source_degree": degree,
                "dimension": master[0],
                "phase": [phase.real, phase.imag],
                "physical_phase_identity_error_max": phase_identity_error,
            },
        )

    mixed_requests = [
        {
            "degree_map": _degree_map_payload(degree_map),
            "requested_edges": list(requested_edges),
            "requested_faces": list(requested_faces),
            "cell_infos": sorted(group["cell_infos"]),
            "cell_count": len(group["target_ids"]),
            "target_ids_sha256": _json_sha256(
                sorted(group["target_ids"])
            ),
            "target_ids_preview": sorted(group["target_ids"])[:8],
        }
        for (
            degree_map,
            requested_edges,
            requested_faces,
        ), group in sorted(
            mixed_component_groups.items(),
            key=lambda row: (
                row[0][0].signature,
                row[0][1],
                row[0][2],
            ),
        )
    ]
    hanging_requests = [
        {
            "patch_index": patch_index,
            "source_degrees": sorted(
                {
                    int(physical_entities[node].degree)
                    for node in hanging_groups[patch_index]
                }
            ),
        }
        for patch_index in selected_hanging_patch_indices
    ]
    mathematical_requests_core = {
        "schema_version": "task035e.p7-mathematical-audit-requests.v1",
        "mixed": mixed_requests,
        "hanging": hanging_requests,
        "floquet": [
            floquet_requests_by_key[key]
            for key in sorted(floquet_requests_by_key)
        ],
    }
    request_catalog_sha256 = _json_sha256(mathematical_requests_core)
    mathematical_requests = {
        **mathematical_requests_core,
        "request_catalog_sha256": request_catalog_sha256,
    }
    request_digest_by_rank = comm.allgather(request_catalog_sha256)
    request_all_rank_digest_pass = (
        len(set(request_digest_by_rank)) == 1
    )
    if not request_all_rank_digest_pass:
        raise P7SaturationBridgeError(
            "MPI ranks derived different p7 mathematical audit requests"
        )
    mathematical_packet = (
        _execute_mathematical_audit_requests(mathematical_requests)
        if int(comm.rank) == 0
        else None
    )
    mathematical_packet = comm.bcast(mathematical_packet, root=0)
    if not isinstance(mathematical_packet, Mapping):
        raise P7SaturationBridgeError(
            "rank 0 did not broadcast a p7 mathematical audit packet"
        )
    mathematical_packet_sha256 = _json_sha256(
        {
            key: value
            for key, value in mathematical_packet.items()
            if key != "mathematical_audit_sha256"
        }
    )
    packet_local_checks = {
        "packet_self_hash": (
            mathematical_packet.get("mathematical_audit_sha256")
            == mathematical_packet_sha256
        ),
        "request_catalog_identity": (
            mathematical_packet.get("request_catalog_sha256")
            == request_catalog_sha256
        ),
        "mixed_request_count": (
            len(mathematical_packet.get("mixed_component_audits", ()))
            + len(mathematical_packet.get("mixed_component_errors", ()))
            == len(mixed_requests)
        ),
        "hanging_request_count": (
            len(mathematical_packet.get("hanging_component_audits", ()))
            + len(mathematical_packet.get("hanging_component_errors", ()))
            == len(hanging_requests)
        ),
        "floquet_request_count": (
            len(mathematical_packet.get("floquet_component_audits", ()))
            + len(mathematical_packet.get("floquet_component_errors", ()))
            == len(floquet_requests_by_key)
        ),
        "execution_rank_is_zero": (
            mathematical_packet.get("execution_rank") == 0
        ),
    }
    packet_validation_by_rank = comm.allgather(
        all(packet_local_checks.values())
    )
    packet_digest_by_rank = comm.allgather(
        str(mathematical_packet["mathematical_audit_sha256"])
    )
    packet_all_rank_validation_pass = all(
        packet_validation_by_rank
    ) and len(set(packet_digest_by_rank)) == 1
    if not packet_all_rank_validation_pass:
        raise P7SaturationBridgeError(
            "one MPI rank rejected the p7 mathematical audit broadcast"
        )
    mixed_component_errors = list(
        mathematical_packet["mixed_component_errors"]
    )
    mixed_component_audits = list(
        mathematical_packet["mixed_component_audits"]
    )
    hanging_component_errors = list(
        mathematical_packet["hanging_component_errors"]
    )
    hanging_component_audits = list(
        mathematical_packet["hanging_component_audits"]
    )
    floquet_component_errors = list(
        mathematical_packet["floquet_component_errors"]
    )
    floquet_component_audits = list(
        mathematical_packet["floquet_component_audits"]
    )
    p7_catalog_audit = dict(mathematical_packet["p7_catalog_audit"])
    p7_catalog_sha256 = str(
        mathematical_packet["p7_catalog_sha256"]
    )
    p7_component_pass = bool(
        mathematical_packet["p7_component_pass"]
    )

    all_degrees = np.concatenate(
        [
            np.asarray(entity_map.global_degrees[dimension])
            for dimension in (1, 2, 3)
        ]
    )
    inactive_numbering_checks = {
        "production_degree_set_is_p4_p5_p6": set(map(int, all_degrees))
        <= {4, 5, 6},
        "production_maximum_degree_is_at_most_p6": (
            int(np.max(all_degrees, initial=0)) <= 6
        ),
        "active_row_formula_matches_numbering": (
            _expected_numbered_rows(entity_map.global_degrees)
            == int(entity_map.active_rows)
        ),
        "entity_map_reports_no_inactive_modes": (
            entity_map.audit["inactive_modes_globally_numbered"] is False
        ),
        "degree_plan_reports_no_inactive_high_order_trace": (
            reduction.degree_plan.audit[
                "inactive_high_order_trace_rows_globally_numbered"
            ]
            is False
        ),
        "p7_production_rows_added": True,
    }
    inactive_p7_numbering_pass = all(
        inactive_numbering_checks.values()
    )

    blockers: list[dict[str, Any]] = []
    if not all(ownership_checks.values()) or not mpi_digest_pass:
        failures = [
            name
            for name, passed in ownership_checks.items()
            if not passed
        ]
        blockers.append(
            _blocker(
                "mpi_ownership_catalog_incomplete",
                count=len(failures) + (not mpi_digest_pass),
                examples=failures,
                explanation=(
                    "distributed leaf/entity ownership is not uniquely "
                    "reconstructible on all ranks"
                ),
                remediation=(
                    "repair the carrier ownership packet before any p7 "
                    "shadow assembly"
                ),
            )
        )
    if comm.size != binding.formal_mpi_size:
        blockers.append(
            _blocker(
                "formal_mpi8_partition_not_executed",
                count=1,
                examples=[{"observed_mpi_size": int(comm.size)}],
                explanation=(
                    "serial or non-MPI8 structure is diagnostic only"
                ),
                remediation=(
                    "run the same hash-bound bridge once with MPI8"
                ),
            )
        )
    if mixed_component_errors:
        blockers.append(
            _blocker(
                "mixed_p_to_p7_exact_sequence_closure_failed",
                count=len(mixed_component_errors),
                examples=mixed_component_errors,
                explanation=(
                    "one actual variable-p cell could not be embedded into "
                    "the selected p7 exact-sequence shadow"
                ),
                remediation=(
                    "repair the reported Basix injection, orientation, or "
                    "discrete-gradient range identity"
                ),
            )
        )
    if hanging_component_errors:
        blockers.append(
            _blocker(
                "p7_hanging_trace_transform_failed",
                count=len(hanging_component_errors),
                examples=hanging_component_errors,
                explanation=(
                    "one selected hanging patch failed the real p-to-p7 "
                    "coarse/fine restriction identity"
                ),
                remediation=(
                    "repair the reported Piola restriction, D4 orientation, "
                    "or complement decomposition"
                ),
            )
        )
    if floquet_component_errors:
        blockers.append(
            _blocker(
                "mixed_p7_floquet_constraint_failed",
                count=len(floquet_component_errors),
                examples=floquet_component_errors,
                explanation=(
                    "one selected physical Floquet relation failed its "
                    "mixed entity injection or complement closure"
                ),
                remediation=(
                    "repair the physical phase/orientation binding before "
                    "constructing a p7 shadow"
                ),
            )
        )
    if not p7_component_pass:
        blockers.append(
            _blocker(
                "p7_trace_shadow_catalog_failed",
                count=1,
                examples=[
                    {
                        "catalog_sha256": p7_catalog_sha256,
                        "error": mathematical_packet.get(
                            "p7_catalog_error"
                        ),
                    }
                ],
                explanation=(
                    "the canonical p6-to-p7 trace complement catalog did "
                    "not pass on the mathematical execution rank"
                ),
                remediation=(
                    "repair the p7 Basix trace catalog before global "
                    "shadow assembly"
                ),
            )
        )

    enumeration_checks = {
        "all_cells_enumerated": observed_cell_ids == expected_cell_ids,
        "all_p6_cells_enumerated": p6_inventory_complete,
        "each_cell_has_12_edges_and_6_faces": all(
            len(cell_trace_nodes[row["target_id"]]) == 18
            for row in all_cells
        ),
        "physical_trace_catalog_complete": trace_catalog_complete,
        "periodic_orbits_closed": periodic_closure_pass,
    }
    enumeration_pass = all(enumeration_checks.values())
    mathematical_structural_coverage_pass = (
        not mixed_component_errors
        and not hanging_component_errors
        and not floquet_component_errors
        and len(mixed_component_audits) == len(mixed_component_groups)
        and len(hanging_component_audits)
        == len(selected_hanging_patch_indices)
    )
    exact_sequence_region_closure_pass = (
        mathematical_structural_coverage_pass
    )
    structural_coverage_pass = (
        binding_audit["pass"]
        and enumeration_pass
        and p7_component_pass
        and inactive_p7_numbering_pass
        and mpi8_status == "pass"
        and exact_sequence_region_closure_pass
        and not blockers
    )

    trace_before_periodic = sum(
        _trace_complement_dimension(
            family="hcurl",
            dimension=node[0],
            source_degree=int(physical_entities[node].degree),
        )
        for node in selected_trace_nodes
    )
    trace_after_periodic = sum(
        _trace_complement_dimension(
            family="hcurl",
            dimension=component[0][0],
            source_degree=int(
                physical_entities[component[0]].degree
            ),
        )
        for component in selected_components
    )
    h1_trace_before_periodic = sum(
        _trace_complement_dimension(
            family="h1",
            dimension=node[0],
            source_degree=int(physical_entities[node].degree),
        )
        for node in selected_trace_nodes
    )
    h1_trace_after_periodic = sum(
        _trace_complement_dimension(
            family="h1",
            dimension=component[0][0],
            source_degree=int(
                physical_entities[component[0]].degree
            ),
        )
        for component in selected_components
    )
    cell_orbits = [
        {
            "target_id": row["target_id"],
            "dyadic_key": row["dyadic_key"],
            "owner_rank": row["owner_rank"],
            "source_degree": int(row["cell_degree"]),
            "hcurl_p7_cell_complement_rows": (
                _cell_complement_dimension(
                    family="hcurl",
                    source_degree=int(row["cell_degree"]),
                )
            ),
            "h1_p7_cell_complement_rows": (
                _cell_complement_dimension(
                    family="h1",
                    source_degree=int(row["cell_degree"]),
                )
            ),
        }
        for row in selected_shadow_cells
    ]
    hcurl_cell_rows = sum(
        int(row["hcurl_p7_cell_complement_rows"])
        for row in cell_orbits
    )
    h1_cell_rows = sum(
        int(row["h1_p7_cell_complement_rows"])
        for row in cell_orbits
    )
    core = {
        "schema_version": P7_SATURATION_BRIDGE_SCHEMA,
        "status": (
            "p7_saturation_structural_coverage_pass"
            if structural_coverage_pass
            else "p7_saturation_structural_coverage_blocked"
        ),
        "evidence_closed": True,
        "structural_coverage_pass": structural_coverage_pass,
        "mathematical_structural_coverage_pass": (
            mathematical_structural_coverage_pass
        ),
        "numerical_saturation_status": "unknown",
        "measured_pass": False,
        "accuracy_credit": False,
        "selectable_as_production": False,
        "next_production_plan": None,
        "candidate_binding": candidate_binding_payload(binding),
        "binding_audit": binding_audit,
        "mathematical_audit_distribution": {
            "execution_rank": 0,
            "canonical_broadcast": True,
            "request_catalog_sha256": request_catalog_sha256,
            "request_digest_by_rank": list(request_digest_by_rank),
            "request_all_rank_digest_pass": (
                request_all_rank_digest_pass
            ),
            "mathematical_audit_sha256": mathematical_packet[
                "mathematical_audit_sha256"
            ],
            "mathematical_audit_digest_by_rank": list(
                packet_digest_by_rank
            ),
            "mathematical_audit_validation_by_rank": list(
                packet_validation_by_rank
            ),
            "mathematical_audit_all_rank_validation_pass": (
                packet_all_rank_validation_pass
            ),
            "each_rank_rederived_request_catalog": True,
            "each_rank_verified_broadcast_digest": True,
        },
        "mpi": {
            "observed_size": int(comm.size),
            "formal_size": binding.formal_mpi_size,
            "formal_partition_identity_status": mpi8_status,
            "all_rank_digest_pass": mpi_digest_pass,
            "all_rank_digest_sha256": global_digest,
            "digest_by_rank": list(digest_packets),
            "rank_packet_sha256": rank_packet_digests,
            "ownership_checks": ownership_checks,
            "owned_cell_counts_by_rank": [
                len(packet["cells"]) for packet in packets
            ],
            "owned_trace_entity_counts_by_rank": [
                len(packet["owner_blocks"]) for packet in packets
            ],
            "work_owned_trace_entity_counts_by_rank": [
                len(packet["work_blocks"]) for packet in packets
            ],
        },
        "production_numbering": {
            "active_rows": int(entity_map.active_rows),
            "active_trace_rows": int(entity_map.active_trace_rows),
            "production_degrees": sorted(set(map(int, all_degrees))),
            "p7_rows_added": 0,
            "inactive_p7_numbering_pass": inactive_p7_numbering_pass,
            "checks": inactive_numbering_checks,
        },
        "p7_component_binding": {
            "catalog_schema_version": p7_catalog_audit[
                "schema_version"
            ],
            "catalog_sha256": p7_catalog_sha256,
            "component_pass": (
                p7_component_pass
                and mathematical_structural_coverage_pass
            ),
            "p6_injection_is_not_prefix": True,
            "mixed_p4_p5_p6_injection_component_available": True,
            "floquet_component_available": True,
            "hanging_component_available": True,
            "mixed_cell_pattern_count": len(mixed_component_groups),
            "mixed_cell_component_audits": mixed_component_audits,
            "selected_hanging_patch_count": len(
                selected_hanging_patch_indices
            ),
            "hanging_component_audits": hanging_component_audits,
            "floquet_component_audits": floquet_component_audits,
        },
        "enumeration": {
            "pass": enumeration_pass,
            "checks": enumeration_checks,
            "forest_leaf_count": len(context.forest.leaves),
            "p6_leaf_count": len(p6_cells),
            "p6_target_ids": list(p6_target_ids),
            "p6_target_ids_sha256": _json_sha256(
                {"p6_target_ids": list(p6_target_ids)}
            ),
            "requested_trace_entity_count": len(
                requested_trace_nodes
            ),
            "selected_trace_entity_count_after_constraint_closure": len(
                selected_trace_nodes
            ),
            "total_constraint_closure_added_entity_count": len(
                periodic_closure_added
            ),
            "constraint_closure_fixed_point_iterations": (
                closure_iterations
            ),
            "selected_hanging_entity_count": len(
                selected_hanging_nodes
            ),
            "selected_shadow_cell_count": len(selected_shadow_cells),
            "cell_orbits": cell_orbits,
            "periodic_trace_orbits": periodic_orbits,
        },
        "potential_shadow_rows": {
            "semantics": (
                "structural complement dimensions only; no production "
                "row, tensor, residual, or adjoint was constructed"
            ),
            "hcurl_trace_before_periodic_elimination": (
                trace_before_periodic
            ),
            "hcurl_trace_after_periodic_elimination": (
                trace_after_periodic
            ),
            "hcurl_cell_interior": hcurl_cell_rows,
            "hcurl_total_after_periodic_elimination": (
                trace_after_periodic + hcurl_cell_rows
            ),
            "h1_trace_before_periodic_elimination": (
                h1_trace_before_periodic
            ),
            "h1_trace_after_periodic_elimination": (
                h1_trace_after_periodic
            ),
            "h1_cell_interior": h1_cell_rows,
            "h1_total_after_periodic_elimination": (
                h1_trace_after_periodic + h1_cell_rows
            ),
        },
        "exact_sequence_region_closure_pass": (
            exact_sequence_region_closure_pass
        ),
        "blockers": blockers,
        "blocker_codes": [row["code"] for row in blockers],
        "formal_coverage_semantics": {
            "structural_and_numerical_are_separate": True,
            "structural_success_cannot_set_measured_pass": True,
            "p7_tensor_evaluation_status": "not_run",
            "p7_residual_evaluation_status": "not_run",
            "p7_adjoint_evaluation_status": "not_run",
            "p7_59_goal_dwr_status": "not_run",
            "p6_saturation_credit": "withheld",
        },
        "ordinary_default_changed": False,
    }
    return MappingProxyType(
        core | {"evidence_sha256": _json_sha256(core)}
    )


def build_p7_saturation_structural_evidence_from_plan(
    *,
    binding: P7SaturationCandidateBinding,
    phase_x: complex,
    phase_y: complex,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> Mapping[str, Any]:
    """Replay a bound plan and build its structural p7 evidence."""

    payload = _load_json(binding.plan_path)
    base = payload.get("base_config")
    if not isinstance(base, Mapping):
        raise P7SaturationBridgeError("bound plan has no base_config")
    h_nm = base.get("mesh_target_size")
    if (
        isinstance(h_nm, bool)
        or not isinstance(h_nm, (int, float))
        or not np.isfinite(float(h_nm))
        or float(h_nm) <= 0.0
    ):
        raise P7SaturationBridgeError(
            "bound plan mesh_target_size is invalid"
        )
    cfg = target_stage4_config(degree=6, h_nm=float(h_nm))
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        binding.plan_path,
        comm=comm,
    )
    context = mesh_data.local_h_context
    if not isinstance(context, Stage4LocalHContext):
        raise P7SaturationBridgeError(
            "bound plan did not construct a Stage4LocalHContext"
        )
    reduction = build_stage4_local_h_reduction_authority(
        context,
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
    )
    return build_p7_saturation_structural_evidence(
        context=context,
        reduction=reduction,
        binding=binding,
    )


def _reject_constant(value: str) -> None:
    raise P7SaturationBridgeError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise P7SaturationBridgeError(
                f"duplicate JSON key is forbidden: {key}"
            )
        output[key] = value
    return output


def _load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P7SaturationBridgeError(
            f"cannot load JSON input {path}: {exc}"
        ) from exc


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> str:
    output = path.expanduser().resolve()
    if os.path.lexists(output):
        raise FileExistsError(
            f"refusing to overwrite p7 bridge evidence: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            _canonical(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
        temporary.unlink()
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(encoded).hexdigest()


def write_p7_saturation_structural_evidence(
    path: Path,
    evidence: Mapping[str, Any],
) -> str:
    """Write one immutable, self-hashed outer evidence object."""

    payload = dict(evidence)
    if payload.get("evidence_sha256") != _json_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "evidence_sha256"
        }
    ):
        raise P7SaturationBridgeError(
            "p7 bridge evidence self-hash differs"
        )
    outer = {
        "schema_version": P7_SATURATION_BRIDGE_OUTER_SCHEMA,
        "sha256": payload["evidence_sha256"],
        "payload": payload,
    }
    return _atomic_write(path, outer)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind p7 shadow structure to an executed Task035e plan"
        )
    )
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase-x-real", type=float, default=1.0)
    parser.add_argument("--phase-x-imag", type=float, default=0.0)
    parser.add_argument("--phase-y-real", type=float, default=1.0)
    parser.add_argument("--phase-y-imag", type=float, default=0.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    comm = MPI.COMM_WORLD
    binding = candidate_binding_from_payload(
        _load_json(args.binding.expanduser().resolve())
    )
    evidence = build_p7_saturation_structural_evidence_from_plan(
        binding=binding,
        phase_x=complex(args.phase_x_real, args.phase_x_imag),
        phase_y=complex(args.phase_y_real, args.phase_y_imag),
        comm=comm,
    )
    if comm.rank == 0:
        file_sha = write_p7_saturation_structural_evidence(
            args.output,
            evidence,
        )
        print(
            json.dumps(
                {
                    "status": evidence["status"],
                    "structural_coverage_pass": evidence[
                        "structural_coverage_pass"
                    ],
                    "numerical_saturation_status": evidence[
                        "numerical_saturation_status"
                    ],
                    "evidence_sha256": evidence["evidence_sha256"],
                    "file_sha256": file_sha,
                },
                sort_keys=True,
            )
        )
    comm.Barrier()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "P7_SATURATION_BINDING_SCHEMA",
    "P7_SATURATION_BRIDGE_OUTER_SCHEMA",
    "P7_SATURATION_BRIDGE_SCHEMA",
    "P7SaturationBridgeError",
    "P7SaturationCandidateBinding",
    "build_p7_saturation_structural_evidence",
    "build_p7_saturation_structural_evidence_from_plan",
    "candidate_binding_from_adapted",
    "candidate_binding_from_authority",
    "candidate_binding_from_payload",
    "candidate_binding_payload",
    "write_p7_saturation_structural_evidence",
]
