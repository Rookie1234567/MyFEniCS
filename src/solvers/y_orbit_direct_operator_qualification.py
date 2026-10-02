"""Exhaustive original-cell qualification for the reviewed direct X/XZ/Y profiles.

This is an opt-in, pre-factor witness producer and an array-only verifier.
It uses the original FFCx curl+mass tensor source, the finalized native MPC,
and the existing shared entity coefficient maps.  All 300 cell columns and
all global/local Fourier pairs are covered.  It creates no whole-Ny matrix,
Fourier map, Schur matrix, factor or solve.  Numerical execution belongs only
to the externally supervised worker; importing this module performs none.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json

import numpy as np

SCHEMA = "task40extra.direct-X-original-cell-contribution-proof.v1"
CELL_DIMENSION = 300
INTERIOR_DIMENSION = 108
TRACE_DIMENSION = 192
LIMIT = 1.0e-11
# A fail-closed allocation bound, not a truncation of any channel.  The
# actual supports are counted before allocation and must fit this bound.
MAX_CELL_SUPPORT = 600


def checked_integer_metadata(values, upper, *, maximum=2**31 - 1):
    """Pure scalar overflow-before-convert admission, usable without NumPy."""
    if type(upper) is not int or type(maximum) is not int or upper <= 0 or maximum < 0:
        raise ValueError("positive explicit integer index-map capacity required")
    if upper - 1 > maximum:
        raise OverflowError("index-map capacity exceeds target dtype before narrowing")
    for value in values:
        if type(value) is not int:
            raise TypeError("indices must be actual integers before narrowing")
        if value < 0 or value >= upper:
            raise ValueError("index outside actual index-map range before narrowing")
        if value > maximum:
            raise OverflowError("index exceeds target dtype before narrowing")
    return True


def _local_int32(values, upper):
    raw = np.asarray(values)
    _require(raw.ndim == 1 and raw.dtype.kind in "iu", "wide integer index input required before narrowing")
    checked_integer_metadata([int(value) for value in raw], int(upper))
    return raw.astype(np.int32, copy=False)


def _local_int64(values, upper):
    raw = np.asarray(values)
    _require(raw.ndim == 1 and raw.dtype.kind in "iu", "wide integer index input required before narrowing")
    checked_integer_metadata([int(value) for value in raw], int(upper), maximum=2**63 - 1)
    return raw.astype(np.int64, copy=False)


def safe_witness_name(name):
    """Injective, scalar-only codec for the runner's safe artifact alphabet."""
    return "direct_operator_" + "".join(
        character if character.isascii() and character.isalnum()
        else "_x" + format(ord(character), "x") + "_" for character in str(name))


def _gate(gate, label, payload=0, workspace=0, **facts):
    if not callable(gate):
        raise ValueError("fresh whole-worker allocation gate required")
    gate(label, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                 "allocation_semantics": "additional_objects_to_current_resident_RSS", **facts})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(array):
    _require(isinstance(array, np.ndarray) and not array.dtype.hasobject,
             "numeric ndarray witness required")
    return hashlib.sha256(memoryview(np.ascontiguousarray(array)).cast("B")).hexdigest()


def _complex(value):
    value = complex(value)
    _require(np.isfinite(value), "finite phase required")
    return [value.real, value.imag]


def _uncomplex(value):
    _require(isinstance(value, (list, tuple)) and len(value) == 2, "explicit complex pair required")
    result = complex(*value)
    _require(np.isfinite(result), "finite saved phase required")
    return result


def _json(value):
    if isinstance(value, np.generic):
        return _json(value.item())
    if isinstance(value, complex):
        return _complex(value)
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json(value.tolist())
    _require(value is None or isinstance(value, (str, int, float, bool)),
             "unsupported source witness metadata")
    return value


