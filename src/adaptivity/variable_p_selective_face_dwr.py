"""Hash-bound cross-trace DWR for true selective p6 physical faces.

This is deliberately separate from :mod:`variable_p_nested_dwr`: that module
proves a same-trace, cell-interior-only comparison, while a real p6 face adds
matrix rows.  The coarse callback stores its physical constraint graph and a
small deterministic Galerkin probe set.  The enriched callback then builds
the geometry-bound root injection, validates the common-space operator and
RHS, forms the residual of the injected coarse solution in the *actual*
selective-face matrix, and streams the twelve physical channel adjoints.

No full-p6 trace matrix is created and no inactive face mode is numbered.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
from scipy import sparse

from .dtn_goal_adjoint import (
    dtn_channel_goal_value,
    evaluate_actual_dtn_unit_channel_adjoint_basis,
)
from .hcurl_broken_trace_graph import (
    BrokenHexTraceConstraintAuthority,
    PhysicalTraceEntity,
)
from .hcurl_trace_constraint_graph import (
    FlattenedTraceConstraintMap,
    PhysicalTraceRowKey,
)
from .nested_p_dwr import (
    scaled_unit_adjoint_pairing,
    unit_channel_goal_scalar,
)
from .selective_face_root_transfer import (
    SelectiveFaceRootTransfer,
    build_selective_face_root_transfer,
)
from .variable_p_nested_dwr import (
    SignificantChannelAuthority,
    _array_sha256,
    _atomic_npz,
    _candidate_identity,
    _channel_label,
    _collective_local_call,
    _collective_publish_json,
    _complex_pair,
    _coordinate_scales,
    _file_sha256,
    _global_petsc_values,
    _goal_tolerance_by_label,
    _json_sha256,
    _jsonable,
    _mode_identity,
    _normalized_config_identity,
    _primal_residual_gate,
    _temporary_vector_from_global,
    load_significant_channel_authority,
)
from .high_order_resource_audit import (
    partition_independent_linear_mesh_identity,
)


_SNAPSHOT_SCHEMA = "task035d.selective-face-coarse-snapshot.v1"
_ARRAY_SCHEMA = "task035d.selective-face-coarse-arrays.v1"
_REPORT_SCHEMA = "task035d.selective-face-cross-trace-dwr.v1"
_PROBE_COUNT = 3


@dataclass(frozen=True)
class SelectiveFaceCoarseSnapshot:
    """Loaded immutable coarse endpoint and physical-root graph."""

    manifest: Mapping[str, Any]
    manifest_path: Path
    authority: BrokenHexTraceConstraintAuthority
    state_b: np.ndarray
    rhs_b: np.ndarray
    action_b_on_b: np.ndarray
    residual_b: np.ndarray
    probe_vectors: np.ndarray
    probe_actions: np.ndarray
    auxiliary_values_b: np.ndarray
    incident_projections: np.ndarray
    coordinate_scales: np.ndarray


def _csr_sha256(
    matrix: sparse.spmatrix,
    *,
    namespace: str,
) -> str:
    """Hash one CSR matrix without lossy integer-to-float conversion."""

    values = sparse.csr_matrix(matrix, dtype=np.complex128)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    for label, array in (
        ("shape", np.asarray(values.shape, dtype=np.int64)),
        ("indptr", np.asarray(values.indptr, dtype=np.int64)),
        ("indices", np.asarray(values.indices, dtype=np.int64)),
        ("data", np.asarray(values.data, dtype=np.complex128)),
    ):
        contiguous = np.ascontiguousarray(array)
        digest.update(label.encode("ascii"))
        digest.update(b"\0")
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(b"\0")
        digest.update(
            np.asarray(contiguous.shape, dtype=np.int64).tobytes()
        )
        digest.update(contiguous.view(np.uint8))
    return digest.hexdigest()


def _csr_arrays(
    matrix: sparse.spmatrix,
    *,
    prefix: str,
) -> dict[str, np.ndarray]:
    values = sparse.csr_matrix(matrix, dtype=np.complex128)
    return {
        f"{prefix}_data": np.ascontiguousarray(values.data),
        f"{prefix}_indices": np.ascontiguousarray(
            values.indices,
            dtype=np.int64,
        ),
        f"{prefix}_indptr": np.ascontiguousarray(
            values.indptr,
            dtype=np.int64,
        ),
        f"{prefix}_shape": np.asarray(values.shape, dtype=np.int64),
    }


def _csr_from_arrays(
    arrays: Mapping[str, np.ndarray],
    *,
    prefix: str,
) -> sparse.csr_matrix:
    shape_values = np.asarray(arrays[f"{prefix}_shape"], dtype=np.int64)
    if shape_values.shape != (2,):
        raise ValueError("stored CSR shape is malformed")
    matrix = sparse.csr_matrix(
        (
            np.asarray(
                arrays[f"{prefix}_data"],
                dtype=np.complex128,
            ),
            np.asarray(
                arrays[f"{prefix}_indices"],
                dtype=np.int64,
            ),
            np.asarray(
                arrays[f"{prefix}_indptr"],
                dtype=np.int64,
            ),
        ),
        shape=tuple(map(int, shape_values)),
    )
    if not np.all(np.isfinite(matrix.data)):
        raise ValueError("stored physical constraint graph is non-finite")
    return matrix


def _entity_catalog(
    authority: BrokenHexTraceConstraintAuthority,
) -> list[dict[str, Any]]:
    return [
        {
            "dimension": int(entity.dimension),
            "geometry_key": list(entity.geometry_key),
            "degree": int(entity.degree),
            "canonical_points": [
                list(point) for point in entity.canonical_points
            ],
            "mode_count": len(entity.rows),
        }
        for entity in authority.entities
    ]


def _row(
    *,
    dimension: int,
    geometry_key: tuple[int, ...],
    degree: int,
    mode: int,
) -> PhysicalTraceRowKey:
    return PhysicalTraceRowKey(
        entity_dimension=dimension,
        entity_geometry_key=geometry_key,
        degree=degree,
        mode=mode,
    )


def _authority_from_snapshot(
    manifest: Mapping[str, Any],
    expansion: sparse.csr_matrix,
) -> BrokenHexTraceConstraintAuthority:
    rows = manifest.get("physical_entity_catalog")
    if not isinstance(rows, list) or not rows:
        raise ValueError("coarse snapshot has no physical entity catalog")
    entities: list[PhysicalTraceEntity] = []
    raw_rows: list[PhysicalTraceRowKey] = []
    for record in rows:
        dimension = int(record["dimension"])
        geometry_key = tuple(map(int, record["geometry_key"]))
        degree = int(record["degree"])
        mode_count = int(record["mode_count"])
        entity_rows = tuple(
            _row(
                dimension=dimension,
                geometry_key=geometry_key,
                degree=degree,
                mode=mode,
            )
            for mode in range(mode_count)
        )
        entity = PhysicalTraceEntity(
            dimension=dimension,
            geometry_key=geometry_key,
            degree=degree,
            canonical_points=tuple(
                tuple(map(int, point))
                for point in record["canonical_points"]
            ),
            rows=entity_rows,
        )
        entities.append(entity)
        raw_rows.extend(entity_rows)
    root_indices = tuple(
        map(int, manifest["physical_root_raw_indices"])
    )
    if (
        len(set(root_indices)) != len(root_indices)
        or any(index < 0 or index >= len(raw_rows) for index in root_indices)
    ):
        raise ValueError("coarse physical root-row indices are malformed")
    root_rows = tuple(raw_rows[index] for index in root_indices)
    if expansion.shape != (len(raw_rows), len(root_rows)):
        raise ValueError("coarse physical graph shape differs from its catalog")
    graph = FlattenedTraceConstraintMap(
        raw_rows=tuple(raw_rows),
        root_rows=root_rows,
        raw_from_independent=expansion,
        component_gram=(
            expansion.conj().T @ expansion
        ).tocsr(),
        cells=(),
        audit=MappingProxyType(
            {
                "pass": True,
                "snapshot_reconstruction_only": True,
                "raw_from_independent_sha256": manifest[
                    "physical_graph_sha256"
                ],
            }
        ),
    )
    return BrokenHexTraceConstraintAuthority(
        degree=int(manifest["base_trace_degree"]),
        entities=tuple(entities),
        hanging_relations=(),
        periodic_relations=(),
        graph=graph,
        selected_p6_face_geometry_keys=(),
        audit=MappingProxyType(
            {
                "pass": True,
                "snapshot_reconstruction_only": True,
                "physical_authority_sha256": manifest[
                    "physical_authority_sha256"
                ],
            }
        ),
    )


def _physical_identity(view: Any) -> dict[str, Any]:
    constraints = view.reduction.system.trace_constraints
    if constraints is None or not hasattr(constraints, "authority"):
        raise RuntimeError(
            "selective-face DWR requires a physical trace authority"
        )
    authority = constraints.authority
    graph = sparse.csr_matrix(
        authority.graph.raw_from_independent,
        dtype=np.complex128,
    )
    raw_index = {
        row: index for index, row in enumerate(authority.graph.raw_rows)
    }
    root_indices = [
        raw_index[row] for row in authority.graph.root_rows
    ]
    catalog = _entity_catalog(authority)
    return {
        "authority": authority,
        "graph": graph,
        "catalog": catalog,
        "root_raw_indices": root_indices,
        "catalog_sha256": _json_sha256(
            catalog,
            namespace="task035d.selective-face-entity-catalog.v1",
        ),
        "graph_sha256": _csr_sha256(
            graph,
            namespace="task035d.selective-face-physical-graph.v1",
        ),
    }


def _probe_seed(identity: Mapping[str, Any]) -> int:
    digest = _json_sha256(
        identity,
        namespace="task035d.selective-face-galerkin-probe-seed.v1",
    )
    return int(digest[:16], 16)


def _probe_vectors(
    *,
    rows: int,
    trace_rows: int,
    seed: int,
) -> np.ndarray:
    if not 0 < trace_rows < rows:
        raise ValueError("Galerkin probes require trace and auxiliary rows")
    rng = np.random.default_rng(int(seed))
    probes = np.zeros((rows, _PROBE_COUNT), dtype=np.complex128)
    probes[:trace_rows, 0] = (
        rng.standard_normal(trace_rows)
        + 1j * rng.standard_normal(trace_rows)
    )
    probes[trace_rows:, 1] = (
        rng.standard_normal(rows - trace_rows)
        + 1j * rng.standard_normal(rows - trace_rows)
    )
    probes[:, 2] = (
        rng.standard_normal(rows) + 1j * rng.standard_normal(rows)
    )
    for column in range(_PROBE_COUNT):
        norm = np.linalg.norm(probes[:, column])
        if not np.isfinite(norm) or norm <= np.finfo(float).tiny:
            raise RuntimeError("Galerkin probe construction failed")
        probes[:, column] /= norm
    return probes


def _matrix_actions(
    view: Any,
    probes: np.ndarray,
) -> np.ndarray:
    comm = view.mesh_data.mesh.comm
    actions = np.empty_like(probes)
    for column in range(probes.shape[1]):
        source: PETSc.Vec | None = None
        target: PETSc.Vec | None = None
        try:
            source = _temporary_vector_from_global(
                view.x,
                probes[:, column],
            )
            target = view.x.duplicate()
            view.A.mult(source, target)
            actions[:, column] = _global_petsc_values(
                target,
                comm,
            )[0]
        finally:
            if target is not None:
                target.destroy()
            if source is not None:
                source.destroy()
    return actions


def write_selective_face_coarse_snapshot(
    view: Any,
    *,
    artifact_directory: str | Path,
    candidate_id: str,
    expected_plan_sha256: str,
    source_sha: str,
    significant_channel_authority_path: str | Path,
    significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Publish one immutable p5-trace endpoint for cross-trace DWR."""

    comm = view.mesh_data.mesh.comm
    authority = _collective_local_call(
        comm,
        "selective-face significant authority load",
        lambda: load_significant_channel_authority(
            significant_channel_authority_path,
            expected_sha256=significant_channel_authority_sha256,
        ),
    )
    if authority is None:
        raise RuntimeError("significant channel authority is absent")
    candidate = _candidate_identity(
        view,
        candidate_id=candidate_id,
        expected_plan_sha256=expected_plan_sha256,
        source_sha=source_sha,
    )
    physical = _physical_identity(view)
    physical_authority = physical["authority"]
    if physical_authority.selected_p6_face_geometry_keys:
        raise ValueError(
            "coarse selective-face snapshot must have a pure p5 trace"
        )
    if physical_authority.degree != 5:
        raise ValueError("coarse selective-face snapshot requires p5 trace")
    state_b, ownership = _global_petsc_values(view.x, comm)
    rhs_b, rhs_ownership = _global_petsc_values(view.b, comm)
    if ownership != rhs_ownership:
        raise RuntimeError("coarse state and RHS ownership differ")
    action_vector = view.x.duplicate()
    try:
        view.A.mult(view.x, action_vector)
        action_b, action_ownership = _global_petsc_values(
            action_vector,
            comm,
        )
    finally:
        action_vector.destroy()
    if ownership != action_ownership:
        raise RuntimeError("coarse matrix action ownership differs")
    residual_b = np.ascontiguousarray(rhs_b - action_b)
    relative_residual = float(
        np.linalg.norm(residual_b)
        / max(np.linalg.norm(rhs_b), np.finfo(float).tiny)
    )
    residual_gate = _primal_residual_gate(
        full_active_residual=view.full_active_residual,
        reduced_relative_residual=relative_residual,
    )
    if not residual_gate["pass"]:
        raise RuntimeError(
            "coarse selective-face endpoint failed primal residual Gate"
        )
    trace_rows = int(view.reduction.system.active_trace_rows)
    auxiliary_rows = int(view.reduction.system.appended_rows)
    if trace_rows + auxiliary_rows != len(state_b):
        raise RuntimeError("coarse trace plus auxiliary dimensions do not close")
    normalized_config = _normalized_config_identity(view.config)
    mode_identity = _mode_identity(view.goal_context)
    mesh_identity = partition_independent_linear_mesh_identity(
        view.mesh_data
    )
    seed_identity = {
        "candidate": candidate,
        "mesh_sha256": mesh_identity[
            "partition_independent_mesh_sha256"
        ],
        "config_sha256": normalized_config["normalized_config_sha256"],
        "mode_sha256": mode_identity["ordered_modes_sha256"],
        "physical_graph_sha256": physical["graph_sha256"],
    }
    probes = _probe_vectors(
        rows=len(state_b),
        trace_rows=trace_rows,
        seed=_probe_seed(seed_identity),
    )
    probe_actions = _matrix_actions(view, probes)
    auxiliary = np.asarray(
        view.goal_context["auxiliary_values"],
        dtype=np.complex128,
    ).copy()
    incident = np.asarray(
        view.goal_context["incident_projections"],
        dtype=np.complex128,
    ).copy()
    scales = _coordinate_scales(view.goal_context)
    if not np.allclose(
        auxiliary,
        state_b[trace_rows:] / scales,
        rtol=2.0e-12,
        atol=2.0e-13,
    ):
        raise RuntimeError("coarse auxiliary endpoint differs from solver state")

    output = Path(artifact_directory).resolve()
    arrays_path = output / "coarse_arrays.npz"
    manifest_path = output / "manifest.json"
    arrays = {
        "schema_version": np.asarray([_ARRAY_SCHEMA], dtype=np.str_),
        "state_b": state_b,
        "rhs_b": rhs_b,
        "action_b_on_b": action_b,
        "residual_b": residual_b,
        "probe_vectors": probes,
        "probe_actions": probe_actions,
        "auxiliary_values_b": auxiliary,
        "incident_projections": incident,
        "coordinate_scales": scales,
        **_csr_arrays(physical["graph"], prefix="physical_graph"),
    }
    write_error = None
    arrays_sha256 = None
    if comm.rank == 0:
        try:
            output.mkdir(parents=True, exist_ok=True)
            _atomic_npz(arrays_path, arrays)
            arrays_sha256 = _file_sha256(arrays_path)
        except Exception as exc:
            write_error = f"{type(exc).__name__}: {exc}"
    write_errors = comm.allgather(write_error)
    if any(error is not None for error in write_errors):
        raise RuntimeError(
            "selective-face coarse array publication failed: "
            f"{write_errors}"
        )
    root_arrays_sha256 = comm.bcast(arrays_sha256, root=0)
    arrays_sha256 = _collective_local_call(
        comm,
        "selective-face coarse array publication verification",
        lambda: _file_sha256(arrays_path),
    )
    if arrays_sha256 != root_arrays_sha256:
        raise RuntimeError(
            "selective-face coarse array publication SHA changed"
        )
    manifest = {
        "schema_version": _SNAPSHOT_SCHEMA,
        "status": "selective_face_coarse_snapshot_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "candidate": candidate,
        "source_sha": str(source_sha),
        "mesh_identity": mesh_identity,
        "normalized_config_identity": normalized_config,
        "mode_identity": mode_identity,
        "floquet_phases": {
            "phase_x": _jsonable(complex(view.floquet_data.phase_x)),
            "phase_y": _jsonable(complex(view.floquet_data.phase_y)),
        },
        "significant_channel_authority": {
            "path": str(authority.path),
            "sha256": authority.file_sha256,
            "physical_channel_count": len(authority.channels),
            "real_goal_count": len(authority.goals),
        },
        "base_trace_degree": 5,
        "independent_trace_rows": trace_rows,
        "auxiliary_rows": auxiliary_rows,
        "matrix_rows": len(state_b),
        "matrix_vector_ownership_ranges": [
            list(values) for values in ownership
        ],
        "physical_entity_catalog": physical["catalog"],
        "physical_entity_catalog_sha256": physical["catalog_sha256"],
        "physical_root_raw_indices": physical["root_raw_indices"],
        "physical_graph_sha256": physical["graph_sha256"],
        "physical_authority_sha256": str(
            physical_authority.audit["physical_authority_sha256"]
        ),
        "port_operator_audit": _jsonable(view.port_operator_audit),
        "primal_residual_gate": residual_gate,
        "primal_solver_telemetry": _jsonable(
            view.primal_solver_telemetry
        ),
        "probe_contract": {
            "probe_count": _PROBE_COUNT,
            "roles": [
                "trace_only_random",
                "auxiliary_only_random",
                "combined_random",
            ],
            "seed_identity": seed_identity,
            "probe_vectors_sha256": _array_sha256(
                probes,
                namespace="task035d.selective-face-probes.v1",
            ),
            "probe_actions_sha256": _array_sha256(
                probe_actions,
                namespace="task035d.selective-face-probe-actions.v1",
            ),
        },
        "arrays": {
            "path": arrays_path.name,
            "sha256": arrays_sha256,
        },
        "vector_identity": {
            "state_b_sha256": _array_sha256(
                state_b,
                namespace="task035d.selective-face-state-b.v1",
            ),
            "rhs_b_sha256": _array_sha256(
                rhs_b,
                namespace="task035d.selective-face-rhs-b.v1",
            ),
            "action_b_on_b_sha256": _array_sha256(
                action_b,
                namespace="task035d.selective-face-action-b.v1",
            ),
            "residual_b_sha256": _array_sha256(
                residual_b,
                namespace="task035d.selective-face-residual-b.v1",
            ),
            "auxiliary_values_b_sha256": _array_sha256(
                auxiliary,
                namespace=(
                    "task035d.selective-face-auxiliary-values-b.v1"
                ),
            ),
            "incident_projections_sha256": _array_sha256(
                incident,
                namespace=(
                    "task035d.selective-face-incident-projections.v1"
                ),
            ),
            "coordinate_scales_sha256": _array_sha256(
                scales,
                namespace=(
                    "task035d.selective-face-coordinate-scales.v1"
                ),
            ),
            "relative_residual": relative_residual,
        },
    }
    manifest_sha256 = _collective_publish_json(
        comm,
        manifest_path,
        manifest,
    )
    return {
        "schema_version": _SNAPSHOT_SCHEMA,
        "status": "selective_face_coarse_snapshot_published",
        "pass": True,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "arrays_sha256": arrays_sha256,
        "ordinary_default_changed": False,
    }


