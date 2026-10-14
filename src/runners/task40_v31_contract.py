"""Pending-only V31 registration artifacts; no execution window is created here."""
from __future__ import annotations

import hashlib
import json
import argparse
from copy import deepcopy
from collections.abc import Mapping
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tomllib
from typing import Any

V31_CONTRACT_SCHEMA = "task40extra.review_v31_execution_contract.v1"
V31_REGISTRATION_SCHEMA = "task40extra.review_v31_campaign_registration.v1"
V31_SELECTOR_SCHEMA = "task40extra.review_v31_q_csr_selector_draft.v1"
V31_REVIEW_COMMIT = "d7ffbfea952bc160742b18739369f2e3f656ee8e"
V31_REVIEW_SHA256 = "d93625d435d4db47f2ae5ff2334558c17f4afec8523e63ee1cd2bc905eafe380"
V31_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v31.md"
V31_BRANCH = "task40extra_0p7nm_engineering"
V31_PROFILE = "task40extra_v20_p6_y_orbit_target_original_ny8_v1"
V31_PREPARATION_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation"
)
V31_ARTIFACT_ROOT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native"
)
V31_WORKSTATION_ROOT = "/home/fenics/Projects/laptop_share"
V31_TOTAL_SECONDS = 43_200
V31_NUMERIC_SECONDS = 42_000
V31_CLOSEOUT_SECONDS = 1_200
V31_STAGE_SCOPE = (
    "P0_contract_and_generic_entry",
    "P1_q4_saved_csr_and_native",
    "P2_q1_q7_csr_and_native",
    "P3_all_q_resident_factor_bank",
    "P4_complete_reference_inverse",
    "P5_conditional_original_size_target_pilot",
    "P6_checker_and_closeout",
)
V31_RESOURCES = {
    "task_memory_max_bytes": 1_649_267_441_664,
    "host_reserve_bytes": 68_719_476_736,
    "memory_swap_max_bytes": 0,
    "mpi_ranks": 1,
    "math_threads": 1,
    "petsc_scalar": "complex128",
    "petsc_int": "int32",
    "mumps_mode": "exact",
}
V31_Q_WORKLIST = [
    {"twist": 0, "q": 4, "action": "saved_contribution_then_own_csr_and_native"},
    {"twist": 1, "q": 1, "action": "shared_twist1_producer_then_own_csr_and_native"},
    {"twist": 1, "q": 5, "action": "reuse_twist1_producer_then_own_csr_and_native"},
    {"twist": 2, "q": 2, "action": "shared_twist2_producer_then_own_csr_and_native"},
    {"twist": 2, "q": 6, "action": "reuse_twist2_producer_then_own_csr_and_native"},
    {"twist": 3, "q": 3, "action": "shared_twist3_producer_then_own_csr_and_native"},
    {"twist": 3, "q": 7, "action": "reuse_twist3_producer_then_own_csr_and_native"},
]
V31_WORKER_BINDING_SCHEMA = "task40extra.review_v31_worker_execution_binding.v1"
V31_Q_CSR_BINDING_SCHEMA = "task40extra.review_v31_q_csr_worker_binding.v1"
V31_FACTOR_BANK_SCHEMA = "task40extra.review_v31_all_q_factor_bank.v1"
V31_APPROVAL_SCOPE = "V31_WINDOW_43200_NUMERIC_42000_CLOSEOUT_1200"
V31_USER_APPROVAL_EVIDENCE_SCHEMA = "task40extra.review_v31_user_approval_evidence.v1"
V32_REVIEW_COMMIT = "e2737b4049045a1824f5a1c49bb7bfac85e6e929"
V32_REVIEW_SHA256 = "1276514cbac4bcb7e91a2dae9312b434af3163d3d4e69964f3638d9fc6b00496"
V32_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v32.md"
V32_CONTRACT_SCHEMA = "task40extra.review_v32_execution_contract.v1"
V32_REGISTRATION_SCHEMA = "task40extra.review_v32_campaign_registration.v1"
V32_SELECTOR_SCHEMA = "task40extra.review_v32_q_csr_selector_draft.v1"
V32_PREPARATION_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation"
)
V32_TOTAL_SECONDS = 86_400
V32_NUMERIC_SECONDS = 85_200
V32_CLOSEOUT_SECONDS = 1_200
V32_Q4_PENDING_IMPORT_SCHEMA = "task40extra.review_v32_q4_numeric_pending_import.v1"
V32_Q4_PENDING_RECORD_RELATIVE = (
    V31_ARTIFACT_ROOT_RELATIVE
    / "source_54cf6d367b07355c0ab08c8c10655ecac73cfc6a"
    / "factor_bank" / "selected_q" / "q4_twist0"
    / "task40_v30_q4_twist0_numeric_pending.json"
)
V32_Q4_PENDING_RECORD_SHA256 = "1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad"
V32_Q4_ARRAY_SHA256 = {
    "data": "e0e209b7804956a8c998eac05422f6f6ff255ed857182e066eedfd509b005ad2",
    "indices": "3af86cbe15de1615304659e112deccb0d00c86c7cfe5d588cde846d84c3a7c97",
    "indptr": "0049c1ab9662e30b7cfe460f622557571172f8b5196174e64d4b4529ba2f334b",
}
V32_Q4_PRODUCER_EXECUTION_IDENTITY = {
    "source_sha": "54cf6d367b07355c0ab08c8c10655ecac73cfc6a",
    "window_sha256": "57133ebfe54c109ca77af4e529df94708c29c2b4c79d301b862b01ee70cf8f56",
}
V32_Q4_MATRIX_SOURCE_IDENTITY = {
    "source_sha": "9d0f4dbfc730dd620b709d048e33e9da6c77520c",
    "window_sha256": "a8ee7ab9970ece892d85f9313180438e88561f0bfc63b68acdb11f536400def7",
}
V32_STAGE_SCOPE = (
    "P0_import_owner_events_supervised_checker_and_freeze",
    "P1_old_q4_numeric_pending_import",
    "P2_q4_independent_native_qualification",
    "P3_three_new_real_sectors_and_native",
    "P4_eight_q_resident_factor_bank",
    "P5_complete_reference_qualification",
    "P6_conditional_original_size_target_pilot",
    "P7_supervised_checker_and_closeout",
)
V32_APPROVAL_SCOPE = "V32_WINDOW_86400_NUMERIC_85200_CLOSEOUT_1200"
V32_USER_APPROVAL_EVIDENCE_SCHEMA = "task40extra.review_v32_user_approval_evidence.v1"


def v31_source_artifact_relative(source_sha: str) -> Path:
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise V31ContractError("V31 source-qualified artifact root needs a lowercase full SHA")
    return V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_sha}"


def v32_q4_pending_import_template(
    *, execution_root: str | Path, consumer_source_sha: str
) -> dict[str, Any]:
    """Return the fixed, PENDING V32 q4 import identity; it creates no T0 or array read."""
    root = Path(execution_root).resolve()
    consumer_root = (
        root / v31_source_artifact_relative(consumer_source_sha)
        / "factor_bank" / "selected_q" / "q4_twist0"
    ).resolve()
    pending_path = (root / V32_Q4_PENDING_RECORD_RELATIVE).resolve()
    if consumer_root.is_relative_to(pending_path.parent):
        raise V31ContractError("V32 q4 consumer output root must be disjoint from the old read-only root")
    return {
        "schema": V32_Q4_PENDING_IMPORT_SCHEMA,
        "policy": "REQUIRE_EXISTING_NUMERIC_PENDING",
        "q_index": 4,
        "twist_index": 0,
        "pending_record_path": str(pending_path),
        "pending_record_sha256": V32_Q4_PENDING_RECORD_SHA256,
        "import_root": str(pending_path.parent),
        "csr_artifacts_sha256": dict(V32_Q4_ARRAY_SHA256),
        "producer_execution_identity": dict(V32_Q4_PRODUCER_EXECUTION_IDENTITY),
        "matrix_source_identity": dict(V32_Q4_MATRIX_SOURCE_IDENTITY),
        "consumer_output_root": str(consumer_root),
        "read_only": True,
    }


