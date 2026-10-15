"""One-materialized-matrix p6 condensed direct full solves.

The route reuses the reviewed p6 local-condensation and carrier machinery.  It
materializes only the augmented p6 trace/port AIJ, then keeps that exact PETSc
matrix alive through MUMPS symbolic analysis, numeric factorization, and solve.
No p4 operator, p4 factor, H6 hierarchy, or outer Krylov method is created.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

PROFILE_ID = "dual_condensed_balh_native_0p7nm_aniso_n0_p6_direct_full_v1"
RSS_HARD_LIMIT_BYTES = 1_800_000_000_000
ACTIVE_ROWS = 9_280_800
APPENDED_PORTS = 572
DIRECT_ROWS = ACTIVE_ROWS + APPENDED_PORTS
FULL_P6_ROWS = 32_061_312
ACTIVE_MODE_SHA256 = "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
PARENT_MODE_SHA256 = "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return {
            "array_omitted": True,
            "dtype": str(value.dtype),
            "shape": [int(item) for item in value.shape],
            "finite": bool(np.isfinite(value).all())
            if np.issubdtype(value.dtype, np.number)
            else False,
        }
    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return [float(number.real), float(number.imag)]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else {"nonfinite": repr(number)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"cannot serialize {type(value).__name__} in direct summary")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_direct_flat_reference_outputs(
    output_dir: Path,
    cfg: Any,
    comm: Any,
    output_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Write flat-layer references from the direct route's recovered outputs."""

    from src.postprocessing.flat_layer_reference_3d import (
        write_flat_layer_reference_outputs,
    )

    return write_flat_layer_reference_outputs(
        output_dir,
        cfg,
        comm,
        port_metrics=output_facts["port_metrics"],
        probe_metrics=output_facts["diffraction_metrics"],
        volume_metrics=output_facts["volume_metrics"],
    )


def _validate_resolved_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    from src.io.native_capacity_profile import (
        P6_CONDENSED_DIRECT_PROFILES,
        native_capacity_profile_identity,
        native_profile_facts,
    )
    from src.io.resolved_config import canonical_json_bytes

    method = payload.get("method")
    solver = payload.get("solver")
    derived = payload.get("derived")
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_direct":
        raise ValueError("p6 direct runner requires method.kind=full3d_direct")
    if not isinstance(solver, Mapping) or not isinstance(derived, Mapping):
        raise TypeError("resolved p6 direct solver/derived identity is missing")
    identity = native_capacity_profile_identity(method.get("kind"), solver)
    if identity not in P6_CONDENSED_DIRECT_PROFILES:
        raise ValueError("p6 direct runner requires an explicit condensed-direct profile")
    resolved_facts = derived.get("native_capacity_profile")
    expected_facts = native_profile_facts(identity)
    if not isinstance(resolved_facts, Mapping):
        raise TypeError("resolved derived.native_capacity_profile is missing")
    if canonical_json_bytes(dict(resolved_facts)) != canonical_json_bytes(expected_facts):
        raise ValueError("resolved direct profile facts differ from the frozen profile")
    if resolved_facts.get("identity") != identity:
        raise ValueError("resolved native profile identity differs from solver selection")
    expected_rss_cap = expected_facts.get("resources", {}).get(
        "rss_hard_limit_bytes", RSS_HARD_LIMIT_BYTES
    )
    if resolved_facts.get("resources", {}).get("rss_hard_limit_bytes") != expected_rss_cap:
        raise ValueError("resolved direct profile RSS hard limit differs from its profile")
    options = resolved_facts.get("component_options")
    if not isinstance(options, Mapping):
        raise TypeError("resolved p6 direct component options are missing")
    if options.get("functional_store_policy") != "disabled_no_functional_store_config":
        raise ValueError("p6 condensed-direct route forbids functional-store reuse")
    if options.get("cross_mesh_fe_reuse") is not False:
        raise ValueError("p6 condensed-direct routes forbid cross-mesh FE reuse")
    return dict(resolved_facts)


def _direct_run_contract(profile_identity: str) -> dict[str, Any]:
    """Return route-specific immutable identities without conflating V7 N0."""

    from src.io.native_capacity_profile import (
        DISPERSION_FLAT_P6_PROFILES,
        V6_F5_P6_DIRECT_FULL600_PROFILE,
        V6_F5_P6_DIRECT_N0_PROFILE,
        V7_ANISO_N0_P6_DIRECT_PROFILE,
    )

    if profile_identity == V7_ANISO_N0_P6_DIRECT_PROFILE:
        return {
            "family": "v7_aniso_n0",
            "truncated": True,
            "operator_scope": "n0_filtered_dtn_not_full_dtn",
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "parent_count": 32_060,
            "parent_sha256": PARENT_MODE_SHA256,
            "active_count": APPENDED_PORTS,
            "active_sha256": ACTIVE_MODE_SHA256,
            "residual_key": "original_A6_n0_relative",
            "residual_scope": "A6_n0",
            "summary_prefix": "p6_condensed_direct_n0",
        }
    if profile_identity in DISPERSION_FLAT_P6_PROFILES:
        return {
            "family": "dispersion_flat",
            "truncated": False,
            "operator_scope": "all_auto_propagating_orders_flat_1nm_period",
            "full_dtn_status": (
                "AUTO_PROPAGATING_PORT_OPERATOR_BUILT; evanescent orders excluded"
            ),
            "parent_count": None,
            "parent_sha256": None,
            "active_count": None,
            "active_sha256": None,
            "residual_key": "original_A6_full_relative",
            "residual_scope": "A6_all_auto_propagating_flat_inventory",
            "summary_prefix": "dispersion_flat_p6_condensed_direct",
            "surface_quadrature_degree": 160,
        }
    if profile_identity == V6_F5_P6_DIRECT_FULL600_PROFILE:
        return {
            "family": "v6_f5",
            "truncated": False,
            "operator_scope": "full_600_mode_dtn",
            "full_dtn_status": "FULL_600_MODE_OPERATOR_BUILT",
            "parent_count": 600,
            "parent_sha256": "dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645",
            "active_count": 600,
            "active_sha256": "dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645",
            "residual_key": "original_A6_full_relative",
            "residual_scope": "A6_full_600",
            "summary_prefix": "v6_f5_p6_condensed_direct_full600",
        }
    if profile_identity == V6_F5_P6_DIRECT_N0_PROFILE:
        return {
            "family": "v6_f5",
            "truncated": True,
            "operator_scope": "n0_filtered_dtn_not_full_dtn",
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "parent_count": 600,
            "parent_sha256": "dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645",
            "active_count": 80,
            "active_sha256": "36337e70f52f959b4f8b7e1727ee8babccd3e84d2e25d70bd32e87c79040e012",
            "residual_key": "original_A6_n0_relative",
            "residual_scope": "A6_n0_from_600_parent",
            "summary_prefix": "v6_f5_p6_condensed_direct_n0",
        }
    raise ValueError(f"unsupported p6 condensed-direct profile: {profile_identity}")


def _validate_direct_condensed_dimensions(
    condensed: Any,
    *,
    full_p6_rows: int,
    appended_rows: int,
    matrix_size: tuple[int, int],
    expected_active_rows: int | None = None,
) -> None:
    """Check full, trace, active/slave and condensed dimensions consistently.

    ``full_rows`` includes MPC slave storage.  The cell-interior elimination
    partitions that full storage into trace and interior rows; only active
    trace rows enter the reduced matrix, while slave rows are represented by
    the trace-constraint expansion.
    """

    constraints = getattr(condensed, "trace_constraints", None)
    if constraints is None:
        raise ValueError("p6 direct condensation is missing its trace constraint map")
    full_rows = int(condensed.full_rows)
    trace_rows = int(condensed.trace_rows)
    active_rows = int(condensed.active_rows)
    interior_rows = int(condensed.interior_rows)
    appended_rows = int(appended_rows)
    slave_rows = int(constraints.slave_rows)
    expected_matrix_rows = active_rows + appended_rows

    if (
        full_rows != int(full_p6_rows)
        or trace_rows + interior_rows != full_rows
        or active_rows + slave_rows != trace_rows
        or int(constraints.full_trace_rows) != trace_rows
        or int(constraints.active_rows) != active_rows
        or int(constraints.full_trace_rows)
        != int(constraints.active_rows) + int(constraints.slave_rows)
        or len(constraints.expansion_by_original) != trace_rows
        or len(constraints.original_to_active) != active_rows
        or int(condensed.appended_rows) != appended_rows
        or tuple(map(int, matrix_size)) != (expected_matrix_rows, expected_matrix_rows)
        or (
            expected_active_rows is not None
            and active_rows != int(expected_active_rows)
        )
    ):
        raise ValueError("actual p6 direct condensed dimensions violate the live dof maps")


def _direct_output_policy(route: Mapping[str, Any]) -> dict[str, Any]:
    """Keep V7's active-only audit separate from F5 active-mode exports."""

    if route["family"] == "v7_aniso_n0":
        if int(route["active_count"]) != APPENDED_PORTS:
            raise ValueError("V7 active-only outputs require its frozen 572-mode route")
        return {
            "active_port_outputs_only": True,
            "dtn_output_mode_count": int(route["active_count"]),
            "omitted_dtn_channels": "NOT_COMPUTED",
            "diffraction_source": "n0_active_port_output_contract",
        }
    if route["family"] == "v6_f5":
        return {
            "active_port_outputs_only": False,
            "dtn_output_mode_count": int(route["active_count"]),
            "omitted_dtn_channels": (
                "NOT_COMPUTED" if route["truncated"] else "NONE"
            ),
            "diffraction_source": "field_sample_based_independent_of_dtn_mode_list",
        }
    if route["family"] == "dispersion_flat":
        return {
            "active_port_outputs_only": False,
            "dtn_output_mode_count": int(route["active_count"]),
            "omitted_dtn_channels": "EVANESCENT_ORDERS_EXCLUDED_BY_AUTO_PROPAGATING_POLICY",
            "diffraction_source": "recovered_flat_layer_field_sampling",
        }
    raise ValueError(f"unsupported output policy family: {route['family']}")


