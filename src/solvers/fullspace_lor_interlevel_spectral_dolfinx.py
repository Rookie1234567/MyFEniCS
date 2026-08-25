"""DOLFINx adapter for shared Route-A/Route-B interlevel probe evidence.

The module keeps mesh, MPC, and vector construction here.  It deliberately
does not create a global transfer or a solver; the retained numerical payload
is supplied by the small local spectral cores and owner-packet bridges.  The
Route-A schema and default calls remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping

import numpy as np

from .fullspace_lor_interlevel_route_selection import PROBE_NAMES


R3_LONG_TAIL_MANIFEST_SHA256 = (
    "62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce"
)
R3_LONG_TAIL_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
ALPHA = 0.37 + 0.19j
BETA = -0.23 + 0.41j
MATERIAL_INVENTORY_SCHEMA = "task038.full3d.route-a.material-inventory.v1"
PROBE_SCHEMA = "task038.full3d.route-a.global-probe.v1"
SOURCE_GENERATION = {
    "random": "native_l2_analytic_values:random",
    "gradient": "native_l2_analytic_values:gradient",
    "curl": "native_l2_analytic_values:curl",
    "checkerboard": "native_l2_analytic_values:checkerboard",
    "physical_component_derived": "s2_physical_rhs.compose_then_high_dual_restrict_then_p63_adjoint",
    "r3_long_tail_derived": "r3_canonical_full_fe_dual_packets_then_high_dual_restrict_then_p63_adjoint",
}
ROUTE_B_PROBE_SCHEMA = "task038.route-b.global-probe.v1"
ROUTE_B_SOURCE_GENERATION = {
    **SOURCE_GENERATION,
    "physical_component_derived": "s2_physical_rhs.compose_then_high_dual_restrict_then_p62_adjoint",
    "r3_long_tail_derived": "r3_canonical_full_fe_dual_packets_then_high_dual_restrict_then_p62_adjoint",
}


def _semantic_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def source_generation_identity(
    name: str, source_generation: Mapping[str, str] | None = None,
) -> str:
    source_generation = SOURCE_GENERATION if source_generation is None else source_generation
    try:
        return source_generation[name]
    except KeyError as exc:
        raise ValueError(f"unknown source {name!r}") from exc


def _probe_levels(
    extension: Any, *, fine_degree: int, coarse_degree: int,
) -> tuple[Any, Any]:
    pair = (int(fine_degree), int(coarse_degree))
    if hasattr(extension, "pair_levels"):
        fine, coarse = extension.pair_levels(pair)
        return fine, coarse
    levels = getattr(extension, "levels", None)
    if isinstance(levels, Mapping):
        try:
            return levels[pair[0]], levels[pair[1]]
        except KeyError as exc:
            raise ValueError(f"probe levels are missing pair {pair}") from exc
    if pair == (6, 3) and isinstance(levels, tuple) and len(levels) == 2:
        return levels[0], levels[1]
    raise ValueError("probe extension does not expose the requested explicit levels")


def _apply_pair(extension: Any, pair: tuple[int, int], source: Any, *, adjoint: bool):
    method = extension.apply_adjoint if adjoint else extension.apply_primal
    if hasattr(extension, "pair_levels"):
        return method(pair, source)
    if pair != (6, 3):
        raise ValueError("the legacy Route-A extension only exposes pair (6, 3)")
    return method(source)


def _owned_cell_widths(function_space: Any, cell: int) -> tuple[float, float, float]:
    from .fullspace_lor_native_hx_fixture import _entity_coordinates

    coordinates = np.asarray(_entity_coordinates(function_space, 3, cell), dtype=np.float64)
    if coordinates.shape != (8, 3) or np.unique(coordinates, axis=0).shape[0] != 8:
        raise ValueError("owned cell must have eight unique vertex coordinates")
    if not np.all(np.isfinite(coordinates)):
        raise ValueError("owned cell coordinates must be finite")
    axes: list[float] = []
    expected_corners: set[tuple[float, float, float]] = set()
    for axis in range(3):
        values = np.unique(coordinates[:, axis])
        if values.size != 2 or not values[1] > values[0]:
            raise ValueError("owned cell must be a positive axis-aligned affine hexahedron")
        axes.append(float(values[1] - values[0]))
    for x in (float(np.min(coordinates[:, 0])), float(np.max(coordinates[:, 0]))):
        for y in (float(np.min(coordinates[:, 1])), float(np.max(coordinates[:, 1]))):
            for z in (float(np.min(coordinates[:, 2])), float(np.max(coordinates[:, 2]))):
                expected_corners.add((x, y, z))
    actual_corners = {tuple(float(value) for value in row) for row in coordinates}
    if actual_corners != expected_corners:
        raise ValueError("owned cell is not an axis-aligned affine hexahedron")
    if not all(np.isfinite(value) and value > 0.0 for value in axes):
        raise ValueError("owned cell widths must be positive and finite")
    return tuple(axes)


def build_material_class_inventory_from_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Group exact float64 cell metadata without tolerance merging."""

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        from .fullspace_lor_interlevel_spectral import build_route_a_class_identity

        material_role = str(row["material_role"])
        tag = int(row["tag"])
        if material_role not in {"air", "substrate", "grating"}:
            raise ValueError("material rows require air/substrate/grating roles")
        widths = tuple(float(value) for value in row["widths"])
        curl_coefficient = float(row["curl_coefficient"])
        mass_coefficient = float(row["mass_coefficient"])
        if len(widths) != 3 or not all(math.isfinite(value) and value > 0.0 for value in widths + (curl_coefficient, mass_coefficient)):
            raise ValueError("material class rows require positive finite geometry/coefficient facts")
        identity_record = build_route_a_class_identity(
            class_name=f"{material_role}_tag_{tag}",
            widths=widths,
            curl_coefficient=curl_coefficient,
            mass_coefficient=mass_coefficient,
            material_role=material_role,
        )
        identity = identity_record["class_identity"]
        digest = identity_record["class_digest"]
        item = grouped.setdefault(
            digest,
            {
                "class_digest": digest,
                "class_identity": identity,
                "tag": tag,
                "material_role": material_role,
                "cell_count_local": 0,
            },
        )
        item["cell_count_local"] += 1
    classes = sorted(grouped.values(), key=lambda item: item["class_digest"])
    return {
        "schema": MATERIAL_INVENTORY_SCHEMA,
        "class_count": len(classes),
        "classes": classes,
        "exact_float64_identity": True,
        "numeric_allgather": False,
    }


