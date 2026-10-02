"""Explicit X-only raw-observer admission; no assembly or numerical changes.

The default observer remains bounded by its original carrier guard. This
module verifies actual current metadata for the separately reviewed X profile.
Module loading uses only the standard library; runtime checks reuse the exact
existing discrete identity codecs and profile validators.
"""
from collections.abc import Mapping
from importlib.metadata import version as package_version
from pathlib import Path
import hashlib
import sys


SCHEMA = "task40extra.direct-X-raw-observer-admission.v1"


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def direct_raw_observer_expected_local_cells(quotient_context, cfg):
    """Only the explicit X context may replace the historical local40 bound."""
    from .y_orbit_direct_profile import direct_profile_metadata, PHYSICAL_GENERATOR_SHA256
    from .fullspace_dtn_action import _canonical_json_bytes
    metadata = direct_profile_metadata("X")
    if (quotient_context.direct_profile_name != "X"
            or quotient_context.global_axes != metadata.global_axes
            or quotient_context.local_axes != metadata.local_axes
            or quotient_context.global_y_cells != 4 or quotient_context.replication_count != 2
            or quotient_context.local_y_cells != 2
            or type(quotient_context.twist_index) is not int or quotient_context.twist_index not in (0, 1)
            or quotient_context.physical_generator_manifest_sha256 != PHYSICAL_GENERATOR_SHA256
            or tuple(cfg.mesh_axis_cell_counts) != (6, 2, 5)
            or tuple(tuple(getattr(cfg, f"mesh_axis_{name}_values")) for name in ("x", "y", "z")) != metadata.local_axes
            or int(cfg.nedelec_degree) != 4 or cfg.nedelec_trace_degree is not None
            or cfg.nedelec_interior_degree is not None
            or quotient_context.assembly_config_sha256 != hashlib.sha256(_canonical_json_bytes(cfg.as_jsonable())).hexdigest()):
        raise ValueError("only the explicit frozen X local60 config/context is admitted")
    return metadata.local_cell_count