def _persist_flat_parent_inventory(directory, inventory):
    """Persist the actual unfiltered propagating inventory for one flat case."""

    from src.solvers.fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    modes, rows, expected_sha = inventory
    encoded = _canonical_json_bytes(
        {
            "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
            "profile": FULLSPACE_DTN_PROFILE,
            "mode_count": len(modes),
            "modes": rows,
        }
    )
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != expected_sha:
        raise ValueError("flat parent manifest serialization hash differs")
    path = Path(directory) / "auto_propagating_parent_mode_manifest.json"
    with path.open("xb") as stream:
        stream.write(encoded)
    return {"filename": path.name, "sha256": digest, "bytes": len(encoded)}


def _build_f5_n0_inventory(parent_inventory, cfg):
    """Select n==0 from the verified full 600 parent without prefix assumptions."""

    from src.solvers.fullspace_dtn_action import (
        _canonical_json_bytes,
        build_ordered_mode_manifest,
    )

    parent_modes, parent_rows, parent_sha = parent_inventory
    parent_modes = tuple(parent_modes)
    parent_rows = tuple(parent_rows)
    if (
        len(parent_modes) != 600
        or len(parent_rows) != 600
        or parent_sha != "dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645"
    ):
        raise ValueError("F5 n0 selection requires the exact historical full600 parent")
    for index, (mode, row) in enumerate(zip(parent_modes, parent_rows, strict=True)):
        if (
            not isinstance(row, Mapping)
            or int(row.get("mode_index", -1)) != index
            or int(row.get("n", 999999)) != int(mode.n)
            or int(row.get("m", 999999)) != int(mode.m)
            or str(row.get("side")) != str(mode.side)
            or str(row.get("polarization")) != str(mode.polarization)
        ):
            raise ValueError("F5 full600 manifest does not match live mode objects")

    indices = tuple(index for index, mode in enumerate(parent_modes) if int(mode.n) == 0)
    active_modes = tuple(parent_modes[index] for index in indices)
    active_rows, _encoded, active_sha = build_ordered_mode_manifest(active_modes, cfg)
    expected_sha = "36337e70f52f959b4f8b7e1727ee8babccd3e84d2e25d70bd32e87c79040e012"
    if len(indices) != 80 or active_sha != expected_sha:
        raise ValueError("F5 live n0 subset differs from the verified 80-mode identity")
    group_counts: dict[str, int] = {}
    for side in ("bottom", "top"):
        for polarization in ("s", "p"):
            key = f"{side}_{polarization}"
            group_counts[key] = sum(
                str(mode.side) == side and str(mode.polarization) == polarization
                for mode in active_modes
            )
    if group_counts != {
        "bottom_s": 20,
        "bottom_p": 20,
        "top_s": 20,
        "top_p": 20,
    }:
        raise ValueError("F5 n0 selection must contain 20 modes in each side/polarization")
    if any(
        {int(mode.m) for mode in active_modes
         if str(mode.side) == side and str(mode.polarization) == polarization}
        != set(range(-19, 1))
        for side in ("bottom", "top")
        for polarization in ("s", "p")
    ):
        raise ValueError("F5 n0 selection must retain all actual m=-19..0 orders")

    active_inventory = (active_modes, tuple(active_rows), active_sha)
    index_sha = hashlib.sha256(_canonical_json_bytes(list(indices))).hexdigest()
    selection = {
        "schema": "task39extra.dtn-mode-selection.v1",
        "policy": "n_equals_zero_both_ports_both_polarizations",
        "parent_mode_count": 600,
        "parent_mode_sha256": parent_sha,
        "active_mode_count": len(active_modes),
        "active_mode_sha256": active_sha,
        "expected_active_mode_sha256": expected_sha,
        "selected_parent_indices_sha256": index_sha,
        "side_polarization_counts": group_counts,
        "m_range_in_each_side_polarization": [-19, 0],
        "quadrature_inventory": "full_600_parent_modes",
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
    }
    return active_inventory, selection, indices


def _persist_f5_inventory(directory, parent_inventory, active_inventory, selection, indices):
    from src.solvers.fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    artifacts: dict[str, Any] = {}
    inventories = [("parent", parent_inventory)]
    if tuple(indices) != tuple(range(len(parent_inventory[1]))):
        inventories.append(("active", active_inventory))
    for label, inventory in inventories:
        modes, rows, expected_sha = inventory
        encoded = _canonical_json_bytes(
            {
                "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": len(modes),
                "modes": rows,
            }
        )
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != expected_sha:
            raise ValueError(f"F5 {label} manifest serialization hash differs")
        path = directory / f"{label}_mode_manifest.json"
        with path.open("xb") as stream:
            stream.write(encoded)
        artifacts[label] = {"filename": path.name, "sha256": digest, "bytes": len(encoded)}
    if selection is not None:
        old_to_new = [-1] * len(parent_inventory[1])
        for new_index, old_index in enumerate(indices):
            old_to_new[int(old_index)] = int(new_index)
        mapping = {
            "schema": "task39extra.v6-f5-mode-index-map.v1",
            "selection": dict(selection),
            "selected_parent_indices": list(indices),
            "old_to_new": old_to_new,
            "active_keys": [
                [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]
                for row in active_inventory[1]
            ],
            "omitted_values_policy": "not measured; never filled with zero",
        }
        encoded = _canonical_json_bytes(mapping)
        path = directory / "mode_index_map.json"
        with path.open("xb") as stream:
            stream.write(encoded)
        artifacts["index_map"] = {
            "filename": path.name,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
        }
    return artifacts


def _inventory_mode_counts_by_side(
    mode_rows: Any, *, expected_total: int
) -> dict[str, int]:
    """Bind carrier side counts to the exact selected mode inventory."""

    counts = {"bottom": 0, "top": 0}
    rows = tuple(mode_rows)
    if len(rows) != int(expected_total):
        raise ValueError("active mode rows differ from the selected direct inventory")
    for row in rows:
        if not isinstance(row, Mapping) or row.get("side") not in counts:
            raise ValueError("active mode inventory contains an unknown port side")
        counts[str(row["side"])] += 1
    if sum(counts.values()) != int(expected_total) or any(
        value <= 0 for value in counts.values()
    ):
        raise ValueError("active direct inventory has an incomplete top/bottom side partition")
    return counts


def _persist_n0_inventory(
    directory: Path,
    parent_inventory: tuple[Any, Any, str],
    active_inventory: tuple[Any, Any, str],
    selection: Mapping[str, Any],
    indices: tuple[int, ...],
) -> dict[str, Any]:
    from src.solvers.fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    artifacts: dict[str, Any] = {}
    for label, inventory in (("parent", parent_inventory), ("active", active_inventory)):
        _modes, rows, expected_sha = inventory
        encoded = _canonical_json_bytes(
            {
                "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": len(rows),
                "modes": rows,
            }
        )
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != expected_sha:
            raise ValueError(f"live N0 {label} mode inventory hash differs")
        path = directory / f"n0_{label}_mode_manifest.json"
        with path.open("xb") as stream:
            stream.write(encoded)
        artifacts[label] = {
            "filename": path.name,
            "sha256": digest,
            "bytes": len(encoded),
        }
    old_to_new = [-1] * len(parent_inventory[1])
    for new_index, old_index in enumerate(indices):
        old_to_new[int(old_index)] = int(new_index)

    def key(row):
        return [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]

    mapping = {
        "schema": "task39extra.n0-mode-index-map.v1",
        "selection": dict(selection),
        "selected_parent_indices": list(indices),
        "old_to_new": old_to_new,
        "retained_keys": [key(row) for row in active_inventory[1]],
        "omitted_keys": [
            key(row) for index, row in enumerate(parent_inventory[1])
            if old_to_new[index] == -1
        ],
        "omitted_values_policy": "not measured; never filled with zero",
    }
    encoded = _canonical_json_bytes(mapping)
    path = directory / "n0_mode_index_map.json"
    with path.open("xb") as stream:
        stream.write(encoded)
    artifacts["index_map"] = {
        "filename": path.name,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }
    return artifacts