def build_material_class_inventory(foundation: Any) -> dict[str, Any]:
    """Extract exact owned-cell classes using the S2 coefficient semantics."""

    from .fullspace_lor_native_hx_fixture import _piecewise_positive_coefficients
    from mpi4py import MPI

    mesh = foundation.high_mesh
    tags = foundation.high_data.cell_tags
    cfg = foundation.cfg
    local_cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    tag_values = np.full(local_cell_count, int(cfg.tags.air), dtype=np.int32)
    tag_values[np.asarray(tags.indices, dtype=np.int32)] = np.asarray(
        tags.values, dtype=np.int32
    )
    mu_function, mass_function, _audit = _piecewise_positive_coefficients(
        mesh, tags, cfg
    )
    mu_values = np.asarray(mu_function.x.array[:local_cell_count], dtype=np.float64).copy()
    mass_values = np.asarray(mass_function.x.array[:local_cell_count], dtype=np.float64).copy()
    role_by_tag = {
        int(cfg.tags.air): "air",
        int(cfg.tags.substrate): "substrate",
        int(cfg.tags.grating): "grating",
    }
    roles = [role_by_tag.get(int(tag)) for tag in tag_values]
    if any(role is None for role in roles):
        raise ValueError("owned material inventory contains an unmapped cell tag")
    rows = []
    for cell in range(local_cell_count):
        widths = _owned_cell_widths(foundation.high_space, cell)
        rows.append(
            {
                "tag": int(tag_values[cell]),
                "material_role": roles[cell],
                "widths": tuple(float(value) for value in widths),
                "curl_coefficient": float(mu_values[cell]),
                "mass_coefficient": float(mass_values[cell]),
            }
        )
    result = build_material_class_inventory_from_rows(rows)
    comm = mesh.comm
    local_keys = tuple(item["class_digest"] for item in result["classes"])
    all_keys = comm.allgather(local_keys)
    for item in result["classes"]:
        item["cell_count_global"] = int(
            comm.allreduce(int(item["cell_count_local"]), op=MPI.SUM)
        )
    result["class_inventory_by_rank"] = [list(keys) for keys in all_keys]
    result["cell_count_local"] = local_cell_count
    result["cell_count_global"] = int(comm.allreduce(local_cell_count, op=MPI.SUM))
    del mu_function, mass_function
    return result