def load_selective_face_coarse_snapshot(
    manifest_path: str | Path,
    *,
    communicator: MPI.Intracomm,
    expected_manifest_sha256: str,
    expected_source_sha: str,
    expected_significant_channel_authority_sha256: str,
) -> SelectiveFaceCoarseSnapshot:
    """Collectively load and validate one immutable coarse snapshot."""

    path = Path(manifest_path).resolve()
    expected_manifest = str(expected_manifest_sha256).lower()
    expected_channel_authority = str(
        expected_significant_channel_authority_sha256
    ).lower()

    def load_local() -> SelectiveFaceCoarseSnapshot:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        observed_manifest_sha256 = _file_sha256(path)
        if observed_manifest_sha256 != expected_manifest:
            raise ValueError("selective-face coarse manifest SHA mismatch")
        if (
            manifest.get("schema_version") != _SNAPSHOT_SCHEMA
            or manifest.get("pass") is not True
        ):
            raise ValueError("selective-face coarse manifest is not passing")
        if str(manifest.get("source_sha")) != str(expected_source_sha):
            raise ValueError("selective-face coarse source SHA mismatch")
        if (
            manifest["significant_channel_authority"]["sha256"]
            != expected_channel_authority
        ):
            raise ValueError(
                "selective-face significant channel authority SHA mismatch"
            )
        arrays_path = path.parent / manifest["arrays"]["path"]
        if _file_sha256(arrays_path) != manifest["arrays"]["sha256"]:
            raise ValueError("selective-face coarse array SHA mismatch")
        with np.load(arrays_path, allow_pickle=False) as stored:
            arrays = {name: stored[name].copy() for name in stored.files}
        if (
            arrays["schema_version"].shape != (1,)
            or str(arrays["schema_version"][0]) != _ARRAY_SCHEMA
        ):
            raise ValueError("selective-face coarse array schema mismatch")

        expansion = _csr_from_arrays(arrays, prefix="physical_graph")
        catalog = manifest["physical_entity_catalog"]
        catalog_sha256 = _json_sha256(
            catalog,
            namespace="task035d.selective-face-entity-catalog.v1",
        )
        graph_sha256 = _csr_sha256(
            expansion,
            namespace="task035d.selective-face-physical-graph.v1",
        )
        if (
            catalog_sha256
            != manifest["physical_entity_catalog_sha256"]
            or graph_sha256 != manifest["physical_graph_sha256"]
        ):
            raise ValueError(
                "selective-face physical catalog or graph identity mismatch"
            )
        authority = _authority_from_snapshot(manifest, expansion)
        root_indices = np.asarray(
            manifest["physical_root_raw_indices"],
            dtype=np.int64,
        )
        root_identity = expansion[root_indices].tocsr()
        root_identity_error = root_identity - sparse.eye(
            expansion.shape[1],
            dtype=np.complex128,
            format="csr",
        )
        root_identity_error.eliminate_zeros()
        if (
            root_identity_error.nnz
            and float(np.max(np.abs(root_identity_error.data)))
            > 2.0e-13
        ):
            raise ValueError(
                "selective-face physical roots do not inject as identity"
            )

        matrix_rows = int(manifest["matrix_rows"])
        trace_rows = int(manifest["independent_trace_rows"])
        auxiliary_rows = int(manifest["auxiliary_rows"])
        if (
            matrix_rows != trace_rows + auxiliary_rows
            or expansion.shape[1] != trace_rows
        ):
            raise ValueError(
                "selective-face snapshot dimensions do not close"
            )
        vector_namespaces = {
            "state_b": "task035d.selective-face-state-b.v1",
            "rhs_b": "task035d.selective-face-rhs-b.v1",
            "action_b_on_b": (
                "task035d.selective-face-action-b.v1"
            ),
            "residual_b": "task035d.selective-face-residual-b.v1",
        }
        identity = manifest["vector_identity"]
        for name, namespace in vector_namespaces.items():
            values = np.asarray(arrays[name], dtype=np.complex128)
            if (
                values.shape != (matrix_rows,)
                or not np.all(np.isfinite(values))
                or _array_sha256(values, namespace=namespace)
                != identity[f"{name}_sha256"]
            ):
                raise ValueError(
                    f"selective-face coarse {name} identity is malformed"
                )
        residual_rebuilt = np.asarray(
            arrays["rhs_b"] - arrays["action_b_on_b"],
            dtype=np.complex128,
        )
        residual_scale = max(
            float(np.linalg.norm(arrays["rhs_b"])),
            float(np.linalg.norm(arrays["action_b_on_b"])),
            1.0,
        )
        if (
            np.linalg.norm(residual_rebuilt - arrays["residual_b"])
            > 2.0e-13 + 2.0e-13 * residual_scale
        ):
            raise ValueError(
                "selective-face coarse residual is not rhs minus action"
            )
        observed_relative_residual = float(
            np.linalg.norm(arrays["residual_b"])
            / max(
                np.linalg.norm(arrays["rhs_b"]),
                np.finfo(float).tiny,
            )
        )
        if not np.isclose(
            observed_relative_residual,
            float(identity["relative_residual"]),
            rtol=2.0e-13,
            atol=2.0e-15,
        ):
            raise ValueError(
                "selective-face coarse residual scalar identity mismatch"
            )

        probes = np.asarray(
            arrays["probe_vectors"],
            dtype=np.complex128,
        )
        actions = np.asarray(
            arrays["probe_actions"],
            dtype=np.complex128,
        )
        probe_contract = manifest["probe_contract"]
        if (
            probes.shape != (matrix_rows, _PROBE_COUNT)
            or actions.shape != probes.shape
            or not np.all(np.isfinite(probes))
            or not np.all(np.isfinite(actions))
            or _array_sha256(
                probes,
                namespace="task035d.selective-face-probes.v1",
            )
            != probe_contract["probe_vectors_sha256"]
            or _array_sha256(
                actions,
                namespace=(
                    "task035d.selective-face-probe-actions.v1"
                ),
            )
            != probe_contract["probe_actions_sha256"]
        ):
            raise ValueError(
                "selective-face Galerkin probe identity is malformed"
            )
        endpoint_namespaces = {
            "auxiliary_values_b": (
                "task035d.selective-face-auxiliary-values-b.v1"
            ),
            "incident_projections": (
                "task035d.selective-face-incident-projections.v1"
            ),
            "coordinate_scales": (
                "task035d.selective-face-coordinate-scales.v1"
            ),
        }
        endpoints: dict[str, np.ndarray] = {}
        for name, namespace in endpoint_namespaces.items():
            values = np.asarray(arrays[name], dtype=np.complex128)
            if (
                values.shape != (auxiliary_rows,)
                or not np.all(np.isfinite(values))
                or _array_sha256(values, namespace=namespace)
                != identity[f"{name}_sha256"]
            ):
                raise ValueError(
                    f"selective-face coarse {name} identity is malformed"
                )
            endpoints[name] = values
        if np.any(np.abs(endpoints["coordinate_scales"]) <= 0.0):
            raise ValueError(
                "selective-face coarse coordinate scale is zero"
            )
        if not np.allclose(
            endpoints["auxiliary_values_b"],
            np.asarray(arrays["state_b"][trace_rows:])
            / endpoints["coordinate_scales"],
            rtol=2.0e-12,
            atol=2.0e-13,
        ):
            raise ValueError(
                "selective-face coarse auxiliary endpoint is inconsistent"
            )
        return SelectiveFaceCoarseSnapshot(
            manifest=MappingProxyType(manifest),
            manifest_path=path,
            authority=authority,
            state_b=np.asarray(arrays["state_b"], dtype=np.complex128),
            rhs_b=np.asarray(arrays["rhs_b"], dtype=np.complex128),
            action_b_on_b=np.asarray(
                arrays["action_b_on_b"],
                dtype=np.complex128,
            ),
            residual_b=np.asarray(
                arrays["residual_b"],
                dtype=np.complex128,
            ),
            probe_vectors=probes,
            probe_actions=actions,
            auxiliary_values_b=endpoints["auxiliary_values_b"],
            incident_projections=endpoints["incident_projections"],
            coordinate_scales=endpoints["coordinate_scales"],
        )

    snapshot = _collective_local_call(
        communicator,
        "selective-face coarse snapshot load and semantic validation",
        load_local,
    )
    if snapshot is None:
        raise RuntimeError("selective-face coarse snapshot load was empty")
    identity_packet = {
        "manifest_sha256": expected_manifest,
        "arrays_sha256": snapshot.manifest["arrays"]["sha256"],
        "physical_graph_sha256": snapshot.manifest[
            "physical_graph_sha256"
        ],
        "physical_entity_catalog_sha256": snapshot.manifest[
            "physical_entity_catalog_sha256"
        ],
    }
    if len(
        {
            json.dumps(packet, sort_keys=True)
            for packet in communicator.allgather(identity_packet)
        }
    ) != 1:
        raise RuntimeError("MPI ranks loaded different coarse snapshots")
    return snapshot