def _port_support_groups(
    setup: Mapping[str, Any],
    carrier: Any,
    cfg: Any,
    *,
    expected_boundary_cells: int = 200,
    expected_modes_by_side: Mapping[str, int] | None = None,
):
    """Use the actual top/bottom boundary-cell layers as sparse port supports."""

    mesh = setup["mesh"]
    space = setup["spaces"][6]
    local_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    coordinates = np.asarray(mesh.geometry.x)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    groups: dict[str, list[int]] = {"bottom": [], "top": []}
    for cell in range(local_cells):
        points = coordinates[geometry_dofmap[cell]]
        lower_z = float(np.min(points[:, 2]))
        upper_z = float(np.max(points[:, 2]))
        if np.isclose(lower_z, float(cfg.domain_z_min), rtol=0.0, atol=1.0e-12):
            groups["bottom"].append(cell)
        if np.isclose(upper_z, float(cfg.domain_z_max), rtol=0.0, atol=1.0e-12):
            groups["top"].append(cell)
    if (
        len(groups["bottom"]) != int(expected_boundary_cells)
        or len(groups["top"]) != int(expected_boundary_cells)
    ):
        raise ValueError(
            "p6 direct port support differs from the selected mesh-plan boundary layers"
        )

    order = ("bottom", "top")
    side_group = {side: index for index, side in enumerate(order)}
    group_rows: list[int] = []
    entries_by_side: dict[str, list[Any]] = {side: [] for side in order}
    for entry in tuple(carrier.entries):
        identity = getattr(entry, "mode_identity", None)
        side = identity.get("side") if isinstance(identity, Mapping) else None
        if side not in side_group:
            raise ValueError("V7 carrier entry has no top/bottom mode identity")
        entries_by_side[side].append(entry)
        group_rows.append(side_group[side])
    if expected_modes_by_side is None:
        raise ValueError("p6 direct support requires counts derived from the active inventory")
    if any(
        len(entries_by_side[side]) != int(expected_modes_by_side.get(side, -1))
        for side in order
    ):
        raise ValueError("p6 direct carrier side counts differ from the mode inventory")

    support_rows: dict[str, np.ndarray] = {}
    for side in order:
        local_dofs = [
            np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
            for cell in groups[side]
        ]
        local = np.unique(np.concatenate(local_dofs))
        support_rows[side] = np.asarray(
            space.dofmap.index_map.local_to_global(local), dtype=np.int64
        )
        support_rows[side].sort()
        for entry in entries_by_side[side]:
            for field in ("coupling_rows", "projection_rows"):
                rows = np.asarray(getattr(entry, field), dtype=np.int64).reshape(-1)
                if rows.size and not np.all(np.isin(rows, support_rows[side], assume_unique=False)):
                    raise ValueError(
                        f"V7 {side} carrier {field} escapes its actual boundary-cell layer"
                    )
    return (
        tuple(np.asarray(groups[side], dtype=np.int64) for side in order),
        tuple(group_rows),
        {
            "support_cell_counts": {side: len(groups[side]) for side in order},
            "support_row_counts": {side: len(support_rows[side]) for side in order},
            "carrier_rows_within_actual_boundary_layers": True,
            "support_identity": "actual_mesh_geometry_top_bottom_cell_layers_v1",
        },
    )


def _f5_expected_material_tag_counts(
    x_values: tuple[float, ...],
    y_values: tuple[float, ...],
    z_values: tuple[float, ...],
    cfg: Any,
) -> dict[str, int]:
    """Compute structured F5 tag counts from frozen intervals, without a mesh."""

    def contained_cells(values: tuple[float, ...], lower: float, upper: float) -> int:
        return sum(
            left >= lower - 1.0e-12 and right <= upper + 1.0e-12
            for left, right in pairwise(values)
        )

    nx = contained_cells(x_values, cfg.x_min, cfg.x_max)
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    grating_x = contained_cells(x_values, cfg.grating_x_min, cfg.grating_x_max)
    grating_z = contained_cells(z_values, cfg.grating_z_min, cfg.grating_z_max)
    substrate_z = contained_cells(z_values, cfg.domain_z_min, cfg.interface_z)
    grating = grating_x * ny * grating_z
    substrate = nx * ny * substrate_z
    total = nx * ny * nz
    return {
        "total": total,
        "grating": grating,
        "substrate": substrate,
        "air": total - grating - substrate,
    }


def _f5_mesh_evidence(levels: Mapping[str, Any], cfg: Any) -> dict[str, Any]:
    """Check the actual 5 nm hexa mesh against the input's frozen axis plan."""

    mesh_data = levels["mesh_data"]
    msh = mesh_data.mesh
    axes = {
        "x": tuple(float(value) for value in cfg.mesh_axis_x_values_requested),
        "y": tuple(float(value) for value in cfg.mesh_axis_y_values_requested),
        "z": tuple(float(value) for value in cfg.mesh_axis_z_values_requested),
    }
    expected_counts = {axis: len(values) - 1 for axis, values in axes.items()}
    actual_axes = {
        axis: tuple(float(value) for value in np.unique(np.asarray(msh.geometry.x)[:, index]))
        for index, axis in enumerate(("x", "y", "z"))
    }
    axis_match = all(actual_axes[axis] == axes[axis] for axis in axes)
    actual_axis_counts = {
        axis: len(actual_axes[axis]) - 1 for axis in actual_axes
    }
    actual_cells = int(msh.topology.index_map(msh.topology.dim).size_global)
    actual_cell_type = str(msh.topology.cell_name())
    expected_tags = _f5_expected_material_tag_counts(
        axes["x"], axes["y"], axes["z"], cfg
    )
    values = np.asarray(mesh_data.cell_tags.values, dtype=np.int64)
    actual_tag_counts = {
        str(int(tag)): int(np.count_nonzero(values == int(tag)))
        for tag in (
            cfg.tags.air,
            cfg.tags.substrate,
            cfg.tags.grating,
        )
    }
    expected_tag_counts = {
        str(int(cfg.tags.air)): expected_tags["air"],
        str(int(cfg.tags.substrate)): expected_tags["substrate"],
        str(int(cfg.tags.grating)): expected_tags["grating"],
    }
    if actual_cells != expected_tags["total"]:
        raise ValueError("actual F5 global mesh cell count differs from its frozen axes")
    if not axis_match or tuple(
        actual_axis_counts[axis] for axis in ("x", "y", "z")
    ) != tuple(expected_counts[axis] for axis in ("x", "y", "z")):
        raise ValueError("actual F5 mesh coordinate axes differ from the frozen plan")
    if actual_tag_counts != expected_tag_counts or int(values.size) != actual_cells:
        raise ValueError("actual F5 material tags differ from frozen axis geometry")
    if actual_cell_type != "hexahedron":
        raise ValueError("actual F5 mesh is not hexahedral")
    return {
        "status": "PASS",
        "actual_global_cell_count": actual_cells,
        "axis_cell_counts": [actual_axis_counts[axis] for axis in ("x", "y", "z")],
        "actual_axes_match_frozen_input": True,
        "axis_sha256_le_f64": {
            axis: hashlib.sha256(
                np.asarray(actual_axes[axis], dtype="<f8").tobytes()
            ).hexdigest()
            for axis in actual_axes
        },
        "material_tag_counts": actual_tag_counts,
        "material_tag_counts_expected_from_axes": expected_tag_counts,
        "cell_type": actual_cell_type,
        "mpi_size": 1,
    }


def _dispersion_flat_mesh_evidence(
    levels: Mapping[str, Any], cfg: Any
) -> dict[str, Any]:
    """Check actual flat axes, cell count, tags, and cell type against the plan."""

    from src.geometry.dispersion_flat_axis_plan import (
        validate_frozen_dispersion_flat_axes,
    )

    mesh_data = levels["mesh_data"]
    msh = mesh_data.mesh
    plan = validate_frozen_dispersion_flat_axes(
        {
            "mesh_plan_id": cfg.mesh_plan_id,
            "mesh_plan_sha256": cfg.mesh_plan_sha256,
            "mesh_axis_cell_counts": cfg.mesh_axis_cell_counts_requested,
            "mesh_axis_x_values": cfg.mesh_axis_x_values_requested,
            "mesh_axis_y_values": cfg.mesh_axis_y_values_requested,
            "mesh_axis_z_values": cfg.mesh_axis_z_values_requested,
        }
    )
    actual_axes = {
        axis: tuple(
            float(value)
            for value in np.unique(np.asarray(msh.geometry.x)[:, index])
        )
        for index, axis in enumerate(("x", "y", "z"))
    }
    if any(actual_axes[axis] != plan[axis] for axis in ("x", "y", "z")):
        raise ValueError("actual flat mesh axes differ from the frozen input plan")
    counts = tuple(len(actual_axes[axis]) - 1 for axis in ("x", "y", "z"))
    nx, ny, nz = counts
    expected_cells = nx * ny * nz
    actual_cells = int(msh.topology.index_map(msh.topology.dim).size_global)
    if actual_cells != expected_cells:
        raise ValueError("actual flat mesh global cell count differs from its axes")
    if str(msh.topology.cell_name()) != "hexahedron":
        raise ValueError("dispersion flat direct route requires hexahedra")
    interface = float(cfg.interface_z)
    substrate_intervals = sum(right <= interface for _, right in pairwise(plan["z"]))
    if substrate_intervals <= 0 or substrate_intervals >= nz:
        raise ValueError("flat mesh must contain both air and substrate cells")
    expected = {
        int(cfg.tags.air): nx * ny * (nz - substrate_intervals),
        int(cfg.tags.substrate): nx * ny * substrate_intervals,
        int(cfg.tags.grating): 0,
    }
    tag_values = np.asarray(mesh_data.cell_tags.values, dtype=np.int64)
    if tag_values.size != actual_cells:
        raise ValueError("MPI1 flat cell-tag array does not cover every owned cell")
    observed = {tag: int(np.count_nonzero(tag_values == tag)) for tag in expected}
    if observed != expected:
        raise ValueError(
            f"actual flat material tags differ from layered axes: {observed} != {expected}"
        )
    msh.topology.create_entity_permutations()
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    if cell_info.ndim != 1 or cell_info.size != actual_cells:
        raise ValueError("flat actual cell-orientation metadata does not cover every cell")
    orientation_values, orientation_counts = np.unique(cell_info, return_counts=True)
    return {
        "status": "PASS",
        "geometry": "flat_layer",
        "cell_type": "hexahedron",
        "actual_global_cell_count": actual_cells,
        "axis_cell_counts": list(counts),
        "axes_match_frozen_plan": True,
        "mesh_plan_id": str(cfg.mesh_plan_id),
        "mesh_plan_sha256": str(cfg.mesh_plan_sha256),
        "axis_sha256_le_f64": {
            axis: hashlib.sha256(
                np.asarray(actual_axes[axis], dtype="<f8").tobytes()
            ).hexdigest()
            for axis in actual_axes
        },
        "actual_material_tag_counts": {str(key): value for key, value in observed.items()},
        "expected_material_tag_counts": {str(key): value for key, value in expected.items()},
        "actual_cell_orientation_histogram": {
            str(int(value)): int(count)
            for value, count in zip(orientation_values, orientation_counts, strict=True)
        },
        "actual_cell_orientation_info_sha256_le_u32": hashlib.sha256(
            np.asarray(cell_info, dtype="<u4").tobytes()
        ).hexdigest(),
        "substrate_z_intervals": int(substrate_intervals),
        "grating_cells": 0,
        "mpi_size": 1,
    }