def validate_direct_raw_observer_profile(profile, *, modes, mpc, cfg,
        assembly_context, physical_cfg, quotient_context, physical_manifest_sha,
        surface_assemblers):
    """Admit only fresh actual X full120/local60 p4, without changing C/D/H."""
    if type(profile) is not str or profile != "X":
        raise ValueError("raw observer profile must be the explicit reviewed X string")
    if not isinstance(assembly_context, Mapping):
        raise ValueError("raw observer X requires the actual frozen discrete context")
    import numpy as np
    import basix
    import dolfinx
    import ffcx
    from petsc4py import PETSc
    from .dtn_boundary_phase_gauge import _array_signature
    from .fullspace_dtn_action import _canonical_json_bytes
    from .y_orbit_direct_profile import validate_direct_physical_config, PHYSICAL_GENERATOR_SHA256

    physical = cfg if quotient_context is None else physical_cfg
    metadata = validate_direct_physical_config(physical, "X")
    if quotient_context is None:
        cells, rows, independent, mode_count, axes = (metadata.cell_count, metadata.storage_rows,
            metadata.independent_rows, 532, metadata.global_axes)
    else:
        if (quotient_context.direct_profile_name != "X"
                or type(quotient_context.twist_index) is not int
                or quotient_context.twist_index not in (0, 1)
                or quotient_context.global_y_cells != 4 or quotient_context.replication_count != 2
                or quotient_context.global_axes != metadata.global_axes
                or quotient_context.local_axes != metadata.local_axes):
            raise ValueError("raw observer X requires its exact two-cell physical quotient context")
        cells, rows, independent, mode_count, axes = (metadata.local_cell_count, metadata.local_storage_rows,
            metadata.local_independent_rows, metadata.sector_port_counts[quotient_context.twist_index], metadata.local_axes)
        local = assembly_context.get("y_orbit_quotient", {})
        if (local.get("contract_sha256") != quotient_context.sha256
                or _canonical_json_bytes(local.get("contract")) != _canonical_json_bytes(quotient_context.identity())
                or local.get("actual_local_cells") != cells
                or local.get("actual_local_storage_rows") != rows
                or local.get("actual_finalized_mpc_slave_rows") != rows-independent):
            raise ValueError("raw observer X actual local context/config/MPC identity differs")
    space, mesh = mpc.function_space, mpc.function_space.mesh
    index_map, element = space.dofmap.index_map, space.element.basix_element
    if (int(mesh.comm.size) != 1 or int(mesh.topology.dim) != 3
            or int(mesh.topology.index_map(3).size_local) != cells
            or int(index_map.size_local) != rows or int(index_map.size_global) != rows
            or tuple(index_map.local_range) != (0, rows)
            or int(element.degree) != 4 or int(space.element.space_dimension) != 300
            or tuple(cfg.mesh_axis_cell_counts) != tuple(len(axis)-1 for axis in axes)
            or not all(np.array_equal(np.unique(mesh.geometry.x[:, axis]), expected)
                       for axis, expected in enumerate(axes))):
        raise ValueError("raw observer X requires actual MPI1 full120/25468 or local60/13236 complete p4")
    slaves = np.asarray(mpc.slaves)
    if (slaves.ndim != 1 or slaves.dtype.kind not in "iu" or len(slaves) != rows-independent
            or (slaves.size and (int(slaves.min()) < 0 or int(slaves.max()) >= rows))
            or len(np.unique(slaves)) != len(slaves)):
        raise ValueError("raw observer X finalized MPC slave partition differs from its actual profile")
    def equal(left, right):
        return _canonical_json_bytes(left) == _canonical_json_bytes(right)
    coeff, offsets = mpc.coefficients()
    actual_mpc = {name: _array_signature(value) for name, value in (
        ("slaves", mpc.slaves), ("masters", mpc.masters.array),
        ("coefficients", coeff), ("offsets", offsets))}
    if (assembly_context.get("schema") != "task40extra.dtn-plane-discrete-context.v1"
            or assembly_context.get("element_degree") != 4
            or assembly_context.get("element_map_type") != element.map_type.name
            or not equal(assembly_context.get("basix_coefficients"), _array_signature(element.coefficient_matrix))
            or not equal(assembly_context.get("MPC"), actual_mpc)
            or assembly_context.get("config_sha256") != hashlib.sha256(_canonical_json_bytes(cfg.as_jsonable())).hexdigest()
            or not equal(assembly_context["mesh"].get("geometry_x"), _array_signature(mesh.geometry.x))
            or not equal(assembly_context["mesh"].get("geometry_dofmap"), _array_signature(mesh.geometry.dofmap))
            or not equal(assembly_context.get("orientation"), _array_signature(mesh.topology.get_cell_permutation_info()))):
        raise ValueError("raw observer X actual config/basis/mesh/orientation/MPC hashes differ")
    dofs_digest = hashlib.sha256()
    for cell in range(cells):
        dofs_digest.update(_canonical_json_bytes(_array_signature(space.dofmap.cell_dofs(cell))))
    if assembly_context.get("cell_dofmap_sha256") != dofs_digest.hexdigest():
        raise ValueError("raw observer X actual complete cell dofmap hash differs")
    solver_dir = Path(__file__).resolve().parent
    source_paths = [solver_dir/name for name in ("dtn_boundary_phase_gauge.py", "dtn_port_3d.py",
        "fullspace_dtn_action.py", "fullspace_same_mesh_hcurl_pmg_physical.py", "dtn_boundary_plane_qualification.py")]
    source_paths += [solver_dir.parent/"common"/name for name in ("modes_3d.py", "config_3d.py")]
    if quotient_context is not None:
        source_paths += [solver_dir/name for name in ("y_orbit_quotient_context.py",
            "fullspace_same_mesh_hcurl_pmg_global.py", "y_orbit_condensed_adapter.py")]
        source_paths += [solver_dir.parent/"constraints"/name for name in (
            "floquet_3d.py", "floquet_3d_high_order.py", "high_order_floquet_trace.py")]
    source_hashes = {path.name: _file_sha256(path) for path in source_paths}
    if not equal(assembly_context.get("source_sha256"), source_hashes):
        raise ValueError("raw observer X actual discrete/physical source files differ from frozen context")
    actual_abi = {"python": sys.version, "numpy": np.__version__, "basix": basix.__version__,
        "dolfinx": dolfinx.__version__, "dolfinx_mpc": package_version("dolfinx_mpc"),
        "ffcx": ffcx.__version__, "PETSc": PETSc.Sys.getVersion(),
        "scalar": str(np.dtype(PETSc.ScalarType)), "integer": str(np.dtype(PETSc.IntType))}
    if actual_abi["scalar"] != "complex128" or not equal(assembly_context.get("ABI"), actual_abi):
        raise ValueError("raw observer X actual ABI differs from frozen context")
    expected_sides = {("top", 0), ("top", 1), ("bottom", 0), ("bottom", 1)}
    primary = {f"{side}/{component}": assembler.compiled_gauss_identity
               for (side, component), assembler in surface_assemblers.items()}
    if (set(surface_assemblers) != expected_sides or assembly_context["gauss"].get("degree") != 23
            or not equal(assembly_context["gauss"].get("compiled_forms_verified"), primary)):
        raise ValueError("raw observer X requires its actual four verified primary Gauss forms")
    for identity in primary.values():
        rules = identity["rules"]
        if len(rules) != 1:
            raise ValueError("raw observer X requires one actual Gauss rule per primary form")
        rule = rules[0]
        if (rule["degree"] != 23 or rule["facet_cell"] != "quadrilateral"
                or rule["integral_type"] != "exterior_facet"
                or tuple(rule["points"]["shape"]) != (144, 2) or tuple(rule["weights"]["shape"]) != (144,)
                or rule["points"]["dtype"] != "float64" or rule["weights"]["dtype"] != "float64"
                or type(rule["compiled_weight_tables_verified"]) is not int
                or rule["compiled_weight_tables_verified"] < 1):
            raise ValueError("raw observer X requires unchanged actual Gauss23/144 nodes and weights")
        kernel = identity["loaded_kernel"]
        for path_key, hash_key in (("module_path", "binary_sha256"), ("module_bound_C_path", "module_bound_C_sha256")):
            if _file_sha256(kernel[path_key]) != kernel[hash_key]:
                raise ValueError("raw observer X actual loaded primary kernel file hash differs")
    keys = tuple((str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)) for mode in modes)
    if (len(modes) != mode_count or len(set(keys)) != mode_count
            or physical_manifest_sha != PHYSICAL_GENERATOR_SHA256
            or (quotient_context is None and tuple(sum(int(mode.n) % 4 == q for mode in modes)
                                                  for q in range(4)) != metadata.q_port_counts)
            or (quotient_context is not None and (keys != quotient_context.original_mode_keys
                or any((int(mode.n)-quotient_context.twist_index) % 2 for mode in modes)))):
        raise ValueError("raw observer X requires all actual unchanged original physical modes and sector aliases")
    return {"schema": SCHEMA, "profile": "X", "actual_cells": cells, "actual_storage_rows": rows,
        "actual_independent_rows": independent, "actual_mode_count": mode_count,
        "twist_index": None if quotient_context is None else quotient_context.twist_index,
        "physical_generator_manifest_sha256": physical_manifest_sha,
        "assembly_context_sha256": hashlib.sha256(_canonical_json_bytes(assembly_context)).hexdigest(),
        "source_sha256": source_hashes, "admission_source_sha256": _file_sha256(__file__),
        "ABI": actual_abi, "primary_Gauss_degree": 23, "primary_facet_point_count": 144,
        "numerical_qualification_performed": False, "assembly_or_cutoff_changed": False}