def _relative_gate(
    observed: np.ndarray,
    expected: np.ndarray,
    *,
    absolute: float = 5.0e-10,
    relative: float = 2.0e-9,
) -> dict[str, Any]:
    delta = np.asarray(observed) - np.asarray(expected)
    error = float(np.linalg.norm(delta))
    scale = max(
        float(np.linalg.norm(observed)),
        float(np.linalg.norm(expected)),
        1.0e-30,
    )
    limit = float(absolute + relative * scale)
    return {
        "pass": error <= limit,
        "error_l2_norm": error,
        "scale_l2_norm": scale,
        "relative_error": error / scale,
        "acceptance_limit": limit,
    }


def _galerkin_audit(
    view: Any,
    snapshot: SelectiveFaceCoarseSnapshot,
    transfer: SelectiveFaceRootTransfer,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
    comm = view.mesh_data.mesh.comm
    rhs_a, _ = _global_petsc_values(view.b, comm)
    state_a, _ = _global_petsc_values(view.x, comm)
    if transfer.total_injection.shape != (
        len(state_a),
        len(snapshot.state_b),
    ):
        raise ValueError("selective-face total injection has a wrong shape")
    rhs_gate = _relative_gate(
        transfer.restrict_dual(rhs_a),
        snapshot.rhs_b,
    )
    probe_rows: list[dict[str, Any]] = []
    for column in range(snapshot.probe_vectors.shape[1]):
        prolonged = transfer.prolong_primal(
            snapshot.probe_vectors[:, column]
        )
        source = _temporary_vector_from_global(view.x, prolonged)
        target = view.x.duplicate()
        try:
            view.A.mult(source, target)
            action_a, _ = _global_petsc_values(target, comm)
        finally:
            source.destroy()
            target.destroy()
        gate = _relative_gate(
            transfer.restrict_dual(action_a),
            snapshot.probe_actions[:, column],
        )
        probe_rows.append({"probe": column, **gate})

    injected_state = transfer.prolong_primal(snapshot.state_b)
    injected: PETSc.Vec | None = None
    action_injected: PETSc.Vec | None = None
    action_a_endpoint: PETSc.Vec | None = None
    try:
        injected = _temporary_vector_from_global(view.x, injected_state)
        action_injected = view.x.duplicate()
        action_a_endpoint = view.x.duplicate()
        view.A.mult(injected, action_injected)
        view.A.mult(view.x, action_a_endpoint)
        action_on_injected, _ = _global_petsc_values(
            action_injected,
            comm,
        )
        action_on_a, _ = _global_petsc_values(
            action_a_endpoint,
            comm,
        )
    finally:
        if action_a_endpoint is not None:
            action_a_endpoint.destroy()
        if action_injected is not None:
            action_injected.destroy()
        if injected is not None:
            injected.destroy()
    residual_injected = np.ascontiguousarray(rhs_a - action_on_injected)
    residual_a = np.ascontiguousarray(rhs_a - action_on_a)
    effective = np.ascontiguousarray(residual_injected - residual_a)
    orthogonality_gate = _relative_gate(
        transfer.restrict_dual(residual_injected),
        snapshot.residual_b,
        absolute=1.0e-9,
        relative=5.0e-9,
    )
    complement_coordinates = transfer.complement_coordinates(effective)
    complement_reconstruction = np.asarray(
        transfer.total_complement @ complement_coordinates
    )
    complement_unexplained = np.ascontiguousarray(
        effective - complement_reconstruction
    )
    common_residual_bound = (
        np.linalg.norm(snapshot.residual_b)
        + np.linalg.norm(residual_a)
    )
    complement_limit = float(5.0e-9 + 20.0 * common_residual_bound)
    complement_error = float(np.linalg.norm(complement_unexplained))
    checks = {
        "rhs_galerkin_identity": rhs_gate["pass"],
        "all_operator_galerkin_probes": all(
            row["pass"] for row in probe_rows
        ),
        "injected_coarse_solution_is_galerkin_orthogonal": (
            orthogonality_gate["pass"]
        ),
        "effective_residual_lies_in_selected_face_complement": (
            complement_error <= complement_limit
        ),
    }
    audit = {
        "schema_version": (
            "task035d.selective-face-cross-trace-galerkin-audit.v1"
        ),
        "status": (
            "selective_face_cross_trace_galerkin_pass"
            if all(checks.values())
            else "selective_face_cross_trace_galerkin_fail"
        ),
        "pass": all(checks.values()),
        "checks": checks,
        "rhs": rhs_gate,
        "operator_probes": probe_rows,
        "injected_coarse_galerkin_orthogonality": orthogonality_gate,
        "residuals": {
            "coarse_l2_norm": float(
                np.linalg.norm(snapshot.residual_b)
            ),
            "enriched_endpoint_l2_norm": float(
                np.linalg.norm(residual_a)
            ),
            "injected_l2_norm": float(
                np.linalg.norm(residual_injected)
            ),
            "effective_l2_norm": float(np.linalg.norm(effective)),
            "complement_coordinate_l2_norm": float(
                np.linalg.norm(complement_coordinates)
            ),
            "complement_unexplained_l2_norm": complement_error,
            "complement_unexplained_limit": complement_limit,
        },
        "probe_semantics": (
            "P^H*A_A*P*v equals stored A_B*v for independent "
            "trace-only, auxiliary-only, and combined deterministic probes"
        ),
        "full_matrix_equality_claimed": False,
        "actual_endpoint_dwr_closure_is_mandatory": True,
    }
    return audit, effective, residual_a, complement_unexplained


def _coarse_goal_context(
    view: Any,
    snapshot: SelectiveFaceCoarseSnapshot,
) -> dict[str, Any]:
    context = dict(view.goal_context)
    context["auxiliary_values"] = snapshot.auxiliary_values_b
    context["incident_projections"] = snapshot.incident_projections
    context["auxiliary_coordinate_scales"] = snapshot.coordinate_scales
    return context


def _goal_reports(
    *,
    view: Any,
    snapshot: SelectiveFaceCoarseSnapshot,
    authority: SignificantChannelAuthority,
    basis_report: Mapping[str, Any],
    unit_pairings: Mapping[str, Mapping[str, Any]],
    state_delta_norm: float,
    transfer: SelectiveFaceRootTransfer,
    complement_unexplained_limit: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    context_a = dict(view.goal_context)
    context_b = _coarse_goal_context(view, snapshot)
    modes = tuple(context_a["modes"])
    tolerances = _goal_tolerance_by_label(authority)
    face_accumulator = {
        key: {
            "geometry_key": list(key),
            "maximum_normalized_absolute_contribution": 0.0,
            "sum_normalized_absolute_contribution": 0.0,
            "goal_contributions": {},
        }
        for key in transfer.complement_slices
    }
    reports: dict[str, Any] = {}
    passed = 0
    power_passed = 0
    amplitude_passed = 0
    for goal in authority.goals:
        goal_metadata = dict(basis_report["goals"][goal.label])
        channel_label = _channel_label(
            goal_metadata["canonical_channel_identity"]
        )
        unit = unit_pairings[channel_label]
        value_a = dtn_channel_goal_value(
            view.config,
            modes,
            np.asarray(context_a["auxiliary_values"]),
            np.asarray(context_a["incident_projections"]),
            goal=goal,
        )
        value_b = dtn_channel_goal_value(
            view.config,
            modes,
            np.asarray(context_b["auxiliary_values"]),
            np.asarray(context_b["incident_projections"]),
            goal=goal,
        )
        if goal.quantity == "power":
            mode_index = int(goal_metadata["auxiliary_mode_index"])
            mode = modes[mode_index]
            outgoing_b = complex(snapshot.auxiliary_values_b[mode_index])
            if mode.side == "top":
                outgoing_b -= complex(
                    snapshot.incident_projections[mode_index]
                )
            outgoing_a_pair = goal_metadata["outgoing_amplitude"]
            outgoing_a = complex(
                float(outgoing_a_pair[0]),
                float(outgoing_a_pair[1]),
            )
            scale_pair = goal_metadata["auxiliary_coordinate_scale"]
            coordinate_scale = complex(
                float(scale_pair[0]),
                float(scale_pair[1]),
            )
            gamma = unit_channel_goal_scalar(
                quantity="power",
                coordinate_scale=coordinate_scale,
                power_weight=float(goal_metadata["power_weight"]),
                outgoing_a=outgoing_a,
                outgoing_b=outgoing_b,
            )
            scaling_semantics = "exact_A_B_midpoint_power_gradient"
        else:
            scalar_pair = goal_metadata[
                "gradient_scalar_solver_coordinate"
            ]
            gamma = complex(
                float(scalar_pair[0]),
                float(scalar_pair[1]),
            )
            scaling_semantics = "exact_affine_amplitude_gradient"
        actual_delta = float(value_a - value_b)
        pairing = scaled_unit_adjoint_pairing(
            complex(unit["effective"]),
            gamma,
        )
        estimate = float(pairing.real)
        closure_error = float(estimate - actual_delta)
        channel_report = basis_report["channels"][channel_label]
        adjoint_residual = float(
            channel_report["adjoint_residual"]["residual_norm"]
        )
        residual_bound = abs(gamma) * adjoint_residual * state_delta_norm
        roundoff = (
            512.0
            * np.finfo(float).eps
            * max(
                abs(value_a),
                abs(value_b),
                abs(actual_delta),
                abs(estimate),
                1.0,
            )
        )
        closure_limit = float(
            8.0
            * (residual_bound + roundoff)
        )
        face_reports: list[dict[str, Any]] = []
        face_sum = 0.0 + 0.0j
        face_absolute_sum = 0.0
        tolerance = tolerances[goal.label]
        for key in sorted(transfer.complement_slices):
            unit_face = complex(unit["faces"][key])
            face_pairing = scaled_unit_adjoint_pairing(
                unit_face,
                gamma,
            )
            signed = float(face_pairing.real)
            normalized = abs(signed) / tolerance
            accumulator = face_accumulator[key]
            accumulator["goal_contributions"][goal.label] = signed
            accumulator[
                "maximum_normalized_absolute_contribution"
            ] = max(
                float(
                    accumulator[
                        "maximum_normalized_absolute_contribution"
                    ]
                ),
                normalized,
            )
            accumulator[
                "sum_normalized_absolute_contribution"
            ] += normalized
            face_reports.append(
                {
                    "geometry_key": list(key),
                    "complex_pairing": _complex_pair(face_pairing),
                    "signed_real_contribution": signed,
                    "absolute_marking_weight": abs(signed),
                    "normalized_absolute_contribution": normalized,
                }
            )
            face_sum += face_pairing
            face_absolute_sum += abs(face_pairing)
        unexplained_pairing = scaled_unit_adjoint_pairing(
            complex(unit["unexplained"]),
            gamma,
        )
        face_closure_error = complex(pairing - face_sum)
        face_roundoff = (
            512.0
            * np.finfo(float).eps
            * max(abs(pairing), face_absolute_sum, tolerance, 1.0)
        )
        face_residual_bound = float(
            abs(gamma)
            * float(unit["adjoint_l2_norm"])
            * float(complement_unexplained_limit)
        )
        face_theoretical_limit = float(
            8.0 * (face_residual_bound + face_roundoff)
        )
        face_tolerance_budget = float(0.05 * tolerance)
        face_closure_limit = max(
            float(8.0 * face_roundoff),
            min(face_theoretical_limit, face_tolerance_budget),
        )
        face_closure_pass = (
            abs(face_closure_error) <= face_closure_limit
        )
        goal_pass = bool(
            channel_report["pass"]
            and goal_metadata["pass"]
            and abs(closure_error) <= closure_limit
            and face_closure_pass
        )
        passed += int(goal_pass)
        power_passed += int(goal.quantity == "power" and goal_pass)
        amplitude_passed += int(
            goal.quantity in {"amplitude_real", "amplitude_imag"}
            and goal_pass
        )
        reports[goal.label] = {
            "goal": goal.as_dict(),
            "pass": goal_pass,
            "value_a": value_a,
            "value_b": value_b,
            "actual_goal_delta_a_minus_b": actual_delta,
            "signed_dwr_estimate": estimate,
            "signed_goal_closure_error": closure_error,
            "goal_closure_limit": closure_limit,
            "unit_adjoint_residual_error_bound": residual_bound,
            "endpoint_closure_does_not_use_partition_error": True,
            "unexplained_residual_complex_pairing": _complex_pair(
                unexplained_pairing
            ),
            "scaling_semantics": scaling_semantics,
            "unit_adjoint_goal_scalar": _complex_pair(gamma),
            "global_complex_pairing": _complex_pair(pairing),
            "selected_face_complex_pairing_sum": _complex_pair(face_sum),
            "selected_face_pairing_closure_error": _complex_pair(
                face_closure_error
            ),
            "selected_face_pairing_closure_limit": face_closure_limit,
            "selected_face_pairing_theoretical_limit": (
                face_theoretical_limit
            ),
            "selected_face_pairing_tolerance_budget": (
                face_tolerance_budget
            ),
            "selected_face_pairing_closure_pass": face_closure_pass,
            "face_contributions": face_reports,
            "unchanged_v0_absolute_tolerance": tolerance,
        }
    ranked = sorted(
        face_accumulator.values(),
        key=lambda row: (
            -float(row["maximum_normalized_absolute_contribution"]),
            tuple(row["geometry_key"]),
        ),
    )
    return (
        {
            "schema_version": (
                "task035d.selective-face-live-36-goal-dwr.v1"
            ),
            "status": (
                "selective_face_live_36_goal_dwr_pass"
                if passed == len(authority.goals)
                else "selective_face_live_36_goal_dwr_fail"
            ),
            "pass": passed == len(authority.goals),
            "requested_real_goal_count": len(authority.goals),
            "passed_real_goal_count": passed,
            "power_goal_count": 12,
            "power_goal_pass_count": power_passed,
            "complex_amplitude_component_goal_count": 24,
            "complex_amplitude_component_goal_pass_count": (
                amplitude_passed
            ),
            "physical_channel_count": 12,
            "power_uses_exact_midpoint_gradient": True,
            "signed_sum_used_for_closure": True,
            "absolute_sum_used_for_marking_only": True,
            "goals": reports,
        },
        ranked,
    )


def evaluate_selective_face_enriched_snapshot(
    view: Any,
    *,
    coarse_manifest_path: str | Path,
    coarse_manifest_sha256: str,
    artifact_path: str | Path,
    candidate_id: str,
    expected_plan_sha256: str,
    source_sha: str,
    significant_channel_authority_path: str | Path,
    significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Evaluate one real selective-face endpoint against its p5 coarse B."""

    comm = view.mesh_data.mesh.comm
    output = Path(artifact_path).resolve()
    authority = _collective_local_call(
        comm,
        "selective-face enriched significant authority load",
        lambda: load_significant_channel_authority(
            significant_channel_authority_path,
            expected_sha256=significant_channel_authority_sha256,
        ),
    )
    if authority is None:
        raise RuntimeError(
            "selective-face enriched significant authority is absent"
        )
    snapshot = load_selective_face_coarse_snapshot(
        coarse_manifest_path,
        communicator=comm,
        expected_manifest_sha256=coarse_manifest_sha256,
        expected_source_sha=source_sha,
        expected_significant_channel_authority_sha256=(
            significant_channel_authority_sha256
        ),
    )
    candidate = _collective_local_call(
        comm,
        "selective-face enriched candidate identity",
        lambda: _candidate_identity(
            view,
            candidate_id=candidate_id,
            expected_plan_sha256=expected_plan_sha256,
            source_sha=source_sha,
        ),
    )
    if candidate is None:
        raise RuntimeError(
            "selective-face enriched candidate identity is absent"
        )
    current_mesh = partition_independent_linear_mesh_identity(
        view.mesh_data
    )
    identity_checks = {
        "same_source_sha": (
            snapshot.manifest["source_sha"] == str(source_sha)
        ),
        "same_mesh": (
            snapshot.manifest["mesh_identity"][
                "partition_independent_mesh_sha256"
            ]
            == current_mesh["partition_independent_mesh_sha256"]
        ),
        "same_normalized_config": (
            snapshot.manifest["normalized_config_identity"][
                "normalized_config_sha256"
            ]
            == _normalized_config_identity(view.config)[
                "normalized_config_sha256"
            ]
        ),
        "same_ordered_modes": (
            snapshot.manifest["mode_identity"]["ordered_modes_sha256"]
            == _mode_identity(view.goal_context)["ordered_modes_sha256"]
        ),
        "same_cell_interior_degree_map": (
            snapshot.manifest["candidate"][
                "cell_interior_degree_sha256"
            ]
            == candidate["cell_interior_degree_sha256"]
        ),
        "same_incident_projections": np.array_equal(
            snapshot.incident_projections,
            np.asarray(view.goal_context["incident_projections"]),
        ),
        "same_auxiliary_coordinate_scales": np.array_equal(
            snapshot.coordinate_scales,
            _coordinate_scales(view.goal_context),
        ),
    }
    if not all(identity_checks.values()):
        raise ValueError(
            "selective-face coarse/enriched identity mismatch: "
            + ", ".join(
                name for name, passed in identity_checks.items() if not passed
            )
        )
    constraints = view.reduction.system.trace_constraints
    if constraints is None or not hasattr(constraints, "authority"):
        raise RuntimeError("enriched endpoint lost physical trace authority")
    transfer = _collective_local_call(
        comm,
        "selective-face physical-root transfer",
        lambda: build_selective_face_root_transfer(
            snapshot.authority,
            constraints.authority,
            auxiliary_rows=int(view.reduction.system.appended_rows),
        ),
    )
    if transfer is None:
        raise RuntimeError("selective-face physical-root transfer is absent")
    transfer_identity = {
        "trace_injection_sha256": transfer.audit[
            "trace_injection_sha256"
        ],
        "total_injection_sha256": transfer.audit[
            "total_injection_sha256"
        ],
        "trace_complement_projector_sha256": transfer.audit[
            "trace_complement_projector_sha256"
        ],
        "coarse_input_identity": transfer.audit[
            "coarse_input_identity"
        ],
        "enriched_input_identity": transfer.audit[
            "enriched_input_identity"
        ],
        "selected_p6_face_geometry_keys": transfer.audit[
            "selected_p6_face_geometry_keys"
        ],
    }
    if len(
        {
            json.dumps(packet, sort_keys=True)
            for packet in comm.allgather(transfer_identity)
        }
    ) != 1:
        raise RuntimeError(
            "selective-face transfer identity differs across MPI ranks"
        )
    galerkin, effective, residual_a, unexplained = _galerkin_audit(
        view,
        snapshot,
        transfer,
    )
    if not galerkin["pass"]:
        failure = {
            "schema_version": _REPORT_SCHEMA,
            "status": "controlled_negative_cross_trace_galerkin_failure",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "cross_trace_galerkin_before_adjoints",
            "identity_checks": identity_checks,
            "root_transfer": dict(transfer.audit),
            "galerkin_audit": galerkin,
            "ordinary_default_changed": False,
        }
        failure_sha256 = _collective_publish_json(comm, output, failure)
        return {
            "schema_version": _REPORT_SCHEMA,
            "status": "selective_face_cross_trace_controlled_negative",
            "pass": False,
            "controlled_negative": True,
            "report_path": str(output),
            "report_sha256": failure_sha256,
            "failure_stage": failure["failure_stage"],
            "ordinary_default_changed": False,
        }
    enriched_relative_residual = float(
        np.linalg.norm(residual_a)
        / max(
            np.linalg.norm(
                _global_petsc_values(view.b, comm)[0]
            ),
            np.finfo(float).tiny,
        )
    )
    enriched_residual_gate = _primal_residual_gate(
        full_active_residual=view.full_active_residual,
        reduced_relative_residual=enriched_relative_residual,
    )
    if not enriched_residual_gate["pass"]:
        failure = {
            "schema_version": _REPORT_SCHEMA,
            "status": "controlled_negative_enriched_primal_residual",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "enriched_primal_residual_before_adjoints",
            "identity_checks": identity_checks,
            "root_transfer": dict(transfer.audit),
            "galerkin_audit": galerkin,
            "enriched_primal_residual_gate": enriched_residual_gate,
            "ordinary_default_changed": False,
        }
        failure_sha256 = _collective_publish_json(comm, output, failure)
        return {
            "schema_version": _REPORT_SCHEMA,
            "status": "selective_face_cross_trace_controlled_negative",
            "pass": False,
            "controlled_negative": True,
            "report_path": str(output),
            "report_sha256": failure_sha256,
            "failure_stage": failure["failure_stage"],
            "ordinary_default_changed": False,
        }

    unit_pairings: dict[str, dict[str, Any]] = {}

    def capture_unit_adjoint(
        identity: dict[str, Any],
        unit_adjoint: PETSc.Vec,
    ) -> None:
        label = _channel_label(identity)
        z, _ = _global_petsc_values(unit_adjoint, comm)
        z_complement = transfer.complement_coordinates(z)
        r_complement = transfer.complement_coordinates(effective)
        faces: dict[tuple[int, ...], complex] = {}
        for key, (start, stop) in transfer.complement_slices.items():
            faces[key] = complex(
                np.vdot(
                    z_complement[start:stop],
                    r_complement[start:stop],
                )
            )
        unit_pairings[label] = {
            "effective": complex(np.vdot(z, effective)),
            "unexplained": complex(np.vdot(z, unexplained)),
            "faces": faces,
            "adjoint_l2_norm": float(np.linalg.norm(z)),
        }

    basis_report = None
    local_basis_error = None
    try:
        basis_report = evaluate_actual_dtn_unit_channel_adjoint_basis(
            linear_system={
                "A": view.A,
                "b": view.b,
                "x": view.x,
                "ksp": view.ksp,
            },
            dtn_result={"goal_context": dict(view.goal_context)},
            config=view.config,
            communicator=comm,
            goals=authority.goals,
            unit_adjoint_observer=capture_unit_adjoint,
        )
    except Exception as exc:
        local_basis_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    basis_errors = [
        error
        for error in comm.allgather(local_basis_error)
        if error is not None
    ]
    if basis_errors:
        failure = {
            "schema_version": _REPORT_SCHEMA,
            "status": "controlled_negative_unit_adjoint_exception",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "unit_channel_adjoint_basis",
            "errors": basis_errors,
            "completed_unit_channel_pairing_count": len(unit_pairings),
            "identity_checks": identity_checks,
            "root_transfer": dict(transfer.audit),
            "galerkin_audit": galerkin,
            "enriched_primal_residual_gate": enriched_residual_gate,
            "ordinary_default_changed": False,
        }
        failure_sha256 = _collective_publish_json(comm, output, failure)
        return {
            "schema_version": _REPORT_SCHEMA,
            "status": "selective_face_cross_trace_controlled_negative",
            "pass": False,
            "controlled_negative": True,
            "report_path": str(output),
            "report_sha256": failure_sha256,
            "failure_stage": failure["failure_stage"],
            "ordinary_default_changed": False,
        }
    if basis_report is None:
        raise RuntimeError(
            "selective-face unit-channel adjoint basis is absent"
        )
    expected_labels = {
        str(channel["label"]) for channel in authority.channels
    }
    if (
        basis_report["pass"] is not True
        or set(unit_pairings) != expected_labels
        or int(basis_report["unit_adjoint_solve_count"]) != 12
    ):
        failure = {
            "schema_version": _REPORT_SCHEMA,
            "status": "controlled_negative_unit_adjoint_incomplete",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "unit_channel_adjoint_basis_gate",
            "observed_unit_pairing_labels": sorted(unit_pairings),
            "expected_unit_pairing_labels": sorted(expected_labels),
            "unit_channel_adjoint_basis": basis_report,
            "identity_checks": identity_checks,
            "root_transfer": dict(transfer.audit),
            "galerkin_audit": galerkin,
            "enriched_primal_residual_gate": enriched_residual_gate,
            "ordinary_default_changed": False,
        }
        failure_sha256 = _collective_publish_json(comm, output, failure)
        return {
            "schema_version": _REPORT_SCHEMA,
            "status": "selective_face_cross_trace_controlled_negative",
            "pass": False,
            "controlled_negative": True,
            "report_path": str(output),
            "report_sha256": failure_sha256,
            "failure_stage": failure["failure_stage"],
            "ordinary_default_changed": False,
        }
    state_a, _ = _global_petsc_values(view.x, comm)
    injected_b = transfer.prolong_primal(snapshot.state_b)
    goal_dwr, ranked_faces = _goal_reports(
        view=view,
        snapshot=snapshot,
        authority=authority,
        basis_report=basis_report,
        unit_pairings=unit_pairings,
        state_delta_norm=float(np.linalg.norm(state_a - injected_b)),
        transfer=transfer,
        complement_unexplained_limit=float(
            galerkin["residuals"]["complement_unexplained_limit"]
        ),
    )
    final_pass = bool(
        enriched_residual_gate["pass"]
        and galerkin["pass"]
        and basis_report["pass"]
        and goal_dwr["pass"]
    )
    report = {
        "schema_version": _REPORT_SCHEMA,
        "status": (
            "selective_face_cross_trace_live_dwr_pass"
            if final_pass
            else "selective_face_cross_trace_live_dwr_fail"
        ),
        "pass": final_pass,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "same_trace_only": False,
        "actual_cross_trace_primal_prolongation_used": True,
        "coarse_snapshot": {
            "manifest_path": str(snapshot.manifest_path),
            "manifest_sha256": str(coarse_manifest_sha256),
            "candidate": snapshot.manifest["candidate"],
        },
        "enriched_candidate": candidate,
        "identity_checks": identity_checks,
        "root_transfer": dict(transfer.audit),
        "galerkin_audit": galerkin,
        "primal_endpoints": {
            "coarse_residual_gate": snapshot.manifest[
                "primal_residual_gate"
            ],
            "enriched_residual_gate": enriched_residual_gate,
            "state_delta_l2_norm": float(
                np.linalg.norm(state_a - injected_b)
            ),
        },
        "significant_channel_authority": {
            "path": str(authority.path),
            "sha256": authority.file_sha256,
            "physical_channel_count": 12,
            "real_goal_count": 36,
        },
        "unit_channel_adjoint_basis": basis_report,
        "goal_dwr": goal_dwr,
        "selected_face_multigoal_marking": {
            "normalization": (
                "absolute signed contribution divided by each frozen "
                "unchanged-v0 channel tolerance"
            ),
            "signed_contributions_used_for_goal_closure": True,
            "absolute_contributions_used_for_marking_only": True,
            "face_count": len(ranked_faces),
            "ranked_faces": ranked_faces,
        },
        "formal_boundary": {
            "this_report_qualifies_the_actual_selected_face_action": True,
            "this_report_does_not_select_unrun_faces": True,
            "full_case095_physics_gate_still_independent": True,
            "hybrid_credit_locked_until_full_full3d_gate": True,
        },
    }
    report_sha256 = _collective_publish_json(comm, output, report)
    return {
        "schema_version": _REPORT_SCHEMA,
        "status": (
            "selective_face_cross_trace_live_dwr_published"
            if report["pass"]
            else "selective_face_cross_trace_controlled_negative"
        ),
        "pass": bool(report["pass"]),
        "controlled_negative": not bool(report["pass"]),
        "report_path": str(output),
        "report_sha256": report_sha256,
        "unit_adjoint_solve_count": int(
            basis_report["unit_adjoint_solve_count"]
        ),
        "passed_real_goal_count": int(
            goal_dwr["passed_real_goal_count"]
        ),
        "ordinary_default_changed": False,
    }


def build_selective_face_coarse_snapshot_observer(**kwargs: Any):
    """Return the default-off coarse cross-trace snapshot callback."""

    def observer(view: Any) -> None:
        write_selective_face_coarse_snapshot(view, **kwargs)

    return observer


def build_selective_face_enriched_evaluator_observer(**kwargs: Any):
    """Return the default-off actual selective-face DWR callback."""

    def observer(view: Any) -> None:
        evaluate_selective_face_enriched_snapshot(view, **kwargs)

    return observer


__all__ = [
    "SelectiveFaceCoarseSnapshot",
    "build_selective_face_coarse_snapshot_observer",
    "build_selective_face_enriched_evaluator_observer",
    "evaluate_selective_face_enriched_snapshot",
    "load_selective_face_coarse_snapshot",
    "write_selective_face_coarse_snapshot",
]