def _dispersion_flat_q192_witness(
    levels: Mapping[str, Any],
    cfg: Any,
    bundle: Mapping[str, Any],
    parent_inventory: tuple[Any, Any, Any],
    volume_quadrature_metadata: Any,
    q160_rhs: Any,
    q160_rhs_facts: Mapping[str, Any],
    marker,
) -> dict[str, Any]:
    """Compare actual production q160/q192 port RHS and DtN actions on Nx=2."""

    import copy

    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )

    cfg_q192 = copy.copy(cfg)
    cfg_q192.stage4_dtn_quadrature_degree = 192
    bundle_q192 = None
    rhs_q192 = None
    action160 = None
    action192 = None
    try:
        marker(
            "dispersion_flat_q192_witness_started",
            {"q160_modes": len(parent_inventory[0]), "q160_is_primary": True},
        )
        bundle_q192 = build_same_mesh_physical_action(
            levels,
            cfg_q192,
            6,
            mode_inventory=parent_inventory,
            volume_quadrature_metadata=volume_quadrature_metadata,
            reuse_surface_vector=True,
            functional_store_config=None,
            stage_callback=lambda stage, facts: marker(
                f"dispersion_flat_q192_{stage}", facts
            ),
            surface_progress_interval=1024,
        )
        if int(bundle_q192["dtn_quadrature_degree"]) != 192:
            raise ValueError("q192 witness did not build at the requested surface degree")
        if bundle_q192["mode_sha256"] != bundle["mode_sha256"]:
            raise ValueError("q192 witness changed the actual auto-propagating inventory")
        rhs_q192, rhs_facts_q192 = build_physical_rhs(bundle_q192)
        if rhs_q192.getSize() != q160_rhs.getSize():
            raise ValueError("q160/q192 production RHS vector sizes differ")
        rhs160_values = np.asarray(q160_rhs.getArray(readonly=True), dtype=np.complex128)
        rhs192_values = np.asarray(rhs_q192.getArray(readonly=True), dtype=np.complex128)
        rhs_delta = rhs192_values - rhs160_values
        rhs_relative = float(np.linalg.norm(rhs_delta)) / max(
            float(np.linalg.norm(rhs192_values)), np.finfo(float).tiny
        )

        action160 = apply_owned(bundle["dtn_action"], q160_rhs)
        action192 = apply_owned(bundle_q192["dtn_action"], q160_rhs)
        action160_values = np.asarray(
            action160.getArray(readonly=True), dtype=np.complex128
        )
        action192_values = np.asarray(
            action192.getArray(readonly=True), dtype=np.complex128
        )
        action_delta = action192_values - action160_values
        action_relative = float(np.linalg.norm(action_delta)) / max(
            float(np.linalg.norm(action192_values)), np.finfo(float).tiny
        )
        facts = {
            "status": "DIAGNOSTIC_ONLY",
            "same_mesh": True,
            "same_actual_parent_mode_sha256": str(bundle["mode_sha256"]),
            "same_source_vector": "production_q160_full_physical_rhs",
            "q160": int(bundle["dtn_quadrature_degree"]),
            "q192": int(bundle_q192["dtn_quadrature_degree"]),
            "production_rhs_q160_facts": dict(q160_rhs_facts),
            "production_rhs_q192_facts": rhs_facts_q192,
            "rhs_difference_norm": float(np.linalg.norm(rhs_delta)),
            "rhs_q192_norm": float(np.linalg.norm(rhs192_values)),
            "rhs_relative_difference": rhs_relative,
            "dtn_action_difference_norm": float(np.linalg.norm(action_delta)),
            "dtn_action_q192_norm": float(np.linalg.norm(action192_values)),
            "dtn_action_relative_difference": action_relative,
            "numeric_gate": False,
            "additional_matrix_or_factor": False,
        }
        marker("dispersion_flat_q192_witness_complete", facts)
        return facts
    finally:
        for vector in (action160, action192, rhs_q192):
            if vector is not None:
                vector.destroy()
        if bundle_q192 is not None:
            destroy_same_mesh_physical_action(bundle_q192)


