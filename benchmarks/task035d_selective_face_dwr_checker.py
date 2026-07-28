"""Independent fail-closed checker for Task035d selective-face DWR."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy import sparse

from benchmarks.task035d_case097_gates import (
    TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256,
    TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256,
    TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256,
    TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256,
)
from benchmarks.task035d_selective_face_case097_gates import (
    TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS,
    TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256,
    TASK035D_SELECTIVE_FACE_TRANSFER_ENTITY_CATALOG_SHA256,
    TASK035D_SELECTIVE_FACE_TRANSFER_FLATTENED_GRAPH_SHA256,
)


COARSE_CANDIDATE_ID = "h15_top_air_local_h_v1"
ENRICHED_CANDIDATE_ID = "h15_grating_top_selective_p6_faces_v1"
COARSE_FULL3D_EQUIVALENT_DOFS = 82_925
ENRICHED_FULL3D_EQUIVALENT_DOFS = 83_125
COARSE_SOLVE_ROWS = 18_470
ENRICHED_SOLVE_ROWS = 18_670
SELECTED_FACE_COUNT = len(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
_ROOT_TRANSFER_ROUNDOFF_LIMIT = 2.0e-10
_ENDPOINT_IDENTITY_CHECKS = {
    "same_source_sha",
    "same_mesh",
    "same_normalized_config",
    "same_ordered_modes",
    "same_cell_interior_degree_map",
    "same_incident_projections",
    "same_auxiliary_coordinate_scales",
}
_ROOT_TRANSFER_CHECKS = {
    "same_physical_entity_geometry_catalog",
    "only_selected_whole_faces_change_degree",
    "full_face_closure_embedding_is_nested",
    "edge_to_face_coupling_is_present",
    "reference_face_closure_has_no_outside_coupling",
    "physical_constraint_graph_injection_closes",
    "selected_patch_injection_is_full_rank",
    "each_graph_expanded_face_has_20_quotient_modes",
    "face_generators_form_direct_sum",
    "face_generators_are_global_complement",
    "generator_and_orthonormal_projectors_agree",
    "face_generator_gram_is_well_conditioned",
    "root_dimension_delta_is_20_per_selected_face",
    "complement_dimension_is_20_per_selected_face",
    "complement_is_solver_coordinate_orthogonal",
    "complement_is_solver_coordinate_orthonormal",
    "auxiliary_coordinates_are_identity",
    "no_hidden_global_p6_matrix",
}
_GALERKIN_CHECKS = {
    "rhs_galerkin_identity",
    "all_operator_galerkin_probes",
    "injected_coarse_solution_is_galerkin_orthogonal",
    "effective_residual_lies_in_selected_face_complement",
}


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: Any, *, namespace: str | None = None) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray, *, namespace: str) -> str:
    array = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(np.asarray(array.shape, dtype=np.dtype("<i8")).tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _csr_sha256(values: sparse.spmatrix, *, namespace: str) -> str:
    matrix = sparse.csr_matrix(values, dtype=np.complex128)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    for label, array in (
        ("shape", np.asarray(matrix.shape, dtype=np.int64)),
        ("indptr", np.asarray(matrix.indptr, dtype=np.int64)),
        ("indices", np.asarray(matrix.indices, dtype=np.int64)),
        ("data", np.asarray(matrix.data, dtype=np.complex128)),
    ):
        contiguous = np.ascontiguousarray(array)
        digest.update(label.encode("ascii"))
        digest.update(b"\0")
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(b"\0")
        digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        digest.update(contiguous.view(np.uint8))
    return digest.hexdigest()


def _transfer_csr_sha256(values: sparse.spmatrix) -> str:
    matrix = sparse.csr_matrix(values, dtype=np.complex128)
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    digest.update(np.ascontiguousarray(matrix.indptr).view(np.uint8))
    digest.update(np.ascontiguousarray(matrix.indices).view(np.uint8))
    digest.update(np.ascontiguousarray(matrix.data).view(np.uint8))
    return digest.hexdigest()


def _normalized_entity_catalog(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("selective-face physical entity catalog is absent")
    normalized: list[dict[str, Any]] = []
    observed: set[tuple[int, tuple[int, ...]]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("selective-face physical entity catalog row is invalid")
        try:
            dimension = int(row["dimension"])
            geometry_key = tuple(int(value) for value in row["geometry_key"])
            degree = int(row["degree"])
            canonical_points = [
                [int(value) for value in point] for point in row["canonical_points"]
            ]
            mode_count = int(row["mode_count"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "selective-face physical entity catalog row is malformed"
            ) from error
        identity = (dimension, geometry_key)
        if (
            dimension not in {0, 1, 2}
            or not geometry_key
            or degree != 5
            or not canonical_points
            or any(not point for point in canonical_points)
            or mode_count <= 0
            or identity in observed
            or set(row)
            != {
                "dimension",
                "geometry_key",
                "degree",
                "canonical_points",
                "mode_count",
            }
        ):
            raise ValueError("selective-face physical entity catalog semantics failed")
        observed.add(identity)
        normalized.append(
            {
                "dimension": dimension,
                "geometry_key": list(geometry_key),
                "degree": degree,
                "canonical_points": canonical_points,
                "mode_count": mode_count,
            }
        )
    return normalized


def _mode_index_by_channel(mode_identity: Any) -> dict[str, int]:
    if not isinstance(mode_identity, Mapping):
        raise ValueError("selective-face ordered mode identity is absent")
    modes = mode_identity.get("ordered_modes")
    if (
        mode_identity.get("mode_count") != 80
        or not isinstance(modes, list)
        or len(modes) != 80
        or mode_identity.get("ordered_modes_sha256")
        != _json_sha256(
            modes,
            namespace="task035d.ordered-dtn-modes.v1",
        )
    ):
        raise ValueError("selective-face ordered mode identity failed")
    result: dict[str, int] = {}
    for index, mode in enumerate(modes):
        if not isinstance(mode, Mapping):
            raise ValueError("selective-face ordered mode is malformed")
        try:
            label = _channel_label(mode)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "selective-face ordered mode channel is malformed"
            ) from error
        if (
            label in result
            or str(mode.get("side")) not in {"top", "bottom"}
            or str(mode.get("polarization")) not in {"s", "p"}
        ):
            raise ValueError(
                "selective-face ordered mode channel identity is duplicated"
            )
        result[label] = index
    return result


def load_selective_face_coarse_endpoint(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    """Load the hash-bound coarse modal endpoint without trusting the report."""

    path = Path(manifest_path).resolve()
    if (
        not path.is_file()
        or not _valid_hex(expected_manifest_sha256, 64)
        or _file_sha256(path) != expected_manifest_sha256
    ):
        raise ValueError("selective-face coarse manifest identity failed")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"selective-face coarse manifest is unreadable: {error}"
        ) from error
    if not isinstance(manifest, Mapping):
        raise ValueError("selective-face coarse manifest is not an object")
    if (
        manifest.get("schema_version") != "task035d.selective-face-coarse-snapshot.v1"
        or manifest.get("status") != "selective_face_coarse_snapshot_pass"
        or manifest.get("pass") is not True
        or manifest.get("ordinary_default_changed") is not False
        or manifest.get("base_trace_degree") != 5
        or manifest.get("independent_trace_rows") != COARSE_SOLVE_ROWS - 80
        or manifest.get("auxiliary_rows") != 80
        or manifest.get("matrix_rows") != COARSE_SOLVE_ROWS
    ):
        raise ValueError("selective-face coarse manifest semantics failed")
    arrays = manifest.get("arrays")
    if not isinstance(arrays, Mapping) or arrays.get("path") != "coarse_arrays.npz":
        raise ValueError("selective-face coarse array descriptor is invalid")
    arrays_path = (path.parent / "coarse_arrays.npz").resolve()
    if (
        arrays_path.parent != path.parent
        or not arrays_path.is_file()
        or not _valid_hex(arrays.get("sha256"), 64)
        or _file_sha256(arrays_path) != arrays.get("sha256")
    ):
        raise ValueError("selective-face coarse array identity failed")
    expected_array_names = {
        "schema_version",
        "state_b",
        "rhs_b",
        "action_b_on_b",
        "residual_b",
        "probe_vectors",
        "probe_actions",
        "auxiliary_values_b",
        "incident_projections",
        "coordinate_scales",
        "physical_graph_data",
        "physical_graph_indices",
        "physical_graph_indptr",
        "physical_graph_shape",
    }
    try:
        with np.load(arrays_path, allow_pickle=False) as payload:
            if set(payload.files) != expected_array_names:
                raise ValueError("selective-face coarse array inventory changed")
            schema = np.asarray(payload["schema_version"])
            vectors = {
                name: np.asarray(
                    payload[name],
                    dtype=np.complex128,
                ).copy()
                for name in (
                    "state_b",
                    "rhs_b",
                    "action_b_on_b",
                    "residual_b",
                    "auxiliary_values_b",
                    "incident_projections",
                    "coordinate_scales",
                )
            }
            probes = np.asarray(
                payload["probe_vectors"],
                dtype=np.complex128,
            ).copy()
            probe_actions = np.asarray(
                payload["probe_actions"],
                dtype=np.complex128,
            ).copy()
            graph_shape = np.asarray(
                payload["physical_graph_shape"],
                dtype=np.int64,
            )
            graph = sparse.csr_matrix(
                (
                    np.asarray(
                        payload["physical_graph_data"],
                        dtype=np.complex128,
                    ),
                    np.asarray(
                        payload["physical_graph_indices"],
                        dtype=np.int64,
                    ),
                    np.asarray(
                        payload["physical_graph_indptr"],
                        dtype=np.int64,
                    ),
                ),
                shape=tuple(int(value) for value in graph_shape),
            )
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"selective-face coarse endpoint arrays are invalid: {error}"
        ) from error
    endpoint = {
        name: vectors[name]
        for name in (
            "auxiliary_values_b",
            "incident_projections",
            "coordinate_scales",
        )
    }
    shapes = {values.shape for values in endpoint.values()}
    if (
        schema.shape != (1,)
        or str(schema[0]) != "task035d.selective-face-coarse-arrays.v1"
        or len(shapes) != 1
        or not shapes
        or next(iter(shapes)) != (80,)
        or any(
            vectors[name].shape != (COARSE_SOLVE_ROWS,)
            for name in (
                "state_b",
                "rhs_b",
                "action_b_on_b",
                "residual_b",
            )
        )
        or probes.shape != (COARSE_SOLVE_ROWS, 3)
        or probe_actions.shape != probes.shape
        or graph_shape.shape != (2,)
        or graph.shape != (23_875, COARSE_SOLVE_ROWS - 80)
        or any(
            not np.all(np.isfinite(values))
            for values in (*vectors.values(), probes, probe_actions)
        )
        or not np.all(np.isfinite(graph.data))
        or np.any(np.abs(endpoint["coordinate_scales"]) <= 0.0)
        or not np.array_equal(
            vectors["residual_b"],
            vectors["rhs_b"] - vectors["action_b_on_b"],
        )
        or any(
            not _roundoff_equal(
                float(np.linalg.norm(probes[:, column])),
                1.0,
                relative_tolerance=5.0e-13,
                absolute_tolerance=5.0e-13,
            )
            for column in range(3)
        )
        or np.count_nonzero(probes[-80:, 0]) != 0
        or np.count_nonzero(probes[:-80, 1]) != 0
        or np.linalg.norm(probes[:-80, 2]) <= 0.0
        or np.linalg.norm(probes[-80:, 2]) <= 0.0
    ):
        raise ValueError("selective-face coarse endpoint is malformed")
    vector_identity = manifest.get("vector_identity")
    if not isinstance(vector_identity, Mapping):
        raise ValueError("selective-face coarse vector identity is absent")
    namespaces = {
        "state_b": "task035d.selective-face-state-b.v1",
        "rhs_b": "task035d.selective-face-rhs-b.v1",
        "action_b_on_b": "task035d.selective-face-action-b.v1",
        "residual_b": "task035d.selective-face-residual-b.v1",
        "auxiliary_values_b": ("task035d.selective-face-auxiliary-values-b.v1"),
        "incident_projections": ("task035d.selective-face-incident-projections.v1"),
        "coordinate_scales": ("task035d.selective-face-coordinate-scales.v1"),
    }
    if any(
        vector_identity.get(f"{name}_sha256")
        != _array_sha256(vectors[name], namespace=namespace)
        for name, namespace in namespaces.items()
    ):
        raise ValueError("selective-face coarse vector hashes failed")
    relative_residual = float(
        np.linalg.norm(vectors["residual_b"])
        / max(
            np.linalg.norm(vectors["rhs_b"]),
            float.fromhex("0x1.0000000000000p-1022"),
        )
    )
    stored_relative = _number(vector_identity.get("relative_residual"))
    primal_residual_gate = manifest.get("primal_residual_gate")
    gate_reduced_residual = (
        _number(primal_residual_gate.get("reduced_trace_dtn_relative_residual"))
        if isinstance(primal_residual_gate, Mapping)
        else None
    )
    if (
        stored_relative is None
        or not _roundoff_equal(stored_relative, relative_residual)
        or not _residual_gate_pass(primal_residual_gate)
        or not isinstance(primal_residual_gate, Mapping)
        or gate_reduced_residual is None
        or not _roundoff_equal(
            gate_reduced_residual,
            relative_residual,
        )
    ):
        raise ValueError("selective-face coarse primal residual failed")
    probe_contract = manifest.get("probe_contract")
    if (
        not isinstance(probe_contract, Mapping)
        or probe_contract.get("probe_count") != 3
        or probe_contract.get("roles")
        != [
            "trace_only_random",
            "auxiliary_only_random",
            "combined_random",
        ]
        or probe_contract.get("probe_vectors_sha256")
        != _array_sha256(
            probes,
            namespace="task035d.selective-face-probes.v1",
        )
        or probe_contract.get("probe_actions_sha256")
        != _array_sha256(
            probe_actions,
            namespace="task035d.selective-face-probe-actions.v1",
        )
        or not isinstance(probe_contract.get("seed_identity"), Mapping)
    ):
        raise ValueError("selective-face coarse probe identity failed")
    catalog = _normalized_entity_catalog(manifest.get("physical_entity_catalog"))
    catalog_sha256 = _json_sha256(
        catalog,
        namespace="task035d.selective-face-entity-catalog.v1",
    )
    authority_catalog_sha256 = _json_sha256(
        [
            [
                row["dimension"],
                row["geometry_key"],
                row["canonical_points"],
                row["mode_count"],
            ]
            for row in catalog
        ]
    )
    transfer_catalog_sha256 = _json_sha256(catalog)
    graph_sha256 = _csr_sha256(
        graph,
        namespace="task035d.selective-face-physical-graph.v1",
    )
    transfer_graph_sha256 = _transfer_csr_sha256(graph)
    root_indices = manifest.get("physical_root_raw_indices")
    if (
        sum(int(row["mode_count"]) for row in catalog) != 23_875
        or manifest.get("physical_entity_catalog_sha256") != catalog_sha256
        or manifest.get("physical_graph_sha256") != graph_sha256
        or manifest.get("physical_authority_sha256")
        != TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
        or authority_catalog_sha256 != TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256
        or transfer_catalog_sha256
        != TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256
        or transfer_graph_sha256
        != TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256
        or not isinstance(root_indices, list)
        or len(root_indices) != COARSE_SOLVE_ROWS - 80
        or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value < 23_875
            for value in root_indices
        )
        or len(set(root_indices)) != COARSE_SOLVE_ROWS - 80
    ):
        raise ValueError("selective-face coarse physical authority identity failed")
    root_identity = graph[np.asarray(root_indices, dtype=np.int64)]
    root_error = root_identity - sparse.eye(
        COARSE_SOLVE_ROWS - 80,
        dtype=np.complex128,
        format="csr",
    )
    root_error.eliminate_zeros()
    if root_error.nnz and float(np.max(np.abs(root_error.data), initial=0.0)) > 2.0e-13:
        raise ValueError("selective-face coarse physical roots are invalid")
    candidate = manifest.get("candidate")
    significant = manifest.get("significant_channel_authority")
    normalized_config = manifest.get("normalized_config_identity")
    mesh_identity = manifest.get("mesh_identity")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("candidate_id") != COARSE_CANDIDATE_ID
        or not _valid_hex(candidate.get("source_sha"), 40)
        or not _valid_hex(candidate.get("plan_file_sha256"), 64)
        or candidate.get("actual_full3d_equivalent_active_fe_dofs")
        != COARSE_FULL3D_EQUIVALENT_DOFS
        or not _valid_hex(
            candidate.get("cell_interior_degree_sha256"),
            64,
        )
        or manifest.get("source_sha") != candidate.get("source_sha")
        or not isinstance(significant, Mapping)
        or not _valid_hex(significant.get("sha256"), 64)
        or significant.get("physical_channel_count") != 12
        or significant.get("real_goal_count") != 36
        or not isinstance(normalized_config, Mapping)
        or normalized_config.get("normalized_config_sha256")
        != _json_sha256(
            normalized_config.get("normalized_config"),
            namespace="task035d.same-trace-physics-config.v1",
        )
        or not isinstance(mesh_identity, Mapping)
        or not _valid_hex(
            mesh_identity.get("partition_independent_mesh_sha256"),
            64,
        )
    ):
        raise ValueError("selective-face coarse model identity failed")
    mode_identity = manifest.get("mode_identity")
    mode_index_by_channel = _mode_index_by_channel(mode_identity)
    expected_probe_seed = {
        "candidate": dict(candidate),
        "mesh_sha256": mesh_identity["partition_independent_mesh_sha256"],
        "config_sha256": normalized_config["normalized_config_sha256"],
        "mode_sha256": mode_identity["ordered_modes_sha256"],
        "physical_graph_sha256": graph_sha256,
    }
    ownership = manifest.get("matrix_vector_ownership_ranges")
    try:
        ownership_pairs = [
            (int(row[0]), int(row[1]))
            for row in ownership
            if (
                isinstance(row, list)
                and len(row) == 2
                and all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in row
                )
            )
        ]
    except TypeError:
        ownership_pairs = []
    if (
        probe_contract.get("seed_identity") != expected_probe_seed
        or not isinstance(ownership, list)
        or len(ownership) != 8
        or len(ownership_pairs) != 8
        or ownership_pairs[0][0] != 0
        or ownership_pairs[-1][1] != COARSE_SOLVE_ROWS
        or any(
            row[0] < 0
            or row[1] <= row[0]
            or (rank > 0 and row[0] != ownership_pairs[rank - 1][1])
            for rank, row in enumerate(ownership_pairs)
        )
    ):
        raise ValueError("selective-face coarse MPI ownership or probe seed failed")
    return {
        "manifest_path": str(path),
        "manifest_sha256": expected_manifest_sha256,
        "arrays_sha256": arrays["sha256"],
        "source_sha": manifest["source_sha"],
        "candidate": dict(candidate),
        "significant_channel_authority": dict(significant),
        "mode_identity": dict(mode_identity),
        "mode_index_by_channel": mode_index_by_channel,
        "normalized_config_identity": dict(normalized_config),
        "mesh_identity": dict(mesh_identity),
        "primal_residual_gate": dict(primal_residual_gate),
        "vector_identity": dict(vector_identity),
        "physical_entity_catalog": catalog,
        "physical_entity_catalog_sha256": catalog_sha256,
        "authority_entity_catalog_sha256": authority_catalog_sha256,
        "transfer_entity_catalog_sha256": transfer_catalog_sha256,
        "physical_graph_sha256": graph_sha256,
        "transfer_flattened_graph_sha256": transfer_graph_sha256,
        **endpoint,
    }


def _number(value: Any) -> float | None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        return None
    return float(value)


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    real = _number(value[0])
    imag = _number(value[1])
    if real is None or imag is None:
        return None
    return complex(real, imag)


def _roundoff_equal(
    observed: float,
    expected: float,
    *,
    relative_tolerance: float = 2.0e-13,
    absolute_tolerance: float = 1.0e-30,
) -> bool:
    return math.isclose(
        observed,
        expected,
        rel_tol=relative_tolerance,
        abs_tol=absolute_tolerance,
    )


def _complex_roundoff_equal(observed: complex, expected: complex) -> bool:
    scale = max(abs(observed), abs(expected), 1.0e-30)
    return abs(observed - expected) <= 2.0e-13 + 5.0e-11 * scale


def _channel_label(channel: Mapping[str, Any]) -> str:
    prefix = "R" if str(channel["side"]) == "top" else "T"
    return (
        f"{prefix}({int(channel['m'])},{int(channel['n'])})_"
        f"{str(channel['polarization'])}"
    )


def _goal_label(channel: Mapping[str, Any], quantity: str) -> str:
    prefix = "R" if str(channel["side"]) == "top" else "T"
    return (
        f"{prefix}_m{int(channel['m'])}_n{int(channel['n'])}_"
        f"{str(channel['polarization'])}_{quantity}"
    )


def _expected_inventory(
    authority: Mapping[str, Any],
) -> tuple[set[str], dict[str, float]]:
    rows = authority.get("channels")
    if not isinstance(rows, list) or len(rows) != 12:
        return set(), {}
    channels: set[str] = set()
    goals: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return set(), {}
        channel = row.get("channel")
        gate = row.get("unchanged_v0_acceptance_gate")
        if not isinstance(channel, Mapping) or not isinstance(gate, Mapping):
            return set(), {}
        try:
            channel_label = _channel_label(channel)
        except (KeyError, TypeError, ValueError):
            return set(), {}
        if channel_label in channels:
            return set(), {}
        power_tolerance = _number(gate.get("power_absolute_tolerance"))
        amplitude_tolerance = _number(gate.get("complex_amplitude_absolute_tolerance"))
        if (
            power_tolerance is None
            or power_tolerance <= 0.0
            or amplitude_tolerance is None
            or amplitude_tolerance <= 0.0
        ):
            return set(), {}
        channels.add(channel_label)
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            label = _goal_label(channel, quantity)
            goals[label] = (
                power_tolerance if quantity == "power" else amplitude_tolerance
            )
    return channels, goals


def _residual_gate_pass(gate: Any) -> bool:
    if not isinstance(gate, Mapping):
        return False
    reduced = _number(gate.get("reduced_trace_dtn_relative_residual"))
    full = _number(gate.get("full_explicit_true_relative_residual"))
    checks = gate.get("checks")
    required_checks = {
        "finite",
        "nonnegative",
        "reduced_trace_dtn_relative_residual_le_1e-9",
        "full_explicit_true_relative_residual_le_1e-9",
    }
    return bool(
        gate.get("schema_version") == "task035d.primal-residual-gate.v1"
        and gate.get("pass") is True
        and isinstance(checks, Mapping)
        and set(checks) == required_checks
        and all(value is True for value in checks.values())
        and _number(gate.get("limit")) == 1.0e-9
        and reduced is not None
        and 0.0 <= reduced <= 1.0e-9
        and full is not None
        and 0.0 <= full <= 1.0e-9
    )


def _linear_residual_report_pass(
    report: Any,
    *,
    expected_rhs_norm: float | None = None,
) -> bool:
    if not isinstance(report, Mapping):
        return False
    rhs_norm = _number(report.get("rhs_norm"))
    residual_norm = _number(report.get("residual_norm"))
    relative_residual = _number(report.get("relative_residual"))
    if (
        rhs_norm is None
        or rhs_norm <= 0.0
        or residual_norm is None
        or residual_norm < 0.0
        or relative_residual is None
        or relative_residual < 0.0
        or (
            expected_rhs_norm is not None
            and (
                expected_rhs_norm <= 0.0
                or not _roundoff_equal(rhs_norm, expected_rhs_norm)
            )
        )
    ):
        return False
    expected_relative = residual_norm / max(
        rhs_norm,
        float.fromhex("0x1.0000000000000p-1022"),
    )
    return bool(
        _roundoff_equal(relative_residual, expected_relative)
        and relative_residual <= 1.0e-9
    )


def _adjoint_content_identity_pass(identity: Any) -> bool:
    if not isinstance(identity, Mapping):
        return False
    partitions = identity.get("partitions")
    if not isinstance(partitions, list) or len(partitions) != 8:
        return False
    cursor = 0
    normalized: list[dict[str, Any]] = []
    for rank, row in enumerate(partitions):
        if not isinstance(row, Mapping):
            return False
        start = row.get("ownership_start")
        end = row.get("ownership_end")
        owned = row.get("owned_value_count")
        if (
            row.get("rank") != rank
            or row.get("world_rank") != rank
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start != cursor
            or end < start
            or owned != end - start
            or not _valid_hex(row.get("owned_content_sha256"), 64)
        ):
            return False
        normalized.append(dict(row))
        cursor = end
    if cursor != ENRICHED_SOLVE_ROWS:
        return False
    payload = {
        "schema_version": ("task035b.petsc-adjoint-partition-content.v1"),
        "global_size": ENRICHED_SOLVE_ROWS,
        "scalar_dtype": "complex128",
        "mpi_size": 8,
        "communicator_content_sha256": identity.get("communicator_content_sha256"),
        "communicator_ordered_world_ranks": list(range(8)),
        "global_value_sha256": identity.get("global_value_sha256"),
        "partitions": normalized,
    }
    communicator_payload = {
        "schema_version": "task035b.mpi-communicator-content.v1",
        "size": 8,
        "ordered_world_ranks": list(range(8)),
    }
    recomputed_communicator = hashlib.sha256(
        json.dumps(
            communicator_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    recomputed_content = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return bool(
        identity.get("schema_version") == "task035b.petsc-adjoint-partition-content.v1"
        and identity.get("global_size") == ENRICHED_SOLVE_ROWS
        and identity.get("scalar_dtype") == "complex128"
        and identity.get("mpi_size") == 8
        and identity.get("communicator_ordered_world_ranks") == list(range(8))
        and identity.get("communicator_content_sha256") == recomputed_communicator
        and _valid_hex(identity.get("global_value_sha256"), 64)
        and identity.get("global_content_sha256") == recomputed_content
    )


def _goal_scalar_from_inputs(inputs: Any) -> complex | None:
    if not isinstance(inputs, Mapping):
        return None
    quantity = inputs.get("quantity")
    coordinate_scale = _complex_pair(inputs.get("coordinate_scale"))
    boundary_phase = _complex_pair(inputs.get("boundary_phase"))
    outgoing_a = _complex_pair(inputs.get("outgoing_a"))
    outgoing_b = _complex_pair(inputs.get("outgoing_b"))
    if (
        quantity not in {"power", "amplitude_real", "amplitude_imag"}
        or coordinate_scale is None
        or abs(coordinate_scale) <= 0.0
        or boundary_phase is None
        or outgoing_a is None
        or outgoing_b is None
    ):
        return None
    if quantity == "amplitude_real":
        return complex(boundary_phase.conjugate() / coordinate_scale.conjugate())
    if quantity == "amplitude_imag":
        return complex(1j * boundary_phase.conjugate() / coordinate_scale.conjugate())
    weight = _number(inputs.get("power_weight"))
    if weight is None or weight < 0.0:
        return None
    midpoint = 0.5 * (outgoing_a + outgoing_b)
    return complex(2.0 * weight * midpoint / coordinate_scale.conjugate())


def _transfer_input_identity_pass(
    identity: Any,
    *,
    physical_authority_sha256: str,
    entity_catalog_sha256: str,
    flattened_graph_sha256: str,
    raw_trace_rows: int,
    independent_trace_rows: int,
) -> bool:
    if not isinstance(identity, Mapping):
        return False
    return bool(
        identity.get("declared_physical_authority_sha256") == physical_authority_sha256
        and identity.get("entity_catalog_sha256") == entity_catalog_sha256
        and identity.get("flattened_graph_sha256") == flattened_graph_sha256
        and identity.get("raw_trace_rows") == raw_trace_rows
        and identity.get("independent_trace_rows") == independent_trace_rows
    )


def _changed_entities_pass(rows: Any) -> bool:
    if not isinstance(rows, list) or len(rows) != SELECTED_FACE_COUNT:
        return False
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        try:
            geometry_key = tuple(int(value) for value in row["geometry_key"])
        except (KeyError, TypeError, ValueError):
            return False
        if set(row) != {
            "dimension",
            "geometry_key",
            "coarse_degree",
            "enriched_degree",
            "coarse_modes",
            "enriched_modes",
        } or geometry_key not in set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS):
            return False
        normalized.append(
            {
                "dimension": row.get("dimension"),
                "geometry_key": geometry_key,
                "coarse_degree": row.get("coarse_degree"),
                "enriched_degree": row.get("enriched_degree"),
                "coarse_modes": row.get("coarse_modes"),
                "enriched_modes": row.get("enriched_modes"),
            }
        )
    expected = [
        {
            "dimension": 2,
            "geometry_key": key,
            "coarse_degree": 5,
            "enriched_degree": 6,
            "coarse_modes": 40,
            "enriched_modes": 60,
        }
        for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS
    ]
    return sorted(normalized, key=lambda row: row["geometry_key"]) == sorted(
        expected,
        key=lambda row: row["geometry_key"],
    )


def _selected_root_support_catalog_pass(rows: Any) -> bool:
    if not isinstance(rows, list) or len(rows) != SELECTED_FACE_COUNT:
        return False
    normalized_keys: set[tuple[int, ...]] = set()
    constrained_rows = 0
    expected_fields = {
        "geometry_key",
        "physical_closure_rows",
        "independent_root_support_rows",
        "constrained_physical_closure_rows",
        "coarse_root_support_columns",
        "local_injection_rank",
        "local_rank_tolerance",
        "local_smallest_singular_value",
        "local_condition_number",
        "local_complement_dimension",
    }
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            return False
        try:
            key = tuple(int(value) for value in row["geometry_key"])
            support = int(row["independent_root_support_rows"])
            constrained = int(row["constrained_physical_closure_rows"])
            coarse = int(row["coarse_root_support_columns"])
            rank = int(row["local_injection_rank"])
            tolerance = float(row["local_rank_tolerance"])
            smallest = float(row["local_smallest_singular_value"])
            condition = float(row["local_condition_number"])
            complement = int(row["local_complement_dimension"])
        except (KeyError, TypeError, ValueError):
            return False
        if (
            key not in set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
            or row["physical_closure_rows"] != 80
            or support <= 0
            or constrained < 0
            or constrained > 80
            or coarse <= 0
            or rank != coarse
            or not math.isfinite(tolerance)
            or tolerance < 0.0
            or not math.isfinite(smallest)
            or smallest <= tolerance
            or not math.isfinite(condition)
            or condition < 1.0
            or condition > 1.0e8
            or support - rank != 20
            or complement != 20
        ):
            return False
        normalized_keys.add(key)
        constrained_rows += constrained
    return bool(
        normalized_keys == set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
        and constrained_rows > 0
    )


def _rank_statistics_pass(
    row: Mapping[str, Any],
    *,
    tolerance_field: str,
    smallest_field: str,
    condition_field: str,
) -> bool:
    tolerance = _number(row.get(tolerance_field))
    smallest = _number(row.get(smallest_field))
    condition = _number(row.get(condition_field))
    return bool(
        tolerance is not None
        and tolerance >= 0.0
        and smallest is not None
        and smallest > tolerance
        and condition is not None
        and 1.0 <= condition <= 1.0e8
    )


def _unit_pairing_content_pass(
    content: Any,
    identity: Any,
    *,
    expected_channels: set[str],
) -> bool:
    if not isinstance(content, Mapping) or set(content) != expected_channels:
        return False
    if not isinstance(identity, Mapping):
        return False
    expected_face_keys = {
        str(key) for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS
    }
    for row in content.values():
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "effective",
                "unexplained",
                "faces",
                "adjoint_l2_norm",
            }
            or _complex_pair(row.get("effective")) is None
            or _complex_pair(row.get("unexplained")) is None
        ):
            return False
        norm = _number(row.get("adjoint_l2_norm"))
        faces = row.get("faces")
        if (
            norm is None
            or norm <= 0.0
            or not isinstance(faces, Mapping)
            or set(faces) != expected_face_keys
            or any(
                _complex_pair(value) is None
                for value in faces.values()
            )
        ):
            return False
    return bool(
        identity.get("schema_version")
        == "task035d.selective-face-unit-pairing-content.v1"
        and identity.get("sha256")
        == _json_sha256(
            content,
            namespace="task035d.selective-face-unit-pairings.v1",
        )
        and identity.get("mpi_size") == 8
        and identity.get("all_ranks_identical") is True
    )


def _basis_report_pass(
    basis: Mapping[str, Any],
    *,
    basis_channels: Mapping[str, Any],
    basis_goals: Mapping[str, Any],
    expected_channels: set[str],
    expected_goal_labels: set[str],
    mode_index_by_channel: Mapping[str, int],
) -> bool:
    if (
        basis.get("schema_version")
        != "task035d.actual-dtn-unit-channel-adjoint-basis.v2"
        or basis.get("status") != "actual_dtn_unit_channel_adjoint_basis_pass"
        or basis.get("pass") is not True
        or basis.get("actual_discrete_system") is not True
        or basis.get("ordinary_default_changed") is not False
        or basis.get("requested_real_goal_count") != 36
        or basis.get("independent_power_goal_count") != 12
        or basis.get("independent_complex_amplitude_component_goal_count") != 24
        or basis.get("complete_complex_amplitude_channel_count") != 12
        or basis.get("physical_channel_count") != 12
        or basis.get("unit_adjoint_solve_count") != 12
        or basis.get("uncompressed_adjoint_solve_count") != 36
        or basis.get("complex_linear_backsolve_basis_rank") != 12
        or basis.get("expected_complex_linear_backsolve_basis_rank") != 12
        or basis.get("real_functional_gradient_span_rank") != 24
        or basis.get("expected_real_functional_gradient_span_rank") != 24
        or basis.get("one_unit_gradient_per_auxiliary_coordinate") is not True
        or basis.get("per_goal_scaled_adjoint_residual_checked") is not True
        or basis.get("complex_conjugation") != "Hermitian A^H, never plain transpose"
        or set(basis_channels) != expected_channels
        or set(basis_goals) != expected_goal_labels
        or not expected_channels <= set(mode_index_by_channel)
    ):
        return False

    labels_by_channel = {label: set() for label in expected_channels}
    mode_by_channel: dict[str, int] = {}
    for label, row in basis_goals.items():
        if not isinstance(row, Mapping):
            return False
        metadata = row.get("goal")
        if not isinstance(metadata, Mapping):
            return False
        try:
            channel_label = _channel_label(metadata)
            expected_label = _goal_label(
                metadata,
                str(metadata["quantity"]),
            )
        except (KeyError, TypeError, ValueError):
            return False
        mode_index = row.get("auxiliary_mode_index")
        augmented_index = row.get("augmented_global_index")
        gradient_norm = _number(row.get("gradient_norm"))
        gradient_scaling_error = _number(row.get("gradient_scaling_relative_error"))
        gradient_scalar = _complex_pair(row.get("gradient_scalar_solver_coordinate"))
        if (
            channel_label not in labels_by_channel
            or expected_label != label
            or metadata.get("label") != label
            or metadata.get("quantity")
            not in {"power", "amplitude_real", "amplitude_imag"}
            or row.get("pass") is not True
            or row.get("actual_discrete_system") is not True
            or row.get("independent_factor_backsolve_performed") is not False
            or row.get("recovered_from_unit_channel_adjoint") is not True
            or not isinstance(mode_index, int)
            or not 0 <= mode_index < 80
            or mode_index != mode_index_by_channel.get(channel_label)
            or augmented_index != ENRICHED_SOLVE_ROWS - 80 + mode_index
            or gradient_norm is None
            or gradient_norm <= 0.0
            or gradient_scaling_error is None
            or not 0.0 <= gradient_scaling_error <= 5.0e-13
            or gradient_scalar is None
            or not _roundoff_equal(
                gradient_norm,
                abs(gradient_scalar),
            )
            or _complex_pair(row.get("unit_adjoint_scalar")) is None
            or _complex_pair(row.get("outgoing_amplitude")) is None
            or _complex_pair(row.get("boundary_phase")) is None
            or _complex_pair(row.get("auxiliary_coordinate_scale")) is None
            or not _linear_residual_report_pass(
                row.get("scaled_adjoint_residual"),
                expected_rhs_norm=gradient_norm,
            )
        ):
            return False
        previous_mode = mode_by_channel.setdefault(channel_label, mode_index)
        if previous_mode != mode_index:
            return False
        labels_by_channel[channel_label].add(label)

    observed_channel_modes: set[int] = set()
    observed_global_value_hashes: set[str] = set()
    observed_global_content_hashes: set[str] = set()
    for label, row in basis_channels.items():
        if not isinstance(row, Mapping):
            return False
        canonical = row.get("canonical_channel_identity")
        try:
            canonical_label = (
                _channel_label(canonical) if isinstance(canonical, Mapping) else ""
            )
        except (KeyError, TypeError, ValueError):
            return False
        mode_index = row.get("auxiliary_mode_index")
        unit_norm = _number(row.get("unit_adjoint_l2_norm"))
        identity = row.get("unit_adjoint_content_identity")
        if (
            canonical_label != label
            or row.get("schema_version") != "task035d.dtn-unit-channel-gradient.v1"
            or row.get("status") != "dtn_unit_channel_gradient_built"
            or row.get("pass") is not True
            or row.get("ordinary_default_changed") is not False
            or not isinstance(mode_index, int)
            or not 0 <= mode_index < 80
            or mode_index != mode_by_channel.get(label)
            or mode_index != mode_index_by_channel.get(label)
            or mode_index in observed_channel_modes
            or row.get("augmented_global_index")
            != ENRICHED_SOLVE_ROWS - 80 + mode_index
            or row.get("solver_coordinate_gradient") != [1.0, 0.0]
            or not _roundoff_equal(
                _number(row.get("gradient_norm")) or -1.0,
                1.0,
            )
            or not isinstance(row.get("transpose_converged_reason"), int)
            or row.get("transpose_converged_reason") <= 0
            or row.get("complex_adjoint_equation") != "A^H z = g"
            or row.get("forward_factor_reused") is not True
            or row.get("independent_factor_backsolve_performed") is not True
            or row.get("goal_count") != 3
            or set(row.get("goal_labels", ())) != labels_by_channel[label]
            or not _linear_residual_report_pass(
                row.get("adjoint_residual"),
                expected_rhs_norm=1.0,
            )
            or not _adjoint_content_identity_pass(identity)
            or not isinstance(identity, Mapping)
            or row.get("unit_adjoint_content_sha256")
            != identity.get("global_value_sha256")
            or unit_norm is None
            or unit_norm <= 0.0
            or identity.get("global_value_sha256") in observed_global_value_hashes
            or identity.get("global_content_sha256") in observed_global_content_hashes
        ):
            return False
        observed_channel_modes.add(mode_index)
        observed_global_value_hashes.add(str(identity["global_value_sha256"]))
        observed_global_content_hashes.add(str(identity["global_content_sha256"]))
    return bool(
        len(observed_channel_modes) == 12
        and len(observed_global_value_hashes) == 12
        and len(observed_global_content_hashes) == 12
    )


def _relative_gate_pass(
    gate: Any,
    *,
    absolute: float,
    relative: float,
) -> bool:
    if not isinstance(gate, Mapping):
        return False
    error = _number(gate.get("error_l2_norm"))
    scale = _number(gate.get("scale_l2_norm"))
    stored_relative = _number(gate.get("relative_error"))
    stored_limit = _number(gate.get("acceptance_limit"))
    if (
        error is None
        or error < 0.0
        or scale is None
        or scale <= 0.0
        or stored_relative is None
        or stored_limit is None
    ):
        return False
    limit = absolute + relative * scale
    return bool(
        _roundoff_equal(stored_relative, error / scale)
        and _roundoff_equal(stored_limit, limit)
        and error <= limit
    )


def _galerkin_audit_pass(galerkin: Mapping[str, Any]) -> bool:
    probes = galerkin.get("operator_probes")
    residuals = galerkin.get("residuals")
    stored_checks = galerkin.get("checks")
    if (
        not isinstance(probes, list)
        or not isinstance(residuals, Mapping)
        or not isinstance(stored_checks, Mapping)
        or set(stored_checks) != _GALERKIN_CHECKS
        or not all(value is True for value in stored_checks.values())
    ):
        return False
    coarse_norm = _number(residuals.get("coarse_l2_norm"))
    enriched_norm = _number(residuals.get("enriched_endpoint_l2_norm"))
    complement_error = _number(residuals.get("complement_unexplained_l2_norm"))
    stored_complement_limit = _number(residuals.get("complement_unexplained_limit"))
    if (
        coarse_norm is None
        or coarse_norm < 0.0
        or enriched_norm is None
        or enriched_norm < 0.0
        or complement_error is None
        or complement_error < 0.0
        or stored_complement_limit is None
    ):
        return False
    complement_limit = 5.0e-9 + 20.0 * (coarse_norm + enriched_norm)
    return bool(
        galerkin.get("schema_version")
        == "task035d.selective-face-cross-trace-galerkin-audit.v1"
        and galerkin.get("status") == "selective_face_cross_trace_galerkin_pass"
        and galerkin.get("pass") is True
        and _relative_gate_pass(
            galerkin.get("rhs"),
            absolute=5.0e-10,
            relative=2.0e-9,
        )
        and len(probes) == 3
        and all(
            isinstance(row, Mapping)
            and row.get("probe") == index
            and _relative_gate_pass(
                row,
                absolute=5.0e-10,
                relative=2.0e-9,
            )
            for index, row in enumerate(probes)
        )
        and _relative_gate_pass(
            galerkin.get("injected_coarse_galerkin_orthogonality"),
            absolute=1.0e-9,
            relative=5.0e-9,
        )
        and _roundoff_equal(
            stored_complement_limit,
            complement_limit,
        )
        and complement_error <= complement_limit
        and galerkin.get("full_matrix_equality_claimed") is False
        and galerkin.get("actual_endpoint_dwr_closure_is_mandatory") is True
    )


def _goal_closure_audit(
    label: str,
    goal: Any,
    *,
    basis_channels: Mapping[str, Any],
    basis_goals: Mapping[str, Any],
    unit_pairings: Mapping[str, Any],
    coarse_endpoint: Mapping[str, Any],
    state_delta_l2_norm: float | None,
    complement_unexplained_limit: float | None,
    tolerance: float,
) -> dict[str, Any]:
    failure = {
        "pass": False,
        "quantity": None,
        "face_values": {},
    }
    if not isinstance(goal, Mapping):
        return failure
    metadata = goal.get("goal")
    if not isinstance(metadata, Mapping):
        return failure
    try:
        channel_label = _channel_label(metadata)
        quantity = str(metadata["quantity"])
        expected_label = _goal_label(metadata, quantity)
    except (KeyError, TypeError, ValueError):
        return failure
    channel = basis_channels.get(channel_label)
    basis_goal = basis_goals.get(label)
    unit_pairing = unit_pairings.get(channel_label)
    if (
        not isinstance(channel, Mapping)
        or not isinstance(basis_goal, Mapping)
        or not isinstance(unit_pairing, Mapping)
        or expected_label != label
        or metadata.get("label") != label
        or basis_goal.get("goal") != metadata
    ):
        return failure
    unit_effective = _complex_pair(unit_pairing.get("effective"))
    unit_unexplained = _complex_pair(unit_pairing.get("unexplained"))
    unit_faces = unit_pairing.get("faces")
    unit_pairing_l2_norm = _number(unit_pairing.get("adjoint_l2_norm"))
    actual = _number(goal.get("actual_goal_delta_a_minus_b"))
    estimate = _number(goal.get("signed_dwr_estimate"))
    value_a = _number(goal.get("value_a"))
    value_b = _number(goal.get("value_b"))
    stored_error = _number(goal.get("signed_goal_closure_error"))
    stored_limit = _number(goal.get("goal_closure_limit"))
    stored_residual_bound = _number(goal.get("unit_adjoint_residual_error_bound"))
    unit_adjoint_l2_norm = _number(goal.get("unit_adjoint_l2_norm"))
    gamma = _complex_pair(goal.get("unit_adjoint_goal_scalar"))
    scalar_inputs = goal.get("goal_scalar_inputs")
    recomputed_gamma = _goal_scalar_from_inputs(scalar_inputs)
    global_pairing = _complex_pair(goal.get("global_complex_pairing"))
    stored_face_sum = _complex_pair(goal.get("selected_face_complex_pairing_sum"))
    stored_face_error = _complex_pair(goal.get("selected_face_pairing_closure_error"))
    unexplained_pairing = _complex_pair(
        goal.get("unexplained_residual_complex_pairing")
    )
    residual = channel.get("adjoint_residual")
    residual = residual if isinstance(residual, Mapping) else {}
    residual_norm = _number(residual.get("residual_norm"))
    face_rows = goal.get("face_contributions")
    try:
        mode_index = int(basis_goal["auxiliary_mode_index"])
        coarse_auxiliary = complex(coarse_endpoint["auxiliary_values_b"][mode_index])
        coarse_incident = complex(coarse_endpoint["incident_projections"][mode_index])
        coarse_scale = complex(coarse_endpoint["coordinate_scales"][mode_index])
    except (IndexError, KeyError, TypeError, ValueError):
        return failure
    expected_outgoing_b = (
        coarse_auxiliary - coarse_incident
        if metadata.get("side") == "top"
        else coarse_auxiliary
    )
    expected_outgoing_a = _complex_pair(basis_goal.get("outgoing_amplitude"))
    expected_boundary_phase = _complex_pair(basis_goal.get("boundary_phase"))
    expected_power_weight = (
        None
        if basis_goal.get("power_weight") is None
        else _number(basis_goal.get("power_weight"))
    )
    basis_gradient_scalar = _complex_pair(
        basis_goal.get("gradient_scalar_solver_coordinate")
    )
    basis_unit_scalar = _complex_pair(basis_goal.get("unit_adjoint_scalar"))
    basis_scale = _complex_pair(basis_goal.get("auxiliary_coordinate_scale"))
    basis_goal_value = _number(basis_goal.get("goal_value"))
    channel_unit_norm = _number(channel.get("unit_adjoint_l2_norm"))
    input_scale = (
        _complex_pair(scalar_inputs.get("coordinate_scale"))
        if isinstance(scalar_inputs, Mapping)
        else None
    )
    input_phase = (
        _complex_pair(scalar_inputs.get("boundary_phase"))
        if isinstance(scalar_inputs, Mapping)
        else None
    )
    input_outgoing_a = (
        _complex_pair(scalar_inputs.get("outgoing_a"))
        if isinstance(scalar_inputs, Mapping)
        else None
    )
    input_outgoing_b = (
        _complex_pair(scalar_inputs.get("outgoing_b"))
        if isinstance(scalar_inputs, Mapping)
        else None
    )
    input_power_weight = (
        _number(scalar_inputs.get("power_weight"))
        if isinstance(scalar_inputs, Mapping)
        and scalar_inputs.get("power_weight") is not None
        else None
    )
    basis_scalar_inputs = (
        {
            **dict(scalar_inputs),
            "outgoing_b": (
                scalar_inputs.get("outgoing_a")
                if isinstance(scalar_inputs, Mapping)
                else None
            ),
        }
        if isinstance(scalar_inputs, Mapping)
        else None
    )
    recomputed_basis_scalar = _goal_scalar_from_inputs(basis_scalar_inputs)
    if (
        actual is None
        or estimate is None
        or value_a is None
        or value_b is None
        or stored_error is None
        or stored_limit is None
        or stored_residual_bound is None
        or unit_adjoint_l2_norm is None
        or unit_adjoint_l2_norm < 0.0
        or gamma is None
        or recomputed_gamma is None
        or global_pairing is None
        or stored_face_sum is None
        or stored_face_error is None
        or unexplained_pairing is None
        or residual_norm is None
        or residual_norm < 0.0
        or expected_outgoing_a is None
        or expected_boundary_phase is None
        or basis_gradient_scalar is None
        or basis_unit_scalar is None
        or basis_scale is None
        or basis_goal_value is None
        or channel_unit_norm is None
        or channel_unit_norm < 0.0
        or unit_effective is None
        or unit_unexplained is None
        or not isinstance(unit_faces, Mapping)
        or unit_pairing_l2_norm is None
        or unit_pairing_l2_norm <= 0.0
        or recomputed_basis_scalar is None
        or input_scale is None
        or input_phase is None
        or input_outgoing_a is None
        or input_outgoing_b is None
        or state_delta_l2_norm is None
        or state_delta_l2_norm < 0.0
        or complement_unexplained_limit is None
        or complement_unexplained_limit < 0.0
        or not isinstance(face_rows, list)
        or len(face_rows) != SELECTED_FACE_COUNT
    ):
        return failure

    if quantity == "power":
        if (
            expected_power_weight is None
            or input_power_weight is None
            or expected_power_weight < 0.0
        ):
            return failure
        expected_value_a = expected_power_weight * abs(expected_outgoing_a) ** 2
        expected_value_b = expected_power_weight * abs(expected_outgoing_b) ** 2
    else:
        if expected_power_weight is not None or input_power_weight is not None:
            return failure
        boundary_a = expected_outgoing_a * expected_boundary_phase
        boundary_b = expected_outgoing_b * expected_boundary_phase
        expected_value_a = (
            boundary_a.real if quantity == "amplitude_real" else boundary_a.imag
        )
        expected_value_b = (
            boundary_b.real if quantity == "amplitude_real" else boundary_b.imag
        )

    recomputed_actual = value_a - value_b
    recomputed_error = estimate - recomputed_actual
    residual_bound = abs(gamma) * residual_norm * state_delta_l2_norm
    roundoff = (
        512.0
        * math.ulp(1.0)
        * max(
            abs(value_a),
            abs(value_b),
            abs(recomputed_actual),
            abs(estimate),
            1.0,
        )
    )
    closure_limit = 8.0 * (residual_bound + roundoff)

    expected_face_keys = set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
    expected_unit_face_keys = {str(key) for key in expected_face_keys}
    face_values: dict[tuple[int, ...], dict[str, float | complex]] = {}
    face_sum = 0.0 + 0.0j
    face_absolute_sum = 0.0
    face_rows_valid = True
    for row in face_rows:
        if not isinstance(row, Mapping):
            face_rows_valid = False
            continue
        raw_key = row.get("geometry_key")
        try:
            key = tuple(int(value) for value in raw_key)
        except (TypeError, ValueError):
            face_rows_valid = False
            continue
        pairing = _complex_pair(row.get("complex_pairing"))
        unit_face_pairing = _complex_pair(unit_faces.get(str(key)))
        signed = _number(row.get("signed_real_contribution"))
        absolute = _number(row.get("absolute_marking_weight"))
        normalized = _number(row.get("normalized_absolute_contribution"))
        if (
            key in face_values
            or key not in expected_face_keys
            or pairing is None
            or unit_face_pairing is None
            or signed is None
            or absolute is None
            or normalized is None
            or not _roundoff_equal(signed, pairing.real)
            or not _roundoff_equal(absolute, abs(signed))
            or not _roundoff_equal(normalized, abs(signed) / tolerance)
            or not _complex_roundoff_equal(
                pairing,
                np.conj(gamma) * unit_face_pairing,
            )
        ):
            face_rows_valid = False
            continue
        face_values[key] = {
            "signed": signed,
            "normalized": normalized,
            "pairing": pairing,
        }
        face_sum += pairing
        face_absolute_sum += abs(pairing)

    face_error = global_pairing - face_sum
    face_roundoff = (
        512.0
        * math.ulp(1.0)
        * max(abs(global_pairing), face_absolute_sum, tolerance, 1.0)
    )
    face_residual_bound = (
        abs(gamma) * unit_adjoint_l2_norm * complement_unexplained_limit
    )
    face_theoretical_limit = 8.0 * (face_residual_bound + face_roundoff)
    face_tolerance_budget = 0.05 * tolerance
    face_closure_limit = max(
        8.0 * face_roundoff,
        min(face_theoretical_limit, face_tolerance_budget),
    )
    stored_face_limit = _number(goal.get("selected_face_pairing_closure_limit"))
    stored_face_theoretical = _number(
        goal.get("selected_face_pairing_theoretical_limit")
    )
    stored_face_budget = _number(goal.get("selected_face_pairing_tolerance_budget"))
    stored_tolerance = _number(goal.get("unchanged_v0_absolute_tolerance"))
    gradient_scaling_error = _number(basis_goal.get("gradient_scaling_relative_error"))
    passed = bool(
        face_rows_valid
        and set(face_values) == expected_face_keys
        and set(unit_faces) == expected_unit_face_keys
        and isinstance(scalar_inputs, Mapping)
        and scalar_inputs.get("quantity") == quantity
        and _linear_residual_report_pass(residual)
        and _linear_residual_report_pass(basis_goal.get("scaled_adjoint_residual"))
        and basis_goal.get("actual_discrete_system") is True
        and basis_goal.get("independent_factor_backsolve_performed") is False
        and basis_goal.get("recovered_from_unit_channel_adjoint") is True
        and basis_goal.get("unit_channel_label") == channel_label
        and gradient_scaling_error is not None
        and gradient_scaling_error <= 5.0e-13
        and _complex_roundoff_equal(
            basis_gradient_scalar,
            basis_unit_scalar,
        )
        and _complex_roundoff_equal(
            basis_gradient_scalar,
            recomputed_basis_scalar,
        )
        and _complex_roundoff_equal(basis_scale, coarse_scale)
        and _roundoff_equal(basis_goal_value, expected_value_a)
        and _roundoff_equal(unit_adjoint_l2_norm, channel_unit_norm)
        and _roundoff_equal(unit_adjoint_l2_norm, unit_pairing_l2_norm)
        and _complex_roundoff_equal(input_scale, coarse_scale)
        and _complex_roundoff_equal(
            input_phase,
            expected_boundary_phase,
        )
        and _complex_roundoff_equal(
            input_outgoing_a,
            expected_outgoing_a,
        )
        and _complex_roundoff_equal(
            input_outgoing_b,
            expected_outgoing_b,
        )
        and (
            quantity != "power"
            or (
                input_power_weight is not None
                and expected_power_weight is not None
                and _roundoff_equal(
                    input_power_weight,
                    expected_power_weight,
                )
            )
        )
        and _complex_roundoff_equal(gamma, recomputed_gamma)
        and goal.get("scaling_semantics")
        == (
            "exact_A_B_midpoint_power_gradient"
            if quantity == "power"
            else "exact_affine_amplitude_gradient"
        )
        and _roundoff_equal(value_a, expected_value_a)
        and _roundoff_equal(value_b, expected_value_b)
        and _roundoff_equal(actual, recomputed_actual)
        and _roundoff_equal(stored_error, recomputed_error)
        and _roundoff_equal(stored_residual_bound, residual_bound)
        and _roundoff_equal(stored_limit, closure_limit)
        and abs(recomputed_error) <= closure_limit
        and _roundoff_equal(global_pairing.real, estimate)
        and _complex_roundoff_equal(
            global_pairing,
            np.conj(gamma) * unit_effective,
        )
        and _complex_roundoff_equal(stored_face_sum, face_sum)
        and _complex_roundoff_equal(stored_face_error, face_error)
        and _complex_roundoff_equal(unexplained_pairing, face_error)
        and _complex_roundoff_equal(
            unexplained_pairing,
            np.conj(gamma) * unit_unexplained,
        )
        and stored_face_limit is not None
        and _roundoff_equal(stored_face_limit, face_closure_limit)
        and stored_face_theoretical is not None
        and _roundoff_equal(
            stored_face_theoretical,
            face_theoretical_limit,
        )
        and stored_face_budget is not None
        and _roundoff_equal(stored_face_budget, face_tolerance_budget)
        and stored_tolerance is not None
        and _roundoff_equal(stored_tolerance, tolerance)
        and abs(face_error) <= face_closure_limit
        and goal.get("endpoint_closure_does_not_use_partition_error") is True
        and goal.get("selected_face_pairing_closure_pass") is True
        and goal.get("pass") is True
    )
    return {
        "pass": passed,
        "quantity": quantity,
        "face_values": face_values,
    }


def _marking_audit(
    marking: Mapping[str, Any],
    *,
    goal_audits: Mapping[str, Mapping[str, Any]],
    expected_goal_labels: set[str],
) -> dict[str, Any]:
    expected_face_keys = set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
    ranked = marking.get("ranked_faces")
    if not isinstance(ranked, list):
        return {"pass": False, "ranked_face_count": 0}
    accumulated = {
        key: {
            "goal_contributions": {},
            "maximum": 0.0,
            "sum": 0.0,
        }
        for key in expected_face_keys
    }
    for label, audit in goal_audits.items():
        values = audit.get("face_values")
        if not isinstance(values, Mapping):
            continue
        for key, value in values.items():
            if key not in accumulated or not isinstance(value, Mapping):
                continue
            signed = _number(value.get("signed"))
            normalized = _number(value.get("normalized"))
            if signed is None or normalized is None:
                continue
            accumulated[key]["goal_contributions"][label] = signed
            accumulated[key]["maximum"] = max(
                float(accumulated[key]["maximum"]),
                normalized,
            )
            accumulated[key]["sum"] = float(accumulated[key]["sum"]) + normalized

    observed_keys: list[tuple[int, ...]] = []
    rows_pass = True
    for row in ranked:
        if not isinstance(row, Mapping):
            rows_pass = False
            continue
        try:
            key = tuple(int(value) for value in row.get("geometry_key", ()))
        except (TypeError, ValueError):
            rows_pass = False
            continue
        maximum = _number(row.get("maximum_normalized_absolute_contribution"))
        total = _number(row.get("sum_normalized_absolute_contribution"))
        contributions = row.get("goal_contributions")
        expected = accumulated.get(key)
        if (
            key in observed_keys
            or expected is None
            or maximum is None
            or total is None
            or not isinstance(contributions, Mapping)
            or set(contributions) != expected_goal_labels
            or set(expected["goal_contributions"]) != expected_goal_labels
            or not _roundoff_equal(maximum, float(expected["maximum"]))
            or not _roundoff_equal(total, float(expected["sum"]))
            or any(
                _number(contributions.get(label)) is None
                or not _roundoff_equal(
                    float(contributions[label]),
                    float(expected["goal_contributions"][label]),
                )
                for label in expected_goal_labels
            )
        ):
            rows_pass = False
        observed_keys.append(key)
    expected_order = sorted(
        expected_face_keys,
        key=lambda key: (
            -float(accumulated[key]["maximum"]),
            key,
        ),
    )
    passed = bool(
        rows_pass
        and marking.get("face_count") == SELECTED_FACE_COUNT
        and len(ranked) == SELECTED_FACE_COUNT
        and observed_keys == expected_order
        and marking.get("signed_contributions_used_for_goal_closure") is True
        and marking.get("absolute_contributions_used_for_marking_only") is True
    )
    return {
        "pass": passed,
        "ranked_face_count": len(ranked),
        "observed_geometry_keys": [list(key) for key in observed_keys],
        "expected_geometry_keys": [list(key) for key in expected_order],
    }


def task035d_selective_face_dwr_report_gate(
    report: Mapping[str, Any] | None,
    significant_channel_authority: Mapping[str, Any] | None,
    coarse_snapshot_endpoint: Mapping[str, Any] | None,
    *,
    expected_source_sha: str,
    expected_coarse_plan_sha256: str,
    expected_enriched_plan_sha256: str,
    expected_coarse_manifest_sha256: str,
    expected_significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Recompute the formal cross-trace DWR verdict from raw report fields."""

    report = report if isinstance(report, Mapping) else {}
    significant_channel_authority = (
        significant_channel_authority
        if isinstance(significant_channel_authority, Mapping)
        else {}
    )
    coarse_snapshot_endpoint = (
        coarse_snapshot_endpoint
        if isinstance(coarse_snapshot_endpoint, Mapping)
        else {}
    )
    expected_channels, expected_goal_tolerances = _expected_inventory(
        significant_channel_authority
    )
    coarse = report.get("coarse_snapshot")
    coarse = coarse if isinstance(coarse, Mapping) else {}
    coarse_candidate = coarse.get("candidate")
    coarse_candidate = coarse_candidate if isinstance(coarse_candidate, Mapping) else {}
    enriched = report.get("enriched_candidate")
    enriched = enriched if isinstance(enriched, Mapping) else {}
    identity = report.get("identity_checks")
    identity = identity if isinstance(identity, Mapping) else {}
    endpoint_authorities = report.get("endpoint_identity_authorities")
    endpoint_authorities = (
        endpoint_authorities if isinstance(endpoint_authorities, Mapping) else {}
    )
    coarse_endpoint_authority = endpoint_authorities.get("coarse")
    coarse_endpoint_authority = (
        coarse_endpoint_authority
        if isinstance(coarse_endpoint_authority, Mapping)
        else {}
    )
    enriched_endpoint_authority = endpoint_authorities.get("enriched")
    enriched_endpoint_authority = (
        enriched_endpoint_authority
        if isinstance(enriched_endpoint_authority, Mapping)
        else {}
    )
    transfer = report.get("root_transfer")
    transfer = transfer if isinstance(transfer, Mapping) else {}
    transfer_checks = transfer.get("checks")
    transfer_checks = transfer_checks if isinstance(transfer_checks, Mapping) else {}
    galerkin = report.get("galerkin_audit")
    galerkin = galerkin if isinstance(galerkin, Mapping) else {}
    primal = report.get("primal_endpoints")
    primal = primal if isinstance(primal, Mapping) else {}
    basis = report.get("unit_channel_adjoint_basis")
    basis = basis if isinstance(basis, Mapping) else {}
    basis_channels = basis.get("channels")
    basis_channels = basis_channels if isinstance(basis_channels, Mapping) else {}
    basis_goals = basis.get("goals")
    basis_goals = basis_goals if isinstance(basis_goals, Mapping) else {}
    unit_pairing_content = report.get("unit_pairing_content")
    unit_pairing_identity = report.get(
        "unit_pairing_content_identity"
    )
    goals = report.get("goal_dwr")
    goals = goals if isinstance(goals, Mapping) else {}
    goal_rows = goals.get("goals")
    goal_rows = goal_rows if isinstance(goal_rows, Mapping) else {}
    marking = report.get("selected_face_multigoal_marking")
    marking = marking if isinstance(marking, Mapping) else {}
    authority = report.get("significant_channel_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    boundary = report.get("formal_boundary")
    boundary = boundary if isinstance(boundary, Mapping) else {}
    state_delta = _number(primal.get("state_delta_l2_norm"))
    galerkin_residuals = galerkin.get("residuals")
    galerkin_residuals = (
        galerkin_residuals if isinstance(galerkin_residuals, Mapping) else {}
    )
    complement_limit = _number(galerkin_residuals.get("complement_unexplained_limit"))
    raw_mode_index_by_channel = coarse_snapshot_endpoint.get("mode_index_by_channel")
    raw_mode_index_by_channel = (
        raw_mode_index_by_channel
        if isinstance(raw_mode_index_by_channel, Mapping)
        else {}
    )

    channel_residuals_pass = bool(
        set(basis_channels) == expected_channels
        and all(
            isinstance(row, Mapping)
            and row.get("pass") is True
            and _linear_residual_report_pass(
                row.get("adjoint_residual"),
                expected_rhs_norm=1.0,
            )
            for row in basis_channels.values()
        )
    )
    goal_residuals_pass = bool(
        set(basis_goals) == set(expected_goal_tolerances)
        and all(
            isinstance(row, Mapping)
            and row.get("pass") is True
            and (_number(row.get("gradient_norm")) or 0.0) > 0.0
            and _linear_residual_report_pass(
                row.get("scaled_adjoint_residual"),
                expected_rhs_norm=_number(row.get("gradient_norm")),
            )
            for row in basis_goals.values()
        )
    )
    basis_schema_pass = _basis_report_pass(
        basis,
        basis_channels=basis_channels,
        basis_goals=basis_goals,
        expected_channels=expected_channels,
        expected_goal_labels=set(expected_goal_tolerances),
        mode_index_by_channel=raw_mode_index_by_channel,
    )
    goal_audits = {
        label: _goal_closure_audit(
            label,
            goal_rows.get(label),
            basis_channels=basis_channels,
            basis_goals=basis_goals,
            unit_pairings=(
                unit_pairing_content
                if isinstance(unit_pairing_content, Mapping)
                else {}
            ),
            coarse_endpoint=coarse_snapshot_endpoint,
            state_delta_l2_norm=state_delta,
            complement_unexplained_limit=complement_limit,
            tolerance=tolerance,
        )
        for label, tolerance in expected_goal_tolerances.items()
    }
    failed_goal_labels = sorted(
        label for label, audit in goal_audits.items() if audit["pass"] is not True
    )
    power_pass_count = sum(
        audit["pass"] is True and audit["quantity"] == "power"
        for audit in goal_audits.values()
    )
    amplitude_pass_count = sum(
        audit["pass"] is True
        and audit["quantity"] in {"amplitude_real", "amplitude_imag"}
        for audit in goal_audits.values()
    )
    marking_audit = _marking_audit(
        marking,
        goal_audits=goal_audits,
        expected_goal_labels=set(expected_goal_tolerances),
    )
    expected_face_keys = [list(key) for key in TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS]
    transfer_errors = [
        _number(transfer.get(name))
        for name in (
            "reference_edge_identity_error_max",
            "reference_edge_target_face_source_error_max",
            "reference_face_interior_block_error_max",
            "reference_closure_target_from_outside_source_max",
            "reference_outside_target_from_closure_source_max",
            "graph_injection_closure_error_max",
            "face_generator_global_cross_error_max",
            "face_generator_projector_error_max",
            "complement_cross_error_max",
            "complement_gram_error_max",
        )
    ]
    coarse_manifest_path = coarse.get("manifest_path")
    endpoint_manifest_path = coarse_snapshot_endpoint.get("manifest_path")
    raw_coarse_candidate = coarse_snapshot_endpoint.get("candidate")
    raw_coarse_candidate = (
        raw_coarse_candidate if isinstance(raw_coarse_candidate, Mapping) else {}
    )
    raw_significant = coarse_snapshot_endpoint.get("significant_channel_authority")
    raw_significant = raw_significant if isinstance(raw_significant, Mapping) else {}
    raw_mesh_identity = coarse_snapshot_endpoint.get("mesh_identity")
    raw_mesh_identity = (
        raw_mesh_identity if isinstance(raw_mesh_identity, Mapping) else {}
    )
    raw_config_identity = coarse_snapshot_endpoint.get("normalized_config_identity")
    raw_config_identity = (
        raw_config_identity if isinstance(raw_config_identity, Mapping) else {}
    )
    raw_mode_identity = coarse_snapshot_endpoint.get("mode_identity")
    raw_mode_identity = (
        raw_mode_identity if isinstance(raw_mode_identity, Mapping) else {}
    )
    raw_vector_identity = coarse_snapshot_endpoint.get("vector_identity")
    raw_vector_identity = (
        raw_vector_identity if isinstance(raw_vector_identity, Mapping) else {}
    )
    endpoint_identity_fields = {
        "source_sha",
        "mesh_sha256",
        "normalized_config_sha256",
        "ordered_modes_sha256",
        "cell_interior_degree_sha256",
        "incident_projections_sha256",
        "auxiliary_coordinate_scales_sha256",
    }
    expected_raw_endpoint_authority = {
        "source_sha": coarse_snapshot_endpoint.get("source_sha"),
        "mesh_sha256": raw_mesh_identity.get("partition_independent_mesh_sha256"),
        "normalized_config_sha256": raw_config_identity.get("normalized_config_sha256"),
        "ordered_modes_sha256": raw_mode_identity.get("ordered_modes_sha256"),
        "cell_interior_degree_sha256": raw_coarse_candidate.get(
            "cell_interior_degree_sha256"
        ),
        "incident_projections_sha256": raw_vector_identity.get(
            "incident_projections_sha256"
        ),
        "auxiliary_coordinate_scales_sha256": raw_vector_identity.get(
            "coordinate_scales_sha256"
        ),
    }
    endpoint_authorities_pass = bool(
        endpoint_authorities.get("schema_version")
        == "task035d.selective-face-endpoint-identities.v1"
        and set(coarse_endpoint_authority) == endpoint_identity_fields
        and dict(coarse_endpoint_authority) == expected_raw_endpoint_authority
        and set(enriched_endpoint_authority) == endpoint_identity_fields
        and enriched_endpoint_authority.get("source_sha") == enriched.get("source_sha")
        and enriched_endpoint_authority.get("cell_interior_degree_sha256")
        == enriched.get("cell_interior_degree_sha256")
        and _valid_hex(enriched_endpoint_authority.get("source_sha"), 40)
        and all(
            _valid_hex(enriched_endpoint_authority.get(name), 64)
            for name in endpoint_identity_fields - {"source_sha"}
        )
    )
    recomputed_endpoint_identity = {
        "same_source_sha": (
            coarse_endpoint_authority.get("source_sha")
            == enriched_endpoint_authority.get("source_sha")
        ),
        "same_mesh": (
            coarse_endpoint_authority.get("mesh_sha256")
            == enriched_endpoint_authority.get("mesh_sha256")
        ),
        "same_normalized_config": (
            coarse_endpoint_authority.get("normalized_config_sha256")
            == enriched_endpoint_authority.get("normalized_config_sha256")
        ),
        "same_ordered_modes": (
            coarse_endpoint_authority.get("ordered_modes_sha256")
            == enriched_endpoint_authority.get("ordered_modes_sha256")
        ),
        "same_cell_interior_degree_map": (
            coarse_endpoint_authority.get("cell_interior_degree_sha256")
            == enriched_endpoint_authority.get("cell_interior_degree_sha256")
        ),
        "same_incident_projections": (
            coarse_endpoint_authority.get("incident_projections_sha256")
            == enriched_endpoint_authority.get("incident_projections_sha256")
        ),
        "same_auxiliary_coordinate_scales": (
            coarse_endpoint_authority.get("auxiliary_coordinate_scales_sha256")
            == enriched_endpoint_authority.get("auxiliary_coordinate_scales_sha256")
        ),
    }
    try:
        recomputed_raw_modes = _mode_index_by_channel(
            coarse_snapshot_endpoint.get("mode_identity")
        )
        normalized_raw_catalog = _normalized_entity_catalog(
            coarse_snapshot_endpoint.get("physical_entity_catalog")
        )
    except (TypeError, ValueError):
        recomputed_raw_modes = {}
        normalized_raw_catalog = []
    raw_catalog_keys = {
        tuple(int(value) for value in row["geometry_key"])
        for row in normalized_raw_catalog
        if row.get("dimension") == 2
    }
    raw_model_identity_pass = bool(
        coarse_snapshot_endpoint.get("source_sha") == expected_source_sha
        and raw_coarse_candidate == coarse_candidate
        and raw_coarse_candidate.get("candidate_id") == COARSE_CANDIDATE_ID
        and raw_coarse_candidate.get("source_sha") == expected_source_sha
        and raw_coarse_candidate.get("plan_file_sha256") == expected_coarse_plan_sha256
        and raw_coarse_candidate.get("actual_full3d_equivalent_active_fe_dofs")
        == COARSE_FULL3D_EQUIVALENT_DOFS
        and _valid_hex(
            raw_coarse_candidate.get("cell_interior_degree_sha256"),
            64,
        )
        and raw_significant.get("sha256")
        == expected_significant_channel_authority_sha256
        and raw_significant.get("physical_channel_count") == 12
        and raw_significant.get("real_goal_count") == 36
        and recomputed_raw_modes == raw_mode_index_by_channel
        and expected_channels <= set(recomputed_raw_modes)
        and _residual_gate_pass(coarse_snapshot_endpoint.get("primal_residual_gate"))
        and coarse_snapshot_endpoint.get("physical_entity_catalog_sha256")
        == _json_sha256(
            normalized_raw_catalog,
            namespace="task035d.selective-face-entity-catalog.v1",
        )
        and coarse_snapshot_endpoint.get("authority_entity_catalog_sha256")
        == TASK035D_LOCAL_H_ENTITY_CATALOG_SHA256
        and coarse_snapshot_endpoint.get("transfer_entity_catalog_sha256")
        == TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256
        and coarse_snapshot_endpoint.get("transfer_flattened_graph_sha256")
        == TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256
        and set(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS) <= raw_catalog_keys
    )
    coarse_manifest_identity_pass = bool(
        _valid_hex(expected_coarse_manifest_sha256, 64)
        and coarse.get("manifest_sha256")
        == expected_coarse_manifest_sha256
        == coarse_snapshot_endpoint.get("manifest_sha256")
        and _valid_hex(
            coarse_snapshot_endpoint.get("arrays_sha256"),
            64,
        )
        and isinstance(coarse_manifest_path, str)
        and isinstance(endpoint_manifest_path, str)
        and Path(coarse_manifest_path).resolve()
        == Path(endpoint_manifest_path).resolve()
        and raw_model_identity_pass
    )
    transfer_input_identity_pass = bool(
        _transfer_input_identity_pass(
            transfer.get("coarse_input_identity"),
            physical_authority_sha256=(TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256),
            entity_catalog_sha256=(
                TASK035D_LOCAL_H_TRANSFER_ENTITY_CATALOG_SHA256
            ),
            flattened_graph_sha256=(
                TASK035D_LOCAL_H_TRANSFER_FLATTENED_GRAPH_SHA256
            ),
            raw_trace_rows=23_875,
            independent_trace_rows=18_390,
        )
        and _transfer_input_identity_pass(
            transfer.get("enriched_input_identity"),
            physical_authority_sha256=(
                TASK035D_SELECTIVE_FACE_PHYSICAL_AUTHORITY_SHA256
            ),
            entity_catalog_sha256=(
                TASK035D_SELECTIVE_FACE_TRANSFER_ENTITY_CATALOG_SHA256
            ),
            flattened_graph_sha256=(
                TASK035D_SELECTIVE_FACE_TRANSFER_FLATTENED_GRAPH_SHA256
            ),
            raw_trace_rows=24_075,
            independent_trace_rows=18_590,
        )
    )
    transfer_hashes_pass = all(
        _valid_hex(transfer.get(name), 64)
        for name in (
            "physical_injection_sha256",
            "trace_injection_sha256",
            "total_injection_sha256",
            "trace_complement_projector_sha256",
            "complement_basis_sha256_noncanonical",
            "selected_root_positions_sha256",
            "reference_face_closure_injection_sha256",
            "face_generator_slices_sha256",
            "face_generator_gram_sha256",
            "selected_face_root_support_catalog_sha256",
        )
    )
    expected_face_generator_slices = {
        str(key): [20 * index, 20 * (index + 1)]
        for index, key in enumerate(
            sorted(TASK035D_SELECTIVE_FACE_GEOMETRY_KEYS)
        )
    }
    transfer_payload_hashes_pass = bool(
        isinstance(
            transfer.get("selected_face_root_support_catalog"),
            list,
        )
        and transfer.get(
            "selected_face_root_support_catalog_sha256"
        )
        == _json_sha256(
            transfer["selected_face_root_support_catalog"]
        )
        and transfer.get("face_generator_slices_sha256")
        == _json_sha256(expected_face_generator_slices)
    )
    checks = {
        "report_schema_and_status": (
            report.get("schema_version") == "task035d.selective-face-cross-trace-dwr.v1"
            and report.get("status") == "selective_face_cross_trace_live_dwr_pass"
            and report.get("pass") is True
            and report.get("controlled_negative") is False
        ),
        "source_sha_is_frozen_and_shared": (
            _valid_hex(expected_source_sha, 40)
            and coarse_candidate.get("source_sha") == expected_source_sha
            and enriched.get("source_sha") == expected_source_sha
        ),
        "endpoint_candidates_are_exact": (
            coarse_candidate.get("candidate_id") == COARSE_CANDIDATE_ID
            and enriched.get("candidate_id") == ENRICHED_CANDIDATE_ID
            and coarse_candidate.get("plan_file_sha256") == expected_coarse_plan_sha256
            and enriched.get("plan_file_sha256") == expected_enriched_plan_sha256
            and coarse_candidate.get("actual_full3d_equivalent_active_fe_dofs")
            == COARSE_FULL3D_EQUIVALENT_DOFS
            and enriched.get("actual_full3d_equivalent_active_fe_dofs")
            == ENRICHED_FULL3D_EQUIVALENT_DOFS
            and _valid_hex(
                coarse_candidate.get("cell_interior_degree_sha256"),
                64,
            )
            and _valid_hex(
                enriched.get("cell_interior_degree_sha256"),
                64,
            )
            and coarse_candidate.get("cell_interior_degree_sha256")
            == enriched.get("cell_interior_degree_sha256")
        ),
        "coarse_snapshot_manifest_and_modal_endpoint": (coarse_manifest_identity_pass),
        "significant_channel_authority": (
            significant_channel_authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
            and significant_channel_authority.get("pass") is True
            and len(expected_channels) == 12
            and len(expected_goal_tolerances) == 36
            and _valid_hex(
                expected_significant_channel_authority_sha256,
                64,
            )
            and authority.get("sha256") == expected_significant_channel_authority_sha256
            and authority.get("physical_channel_count") == 12
            and authority.get("real_goal_count") == 36
        ),
        "all_endpoint_identities": (
            set(identity) == _ENDPOINT_IDENTITY_CHECKS
            and identity == recomputed_endpoint_identity
            and all(value is True for value in identity.values())
            and endpoint_authorities_pass
        ),
        "actual_cross_trace_transfer": (
            report.get("same_trace_only") is False
            and report.get("actual_cross_trace_primal_prolongation_used") is True
            and transfer.get("schema_version")
            == "task035d.selective-face-physical-root-transfer.v2"
            and transfer.get("status") == "selective_face_physical_root_transfer_pass"
            and transfer.get("pass") is True
            and transfer.get("coarse_raw_trace_rows") == 23_875
            and transfer.get("selected_p6_face_count") == SELECTED_FACE_COUNT
            and transfer.get("selected_p6_face_geometry_keys") == expected_face_keys
            and transfer.get("trace_dimension_delta") == 200
            and transfer.get("reference_face_closure_shape") == [80, 60]
            and transfer.get("reference_face_closure_rank") == 60
            and transfer.get(
                "reference_face_generator_face_block_rank"
            )
            == 20
            and _rank_statistics_pass(
                transfer,
                tolerance_field=(
                    "reference_face_closure_rank_tolerance"
                ),
                smallest_field=(
                    "reference_face_closure_smallest_singular_value"
                ),
                condition_field=(
                    "reference_face_closure_condition_number"
                ),
            )
            and _number(
                transfer.get("reference_face_target_edge_source_max")
            )
            is not None
            and float(
                transfer.get("reference_face_target_edge_source_max")
            )
            > 1.0e-12
            and isinstance(transfer.get("affected_root_row_count"), int)
            and isinstance(
                transfer.get("affected_coarse_column_count"),
                int,
            )
            and transfer.get("affected_root_row_count")
            - transfer.get("affected_coarse_column_count")
            == 200
            and transfer.get("dense_patch_shape")
            == [
                transfer.get("affected_root_row_count"),
                transfer.get("affected_coarse_column_count"),
            ]
            and transfer.get("full_width_dense_transfer_materialized")
            is False
            and transfer.get("selected_patch_injection_rank")
            == transfer.get("affected_coarse_column_count")
            and _rank_statistics_pass(
                transfer,
                tolerance_field="selected_patch_rank_tolerance",
                smallest_field=(
                    "selected_patch_smallest_singular_value"
                ),
                condition_field="selected_patch_condition_number",
            )
            and transfer.get("face_generator_rank") == 200
            and _rank_statistics_pass(
                transfer,
                tolerance_field="face_generator_rank_tolerance",
                smallest_field=(
                    "face_generator_smallest_singular_value"
                ),
                condition_field="face_generator_condition_number",
            )
            and _selected_root_support_catalog_pass(
                transfer.get("selected_face_root_support_catalog")
            )
            and _number(
                transfer.get("face_generator_gram_condition_number")
            )
            is not None
            and 1.0
            <= float(
                transfer.get("face_generator_gram_condition_number")
            )
            <= 1.0e8
            and transfer.get("coarse_independent_trace_rows") == COARSE_SOLVE_ROWS - 80
            and transfer.get("enriched_independent_trace_rows")
            == ENRICHED_SOLVE_ROWS - 80
            and transfer.get("enriched_raw_trace_rows") == 24_075
            and transfer.get("auxiliary_rows") == 80
            and transfer_input_identity_pass
            and _changed_entities_pass(transfer.get("changed_entities"))
            and transfer_hashes_pass
            and transfer_payload_hashes_pass
            and transfer.get("complement_basis_is_identity_authority") is False
            and all(value is not None for value in transfer_errors)
            and all(
                0.0 <= float(value) <= _ROOT_TRANSFER_ROUNDOFF_LIMIT
                for value in transfer_errors
                if value is not None
            )
            and set(transfer_checks) == _ROOT_TRANSFER_CHECKS
            and all(value is True for value in transfer_checks.values())
            and transfer.get("cross_trace_dwr_scope")
            == (
                "whole non-periodic physical p6 faces with "
                "graph-expanded closure-root support"
            )
            and transfer.get("periodic_selected_face_backend_supported_but_dwr_v2")
            is False
            and transfer.get(
                "physical_closure_rows_assumed_independent_roots"
            )
            is False
            and transfer.get("signed_face_attribution")
            == "direct_sum_face_generators_with_full_gram_decomposition"
            and transfer.get("ordinary_default_changed") is False
        ),
        "galerkin_and_complement_recomputed": (_galerkin_audit_pass(galerkin)),
        "both_primal_residual_gates_recomputed": (
            _residual_gate_pass(primal.get("coarse_residual_gate"))
            and _residual_gate_pass(primal.get("enriched_residual_gate"))
        ),
        "twelve_actual_unit_adjoints_recomputed": (
            basis_schema_pass and channel_residuals_pass
        ),
        "all_rank_unit_pairing_content_identity": (
            _unit_pairing_content_pass(
                unit_pairing_content,
                unit_pairing_identity,
                expected_channels=expected_channels,
            )
        ),
        "all_scaled_goal_residuals_recomputed": goal_residuals_pass,
        "goal_inventory_exact": (set(goal_rows) == set(expected_goal_tolerances)),
        "all_36_goal_closures_recomputed": (
            len(goal_audits) == 36
            and not failed_goal_labels
            and power_pass_count == 12
            and amplitude_pass_count == 24
            and goals.get("schema_version")
            == "task035d.selective-face-live-36-goal-dwr.v1"
            and goals.get("status") == "selective_face_live_36_goal_dwr_pass"
            and goals.get("pass") is True
            and goals.get("requested_real_goal_count") == 36
            and goals.get("passed_real_goal_count") == 36
            and goals.get("power_goal_count") == 12
            and goals.get("power_goal_pass_count") == 12
            and goals.get("complex_amplitude_component_goal_count") == 24
            and goals.get("complex_amplitude_component_goal_pass_count") == 24
        ),
        "ten_face_multigoal_partition_recomputed": (marking_audit["pass"] is True),
        "formal_boundary_preserved": (
            boundary.get("this_report_qualifies_the_actual_selected_face_action")
            is True
            and boundary.get("this_report_does_not_select_unrun_faces") is True
            and boundary.get("full_case095_physics_gate_still_independent") is True
            and boundary.get("hybrid_credit_locked_until_full_full3d_gate") is True
        ),
        "ordinary_default_unchanged": (report.get("ordinary_default_changed") is False),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": ("task035d.selective-face-cross-trace-dwr-checker.v2"),
        "status": (
            "selective_face_cross_trace_dwr_checker_pass"
            if not failures
            else "selective_face_cross_trace_dwr_checker_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "recomputed_channel_count": len(expected_channels),
        "recomputed_goal_count": len(expected_goal_tolerances),
        "recomputed_goal_pass_count": (
            len(expected_goal_tolerances) - len(failed_goal_labels)
        ),
        "failed_goal_labels": failed_goal_labels,
        "recomputed_power_goal_pass_count": power_pass_count,
        "recomputed_amplitude_component_goal_pass_count": (amplitude_pass_count),
        "selected_face_marking_audit": marking_audit,
        "goal_oriented_selection_credit": False,
        "posthoc_actual_action_attribution": not failures,
        "full_case095_physics_gate_still_independent": True,
        "ordinary_default_changed": False,
    }


__all__ = [
    "load_selective_face_coarse_endpoint",
    "task035d_selective_face_dwr_report_gate",
]
