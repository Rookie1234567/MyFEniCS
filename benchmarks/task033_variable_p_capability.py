from __future__ import annotations

from dataclasses import dataclass
import importlib
import inspect
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENVIRONMENT_RECORD = ROOT / "benchmarks" / "environment.json"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class RepositorySourceState:
    """One complete Git source snapshot, including non-ignored untracked files."""

    head_sha: str
    porcelain_lines: tuple[str, ...]

    @property
    def complete_clean(self) -> bool:
        return not self.porcelain_lines


def inspect_repository_source(repo_root: Path = ROOT) -> RepositorySourceState:
    """Read HEAD and full non-ignored worktree status without changing Git state."""

    root = Path(repo_root).resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise RuntimeError(f"cannot read Git HEAD: {head.stderr.strip()}")
    sha = head.stdout.strip().lower()
    if FULL_SHA_RE.fullmatch(sha) is None:
        raise RuntimeError("formal source requires one complete 40-character Git HEAD")
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=no",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        raise RuntimeError(f"cannot read complete Git status: {status.stderr.strip()}")
    return RepositorySourceState(
        head_sha=sha,
        porcelain_lines=tuple(
            line for line in status.stdout.splitlines() if line.strip()
        ),
    )


def qualify_formal_source(
    before: RepositorySourceState,
    after: RepositorySourceState,
) -> dict[str, Any]:
    """Require one clean, stable checkout across a formal runner invocation."""

    failures: list[str] = []
    if not before.complete_clean:
        failures.append("source_not_completely_clean_before")
    if not after.complete_clean:
        failures.append("source_not_completely_clean_after")
    if before.head_sha != after.head_sha:
        failures.append("source_head_changed_during_run")
    if FULL_SHA_RE.fullmatch(before.head_sha) is None:
        failures.append("source_head_before_not_full_sha")
    if FULL_SHA_RE.fullmatch(after.head_sha) is None:
        failures.append("source_head_after_not_full_sha")
    if failures:
        raise RuntimeError(f"formal source gate failed: {failures!r}")
    return {
        "commit_sha": before.head_sha,
        "tracked_source_clean": True,
        "head_before_sha": before.head_sha,
        "head_after_sha": after.head_sha,
        "source_stable_during_run": True,
        "nonignored_untracked_clean": True,
        "complete_worktree_clean": True,
    }


def _public_signature(value: Any) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _probe_symbol(module_name: str, symbol: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - depends on the active runtime
        return {
            "module": module_name,
            "symbol": symbol,
            "available": False,
            "error_type": type(exc).__name__,
            "signature": None,
        }

    value = getattr(module, symbol, None)
    return {
        "module": module_name,
        "symbol": symbol,
        "available": value is not None,
        "error_type": None,
        "signature": _public_signature(value) if value is not None else None,
    }


def probe_active_runtime() -> dict[str, Any]:
    """Inspect only public imports and symbols in the current Python process.

    Symbol presence is deliberately kept separate from semantic qualification.
    A mixed field or mixed-topology form is not evidence that adjacent H(curl)
    cells may safely use different polynomial orders.
    """

    package_modules = {
        "basix": "basix",
        "dolfinx": "dolfinx",
        "ufl": "ufl",
    }
    packages: dict[str, Any] = {}
    for name, module_name in package_modules.items():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - active-runtime dependent
            packages[name] = {
                "imported": False,
                "version": None,
                "error_type": type(exc).__name__,
            }
        else:
            packages[name] = {
                "imported": True,
                "version": getattr(module, "__version__", None),
                "error_type": None,
            }

    symbols = {
        "basix_ufl_element": _probe_symbol("basix.ufl", "element"),
        "basix_ufl_mixed_element": _probe_symbol("basix.ufl", "mixed_element"),
        "dolfinx_functionspace": _probe_symbol("dolfinx.fem", "functionspace"),
        "dolfinx_mixed_topology_form": _probe_symbol(
            "dolfinx.fem", "mixed_topology_form"
        ),
        "dolfinx_create_submesh": _probe_symbol("dolfinx.mesh", "create_submesh"),
        "ufl_mixed_function_space": _probe_symbol("ufl", "MixedFunctionSpace"),
    }
    return {
        "data_identity": "direct_current_python_import_and_public_symbol_probe",
        "packages": packages,
        "symbols": symbols,
    }


def _repository_environment_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "data_identity": "repository_pinned_environment_record_not_direct_import",
        "record": path.relative_to(ROOT).as_posix(),
        "reproducibility_status": payload.get("reproducibility_status"),
        "python": payload.get("python"),
        "dolfinx": payload.get("dolfinx"),
        "petsc": payload.get("petsc"),
        "mpi4py": payload.get("mpi4py"),
        "petsc_scalar_type": payload.get("petsc_scalar_type"),
        "basix_version": None,
        "limitation": (
            "This file identifies the pinned qualified image, but does not prove "
            "cellwise variable-order H(curl) semantics or current-host imports."
        ),
    }


