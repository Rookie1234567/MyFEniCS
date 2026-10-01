"""Explicit reviewed cross-HEAD bridge to the frozen centered p2 authority.

This source-diff contract only admits a numerical comparison. It never grants
equivalence: the new run must independently qualify its live carrier, compare
all 2048 operator columns and four complete original fields and mode outputs.
"""
from __future__ import annotations

AUTHORITY_HEAD = "7c4410dbc55bce804d148493760d4de68acd8405"
AUTHORITY_REPORT_SHA256 = "33415b7a1cde1001c4945cfa88b8517fc351478cf1b022b9ff9770b70dea6859"
AUTHORITY_CHECKER_SHA256 = "d2b3a4d28411db477899509ac0bf86deda79c12222029502ec408af05e81e1e7"
AUTHORITY_PROVENANCE_SHA256 = "172be941df7e64a4f9b789149ed251f585297ad67fe3b2b15be2957f164c44a7"

# Each path belongs to the reviewed p4 profile/receipt extension. The six
# physical assembly/gauge/config/generator sources are deliberately absent.
REVIEWED_EXTENSION_PATHS = frozenset({
    "src/solvers/dtn_boundary_plane_qualification.py",
    "src/solvers/y_orbit_live_boundary_contract.py",
    "src/solvers/y_orbit_centered_evidence.py",
    "src/solvers/y_orbit_centered_bridge.py",
    "src/solvers/y_orbit_sparse_probe.py",
    "benchmarks/run_y_orbit_sparse_probe.py",
    "benchmarks/check_y_orbit_sparse_probe.py",
    "src/test/test_dtn_boundary_live_qualification.py",
    "src/test/test_dtn_boundary_plane_degree_profiles.py",
    "src/test/test_y_orbit_live_boundary_contract.py",
    "src/test/test_y_orbit_centered_contracts.py",
    "src/test/test_y_orbit_p4_centered_contracts.py",
    "benchmarks/cases/y_orbit_sparse_reference/centered_p4_admission_plan_v1_zh.md",
})


def cross_head_source_binding(authority_source, executed_source):
    """Record every old/new byte identity and reject unrelated source changes."""
    if (authority_source["head"] != AUTHORITY_HEAD
            or authority_source["branch"] != "task40extra_dot_parallel_cloud"
            or executed_source["branch"] != authority_source["branch"]
            or authority_source["dirty"] or executed_source["dirty"]):
        raise ValueError("cross-HEAD centered bridge requires the frozen clean authority and own source")
    old, new = authority_source["files_sha256"], executed_source["files_sha256"]
    changed = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
    if not set(changed).issubset(REVIEWED_EXTENSION_PATHS):
        raise ValueError("unreviewed source/config change in centered cross-HEAD bridge")
    return {"authority_head": authority_source["head"], "executed_head": executed_source["head"],
            "changed_dependencies": [{"path": p, "authority_sha256": old.get(p),
                                       "executed_sha256": new.get(p)} for p in changed],
            "unchanged_dependency_count": len((set(old) | set(new)) - set(changed)),
            "reviewed_extension_paths": sorted(REVIEWED_EXTENSION_PATHS),
            "numerical_equivalence_requires_all_columns_fields_and_outputs": True}


def compare_bridge_discrete_contract(authority, executed, source_binding):
    """Compare every discrete field, recording the one reviewed helper change.

    Full raw contexts and loaded C identities remain separately bound to their
    own live receipts. The helper source changes to enable degree4; no physical
    assembly dependency may change even when all other input fields match.
    """
    if set(authority) != set(executed):
        raise ValueError("cross-HEAD fixed discrete inventory differs")
    for field in authority:
        if field != "source_sha256" and authority[field] != executed[field]:
            raise ValueError("cross-HEAD fixed physical/discrete field differs: " + field)
    old, new = authority["source_sha256"], executed["source_sha256"]
    if set(old) != set(new):
        raise ValueError("cross-HEAD raw numerical source inventory differs")
    diffs = {name for name in old if old[name] != new[name]}
    if not diffs.issubset({"dtn_boundary_plane_qualification.py"}):
        raise ValueError("physical assembly source changed in centered bridge")
    source_diffs = {r["path"]: r for r in source_binding["changed_dependencies"]}
    for name in diffs:
        record = source_diffs.get("src/solvers/" + name)
        if (record is None or record["authority_sha256"] != old[name]
                or record["executed_sha256"] != new[name]):
            raise ValueError("context helper source not bound to exact old/new worker bytes")
    return {"all_nonnumerical_and_discrete_inputs_equal": True,
            "raw_context_source_changes": sorted(diffs),
            "raw_compiler_identity_equivalence_assumed": False,
            "requires_all_2048_columns_and_four_load_controls": True}
