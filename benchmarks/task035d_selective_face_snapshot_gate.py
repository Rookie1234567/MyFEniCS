"""Artifact Gate for the Task035d selective-face coarse snapshot."""

from __future__ import annotations

from typing import Any, Mapping


COARSE_CANDIDATE_ID = "h15_top_air_local_h_v1"
COARSE_FULL3D_EQUIVALENT_DOFS = 82_925
COARSE_INDEPENDENT_TRACE_ROWS = 18_390
DTN_AUXILIARY_ROWS = 80


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def task035d_selective_face_coarse_snapshot_gate(
    manifest: Mapping[str, Any] | None,
    *,
    expected_source_sha: str,
    expected_plan_sha256: str,
    expected_significant_channel_authority_sha256: str,
    observed_arrays_sha256: str | None,
) -> dict[str, Any]:
    """Validate the immutable p5-trace endpoint before enriched launch."""

    manifest = manifest if isinstance(manifest, Mapping) else {}
    candidate = manifest.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    authority = manifest.get("significant_channel_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    arrays = manifest.get("arrays")
    arrays = arrays if isinstance(arrays, Mapping) else {}
    residual = manifest.get("primal_residual_gate")
    residual = residual if isinstance(residual, Mapping) else {}
    probe = manifest.get("probe_contract")
    probe = probe if isinstance(probe, Mapping) else {}
    checks = {
        "schema_and_status": (
            manifest.get("schema_version")
            == "task035d.selective-face-coarse-snapshot.v1"
            and manifest.get("status")
            == "selective_face_coarse_snapshot_pass"
            and manifest.get("pass") is True
            and manifest.get("production_qualified") is False
        ),
        "source_and_candidate": (
            _valid_hex(expected_source_sha, 40)
            and manifest.get("source_sha") == expected_source_sha
            and candidate.get("source_sha") == expected_source_sha
            and candidate.get("candidate_id") == COARSE_CANDIDATE_ID
            and candidate.get("plan_file_sha256")
            == expected_plan_sha256
            and candidate.get(
                "actual_full3d_equivalent_active_fe_dofs"
            )
            == COARSE_FULL3D_EQUIVALENT_DOFS
        ),
        "pure_p5_trace_endpoint": (
            manifest.get("base_trace_degree") == 5
            and manifest.get("independent_trace_rows")
            == COARSE_INDEPENDENT_TRACE_ROWS
            and manifest.get("auxiliary_rows") == DTN_AUXILIARY_ROWS
            and manifest.get("matrix_rows")
            == COARSE_INDEPENDENT_TRACE_ROWS + DTN_AUXILIARY_ROWS
        ),
        "significant_channel_authority": (
            _valid_hex(
                expected_significant_channel_authority_sha256,
                64,
            )
            and authority.get("sha256")
            == expected_significant_channel_authority_sha256
            and authority.get("physical_channel_count") == 12
            and authority.get("real_goal_count") == 36
        ),
        "semantic_hashes_present": (
            _valid_hex(
                manifest.get("physical_entity_catalog_sha256"),
                64,
            )
            and _valid_hex(manifest.get("physical_graph_sha256"), 64)
            and _valid_hex(
                manifest.get("physical_authority_sha256"),
                64,
            )
            and _valid_hex(
                probe.get("probe_vectors_sha256"),
                64,
            )
            and _valid_hex(
                probe.get("probe_actions_sha256"),
                64,
            )
        ),
        "three_galerkin_probes": (
            probe.get("probe_count") == 3
            and probe.get("roles")
            == [
                "trace_only_random",
                "auxiliary_only_random",
                "combined_random",
            ]
        ),
        "array_artifact_hash": (
            _valid_hex(observed_arrays_sha256, 64)
            and arrays.get("sha256") == observed_arrays_sha256
            and arrays.get("path") == "coarse_arrays.npz"
        ),
        "coarse_primal_residual": (
            residual.get("pass") is True
            and isinstance(residual.get("checks"), Mapping)
            and residual["checks"]
            and all(value is True for value in residual["checks"].values())
        ),
        "ordinary_default_unchanged": (
            manifest.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "task035d.selective-face-coarse-snapshot-gate.v1"
        ),
        "status": (
            "selective_face_coarse_snapshot_gate_pass"
            if not failures
            else "selective_face_coarse_snapshot_gate_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "enriched_launch_gate": not failures,
        "ordinary_default_changed": False,
    }


__all__ = ["task035d_selective_face_coarse_snapshot_gate"]
