"""Read-only actual tagged-mesh evidence for the explicit N0 target pilot."""

import hashlib

import numpy as np


def _y_column_evidence(bounds, tags, *, y_min, y_max, y_slabs):
    """Check raw bounding planes and tags; no rounding or material projection."""
    bounds = np.asarray(bounds)
    tags = np.asarray(tags)
    if (bounds.ndim != 2 or bounds.shape[1] != 6 or not len(bounds)
            or tags.shape != (len(bounds),) or not np.isfinite(bounds).all()
            or not np.issubdtype(tags.dtype, np.integer)
            or y_slabs <= 0 or y_min >= y_max):
        raise ValueError("invalid actual cell bounds/tag metadata")
    if np.any(bounds[:, (1, 3, 5)] <= bounds[:, (0, 2, 4)]):
        raise ValueError("actual cell has a nonpositive coordinate extent")
    # Primary key: exact x/z bounding planes. Secondary key: exact y interval.
    order = np.lexsort(tuple(bounds[:, i] for i in (3, 2, 5, 4, 1, 0)))
    ordered = bounds[order]
    ordered_tags = tags[order]
    xz = ordered[:, (0, 1, 4, 5)]
    starts = np.r_[0, 1 + np.flatnonzero(np.any(xz[1:] != xz[:-1], axis=1))]
    counts = np.diff(np.r_[starts, len(ordered)])
    if np.any(counts != y_slabs):
        raise ValueError("actual x/z columns do not all contain the required y slabs")
    columns = ordered.reshape(-1, y_slabs, 6)
    column_tags = ordered_tags.reshape(-1, y_slabs)
    reference_y = columns[0, :, 2:4]
    if (reference_y[0, 0] != y_min or reference_y[-1, 1] != y_max
            or np.any(reference_y[1:, 0] != reference_y[:-1, 1])
            or np.any(columns[:, :, 2:4] != reference_y)):
        raise ValueError("actual y slabs have a gap, overlap or inconsistent column coverage")
    if np.any(column_tags != column_tags[:, :1]):
        raise ValueError("actual material cell tags vary along a y column")
    values, tag_counts = np.unique(tags, return_counts=True)
    return {
        "actual_cell_count": len(bounds),
        "actual_xz_column_count": len(starts),
        "actual_y_slabs_per_column": int(y_slabs),
        "actual_cell_tag_counts": {
            str(int(tag)): int(count) for tag, count in zip(values, tag_counts, strict=True)
        },
        "raw_cell_bounds_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(bounds)).cast("B")
        ).hexdigest(),
        "raw_cell_tag_values_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(tags)).cast("B")
        ).hexdigest(),
        "raw_bounds_dtype": bounds.dtype.str,
        "raw_tag_dtype": tags.dtype.str,
        "raw_xz_column_y_coverage_exact": True,
        "actual_tags_constant_along_y": True,
        "geometry_rounding_applied": False,
    }


def actual_n0_y_material_evidence(levels, cfg):
    """Inspect the already built target mesh; create no mesh or FE operators."""
    mesh = levels["mesh"]
    cell_tags = levels["mesh_data"].cell_tags
    count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    if (int(mesh.comm.size) != 1 or mesh.topology.cell_name() != "hexahedron"
            or count != 530856
            or int(mesh.topology.index_map(mesh.topology.dim).size_global) != count):
        raise ValueError("N0 pilot requires the actual MPI1 530856-cell hexahedral target")
    if (cfg.geometry_kind != "rectangular_block_grating" or cfg.cell_notch is not None
            or cfg.use_pml or cfg.grating_y_min != cfg.y_min
            or cfg.grating_y_max != cfg.y_max or complex(cfg.ky) != 0j):
        raise ValueError("N0 target material/incident configuration is not y invariant")
    indices = np.asarray(cell_tags.indices)
    tags = np.asarray(cell_tags.values)
    if not np.array_equal(indices, np.arange(count, dtype=indices.dtype)):
        raise ValueError("N0 material audit requires every owned cell tag exactly once")
    materials = {
        int(cfg.tags.air): complex(cfg.eps_air),
        int(cfg.tags.substrate): complex(cfg.eps_substrate),
        int(cfg.tags.grating): complex(cfg.eps_grating),
    }
    if (len(materials) != 3 or set(map(int, np.unique(tags))) != set(materials)
            or not np.isfinite(list(materials.values())).all()):
        raise ValueError("N0 actual material tags or their permittivities differ")
    coordinates = np.asarray(mesh.geometry.x)
    cells = np.asarray(mesh.geometry.dofmap)
    if (coordinates.dtype != np.dtype(np.float64) or coordinates.shape[1] != 3
            or cells.ndim != 2 or cells.shape[0] < count or cells.shape[1] != 8):
        raise ValueError("N0 material audit requires the actual affine Q1 hex geometry")
    bounds = np.empty((count, 6), dtype=np.float64)
    # Bounded vertex gather: no field, matrix or complete per-cell tensor copy.
    for first in range(0, count, 4096):
        last = min(first + 4096, count)
        vertices = coordinates[cells[first:last]]
        bounds[first:last, (0, 2, 4)] = np.min(vertices, axis=1)
        bounds[first:last, (1, 3, 5)] = np.max(vertices, axis=1)
    facts = _y_column_evidence(
        bounds, tags, y_min=float(cfg.y_min), y_max=float(cfg.y_max), y_slabs=36
    )
    return {
        "schema": "task39extra.n0-actual-y-material-evidence.v1",
        **facts,
        "material_relative_permittivity_by_tag": {
            str(tag): {"real": value.real, "imag": value.imag}
            for tag, value in materials.items()
        },
        "incident_ky": {"real": float(complex(cfg.ky).real), "imag": 0.0},
        "scope": "actual tagged target mesh only; not full-DtN equivalence or convergence",
        "geometry_material_or_fe_constraints_modified": False,
    }