def audit_material_classes(
    inventory: Mapping[str, Any], p63: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Run the local dense core once per exact class, reusing one P63."""

    from .fullspace_lor_interlevel_spectral import build_route_a_material_class

    audits: list[dict[str, Any]] = []
    arrays: dict[str, np.ndarray] = {"p63": np.asarray(p63, dtype=np.complex128).copy()}
    for item in inventory["classes"]:
        identity = item["class_identity"]
        result = build_route_a_material_class(
            class_name=str(identity["material_coefficient_identity"]["class_name"]),
            widths=tuple(identity["geometry_jacobian_identity"]["widths"]),
            curl_coefficient=float(identity["material_coefficient_identity"]["curl_coefficient"]),
            mass_coefficient=float(identity["material_coefficient_identity"]["mass_coefficient"]),
            material_role=str(identity["material_coefficient_identity"]["material_role"]),
            p63=p63,
        )
        audit = dict(result.audit)
        audit.update(
            {
                "class_identity": identity,
                "class_digest_matches_inventory": audit["class_digest"] == item["class_digest"],
                "tag": int(item["tag"]),
                "material_role": str(item["material_role"]),
                "cell_count_local": int(item["cell_count_local"]),
                "cell_count_global": int(item.get("cell_count_global", item["cell_count_local"])),
            }
        )
        audits.append(audit)
        prefix = f"class_{item['class_digest']}"
        arrays[f"{prefix}__b3"] = np.asarray(result.retained["b3"]).copy()
        arrays[f"{prefix}__b6p"] = np.asarray(result.retained["b6p"]).copy()
        arrays[f"{prefix}__eigenvector_min"] = np.asarray(
            result.retained["eigenvector_min"]
        ).copy()
        arrays[f"{prefix}__eigenvector_max"] = np.asarray(
            result.retained["eigenvector_max"]
        ).copy()
    return audits, arrays


def audit_nested_material_classes(
    inventory: Mapping[str, Any], p62: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Audit all exact classes with one retained nested P62 map."""

    from .fullspace_lor_nested_interlevel import build_nested_material_class

    audits: list[dict[str, Any]] = []
    arrays: dict[str, np.ndarray] = {
        "p62": np.asarray(p62, dtype=np.complex128).copy()
    }
    for item in inventory["classes"]:
        identity = item["class_identity"]
        material = identity["material_coefficient_identity"]
        geometry = identity["geometry_jacobian_identity"]
        result = build_nested_material_class(
            class_name=str(material["class_name"]),
            widths=tuple(geometry["widths"]),
            curl_coefficient=float(material["curl_coefficient"]),
            mass_coefficient=float(material["mass_coefficient"]),
            material_role=str(material["material_role"]),
            p62=p62,
        )
        audit = dict(result.audit)
        audit.update({
            "class_identity": identity,
            "class_digest_matches_inventory": (
                audit["class_digest"] == item["class_digest"]
            ),
            "tag": int(item["tag"]),
            "material_role": str(item["material_role"]),
            "cell_count_local": int(item["cell_count_local"]),
            "cell_count_global": int(
                item.get("cell_count_global", item["cell_count_local"])
            ),
        })
        audits.append(audit)
        prefix = f"class_{item['class_digest']}"
        for role in ("b2", "b6p", "eigenvector_min", "eigenvector_max"):
            arrays[f"{prefix}__{role}"] = np.asarray(
                result.retained[role]
            ).copy()
    return audits, arrays


def _vector_array(vector: Any) -> np.ndarray:
    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()


def _vector_digest(vector: Any) -> str:
    return hashlib.sha256(np.ascontiguousarray(_vector_array(vector)).view(np.uint8)).hexdigest()


def _canonical_primal(level: Any, source: Any) -> Any:
    owner_packet = level.primal_to_owner(source)
    return level.owner_to_primal(owner_packet)


def _deterministic_seed(level: Any, offset: float) -> Any:
    vector = level.matrix.createVecRight()
    start, stop = vector.getOwnershipRange()
    index = np.arange(int(start), int(stop), dtype=np.float64) + 1.0 + float(offset)
    vector.array[:] = index + 1j * (0.25 * index + 0.5 * float(offset))
    vector.assemble()
    return vector


def _analytic_source(level: Any, foundation: Any, name: str) -> Any:
    from dolfinx import fem
    from .fullspace_lor_native_hx_fixture import _l2_analytic_values

    field = fem.Function(level.raw_space)
    field.interpolate(lambda coordinates: _l2_analytic_values(name, coordinates, foundation.cfg))
    field.x.scatter_forward()
    level.raw_floquet.mpc.homogenize(field)
    level.raw_floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    try:
        return _canonical_primal(level, field.x.petsc_vec)
    finally:
        del field


def _physical_rhs_high_dual(foundation: Any) -> Any:
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _dtn_surface_quadrature_degree,
        _incident_projection_onto_top_mode,
        _incident_top_traction_form,
    )
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    modes, _rows, mode_sha = build_dynamic_mode_inventory(foundation.cfg)
    if mode_sha != foundation.mode_sha:
        raise RuntimeError("physical probe mode manifest identity mismatch")
    qdegree = _dtn_surface_quadrature_degree(foundation.cfg, list(modes))
    base = _assemble_mpc_vector(
        _incident_top_traction_form(foundation.high_space, foundation.high_data, foundation.cfg),
        foundation.high_floquet.mpc,
        quadrature_degree=qdegree,
    )
    target = foundation.high_work_output.duplicate()
    amplitudes = tuple(_incident_projection_onto_top_mode(mode, foundation.cfg) for mode in modes)
    foundation.physical_action.compose_physical_rhs(base, amplitudes, target)
    base.destroy()
    return target


