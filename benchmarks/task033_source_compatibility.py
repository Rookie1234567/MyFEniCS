from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_FULL3D_SOURCE = "bd828f24dc1546263210d73d08bf7bc16ba8a129"
DEFAULT_HYBRID_SOURCE = "95921ab76e39eb1a7c5b3321b93d36939afb4075"

CRITICAL_NUMERICAL_KERNELS = (
    "src/common/config_3d.py",
    "src/geometry/mesh_builder_3d.py",
    "src/constraints/floquet_3d.py",
    "src/constraints/floquet_3d_high_order.py",
    "src/modes/cross_section_spaces.py",
    "src/modes/mode_classification.py",
    "src/modes/quadratic_beta_eigenproblem.py",
    "src/coupling/hybrid_internal_modes.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/hybrid_fem_modal_schur_direct.py",
    "src/solvers/hybrid_local_dtn.py",
)

ALLOWED_CHANGED_PATHS = frozenset(
    {
        (
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
            "stage3_p3_h5/full3d_reference.json"
        ),
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/run_task033_matched_trace.py",
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/task033_matched_trace_qualification.py",
        "src/test/test_66_task033_matched_trace_qualification.py",
        "src/test/test_68_task033_full3d_watchdog.py",
    }
)


def _git(*args: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _source_at(commit: str, path: str, *, root: Path) -> str:
    return _git("show", f"{commit}:{path}", root=root)


class _ReferenceRegistryStripper(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
        if any(
            isinstance(target, ast.Name)
            and target.id == "REFERENCE_BY_DEGREE_AND_H"
            for target in node.targets
        ):
            return None
        return self.generic_visit(node)


def normalized_phase6_ast(source: str) -> str:
    """Return the executable AST with only the reference registry removed."""

    tree = ast.parse(source)
    stripped = _ReferenceRegistryStripper().visit(tree)
    ast.fix_missing_locations(stripped)
    return ast.dump(
        stripped, annotate_fields=True, include_attributes=False
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_full3d_hybrid_source_compatibility_audit(
    *,
    full3d_source: str = DEFAULT_FULL3D_SOURCE,
    hybrid_source: str = DEFAULT_HYBRID_SOURCE,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Prove that accepted p3 direct and Hybrid runs share numerical kernels."""

    root = Path(repo_root).resolve()
    for label, value in (
        ("full3d_source", full3d_source),
        ("hybrid_source", hybrid_source),
    ):
        if FULL_SHA_RE.fullmatch(value) is None:
            raise ValueError(f"{label} must be a full lowercase Git SHA")

    merge_base = _git(
        "merge-base", full3d_source, hybrid_source, root=root
    )
    changed_paths = tuple(
        line
        for line in _git(
            "diff",
            "--name-only",
            f"{full3d_source}..{hybrid_source}",
            root=root,
        ).splitlines()
        if line
    )
    kernel_rows = []
    for path in CRITICAL_NUMERICAL_KERNELS:
        before = _git("rev-parse", f"{full3d_source}:{path}", root=root)
        after = _git("rev-parse", f"{hybrid_source}:{path}", root=root)
        kernel_rows.append(
            {
                "path": path,
                "full3d_blob": before,
                "hybrid_blob": after,
                "identical": before == after,
            }
        )

    phase6_path = "benchmarks/run_task032_phase6_augmented.py"
    before_ast = normalized_phase6_ast(
        _source_at(full3d_source, phase6_path, root=root)
    )
    after_ast = normalized_phase6_ast(
        _source_at(hybrid_source, phase6_path, root=root)
    )
    disallowed = sorted(set(changed_paths) - ALLOWED_CHANGED_PATHS)
    checks = {
        "full3d_source_is_ancestor_of_hybrid_source": (
            merge_base == full3d_source
        ),
        "all_critical_numerical_kernel_blobs_identical": all(
            row["identical"] for row in kernel_rows
        ),
        "phase6_executable_ast_identical_after_reference_registry_removed": (
            before_ast == after_ast
        ),
        "changed_paths_exactly_within_audited_allow_list": not disallowed,
        "same_degree_reference_descriptor_added": (
            (
                "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
                "records/stage3_p3_h5/full3d_reference.json"
            )
            in changed_paths
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task033.phaseD0-source-compatibility.v1",
        "record_type": (
            "task033_full3d_hybrid_source_compatibility_audit"
        ),
        "status": (
            "full3d_hybrid_numerical_source_compatible"
            if not failures
            else "source_compatibility_not_qualified"
        ),
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "ordinary_default_changed": False,
            "scope": "p3_h5_full3d_reference_vs_hybrid_closure",
        },
        "full3d_reference_source_commit_sha": full3d_source,
        "hybrid_closure_source_commit_sha": hybrid_source,
        "merge_base": merge_base,
        "changed_paths": list(changed_paths),
        "allowed_changed_paths": sorted(ALLOWED_CHANGED_PATHS),
        "disallowed_changed_paths": disallowed,
        "critical_numerical_kernels": kernel_rows,
        "phase6_reference_registry_audit": {
            "path": phase6_path,
            "normalized_ast_full3d_sha256": _sha256_text(before_ast),
            "normalized_ast_hybrid_sha256": _sha256_text(after_ast),
            "identical_after_registry_removed": before_ast == after_ast,
            "interpretation": (
                "The accepted Phase6 edit only registers the tracked p3/h5 "
                "full3D descriptor; solver, QEP, coupling, assembly and "
                "postprocessing executable AST remain identical."
            ),
        },
        "checks": checks,
        "failures": failures,
        "compatible": not failures,
        "limitations": [
            (
                "This audit establishes discrete implementation "
                "compatibility, not grid convergence."
            ),
            (
                "The direct and Hybrid formal records retain their distinct "
                "source SHAs."
            ),
        ],
    }
