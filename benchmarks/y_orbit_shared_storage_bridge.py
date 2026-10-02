"""Exact same80 storage-only source permission; no numerical imports.

The original executed worker is a separate immutable baseline. Its report is
used solely to recover the complete source/ABI inventory, never as a candidate
source identity or as a substitute for the new equivalence gates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

WORKER_HEAD = "5e0364cd2eebfffb63a5f3ee8bda8e21083b2495"
WORKER_RUN = "y_orbit_quotient_p4_phi5_solve_attempt1"
WORKER_REPORT_SHA256 = "32a9ee70f2641d2465b2b12431526b7f204bbc524b9ed18e12553734e6896352"
WORKER_SOURCE_MANIFEST_SHA256 = "5a57a2b067541da0bde4cfc7060b77e21846ae794984873c3a2ac6c1275099b0"
SCHEMA = "task40extra.same80-shared-storage-source-bridge.v1"
ALLOWED_PATHS = frozenset({
    "src/solvers/task40extra_y_orbit_reference.py",
    "src/solvers/y_orbit_transform_bank.py",
    "src/solvers/y_orbit_shared_transform_evidence.py",
    "src/solvers/y_orbit_two_cell_inverse_probe.py",
    "src/solvers/y_orbit_qualified_snapshot.py",
    "benchmarks/y_orbit_two_cell_authority.py",
    "benchmarks/y_orbit_shared_storage_bridge.py",
    "benchmarks/run_y_orbit_quotient_probe.py",
    "benchmarks/check_y_orbit_quotient_probe.py",
    "src/test/test_y_orbit_transform_bank.py",
    "src/test/test_y_orbit_shared_storage_metadata.py",
    "src/test/test_y_orbit_quotient_checker_sort_metadata.py",
})
REQUIRED_CHANGED_PATHS = ALLOWED_PATHS - {
    "src/test/test_y_orbit_transform_bank.py",
    "src/test/test_y_orbit_shared_storage_metadata.py",
    "src/test/test_y_orbit_quotient_checker_sort_metadata.py",
}
ENVIRONMENT_FIELDS = ("python", "prefix", "modules", "petsc_scalar_type", "petsc_int_type",
    "petsc_version", "mpi_library", "qualification_manifest_sha256", "qualification_scope")
REQUIRED_EQUIVALENCE_ROLES = ("full", "twist_0", "twist_1")


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def validate_storage_source_bridge(worker_source, new_source, worker_environment, new_environment):
    """Only reviewed representation files may differ from the executed source."""
    if (worker_source.get("head") != WORKER_HEAD or worker_source.get("dirty")
            or new_source.get("dirty") or new_source.get("head") == WORKER_HEAD
            or not re.fullmatch(r"[0-9a-f]{40}", new_source.get("head", ""))
            or worker_source.get("branch") != "task40extra_dot_parallel_cloud"
            or new_source.get("branch") != worker_source.get("branch")):
        raise ValueError("storage bridge requires immutable worker5e and actual distinct clean own-branch source")
    old, new = worker_source.get("files_sha256", {}), new_source.get("files_sha256", {})
    if (not old or not new or digest_json(old) != WORKER_SOURCE_MANIFEST_SHA256
            or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in list(old.values()) + list(new.values()))):
        raise ValueError("complete pinned worker and actual new source inventories required")
    changed = sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))
    if (not set(changed).issubset(ALLOWED_PATHS) or not REQUIRED_CHANGED_PATHS.issubset(changed)
            or any(path not in new for path in ALLOWED_PATHS)):
        raise ValueError("storage bridge permits only the complete explicitly reviewed same80 representation paths")
    if any(name not in worker_environment or name not in new_environment
           or worker_environment[name] != new_environment[name] for name in ENVIRONMENT_FIELDS):
        raise ValueError("storage bridge numerical/configuration ABI differs")
    return {"schema": SCHEMA, "worker_head": WORKER_HEAD, "new_head": new_source["head"],
        "worker_report_sha256": WORKER_REPORT_SHA256,
        "worker_source_manifest_sha256": digest_json(old), "new_source_manifest_sha256": digest_json(new),
        "allowed_paths": sorted(ALLOWED_PATHS), "changed_paths": changed,
        "changed_dependencies": [{"path": path, "worker_sha256": old.get(path), "new_sha256": new.get(path)}
                                 for path in changed],
        "all_other_numerical_config_input_dependencies_equal": True,
        "environment_fields_equal": list(ENVIRONMENT_FIELDS), "source_equality_claimed": False,
        "qualification": "same80 storage-only; complete actual equivalence required before any factor",
        "required_pre_factor_equivalence_roles": list(REQUIRED_EQUIVALENCE_ROLES)}


def load_storage_source_bridge(artifact_root, *, new_source, new_environment, allocation_gate):
    """Verify immutable report bytes before admitting the scoped source bridge."""
    path = Path(artifact_root).resolve() / WORKER_RUN / "probe_report.json"
    if not path.is_file() or path.parent.name != WORKER_RUN or not callable(allocation_gate):
        raise ValueError("immutable original worker report and measured allocation gate required")
    allocation_gate("shared_storage_worker_source_metadata", {
        "matrix_payload_bytes": 0, "workspace_bytes": 8 * path.stat().st_size + (2 << 20)})
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != WORKER_REPORT_SHA256:
        raise ValueError("immutable original worker report changed")
    report = json.loads(raw)
    if (report.get("status") != "QUOTIENT_FULL3D_INVERSE_PROBE_PASS"
            or report.get("source_clean_unchanged") is not True or report.get("degree") != 4
            or report.get("physical_mode_count") != 532 or report.get("factor_count") != 4):
        raise ValueError("original same80 executed worker identity differs")
    receipt = validate_storage_source_bridge(report["source"], new_source, report["environment"], new_environment)
    return {"receipt": receipt, "worker_source": report["source"], "worker_environment": report["environment"],
            "worker_snapshot_source_bridge": report["authority"]["source_bridge"],
            "worker_full_p4_source_bridge": report["saved_full_p4_authority"]["old_new_dependency_diff"]}


def validate_loaded_storage_bridge(bridge, *, new_source, new_environment):
    if not isinstance(bridge, dict):
        raise ValueError("explicit immutable storage bridge required")
    expected = validate_storage_source_bridge(bridge["worker_source"], new_source,
                                             bridge["worker_environment"], new_environment)
    if bridge.get("receipt") != expected:
        raise ValueError("storage bridge receipt detached from actual source/ABI")
    return expected