def _coarse_from_high_dual(
    foundation: Any, extension: Any, high_dual: Any, *,
    fine_degree: int = 6, coarse_degree: int = 3,
) -> Any:
    low_dual = foundation.low_matrix.createVecRight()
    coarse_dual = None
    try:
        foundation.restrict_into(high_dual, low_dual)
        coarse_dual = _apply_pair(
            extension, (int(fine_degree), int(coarse_degree)), low_dual,
            adjoint=True,
        )
        _fine_level, coarse_level = _probe_levels(
            extension, fine_degree=fine_degree, coarse_degree=coarse_degree
        )
        return _canonical_primal(coarse_level, coarse_dual)
    finally:
        low_dual.destroy()
        if coarse_dual is not None:
            coarse_dual.destroy()


def _r3_coarse_source(
    foundation: Any, extension: Any, packets: Any, *,
    fine_degree: int = 6, coarse_degree: int = 3,
) -> Any:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        reconstruct_canonical_full_fe_dual_vector,
    )

    high_dual = reconstruct_canonical_full_fe_dual_vector(
        foundation.high_space, foundation.high_floquet.mpc, packets
    )
    try:
        return _coarse_from_high_dual(
            foundation, extension, high_dual,
            fine_degree=fine_degree, coarse_degree=coarse_degree,
        )
    finally:
        high_dual.destroy()