def _token(value):
    return json.dumps(_json(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _relative(left, right):
    numerator = float(np.linalg.norm(left - right))
    denominator = float(np.linalg.norm(left) + np.linalg.norm(right))
    return numerator / denominator if denominator else (0.0 if numerator == 0 else float("inf"))


def _finite_array(array, *, shape=None, kind=None):
    _require(isinstance(array, np.ndarray) and not array.dtype.hasobject,
             "loaded witness must be a numeric ndarray")
    if shape is not None:
        _require(tuple(array.shape) == tuple(shape), "loaded witness shape differs")
    if kind is not None:
        _require(array.dtype.kind in kind, "loaded witness dtype kind differs")
    if array.dtype.kind in "fc":
        _require(np.isfinite(array).all(), "nonfinite complete witness")
    return array


class _Writer:
    """Persist immutable templates by full content without retaining arrays."""
    def __init__(self, save, gate):
        _require(callable(save), "array writer callback required")
        self.save, self.gate = save, gate
        self.templates = {}
        self.names = {}
        self.payload_bytes = 0

    def array(self, name, array, *, intern=False):
        array = _finite_array(np.asarray(array))
        _gate(self.gate, "original_cell_witness_writer", workspace=2 * array.nbytes + 65536,
              shape=list(array.shape), dtype=array.dtype.str)
        digest = _hash(array)
        key = (array.dtype.str, tuple(array.shape), digest)
        if intern and key in self.templates:
            return self.templates[key]
        # Injective byte codec: underscores are encoded too, so a literal
        # name cannot collide with an encoded slash or another punctuation.
        safe = safe_witness_name(name)
        if safe in self.names:
            original_name, original_key, original_reference = self.names[safe]
            _require(original_name == str(name) and original_key == key,
                     "array witness safe-name or repeated-content collision")
            return original_reference
        descriptor = self.save(safe, array)
        _require(isinstance(descriptor, Mapping), "writer must return a manifest descriptor")
        reference = {"artifact": safe, "descriptor": _json(descriptor),
                     "numeric_sha256": digest, "shape": list(array.shape), "dtype": array.dtype.str}
        self.names[safe] = (str(name), key, reference)
        if intern:
            self.templates[key] = reference
        self.payload_bytes += int(array.nbytes)
        return reference


def _read(reference, load):
    _require(isinstance(reference, Mapping) and isinstance(reference.get("artifact"), str),
             "manifest-bound array reference required")
    array = _finite_array(load(reference["artifact"]), shape=reference["shape"])
    _require(array.dtype.str == reference["dtype"] and _hash(array) == reference["numeric_sha256"],
             "complete numeric witness hash/dtype differs")
    return array


def _metadata(direct_profile):
    from .y_orbit_direct_profile import DirectTwoCellProfile, direct_profile_metadata
    selected = DirectTwoCellProfile(direct_profile)
    inventories = {
        DirectTwoCellProfile.X: ((6, 4, 5), (120, 25468, 23808, 12960, 60, 13236, 11904, 6480)),
        DirectTwoCellProfile.XZ: ((6, 4, 7), (168, 35332, 33024, 18144, 84, 18364, 16512, 9072)),
        DirectTwoCellProfile.Y: ((4, 6, 5), (120, 25468, 23808, 12960, 40, 8940, 7936, 4320)),
    }
    _require(selected in inventories, "this qualification is authorized only for direct X/XZ/Y")
    metadata = direct_profile_metadata(selected)
    dimensions, inventory = inventories[selected]
    _require(metadata.name == selected.value and metadata.dimensions == dimensions,
             "reviewed direct profile dimensions changed")
    _require((metadata.cell_count, metadata.storage_rows, metadata.independent_rows,
              metadata.interior_rows, metadata.local_cell_count, metadata.local_storage_rows,
              metadata.local_independent_rows, metadata.local_interior_rows) == inventory,
             "reviewed X/XZ/Y complete inventory changed")
    if selected is DirectTwoCellProfile.Y:
        _require(metadata.ny == 6 and metadata.local_y_cells == 2 and metadata.replication_count == 3
                 and metadata.q_port_counts == (76, 76, 76, 152, 76, 76)
                 and metadata.sector_port_counts == (228, 152, 152)
                 and metadata.augmented_rows_per_q == (1884, 1884, 1884, 1960, 1884, 1884),
                 "reviewed Y complete q/sector/alias inventory changed")
    return metadata


def _native_controls(space, mpc, entities, writer, role):
    """Export actual finalized links; use no coordinate-derived MPC surrogate."""
    full_rows = int(space.dofmap.index_map.size_local)
    _gate(writer.gate, role + "_complete_native_MPC_controls", 8 * full_rows * 8,
          8 * full_rows * 8, full_rows=full_rows)
    slaves_raw = np.asarray(mpc.slaves)
    _require(slaves_raw.ndim == 1 and slaves_raw.dtype.kind in "iu", "wide actual slave integers required")
    checked_integer_metadata([int(value) for value in slaves_raw], full_rows, maximum=2**63 - 1)
    slaves = slaves_raw.astype(np.int64, copy=False)
    _require(slaves.ndim == 1 and len(np.unique(slaves)) == len(slaves)
             and (not len(slaves) or (slaves.min() >= 0 and slaves.max() < full_rows)),
             "actual serial native slave inventory invalid")
    slaves = np.sort(slaves)
    independent = np.setdiff1d(np.arange(full_rows, dtype=np.int64), slaves)
    _require(np.array_equal(independent, entities.independent),
             "entity rows must equal complete actual finalized independent inventory")
    coefficients, offsets = mpc.coefficients()
    coefficients, offsets = np.asarray(coefficients), np.asarray(offsets)
    _require(coefficients.dtype == np.dtype(np.complex128) and offsets.dtype.kind in "iu"
             and len(offsets) > (int(slaves.max()) if len(slaves) else 0),
             "actual finalized MPC coefficient/offset controls missing")
    row_offsets, masters, values = [0], [], []
    for slave in slaves:
        linked = np.asarray(mpc.masters.links(int(slave)))
        start, stop = int(offsets[int(slave)]), int(offsets[int(slave) + 1])
        _require(0 <= start <= stop <= len(coefficients) and len(linked) == stop - start,
                 "native MPC master/actual coefficient lengths differ")
        master_map = mpc.function_space.dofmap.index_map
        linked_int32 = _local_int32(linked, int(master_map.size_local) + int(master_map.num_ghosts))
        original_raw = np.asarray(master_map.local_to_global(linked_int32))
        _require(original_raw.dtype.kind in "iu", "wide original master integers required")
        checked_integer_metadata([int(value) for value in original_raw], full_rows, maximum=2**63 - 1)
        original = original_raw.astype(np.int64, copy=False)
        _require(len(original) and np.isin(original, independent).all(),
                 "chained/missing native MPC master is outside the proven original profile")
        masters.extend(map(int, original))
        values.extend(map(complex, coefficients[start:stop]))
        row_offsets.append(len(masters))
    return {"full_rows": full_rows,
            "independent": writer.array(role + "/native/independent", independent),
            "slaves": writer.array(role + "/native/slaves", slaves),
            "slave_offsets": writer.array(role + "/native/slave_offsets", np.asarray(row_offsets, dtype=np.int64)),
            "masters": writer.array(role + "/native/masters", np.asarray(masters, dtype=np.int64)),
            "coefficients": writer.array(role + "/native/coefficients", np.asarray(values, dtype=np.complex128)),
            "actual_offsets": writer.array(role + "/native/actual_offsets", offsets),
            "actual_coefficients": writer.array(role + "/native/actual_coefficients", coefficients),
            "MPC_is_finalized": bool(getattr(mpc, "is_finalized", True)),
            "master_semantics": "actual finalized augmented-local links converted with MPC index_map"}


def _entity_controls(entities, writer, role):
    _require(entities._transform_bank is not None, "mandatory Step0 shared transform bank missing")
    records = []
    for index, (key, (rows, matrix)) in enumerate(entities.records.items()):
        orbit, base = key
        transform_key = entities.transform_key(key)
        _require(not matrix.flags.writeable, "shared original coefficient template is writable")
        first, size = entities.slots[base]
        _require(len(rows) == size and matrix.shape == (size, size), "complete entity channels changed")
        records.append({"orbit": int(orbit), "base": _json(base), "first": int(first), "size": int(size),
                        "rows": writer.array(role + f"/entity/{index}/rows", rows),
                        "matrix": writer.array(role + f"/entity/{index}/template", matrix, intern=True),
                        "actual_state": _json(entities.actual_state_witness(key)),
                        "template_key": _json(vars(transform_key))})
    return {"ny": int(entities.ny), "width": int(entities.width), "records": records,
            "dimension_counts": _json(entities.dimension_counts),
            "y_widths": writer.array(role + "/entity/actual_y_widths", entities.y_widths),
            "complete_coefficient_schema": "actual original canonical_to_native; inverse/adjoint not substituted"}


def _decoded_native(source, load):
    controls = source["native"]
    full = int(controls["full_rows"])
    independent = _read(controls["independent"], load)
    slaves = _read(controls["slaves"], load)
    offsets = _read(controls["slave_offsets"], load)
    masters = _read(controls["masters"], load)
    coefficients = _read(controls["coefficients"], load)
    actual_offsets = _read(controls["actual_offsets"], load)
    actual_coefficients = _read(controls["actual_coefficients"], load)
    _require(independent.dtype.kind in "iu" and slaves.dtype.kind in "iu"
             and offsets.dtype.kind in "iu" and masters.dtype.kind in "iu",
             "integer native controls required before narrowing")
    _require(np.array_equal(np.sort(np.concatenate((independent, slaves))), np.arange(full))
             and len(np.unique(independent)) == len(independent)
             and len(np.unique(slaves)) == len(slaves)
             and np.intersect1d(independent, slaves).size == 0,
             "saved complete independent/slave partition fails")
    _require(len(offsets) == len(slaves) + 1 and offsets[0] == 0
             and np.all(np.diff(offsets) > 0) and offsets[-1] == len(masters)
             and len(masters) == len(coefficients) and np.isin(masters, independent).all(),
             "saved finalized MPC full slave links fail")
    rows = {int(original): ((int(original), 1.0 + 0j),) for original in independent}
    for index, slave in enumerate(slaves):
        start, stop = int(offsets[index]), int(offsets[index + 1])
        raw_start, raw_stop = int(actual_offsets[int(slave)]), int(actual_offsets[int(slave) + 1])
        _require(raw_stop - raw_start == stop - start
                 and np.array_equal(actual_coefficients[raw_start:raw_stop], coefficients[start:stop]),
                 "compact MPC witness is not the actual finalized coefficient slice")
        rows[int(slave)] = tuple((int(master), complex(value)) for master, value
                                in zip(masters[start:stop], coefficients[start:stop], strict=True))
    return independent, rows


def _decoded_entities(source, load):
    entity = source["entities"]
    independent = _read(source["native"]["independent"], load)
    row_owner, canonical_covered, bases = {}, set(), {}
    for record in entity["records"]:
        rows, matrix = _read(record["rows"], load), _read(record["matrix"], load)
        size, first, orbit = int(record["size"]), int(record["first"]), int(record["orbit"])
        _require(rows.dtype.kind in "iu" and len(rows) == size and matrix.shape == (size, size)
                 and 0 <= orbit < entity["ny"] and 0 <= first <= entity["width"] - size,
                 "complete saved entity row/channel shape fails")
        state = record["actual_state"]
        _require(int(state["dimension"]) in (1, 2, 3) and len(state["positions"]) == size,
                 "actual native incidence/ordered channel witness missing")
        base = _token(record["base"])
        bases.setdefault(base, set()).add(orbit)
        for position, row in enumerate(rows):
            _require(0 <= int(row) < len(independent) and int(row) not in row_owner,
                     "duplicate/missing entity independent row")
            canonical = tuple(orbit * entity["width"] + first + j for j in range(size))
            row_owner[int(row)] = (matrix, position, canonical)
        for j in range(size):
            canonical = orbit * entity["width"] + first + j
            _require(canonical not in canonical_covered, "duplicate canonical entity channel")
            canonical_covered.add(canonical)
    _require(set(row_owner) == set(range(len(independent)))
             and canonical_covered == set(range(len(independent)))
             and entity["ny"] * entity["width"] == len(independent)
             and all(value == set(range(entity["ny"])) for value in bases.values()),
             "complete entity orbit/base/channel partition fails")
    return row_owner


def _cell_map(native_dofs, independent, expansion, row_owner, gate, label):
    """Compose existing MPC rows with existing coefficient rows, all columns."""
    position = {int(row): index for index, row in enumerate(independent)}
    support = set()
    for original in native_dofs:
        for master, _ in expansion[int(original)]:
            support.update(row_owner[position[master]][2])
    support = tuple(sorted(support))
    _require(0 < len(support) <= MAX_CELL_SUPPORT,
             "actual cell canonical support exceeds reviewed bounded audit; no channels dropped")
    _gate(gate, label, CELL_DIMENSION * len(support) * 16 + len(support) * 8,
          CELL_DIMENSION * 32, actual_complete_columns=len(support), original_columns=CELL_DIMENSION)
    matrix = np.zeros((CELL_DIMENSION, len(support)), dtype=np.complex128)
    column = {value: index for index, value in enumerate(support)}
    for local_row, original in enumerate(native_dofs):
        for master, coefficient in expansion[int(original)]:
            transform, entity_row, canonical = row_owner[position[master]]
            for j, value in enumerate(canonical):
                matrix[local_row, column[value]] += coefficient * transform[entity_row, j]
    return np.asarray(support, dtype=np.int64), matrix


def _actual_grid_cell(coordinates, axes):
    lower, upper = coordinates.min(axis=0), coordinates.max(axis=0)
    grid = []
    for axis in range(3):
        matches = np.flatnonzero(np.abs(np.asarray(axes[axis]) - lower[axis]) <= 1e-11)
        _require(len(matches) == 1 and matches[0] < len(axes[axis]) - 1,
                 "actual cell has no unique declared tensor-grid lower plane")
        index = int(matches[0])
        _require(abs(float(axes[axis][index + 1]) - upper[axis]) <= 1e-11,
                 "actual cell upper plane differs from complete profile")
        grid.append(index)
    return tuple(grid)


def _export_source(bundle, entities, *, writer, load_array, role, metadata, entity_config=None):
    """Only original helpers tabulate/orient; no elimination is performed."""
    from dolfinx import fem
    from .hcurl_assembly_time_condensation import (
        _cell_tag_array, _cell_integral_kernels, _canonical_axis_aligned_coordinates,
        _global_raw_tensor_cache, _orient_cell_tensor,
    )
    from .y_orbit_direct_profile import validate_direct_physical_config, direct_notch_box_and_count
    from dataclasses import fields
    setup = bundle["setup"]
    space, floquet = setup["spaces"][4], setup["floquets"][4]
    mesh, mpc = space.mesh, floquet.mpc
    _require(int(entities.ny) in (metadata.local_y_cells, metadata.ny),
             "actual source Ny differs from the selected full/two-cell profile")
    local = int(entities.ny) == metadata.local_y_cells
    _require(role != "notch" or (not local and entity_config is not None),
             "notch export requires explicit original full-profile entity config")
    if role == "notch":
        validate_direct_physical_config(entity_config, metadata.name)
        # The Y box is independently approved for three actual mesh cells;
        # actual raw geometry and state keys remain unchanged.
        expected_box, _changed_cell_count = direct_notch_box_and_count(metadata.name)
        _require(tuple(bundle["cfg"].air_void_box_nm) == expected_box and bundle["cfg"].cell_notch is None,
                 "only the approved profile-specific physical air-void notch may be exported")
        for field in fields(entity_config):
            if field.name not in ("case_name", "geometry_identity", "air_void_box_nm"):
                _require(getattr(bundle["cfg"], field.name) == getattr(entity_config, field.name),
                         "notch source changed an unapproved physical/discrete config field")
    elif not local:
        _require(entity_config is None, "regular global source may not substitute its entity config")
        validate_direct_physical_config(bundle["cfg"], metadata.name)
    else:
        validate_direct_physical_config(bundle["physical_cfg"], metadata.name)
        _require(bundle["quotient_context"].direct_profile_name == metadata.name
                 and float(bundle["cfg"].lambda0) == .7 and float(bundle["cfg"].incident_phi_deg) == 5.0,
                 "actual local original physical/profile identity differs")
    axes = metadata.local_axes if local else metadata.global_axes
    expected_cells = metadata.local_cell_count if local else metadata.cell_count
    expected_rows = metadata.local_storage_rows if local else metadata.storage_rows
    expected_independent = metadata.local_independent_rows if local else metadata.independent_rows
    _require(mesh.comm.size == 1 and int(mesh.topology.dim) == 3
             and int(space.element.space_dimension) == CELL_DIMENSION
             and int(space.element.basix_element.degree) == 4
             and int(space.dofmap.index_map_bs) == 1
             and int(mesh.topology.index_map(3).size_local) == expected_cells
             and int(space.dofmap.index_map.size_local) == expected_rows
             and int(entities.full_rows) == expected_rows and len(entities.independent) == expected_independent,
             "actual original cell/storage/full-channel inventory differs from reviewed X")
    collection = entities._collection_identity
    expected_entity_cfg = bundle["cfg"] if entity_config is None else entity_config
    _require(collection is not None and collection[0] is space and collection[1] is floquet
             and collection[2] is expected_entity_cfg, "entity maps do not belong to the actual primary space/MPC/entity config")
    _require(tuple(tuple(getattr(expected_entity_cfg, f"mesh_axis_{name}_values")) for name in ("x", "y", "z")) == axes,
             "original entity config axes differ from the actual changed/source geometry")
    _require(tuple(tuple(getattr(bundle["cfg"], f"mesh_axis_{name}_values")) for name in ("x", "y", "z")) == axes,
             "actual original axes differ from reviewed X source")
    _gate(writer.gate, role + "_source_metadata", 8 * expected_cells * CELL_DIMENSION * 8,
          32 * expected_rows, expected_cells=expected_cells)
    source = {"role": role, "axes": _json(axes), "cell_count": expected_cells,
              "profile": metadata.identity(), "local_two_cell": local,
              "native": _native_controls(space, mpc, entities, writer, role),
              "entities": _entity_controls(entities, writer, role), "cells": [], "raw_templates": [],
              "oriented_templates": [], "numeric_factor_calls": 0, "whole_Ny_matrix_created": False}
    source["explicit_shared_entity_config_for_changed_material"] = entity_config is not None
    source["actual_volume_cfg_identity"] = _json({name: getattr(bundle["cfg"], name) for name in (
        "case_name", "lambda0", "incident_phi_deg", "mesh_axis_cell_counts", "mesh_axis_x_values",
        "mesh_axis_y_values", "mesh_axis_z_values")})
    interior = _local_int64(space.element.basix_element.entity_dofs[3][0], CELL_DIMENSION)
    trace = np.setdiff1d(np.arange(CELL_DIMENSION, dtype=np.int64), interior)
    _require(len(interior) == INTERIOR_DIMENSION and len(trace) == TRACE_DIMENSION,
             "complete p4 trace/interior local positions differ")
    source["interior_positions"] = writer.array(role + "/positions/interior", interior, intern=True)
    source["trace_positions"] = writer.array(role + "/positions/trace", trace, intern=True)
    actual_cell_tags = setup["mesh_data"].cell_tags
    _local_int32(actual_cell_tags.indices, expected_cells)
    _local_int32(actual_cell_tags.values, 2**31)
    tags = _cell_tag_array(actual_cell_tags, expected_cells)
    mesh.topology.create_entity_permutations()
    permutations = mesh.topology.get_cell_permutation_info()
    coordinates_by_class, cell_metadata = {}, []
    for cell in range(expected_cells):
        # The inherited geometry helper uses int32 internally.  Admit its
        # complete wide input before entering it, rather than after conversion.
        geometry_dofs = _local_int32(mesh.geometry.dofmap[cell], len(mesh.geometry.x))
        index_map = space.dofmap.index_map
        local_dofs = _local_int32(space.dofmap.cell_dofs(cell), int(index_map.size_local) + int(index_map.num_ghosts))
        checked_integer_metadata([int(permutations[cell])], 2**30, maximum=2**32 - 1)
        canonical, widths = _canonical_axis_aligned_coordinates(
            mesh, cell, tolerance=1e-11, preserve_exact_geometry=True)
        key = ("actual_space", int(tags[cell]), *widths)
        if key in coordinates_by_class:
            _require(np.array_equal(coordinates_by_class[key], canonical),
                     "original helper raw class has inconsistent native geometry order")
        coordinates_by_class.setdefault(key, canonical)
        coordinates = np.asarray(mesh.geometry.x[geometry_dofs], dtype=np.float64)
        original_raw = np.asarray(index_map.local_to_global(local_dofs))
        _require(original_raw.dtype.kind in "iu", "wide original cell integers required")
        checked_integer_metadata([int(value) for value in original_raw], expected_rows, maximum=2**63 - 1)
        original = original_raw.astype(np.int64, copy=False)
        _require(len(original) == CELL_DIMENSION and len(np.unique(original)) == CELL_DIMENSION,
                 "complete original native cell row ordering invalid")
        cell_metadata.append((key, int(permutations[cell])))
        source["cells"].append({"cell_index": cell, "grid": list(_actual_grid_cell(coordinates, axes)),
                                "tag": int(tags[cell]), "widths": list(widths),
                                "cell_info": int(permutations[cell]),
                                "native_dofs": writer.array(role + f"/cell/{cell}/native_dofs", original),
                                "native_coordinates": writer.array(role + f"/cell/{cell}/native_coordinates", coordinates),
                                "raw_key": _json(key), "class_key": _json((*key[1:], int(permutations[cell])))})
    _gate(writer.gate, role + "_compile_original_curl_mass", workspace=64 * 1024**2,
          estimate_status="declared_existing_FFCx_compilation_allowance_not_measured")
    compiled = fem.form(bundle["volume_action"].bilinear_form)
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    _require(-1 in kernels or set(map(int, tags)).issubset(kernels), "original FFCx material cell kernel missing")
    _gate(writer.gate, role + "_complete_original_raw_tensor_cache",
          len(coordinates_by_class) * CELL_DIMENSION**2 * 16,
          3 * CELL_DIMENSION**2 * 16 + 16 * 1024**2,
          raw_class_count=len(coordinates_by_class), original_cell_count=expected_cells,
          raw_source="existing _global_raw_tensor_cache original complete curl+mass")
    raw_cache, raw_audit, seconds = _global_raw_tensor_cache(
        mesh.comm, coordinates_by_class, {"actual_space": (compiled, kernels, CELL_DIMENSION)})
    source["original_raw_cache_audit"] = _json(raw_audit)
    source["raw_kernel_seconds"] = float(seconds)
    source["full_form_signature"] = str(bundle["volume_action"].bilinear_form.signature())
    # Bind the exact compiled binary and its module-bound C, as the existing
    # primary surface qualification does, without searching for another kernel.
    from pathlib import Path
    module_path = Path(compiled.module.__file__).resolve()
    c_path = module_path.parent / (compiled.module.__name__ + ".c")
    _require(module_path.is_file() and c_path.is_file(), "actual original volume module-bound binary/C is missing")
    signature = compiled.module.ffi.string(compiled.ufcx_form.signature).decode("ascii")
    _require(signature in c_path.read_text(), "original volume module-bound C does not contain its loaded form signature")
    def file_digest(path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    source["loaded_original_volume_kernel"] = {"module_name": compiled.module.__name__,
        "module_path": str(module_path), "binary_sha256": file_digest(module_path),
        "module_bound_C_path": str(c_path), "module_bound_C_sha256": file_digest(c_path),
        "ufcx_form_signature": signature, "num_coefficients": int(compiled.ufcx_form.num_coefficients),
        "num_constants": int(compiled.ufcx_form.num_constants), "sum_duplicate_cell_integrals": True}
    source["tensor_source"] = "existing original FFCx multi-cell-integral curl+mass; exact geometry; original T A T^T"
    raw_refs, oriented_refs, orientation_refs = {}, {}, {}
    for index, key in enumerate(sorted(raw_cache)):
        tensor = raw_cache[key]
        _finite_array(tensor, shape=(CELL_DIMENSION, CELL_DIMENSION), kind="c")
        raw_refs[key] = writer.array(role + f"/raw_template/{index}", tensor, intern=True)
        source["raw_templates"].append({"key": _json(key), "tensor": raw_refs[key],
                                        "canonical_geometry": writer.array(role + f"/raw_template/{index}/geometry",
                                                                          coordinates_by_class[key], intern=True)})
    for cell, (raw_key, info) in enumerate(cell_metadata):
        oriented_key = (raw_key, info)
        if oriented_key not in oriented_refs:
            _gate(writer.gate, role + "_orient_complete_original_tensor", CELL_DIMENSION**2 * 16,
                  2 * CELL_DIMENSION**2 * 16, original_columns=CELL_DIMENSION)
            tensor = raw_cache[raw_key].copy()
            _orient_cell_tensor(space.element, tensor, np.asarray([info], dtype=np.uint32))
            reference = writer.array(role + f"/oriented_template/{len(oriented_refs)}", tensor, intern=True)
            if info not in orientation_refs:
                _gate(writer.gate, role + "_original_T_apply_complete_orientation_witness",
                      CELL_DIMENSION**2 * 16, CELL_DIMENSION**2 * 16)
                orientation = np.eye(CELL_DIMENSION, dtype=np.complex128)
                cell_info = np.asarray([info], dtype=np.uint32)
                # The first transformation in the inherited orientation helper.
                if hasattr(space.element, "space_dimension"):
                    space.element.T_apply(orientation.ravel(), cell_info, CELL_DIMENSION)
                else:
                    space.element.T_apply(orientation.ravel(), CELL_DIMENSION, info)
                orientation_refs[info] = writer.array(role + f"/orientation/{info}", orientation, intern=True)
                del orientation
            oriented_refs[oriented_key] = reference
            source["oriented_templates"].append({"raw_key": _json(raw_key), "cell_info": info,
                                                  "raw": raw_refs[raw_key], "tensor": reference,
                                                  "orientation": orientation_refs[info]})
            del tensor
        source["cells"][cell]["raw_tensor"] = raw_refs[raw_key]
        source["cells"][cell]["oriented_tensor"] = oriented_refs[oriented_key]
    del raw_cache, compiled, kernels, coordinates_by_class
    independent, expansion = _decoded_native(source, load_array)
    owners = _decoded_entities(source, load_array)
    for cell in source["cells"]:
        dofs = _read(cell["native_dofs"], load_array)
        support, cell_map = _cell_map(dofs, independent, expansion, owners, writer.gate,
                                      role + "_complete_cell_MPC_entity_map")
        cell["canonical_ids"] = writer.array(role + f"/cell/{cell['cell_index']}/canonical_ids", support, intern=True)
        cell["canonical_map"] = writer.array(role + f"/cell/{cell['cell_index']}/canonical_map", cell_map, intern=True)
        tensor = _read(cell["oriented_tensor"], load_array)
        _gate(writer.gate, role + "_complete_300_column_cell_congruence", len(support)**2 * 16,
              CELL_DIMENSION * len(support) * 32 + len(support)**2 * 32,
              all_original_columns=CELL_DIMENSION, all_canonical_columns=len(support))
        projected = cell_map.conj().T @ (tensor @ cell_map)
        cell["complete_canonical_contribution"] = writer.array(
            role + f"/cell/{cell['cell_index']}/canonical_contribution", projected, intern=True)
        del projected, tensor
        del support, cell_map
    source["complete_cell_coverage_digest"] = hashlib.sha256(_token(
        [(cell["cell_index"], cell["grid"], cell["native_dofs"]["numeric_sha256"],
          cell["oriented_tensor"]["numeric_sha256"], cell["canonical_map"]["numeric_sha256"])
         for cell in source["cells"]]).encode()).hexdigest()
    source["raw_class_count"] = len(raw_refs)
    source["oriented_class_count"] = len(oriented_refs)
    return source


def export_direct_volume_source(bundle, entities, *, allocation_gate, save_array, load_array,
                                role="changed_original", direct_profile="X", entity_config=None):
    """Export every actual original tensor/MPC map, including a notch source.

    This export alone is NOT a qualification result.  Changed source support
    must be compared with the regular source by the supervised workflow.
    """
    writer = _Writer(save_array, allocation_gate)
    return _export_source(bundle, entities, writer=writer, load_array=load_array,
                          role=role, metadata=_metadata(direct_profile), entity_config=entity_config)


def _save_csr(writer, name, matrix):
    from scipy import sparse
    _require(sparse.isspmatrix_csr(matrix), "original local CSR map required")
    return {"shape": list(matrix.shape), "data": writer.array(name + "/data", matrix.data, intern=True),
            "indices": writer.array(name + "/indices", matrix.indices, intern=True),
            "indptr": writer.array(name + "/indptr", matrix.indptr, intern=True)}


def _read_csr(record, load):
    from scipy import sparse
    data, indices, indptr = (_read(record[name], load) for name in ("data", "indices", "indptr"))
    _require(isinstance(record["shape"], (list, tuple)) and len(record["shape"]) == 2
             and all(type(value) is int and value > 0 for value in record["shape"]),
             "explicit positive integer CSR dimensions required before conversion")
    rows, columns = record["shape"]
    _require(indices.dtype.kind in "iu" and indptr.dtype.kind in "iu"
             and len(indptr) == rows + 1 and indptr[0] == 0 and indptr[-1] == len(data)
             and len(indices) == len(data) and np.all(np.diff(indptr) >= 0)
             and (not len(indices) or (indices.min() >= 0 and indices.max() < columns)),
             "saved CSR whole local map inventory fails")
    checked_integer_metadata([int(value) for value in indices], columns)
    checked_integer_metadata([int(value) for value in indptr], len(data) + 1)
    checked_integer_metadata([], rows)
    return sparse.csr_matrix((data, indices, indptr), shape=(rows, columns), copy=False)


def _export_condensation(condensed, source, provider, blocks, writer, role):
    """Bind inherited elimination and exact reduced iterator to original cells."""
    system = condensed.system
    _require(system.matrix is None and not condensed.destroyed
             and system.retained_local_schur_by_class is not None
             and provider.condensed is condensed, "actual action-only provider ownership differs")
    interior_positions = _read(source["interior_positions"], writer.load)
    trace_positions = _read(source["trace_positions"], writer.load)
    classes, cells, trace_expansion_rows = {}, [], {}
    inventory = tuple(condensed.complete_cell_inventory())
    _require(len(inventory) == source["cell_count"], "complete borrowed condensation cell inventory differs")
    for item in inventory:
        index, key = int(item["cell_index"]), item["class_key"]
        _require(0 <= index < len(source["cells"]), "borrowed cell index missing")
        original = source["cells"][index]
        native = _read(original["native_dofs"], writer.load)
        _require(_token(key) == _token(original["class_key"])
                 and np.array_equal(native[interior_positions], item["interior_original_rows"])
                 and np.array_equal(native[trace_positions], item["trace_original_rows"]),
                 "borrowed native order/class/interior/trace rows differ from original source")
        identity = item["full_tensor_identity"]
        _require(identity["raw_sha256"] == original["raw_tensor"]["numeric_sha256"]
                 and identity["oriented_sha256"] == original["oriented_tensor"]["numeric_sha256"]
                 and tuple(identity["shape"]) == (CELL_DIMENSION, CELL_DIMENSION),
                 "condensation did not eliminate this same complete original tensor")
        class_id = _token(key)
        if class_id not in classes:
            name = role + f"/elimination/{len(classes)}"
            classes[class_id] = {"class_key": _json(key), "original_tensor": original["oriented_tensor"],
                "recovery": writer.array(name + "/recovery", system.interior_from_trace_by_class[key], intern=True),
                "trace_rhs": writer.array(name + "/trace_rhs", system.trace_from_interior_rhs_by_class[key], intern=True),
                "schur": writer.array(name + "/schur", item["retained_schur"], intern=True),
                "rhs_projection": writer.array(name + "/rhs_projection", system.interior_rhs_projection_by_class[key], intern=True),
                "solution_embedding": writer.array(name + "/solution_embedding", system.interior_solution_embedding_by_class[key], intern=True),
                "residual_projection": writer.array(name + "/residual_projection", system.interior_residual_projection_by_class[key], intern=True)}
        cells.append({"cell_index": index, "class_id": class_id,
                      "interior_rows": writer.array(role + f"/elimination_cell/{index}/interiors", item["interior_original_rows"]),
                      "trace_rows": writer.array(role + f"/elimination_cell/{index}/traces", item["trace_original_rows"])})
        for row, (ids, coefficients) in zip(item["trace_original_rows"], item["trace_expansions"], strict=True):
            value = (tuple(map(int, ids)), tuple(map(complex, coefficients)))
            if int(row) in trace_expansion_rows:
                _require(trace_expansion_rows[int(row)] == value, "shared native trace expansion changed between cells")
            trace_expansion_rows[int(row)] = value
    offsets, original_rows, active_ids, values = [0], [], [], []
    for row, (ids, coefficients) in sorted(trace_expansion_rows.items()):
        original_rows.append(row)
        active_ids.extend(ids)
        values.extend(coefficients)
        offsets.append(len(active_ids))
    result = {"active_rows": int(system.active_rows), "port_rows": int(system.appended_rows),
              "active_original": writer.array(role + "/active_original", system.trace_constraints.owned_active_original_dofs),
              "expansion_original": writer.array(role + "/trace_expansion/original", np.asarray(original_rows, dtype=np.int64)),
              "expansion_offsets": writer.array(role + "/trace_expansion/offsets", np.asarray(offsets, dtype=np.int64)),
              "expansion_ids": writer.array(role + "/trace_expansion/ids", np.asarray(active_ids, dtype=np.int64)),
              "expansion_values": writer.array(role + "/trace_expansion/values", np.asarray(values, dtype=np.complex128)),
              "classes": list(classes.values()), "cells": cells, "contributions": [], "q_maps": [],
              "provider_blocks": [], "all_borrowed_cells_covered": len(cells)}
    carrier = condensed.action_bundle["dtn_action"].carrier
    result["port_H"] = writer.array(role + "/port_H", np.asarray([entry.normalization_h for entry in carrier.entries]))
    _require(condensed.action._Hhat is not None, "actual retained cached full Hhat required")
    result["retained_Hhat"] = writer.array(role + "/retained_Hhat", condensed.action._Hhat, intern=True)
    result["port_original_indices"] = writer.array(role + "/port_original_indices", condensed.global_mode_indices)
    result["port_n"] = writer.array(role + "/port_n", np.asarray([int(mode.n) for mode in condensed.action_bundle["modes"]], dtype=np.int64))
    result["global_q_indices"] = list(provider.coordinates.context.global_q_indices)
    from .dtn_boundary_plane_qualification import carrier_numeric_identity
    result["same_live_primary_carrier_identity"] = _json(carrier_numeric_identity(carrier))
    result["carrier_global_rows"] = int(carrier.global_rows)
    result["carrier_ownership_range"] = list(carrier.ownership_range)
    result["carrier_slaves"] = writer.array(role + "/carrier/slaves", carrier.slave_rows, intern=True)
    result["carrier_entries"] = []
    for index, entry in enumerate(carrier.entries):
        entry_record = {"port": index, "mode_key": _json(entry.mode_key), "mode_identity": _json(entry.mode_identity),
                        "H": float(entry.normalization_h)}
        for field in ("coupling_rows", "coupling_values", "projection_rows", "projection_values"):
            entry_record[field] = writer.array(role + f"/carrier/{index}/{field}", getattr(entry, field), intern=True)
        result["carrier_entries"].append(entry_record)
    result["port_cells"] = []
    # Raw blocks are borrowed from the existing original carrier adapter.
    # They make the complete port-elimination algebra independently checkable.
    for index, data in enumerate(condensed.action._cells):
        if not len(data.ports):
            continue
        port_cell = {"cell_index": index, "ports": writer.array(role + f"/port_cell/{index}/ports", data.ports)}
        for field in ("Bi", "Bt", "Di", "Dt", "Bhat", "Dhat", "XiB"):
            value = getattr(data, field)
            _require(value is not None, "cached original port elimination field missing")
            port_cell[field] = writer.array(role + f"/port_cell/{index}/{field}", value, intern=True)
        result["port_cells"].append(port_cell)
    for branch in (0, 1):
        matrix = provider.coordinates.q_map(branch)
        result["q_maps"].append(_save_csr(writer, role + f"/branch/{branch}/q_map", matrix))
        del matrix
    labels = set()
    for index, (rows, columns, values, label) in enumerate(condensed.iter_contributions(allocation_gate=writer.gate)):
        _require(str(label) not in labels, "duplicate actual reduced contribution label")
        labels.add(str(label))
        result["contributions"].append({"label": str(label),
            "rows": writer.array(role + f"/reduced_contribution/{index}/rows", rows, intern=True),
            "columns": writer.array(role + f"/reduced_contribution/{index}/columns", columns, intern=True),
            "values": writer.array(role + f"/reduced_contribution/{index}/values", values, intern=True)})
    _require({f"volume/cell/{i}" for i in range(source["cell_count"])}.issubset(labels)
             and "ports/H_original" in labels, "original reduced volume or H contribution omitted")
    for p in (0, 1):
        for q in (0, 1):
            block = blocks[(p, q)]
            _require(isinstance(block, Mapping) and "csr_prefix" in block,
                     "already-built complete provider CSR witness missing")
            result["provider_blocks"].append({"p": p, "q": q, **_json(block)})
    return result


def _check_source(source, *, load, gate, metadata):
    """Array-only complete coverage, native composition and tensor proof."""
    local = bool(source["local_two_cell"])
    expected_cells = metadata.local_cell_count if local else metadata.cell_count
    expected_rows = metadata.local_storage_rows if local else metadata.storage_rows
    ny = metadata.local_y_cells if local else metadata.ny
    axes = metadata.local_axes if local else metadata.global_axes
    if metadata.name == "Y":
        _require(_token(source["profile"]) == _token(metadata.identity()),
                 "saved Y source must retain the complete selected profile identity")
    _require(_token(source["axes"]) == _token(axes) and source["cell_count"] == expected_cells
             and source["native"]["full_rows"] == expected_rows
             and source["entities"]["ny"] == ny and len(source["cells"]) == expected_cells,
             "saved profile/source cardinalities differ")
    from pathlib import Path
    loaded = source["loaded_original_volume_kernel"]
    _require(loaded["num_coefficients"] == 0 and loaded["num_constants"] == 0
             and loaded["sum_duplicate_cell_integrals"] is True,
             "complete original compiled curl+mass kernel policy differs")
    for path_field, hash_field in (("module_path", "binary_sha256"),
                                  ("module_bound_C_path", "module_bound_C_sha256")):
        digest = hashlib.sha256()
        with Path(loaded[path_field]).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        _require(digest.hexdigest() == loaded[hash_field], "same actual loaded original volume binary/C changed")
    policy = source["original_raw_cache_audit"]["raw_tensor_policy_signatures"]["actual_space"]
    _require(policy["dimension"] == CELL_DIMENSION and policy["ufcx_form_signature"] == loaded["ufcx_form_signature"]
             and policy["dtype"] == "complex128", "complete raw tensor source differs from actual original FFCx kernel")
    _gate(gate, "independent_complete_native_controls", 16 * expected_rows * 8,
          16 * expected_rows * 8)
    independent, expansion = _decoded_native(source, load)
    owners = _decoded_entities(source, load)
    interior, trace = _read(source["interior_positions"], load), _read(source["trace_positions"], load)
    _require(len(interior) == INTERIOR_DIMENSION and len(trace) == TRACE_DIMENSION
             and np.array_equal(np.sort(np.concatenate((interior, trace))), np.arange(CELL_DIMENSION)),
             "saved all300 original trace/interior channel partition fails")
    # Check every unique original orientation against its raw FFCx tensor.
    orientation_errors = []
    for template in source["oriented_templates"]:
        raw, oriented, transform = (_read(template[name], load) for name in ("raw", "tensor", "orientation"))
        _finite_array(raw, shape=(CELL_DIMENSION, CELL_DIMENSION), kind="c")
        _finite_array(oriented, shape=(CELL_DIMENSION, CELL_DIMENSION), kind="c")
        _finite_array(transform, shape=(CELL_DIMENSION, CELL_DIMENSION), kind="c")
        _gate(gate, "independent_original_TATt_complete_columns", 2 * CELL_DIMENSION**2 * 16,
              3 * CELL_DIMENSION**2 * 16, all_original_columns=CELL_DIMENSION)
        reconstructed = transform @ raw @ transform.T
        error = _relative(reconstructed, oriented)
        _require(error <= LIMIT, "independent complete original T A T^T orientation failed")
        orientation_errors.append(error)
        del raw, oriented, transform, reconstructed
    seen_cells, seen_grid, seen_interiors = set(), set(), set()
    independent_set = set(map(int, independent))
    templates = {(_token(item["raw_key"]), int(item["cell_info"])): item for item in source["oriented_templates"]}
    raw_templates = {_token(item["key"]): item for item in source["raw_templates"]}
    map_errors, congruence_errors = [], []
    validated_congruences = set()
    for cell in source["cells"]:
        index = int(cell["cell_index"])
        _require(index not in seen_cells and 0 <= index < expected_cells, "missing/repeated actual cell")
        seen_cells.add(index)
        dofs, coordinates = _read(cell["native_dofs"], load), _read(cell["native_coordinates"], load)
        _require(dofs.dtype.kind in "iu" and len(dofs) == CELL_DIMENSION
                 and len(np.unique(dofs)) == CELL_DIMENSION and dofs.min() >= 0 and dofs.max() < expected_rows,
                 "saved original native full300-cell ordering invalid")
        _finite_array(coordinates, shape=(8, 3), kind="f")
        grid = _actual_grid_cell(coordinates, axes)
        _require(list(grid) == cell["grid"] and grid not in seen_grid
                 and np.array_equal(coordinates.max(axis=0) - coordinates.min(axis=0), np.asarray(cell["widths"])),
                 "actual saved material/metric/native-grid cell witness fails")
        seen_grid.add(grid)
        _require(cell["raw_key"][1:] == [cell["tag"], *cell["widths"]]
                 and cell["class_key"] == [cell["tag"], *cell["widths"], cell["cell_info"]],
                 "actual cell raw/orientation key differs from complete metric/tag")
        template = templates[(_token(cell["raw_key"]), int(cell["cell_info"]))]
        _require(cell["oriented_tensor"] == template["tensor"] and cell["raw_tensor"] == template["raw"],
                 "actual cell does not reference the raw/oriented template for its complete state")
        raw_template = raw_templates[_token(cell["raw_key"])]
        _require(cell["raw_tensor"] == raw_template["tensor"], "actual cell raw source class changed")
        canonical_geometry = _read(raw_template["canonical_geometry"], load).reshape(8, 3)
        _require(np.max(np.abs(canonical_geometry - (coordinates - coordinates.min(axis=0)))) <= 1e-11,
                 "actual native geometry order differs from its complete original FFCx raw class")
        for row in dofs[interior]:
            _require(int(row) not in seen_interiors and int(row) in independent_set,
                     "interior channel is shared/eliminated/missing")
            seen_interiors.add(int(row))
        support, rebuilt = _cell_map(dofs, independent, expansion, owners, gate,
                                     "independent_actual_full300_MPC_entity_composition")
        saved_support, saved_map = _read(cell["canonical_ids"], load), _read(cell["canonical_map"], load)
        _require(np.array_equal(support, saved_support), "full canonical cell support differs; no zero-channel omission allowed")
        map_error = _relative(rebuilt, saved_map)
        _require(map_error <= LIMIT, "independent finalized MPC/entity complete cell map failed")
        map_errors.append(map_error)
        congruence_key = (cell["oriented_tensor"]["numeric_sha256"], cell["canonical_map"]["numeric_sha256"],
                          cell["complete_canonical_contribution"]["numeric_sha256"])
        if congruence_key not in validated_congruences:
            tensor = _read(cell["oriented_tensor"], load)
            projected = _read(cell["complete_canonical_contribution"], load)
            _gate(gate, "independent_complete_cell_all_column_congruence", len(support)**2 * 16,
                  CELL_DIMENSION * len(support) * 32 + len(support)**2 * 32,
                  original_columns=CELL_DIMENSION, actual_complete_columns=len(support))
            recomputed = rebuilt.conj().T @ (tensor @ rebuilt)
            congruence_error = _relative(recomputed, projected)
            _require(congruence_error <= LIMIT, "independent complete cell tensor projection failed")
            congruence_errors.append(congruence_error)
            validated_congruences.add(congruence_key)
            del tensor, projected, recomputed
        del rebuilt, saved_map, dofs, coordinates
    _require(seen_cells == set(range(expected_cells))
             and seen_grid == {(ix, iy, iz) for ix in range(metadata.nx) for iy in range(ny) for iz in range(metadata.nz)}
             and len(seen_interiors) == expected_cells * INTERIOR_DIMENSION,
             "complete actual cell/grid/interior coverage is not exhaustive")
    # Actual entity incidence connects controls to independently saved native
    # cell ordering and geometry, rather than just to a template label.
    by_index = {int(cell["cell_index"]): cell for cell in source["cells"]}
    for record in source["entities"]["records"]:
        state = record["actual_state"]
        cell = by_index[int(state["cell"])]
        native = _read(cell["native_dofs"], load)
        rows = _read(record["rows"], load)
        positions = np.asarray(state["positions"], dtype=np.int64)
        _require(np.array_equal(native[positions], independent[rows])
                 and int(state["cell_info"]) == int(cell["cell_info"]),
                 "actual saved entity incidence/native order/orientation differs")
        native_coordinates = _read(cell["native_coordinates"], load)
        for point in state["native_coordinates"]:
            _require(np.any(np.all(np.abs(native_coordinates - np.asarray(point)) <= 1e-11, axis=1)),
                     "actual entity coordinates are outside the recorded source cell")
    return {"cell_count": expected_cells, "full300_columns_per_cell": CELL_DIMENSION,
            "independent_rows": len(independent), "all_interior_rows": len(seen_interiors),
            "entity_record_count": len(source["entities"]["records"]),
            "orientation_maximum": max(orientation_errors, default=0),
            "map_maximum": max(map_errors, default=0),
            "complete_congruence_maximum": max(congruence_errors, default=0),
            "complete_unique_congruence_count": len(validated_congruences),
            "complete_actual_coverage": True}


def _orbit_pair_sums(source, cells, etas, *, load, gate, label):
    """Sum all original contributions in one actual y translation orbit."""
    width, ny = int(source["entities"]["width"]), int(source["entities"]["ny"])
    support = sorted({int(canonical) % width for cell in cells
                      for canonical in _read(cell["canonical_ids"], load)})
    _require(0 < len(support) <= MAX_CELL_SUPPORT, "complete orbit support exceeds bounded proof allocation")
    count = len(etas)
    _gate(gate, label, count**2 * len(support)**2 * 16,
          5 * len(support)**2 * 16 + len(support) * 128,
          all_q_pairs=count**2, complete_columns=len(support), actual_y_cells=len(cells))
    sums = {(p, q): np.zeros((len(support), len(support)), dtype=np.complex128)
            for p in range(count) for q in range(count)}
    position = {value: index for index, value in enumerate(support)}
    for cell in cells:
        canonical = _read(cell["canonical_ids"], load)
        values = _read(cell["complete_canonical_contribution"], load)
        _require(values.shape == (len(canonical), len(canonical)), "complete saved contribution shape differs")
        phase = [eta ** (canonical // width) / np.sqrt(ny) for eta in etas]
        target = np.asarray([position[int(value) % width] for value in canonical], dtype=np.int64)
        # Different native y-plane channels may collapse to one modal slot;
        # scatter-add keeps every such entry, including exact zeros.
        for p in range(count):
            for q in range(count):
                projected = np.conjugate(phase[p])[:, None] * values * phase[q][None, :]
                for row, global_row in enumerate(target):
                    np.add.at(sums[(p, q)][int(global_row)], target, projected[row])
        del values, canonical
    return support, sums


def _check_orbits(receipt, *, load, gate, metadata):
    sources = [receipt["global_source"], *receipt["local_sources"]]
    global_eta = [_uncomplex(value) for value in receipt["global_eta"]]
    ny, replication_count = metadata.ny, metadata.replication_count
    _require(len(sources) == replication_count + 1 and len(global_eta) == ny,
             "every original q eigenphase and local twist source required")
    for q, eta in enumerate(global_eta):
        _require(abs(abs(eta) - 1) <= 1e-12 and abs(eta**ny - _uncomplex(receipt["global_phase_y"])) <= 1e-12
                 and abs(eta / global_eta[0] - np.exp(2j * np.pi * q / ny)) <= 1e-12,
                 "original all-q/full-cycle Fourier covariance controls fail")
    grouped = [{(ix, iz): [cell for cell in source["cells"] if cell["grid"][0] == ix and cell["grid"][2] == iz]
                for ix in range(metadata.nx) for iz in range(metadata.nz)} for source in sources]
    results = []
    for ix in range(metadata.nx):
        for iz in range(metadata.nz):
            actual = grouped[0][(ix, iz)]
            _require({cell["grid"][1] for cell in actual} == set(range(ny)), "global orbit omits an actual translated cell")
            support, global_sums = _orbit_pair_sums(sources[0], actual, global_eta,
                load=load, gate=gate, label=f"original_all{ny}x{ny}_q_actual_cell_orbit")
            norms = {q: float(np.linalg.norm(global_sums[(q, q)])) for q in range(ny)}
            item = {"grid_xz": [ix, iz], "complete_columns": len(support), "global_cell_ids": [c["cell_index"] for c in actual],
                    "all_global_q_pairs": [], "local_twists": []}
            for p in range(ny):
                for q in range(ny):
                    norm = float(np.linalg.norm(global_sums[(p, q)]))
                    relative = (max(norm / max(norms[p], np.finfo(float).tiny),
                                    norm / max(norms[q], np.finfo(float).tiny)) if p != q else 0.0)
                    _require(np.isfinite(relative) and relative <= LIMIT,
                             "complete actual global off-q/cross-twist contribution covariance failed")
                    item["all_global_q_pairs"].append({"p": p, "q": q, "norm": norm, "off_q_relative": relative,
                                                      "cross_twist": p % replication_count != q % replication_count})
            for b in range(replication_count):
                local_cells = grouped[b + 1][(ix, iz)]
                _require({cell["grid"][1] for cell in local_cells} == {0, 1}, "local orbit omits either actual cell")
                # Every actual original cell has a translated local counterpart,
                # with independently retained material and exact native widths.
                local_by_y = {cell["grid"][1]: cell for cell in local_cells}
                for global_cell in actual:
                    local_cell = local_by_y[global_cell["grid"][1] % 2]
                    _require(global_cell["tag"] == local_cell["tag"]
                             and np.max(np.abs(np.asarray(global_cell["widths"]) - np.asarray(local_cell["widths"]))
                                        / np.asarray(local_cell["widths"])) <= 1e-12,
                             "actual translated original/local material or metric differs")
                local_support, local_sums = _orbit_pair_sums(sources[b + 1], local_cells,
                    [global_eta[b], global_eta[b + replication_count]], load=load, gate=gate,
                    label="local_all2x2_branch_actual_cell_orbit")
                _require(local_support == support, "local/full all-polynomial orbit channel support differs")
                pairs = []
                for p in (0, 1):
                    for q in (0, 1):
                        global_p, global_q = b + replication_count * p, b + replication_count * q
                        error = _relative(local_sums[(p, q)], global_sums[(global_p, global_q)])
                        if p == q:
                            _require(error <= LIMIT, "complete original/global versus local diagonal contribution sum differs")
                        scale = min(norms[global_p], norms[global_q])
                        off_relative = float(np.linalg.norm(local_sums[(p, q)])) / max(scale, np.finfo(float).tiny) if p != q else 0.0
                        _require(off_relative <= LIMIT, "complete local off-branch cell covariance failed")
                        pairs.append({"p": p, "q": q, "global_p": global_p, "global_q": global_q,
                                      "diagonal_relative": error if p == q else None, "offbranch_relative": off_relative})
                item["local_twists"].append({"b": b, "cell_ids": [c["cell_index"] for c in local_cells], "all2x2_pairs": pairs})
                del local_sums
            results.append(item)
            del global_sums
    _require(len(results) == metadata.nx * metadata.nz, "not all actual x-z translation groups were audited")
    return results


def _check_condensation(source, record, *, load, gate, global_eta, twist):
    """Recompute inherited elimination and the complete native iterator blocks."""
    from scipy import sparse
    independent, original_expansion = _decoded_native(source, load)
    owners = _decoded_entities(source, load)
    ni = _read(source["interior_positions"], load)
    nt = _read(source["trace_positions"], load)
    active = _read(record["active_original"], load)
    _require(active.dtype.kind in "iu" and len(active) == record["active_rows"]
             and len(np.unique(active)) == len(active) and np.isin(active, independent).all(),
             "complete inherited active trace partition fails")
    originals = _read(record["expansion_original"], load)
    offsets = _read(record["expansion_offsets"], load)
    ids = _read(record["expansion_ids"], load)
    coefficients = _read(record["expansion_values"], load)
    _require(len(offsets) == len(originals) + 1 and offsets[0] == 0 and offsets[-1] == len(ids)
             and len(ids) == len(coefficients) and np.all(np.diff(offsets) > 0)
             and (not len(ids) or (ids.min() >= 0 and ids.max() < len(active))),
             "complete inherited trace expansion controls fail")
    active_position = {int(original): index for index, original in enumerate(active)}
    expansions = {}
    for row, original in enumerate(originals):
        first, last = int(offsets[row]), int(offsets[row + 1])
        actual = tuple((int(index), complex(value)) for index, value
                       in zip(ids[first:last], coefficients[first:last], strict=True))
        expected = tuple((active_position[master], value) for master, value in original_expansion[int(original)])
        _require(actual == expected, "inherited trace expansion is not the actual finalized original MPC")
        expansions[int(original)] = actual
    class_by_key, maximum = {}, 0.0
    for cls in record["classes"]:
        tensor = _read(cls["original_tensor"], load)
        recovery, projection, schur = (_read(cls[name], load) for name in ("recovery", "trace_rhs", "schur"))
        _gate(gate, "independent_original_complete_inherited_elimination", 4 * CELL_DIMENSION**2 * 16,
              4 * CELL_DIMENSION**2 * 16, no_factor_or_solve=True)
        Aii, Ait, Ati, Att = (tensor[np.ix_(left, right)] for left, right in ((ni, ni), (ni, nt), (nt, ni), (nt, nt)))
        errors = [_relative(Aii @ recovery, -Ait), _relative(projection @ Aii, -Ati),
                  _relative(Att + Ati @ recovery, schur)]
        for field in ("rhs_projection", "solution_embedding", "residual_projection"):
            value = _read(cls[field], load)
            _require(value.shape == (INTERIOR_DIMENSION, INTERIOR_DIMENSION), "inherited interior identity shape differs")
            errors.append(_relative(value, np.eye(INTERIOR_DIMENSION)))
        _require(all(np.isfinite(error) and error <= LIMIT for error in errors),
                 "complete original tensor/inherited condensation/recovery algebra differs")
        maximum = max(maximum, *errors)
        class_by_key[_token(cls["class_key"])] = cls
        del tensor, recovery, projection, schur, Aii, Ait, Ati, Att
    source_by_index = {int(cell["cell_index"]): cell for cell in source["cells"]}
    contribution_by_label = {item["label"]: item for item in record["contributions"]}
    _require(len(contribution_by_label) == len(record["contributions"]), "duplicate reduced contribution label")
    checked_cells, cell_maps = set(), {}
    for cell in record["cells"]:
        index = int(cell["cell_index"])
        _require(index not in checked_cells and index in source_by_index, "missing/duplicated inherited cell")
        checked_cells.add(index)
        original = source_by_index[index]
        dofs = _read(original["native_dofs"], load)
        interiors, traces = _read(cell["interior_rows"], load), _read(cell["trace_rows"], load)
        _require(np.array_equal(interiors, dofs[ni]) and np.array_equal(traces, dofs[nt])
                 and cell["class_id"] == _token(original["class_key"]), "inherited native ordered cell partition differs")
        active_ids = sorted({index for trace_row in traces for index, _ in expansions[int(trace_row)]})
        _gate(gate, "independent_complete_native_trace_expansion", len(traces) * len(active_ids) * 16,
              len(traces) * len(active_ids) * 16)
        expansion = np.zeros((len(traces), len(active_ids)), dtype=np.complex128)
        position = {index: column for column, index in enumerate(active_ids)}
        for row, trace_row in enumerate(traces):
            for index_active, value in expansions[int(trace_row)]:
                expansion[row, position[index_active]] += value
        cls = class_by_key[cell["class_id"]]
        schur = _read(cls["schur"], load)
        native_schur = expansion.conj().T @ schur @ expansion
        item = contribution_by_label[f"volume/cell/{index}"]
        _require(np.array_equal(_read(item["rows"], load), active_ids)
                 and np.array_equal(_read(item["columns"], load), active_ids)
                 and _relative(native_schur, _read(item["values"], load)) <= LIMIT,
                 "actual reduced iterator volume contribution differs from original complete tensor")
        cell_maps[index] = (np.asarray(active_ids, dtype=np.int64), expansion, cls)
        # Do not retain dense maps from every cell: port cells are rebuilt
        # below, and only descriptor metadata survives this iteration.
        del cell_maps[index], expansion, native_schur, schur
    _require(checked_cells == set(range(source["cell_count"])), "not every inherited cell was independently checked")
    # Bind every cached raw port block and every direct trace term to the same
    # measured primary carrier, with no assumption that interior support is zero.
    H = _read(record["port_H"], load)
    _require(record["carrier_global_rows"] == source["native"]["full_rows"]
             and record["carrier_ownership_range"] == [0, source["native"]["full_rows"]]
             and np.array_equal(np.sort(_read(record["carrier_slaves"], load)),
                                _read(source["native"]["slaves"], load)),
             "actual primary carrier native ownership/MPC controls differ")
    interior_location = {}
    for index, source_cell in source_by_index.items():
        native = _read(source_cell["native_dofs"], load)
        for local_row, original in enumerate(native[ni]):
            _require(int(original) not in interior_location, "carrier interior owner duplicated")
            interior_location[int(original)] = (index, local_row)
    expected_internal, direct, expected_labels = {}, {}, {"ports/H_original"}
    expected_labels.update(f"volume/cell/{index}" for index in range(source["cell_count"]))
    _require(len(record["carrier_entries"]) == len(H), "complete same-live carrier mode inventory missing")
    from .fullspace_dtn_action import _canonical_json_bytes
    from .dtn_boundary_phase_gauge import _array_signature
    carrier_digest = hashlib.sha256()
    carrier_digest.update(_canonical_json_bytes({"schema": "task40extra.live-boundary-carrier-digest.v1",
        "global_rows": record["carrier_global_rows"], "ownership_range": tuple(record["carrier_ownership_range"]),
        "mode_count": len(H), "slave_rows": _array_signature(_read(record["carrier_slaves"], load))}))
    stored_entry_count, partitioned_entry_count = 0, 0
    for port, entry in enumerate(record["carrier_entries"]):
        _require(entry["port"] == port and float(entry["H"]) == float(H[port]) and H[port] > 0,
                 "complete original primary H/mode order changed")
        controls = {field: _read(entry[field], load) for field in (
            "coupling_rows", "coupling_values", "projection_rows", "projection_values")}
        carrier_digest.update(_canonical_json_bytes({"index": port, "key": entry["mode_key"], "H": entry["H"],
            **{field: _array_signature(value) for field, value in controls.items()}}))
        for side, row_field, value_field, label_prefix in (
            ("B", "coupling_rows", "coupling_values", "direct/C/port/"),
            ("D", "projection_rows", "projection_values", "direct/-D/port/")):
            rows, values = controls[row_field], controls[value_field]
            _require(rows.ndim == 1 and rows.dtype.kind in "iu" and values.shape == rows.shape,
                     "complete original primary carrier row/value controls invalid")
            checked_integer_metadata([int(value) for value in rows], source["native"]["full_rows"])
            stored_entry_count += len(rows)
            direct_rows, direct_values = [], []
            for original, value in zip(rows, values, strict=True):
                original = int(original)
                if original in interior_location:
                    cell_index, local_row = interior_location[original]
                    target = expected_internal.setdefault(cell_index, {}).setdefault(port, {"B": {}, "D": {}})[side]
                    target[local_row] = target.get(local_row, 0j) + complex(value)
                else:
                    _require(original in active_position, "primary carrier touches slave/unknown native trace row")
                    direct_rows.append(active_position[original])
                    direct_values.append(complex(value))
                partitioned_entry_count += 1
            if direct_rows:
                label = label_prefix + str(port)
                expected_labels.add(label)
                direct[label] = (direct_rows, direct_values, port, side)
    _require(stored_entry_count == partitioned_entry_count
             and carrier_digest.hexdigest() == record["same_live_primary_carrier_identity"]["carrier_numeric_sha256"],
             "saved primary carrier numeric identity or complete entry partition differs")
    _require({int(cell["cell_index"]) for cell in record["port_cells"]} == set(expected_internal),
             "actual carrier interior-support cells missing or invented")
    port_ids = np.arange(int(record["active_rows"]), int(record["active_rows"]) + len(H), dtype=np.int64)
    original_h = contribution_by_label["ports/H_original"]
    _gate(gate, "independent_actual_primary_full_H_and_cached_Hhat", 3 * len(H)**2 * 16,
          3 * len(H)**2 * 16)
    reconstructed_Hhat = np.diag(H.astype(np.complex128))
    _require(np.array_equal(_read(original_h["rows"], load), port_ids)
             and np.array_equal(_read(original_h["columns"], load), port_ids)
             and np.array_equal(_read(original_h["values"], load), reconstructed_Hhat),
             "ports/H_original is not complete diag(actual positive H)")
    for label, (direct_rows, direct_values, port, side) in direct.items():
        item = contribution_by_label[label]
        if side == "B":
            expected_rows, expected_columns = direct_rows, [int(record["active_rows"]) + port]
            expected_values = np.asarray(direct_values, dtype=np.complex128).reshape(-1, 1)
        else:
            expected_rows, expected_columns = [int(record["active_rows"]) + port], direct_rows
            expected_values = -np.asarray(direct_values, dtype=np.complex128).reshape(1, -1)
        _require(np.array_equal(_read(item["rows"], load), expected_rows)
                 and np.array_equal(_read(item["columns"], load), expected_columns)
                 and np.array_equal(_read(item["values"], load), expected_values),
                 "complete original direct C/-D contribution differs from primary carrier")
    for port_cell in record["port_cells"]:
        index = int(port_cell["cell_index"])
        original = source_by_index[index]
        dofs = _read(original["native_dofs"], load)
        traces = dofs[nt]
        active_ids = sorted({index for row in traces for index, _ in expansions[int(row)]})
        _gate(gate, "independent_actual_port_cell_elimination", 8 * CELL_DIMENSION**2 * 16,
              8 * CELL_DIMENSION**2 * 16)
        expansion = np.zeros((TRACE_DIMENSION, len(active_ids)), dtype=np.complex128)
        position = {value: column for column, value in enumerate(active_ids)}
        for row, original_row in enumerate(traces):
            for active_row, value in expansions[int(original_row)]:
                expansion[row, position[active_row]] += value
        cls = class_by_key[_token(original["class_key"])]
        recovery, rhs = _read(cls["recovery"], load), _read(cls["trace_rhs"], load)
        tensor = _read(cls["original_tensor"], load)
        Bi, Bt, Di, Dt, Bhat, Dhat, XiB = (_read(port_cell[field], load)
                                          for field in ("Bi", "Bt", "Di", "Dt", "Bhat", "Dhat", "XiB"))
        ports = _read(port_cell["ports"], load)
        expected_ports = sorted(expected_internal[index])
        _require(np.array_equal(ports, expected_ports) and Bi.shape == (INTERIOR_DIMENSION, len(ports))
                 and Di.shape == (len(ports), INTERIOR_DIMENSION) and np.all(Bt == 0) and np.all(Dt == 0),
                 "complete original carrier cell port order/raw Bt/Dt differs")
        expected_Bi = np.zeros_like(Bi)
        expected_Di = np.zeros_like(Di)
        for port_column, port in enumerate(expected_ports):
            for local_row, value in expected_internal[index][port]["B"].items():
                expected_Bi[local_row, port_column] = value
            for local_row, value in expected_internal[index][port]["D"].items():
                expected_Di[port_column, local_row] = value
        _require(np.array_equal(Bi, expected_Bi) and np.array_equal(Di, expected_Di),
                 "complete actual primary carrier Bi/Di ownership/values differ")
        errors = [_relative(tensor[np.ix_(ni, ni)] @ XiB, Bi), _relative(Bt + rhs @ Bi, Bhat),
                  _relative(Dt + Di @ recovery, Dhat)]
        _require(all(value <= LIMIT for value in errors), "complete original carrier interior elimination differs")
        port_ids = int(record["active_rows"]) + ports
        for label, rows, columns, values in (
            (f"cell/C_hat/{index}", active_ids, port_ids, expansion.conj().T @ Bhat),
            (f"cell/-D_hat/{index}", port_ids, active_ids, -Dhat @ expansion),
            (f"cell/Hhat_correction/{index}", port_ids, port_ids, Di @ XiB)):
            item = contribution_by_label[label]
            expected_labels.add(label)
            _require(np.array_equal(_read(item["rows"], load), rows)
                     and np.array_equal(_read(item["columns"], load), columns)
                     and _relative(values, _read(item["values"], load)) <= LIMIT,
                     "complete exact reduced port contribution has changed sign/order/algebra")
        reconstructed_Hhat[np.ix_(ports, ports)] += Di @ XiB
        maximum = max(maximum, *errors)
        del expansion, Bi, Bt, Di, Dt, Bhat, Dhat, XiB, tensor, recovery, rhs
    _require(set(contribution_by_label) == expected_labels,
             "exact native contribution label cover has missing/invented/double-counted terms")
    _require(_relative(reconstructed_Hhat, _read(record["retained_Hhat"], load)) <= LIMIT,
             "actual retained full cached Hhat differs from diag(primary H)+all Di*XiB including offdiagonals")
    del reconstructed_Hhat
    # Reconstruct complete FE and alias columns of each local branch map from
    # the actual shared entity coefficients, not the saved q_map values.
    trace_slots = sorted({int(record_entity["first"]) + j for record_entity in source["entities"]["records"]
                          if record_entity["orbit"] == 0 and record_entity["actual_state"]["dimension"] < 3
                          for j in range(int(record_entity["size"]))})
    metadata = _metadata(source["profile"]["name"])
    _require(len(trace_slots) == metadata.trace_rows_per_q, "complete p4 direct trace slots omitted")
    trace_slot_position = {value: index for index, value in enumerate(trace_slots)}
    independent_position = {int(original): position for position, original in enumerate(independent)}
    H, mode_n = _read(record["port_H"], load), _read(record["port_n"], load)
    _require(len(H) == record["port_rows"] and np.isfinite(H).all() and np.all(H > 0),
             "actual original positive H inventory differs")
    if metadata.name == "Y":
        _require(type(twist) is int and twist in range(metadata.replication_count)
                 and tuple(record["global_q_indices"]) == (twist, twist + metadata.replication_count)
                 and len(record["q_maps"]) == metadata.local_y_cells
                 and len(mode_n) == len(H) == metadata.sector_port_counts[twist]
                 and mode_n.dtype.kind in "iu"
                 and all((int(n) - twist) % metadata.replication_count == 0 for n in mode_n),
                 "complete Y sector/q/physical alias inventory differs")
    qmap_errors = []
    for branch in (0, 1):
        qglobal = twist + metadata.replication_count * branch
        _require(record["global_q_indices"][branch] == qglobal, "local branch/global q key changed")
        qmap = _read_csr(record["q_maps"][branch], load)
        aliases = np.flatnonzero(mode_n % metadata.ny == qglobal)
        _require(len(aliases) == metadata.q_port_counts[qglobal], "complete physical aliases differ")
        rows, columns, values = [], [], []
        for active_row, original in enumerate(active):
            transform, entity_row, canonical = owners[independent_position[int(original)]]
            for channel, canonical_id in enumerate(canonical):
                orbit, slot = divmod(canonical_id, source["entities"]["width"])
                _require(slot in trace_slot_position, "trace map accidentally reaches an interior slot")
                value = transform[entity_row, channel] * global_eta[qglobal]**orbit / np.sqrt(2)
                if value != 0:
                    rows.append(active_row)
                    columns.append(trace_slot_position[slot])
                    values.append(value)
        for alias_column, alias in enumerate(aliases):
            rows.append(int(record["active_rows"]) + int(alias))
            columns.append(len(trace_slots) + alias_column)
            values.append(1 / np.sqrt(H[int(alias)]))
        shape = (int(record["active_rows"]) + len(H), len(trace_slots) + len(aliases))
        _gate(gate, "independent_complete_local_q_map", len(values) * 48,
              len(values) * 64 + (shape[0] + 1) * 8)
        checked_integer_metadata([int(value) for value in rows], shape[0])
        checked_integer_metadata([int(value) for value in columns], shape[1])
        expected_map = sparse.coo_matrix((values, (rows, columns)), shape=shape).tocsr()
        _require(qmap.shape == shape, "complete local q map dimensions differ")
        error = float(sparse.linalg.norm(qmap - expected_map) / max(sparse.linalg.norm(expected_map), np.finfo(float).tiny))
        _require(error <= LIMIT, "complete actual native/primal/alias q map differs")
        qmap_errors.append(error)
        del qmap, expected_map
    return {"every_actual_cell": len(checked_cells), "inherited_algebra_maximum": maximum,
            "complete_native_qmap_maximum": max(qmap_errors), "numeric_factor_calls": 0,
            "complete_primary_carrier_entries_partitioned_once": partitioned_entry_count,
            "exact_native_contribution_label_count": len(expected_labels),
            "retained_full_Hhat_recomputed": True}


def _check_provider_block_norms(results):
    """Gate zero offbranches on both diagonal operator scales, never residue.

    Tiny cancellation residues do not have a stable self-relative accuracy.
    Both independent reconstructions and their difference must satisfy the
    unchanged operator tolerance. This is not an inverse-error estimate or
    relative-accuracy claim for individual small volume/port entries.
    """
    import math
    _require(len(results) == 4 and {(item["p"], item["q"]) for item in results}
             == {(0, 0), (0, 1), (1, 0), (1, 1)},
             "existing provider did not supply every2x2 block")
    diagonal_scales = {}
    for item in results:
        norms = [item[name] for name in ("norm", "reference_norm", "difference_norm",
                 "absolute_max_difference", "absolute_max_reference", "absolute_max_independent")]
        _require(all(math.isfinite(value) and value >= 0 for value in norms),
                 "complete provider block norm diagnostics must be finite and nonnegative")
        reference_norm = item["reference_norm"]
        item["full_column_difference"] = (item["difference_norm"] / reference_norm
            if reference_norm > 0 else (0.0 if item["difference_norm"] == 0 else None))
        if item["p"] == item["q"]:
            _require(reference_norm > 0 and item["norm"] > 0,
                     "zero diagonal operator cannot supply an offbranch scale")
            diagonal_scales[item["q"]] = min(reference_norm, item["norm"])
            _require(item["full_column_difference"] <= LIMIT,
                     "complete original diagonal contribution sum differs from provider block")
    for item in results:
        if item["p"] == item["q"]:
            continue
        comparisons = []
        for branch in (item["p"], item["q"]):
            scale = diagonal_scales[branch]
            comparisons.append({"diagonal_branch": branch, "diagonal_scale": scale,
                "difference_relative": item["difference_norm"] / scale,
                "reference_leakage_relative": item["reference_norm"] / scale,
                "independent_leakage_relative": item["norm"] / scale})
        item["both_diagonal_operation_scales"] = comparisons
        item["operation_scaled_difference"] = max(row["difference_relative"] for row in comparisons)
        item["reference_offbranch_relative"] = max(row["reference_leakage_relative"] for row in comparisons)
        item["offbranch_relative"] = max(row["independent_leakage_relative"] for row in comparisons)
        _require(max(item["operation_scaled_difference"], item["reference_offbranch_relative"],
                     item["offbranch_relative"]) <= LIMIT,
                 "complete original augmented local offbranch difference or leakage failed")
    # A collection of per-block bounds alone need not give the same whole
    # operator bound. Reuse the complete block norms without a global matrix.
    whole_difference = math.hypot(*(item["difference_norm"] for item in results))
    whole_reference = math.hypot(*(item["reference_norm"] for item in results))
    _require(math.isfinite(whole_difference) and math.isfinite(whole_reference) and whole_reference > 0,
             "complete original2x2 aggregate norms must be finite with positive reference")
    whole_relative = whole_difference / whole_reference
    _require(math.isfinite(whole_relative) and whole_relative <= LIMIT,
             "complete original2x2 Frobenius difference failed")
    for item in results:
        item["whole_2x2_frobenius_relative_difference"] = whole_relative
    return results


def _check_provider_blocks(record, *, load, load_csr, gate):
    """Independently project every saved native contribution, all2x2 columns."""
    from scipy import sparse
    from .y_orbit_sparse_reference import integer_admission, csr_audit
    qmaps = [_read_csr(item, load) for item in record["q_maps"]]
    results = []
    for block_record in record["provider_blocks"]:
        p, q = int(block_record["p"]), int(block_record["q"])
        reference = load_csr(block_record["csr_prefix"], tuple(block_record["shape"]))
        _require(sparse.isspmatrix_csr(reference), "verified already-built provider CSR required")
        csr_audit(reference, petsc_index_dtype=reference.indices.dtype)
        shape = (qmaps[p].shape[1], qmaps[q].shape[1])
        _require(reference.shape == shape, "provider block complete branch shape differs")
        _gate(gate, "independent_saved_provider_block_difference", workspace=3 * (
            reference.data.nbytes + reference.indices.nbytes + reference.indptr.nbytes))
        result = sparse.csr_matrix(shape, dtype=np.complex128)
        for item in record["contributions"]:
            rows, columns, values = (_read(item[name], load) for name in ("rows", "columns", "values"))
            _require(rows.dtype.kind in "iu" and columns.dtype.kind in "iu"
                     and values.shape == (len(rows), len(columns))
                     and len(np.unique(rows)) == len(rows) and len(np.unique(columns)) == len(columns),
                     "complete original reduced contribution controls invalid")
            checked_integer_metadata([int(value) for value in rows], qmaps[p].shape[0])
            checked_integer_metadata([int(value) for value in columns], qmaps[q].shape[0])
            left, right = qmaps[p][rows, :].tocsr(), qmaps[q][columns, :].tocsr()
            support_p, support_q = np.unique(left.indices), np.unique(right.indices)
            if not len(support_p) or not len(support_q):
                continue
            entries = len(support_p) * len(support_q)
            integer_admission(shape, int(result.nnz) + entries, index_dtype=reference.indices.dtype)
            dense_count = len(rows) * len(support_p) + len(columns) * len(support_q) + len(support_p) * len(columns) + entries
            _gate(gate, "independent_every_actual_reduced_contribution_full_columns", dense_count * 16,
                  entries * 48 + 3 * (result.data.nbytes + result.indices.nbytes + result.indptr.nbytes))
            l, r = left[:, support_p].toarray(), right[:, support_q].toarray()
            projected = l.conj().T @ (values @ r)
            i, j = np.nonzero(projected)
            term = sparse.coo_matrix((projected[i, j], (support_p[i], support_q[j])), shape=shape).tocsr()
            result = (result + term).tocsr()
            del l, r, projected, term, left, right, values
        difference = result - reference
        norm = float(sparse.linalg.norm(result))
        results.append({"p": p, "q": q, "norm": norm,
                        "reference_norm": float(sparse.linalg.norm(reference)),
                        "difference_norm": float(sparse.linalg.norm(difference)),
                        "absolute_max_difference": float(np.max(np.abs(difference.data))) if difference.nnz else 0.0,
                        "absolute_max_reference": float(np.max(np.abs(reference.data))) if reference.nnz else 0.0,
                        "absolute_max_independent": float(np.max(np.abs(result.data))) if result.nnz else 0.0,
                        "complete_actual_contribution_count": len(record["contributions"]), "numeric_factor_calls": 0})
        del reference, result, difference
    return _check_provider_block_norms(results)


def audit_direct_original_cell_contributions(global_bundle, local_condensed_by_twist,
        global_entities, local_entities_by_twist, transports, *, allocation_gate,
        save_array, load_array, event, providers_by_twist, provider_block_records_by_twist,
        load_csr, direct_profile="X", tolerance=LIMIT):
    """Pre-factor exhaustive proof; exact same source is saved for the checker."""
    _require(float(tolerance) == LIMIT, "original finite gate cannot be relaxed")
    metadata = _metadata(direct_profile)
    _require(callable(event) and callable(load_csr), "record/event/verified CSR loader required")
    replication_count = metadata.replication_count
    _require(all(len(items) == replication_count for items in (
        local_condensed_by_twist, local_entities_by_twist, transports, providers_by_twist,
        provider_block_records_by_twist)), "all ordered actual local twists are required")
    _require(all(local_entities_by_twist[b]._transform_bank is global_entities._transform_bank
                 for b in range(replication_count)),
             "full and all local sources must borrow the same mandatory Step0 bank")
    writer = _Writer(save_array, allocation_gate)
    writer.load = load_array
    ky, period = complex(global_bundle["cfg"].ky), float(global_bundle["cfg"].period_y)
    _require(abs(ky.imag) <= 1e-12 and period > 0, "original physical real ky/full period required")
    phase_y = np.exp(1j * ky.real * period)
    etas = [np.exp(1j * (ky.real * period + 2 * np.pi * q) / metadata.ny) for q in range(metadata.ny)]
    receipt = {"schema": SCHEMA, "status": "INCOMPLETE_NOT_QUALIFIED", "profile": metadata.identity(),
               "global_phase_y": _complex(phase_y), "global_eta": [_complex(eta) for eta in etas],
               "global_source": _export_source(global_bundle, global_entities, writer=writer,
                   load_array=load_array, role="original_global", metadata=metadata),
               "local_sources": [], "local_condensation": [], "numeric_factor_calls": 0,
               "no_global_Ny_S_F_Q_FE_square": True,
               "proof_scope": f"all actual original300-column curl+mass cells, every finalized MPC/entity row, all{metadata.ny}x{metadata.ny}/global and2x2/local sums"}
    event("direct_complete_original_global_source_saved", {"source": receipt["global_source"], "status": receipt["status"]})
    for b in range(metadata.replication_count):
        condensed, provider, transport = local_condensed_by_twist[b], providers_by_twist[b], transports[b]
        _require(transport.full is global_entities and transport.local is local_entities_by_twist[b]
                 and transport.b == b and transport.K == replication_count and abs(transport.eta - etas[b]) <= 1e-12
                 and abs(transport.tau - etas[b]**2) <= 1e-12,
                 "complete actual transport/shared-source/branch phase binding differs")
        source = _export_source(condensed.action_bundle, local_entities_by_twist[b], writer=writer,
                                 load_array=load_array, role=f"original_local_{b}", metadata=metadata)
        receipt["local_sources"].append(source)
        receipt["local_condensation"].append(_export_condensation(condensed, source, provider,
            provider_block_records_by_twist[b], writer, f"original_local_{b}"))
        event("direct_original_complete_cell_source_exported", {"twist": b, "cell_count": source["cell_count"],
              "original_columns_per_cell": CELL_DIMENSION, "numeric_factor_calls": 0})
    receipt["saved_named_payload_bytes"] = writer.payload_bytes
    event("direct_complete_original_proof_primitives_before_recompute", receipt)
    # The same array-only verifier is also run in the separate supervised
    # checker.  It never calls this worker producer or trusts this status.
    checks = check_direct_original_cell_contributions(receipt, load=load_array,
        allocation_gate=allocation_gate, direct_profile=direct_profile, load_csr=load_csr)
    receipt["worker_recomputed_checks"] = checks
    receipt["status"] = "PASS_COMPLETE_ORIGINAL_CONTRIBUTION_PROOF_PREFACTOR"
    event("direct_complete_original_operator_qualification", {"status": receipt["status"],
          "global_actual_cells": metadata.cell_count, "local_actual_cells_per_twist": metadata.local_cell_count,
          "full_original_columns_per_cell": CELL_DIMENSION, "all_q_pairs": metadata.ny**2,
          "all_local_pairs_per_twist": 4, "numeric_factor_calls": 0})
    return receipt


def check_direct_original_cell_contributions(receipt, *, load, allocation_gate,
                                             direct_profile="X", load_csr=None):
    """Independent array-only exhaustive recomputation, including negative gates.

    Source/ABI/manifest/file hashes and fresh raw-carrier qualification are
    separate mandatory workflow gates.  This verifier proves the full volume
    and unchanged augmented contribution algebra; it does not certify a PDE
    solution or replace the original residual and output gates.
    """
    _require(receipt.get("schema") == SCHEMA and callable(load) and callable(load_csr),
             "same complete proof schema and independent verified loaders required")
    metadata = _metadata(direct_profile)
    _require(_token(receipt["profile"]) == _token(metadata.identity()),
             "complete proof receipt profile identity differs")
    _require(len(receipt["local_sources"]) == metadata.replication_count
             and len(receipt["local_condensation"]) == metadata.replication_count,
             "all actual twists required")
    source_checks = [_check_source(source, load=load, gate=allocation_gate, metadata=metadata)
                     for source in (receipt["global_source"], *receipt["local_sources"])]
    orbits = _check_orbits(receipt, load=load, gate=allocation_gate, metadata=metadata)
    etas = [_uncomplex(value) for value in receipt["global_eta"]]
    condensation, provider = [], []
    for b in range(metadata.replication_count):
        record = receipt["local_condensation"][b]
        condensation.append(_check_condensation(receipt["local_sources"][b], record,
            load=load, gate=allocation_gate, global_eta=etas, twist=b))
        provider.append(_check_provider_blocks(record, load=load, load_csr=load_csr, gate=allocation_gate))
    return {"schema": SCHEMA + ".independent-checks", "passed": True, "sources": source_checks,
            "complete_actual_xz_y_orbits": orbits, "local_original_condensation": condensation,
            "existing_provider_all2x2_full_columns": provider, "numeric_factor_calls": 0,
            "global_whole_Ny_matrix_created": False, "finite_original_tolerance": LIMIT,
            "all_column_equivalence_basis": "complete original additive cell coverage + exact native/MPC/coefficient maps + every q contribution sum + inherited elimination identities + complete augmented provider projections",
            "mandatory_other_gates": ["fresh literal raw/stored all532C/D/H and alias/fold/cross-sector proof",
                "source_ABI_manifest_and_resource_supervision", "original fullFE/augmented/port residual and full recovery/output"]}


def saved_direct_volume_action(receipt, x_storage, *, load, allocation_gate,
                               changed_cell_ids=None, changed_tensors=None):
    """Recompute original volume action from every complete original cell.

    x_storage uses original storage with zero slaves.  MPC expansion applies
    the finalized original coefficients on gather and their conjugates on
    scatter.  Optional changed cells replace only their full tensor, with
    exact support equality; they never modify native maps or omit channels.
    """
    source = receipt.get("global_source", receipt)
    independent, expansion = _decoded_native(source, load)
    full = int(source["native"]["full_rows"])
    x = _finite_array(np.asarray(x_storage), shape=(full,), kind="c")
    slaves = _read(source["native"]["slaves"], load)
    _require(np.all(x[slaves] == 0), "original independent-storage action requires complete slave-zero input")
    replacements = {} if changed_tensors is None else dict(changed_tensors)
    changed = set() if changed_cell_ids is None else {int(value) for value in changed_cell_ids}
    _require(set(replacements) == changed and changed.issubset(set(range(source["cell_count"]))),
             "changed original complete tensor support is not exactly the authorized cell set")
    _gate(allocation_gate, "independent_saved_original_full_volume_action", full * 16,
          2 * CELL_DIMENSION * 16 + CELL_DIMENSION**2 * 16,
          actual_original_cell_count=source["cell_count"], full_original_columns_per_cell=CELL_DIMENSION)
    result = np.zeros(full, dtype=np.complex128)
    seen = set()
    for cell in source["cells"]:
        index = int(cell["cell_index"])
        _require(index not in seen, "original saved volume action repeated a cell")
        seen.add(index)
        tensor = _read(replacements[index] if index in changed else cell["oriented_tensor"], load)
        _finite_array(tensor, shape=(CELL_DIMENSION, CELL_DIMENSION), kind="c")
        dofs = _read(cell["native_dofs"], load)
        local = np.zeros(CELL_DIMENSION, dtype=np.complex128)
        for row, original in enumerate(dofs):
            local[row] = sum(value * x[master] for master, value in expansion[int(original)])
        action = tensor @ local
        for row, original in enumerate(dofs):
            for master, value in expansion[int(original)]:
                result[master] += np.conjugate(value) * action[row]
        del tensor, local, action
    _require(seen == set(range(source["cell_count"])) and np.all(result[slaves] == 0),
             "original complete saved action coverage or slave-zero scatter failed")
    return result
