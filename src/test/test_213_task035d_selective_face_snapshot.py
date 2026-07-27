from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mpi4py import MPI
import numpy as np
import pytest
from scipy import sparse

from src.adaptivity import variable_p_selective_face_dwr as dwr


_SOURCE_SHA = "1" * 40
_CHANNEL_SHA = "2" * 64


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_snapshot(
    directory: Path,
    *,
    inconsistent_residual: bool = False,
    nonidentity_root: bool = False,
) -> tuple[Path, str]:
    trace_rows = 40
    auxiliary_rows = 2
    matrix_rows = trace_rows + auxiliary_rows
    rng = np.random.default_rng(20260727)
    state = (
        rng.standard_normal(matrix_rows)
        + 1j * rng.standard_normal(matrix_rows)
    )
    rhs = (
        rng.standard_normal(matrix_rows)
        + 1j * rng.standard_normal(matrix_rows)
    )
    action = rhs.copy()
    residual = rhs - action
    if inconsistent_residual:
        residual = residual.copy()
        residual[0] = 1.0e-3 + 2.0e-3j
    probes = (
        rng.standard_normal((matrix_rows, 3))
        + 1j * rng.standard_normal((matrix_rows, 3))
    )
    probe_actions = (
        rng.standard_normal((matrix_rows, 3))
        + 1j * rng.standard_normal((matrix_rows, 3))
    )
    scales = np.asarray([2.0 + 0.0j, 3.0 + 0.0j])
    auxiliary = state[-auxiliary_rows:] / scales
    incident = np.zeros(auxiliary_rows, dtype=np.complex128)
    expansion = sparse.eye(
        trace_rows,
        dtype=np.complex128,
        format="lil",
    )
    if nonidentity_root:
        expansion[0, 0] = 0.5
    expansion = expansion.tocsr()
    arrays = {
        "schema_version": np.asarray(
            [dwr._ARRAY_SCHEMA],
            dtype=np.str_,
        ),
        "state_b": state,
        "rhs_b": rhs,
        "action_b_on_b": action,
        "residual_b": residual,
        "probe_vectors": probes,
        "probe_actions": probe_actions,
        "auxiliary_values_b": auxiliary,
        "incident_projections": incident,
        "coordinate_scales": scales,
        **dwr._csr_arrays(expansion, prefix="physical_graph"),
    }
    arrays_path = directory / "coarse_arrays.npz"
    np.savez(arrays_path, **arrays)
    catalog = [
        {
            "dimension": 2,
            "geometry_key": [2, 1, 0, 1, 0, 1],
            "degree": 5,
            "canonical_points": [
                [0, 0, 1],
                [0, 1, 1],
                [1, 0, 1],
                [1, 1, 1],
            ],
            "mode_count": trace_rows,
        }
    ]
    relative_residual = float(
        np.linalg.norm(residual)
        / max(np.linalg.norm(rhs), np.finfo(float).tiny)
    )
    vector_identity = {
        "state_b_sha256": dwr._array_sha256(
            state,
            namespace="task035d.selective-face-state-b.v1",
        ),
        "rhs_b_sha256": dwr._array_sha256(
            rhs,
            namespace="task035d.selective-face-rhs-b.v1",
        ),
        "action_b_on_b_sha256": dwr._array_sha256(
            action,
            namespace="task035d.selective-face-action-b.v1",
        ),
        "residual_b_sha256": dwr._array_sha256(
            residual,
            namespace="task035d.selective-face-residual-b.v1",
        ),
        "auxiliary_values_b_sha256": dwr._array_sha256(
            auxiliary,
            namespace="task035d.selective-face-auxiliary-values-b.v1",
        ),
        "incident_projections_sha256": dwr._array_sha256(
            incident,
            namespace=(
                "task035d.selective-face-incident-projections.v1"
            ),
        ),
        "coordinate_scales_sha256": dwr._array_sha256(
            scales,
            namespace="task035d.selective-face-coordinate-scales.v1",
        ),
        "relative_residual": relative_residual,
    }
    manifest: dict[str, Any] = {
        "schema_version": dwr._SNAPSHOT_SCHEMA,
        "pass": True,
        "source_sha": _SOURCE_SHA,
        "significant_channel_authority": {"sha256": _CHANNEL_SHA},
        "base_trace_degree": 5,
        "independent_trace_rows": trace_rows,
        "auxiliary_rows": auxiliary_rows,
        "matrix_rows": matrix_rows,
        "physical_entity_catalog": catalog,
        "physical_entity_catalog_sha256": dwr._json_sha256(
            catalog,
            namespace="task035d.selective-face-entity-catalog.v1",
        ),
        "physical_root_raw_indices": list(range(trace_rows)),
        "physical_graph_sha256": dwr._csr_sha256(
            expansion,
            namespace="task035d.selective-face-physical-graph.v1",
        ),
        "physical_authority_sha256": "3" * 64,
        "probe_contract": {
            "probe_vectors_sha256": dwr._array_sha256(
                probes,
                namespace="task035d.selective-face-probes.v1",
            ),
            "probe_actions_sha256": dwr._array_sha256(
                probe_actions,
                namespace="task035d.selective-face-probe-actions.v1",
            ),
        },
        "arrays": {
            "path": arrays_path.name,
            "sha256": _file_sha256(arrays_path),
        },
        "vector_identity": vector_identity,
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, _file_sha256(manifest_path)


def _load(path: Path, digest: str) -> dwr.SelectiveFaceCoarseSnapshot:
    return dwr.load_selective_face_coarse_snapshot(
        path,
        communicator=MPI.COMM_SELF,
        expected_manifest_sha256=digest,
        expected_source_sha=_SOURCE_SHA,
        expected_significant_channel_authority_sha256=_CHANNEL_SHA,
    )


def test_selective_face_snapshot_round_trip_recomputes_semantics(
    tmp_path: Path,
) -> None:
    manifest, digest = _write_snapshot(tmp_path)
    snapshot = _load(manifest, digest)
    assert snapshot.manifest["matrix_rows"] == 42
    assert snapshot.authority.graph.component_gram.shape == (40, 40)
    assert np.allclose(
        snapshot.authority.graph.component_gram.toarray(),
        np.eye(40),
    )


def test_selective_face_snapshot_rejects_self_hashed_wrong_residual(
    tmp_path: Path,
) -> None:
    manifest, digest = _write_snapshot(
        tmp_path,
        inconsistent_residual=True,
    )
    with pytest.raises(RuntimeError, match="residual is not rhs minus action"):
        _load(manifest, digest)


def test_selective_face_snapshot_rejects_nonidentity_root_rows(
    tmp_path: Path,
) -> None:
    manifest, digest = _write_snapshot(
        tmp_path,
        nonidentity_root=True,
    )
    with pytest.raises(RuntimeError, match="roots do not inject as identity"):
        _load(manifest, digest)