def build_probe_source(
    name: str, foundation: Any, extension: Any, r3_packets: Any, *,
    fine_degree: int = 6, coarse_degree: int = 3,
    probe_schema: str = PROBE_SCHEMA,
    source_generation: Mapping[str, str] = SOURCE_GENERATION,
) -> Any:
    if name not in PROBE_NAMES:
        label = "Route-A" if probe_schema == PROBE_SCHEMA else "interlevel"
        raise ValueError(f"unknown frozen {label} probe: {name}")
    source_generation_identity(name, source_generation)
    _fine_level, coarse_level = _probe_levels(
        extension, fine_degree=fine_degree, coarse_degree=coarse_degree
    )
    if name in {"random", "gradient", "curl", "checkerboard"}:
        return _analytic_source(coarse_level, foundation, name)
    if name == "physical_component_derived":
        high_dual = _physical_rhs_high_dual(foundation)
        try:
            return _coarse_from_high_dual(
                foundation, extension, high_dual,
                fine_degree=fine_degree, coarse_degree=coarse_degree,
            )
        finally:
            high_dual.destroy()
    if r3_packets is None:
        raise ValueError("R3 canonical packets are required for the frozen tail probe")
    return _r3_coarse_source(
        foundation, extension, r3_packets,
        fine_degree=fine_degree, coarse_degree=coarse_degree,
    )


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


