"""Fail-closed Task034 evidence-to-current numerical blob audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "82a5107b5c2bfe4c466a0d00ead31d7b172e2af4"
COMPLETION_RECORD = (
    ROOT / "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
    "task033_reduced_scope_completion.json"
)
NUMERICAL_KERNELS = (
    "src/common/config_3d.py",
    "src/common/analytic_fields_3d.py",
    "src/common/high_order_quadrature.py",
    "src/geometry/mesh_builder_3d.py",
    "src/constraints/floquet_3d.py",
    "src/constraints/floquet_3d_high_order.py",
    "src/constraints/high_order_floquet_trace.py",
    "src/constraints/cross_section_floquet.py",
    "src/modes/cross_section_spaces.py",
    "src/modes/quadratic_beta_eigenproblem.py",
    "src/modes/mode_classification.py",
    "src/coupling/hybrid_internal_modes.py",
    "src/coupling/modal_trace_projection.py",
    "src/postprocessing/hybrid_field_reconstruction.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/common_3d_fields.py",
    "src/solvers/common_3d_postprocess.py",
    "src/solvers/dtn_port_3d.py",
    "src/solvers/hybrid_local_dtn.py",
    "src/solvers/hybrid_fem_modal_schur_direct.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/hcurl_multilevel.py",
)
INTENTIONAL_CLASSIFICATIONS = {
    "src/common/config_3d.py": {
        "classification": "diagnostic only",
        "reason": "explicit factorization-only Gate flag defaults off; physical and full-solve configuration unchanged",
        "requires_corresponding_pde_rerun": False,
    },
    "src/constraints/floquet_3d_high_order.py": {
        "classification": "lifecycle only",
        "reason": "weak-owner cache lookup and explicit clear; topology coefficients unchanged",
        "requires_corresponding_pde_rerun": False,
    },
    "src/constraints/high_order_floquet_trace.py": {
        "classification": "lifecycle only",
        "reason": "cache ownership storage changed from strong to weak references",
        "requires_corresponding_pde_rerun": False,
    },
    "src/modes/mode_classification.py": {
        "classification": "numerical kernel intentionally changed and requires PDE rerun",
        "reason": "batched QEP overlap evaluation reuses MatMult actions and performs the final cancellation in extended precision; Hybrid QEP/PDE anchors must be rerun",
        "requires_corresponding_pde_rerun": True,
    },
    "src/solvers/common_3d_case_flow.py": {
        "classification": "diagnostic only",
        "reason": "factorization-only status and postprocess skip path; ordinary solve path unchanged",
        "requires_corresponding_pde_rerun": False,
    },
    "src/solvers/dtn_port_3d.py": {
        "classification": "diagnostic only",
        "reason": "explicit return after KSPSetUp for staged Gate; KSPSolve path unchanged when the flag is false",
        "requires_corresponding_pde_rerun": False,
    },
    "src/solvers/hybrid_fem_modal_schur_direct.py": {
        "classification": "numerical kernel intentionally changed and requires PDE rerun",
        "reason": "explicit MUMPS ICNTL(14)=100 workspace relaxation prevents INFOG(1)=-9 local-factor failures; Hybrid PDE anchors must be rerun",
        "requires_corresponding_pde_rerun": True,
    },
    "src/solvers/hcurl_multilevel.py": {
        "classification": "numerical kernel intentionally changed and requires PDE rerun",
        "reason": "materialized P^H compatibility path for PETSc 3.19 complex MatMatMult; algebra unchanged",
        "requires_corresponding_pde_rerun": True,
    },
}
ALLOWED_CLASSIFICATIONS = {
    "numerical kernel unchanged", "numerical kernel intentionally changed and requires PDE rerun",
    "diagnostic only", "lifecycle only", "resource-monitoring only", "documentation/test only",
}


def _git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_record() -> dict[str, Any]:
    baseline_resolved = _git_bytes("rev-parse", BASELINE_COMMIT).decode().strip()
    completion_bytes = COMPLETION_RECORD.read_bytes()
    completion = json.loads(completion_bytes)
    rows = []
    failures = []
    requires_rerun = []
    for relative in NUMERICAL_KERNELS:
        baseline = _git_bytes("show", f"{BASELINE_COMMIT}:{relative}")
        current_path = ROOT / relative
        if not current_path.is_file():
            rows.append({"path": relative, "classification": "missing", "pass": False})
            failures.append(f"missing:{relative}")
            continue
        current = current_path.read_bytes()
        unchanged = current == baseline
        classification = (
            {"classification": "numerical kernel unchanged", "reason": "byte-identical to Task034 base",
             "requires_corresponding_pde_rerun": False}
            if unchanged else INTENTIONAL_CLASSIFICATIONS.get(relative)
        )
        if classification is None:
            classification = {
                "classification": "unclassified numerical change",
                "reason": "no Task034 allowlisted classification",
                "requires_corresponding_pde_rerun": True,
            }
        passed = classification["classification"] in ALLOWED_CLASSIFICATIONS
        if not passed:
            failures.append(f"unclassified_change:{relative}")
        if classification["requires_corresponding_pde_rerun"]:
            requires_rerun.append(relative)
        rows.append({
            "path": relative,
            "baseline_sha256": _sha256(baseline),
            "current_sha256": _sha256(current),
            "byte_identical": unchanged,
            **classification,
            "pass": passed,
        })
    checks = {
        "baseline_commit_exact": baseline_resolved == BASELINE_COMMIT,
        "task033_completion_status_accepted": completion.get("status") == "task033_reduced_scope_complete",
        "task033_original_full_scope_not_upgraded": completion.get("identity", {}).get("original_task033_full_scope_complete") is False,
        "all_required_kernel_paths_present": len(rows) == len(NUMERICAL_KERNELS) and all(row["pass"] for row in rows),
        "all_changes_classified": not failures,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    return {
        "schema_version": "task034.numerical-blob-compatibility.v1",
        "record_type": "evidence_to_current_checkout_numerical_blob_audit",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "numerical_blob_compatibility_pass" if not failures else "numerical_blob_compatibility_fail",
        "formal_pass": not failures,
        "baseline": {
            "commit_sha": BASELINE_COMMIT,
            "task033_completion_record": str(COMPLETION_RECORD.relative_to(ROOT)),
            "task033_completion_sha256": _sha256(completion_bytes),
            "review_authority": completion.get("review_authority"),
        },
        "rows": rows,
        "corresponding_pde_rerun_required_paths": requires_rerun,
        "checks": checks,
        "failures": failures,
        "identity": {"is_pde_run": False, "ordinary_default_changed": False},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    record = build_record()
    rendered = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": record["status"], "failures": record["failures"]}, ensure_ascii=False))
    return 0 if record["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