def build_variable_p_capability_audit(
    *,
    runtime_probe: dict[str, Any] | None = None,
    environment_record: Path = DEFAULT_ENVIRONMENT_RECORD,
    formal_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed Task033 audit, never a bespoke hp implementation.

    Public API introspection can establish that a symbol exists. It cannot by
    itself establish conformity, periodic synchronization, ownership, or trace
    correctness for cellwise heterogeneous-order Nedelec spaces. Consequently
    every semantic requirement remains unqualified until an independent native
    sparse implementation and numerical/MPI qualification record exists.
    """

    direct = probe_active_runtime() if runtime_probe is None else runtime_probe
    symbols = direct.get("symbols", {})
    mixed_field_symbols = (
        symbols.get("basix_ufl_mixed_element", {}).get("available", False)
        or symbols.get("ufl_mixed_function_space", {}).get("available", False)
    )
    mixed_topology_symbol = symbols.get("dolfinx_mixed_topology_form", {}).get(
        "available", False
    )

    requirements = [
        {
            "requirement": "cellwise_variable_order_nedelec",
            "qualified": False,
            "reason": "no_native_operational_evidence_record",
        },
        {
            "requirement": "tangential_continuity_across_unequal_p_neighbors",
            "qualified": False,
            "reason": "no_native_conformity_and_orientation_evidence_record",
        },
        {
            "requirement": "periodic_paired_face_synchronized_p",
            "qualified": False,
            "reason": "no_native_periodic_pairing_evidence_record",
        },
        {
            "requirement": "high_order_interface_trace",
            "qualified": False,
            "reason": "fixed_p_trace_evidence_does_not_qualify_variable_p",
        },
        {
            "requirement": "mpi_partition_ownership",
            "qualified": False,
            "reason": "no_variable_p_mpi_ownership_evidence_record",
        },
        {
            "requirement": "maintainable_submesh_or_multimesh_coupling",
            "qualified": False,
            "reason": "submesh_api_presence_does_not_prove_variable_p_coupling",
        },
    ]

    record = {
        "schema_version": "task033.case091.variable-p-audit.v1",
        "record_type": "task033_variable_p_hcurl_capability_audit",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "not_qualified_fail_closed",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_capability_implementation": False,
            "is_formal_record": formal_source is not None,
            "ordinary_default_changed": False,
            "proves_native_cellwise_variable_p": False,
            "proves_0p7nm_feasible": False,
        },
        "runtime_evidence": {
            "active_python": direct,
            "repository_environment": _repository_environment_evidence(
                environment_record
            ),
        },
        "api_interpretation": {
            "mixed_fields": {
                "public_symbol_observed": bool(mixed_field_symbols),
                "scope": "product space combining multiple fields/elements",
                "counts_as_cellwise_variable_p_evidence": False,
            },
            "mixed_topology": {
                "public_symbol_observed": bool(mixed_topology_symbol),
                "scope": "form assembly across cell types/topologies",
                "counts_as_cellwise_variable_p_evidence": False,
            },
            "cellwise_polynomial_order": {
                "native_sparse_operational_path_observed": False,
                "scope": "different Nedelec p on adjacent cells with conformity",
                "counts_as_qualified": False,
            },
        },
        "semantic_requirements": requirements,
        "decision": {
            "native_cellwise_variable_p_hcurl_qualified": False,
            "implement_bespoke_arbitrary_variable_p_constraints": False,
            "disposition": "fail_closed_no_hp_zoning_prototype",
            "allowed_task033_fallback": [
                "fixed_p_high_order_equal_accuracy_efficiency",
                "p2_h_adaptive_feasibility",
                "hp_zoning_design_report_only",
            ],
        },
        "limitations": [
            "Absence of qualifying evidence is not a universal claim that future "
            "DOLFINx/Basix releases can never support variable p.",
            "A public symbol or callable signature does not prove H(curl) "
            "conformity, periodic synchronization, sparse ownership, or MPI safety.",
            "The repository environment record is configuration evidence, not a "
            "direct import or API-semantics test in this Python process.",
        ],
    }
    if formal_source is not None:
        record["formal_source"] = dict(formal_source)
    return record