def measure_probe(
    name: str, foundation: Any, extension: Any, source: Any, *,
    fine_degree: int = 6, coarse_degree: int = 3,
    probe_schema: str = PROBE_SCHEMA,
    source_generation: Mapping[str, str] = SOURCE_GENERATION,
    coarse_action_role: str = "B3",
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Measure one probe and return scalar facts plus checker-owned raw arrays."""

    if coarse_action_role not in {"B3", "B2"}:
        raise ValueError("coarse action role must be B3 or B2")
    coarse_action_key = "b2" if coarse_action_role == "B2" else "b3"
    pair = (int(fine_degree), int(coarse_degree))
    level6, level3 = _probe_levels(
        extension, fine_degree=fine_degree, coarse_degree=coarse_degree
    )
    source_generation_identity(name, source_generation)
    source_before = _vector_array(source)
    source_norm = float(np.linalg.norm(source_before))
    source_finite = bool(np.all(np.isfinite(source_before)) and np.isfinite(source_norm))
    source_nonzero = bool(source_norm > 0.0)
    if source_before.ndim != 1 or source_before.size == 0 or not source_finite or not source_nonzero:
        raise ValueError(f"Route-A probe source {name} must be nonzero and finite before apply")
    source_before_digest = _vector_digest(source)
    projected = _apply_pair(extension, pair, source, adjoint=False)
    projected_repeat = _apply_pair(extension, pair, source, adjoint=False)
    seed2 = _deterministic_seed(level3, 17.0)
    source2 = _canonical_primal(level3, seed2)
    seed2.destroy()
    projected2 = _apply_pair(extension, pair, source2, adjoint=False)
    combo = source.copy()
    combo.scale(ALPHA)
    combo.axpy(BETA, source2)
    projected_combo = _apply_pair(extension, pair, combo, adjoint=False)
    fine_dual = _deterministic_seed(level6, 31.0)
    adjoint = _apply_pair(extension, pair, fine_dual, adjoint=True)
    b3 = level3.matrix.createVecLeft()
    level3.matrix.mult(source, b3)
    b6p = level6.matrix.createVecLeft()
    level6.matrix.mult(projected, b6p)
    try:
        source_after = _vector_array(source)
        projected_values = _vector_array(projected)
        projected_repeat_values = _vector_array(projected_repeat)
        projected2_values = _vector_array(projected2)
        projected_combo_values = _vector_array(projected_combo)
        fine_dual_values = _vector_array(fine_dual)
        adjoint_values = _vector_array(adjoint)
        b3_values = _vector_array(b3)
        b6p_values = _vector_array(b6p)
        ec = np.vdot(source_before, b3_values)
        ef = np.vdot(projected_values, b6p_values)
        if not np.isfinite(ec.real) or not np.isfinite(ec.imag) or abs(ec) <= 0.0:
            raise ValueError(f"Route-A probe source {name} has zero/nonfinite coarse energy")
        if not np.isfinite(ef.real) or not np.isfinite(ef.imag):
            raise ValueError(f"Route-A probe source {name} has nonfinite fine energy")
        ratio = ef / ec
        if not np.isfinite(ratio.real) or not np.isfinite(ratio.imag):
            raise ValueError(f"Route-A probe source {name} has nonfinite energy ratio")
        topology_audits = (
            level6.parent_topology.audit,
            level3.parent_topology.audit,
        )
        phase_once = all(
            audit.get("phase_application") == "once_in_canonical_owner_route"
            and audit.get("slave_master_complete") is True
            for audit in topology_audits
        )
        facts = {
            "schema": probe_schema,
            "name": name,
            "q": float(ratio.real),
            "q_imag_defect": float(abs(ratio.imag)),
            "energy_imag_defect": float(max(abs(ec.imag), abs(ef.imag))),
            "energy_coarse": [float(ec.real), float(ec.imag)],
            "energy_fine": [float(ef.real), float(ef.imag)],
            "source_norm": source_norm,
            "source_finite": source_finite,
            "source_nonzero": source_nonzero,
            "adjoint_work_relative": _relative(
                np.asarray([np.vdot(projected_values, fine_dual_values)]),
                np.asarray([np.vdot(source_before, adjoint_values)]),
            ),
            "linearity_relative": _relative(
                projected_combo_values,
                ALPHA * projected_values + BETA * projected2_values,
            ),
            "repeat_relative": _relative(projected_repeat_values, projected_values),
            "finite": bool(all(np.all(np.isfinite(value)) for value in (
                source_before, source_after, projected_values, projected_repeat_values,
                source2.getArray(readonly=True), projected2_values, projected_combo_values,
                fine_dual_values, adjoint_values, b3_values, b6p_values,
            ))),
            "input_unchanged": bool(np.array_equal(source_before, source_after)),
            "phase_once": phase_once,
            "source_before_digest": source_before_digest,
            "source_after_digest": hashlib.sha256(np.ascontiguousarray(source_after).view(np.uint8)).hexdigest(),
            "source_generation": source_generation_identity(name, source_generation),
        }
        if probe_schema != PROBE_SCHEMA:
            facts["coarse_action_role"] = str(coarse_action_role)
        arrays = {
            "source_before": source_before,
            "source_after": source_after,
            "source2": _vector_array(source2),
            "projected": projected_values,
            "projected_repeat": projected_repeat_values,
            "projected2": projected2_values,
            "projected_combo": projected_combo_values,
            "fine_dual": fine_dual_values,
            "adjoint": adjoint_values,
            coarse_action_key: b3_values,
            "b6p": b6p_values,
        }
        return facts, arrays
    finally:
        for vector in (projected, projected_repeat, source2, projected2, combo, fine_dual, adjoint, b3, b6p):
            vector.destroy()


def measure_owner_probe(
    extension: Any, *,
    pair: tuple[int, int] = (2, 1),
    probe_schema: str = ROUTE_B_PROBE_SCHEMA,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Measure one deterministic owner-packet P/P^H probe without a matrix."""

    fine_level, coarse_level = _probe_levels(
        extension, fine_degree=pair[0], coarse_degree=pair[1]
    )
    seed = _deterministic_seed(coarse_level, 71.0)
    seed2 = _deterministic_seed(coarse_level, 73.0)
    fine_seed = _deterministic_seed(fine_level, 79.0)
    source = source2 = fine_dual = None
    projected = projected_repeat = projected2 = projected_combo = combo = adjoint = None
    try:
        source = _canonical_primal(coarse_level, seed)
        source2 = _canonical_primal(coarse_level, seed2)
        fine_dual = _canonical_primal(fine_level, fine_seed)
        source_before = _vector_array(source)
        source_before_digest = _vector_digest(source)
        projected = _apply_pair(extension, pair, source, adjoint=False)
        projected_repeat = _apply_pair(extension, pair, source, adjoint=False)
        projected2 = _apply_pair(extension, pair, source2, adjoint=False)
        combo = source.copy()
        combo.scale(ALPHA)
        combo.axpy(BETA, source2)
        projected_combo = _apply_pair(extension, pair, combo, adjoint=False)
        adjoint = _apply_pair(extension, pair, fine_dual, adjoint=True)
        source_after = _vector_array(source)
        values = {
            "source_before": source_before,
            "source_after": source_after,
            "source2": _vector_array(source2),
            "projected": _vector_array(projected),
            "projected_repeat": _vector_array(projected_repeat),
            "projected2": _vector_array(projected2),
            "projected_combo": _vector_array(projected_combo),
            "fine_dual": _vector_array(fine_dual),
            "adjoint": _vector_array(adjoint),
        }
        lhs = np.vdot(values["projected"], values["fine_dual"])
        rhs = np.vdot(values["source_before"], values["adjoint"])
        repeat = _relative(values["projected_repeat"], values["projected"])
        linearity = _relative(
            values["projected_combo"],
            ALPHA * values["projected"] + BETA * values["projected2"],
        )
        phase_once = all(
            level.parent_topology.audit.get("phase_application") == "once_in_canonical_owner_route"
            and level.parent_topology.audit.get("slave_master_complete") is True
            for level in (fine_level, coarse_level)
        )
        finite = bool(all(np.all(np.isfinite(value)) for value in values.values()))
        source_norm = float(np.linalg.norm(source_before))
        facts = {
            "schema": probe_schema,
            "name": "owner_packet_deterministic",
            "pair": [int(pair[0]), int(pair[1])],
            "source_generation": "deterministic_owner_packet_p21",
            "source_norm": source_norm,
            "source_finite": bool(np.all(np.isfinite(source_before))),
            "source_nonzero": bool(source_norm > 0.0),
            "adjoint_work_relative": _relative(
                np.asarray([lhs]), np.asarray([rhs])
            ),
            "linearity_relative": linearity,
            "repeat_relative": repeat,
            "finite": finite,
            "input_unchanged": bool(np.array_equal(source_before, source_after)),
            "phase_once": phase_once,
            "source_before_digest": source_before_digest,
            "source_after_digest": _digest_array(source_after),
        }
        return facts, values
    finally:
        for vector in (
            seed, seed2, fine_seed, source, source2, fine_dual, projected,
            projected_repeat, projected2, projected_combo, combo, adjoint,
        ):
            if vector is not None:
                vector.destroy()


def _digest_array(value: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(value, dtype=np.complex128).view(np.uint8)
    ).hexdigest()


__all__ = [
    "ALPHA",
    "BETA",
    "MATERIAL_INVENTORY_SCHEMA",
    "PROBE_NAMES",
    "PROBE_SCHEMA",
    "ROUTE_B_PROBE_SCHEMA",
    "ROUTE_B_SOURCE_GENERATION",
    "R3_LONG_TAIL_MANIFEST_SHA256",
    "R3_LONG_TAIL_SOURCE_SHA",
    "audit_material_classes",
    "audit_nested_material_classes",
    "build_material_class_inventory",
    "build_material_class_inventory_from_rows",
    "build_probe_source",
    "measure_probe",
    "measure_owner_probe",
    "_probe_levels",
    "source_generation_identity",
]