def _dispersion_flat_port_mpc_witness(
    floquet: Any,
    bundle: Mapping[str, Any],
    *,
    rhs_size: int,
    rhs_values: np.ndarray,
    rhs_norm: float,
    rhs_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and summarize the actual production port/MPC path."""

    mpc = getattr(floquet, "mpc", None)
    if mpc is None:
        raise ValueError("flat production Floquet witness has no finalized MPC")
    setup = bundle.get("setup")
    if (
        not isinstance(setup, Mapping)
        or setup.get("floquets", {}).get(6) is not floquet
    ):
        raise ValueError("flat RHS bundle is not bound to the witnessed degree-6 MPC")
    if bundle.get("dtn_action") is None:
        raise ValueError("flat production port witness has no DtN action")
    modes = bundle.get("modes")
    carrier = getattr(bundle["dtn_action"], "carrier", None)
    entries = getattr(carrier, "entries", None)
    if not modes or entries is None or len(entries) != len(modes):
        raise ValueError("flat production port inventory/carrier counts differ")
    mode_sha = bundle.get("mode_sha256")
    if not isinstance(mode_sha, str) or len(mode_sha) != 64:
        raise ValueError("flat production port inventory lacks its canonical SHA256")
    if int(bundle.get("dtn_quadrature_degree", -1)) != 160:
        raise ValueError("flat production port witness must use surface q160")
    if (
        rhs_facts.get("generation") != "dtn_port_modal_physical_rhs"
        or rhs_facts.get("phase_application") != "finalized_floquet_mpc_once"
        or int(rhs_facts.get("degree", -1)) != 6
        or int(rhs_facts.get("mode_count", -1)) != len(modes)
        or rhs_facts.get("mode_manifest_sha256") != mode_sha
    ):
        raise ValueError("flat production RHS facts do not match its finalized port/MPC bundle")

    phases = {
        name: complex(getattr(floquet, name))
        for name in ("phase_x", "phase_y", "phase_corner")
    }
    if not all(
        math.isfinite(value.real) and math.isfinite(value.imag)
        for value in phases.values()
    ):
        raise FloatingPointError("flat production Floquet phase is non-finite")
    phase_moduli = {name: abs(value) for name, value in phases.items()}
    if any(abs(value - 1.0) > 2.0e-12 for value in phase_moduli.values()):
        raise ValueError("flat production Floquet phases are not unit-modulus")
    corner_error = abs(phases["phase_corner"] - phases["phase_x"] * phases["phase_y"])
    if corner_error > 2.0e-12:
        raise ValueError("flat production Floquet corner phase is not phase_x*phase_y")

    constraint_mode = str(getattr(floquet, "constraint_mode_resolved", ""))
    if constraint_mode != "topological_trace_p6":
        raise ValueError(
            "flat production degree-6 MPC did not use topological_trace_p6"
        )
    counts = {
        name: int(getattr(floquet, name))
        for name in (
            "num_constraints",
            "num_x_constraints",
            "num_y_constraints",
            "num_corner_constraints",
            "num_slave_edges",
            "num_slave_faces",
            "num_edge_constraints",
            "num_face_constraints",
            "max_masters_per_slave",
        )
    }
    if min(counts["num_constraints"], counts["num_x_constraints"], counts["num_y_constraints"]) <= 0:
        raise ValueError("flat production MPC is missing x/y periodic constraints")
    errors = {
        name: float(getattr(floquet, name))
        for name in (
            "max_face_pairing_coordinate_error",
            "edge_corner_phase_mismatch",
            "max_edge_midpoint_pairing_error",
            "max_face_midpoint_pairing_error",
            "max_face_transform_fit_residual",
        )
    }
    if not np.isfinite(tuple(errors.values())).all():
        raise FloatingPointError("flat production MPC geometry/phase errors are non-finite")
    rhs_values = np.asarray(rhs_values, dtype=np.complex128).reshape(-1)
    if rhs_values.size != int(rhs_size) or not np.isfinite(rhs_values).all():
        raise ValueError("flat production RHS size/finite check failed")
    rhs_norm = float(rhs_norm)
    if not math.isfinite(rhs_norm) or rhs_norm <= 0.0:
        raise ValueError("flat production top-traction/modal RHS must be finite and nonzero")

    return {
        "status": "ACTUAL_PRODUCTION_PORT_MPC_RHS_VERIFIED",
        "mpc_type": f"{type(mpc).__module__}.{type(mpc).__qualname__}",
        "mpc_object_id_this_process": id(mpc),
        "constraint_mode_resolved": constraint_mode,
        "counts": counts,
        "phases": {
            name: [float(value.real), float(value.imag)]
            for name, value in phases.items()
        },
        "phase_moduli": phase_moduli,
        "corner_phase_product_absolute_error": float(corner_error),
        "pairing_and_phase_errors": errors,
        "dtn_mode_count": len(modes),
        "dtn_mode_manifest_sha256": mode_sha,
        "dtn_quadrature_degree": int(bundle["dtn_quadrature_degree"]),
        "carrier_entry_count": len(entries),
        "rhs_generation": dict(rhs_facts),
        "rhs_rows": int(rhs_size),
        "rhs_nonzero_entries": int(np.count_nonzero(rhs_values)),
        "rhs_norm": rhs_norm,
        "actual_top_traction_and_modal_rhs": True,
        "finalized_mpc_used_by_physical_rhs": True,
        "analytic_or_zero_contrast_shortcut": False,
    }


def _factor_same_matrix(factor: Any, matrix: Any, rhs: Any, solution: Any, marker):
    """Run exactly one symbolic/numeric/solve sequence on one matrix object."""

    matrix_object_id = id(matrix)
    factor.symbolic(matrix)
    marker("p6_mumps_symbolic_complete", {
        "matrix_object_id": matrix_object_id,
        "symbolic_calls": int(factor.symbolic_calls),
        "numeric_calls": int(factor.numeric_calls),
        "solve_calls": int(factor.solve_calls),
        "ordering": factor.preferred_ordering,
        "mumps_info": factor.info(),
    })
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed after MUMPS symbolic")
    factor.numeric(matrix)
    marker("p6_mumps_numeric_complete", {
        "matrix_object_id": matrix_object_id,
        "symbolic_calls": int(factor.symbolic_calls),
        "numeric_calls": int(factor.numeric_calls),
        "solve_calls": int(factor.solve_calls),
        "mumps_info": factor.info(),
        "refinement_settings": factor.refinement_settings(),
    })
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed after MUMPS numeric")
    factor.solve(rhs, solution)
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed before MUMPS solve")
    return matrix_object_id


def run_p6_condensed_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str | None,
) -> dict[str, Any]:
    """Execute one explicitly profiled p6 condensed direct full solve."""

    from mpi4py import MPI
    from petsc4py import PETSc

    from src.common.config_3d import SimulationConfig3D
    from src.geometry.task39extra_v6_f5_mesh_plan import (
        F5_AXIS_PLAN_IDS,
        validate_frozen_f5_axes,
    )
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.physical_intermediate import WorkflowLedger
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_n0_mode_inventory,
    )
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import (
        fine_volume_quadrature_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
        recover_p0_outputs,
    )
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.p4_cell_condensed_inverse import assemble_condensed_ports
    from src.solvers.p6_cell_condensed_action import (
        build_p6_cell_condensed_action_from_carrier,
    )

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    numerical_output = directory / "numerical_output"
    numerical_output.mkdir(exist_ok=True)
    phase_path_value = os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH")
    if not phase_path_value:
        raise RuntimeError("p6 condensed-direct route requires the native-capacity watchdog")
    phase_path = Path(phase_path_value)
    if not phase_path.is_absolute():
        raise RuntimeError("watchdog phase path must be absolute")
    ledger = WorkflowLedger(directory, phase_path)
    summary: dict[str, Any] = {
        "schema": "task39extra.p6-condensed-direct-summary.v2",
        "status": "RUNNING",
        "result_classification": "NOT_QUALIFIED",
        "run_id": resolved_payload.get("run_id"),
        "profile": None,
        "operator_scope": "NOT_YET_BOUND",
        "full_dtn_status": "NOT_YET_BOUND",
        "authority": "AUTHORITY_LIMITED",
        "source_sha": source_sha,
        "matrix_lifecycle": "one_materialized_PETSc_AIJ_same_object_symbolic_numeric_solve",
        "p4_operator": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "outer_ksp": "NOT_BUILT",
        "functional_store": "DISABLED",
        "checks": {},
    }
    levels = None
    bundle = None
    condensed = None
    action = None
    factor = None
    full_rhs = None
    rhs_vector = None
    solution_vector = None
    schur_action_vector = None
    schur_residual_vector = None
    saved_field = None
    native_facts = None
    output_facts = None
    route = None
    try:
        profile_facts = _validate_resolved_profile(resolved_payload)
        route = _direct_run_contract(str(profile_facts["identity"]))
        summary.update(
            profile=profile_facts["identity"],
            operator_scope=route["operator_scope"],
            full_dtn_status=route["full_dtn_status"],
            comparison_family=route["family"],
            active_mode_count_expected=route["active_count"],
            active_mode_sha256_expected=route["active_sha256"],
        )
        profile_rss_cap = int(profile_facts["resources"]["rss_hard_limit_bytes"])
        summary["rss_hard_limit_bytes"] = profile_rss_cap
        inherited_store = sorted(
            key for key in os.environ if key.startswith("TASK39EXTRA_FUNCTIONAL_STORE")
        )
        if inherited_store:
            raise ValueError(
                "p6 direct route forbids functional-store environment: "
                + ", ".join(inherited_store)
            )
        expected_threads = {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "BLIS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        bad_threads = {
            name: os.environ.get(name)
            for name, expected in expected_threads.items()
            if os.environ.get(name) != expected
        }
        if bad_threads:
            raise ValueError(f"p6 direct math thread environment differs from one: {bad_threads}")
        if MPI.COMM_WORLD.size != 1 or PETSc.ScalarType is not np.complex128:
            raise RuntimeError("p6 direct route requires complex128 MPI1")
        if np.dtype(PETSc.IntType) != np.dtype(np.int64):
            raise RuntimeError("p6 direct route requires 64-bit PetscInt")
        cap_value = os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES")
        if route["family"] == "dispersion_flat" and cap_value is None:
            raise RuntimeError("flat direct route requires the native watchdog RSS cap")
        if cap_value is not None and int(cap_value) != profile_rss_cap:
            raise RuntimeError("watchdog launch cap differs from the resolved profile RSS hard limit")
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        if not isinstance(cfg, SimulationConfig3D):
            raise TypeError("resolved direct input did not create SimulationConfig3D")
        if route["family"] == "dispersion_flat":
            if cfg.mesh_plan_id is None or cfg.mesh_plan_sha256 is None:
                raise ValueError("flat direct config lost its frozen axis-plan identity")
            # The input schema intentionally has no user-facing surface-q field;
            # this opt-in profile binds q160 in resolved facts and applies it
            # only to the exact flat runner route.
            cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
        ledger.marker("p6_direct_resolved_profile_bound", {
            "profile": profile_facts["identity"],
            "direct_run_contract": route,
            "derived_profile_identity": profile_facts["identity"],
            "component_options": profile_facts["component_options"],
            "rss_hard_limit_bytes": profile_facts["resources"]["rss_hard_limit_bytes"],
            "native_execution": profile_facts["native_execution"],
            "run_config_created_from_validated_resolved_payload": True,
        })

        ledger.marker("p6_direct_mesh_setup_started", {
            "degrees_built": [6],
            "cross_mesh_fe_reuse": False,
            "functional_store": False,
            "mesh_plan_id": cfg.mesh_plan_id,
            "mesh_plan_sha256": cfg.mesh_plan_sha256,
        })
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False
        )
        if route["family"] == "v7_aniso_n0":
            from src.runners.v7_anisotropic_mesh_evidence import (
                actual_v7_anisotropic_mesh_evidence,
            )

            mesh_evidence = actual_v7_anisotropic_mesh_evidence(
                levels, cfg, required_space_degrees=(6,)
            )
        elif route["family"] == "dispersion_flat":
            mesh_evidence = _dispersion_flat_mesh_evidence(levels, cfg)
        else:
            axes = validate_frozen_f5_axes({
                "mesh_plan_id": cfg.mesh_plan_id,
                "mesh_plan_sha256": cfg.mesh_plan_sha256,
                "mesh_axis_cell_counts": cfg.mesh_axis_cell_counts_requested,
                "mesh_axis_x_values": cfg.mesh_axis_x_values_requested,
                "mesh_axis_y_values": cfg.mesh_axis_y_values_requested,
                "mesh_axis_z_values": cfg.mesh_axis_z_values_requested,
            })
            mesh_evidence = _f5_mesh_evidence(levels, cfg)
            actual_requested_axes = {
                axis: tuple(
                    float(value)
                    for value in getattr(cfg, f"mesh_axis_{axis}_values_requested")
                )
                for axis in ("x", "y", "z")
            }
            if cfg.mesh_plan_id not in F5_AXIS_PLAN_IDS or any(
                tuple(axes[axis]) != actual_requested_axes[axis]
                for axis in ("x", "y", "z")
            ):
                raise ValueError("F5 mesh axes differ from the explicitly frozen input plan")
        if mesh_evidence.get("status") != "PASS":
            raise ValueError("actual direct-run mesh evidence did not pass")
        summary["mesh_evidence"] = mesh_evidence
        ledger.marker("p6_direct_actual_mesh_qa_complete", mesh_evidence)

        parent_inventory = build_dynamic_mode_inventory(cfg)
        if route["family"] == "dispersion_flat":
            if (
                not parent_inventory[0]
                or len(parent_inventory[0]) != len(parent_inventory[1])
                or not isinstance(parent_inventory[2], str)
                or len(parent_inventory[2]) != 64
            ):
                raise ValueError("live flat auto-propagating parent inventory is incomplete")
            route.update(
                parent_count=len(parent_inventory[0]),
                parent_sha256=str(parent_inventory[2]),
                active_count=len(parent_inventory[0]),
                active_sha256=str(parent_inventory[2]),
            )
        elif (
            len(parent_inventory[0]) != route["parent_count"]
            or parent_inventory[2] != route["parent_sha256"]
        ):
            raise ValueError("live full parent inventory differs from the selected direct profile")
        if route["family"] == "v7_aniso_n0":
            active_inventory, operator_selection, selected_parent_indices = (
                build_n0_mode_inventory(parent_inventory, cfg)
            )
        elif route["truncated"]:
            active_inventory, operator_selection, selected_parent_indices = (
                _build_f5_n0_inventory(parent_inventory, cfg)
            )
        else:
            active_inventory = parent_inventory
            operator_selection = None
            selected_parent_indices = tuple(range(len(parent_inventory[0])))
        if (
            len(active_inventory[0]) != route["active_count"]
            or active_inventory[2] != route["active_sha256"]
            or (
                route["truncated"]
                and len(selected_parent_indices) != route["active_count"]
            )
        ):
            raise ValueError("live active inventory differs from its direct profile identity")
        active_modes_by_side = _inventory_mode_counts_by_side(
            active_inventory[1], expected_total=route["active_count"]
        )
        if route["family"] == "v7_aniso_n0" and active_modes_by_side != {
            "bottom": 286,
            "top": 286,
        }:
            raise ValueError("live V7 N0 side counts differ from the frozen 572-mode identity")
        if route["family"] == "v7_aniso_n0":
            inventory_artifacts = _persist_n0_inventory(
                directory,
                parent_inventory,
                active_inventory,
                operator_selection,
                selected_parent_indices,
            )
        elif route["family"] == "dispersion_flat":
            inventory_artifacts = {
                "parent": _persist_flat_parent_inventory(directory, parent_inventory)
            }
        else:
            inventory_artifacts = _persist_f5_inventory(
                directory,
                parent_inventory,
                active_inventory,
                operator_selection,
                selected_parent_indices,
            )
        summary["mode_inventory"] = {
            "parent_mode_count": len(parent_inventory[0]),
            "parent_mode_sha256": parent_inventory[2],
            "active_mode_count": len(active_inventory[0]),
            "active_mode_sha256": active_inventory[2],
            "active_mode_counts_by_side": active_modes_by_side,
            "selected_parent_indices_sha256": (
                None if operator_selection is None
                else operator_selection["selected_parent_indices_sha256"]
            ),
            "selected_parent_indices": (
                None if operator_selection is None else list(selected_parent_indices)
            ),
            "quadrature_authority": (
                "full_32060_parent_q160"
                if route["family"] == "v7_aniso_n0"
                else "all_auto_propagating_flat_inventory_q160"
                if route["family"] == "dispersion_flat"
                else "full_600_parent_q37_degree_even_for_n0_subset"
            ),
            "artifacts": inventory_artifacts,
        }
        ledger.marker("p6_direct_mode_inventory_complete", summary["mode_inventory"])

        volume_quadrature_metadata, _volume_quadrature_records = (
            fine_volume_quadrature_metadata(levels, cfg)
        )
        if route["family"] == "dispersion_flat":
            if tuple(volume_quadrature_metadata) != (
                {"quadrature_degree": 15, "quadrature_rule": "default"},
                {"quadrature_degree": 15, "quadrature_rule": "default"},
            ):
                raise ValueError("dispersion flat P6 requires the V1-verified volume q15 rule")
            bundle = build_same_mesh_physical_action(
                levels,
                cfg,
                6,
                mode_inventory=active_inventory,
                volume_quadrature_metadata=volume_quadrature_metadata,
                reuse_surface_vector=True,
                functional_store_config=None,
                stage_callback=ledger.marker,
                surface_progress_interval=1024,
            )
        elif route["family"] == "v7_aniso_n0":
            bundle = build_same_mesh_physical_action(
                levels,
                cfg,
                6,
                mode_inventory=active_inventory,
                quadrature_mode_inventory=parent_inventory,
                operator_selection=operator_selection,
                selected_parent_indices=selected_parent_indices,
                volume_quadrature_metadata=volume_quadrature_metadata,
                reuse_surface_vector=True,
                reuse_surface_geometry_cache=True,
                surface_geometry_cache_limit_bytes=4 * 1024**3,
                surface_weighted_moment_contraction="q160_weighted_moment_x_then_y_v1",
                prepare_surface_trace_contraction=True,
                surface_assembly_backend=(
                    "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
                ),
                functional_store_config=None,
                stage_callback=ledger.marker,
                surface_progress_interval=1024,
            )
        else:
            expected_volume_metadata = (
                {"quadrature_degree": 15, "quadrature_rule": "default"},
                {"quadrature_degree": 15, "quadrature_rule": "default"},
            )
            if tuple(volume_quadrature_metadata) != expected_volume_metadata:
                raise ValueError(
                    "F5 p6 direct route must retain the historical volume q15 rule"
                )
            parent_surface_kwargs = (
                {
                    "quadrature_mode_inventory": parent_inventory,
                    "operator_selection": operator_selection,
                    "selected_parent_indices": selected_parent_indices,
                }
                if route["truncated"] else {}
            )
            bundle = build_same_mesh_physical_action(
                levels,
                cfg,
                6,
                mode_inventory=active_inventory,
                volume_quadrature_metadata=volume_quadrature_metadata,
                reuse_surface_vector=True,
                functional_store_config=None,
                stage_callback=ledger.marker,
                surface_progress_interval=1024,
                **parent_surface_kwargs,
            )
        expected_surface_q = (
            int(route["surface_quadrature_degree"])
            if route["family"] == "dispersion_flat"
            else 160 if route["family"] == "v7_aniso_n0" else 37
        )
        if int(bundle["dtn_quadrature_degree"]) != expected_surface_q:
            raise ValueError(
                f"live surface quadrature degree {bundle['dtn_quadrature_degree']} "
                f"differs from required full-parent degree {expected_surface_q}"
            )
        if (
            len(bundle["modes"]) != route["active_count"]
            or bundle.get("mode_sha256") != route["active_sha256"]
            or len(bundle["dtn_action"].carrier.entries) != route["active_count"]
        ):
            raise ValueError("live p6 carrier differs from its selected active mode identity")
        if route["family"] == "dispersion_flat" and (
            len(parent_inventory[0]) != len(bundle["modes"])
            or bundle["mode_sha256"] != parent_inventory[2]
            or operator_selection is not None
        ):
            raise ValueError("flat route must use its complete unfiltered auto-propagating parent")
        summary["operator_identity"] = {
            "degree": 6,
            "parent_quadrature_degree": int(bundle["dtn_quadrature_degree"]),
            "parent_mode_count": len(parent_inventory[0]),
            "parent_mode_sha256": parent_inventory[2],
            "active_mode_count": len(bundle["modes"]),
            "active_mode_sha256": bundle["mode_sha256"],
            "operator_selection": operator_selection,
            "operator_scope": route["operator_scope"],
            "full_dtn_status": route["full_dtn_status"],
            "volume_quadrature_metadata": volume_quadrature_metadata,
            "volume_quadrature_records": _volume_quadrature_records,
            "functional_store": False,
            "cross_mesh_fe_reuse": False,
        }
        ledger.marker("p6_direct_surface_carrier_complete", summary["operator_identity"])

        # The source is assembled through the production incident top traction,
        # finalized MPC scatter, and modal DtN RHS composition path.  Keeping
        # this actual vector is also the common q160/q192 action witness input.
        full_rhs, rhs_facts = build_physical_rhs(bundle)
        if full_rhs.getSize() != int(
            levels["spaces"][6].dofmap.index_map.size_global
            * levels["spaces"][6].dofmap.index_map_bs
        ):
            raise ValueError("production flat/port RHS differs from full P6 storage")
        rhs_values_for_witness = np.asarray(
            full_rhs.getArray(readonly=True), dtype=np.complex128
        )
        if not np.isfinite(rhs_values_for_witness).all() or not np.any(rhs_values_for_witness):
            raise FloatingPointError("production incident/MPC/DtN RHS is zero or non-finite")
        summary["production_port_mpc_witness"] = _dispersion_flat_port_mpc_witness(
            levels["floquets"][6],
            bundle,
            rhs_size=int(full_rhs.getSize()),
            rhs_values=rhs_values_for_witness,
            rhs_norm=float(full_rhs.norm()),
            rhs_facts=rhs_facts,
        )
        if route["family"] == "dispersion_flat":
            summary["quadrature_comparison"] = (
                _dispersion_flat_q192_witness(
                    levels,
                    cfg,
                    bundle,
                    parent_inventory,
                    volume_quadrature_metadata,
                    full_rhs,
                    rhs_facts,
                    ledger.marker,
                )
                if mesh_evidence["axis_cell_counts"][0] == 2
                else {
                    "status": "NOT_RUN_BY_PROFILE",
                    "reason": "q192 witness is bounded to the Nx=2 case",
                }
            )

        form_started = perf_counter()
        from dolfinx import fem

        compiled_form = fem.form(bundle["volume_action"].bilinear_form)
        form_seconds = perf_counter() - form_started
        ledger.marker("p6_direct_volume_form_compiled", {
            "wall_seconds": form_seconds,
            "dtype": str(compiled_form.dtype),
            "degree": 6,
        })
        mesh_cells = tuple(int(value) for value in mesh_evidence["axis_cell_counts"])
        support_groups, support_group_by_row, support_facts = _port_support_groups(
            levels,
            bundle["dtn_action"].carrier,
            cfg,
            expected_boundary_cells=mesh_cells[0] * mesh_cells[1],
            expected_modes_by_side=active_modes_by_side,
        )
        summary["port_support"] = support_facts
        condensed_started = perf_counter()
        full_p6_rows = int(
            levels["spaces"][6].dofmap.index_map.size_global
            * levels["spaces"][6].dofmap.index_map_bs
        )
        if route["family"] == "v7_aniso_n0" and full_p6_rows != FULL_P6_ROWS:
            raise ValueError("live V7 p6 dof count differs from the frozen identity")
        condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            levels["spaces"][6],
            levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][6].mpc,
            appended_global_rows=route["active_count"],
            appended_support_owned_cell_groups=support_groups,
            appended_support_group_by_row=support_group_by_row,
            dense_appended_block=True,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            defer_final_assembly=True,
            retain_local_schur_for_matrix_free=True,
            materialize_global_matrix=True,
            geometry_identity_policy="raw_unrounded",
            share_identity_cache=True,
        )
        if condensed.matrix is None:
            raise RuntimeError("p6 direct condensation did not materialize its one PETSc AIJ")
        expected_matrix_rows = int(condensed.active_rows) + route["active_count"]
        _validate_direct_condensed_dimensions(
            condensed,
            full_p6_rows=full_p6_rows,
            appended_rows=route["active_count"],
            matrix_size=condensed.matrix.getSize(),
            expected_active_rows=(
                ACTIVE_ROWS if route["family"] == "v7_aniso_n0" else None
            ),
        )
        port_terms = assemble_condensed_ports(
            condensed, bundle["dtn_action"].carrier
        )
        del port_terms
        condensed.matrix.assemble()
        matrix = condensed.matrix
        matrix_object_id = id(matrix)
        matrix_info = dict(matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM))
        matrix_identity = dict(condensed.build_audit["port_condensed_matrix_identity"])
        condensed_seconds = perf_counter() - condensed_started
        summary["matrix"] = {
            "shape": list(matrix.getSize()),
            "full_p6_storage_rows": int(condensed.full_rows),
            "active_trace_rows": int(condensed.active_rows),
            "appended_port_rows": int(condensed.appended_rows),
            "local_interior_rows_eliminated": int(condensed.interior_rows),
            "actual_matrix_info_after_assembly": matrix_info,
            "petsc_stream_identity": matrix_identity,
            "port_matrix_signs": "[S_V,Bhat;-Dhat,Hhat]",
            "materialized_matrix_object_id": matrix_object_id,
            "assembly_wall_seconds": condensed_seconds,
            "global_full_p6_matrix": False,
            "full_trace_matrix": False,
            "dense_trace_dtn_matrix": False,
            "preallocation_scope": (
                "actual_top_bottom_boundary_cell_support_plus_dense_active_port_block"
            ),
            "condensation_build_audit": condensed.build_audit,
        }
        ledger.marker("p6_direct_augmented_matrix_complete", {
            "shape": list(matrix.getSize()),
            "nz_used": matrix_info.get("nz_used"),
            "nz_allocated": matrix_info.get("nz_allocated"),
            "matrix_identity": matrix_identity,
            "matrix_object_id": matrix_object_id,
            "assembly_wall_seconds": condensed_seconds,
        })

        # The P6 action is explicitly action-only.  Give it a shallow,
        # non-owning metadata view so the sole owner keeps the same materialized
        # PETSc matrix throughout MUMPS and still destroys it exactly once.
        import copy

        action_view = copy.copy(condensed)
        action_view.matrix = None
        action = build_p6_cell_condensed_action_from_carrier(
            action_view,
            bundle["dtn_action"].carrier,
            owns_condensed=False,
            exact_carrier_diagonal_hp=True,
            omit_structural_zero_hlocal=True,
        )
        if action.condensed is not action_view or condensed.matrix is not matrix:
            raise RuntimeError("p6 action borrowed ownership or changed the direct matrix")
        summary["matrix_free_action"] = {
            "uses_materialized_matrix": False,
            "borrowed_action_view_has_no_matrix": action_view.matrix is None,
            "matrix_owner_remains_condensed_system": True,
            "owns_condensed": action.owns_condensed,
            "matrix_object_id": id(condensed.matrix),
        }
        ledger.marker("p6_direct_action_view_ready", summary["matrix_free_action"])

        if full_rhs.getSize() != int(condensed.full_rows):
            raise ValueError("physical p6 RHS differs from the condensed full-storage layout")
        full_rhs_array = np.asarray(full_rhs.getArray(readonly=True))
        if full_rhs_array.shape != (int(condensed.full_rows),):
            raise ValueError("MPI1 p6 RHS storage view differs from its global row count")
        reduced_rhs_array = action.reduce_rhs(
            full_rhs_array,
            rhs_is_mpc_dual=True,
        )
        rhs_vector = condensed.create_augmented_vector()
        if rhs_vector.getSize() != expected_matrix_rows:
            raise ValueError("reduced p6 RHS vector size differs from the materialized matrix")
        rhs_vector.getArray()[:] = reduced_rhs_array
        rhs_vector.assemble()
        solution_vector = rhs_vector.duplicate()
        solution_vector.set(0.0 + 0.0j)
        solution_vector.assemble()
        del reduced_rhs_array
        ledger.marker("p6_direct_rhs_ready", {
            "rhs_generation": rhs_facts,
            "full_rhs_norm": float(full_rhs.norm()),
            "reduced_rhs_norm": float(rhs_vector.norm()),
            "initial_guess": "zero_direct_solution_vector",
            "same_matrix_object_id": id(matrix),
        })

        factor = _MumpsFactor(matrix)
        factor_settings = factor.symbolic_memory_settings()
        summary["factor"] = {
            "backend": "PETSc_MUMPS",
            "preferred_ordering": factor.preferred_ordering,
            "symbolic_memory_settings_before_analysis": factor_settings,
            "same_matrix_object_id": id(matrix),
            "predicted_memory_is_not_a_stop_gate": True,
        }
        solve_started = perf_counter()
        matrix_object_after_factor = _factor_same_matrix(
            factor,
            matrix,
            rhs_vector,
            solution_vector,
            ledger.marker,
        )
        summary["factor"].update(
            symbolic_calls=int(factor.symbolic_calls),
            numeric_calls=int(factor.numeric_calls),
            solve_calls=int(factor.solve_calls),
            solve_lifecycle_wall_seconds=perf_counter() - solve_started,
            matrix_object_id_after_solve=matrix_object_after_factor,
            matrix_object_unchanged=matrix_object_after_factor == matrix_object_id,
            mumps_info_after_solve=factor.info(),
            refinement_settings=factor.refinement_settings(),
        )
        post_matrix_info = dict(matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM))
        summary["matrix"]["actual_matrix_info_after_solve"] = post_matrix_info

        # Compare the direct solve with its own materialized condensed matrix.
        schur_action_vector = matrix.createVecLeft()
        schur_residual_vector = rhs_vector.duplicate()
        matrix.mult(solution_vector, schur_action_vector)
        rhs_vector.copy(schur_residual_vector)
        schur_residual_vector.axpy(PETSc.ScalarType(-1.0), schur_action_vector)
        schur_relative = float(schur_residual_vector.norm()) / max(
            float(rhs_vector.norm()), np.finfo(float).tiny
        )
        schur_residual_array = np.asarray(
            schur_residual_vector.getArray(readonly=True), dtype=np.complex128
        ).copy()
        solution_array = np.asarray(
            solution_vector.getArray(readonly=True), dtype=np.complex128
        )
        ledger.set_phase("solve")
        ledger.marker("p6_direct_materialized_solve_complete", {
            "solve_relative_residual": schur_relative,
            "matrix_object_id": id(matrix),
            "nz_used": post_matrix_info.get("nz_used"),
            "nz_allocated": post_matrix_info.get("nz_allocated"),
            "mumps_info": summary["factor"]["mumps_info_after_solve"],
        })

        def native_apply(storage_values: np.ndarray) -> np.ndarray:
            from dolfinx.la.petsc import create_vector

            vector = create_vector(
                [(levels["spaces"][6].dofmap.index_map,
                  int(levels["spaces"][6].dofmap.index_map_bs))]
            )
            output = None
            try:
                values = np.asarray(storage_values, dtype=np.complex128).reshape(-1)
                if vector.getSize() != values.size:
                    raise ValueError("native A6 storage vector has the wrong global size")
                vector.getArray()[:] = values
                vector.assemble()
                output = apply_owned(bundle["physical_action"], vector)
                return np.asarray(output.getArray(readonly=True), dtype=np.complex128).copy()
            finally:
                if output is not None:
                    output.destroy()
                vector.destroy()

        ledger.set_phase("recovery")
        native_started = perf_counter()
        native_facts = action.evaluate_native_residual(
            solution_array,
            full_rhs_array,
            native_apply,
            rhs_is_mpc_dual=True,
            reduced_residual=schur_residual_array,
        )
        native_seconds = perf_counter() - native_started
        native_relative = float(native_facts["native_residual_relative"])
        native_identity_relative = float(native_facts["native_identity_relative"])
        if not np.isfinite([native_relative, native_identity_relative, schur_relative]).all():
            raise FloatingPointError("direct p6 or native A6 residual facts are non-finite")
        residual_key = route["residual_key"]
        residual_gate_key = (
            "original_A6_n0_residual_pass"
            if residual_key == "original_A6_n0_relative"
            else "original_A6_full_residual_pass"
        )
        summary["residuals"] = {
            "condensed_direct_relative": schur_relative,
            residual_key: native_relative,
            f"{residual_key}_gate": 1.0e-6,
            "native_identity_relative": native_identity_relative,
            "native_identity_formula": native_facts["native_identity_formula"],
            "operator_scope": route["residual_scope"],
            "wall_seconds": native_seconds,
            "rhs_norm": native_facts["native_rhs_norm"],
            "finite": True,
        }
        residual_finite_key = (
            "original_A6_n0_finite"
            if residual_key == "original_A6_n0_relative"
            else "original_A6_full_finite"
        )
        summary["checks"].update(
            condensed_direct_residual_finite=True,
            **{residual_finite_key: True},
            **{residual_gate_key: native_relative <= 1.0e-6},
            native_condensed_identity_finite=True,
            native_condensed_identity_relative=native_identity_relative,
        )
        ledger.marker(
            f"p6_direct_{route['residual_scope']}_residual_complete",
            summary["residuals"],
        )

        from dolfinx.la.petsc import create_vector

        recovered = np.asarray(native_facts["storage_solution"], dtype=np.complex128)
        if recovered.shape != (int(condensed.full_rows),) or not np.isfinite(recovered).all():
            raise ValueError("recovered full p6 storage is incomplete or non-finite")
        saved_field = create_vector(
            [(levels["spaces"][6].dofmap.index_map,
              int(levels["spaces"][6].dofmap.index_map_bs))]
        )
        if saved_field.getSize() != recovered.size:
            raise ValueError("recovered p6 field vector has the wrong global size")
        saved_field.getArray()[:] = recovered
        saved_field.assemble()
        del recovered

        truncation = None
        if route["family"] == "v7_aniso_n0":
            from src.runners.v7_n0_output_audit import truncation_action_observation

            truncation = truncation_action_observation(
                modes=bundle["modes"],
                entries=bundle["dtn_action"].carrier.entries,
                solution=np.asarray(saved_field.getArray(readonly=True)),
                residual=np.asarray(native_facts["native_residual"]),
                rhs_norm=float(full_rhs.norm()),
                incident_projections=bundle["incident_projections"],
            )
            summary["same_field_truncation"] = truncation
            ledger.marker("p6_direct_tail20_observation_complete", truncation)

        from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            iter_canonical_full_fe_packets,
        )

        def canonical_export(field, output_dir):
            return write_canonical_packet_shard(
                output_dir / "canonical_solution.rank0000.jsonl",
                iter_canonical_full_fe_packets(
                    field.function_space, field, levels["floquets"][6]
                ),
                audit_packets=True,
            )

        output_policy = _direct_output_policy(route)
        should_export_canonical = bool(
            resolved_payload.get("output", {}).get("export_canonical_vectors", False)
        )
        output_facts = recover_p0_outputs(
            bundle,
            saved_field,
            numerical_output,
            canonical_export=(canonical_export if should_export_canonical else None),
            export_all_port_modes=True,
            active_port_outputs_only=output_policy["active_port_outputs_only"],
        )
        if route["family"] == "dispersion_flat":
            output_facts["flat_layer_reference_outputs"] = (
                _write_direct_flat_reference_outputs(
                    numerical_output,
                    cfg,
                    MPI.COMM_WORLD,
                    output_facts,
                )
            )
        auxiliary = np.asarray(output_facts.pop("auxiliary"), dtype=np.complex128)
        if auxiliary.shape != (route["active_count"],) or not np.isfinite(auxiliary).all():
            raise ValueError("direct p6 output did not recover every active finite modal amplitude")
        auxiliary_sha = hashlib.sha256(memoryview(np.ascontiguousarray(auxiliary)).cast("B")).hexdigest()
        output_facts["auxiliary"] = {
            "count": int(auxiliary.size),
            "finite": True,
            "complex128_payload_sha256": auxiliary_sha,
        }
        rta_closure = output_facts["volume_metrics"].get("energy_closure_error_port_volume")
        if rta_closure is None or not np.isfinite(float(rta_closure)):
            raise ValueError("direct p6 output did not produce a finite port-volume energy closure")
        output_facts["energy_closure_error_port_volume"] = float(rta_closure)
        if route["family"] == "v6_f5" and route["truncated"]:
            # Port files contain only the 80 active N0 amplitudes.  The generic
            # diffraction report is independently sampled from the recovered
            # field; omitted DtN channels are neither reconstructed nor zero-filled.
            output_facts["port_metrics"].update(
                operator_scope=route["operator_scope"],
                full_dtn_status=route["full_dtn_status"],
                parent_mode_count=route["parent_count"],
                active_mode_count=route["active_count"],
                omitted_channel_values="NOT_COMPUTED",
            )
            output_facts["diffraction_metrics"].update(
                operator_scope=route["operator_scope"],
                full_dtn_status=route["full_dtn_status"],
                omitted_channel_values="NOT_COMPUTED",
                source=output_policy["diffraction_source"],
            )
        summary["official_result"] = output_facts
        summary["port_output_policy"] = output_policy
        summary["checks"].update(
            rta_port_volume_energy_closure_pass=abs(float(rta_closure)) <= 1.0e-5,
            physical_energy_gate=1.0e-5,
            field_export_finite=bool(output_facts["electric_finite"]),
            auxiliary_export_finite=bool(output_facts["auxiliary_finite"]),
        )
        if route["family"] == "v7_aniso_n0":
            from src.runners.v7_n0_output_audit import saved_output_observation

            output_audit = saved_output_observation(
                numerical_output, output_facts, cfg, truncation
            )
            summary["v7_output_audit"] = output_audit
        summary["matched_reference"] = {
            "status": "REFERENCE_AUTHORITY_LIMITED",
            "reference_availability": (
                "FLAT_LAYER_ANALYTIC_REFERENCE_COMPUTED"
                if route["family"] == "dispersion_flat"
                else "REFERENCE_NOT_AVAILABLE"
            ),
            "reason": (
                "historical iterative baseline uses y=7 while both new F5 direct runs use y=2; "
                "comparison with that baseline changes both y discretization and solution strategy"
                if route["family"] == "v6_f5"
                else "same-material independent full-DtN reference and mesh convergence were not run"
                if route["family"] != "dispersion_flat"
                else "flat-layer analytic reference is reported separately; auto-propagating DtN omits evanescent orders"
            ),
            "new_f5_pair_comparison": (
                "same y=2 mesh and P6 direct strategy; full600 versus n0 differs in active DtN channels"
                if route["family"] == "v6_f5" and route["truncated"]
                else None
            ),
        }
        summary["complete_solve"] = True
        summary["factor"]["same_matrix_lifecycle_verified"] = (
            factor.symbolic_calls == factor.numeric_calls == factor.solve_calls == 1
            and matrix_object_after_factor == matrix_object_id
        )
        summary["checks"]["same_materialized_matrix_symbolic_numeric_solve"] = bool(
            summary["factor"]["same_matrix_lifecycle_verified"]
        )
        modal_finite_key = "all_active_modal_amplitudes_finite"
        summary["checks"][modal_finite_key] = True
        if route["family"] == "v7_aniso_n0":
            # Retain the already-reviewed V7 report key as a compatibility alias.
            summary["checks"]["all_572_modal_amplitudes_finite"] = True
        required_checks = (
            residual_gate_key,
            modal_finite_key,
            "rta_port_volume_energy_closure_pass",
            "field_export_finite",
            "auxiliary_export_finite",
            "same_materialized_matrix_symbolic_numeric_solve",
        )
        passed = all(bool(summary["checks"].get(key)) for key in required_checks)
        route_label = route["summary_prefix"].upper().replace("_", "_")
        summary["status"] = (
            f"{route_label}_{'COMPLETED' if passed else 'GATE_FAILED'}_AUTHORITY_LIMITED"
        )
        summary["result_classification"] = summary["status"]
        summary["passed"] = passed
        summary["errors"] = [] if passed else [
            key for key in required_checks if not summary["checks"].get(key)
        ]
        summary["elapsed_monotonic_seconds"] = time.monotonic() - ledger.started
        ledger.set_phase("complete")
        ledger.marker(f"{route_label}_{'COMPLETED' if passed else 'GATE_FAILED'}", {
            "passed": passed,
            "status": summary["status"],
            "operator_scope": summary["operator_scope"],
            "full_dtn_status": summary["full_dtn_status"],
            residual_key: native_relative,
            "rta_energy_closure": float(rta_closure),
        })
        summary_path = directory / "p6_condensed_direct_summary.json"
        _atomic_json(summary_path, summary)
        return {
            "passed": passed,
            "errors": list(summary["errors"]),
            "summary": str(summary_path),
            "result_classification": summary["result_classification"],
            "complete_solve": True,
            "numerical_output_directory": str(numerical_output),
        }
    except BaseException as exc:
        summary.update(
            status="FAILED",
            result_classification=(
                f"{route['summary_prefix'].upper()}_FAILED"
                if route is not None
                else "P6_CONDENSED_DIRECT_FAILED_BEFORE_PROFILE_BINDING"
            ),
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            failed_stage=ledger.last_stage,
            failed_phase=ledger.phase,
            elapsed_monotonic_seconds=time.monotonic() - ledger.started,
        )
        try:
            _atomic_json(directory / "p6_condensed_direct_summary.json", summary)
        except (OSError, TypeError, ValueError) as write_error:
            print(
                f"failed to persist direct-solve failure summary: {write_error!r}",
                file=sys.stderr,
            )
        try:
            ledger.marker(
                f"{route['summary_prefix'].upper()}_FAILED"
                if route is not None else "P6_CONDENSED_DIRECT_FAILED",
                {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "failed_stage": ledger.last_stage,
                },
            )
        except (OSError, RuntimeError, TypeError, ValueError) as marker_error:
            print(
                f"failed to persist direct-solve failure marker: {marker_error!r}",
                file=sys.stderr,
            )
        raise
    finally:
        for vector in (
            schur_residual_vector,
            schur_action_vector,
            solution_vector,
            rhs_vector,
            saved_field,
            full_rhs,
        ):
            if vector is not None:
                try:
                    vector.destroy()
                except Exception as cleanup_error:  # noqa: BLE001
                    print(
                        f"direct-solve PETSc vector cleanup failed: {cleanup_error!r}",
                        file=sys.stderr,
                    )
        if factor is not None:
            try:
                factor.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve MUMPS cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if action is not None:
            try:
                action.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve p6 action cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if condensed is not None:
            try:
                condensed.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve condensed system cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if bundle is not None:
            try:
                destroy_same_mesh_physical_action(bundle)
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve physical bundle cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )


__all__ = ["PROFILE_ID", "run_p6_condensed_direct"]