def bind_v32_q4_pending_import(
    template: Mapping[str, Any], *, consumer_execution_identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind the pending import template to the approved source/window without rewriting it."""
    if not isinstance(template, Mapping) or template.get("schema") != V32_Q4_PENDING_IMPORT_SCHEMA:
        raise V31ContractError("V32 q4 import template is missing or has another schema")
    from src.solvers.task40_v30_selected_q_csr import make_v32_q4_numeric_pending_import_authorization

    return make_v32_q4_numeric_pending_import_authorization(
        pending_record_path=str(template["pending_record_path"]),
        pending_record_sha256=str(template["pending_record_sha256"]),
        csr_artifacts_sha256=dict(template["csr_artifacts_sha256"]),
        producer_execution_identity=dict(template["producer_execution_identity"]),
        matrix_source_identity=dict(template["matrix_source_identity"]),
        consumer_execution_identity=dict(consumer_execution_identity),
        consumer_output_root=str(template["consumer_output_root"]),
    )


def require_v31_input_identity(
    canonical_input_path: str | Path,
    staged_input_path: str | Path,
    *,
    repo_root: str | Path,
    source_sha: str,
    selector_sha256: str,
    q4_numeric_pending_import: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Bind a V31-derived stage DAT to the canonical science and its source root."""
    from src.runners.task40_v30_contract import (
        V30_CANONICAL_INPUT_RELATIVE,
        V30_CANONICAL_INPUT_SHA256,
        sha256_file,
    )

    root = Path(repo_root).resolve()
    canonical = Path(canonical_input_path).resolve(strict=True)
    staged = Path(staged_input_path).resolve(strict=True)
    source_root = (root / v31_source_artifact_relative(source_sha)).resolve()
    if (
        not re.fullmatch(r"[0-9a-f]{40}", source_sha)
        or canonical.name != V30_CANONICAL_INPUT_RELATIVE.name
        or sha256_file(canonical) != V30_CANONICAL_INPUT_SHA256
        or staged != source_root / "stage_inputs" / "full" / canonical.name
        or not re.fullmatch(r"[0-9a-f]{64}", selector_sha256)
    ):
        raise V31ContractError("V31 canonical/staged input path or source identity changed")
    selector_relative = (
        v31_source_artifact_relative(source_sha) / "q_csr_selector_v31.json"
    ).as_posix()
    factor_relative = (v31_source_artifact_relative(source_sha) / "factor_bank").as_posix()
    canonical_data = tomllib.loads(canonical.read_text(encoding="utf-8"))
    staged_data = tomllib.loads(staged.read_text(encoding="utf-8"))
    expected = deepcopy(canonical_data)
    expected_execution = expected.get("execution")
    staged_execution = staged_data.get("execution")
    if not isinstance(expected_execution, dict) or not isinstance(staged_execution, dict):
        raise V31ContractError("V31 canonical/staged input omits its execution section")
    expected_execution["task40_execution_stop_stage"] = "full"
    actual = deepcopy(staged_data)
    expected = deepcopy(expected)
    actual_execution = actual["execution"]
    expected_execution = expected["execution"]
    expected_overrides = {
        "task40_target_heavy_authorized",
        "task40_v31_q_csr_binding",
        "task40_v31_factor_bank_config",
    }
    if q4_numeric_pending_import is not None:
        expected_overrides.add("task40_v31_q_csr_import_authorizations")
    if not expected_overrides <= set(actual_execution):
        raise V31ContractError("V31 staged DAT omits its complete target-operation binding")
    selector = actual_execution.get("task40_v31_q_csr_binding")
    factor = actual_execution.get("task40_v31_factor_bank_config")
    imports = actual_execution.get("task40_v31_q_csr_import_authorizations")
    if (
        actual_execution.get("task40_target_heavy_authorized") is not True
        or selector
        != {
            "schema": V31_Q_CSR_BINDING_SCHEMA,
            "selector_path": selector_relative,
            "selector_sha256": selector_sha256,
        }
        or factor
        != {
            "schema": V31_FACTOR_BANK_SCHEMA,
            "output_directory": factor_relative,
            "require_two_strict_rhs": True,
            "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
        }
        or (
            q4_numeric_pending_import is not None
            and imports != {"numeric_pending": {"4": dict(q4_numeric_pending_import)}}
        )
        or (
            q4_numeric_pending_import is None
            and "task40_v31_q_csr_import_authorizations" in actual_execution
        )
    ):
        raise V31ContractError("V31 staged DAT selector or factor bank differs from the execution contract")
    for key in expected_overrides:
        actual_execution.pop(key, None)
        expected_execution.pop(key, None)
    if actual != expected:
        raise V31ContractError("V31 stage DAT changes scientific or solver fields outside its registered route")
    return {
        "canonical_input_path": str(canonical),
        "canonical_input_sha256": V30_CANONICAL_INPUT_SHA256,
        "staged_input_path": str(staged),
        "staged_input_sha256": sha256_file(staged),
        "scientific_input_sha256": V30_CANONICAL_INPUT_SHA256,
        "source_sha": source_sha,
    }


def qualified_activation_identity(environment: dict[str, str]) -> str | None:
    """Return the reviewed imports-only native identity for V31 strict runs."""
    digest = environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256", "")
    if (
        environment.get("TASK40_V31_STRICT_EXECUTION") == "1"
        and environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") == "1"
        and environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") == "native_linux"
        and environment.get("_MYFENICS_CLOUD_QUALIFICATION_SCOPE")
        == "imports_only_C1_FE_JIT_NOT_RUN"
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        return f"native_linux_imports_only:{digest}"
    return None


class V31ContractError(ValueError):
    """A V31 registration or execution contract failed closed."""


def validate_v31_worker_execution_binding(
    binding: dict[str, Any],
    *,
    contract: dict[str, Any],
    contract_sha256: str,
    resolved_payload: dict[str, Any],
    source_sha: str,
    environment: dict[str, str],
    repo_root: str | Path,
) -> dict[str, Any]:
    """Validate the V31-only service-to-worker envelope before numerical imports.

    The selected-q implementation remains shared with the qualified V30 core,
    but its authorization, fixed window, selector binding, factor output root,
    and admission policy are independent V31 facts.
    """
    root = Path(repo_root).resolve()
    execution = contract.get("execution")
    window = execution.get("window") if isinstance(execution, dict) else None
    resources = execution.get("resources") if isinstance(execution, dict) else None
    preparation = contract.get("preparation")
    if not isinstance(binding, dict) or set(binding) != {
        "schema",
        "contract_path",
        "contract_sha256",
        "execution_window_path",
        "execution_window_sha256",
        "source_at_entry",
        "run_source_sha",
        "q_csr_selector_binding",
        "factor_bank_config",
        "accepted_q0_donor",
        "q_csr_worklist",
        "q_csr_import_authorizations",
        "target_admission_policy",
    }:
        raise V31ContractError("V31 worker binding has an open or incomplete schema")
    if (
        binding.get("schema") != V31_WORKER_BINDING_SCHEMA
        or environment.get("TASK40_V31_STRICT_EXECUTION") != "1"
        or environment.get("TASK40_V30_STRICT_EXECUTION") == "1"
        or binding.get("contract_sha256") != contract_sha256
        or not re.fullmatch(r"[0-9a-f]{64}", str(contract_sha256))
        or not isinstance(execution, dict)
        or not isinstance(window, dict)
        or not isinstance(resources, dict)
        or not isinstance(preparation, dict)
    ):
        raise V31ContractError("V31 worker binding is not backed by the separate V31 strict contract")

    contract_path = Path(str(binding["contract_path"])).resolve()
    review = contract.get("review")
    v32_route = (
        review == {"path": V32_REVIEW_PATH, "commit": V32_REVIEW_COMMIT, "sha256": V32_REVIEW_SHA256}
    )
    if not v32_route and review != {
        "path": V31_REVIEW_PATH,
        "commit": V31_REVIEW_COMMIT,
        "sha256": V31_REVIEW_SHA256,
    }:
        raise V31ContractError("V31 worker binding is not registered to Review V31 or V32")
    contract_filename = "execution_contract_v32.approved.json" if v32_route else "execution_contract_v31.approved.json"
    window_filename = "campaign_window_v32.json" if v32_route else "campaign_window_v31.json"
    contract_source_sha = str(contract.get("source_freeze", {}).get("source_sha", ""))
    source_root = root / v31_source_artifact_relative(contract_source_sha)
    expected_contract_path = (source_root / contract_filename).resolve()
    window_path = Path(str(window.get("window_path", ""))).resolve()
    window_source_sha = str(window.get("source_at_entry", ""))
    window_source_root = root / v31_source_artifact_relative(window_source_sha)
    expected_window_path = (window_source_root / window_filename).resolve()
    expected_resources = {
        "TASK40_V31_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK40_V31_EXECUTION_WINDOW_SHA256": str(window.get("window_sha256", "")),
        "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(resources.get("task_memory_max_bytes", "")),
        "TASK40_V31_HOST_RESERVE_BYTES": str(resources.get("host_reserve_bytes", "")),
        "TASK40_V31_MEMORY_SWAP_MAX_BYTES": str(resources.get("memory_swap_max_bytes", "")),
    }
    source_freeze = contract.get("source_freeze")
    if not isinstance(source_freeze, dict):
        raise V31ContractError("V31 worker contract omits its source freeze")
    if (
        contract_path != expected_contract_path
        or execution.get("root") != str(root)
        or window_path != expected_window_path
        or execution.get("campaign_window_path") != window.get("window_path")
        or execution.get("campaign_window_sha256") != window.get("window_sha256")
        or any(environment.get(key) != value for key, value in expected_resources.items())
        or binding.get("execution_window_path") != str(window_path)
        or binding.get("execution_window_sha256") != window.get("window_sha256")
        or binding.get("source_at_entry") != window.get("source_at_entry")
        or binding.get("run_source_sha") != execution.get("run_source_sha")
        or source_sha != contract_source_sha
        or source_sha != execution.get("run_source_sha")
        or execution.get("run_source_sha") != source_freeze.get("source_sha")
    ):
        raise V31ContractError("V31 worker window, source, or resource environment differs from its frozen contract")

    solver = resolved_payload.get("solver", {})
    payload_execution = resolved_payload.get("execution", {})
    provenance = resolved_payload.get("provenance", {})
    expected_input_path = Path(str(execution.get("input_path", "")))
    if not expected_input_path.is_absolute():
        expected_input_path = root / expected_input_path
    if (
        not isinstance(solver, dict)
        or not isinstance(payload_execution, dict)
        or not isinstance(provenance, dict)
        or solver.get("preconditioner") != V31_PROFILE
        or execution.get("profile") != V31_PROFILE
        or payload_execution.get("task40_execution_stop_stage") != "full"
        or payload_execution.get("task40_target_heavy_authorized") is not True
        or resolved_payload.get("run_id") != "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
        or Path(str(provenance.get("source_path", ""))).resolve()
        != expected_input_path.resolve()
        or provenance.get("input_sha256") != execution.get("input_sha256")
    ):
        raise V31ContractError("V31 worker binding is restricted to the exact reviewed Ny8 full-stage case")

    selector = binding.get("q_csr_selector_binding")
    if (
        not isinstance(selector, dict)
        or set(selector) != {"schema", "selector_path", "selector_sha256"}
        or selector.get("schema") != V31_Q_CSR_BINDING_SCHEMA
        or Path(str(selector.get("selector_path", ""))).resolve()
        != Path(str(execution.get("selector_path", ""))).resolve()
        or selector.get("selector_sha256") != execution.get("selector_sha256")
        or not re.fullmatch(r"[0-9a-f]{64}", str(selector.get("selector_sha256", "")))
    ):
        raise V31ContractError("V31 q-CSR selector binding differs from the approved contract")
    expected_factor_root = (source_root / "factor_bank").resolve()
    factor = binding.get("factor_bank_config")
    factor_path = Path(str(factor.get("output_directory", ""))).resolve() if isinstance(factor, dict) else None
    if (
        not isinstance(factor, dict)
        or set(factor)
        != {
            "schema",
            "output_directory",
            "require_two_strict_rhs",
            "second_rhs_formula",
        }
        or factor.get("schema") != V31_FACTOR_BANK_SCHEMA
        or factor_path != expected_factor_root
        or factor.get("require_two_strict_rhs") is not True
        or factor.get("second_rhs_formula")
        != "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13"
    ):
        raise V31ContractError("V31 AllQ factor-bank output is not bound to its native artifact root")

    donor = preparation.get("accepted_q0_donor")
    worklist = preparation.get("q_csr_worklist")
    if (
        not isinstance(donor, dict)
        or binding.get("accepted_q0_donor") != donor
        or not isinstance(worklist, list)
        or binding.get("q_csr_worklist") != worklist
        or [row.get("q") for row in worklist if isinstance(row, dict)]
        != [0, 4, 1, 5, 2, 6, 3, 7]
        or worklist[1].get("action") != "saved_contribution_then_own_csr_and_native"
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(donor.get("identity_sha256", ""))
        )
    ):
        raise V31ContractError("V31 q0 donor or saved-first q4 worklist differs from the approved contract")
    imports = binding.get("q_csr_import_authorizations")
    if not isinstance(imports, dict) or set(imports) - {"complete", "numeric_pending"}:
        raise V31ContractError("V31 q-CSR import authorizations have an open schema")
    for name in ("complete", "numeric_pending"):
        if name in imports and not isinstance(imports[name], dict):
            raise V31ContractError("V31 q-CSR import authorization section must be an object")
    if v32_route:
        template = preparation.get("q4_numeric_pending_import")
        contract_imports = execution.get("q_csr_import_authorizations")
        staged_imports = payload_execution.get("task40_v31_q_csr_import_authorizations")
        expected_template = v32_q4_pending_import_template(
            execution_root=root,
            consumer_source_sha=str(execution.get("run_source_sha", "")),
        )
        consumer_identity = {
            "source_sha": str(execution.get("run_source_sha", "")),
            "window_sha256": str(window.get("window_sha256", "")),
        }
        expected_authorization = bind_v32_q4_pending_import(
            expected_template,
            consumer_execution_identity=consumer_identity,
        )
        if (
            not isinstance(template, Mapping)
            or dict(template) != expected_template
            or imports != {"numeric_pending": {"4": expected_authorization}}
            or contract_imports != imports
            or staged_imports != {"numeric_pending": {"4": dict(template)}}
        ):
            raise V31ContractError("V32 worker import route differs from its contract, staged DAT, or fixed q4 source")
        from src.solvers.task40_v30_selected_q_csr import preflight_v32_q4_numeric_pending_import

        preflight_v32_q4_numeric_pending_import(
            expected_authorization,
            profile=V31_PROFILE,
            execution_identity=consumer_identity,
            output_directory=str(expected_template["consumer_output_root"]),
        )
    admission = binding.get("target_admission_policy")
    if (
        not isinstance(admission, dict)
        or admission.get("schema") != "task40extra.review_v31_target_admission.v1"
        or admission.get("phase") != "REFERENCE_ONLY"
        or set(admission) - {"schema", "phase", "target_owner_increment_inventory"}
    ):
        raise V31ContractError("V31 worker target admission policy is not the closed reference-only policy")
    return {
        "schema": V31_WORKER_BINDING_SCHEMA,
        "review_version": "V32" if v32_route else "V31",
        "contract_path": str(contract_path),
        "contract_sha256": contract_sha256,
        "execution_window_path": str(window_path),
        "execution_window_sha256": str(window["window_sha256"]),
        "source_at_entry": str(window["source_at_entry"]),
        "run_source_sha": str(execution["run_source_sha"]),
        "selector_path": str(Path(str(selector["selector_path"])).resolve()),
        "selector_sha256": str(selector["selector_sha256"]),
        "factor_bank_output_directory": str(factor_path),
        "q4_saved_first": True,
        "accepted_q0_donor_identity": dict(donor),
        "q_csr_worklist": [dict(row) for row in worklist],
        "q4_import_authorization_present": "4" in imports.get("numeric_pending", {}),
        "q4_numeric_pending_import_template": (
            dict(expected_template) if v32_route else None
        ),
        "q4_numeric_pending_import_authorization": (
            dict(imports["numeric_pending"]["4"]) if v32_route else None
        ),
        "target_admission_phase": str(admission["phase"]),
        "official_result": False,
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _write_once(path: Path, value: dict[str, Any]) -> str:
    encoded = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise FileExistsError(f"refusing to replace different V31 preparation artifact: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            import os

            os.fsync(stream.fileno())
    return hashlib.sha256(encoded).hexdigest()


def _write_bytes_once(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"refusing to replace different V31 preparation artifact: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            import os

            os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def _render_v31_stage_input(
    canonical_text: str,
    *,
    selector_relative_path: str,
    selector_sha256: str,
    factor_relative_path: str,
    q4_numeric_pending_import: Mapping[str, Any] | None = None,
) -> str:
    from scripts.task40_v20_service_workflow import render_stage_input

    rendered = render_stage_input(canonical_text, "full")
    if not re.fullmatch(r"[0-9a-f]{64}", selector_sha256):
        raise V31ContractError("V31 stage input needs a full selector SHA-256")
    route_lines_list = [
            "task40_target_heavy_authorized = true",
            "task40_v31_q_csr_binding = { "
            f"schema = {json.dumps(V31_Q_CSR_BINDING_SCHEMA)}, "
            f"selector_path = {json.dumps(selector_relative_path)}, "
            f"selector_sha256 = {json.dumps(selector_sha256)} "
            "}",
            "task40_v31_factor_bank_config = { "
            f"schema = {json.dumps(V31_FACTOR_BANK_SCHEMA)}, "
            f"output_directory = {json.dumps(factor_relative_path)}, "
            "require_two_strict_rhs = true, "
            "second_rhs_formula = \"real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13\" "
            "}",
    ]
    if q4_numeric_pending_import is not None:
        def toml_inline(value: Any) -> str:
            if isinstance(value, Mapping):
                return "{ " + ", ".join(
                    f"{json.dumps(str(key))} = {toml_inline(item)}"
                    for key, item in value.items()
                ) + " }"
            if isinstance(value, bool):
                return "true" if value else "false"
            if type(value) is int:
                return str(value)
            if isinstance(value, str):
                return json.dumps(value)
            raise V31ContractError("V32 q4 import DAT binding contains a non-TOML value")

        route_lines_list.append(
            "task40_v31_q_csr_import_authorizations = "
            + toml_inline({"numeric_pending": {"4": dict(q4_numeric_pending_import)}})
        )
    route_lines = "\n".join(route_lines_list)
    rendered, replaced = re.subn(
        r"(?m)^task40_target_heavy_authorized = false\s*$",
        route_lines,
        rendered,
        count=1,
    )
    if replaced != 1:
        raise V31ContractError("canonical V20 DAT lacks its single disabled target-authorization field")
    parsed = tomllib.loads(rendered)
    execution = parsed.get("execution")
    if (
        not isinstance(execution, dict)
        or execution.get("task40_execution_stop_stage") != "full"
        or execution.get("task40_target_heavy_authorized") is not True
        or execution.get("task40_v31_q_csr_binding", {}).get("selector_path")
        != selector_relative_path
        or (
            q4_numeric_pending_import is not None
            and execution.get("task40_v31_q_csr_import_authorizations")
            != {"numeric_pending": {"4": dict(q4_numeric_pending_import)}}
        )
    ):
        raise V31ContractError("rendered V31 stage input does not carry the exact full-stage route")
    return rendered


def prepare_v31_pending_package(
    *, repo_root: str | Path,
    output_directory: str | Path | None = None,
    execution_root: str | Path | None = None,
) -> dict[str, Any]:
    return _prepare_review_pending_package(
        repo_root=repo_root,
        output_directory=output_directory,
        execution_root=execution_root,
        review_version="V31",
    )


def prepare_v32_pending_package(
    *, repo_root: str | Path,
    output_directory: str | Path | None = None,
    execution_root: str | Path | None = None,
) -> dict[str, Any]:
    return _prepare_review_pending_package(
        repo_root=repo_root,
        output_directory=output_directory,
        execution_root=execution_root,
        review_version="V32",
    )


def _prepare_review_pending_package(
    *,
    repo_root: str | Path,
    output_directory: str | Path | None,
    execution_root: str | Path | None,
    review_version: str,
) -> dict[str, Any]:
    """Write immutable PENDING registration/selector/contract and source-bound commands.

    On the approved execution checkout only, reuse the canonical DAT bytes and the
    accepted q0 selector to create source-qualified route files. This never creates
    a campaign window/T0, starts a service, or authorizes numerical execution.
    """
    if review_version == "V31":
        review_path_text = V31_REVIEW_PATH
        review_commit = V31_REVIEW_COMMIT
        review_sha256 = V31_REVIEW_SHA256
        registration_schema = V31_REGISTRATION_SCHEMA
        contract_schema = V31_CONTRACT_SCHEMA
        selector_schema = V31_SELECTOR_SCHEMA
        preparation_relative = V31_PREPARATION_RELATIVE
        package_name = "v31_pending_package"
        registration_name = "campaign_registration_v31.pending.json"
        selector_name = "q_csr_selector_v31.pending.json"
        contract_name = "execution_contract_v31.pending.json"
        approved_contract_name = "execution_contract_v31.approved.json"
        approved_selector_name = "q_csr_selector_v31.approved.json"
        command_prefix = "v31"
        registration_scope = "V31_REVIEW_ALL_Q_REFERENCE_WITH_CONDITIONAL_TARGET_PILOT"
        total_seconds = V31_TOTAL_SECONDS
        numeric_seconds = V31_NUMERIC_SECONDS
        closeout_seconds = V31_CLOSEOUT_SECONDS
        stage_scope = V31_STAGE_SCOPE
        approval_scope = V31_APPROVAL_SCOPE
        q4_import_template = None
    elif review_version == "V32":
        review_path_text = V32_REVIEW_PATH
        review_commit = V32_REVIEW_COMMIT
        review_sha256 = V32_REVIEW_SHA256
        registration_schema = V32_REGISTRATION_SCHEMA
        contract_schema = V32_CONTRACT_SCHEMA
        selector_schema = V32_SELECTOR_SCHEMA
        preparation_relative = V32_PREPARATION_RELATIVE
        package_name = "v32_pending_package"
        registration_name = "campaign_registration_v32.pending.json"
        selector_name = "q_csr_selector_v32.pending.json"
        contract_name = "execution_contract_v32.pending.json"
        approved_contract_name = "execution_contract_v32.approved.json"
        approved_selector_name = "q_csr_selector_v32.approved.json"
        command_prefix = "v32"
        registration_scope = "V32_REVIEW_ALL_Q_REFERENCE_WITH_CONDITIONAL_TARGET_PILOT"
        total_seconds = V32_TOTAL_SECONDS
        numeric_seconds = V32_NUMERIC_SECONDS
        closeout_seconds = V32_CLOSEOUT_SECONDS
        stage_scope = V32_STAGE_SCOPE
        approval_scope = V32_APPROVAL_SCOPE
        q4_import_template = None
    else:
        raise V31ContractError("pending package review version must be exactly V31 or V32")

    root = Path(repo_root).resolve()
    target_root = Path(execution_root or V31_WORKSTATION_ROOT).resolve()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root, text=True
    )
    review_path = root / review_path_text
    if (
        branch != V31_BRANCH
        or subprocess.run(
            ["git", "merge-base", "--is-ancestor", review_commit, "HEAD"],
            cwd=root,
            check=False,
        ).returncode != 0
        or not review_path.is_file()
        or hashlib.sha256(review_path.read_bytes()).hexdigest() != review_sha256
    ):
        raise V31ContractError(
            f"{review_version} preparation requires the reviewed branch, review ancestor, and exact review bytes"
        )
    frozen_source = {
        "required": True,
        "source_sha": head if not status.strip() else None,
        "branch": branch,
        "clean": not bool(status.strip()),
    }
    output = (
        Path(output_directory).resolve()
        if output_directory is not None
        else (
            root
            / preparation_relative
            / package_name
            / f"source_{head}"
        ).resolve()
    )
    if not output.is_relative_to((root / preparation_relative).resolve()):
        raise V31ContractError(f"{review_version} PENDING package must remain under its local preparation root")

    registration = {
        "schema": registration_schema,
        "status": "PENDING_USER_APPROVAL",
        "review": {"path": review_path_text, "commit": review_commit, "sha256": review_sha256},
        "source_at_preparation": {
            **frozen_source,
            "head": head,
            "source_freeze_required_before_window": not frozen_source["clean"],
        },
        "window": {
            "total_seconds": total_seconds,
            "numeric_seconds": numeric_seconds,
            "closeout_seconds": closeout_seconds,
            "campaign_seconds": total_seconds,
            "numeric_cutoff_seconds": numeric_seconds,
            "closeout_reserve_seconds": closeout_seconds,
            "t0_utc": None,
            "numeric_cutoff_utc": None,
            "deadline_utc": None,
            "window_path": None,
            "window_sha256": None,
            "source_at_entry": None,
            "approval": None,
        },
        "scope": registration_scope,
        "stage_scope": list(stage_scope),
        "resources": dict(V31_RESOURCES),
        "forbidden_before_approval": [
            "FE", "JIT", "full_payload_scan", "pattern_fill_real_case", "native_real_case",
            "factor", "target_PDE", "SSH", "V30_restart", "T0_creation",
        ],
    }
    selector = {
        "schema": selector_schema,
        "status": "PENDING_SOURCE_FREEZE_AND_USER_APPROVAL",
        "review_sha256": review_sha256,
        "profile": V31_PROFILE,
        "q_worklist": V31_Q_WORKLIST,
        "q0_reuse": "reuse accepted q0 CSR/native evidence; create one fresh q0 factor in the live bank and charge it once",
        "live_factor_bank": "after all eight symbolic factorizations, create and retain one new q0 numeric factor; prior V29 q0 factor was destroyed",
        "source_sha": frozen_source["source_sha"],
        "campaign_window_sha256": None,
        "scientific_input_sha256": None,
    }
    from src.runners.task40_v30_contract import (
        V30_ABI_RECEIPT_RELATIVE,
        V30_ARTIFACT_ROOT_RELATIVE,
        V30_CANONICAL_INPUT_RELATIVE,
        V30_CANONICAL_INPUT_SHA256,
        V30_JIT_CACHE_RELATIVE,
        V30_Q0_DONOR,
        V30_RUNTIME_RELATIVE,
    )
    source_root_relative = v31_source_artifact_relative(head)
    if review_version == "V32":
        q4_import_template = v32_q4_pending_import_template(
            execution_root=target_root,
            consumer_source_sha=head,
        )
        selector["q4_numeric_pending_import"] = dict(q4_import_template)
    selector_relative = source_root_relative / "q_csr_selector_v31.json"
    staged_input = (
        source_root_relative / "stage_inputs" / "full" / V30_CANONICAL_INPUT_RELATIVE.name
    )
    factor_directory = source_root_relative / "factor_bank"
    selector_sha256: str | None = None
    staged_input_sha256: str | None = None
    reused_canonical_input = False
    if frozen_source["clean"] and target_root == root:
        canonical_path = root / V30_CANONICAL_INPUT_RELATIVE
        selector_donor_path = root / V30_ARTIFACT_ROOT_RELATIVE / "q0_selector_v30_partial.json"
        if not canonical_path.is_file() or not selector_donor_path.is_file():
            raise V31ContractError(
                "clean V31 preparation checkout is missing the canonical DAT or accepted V30 q0 selector"
            )
        canonical_bytes = canonical_path.read_bytes()
        if hashlib.sha256(canonical_bytes).hexdigest() != V30_CANONICAL_INPUT_SHA256:
            raise V31ContractError("canonical V20 DAT differs from the accepted scientific input identity")
        selector_bytes = selector_donor_path.read_bytes()
        selector_sha256 = _write_bytes_once(root / selector_relative, selector_bytes)
        staged_text = _render_v31_stage_input(
            canonical_bytes.decode("utf-8"),
            selector_relative_path=selector_relative.as_posix(),
            selector_sha256=selector_sha256,
            factor_relative_path=factor_directory.as_posix(),
            q4_numeric_pending_import=q4_import_template,
        )
        staged_input_sha256 = _write_bytes_once(
            root / staged_input,
            staged_text.encode("utf-8"),
        )
        identity = require_v31_input_identity(
            canonical_path,
            root / staged_input,
            repo_root=root,
            source_sha=head,
            selector_sha256=selector_sha256,
            q4_numeric_pending_import=q4_import_template,
        )
        selector.update(
            {
                "scientific_input_sha256": identity["scientific_input_sha256"],
                "selector_sha256": selector_sha256,
                "selector_path": selector_relative.as_posix(),
            }
        )
        reused_canonical_input = True
    contract = {
        "schema": contract_schema,
        "status": "PENDING_USER_APPROVAL",
        "registration_schema": registration_schema,
        "review": registration["review"],
        "source_freeze": frozen_source,
        "preparation": {
            "accepted_q0_donor": dict(V30_Q0_DONOR),
            "q_csr_worklist": [
                {"q": 0, "action": "reuse accepted CSR/native producer; build one fresh live-bank factor"},
                *[dict(row) for row in V31_Q_WORKLIST],
            ],
            "final_all_q_selector_required_at": "after_all_q_symbolic_before_any_numeric",
            "prior_v29_q0_factor": "DESTROYED; rebuild exactly once for the live bank and charge its actual cost",
            "new_window_registration_separate_from_historical_producer_identity": True,
            **(
                {"q4_numeric_pending_import": dict(q4_import_template)}
                if q4_import_template is not None
                else {}
            ),
        },
        "execution": {
            "root": str(target_root),
            "profile": V31_PROFILE,
            "resources": dict(V31_RESOURCES),
            "window": dict(registration["window"]),
            "campaign_window_path": None,
            "campaign_window_sha256": None,
            "run_source_sha": frozen_source["source_sha"],
            "runtime_prefix": str(V30_RUNTIME_RELATIVE),
            "abi_receipt_path": str(V30_ABI_RECEIPT_RELATIVE),
            "jit_cache": str(V30_JIT_CACHE_RELATIVE),
            "input_path": str(staged_input),
            "input_sha256": staged_input_sha256,
            "selector_path": str(selector_relative),
            "selector_sha256": selector_sha256,
            **(
                {"q_csr_import_authorizations": {"numeric_pending": {"4": dict(q4_import_template)}}}
                if q4_import_template is not None
                else {}
            ),
        },
        "user_approval": None,
        "service_start_allowed": False,
    }
    pending_contract_path = output / contract_name
    selector_path = output / selector_name
    registration_path = output / registration_name
    contract_sha = _write_once(pending_contract_path, contract)
    selector_sha = _write_once(selector_path, selector)
    registration["contract"] = {"path": str(pending_contract_path), "sha256": contract_sha}
    registration["selector"] = {"path": str(selector_path), "sha256": selector_sha}
    registration_sha = _write_once(registration_path, registration)
    from src.runners.task40_v30_contract import (
        V30_ABI_RECEIPT_RELATIVE,
        V30_JIT_CACHE_RELATIVE,
        V30_RUNTIME_RELATIVE,
    )
    target_root_text = shlex.quote(str(target_root))
    target_stage = f"{V31_ARTIFACT_ROOT_RELATIVE}/source_${{v31_source_sha}}"
    target_contract = f"{target_stage}/{approved_contract_name}"
    target_input = f"{target_stage}/stage_inputs/full/{V30_CANONICAL_INPUT_RELATIVE.name}"
    target_unit = f"myfenics-case-task40-{command_prefix}-all-q-reference-${{v31_source_sha:0:12}}"
    target_run = f"{target_stage}/service_runs/${{v31_unit}}"
    pending_directory = (
        preparation_relative / package_name / f"source_{head}"
    )
    activation = (
        "source scripts/task40_fresh_c1/activate_native_complex.sh "
        f"{V30_RUNTIME_RELATIVE} {V30_ABI_RECEIPT_RELATIVE} {V30_JIT_CACHE_RELATIVE} native_linux"
    )
    source_binding = (
        'v31_source_sha="$(git rev-parse HEAD)" && '
        f'v31_root="{V31_ARTIFACT_ROOT_RELATIVE}/source_${{v31_source_sha}}" && '
        f'v31_unit="{target_unit}"'
    )
    reuse_contract_variable = (
        "V32_EXISTING_APPROVED_CONTRACT"
        if review_version == "V32"
        else "V31_EXISTING_APPROVED_CONTRACT"
    )
    commands = {
        "prepare_p0": (
            f"cd {target_root_text} && {activation} && "
            f"python scripts/task40_v20_service_workflow.py prepare-{command_prefix}-p0 "
            f"--output-dir {pending_directory} "
            f"--execution-root {target_root_text}"
        ),
        "prepare_approved_package_after_explicit_user_approval": (
            f"cd {target_root_text} && {activation} && "
            f"python scripts/task40_v20_service_workflow.py prepare-{command_prefix}-approved "
            f'--pending-dir "{pending_directory}" '
            f'--approval-receipt "{pending_directory / "user_approval_v31.receipt.json"}"'
        ),
        "prepare_same_window_after_source_fix": (
            f"cd {target_root_text} && {activation} && "
            f"python scripts/task40_v20_service_workflow.py prepare-{command_prefix}-approved "
            f'--pending-dir "{pending_directory}" '
            f'--reuse-approved-contract "${reuse_contract_variable}"'
        ),
        "service_after_explicit_new_window_approval": (
            f"cd {target_root_text} && {source_binding} && "
            f"bash scripts/run_case_in_user_service.sh --service-unit \"$v31_unit\" "
            f"\"$v31_root/stage_inputs/full/{V30_CANONICAL_INPUT_RELATIVE.name}\" "
            f"--task40-v31-execution-contract \"$v31_root/{approved_contract_name}\""
        ),
        "official_checker_after_valid_output": (
            f"cd {target_root_text} && {activation} && {source_binding} && "
            f'v31_outer="{target_run}/outer_workflow_record.json" && '
            'v31_summary="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["run_summary_path"])\' "$v31_outer")" && '
            'v31_numerical_output="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["numerical_output_directory"])\' "$v31_summary")" && '
            'python -m src.runners.task40_v10_output_checker "$v31_numerical_output/v10_candidate_official_output.json" '
            "--expected-channel-count 32060"
        ),
        "partial_receipt_checker_after_controlled_stop": (
            f"cd {target_root_text} && {activation} && {source_binding} && "
            f'v31_outer="{target_run}/outer_workflow_record.json" && '
            'v31_summary="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["run_summary_path"])\' "$v31_outer")" && '
            'v31_manifest="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["run_manifest_path"])\' "$v31_outer")" && '
            'v31_run_directory="$(python -c \'import json,sys; print(json.load(open(sys.argv[1]))["run_directory"])\' "$v31_outer")" && '
            'v31_numerical_output="$(python -c \'import json,sys; from pathlib import Path; p=Path(json.load(open(sys.argv[1]))["numerical_output_directory"]); print((p if p.is_absolute() else Path(sys.argv[2])/p).resolve())\' "$v31_summary" "$v31_run_directory")" && '
            "python scripts/task40_v20_service_workflow.py check-partial "
            f'--input "$v31_root/stage_inputs/full/{V30_CANONICAL_INPUT_RELATIVE.name}" '
            '--summary "$v31_summary" --manifest "$v31_manifest" '
            '--numerical-output "$v31_numerical_output" --stop-stage full '
            f'--output "{target_run}/partial_checker_result.manual.json"'
        ),
    }
    if review_version == "V32":
        commands = {
            "prepare_p0": commands["prepare_p0"],
            "prepare_approved_package_after_explicit_user_approval": (
                f"cd {target_root_text} && {activation} && "
                "python scripts/task40_v20_service_workflow.py prepare-v32-approved "
                f'--pending-dir "{pending_directory}" '
                f'--approval-receipt "{pending_directory / "user_approval_v32.receipt.json"}"'
            ),
            "prepare_same_window_after_source_fix": commands[
                "prepare_same_window_after_source_fix"
            ],
            "single_supervised_service_after_approved_package": (
                f"cd {target_root_text} && {source_binding} && "
                f"bash scripts/run_case_in_user_service.sh --service-unit \"$v31_unit\" "
                f'"$v31_root/stage_inputs/full/{V30_CANONICAL_INPUT_RELATIVE.name}" '
                f'--task40-v32-execution-contract "$v31_root/{approved_contract_name}"'
            ),
        }
    return {
        "schema": f"task40extra.review_{review_version.lower()}_p0_command_registration.v1",
        "status": (
            "PENDING_USER_APPROVAL_NO_WINDOW_CREATED"
            if frozen_source["clean"]
            else "PENDING_SOURCE_FREEZE_AND_USER_APPROVAL_NO_WINDOW_CREATED"
        ),
        "registration": {"path": str(registration_path), "sha256": registration_sha},
        "selector": {"path": str(selector_path), "sha256": selector_sha},
        "contract": {"path": str(pending_contract_path), "sha256": contract_sha},
        "pending_directory": str(output),
        "commands": commands,
        **(
            {
                "service_handoff": (
                    "The approved single service command automatically writes the supervision request, "
                    "starts the qualified supervisor/watchdog and actual check-partial CLI, then waits "
                    "for the checker receipt and process-group cleanup. Do not treat a separately run "
                    "check-partial command as supervised completion."
                )
            }
            if review_version == "V32"
            else {}
        ),
        "created_payload_or_window": reused_canonical_input,
        "canonical_dat_bytes_reused": reused_canonical_input,
        "scientific_input_scanned": False,
        "window_created": False,
        "approval_scope": approval_scope,
    }


def prepare_v31_approved_package(
    *,
    repo_root: str | Path,
    pending_directory: str | Path,
    approval_receipt: str | Path | None = None,
    reuse_approved_contract: str | Path | None = None,
) -> dict[str, Any]:
    return _prepare_review_approved_package(
        repo_root=repo_root,
        pending_directory=pending_directory,
        approval_receipt=approval_receipt,
        reuse_approved_contract=reuse_approved_contract,
        review_version="V31",
    )


def prepare_v32_approved_package(
    *,
    repo_root: str | Path,
    pending_directory: str | Path,
    approval_receipt: str | Path | None = None,
    reuse_approved_contract: str | Path | None = None,
) -> dict[str, Any]:
    return _prepare_review_approved_package(
        repo_root=repo_root,
        pending_directory=pending_directory,
        approval_receipt=approval_receipt,
        reuse_approved_contract=reuse_approved_contract,
        review_version="V32",
    )


def _prepare_review_approved_package(
    *,
    repo_root: str | Path,
    pending_directory: str | Path,
    approval_receipt: str | Path | None,
    reuse_approved_contract: str | Path | None,
    review_version: str,
) -> dict[str, Any]:
    """Materialize one approved V31/V32 window, or rebind that live window.

    The initial path consumes a closed receipt made from the user's actual
    approval reply. Its single clock sample is T0 and is taken before pending
    inputs and source-qualified artifacts are prepared. The resume path preserves the old
    window file, digest, entry source, and T0 and never creates a replacement.
    """
    root = Path(repo_root).resolve()
    if review_version == "V31":
        review_path_text = V31_REVIEW_PATH
        review_commit = V31_REVIEW_COMMIT
        review_sha256 = V31_REVIEW_SHA256
        contract_schema = V31_CONTRACT_SCHEMA
        registration_schema = V31_REGISTRATION_SCHEMA
        approval_schema = V31_USER_APPROVAL_EVIDENCE_SCHEMA
        approval_scope = V31_APPROVAL_SCOPE
        total_seconds = V31_TOTAL_SECONDS
        numeric_seconds = V31_NUMERIC_SECONDS
        closeout_seconds = V31_CLOSEOUT_SECONDS
        stage_scope = V31_STAGE_SCOPE
        preparation_relative = V31_PREPARATION_RELATIVE
        package_name = "v31_pending_package"
        window_name = "campaign_window_v31.json"
        contract_name = "execution_contract_v31.approved.json"
        anchor_schema = "task40extra.review_v31_t0_anchor.v1"
        campaign_name = "task40extra_v31_all_q_reference_conditional_target_pilot"
    elif review_version == "V32":
        review_path_text = V32_REVIEW_PATH
        review_commit = V32_REVIEW_COMMIT
        review_sha256 = V32_REVIEW_SHA256
        contract_schema = V32_CONTRACT_SCHEMA
        registration_schema = V32_REGISTRATION_SCHEMA
        approval_schema = V32_USER_APPROVAL_EVIDENCE_SCHEMA
        approval_scope = V32_APPROVAL_SCOPE
        total_seconds = V32_TOTAL_SECONDS
        numeric_seconds = V32_NUMERIC_SECONDS
        closeout_seconds = V32_CLOSEOUT_SECONDS
        stage_scope = V32_STAGE_SCOPE
        preparation_relative = V32_PREPARATION_RELATIVE
        package_name = "v32_pending_package"
        window_name = "campaign_window_v32.json"
        contract_name = "execution_contract_v32.approved.json"
        anchor_schema = "task40extra.review_v32_t0_anchor.v1"
        campaign_name = "task40extra_v32_all_q_reference_conditional_target_pilot"
    else:
        raise V31ContractError("approved package review version must be exactly V31 or V32")
    resume_path = Path(reuse_approved_contract).resolve() if reuse_approved_contract else None
    approval_path = Path(approval_receipt).resolve() if approval_receipt else None
    if (resume_path is None) == (approval_path is None):
        raise V31ContractError(
            f"{review_version} preparation needs exactly one of a user approval receipt or an existing approved contract"
        )

    from src.runners.task40_v10_campaign import (
        CAMPAIGN_SCHEMA,
        CONSERVATIVE_REALTIME,
        _utc_ns,
        load_fixed_campaign_window,
    )
    window_created = False

    if resume_path is None:
        assert approval_path is not None
        try:
            receipt_bytes = approval_path.read_bytes()
            receipt = json.loads(receipt_bytes)
        except (OSError, json.JSONDecodeError) as error:
            raise V31ContractError(f"{review_version} user approval receipt is unreadable") from error
        if (
            not isinstance(receipt, dict)
            or set(receipt) != {
                "schema", "origin", "approved", "scope", "review_sha256",
                "source_sha", "execution_root", "user_message",
            }
            or receipt.get("schema") != approval_schema
            or receipt.get("origin") != "direct_user_message"
            or receipt.get("approved") is not True
            or receipt.get("scope") != approval_scope
            or receipt.get("review_sha256") != review_sha256
            or not isinstance(receipt.get("source_sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", receipt["source_sha"])
            or Path(str(receipt.get("execution_root", ""))).resolve() != root
            or not isinstance(receipt.get("user_message"), str)
            or not receipt["user_message"].strip()
            or not approval_path.is_relative_to(
                (root / preparation_relative / package_name).resolve()
            )
        ):
            raise V31ContractError(f"{review_version} approval receipt does not bind a direct user reply to this review/window")
        run_source_sha = str(receipt["source_sha"])
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=root, text=True
        ).strip()
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            text=True,
        )
        review_path = root / review_path_text
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", review_commit, "HEAD"],
            cwd=root,
            check=False,
        )
        if (
            branch != V31_BRANCH
            or head != run_source_sha
            or status.strip()
            or not review_path.is_file()
            or hashlib.sha256(review_path.read_bytes()).hexdigest() != review_sha256
            or ancestry.returncode != 0
        ):
            raise V31ContractError(f"{review_version} approval receipt requires the exact clean reviewed source")
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        window_path = root / v31_source_artifact_relative(run_source_sha) / window_name
        anchor_path = (
            root
            / preparation_relative
            / "t0_anchors"
            / f"source_{run_source_sha}.json"
        )
        status = "USER_APPROVED_WINDOW_READY"
        if window_path.is_file():
            try:
                window_payload = json.loads(window_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise V31ContractError(f"existing {review_version} preparation window is unreadable; do not refresh it") from error
            t0_utc = window_payload.get("t0_utc")
            cutoff_utc = window_payload.get("numeric_cutoff_utc")
            deadline_utc = window_payload.get("deadline_utc")
            first_sample = window_payload.get("first_full_three_clock_sample")
            if not anchor_path.is_file():
                raise V31ContractError(f"existing {review_version} window has no persisted approval/T0 anchor; do not refresh it")
            try:
                anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise V31ContractError(f"existing {review_version} approval/T0 anchor is unreadable") from error
            if (
                anchor.get("schema") != anchor_schema
                or anchor.get("source_sha") != run_source_sha
                or anchor.get("approval_receipt_sha256") != receipt_sha256
                or anchor.get("first_full_three_clock_sample") != first_sample
                or window_payload.get("schema") != CAMPAIGN_SCHEMA
                or window_payload.get("campaign") != campaign_name
                or window_payload.get("active_review_sha256") != review_sha256
                or window_payload.get("source_at_entry") != run_source_sha
                or window_payload.get("user_approval_receipt_sha256") != receipt_sha256
                or window_payload.get("campaign_seconds") != total_seconds
                or window_payload.get("numeric_cutoff_seconds") != float(numeric_seconds)
                or window_payload.get("closeout_reserve_seconds") != closeout_seconds
                or not isinstance(first_sample, dict)
                or not isinstance(t0_utc, str)
                or not isinstance(cutoff_utc, str)
                or not isinstance(deadline_utc, str)
                or _utc_ns(cutoff_utc) - _utc_ns(t0_utc)
                != numeric_seconds * 1_000_000_000
                or _utc_ns(deadline_utc) - _utc_ns(t0_utc)
                != total_seconds * 1_000_000_000
            ):
                raise V31ContractError(f"existing {review_version} T0/approval anchor differs; never refresh it")
            window_sha256 = hashlib.sha256(window_path.read_bytes()).hexdigest()
            status = "USER_APPROVED_WINDOW_RESUMED_PREPARATION"
        else:
            if anchor_path.is_file():
                try:
                    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise V31ContractError(f"existing {review_version} approval/T0 anchor is unreadable; do not refresh it") from error
                first_sample = anchor.get("first_full_three_clock_sample")
                if (
                    anchor.get("schema") != anchor_schema
                    or anchor.get("source_sha") != run_source_sha
                    or anchor.get("approval_receipt_sha256") != receipt_sha256
                    or not isinstance(first_sample, dict)
                    or type(first_sample.get("utc_ns")) is not int
                    or not isinstance(first_sample.get("monotonic"), (int, float))
                    or not isinstance(first_sample.get("boottime"), (int, float))
                    or not isinstance(first_sample.get("boot_id"), str)
                ):
                    raise V31ContractError(f"existing {review_version} approval/T0 anchor differs; never refresh it")
                status = "USER_APPROVED_WINDOW_RESUMED_PREPARATION"
            else:
                from src.runners.workflow_timebase import clock_sample

                first_sample = clock_sample(include_boot_id=True)
                if (
                    type(first_sample.get("utc_ns")) is not int
                    or not isinstance(first_sample.get("monotonic"), (int, float))
                    or not isinstance(first_sample.get("boottime"), (int, float))
                    or not isinstance(first_sample.get("boot_id"), str)
                    or not re.fullmatch(r"[0-9a-fA-F-]{36}", first_sample["boot_id"])
                ):
                    raise V31ContractError(f"{review_version} T0 requires one complete UTC/monotonic/boottime/boot-id sample")
                _write_once(
                    anchor_path,
                    {
                        "schema": anchor_schema,
                        "source_sha": run_source_sha,
                        "approval_receipt_path": str(approval_path),
                        "approval_receipt_sha256": receipt_sha256,
                        "first_full_three_clock_sample": dict(first_sample),
                    },
                )
            t0_ns = int(first_sample["utc_ns"])

            def utc_text(value_ns: int) -> str:
                from datetime import datetime, timezone

                seconds, nanos = divmod(value_ns, 1_000_000_000)
                stamp = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                return f"{stamp}.{nanos:09d}Z"

            t0_utc = utc_text(t0_ns)
            cutoff_utc = utc_text(t0_ns + numeric_seconds * 1_000_000_000)
            deadline_utc = utc_text(t0_ns + total_seconds * 1_000_000_000)
            window_payload = {
                "schema": CAMPAIGN_SCHEMA,
                "campaign": campaign_name,
                "authority": f"User-approved Review {review_version} execution window",
                "active_review_sha": review_commit,
                "active_review_path": review_path_text,
                "active_review_sha256": review_sha256,
                "source_at_entry": run_source_sha,
                "review_at_registration": review_commit,
                "t0_utc": t0_utc,
                "numeric_cutoff_utc": cutoff_utc,
                "deadline_utc": deadline_utc,
                "campaign_seconds": total_seconds,
                "numeric_cutoff_seconds": float(numeric_seconds),
                "closeout_reserve_seconds": closeout_seconds,
                "time_policy": CONSERVATIVE_REALTIME,
                "stage_scope": list(stage_scope),
                "forbidden_scope": [
                    "automatic_cap_increase", "window_refresh", "parameter_or_accuracy_scan",
                    "MUMPS_or_ABI_change", "OOC_or_BLR", "unrelated_project_mutation", "master_merge",
                ],
                "window_refreshed": False,
                "old_costs_and_unknowns_preserved": True,
                "artifact_execution_identity_separate": True,
                "bootstrap_boottime_elapsed_seconds": None,
                "first_full_three_clock_sample": dict(first_sample),
                "initial_boot_id": str(first_sample["boot_id"]),
                "bootstrap_utc_elapsed_seconds": (
                    int(first_sample["utc_ns"]) - _utc_ns(t0_utc)
                ) / 1e9,
                "bootstrap_time_treatment": (
                    f"T0 and the first full three-clock sample are recorded before {review_version} artifact preparation; "
                    "UTC elapsed is charged; UNKNOWN is retained; null is not zero; Never refresh T0."
                ),
                "user_approval_receipt_sha256": receipt_sha256,
            }
            window_sha256 = _write_once(window_path, window_payload)
            window_created = True
            if status != "USER_APPROVED_WINDOW_RESUMED_PREPARATION":
                status = "USER_APPROVED_WINDOW_READY"
        window = {
            "window_path": str(window_path.resolve()),
            "window_sha256": window_sha256,
            "source_at_entry": run_source_sha,
            "total_seconds": total_seconds,
            "numeric_seconds": numeric_seconds,
            "closeout_seconds": closeout_seconds,
            "closeout_reserve_seconds": closeout_seconds,
            "t0_utc": t0_utc,
            "numeric_cutoff_utc": cutoff_utc,
            "deadline_utc": deadline_utc,
        }
        approval_record = {
            "approved": True,
            "scope": approval_scope,
            "window_sha256": window_sha256,
            "evidence": {
                **receipt,
                "receipt_path": str(approval_path),
                "receipt_sha256": receipt_sha256,
            },
        }
    else:
        prior_contract, _prior_sha = require_v31_execution_contract(resume_path)
        prior_execution = prior_contract["execution"]
        if Path(str(prior_execution.get("root", ""))).resolve() != root:
            raise V31ContractError(f"{review_version} same-window resume contract belongs to a different execution root")
        window = deepcopy(prior_execution["window"])
        window_path = Path(str(window["window_path"])).resolve(strict=True)
        window_sha256 = str(window["window_sha256"])
        if hashlib.sha256(window_path.read_bytes()).hexdigest() != window_sha256:
            raise V31ContractError(f"{review_version} same-window resume changed the original window bytes")
        load_fixed_campaign_window(
            window_path,
            require_current_boot=True,
            v31_contract=prior_contract,
        )
        approval_record = deepcopy(prior_contract["user_approval"])
        status = "USER_APPROVED_SAME_WINDOW_RESUME_READY"

    pending_builder = prepare_v31_pending_package if review_version == "V31" else prepare_v32_pending_package
    pending = pending_builder(
        repo_root=root,
        output_directory=pending_directory,
        execution_root=root,
    )
    if pending.get("canonical_dat_bytes_reused") is not True:
        raise V31ContractError(f"{review_version} approved preparation requires the clean source-qualified DAT and selector")
    pending_contract_path = Path(str(pending["contract"]["path"])).resolve(strict=True)
    pending_selector_path = Path(str(pending["selector"]["path"])).resolve(strict=True)
    pending_registration_path = Path(str(pending["registration"]["path"])).resolve(strict=True)
    pending_contract = json.loads(pending_contract_path.read_text(encoding="utf-8"))
    pending_selector = json.loads(pending_selector_path.read_text(encoding="utf-8"))
    pending_registration = json.loads(pending_registration_path.read_text(encoding="utf-8"))
    source_freeze = pending_contract.get("source_freeze")
    execution = pending_contract.get("execution")
    if (
        not isinstance(source_freeze, dict)
        or source_freeze.get("clean") is not True
        or source_freeze.get("branch") != V31_BRANCH
        or not isinstance(source_freeze.get("source_sha"), str)
        or not isinstance(execution, dict)
        or Path(str(execution.get("root", ""))).resolve() != root
    ):
        raise V31ContractError(f"{review_version} approved preparation lacks a clean, source-bound pending package")
    run_source_sha = str(source_freeze["source_sha"])
    current_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    current_status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        text=True,
    )
    if current_head != run_source_sha or current_status.strip():
        raise V31ContractError(f"{review_version} approved preparation requires the same clean source after artifact preparation")

    from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

    input_path = Path(str(execution["input_path"]))
    input_path = (input_path if input_path.is_absolute() else root / input_path).resolve(strict=True)
    selector_path = Path(str(execution["selector_path"]))
    selector_path = (selector_path if selector_path.is_absolute() else root / selector_path).resolve(strict=True)
    input_identity = require_v31_input_identity(
        root / V30_CANONICAL_INPUT_RELATIVE,
        input_path,
        repo_root=root,
        source_sha=run_source_sha,
        selector_sha256=str(execution.get("selector_sha256", "")),
        q4_numeric_pending_import=(
            pending_contract.get("preparation", {}).get("q4_numeric_pending_import")
            if review_version == "V32"
            else None
        ),
    )
    if (
        hashlib.sha256(selector_path.read_bytes()).hexdigest() != execution.get("selector_sha256")
        or input_identity["staged_input_sha256"] != execution.get("input_sha256")
    ):
        raise V31ContractError(f"{review_version} prepared selector or derived DAT differs from the pending source identity")
    if (
        not isinstance(window, dict)
        or not isinstance(approval_record, dict)
        or Path(str(window.get("window_path", ""))).resolve() != window_path.resolve()
        or window.get("window_sha256") != window_sha256
        or approval_record.get("window_sha256") != window_sha256
    ):
        raise V31ContractError(f"{review_version} approved preparation did not retain one bound window and approval receipt")

    contract = deepcopy(pending_contract)
    contract["status"] = "USER_APPROVED"
    contract["service_start_allowed"] = True
    contract["user_approval"] = approval_record
    contract["execution"]["window"] = window
    contract["execution"]["campaign_window_path"] = window["window_path"]
    contract["execution"]["campaign_window_sha256"] = window_sha256
    contract["execution"]["run_source_sha"] = run_source_sha
    if review_version == "V32":
        q4_template = v32_q4_pending_import_template(
            execution_root=root,
            consumer_source_sha=run_source_sha,
        )
        contract["preparation"]["q4_numeric_pending_import"] = dict(q4_template)
        contract["execution"]["q_csr_import_authorizations"] = {
            "numeric_pending": {
                "4": bind_v32_q4_pending_import(
                    q4_template,
                    consumer_execution_identity={
                        "source_sha": run_source_sha,
                        "window_sha256": window_sha256,
                    },
                )
            }
        }
    contract_path = root / v31_source_artifact_relative(run_source_sha) / contract_name
    contract_sha256 = _write_once(contract_path, contract)

    selector_descriptor = deepcopy(pending_selector)
    selector_descriptor.update(
        {
            "status": "USER_APPROVED",
            "campaign_window_sha256": window_sha256,
            "scientific_input_sha256": input_identity["scientific_input_sha256"],
            "selector_path": execution["selector_path"],
            "selector_sha256": execution["selector_sha256"],
            "approved_contract_path": str(contract_path.resolve()),
            "approved_contract_sha256": contract_sha256,
        }
    )
    approved_selector_path = Path(pending["pending_directory"]) / f"q_csr_selector_{review_version.lower()}.approved.json"
    approved_selector_sha = _write_once(approved_selector_path, selector_descriptor)
    registration = deepcopy(pending_registration)
    registration["status"] = status
    registration["window"] = dict(window)
    registration["user_approval"] = approval_record
    registration["contract"] = {"path": str(contract_path.resolve()), "sha256": contract_sha256}
    registration["selector"] = {
        "path": str(approved_selector_path.resolve()),
        "sha256": approved_selector_sha,
    }
    approved_registration_path = Path(pending["pending_directory"]) / f"campaign_registration_{review_version.lower()}.approved.json"
    approved_registration_sha = _write_once(approved_registration_path, registration)
    return {
        "schema": f"task40extra.review_{review_version.lower()}_approved_package.v1",
        "status": status,
        "run_source_sha": run_source_sha,
        "source_at_entry": window["source_at_entry"],
        "contract": {"path": str(contract_path.resolve()), "sha256": contract_sha256},
        "window": {"path": str(window_path.resolve()), "sha256": window_sha256},
        "selector": {"path": str(approved_selector_path.resolve()), "sha256": approved_selector_sha},
        "staged_input": {
            "path": str(input_path.resolve()),
            "sha256": str(execution["input_sha256"]),
            "scientific_input_sha256": input_identity["scientific_input_sha256"],
        },
        "registration": {
            "path": str(approved_registration_path.resolve()),
            "sha256": approved_registration_sha,
        },
        "commands": dict(pending["commands"]),
        "new_window_created": window_created,
        "t0_refreshed": False,
    }


def require_v31_execution_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    contract_path = Path(path).resolve(strict=True)
    digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise V31ContractError("V31 execution contract SHA differs from the launcher registration")
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V31ContractError("V31 execution contract is unreadable") from error
    if not isinstance(payload, dict):
        raise V31ContractError("Task40 execution contract is not an object")
    review = payload.get("review")
    if review == {"path": V31_REVIEW_PATH, "commit": V31_REVIEW_COMMIT, "sha256": V31_REVIEW_SHA256}:
        review_version = "V31"
        expected_schema = V31_CONTRACT_SCHEMA
        expected_registration_schema = V31_REGISTRATION_SCHEMA
        total_seconds = V31_TOTAL_SECONDS
        numeric_seconds = V31_NUMERIC_SECONDS
        closeout_seconds = V31_CLOSEOUT_SECONDS
        approval_scope = V31_APPROVAL_SCOPE
        contract_filename = "execution_contract_v31.approved.json"
        window_filename = "campaign_window_v31.json"
    elif review == {"path": V32_REVIEW_PATH, "commit": V32_REVIEW_COMMIT, "sha256": V32_REVIEW_SHA256}:
        review_version = "V32"
        expected_schema = V32_CONTRACT_SCHEMA
        expected_registration_schema = V32_REGISTRATION_SCHEMA
        total_seconds = V32_TOTAL_SECONDS
        numeric_seconds = V32_NUMERIC_SECONDS
        closeout_seconds = V32_CLOSEOUT_SECONDS
        approval_scope = V32_APPROVAL_SCOPE
        contract_filename = "execution_contract_v32.approved.json"
        window_filename = "campaign_window_v32.json"
    else:
        raise V31ContractError("Task40 execution contract review identity is not registered")
    if payload.get("schema") != expected_schema:
        raise V31ContractError(f"{review_version} execution contract schema is not registered")
    if payload.get("status") == "PENDING_USER_APPROVAL" or payload.get("service_start_allowed") is False:
        raise V31ContractError("V31 execution contract is PENDING; no service or campaign window is authorized")
    source = payload.get("source_freeze")
    execution = payload.get("execution")
    window = execution.get("window") if isinstance(execution, dict) else None
    approval = payload.get("user_approval")
    if (
        payload.get("status") != "USER_APPROVED"
        or payload.get("service_start_allowed") is not True
        or payload.get("registration_schema") != expected_registration_schema
        or not isinstance(source, dict)
        or set(source) != {"required", "source_sha", "branch", "clean"}
        or source.get("required") is not True
        or source.get("branch") != V31_BRANCH
        or source.get("clean") is not True
        or not isinstance(source.get("source_sha"), str)
        or len(source["source_sha"]) != 40
        or not isinstance(execution, dict)
        or execution.get("profile") != V31_PROFILE
        or not isinstance(window, dict)
        or window.get("total_seconds") != total_seconds
        or window.get("numeric_seconds") != numeric_seconds
        or window.get("closeout_seconds") != closeout_seconds
        or not isinstance(window.get("window_path"), str)
        or not isinstance(window.get("window_sha256"), str)
        or len(window["window_sha256"]) != 64
        or not isinstance(window.get("source_at_entry"), str)
        or len(window["source_at_entry"]) != 40
        or not isinstance(window.get("t0_utc"), str)
        or not isinstance(window.get("numeric_cutoff_utc"), str)
        or not isinstance(window.get("deadline_utc"), str)
        or not isinstance(approval, dict)
        or approval.get("approved") is not True
        or approval.get("scope") != approval_scope
        or approval.get("window_sha256") != window.get("window_sha256")
        or not isinstance(execution.get("resources"), dict)
        or execution["resources"] != V31_RESOURCES
        or execution.get("campaign_window_path") != window.get("window_path")
        or execution.get("campaign_window_sha256") != window.get("window_sha256")
        or execution.get("run_source_sha") != source.get("source_sha")
        or any(not isinstance(execution.get(key), str) or not execution[key] for key in (
            "root", "runtime_prefix", "abi_receipt_path", "jit_cache", "input_path", "selector_path"
        ))
        or any(len(str(execution.get(key, ""))) != 64 for key in (
            "input_sha256", "selector_sha256"
        ))
    ):
        raise V31ContractError(f"{review_version} execution contract is incomplete or differs from the approved review")
    source_sha = str(source["source_sha"])
    execution_root = Path(str(execution["root"])).resolve()
    source_root = (execution_root / v31_source_artifact_relative(source_sha)).resolve()
    expected_contract_path = (source_root / contract_filename).resolve()
    window_source_sha = str(window.get("source_at_entry", ""))
    expected_window_path = (
        execution_root / v31_source_artifact_relative(window_source_sha) / window_filename
    ).resolve()
    raw_input_path = Path(str(execution["input_path"]))
    raw_selector_path = Path(str(execution["selector_path"]))
    input_path = (raw_input_path if raw_input_path.is_absolute() else execution_root / raw_input_path).resolve()
    selector_path = (raw_selector_path if raw_selector_path.is_absolute() else execution_root / raw_selector_path).resolve()
    if (
        contract_path != expected_contract_path
        or Path(window["window_path"]).resolve() != expected_window_path
        or Path(str(execution["campaign_window_path"])).resolve() != expected_window_path
        or input_path != (source_root / "stage_inputs" / "full" / input_path.name).resolve()
        or selector_path != (source_root / "q_csr_selector_v31.json").resolve()
    ):
        raise V31ContractError(f"{review_version} contract/input/selector and original-entry window paths differ from their source bindings")
    window_path = Path(window["window_path"]).resolve(strict=True)
    if hashlib.sha256(window_path.read_bytes()).hexdigest() != window["window_sha256"]:
        raise V31ContractError(f"{review_version} fixed campaign window is missing or changed")
    if review_version == "V32":
        preparation = payload.get("preparation")
        template = preparation.get("q4_numeric_pending_import") if isinstance(preparation, dict) else None
        execution_imports = execution.get("q_csr_import_authorizations")
        if not isinstance(template, Mapping):
            raise V31ContractError("V32 approved contract omits the exact q4 pending import template")
        expected_template = v32_q4_pending_import_template(
            execution_root=execution_root,
            consumer_source_sha=source_sha,
        )
        consumer_identity = {
            "source_sha": source_sha,
            "window_sha256": str(window["window_sha256"]),
        }
        expected_authorization = bind_v32_q4_pending_import(
            expected_template,
            consumer_execution_identity=consumer_identity,
        )
        if (
            dict(template) != expected_template
            or not isinstance(execution_imports, Mapping)
            or dict(execution_imports) != {"numeric_pending": {"4": expected_authorization}}
        ):
            raise V31ContractError("V32 q4 import contract differs from its fixed pending/source/window identity")
        from src.solvers.task40_v30_selected_q_csr import preflight_v32_q4_numeric_pending_import

        preflight_v32_q4_numeric_pending_import(
            expected_authorization,
            profile=V31_PROFILE,
            execution_identity=consumer_identity,
            output_directory=str(expected_template["consumer_output_root"]),
        )
    if current_root is not None:
        root = Path(current_root).resolve()
        if Path(str(execution.get("root", ""))).resolve() != root:
            raise V31ContractError("V31 execution root differs from the contract")
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=root, text=True
            ).strip()
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            status = subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=root,
                text=True,
            )
            review_path = root / (V32_REVIEW_PATH if review_version == "V32" else V31_REVIEW_PATH)
            review_sha = hashlib.sha256(review_path.read_bytes()).hexdigest()
            ancestry = subprocess.run(
                [
                    "git", "merge-base", "--is-ancestor",
                    V32_REVIEW_COMMIT if review_version == "V32" else V31_REVIEW_COMMIT,
                    "HEAD",
                ],
                cwd=root,
                check=False,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise V31ContractError("V31 live source identity could not be verified") from error
        if (
            branch != V31_BRANCH
            or head != source["source_sha"]
            or status.strip()
            or review_sha != (V32_REVIEW_SHA256 if review_version == "V32" else V31_REVIEW_SHA256)
            or ancestry.returncode != 0
        ):
            raise V31ContractError(f"{review_version} execution requires the exact clean frozen source and review")
        source_root = root / v31_source_artifact_relative(str(source.get("source_sha", "")))
        window_source_root = root / v31_source_artifact_relative(str(window.get("source_at_entry", "")))
        expected_window_path = (window_source_root / window_filename).resolve()
        if window_path != expected_window_path:
            raise V31ContractError(f"{review_version} fixed window path differs from the source-qualified native artifact path")
        for path_key, sha_key in (("input_path", "input_sha256"), ("selector_path", "selector_sha256")):
            identity_path = Path(execution[path_key])
            if not identity_path.is_absolute():
                identity_path = root / identity_path
            try:
                identity_sha = hashlib.sha256(identity_path.resolve(strict=True).read_bytes()).hexdigest()
            except OSError as error:
                raise V31ContractError(f"V31 {path_key} is missing") from error
            if identity_sha != execution[sha_key]:
                raise V31ContractError(f"{review_version} {path_key} identity differs from the approved contract")
            if not identity_path.resolve().is_relative_to(source_root.resolve()):
                raise V31ContractError(f"{review_version} {path_key} is outside the source-qualified native artifact root")
        if review_version == "V32":
            from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

            template = payload["preparation"]["q4_numeric_pending_import"]
            input_identity = require_v31_input_identity(
                root / V30_CANONICAL_INPUT_RELATIVE,
                input_path,
                repo_root=root,
                source_sha=source_sha,
                selector_sha256=str(execution["selector_sha256"]),
                q4_numeric_pending_import=template,
            )
            if input_identity["staged_input_sha256"] != execution["input_sha256"]:
                raise V31ContractError("V32 staged DAT import template differs from the approved contract")
    return payload, digest


def v31_launcher_values(
    contract_path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
) -> tuple[str, ...]:
    """Return the fixed native launcher binding after strict contract validation."""
    contract, contract_sha = require_v31_execution_contract(
        contract_path,
        expected_sha256=expected_sha256,
        current_root=current_root,
    )
    execution = contract["execution"]
    root = Path(str(execution["root"])).resolve()
    if current_root is not None and root != Path(current_root).resolve():
        raise V31ContractError("V31 launcher root differs from the current checkout")
    if dict(execution.get("resources", {})) != V31_RESOURCES:
        raise V31ContractError("V31 launcher resources differ from the approved contract")

    from src.runners.task40_v30_contract import (
        V30_ABI_RECEIPT_RELATIVE,
        V30_JIT_CACHE_RELATIVE,
        V30_RUNTIME_RELATIVE,
    )

    def resolve_registered_path(key: str, expected_relative: Path) -> str:
        raw = Path(str(execution.get(key, "")))
        resolved = (raw if raw.is_absolute() else root / raw).resolve()
        expected = (root / expected_relative).resolve()
        if resolved != expected or not resolved.is_relative_to(root):
            raise V31ContractError(f"V31 {key} differs from its fixed native runtime path")
        return str(resolved)

    window = execution["window"]
    window_path = Path(str(window["window_path"])).resolve()
    if (
        execution.get("campaign_window_path") != str(window_path)
        or execution.get("campaign_window_sha256") != window.get("window_sha256")
    ):
        raise V31ContractError("V31 launcher window alias differs from its approved window")
    resources = execution["resources"]
    return (
        str(root),
        resolve_registered_path("runtime_prefix", V30_RUNTIME_RELATIVE),
        resolve_registered_path("abi_receipt_path", V30_ABI_RECEIPT_RELATIVE),
        resolve_registered_path("jit_cache", V30_JIT_CACHE_RELATIVE),
        str(resources["task_memory_max_bytes"]),
        contract_sha,
        str(window_path),
        str(window["window_sha256"]),
        str(resources["host_reserve_bytes"]),
        str(resources["memory_swap_max_bytes"]),
    )


def require_v31_all_q_route(
    resolved_payload: dict[str, Any],
    *,
    source_sha: str,
    repo_root: str | Path,
    environment: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Authorize the V31-only V19-request to AllQ worker normalization."""
    execution_payload = resolved_payload.get("execution", {})
    if not isinstance(execution_payload, dict):
        return None
    has_selector = "task40_v31_q_csr_binding" in execution_payload
    has_factor = "task40_v31_factor_bank_config" in execution_payload
    if not has_selector and not has_factor:
        return None
    if (
        not has_selector
        or not has_factor
        or "task40_v30_q_csr_binding" in execution_payload
        or "task40_v30_factor_bank_config" in execution_payload
    ):
        raise V31ContractError("V31 AllQ route requires only its complete V31 execution bindings")
    env = dict(os.environ if environment is None else environment)
    if env.get("TASK40_V31_STRICT_EXECUTION") != "1" or env.get(
        "TASK40_V30_STRICT_EXECUTION"
    ) == "1":
        raise V31ContractError("V31 AllQ route requires separate strict V31 authorization")
    root = Path(repo_root).resolve()
    contract, contract_sha = require_v31_execution_contract(
        env.get("TASK40_V31_CONTRACT_PATH", ""),
        expected_sha256=env.get("TASK40_V31_CONTRACT_SHA256"),
        current_root=root,
    )
    preparation = contract.get("preparation", {})
    if contract.get("schema") == V32_CONTRACT_SCHEMA:
        q4_numeric_pending_import = (
            preparation.get("q4_numeric_pending_import")
            if isinstance(preparation, Mapping)
            else None
        )
        if not isinstance(q4_numeric_pending_import, Mapping):
            raise V31ContractError("V32 AllQ route contract omits its fixed q4 import template")
        q4_numeric_pending_import = dict(q4_numeric_pending_import)
    elif contract.get("schema") == V31_CONTRACT_SCHEMA:
        q4_numeric_pending_import = None
    else:
        raise V31ContractError("V31 AllQ route has an unknown approved contract schema")
    expected_payload_imports = (
        {"numeric_pending": {"4": q4_numeric_pending_import}}
        if q4_numeric_pending_import is not None
        else None
    )
    if (
        execution_payload.get("task40_v31_q_csr_import_authorizations")
        != expected_payload_imports
    ):
        raise V31ContractError("V31/V32 AllQ q4 import differs from its frozen execution contract")
    execution = contract["execution"]
    window = execution["window"]
    resources = execution["resources"]
    expected_environment = {
        "TASK40_V31_EXECUTION_WINDOW_PATH": str(Path(window["window_path"]).resolve()),
        "TASK40_V31_EXECUTION_WINDOW_SHA256": str(window["window_sha256"]),
        "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(resources["task_memory_max_bytes"]),
        "TASK40_V31_HOST_RESERVE_BYTES": str(resources["host_reserve_bytes"]),
        "TASK40_V31_MEMORY_SWAP_MAX_BYTES": str(resources["memory_swap_max_bytes"]),
    }
    if any(env.get(key) != value for key, value in expected_environment.items()):
        raise V31ContractError("V31 AllQ route environment differs from its frozen execution contract")

    run_source_sha = str(execution.get("run_source_sha", ""))
    source_root = root / v31_source_artifact_relative(run_source_sha)
    expected_selector_path = (source_root / "q_csr_selector_v31.json").resolve()
    expected_input_path = (source_root / "stage_inputs" / "full" / "target_original_ny8_resource_pilot_v20.dat").resolve()

    def rooted_path(value: Any) -> Path:
        raw = Path(str(value))
        return (raw if raw.is_absolute() else root / raw).resolve()

    selector_relative = (v31_source_artifact_relative(run_source_sha) / "q_csr_selector_v31.json").as_posix()
    factor_relative = (v31_source_artifact_relative(run_source_sha) / "factor_bank").as_posix()
    selector = execution_payload.get("task40_v31_q_csr_binding")
    factor = execution_payload.get("task40_v31_factor_bank_config")
    expected_selector = {
        "schema": V31_Q_CSR_BINDING_SCHEMA,
        "selector_path": selector_relative,
        "selector_sha256": execution.get("selector_sha256"),
    }
    expected_factor = {
        "schema": V31_FACTOR_BANK_SCHEMA,
        "output_directory": factor_relative,
        "require_two_strict_rhs": True,
        "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
    }
    if (
        execution.get("root") != str(root)
        or run_source_sha != source_sha
        or rooted_path(execution.get("selector_path", "")) != expected_selector_path
        or rooted_path(execution.get("input_path", "")) != expected_input_path
        or not isinstance(selector, dict)
        or selector != expected_selector
        or not isinstance(factor, dict)
        or factor != expected_factor
        or execution_payload.get("task40_execution_stop_stage") != "full"
        or execution_payload.get("task40_target_heavy_authorized") is not True
    ):
        raise V31ContractError("V31 stage input selector/factor/source bindings differ from the frozen contract")

    solver = resolved_payload.get("solver", {})
    method = resolved_payload.get("method", {})
    if not isinstance(solver, dict) or not isinstance(method, dict):
        raise V31ContractError("V31 AllQ route lacks solver or method identity")
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
    )
    from src.solvers.task40_v20_registry import task40_v20_case

    try:
        case = task40_v20_case(profile=str(solver.get("preconditioner", "")))
    except ValueError as error:
        raise V31ContractError("V31 AllQ route has an unknown target profile") from error
    if (
        case.mesh_id != "TARGET_ORIGINAL_NY8"
        or resolved_payload.get("run_id") != case.run_id
        or resolved_payload.get("comparison_group") != TASK40_COMPARISON_GROUP
        or method.get("kind") != "full3d_iterative"
        or solver.get("stage") != case.solver_stage
        or solver.get("preconditioner") != V31_PROFILE
        or solver.get("task40_reference_pc_strategy") != TASK40_V15_REFERENCE_PC_STRATEGY
        or solver.get("task40_q_assembly_strategy") != TASK40_Q_ASSEMBLY_ROW_TILE_V17
        or solver.get("task40_factor_lifecycle_strategy")
        != TASK40_V19_FACTOR_LIFECYCLE_STRATEGY
    ):
        raise V31ContractError(
            "V31 AllQ normalization is limited to the exact Ny8 V20/V15 row-tile V19-request route"
        )
    from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

    provenance = resolved_payload.get("provenance", {})
    staged_path = provenance.get("source_path") if isinstance(provenance, dict) else None
    if not isinstance(staged_path, str) or Path(staged_path).resolve() != expected_input_path:
        raise V31ContractError("V31 AllQ route lacks the source-qualified staged input")
    input_identity = require_v31_input_identity(
        root / V30_CANONICAL_INPUT_RELATIVE,
        staged_path,
        repo_root=root,
        source_sha=run_source_sha,
        selector_sha256=str(execution.get("selector_sha256", "")),
        q4_numeric_pending_import=q4_numeric_pending_import,
    )
    if input_identity["staged_input_sha256"] != provenance.get("input_sha256"):
        raise V31ContractError("V31 AllQ route staged input hash differs from run provenance")
    return {
        "requested_factor_lifecycle_strategy": TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
        "effective_factor_lifecycle_strategy": TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        "contract_path": str(Path(env["TASK40_V31_CONTRACT_PATH"]).resolve()),
        "contract_sha256": contract_sha,
        "execution_window_sha256": str(window["window_sha256"]),
        "input_identity": dict(input_identity),
        "contract": contract,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher-values", action="store_true")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        contract, digest = require_v31_execution_contract(
            args.contract,
            expected_sha256=args.expected_sha256,
            current_root=Path(__file__).resolve().parents[2],
        )
        if args.launcher_values:
            values = v31_launcher_values(
                args.contract,
                expected_sha256=digest,
                current_root=Path(__file__).resolve().parents[2],
            )
            sys.stdout.write("\n".join(values) + "\n")
        else:
            print(json.dumps({"status": "V31_AUTHORIZED", "contract_sha256": digest}))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
