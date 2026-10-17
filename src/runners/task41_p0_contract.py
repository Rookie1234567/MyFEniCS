"""Fixed Task41 P0 source, input, runtime, resource, and deadline contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

from src.runners.task40_v10_campaign import FixedCampaignWindow, _utc_ns
from src.runners.workflow_timebase import clock_sample

TASK41_P0_CONTRACT_SCHEMA = "task41.p0.execution_contract.v1"
TASK41_P0_WINDOW_SCHEMA = "task41.p0.execution_window.v1"
TASK41_P0_AUTH_SCHEMA = "task41.p0.closeout_checker_authorization.v1"
TASK41_BRANCH = "task41extra_phi90_p50x50_g17x20"
TASK41_MODEL_ID = "task41extra_phi90_p50x50_g17x20"
TASK41_RUN_ID = "task41extra_g13_p6_phi90_direct_a1"
TASK41_A2_RUN_ID = "task41extra_g13_p6_phi90_iterative_a2"
TASK41_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller"
)
TASK41_A2_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2_controller"
)
TASK41_WINDOW_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller/execution_window.json"
)
TASK41_A2_WINDOW_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2_controller/execution_window.json"
)
TASK41_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat"
)
TASK41_A2_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_iterative_a2.dat"
)
TASK41_A1_COMPARISON_BINDING_SCHEMA = "task41.p0.a1_comparison_binding.v1"
TASK41_A2_Q_CSR_REUSE_SCHEMA_V1 = "task41.p0.a2_q_csr_reuse.v1"
TASK41_A2_Q_CSR_REUSE_SCHEMA = "task41.p0.a2_q_csr_reuse.v2"
TASK41_A1_COMPARISON_BINDING_RELATIVE = (
    TASK41_A2_CONTROLLER_RELATIVE / "a1_comparison_binding.json"
)
TASK41_A1_SERVICE_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a1"
)
TASK41_A2_SERVICE_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2"
)
TASK41_COMPARISON_GROUP = "task41extra_phi90_p50x50_g17x20_g13_a1a2"
TASK41_TOTAL_SECONDS = 172_800.0
TASK41_NUMERICAL_SECONDS = 171_600.0
TASK41_CLOSEOUT_SECONDS = 1_200.0
TASK41_TASK_MEMORY_MAX_BYTES = 1_649_267_441_664
TASK41_HOST_RESERVE_BYTES = 68_719_476_736


class Task41ContractError(ValueError):
    """The fixed Task41 P0 execution contract is incomplete or inconsistent."""


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()





def _task41_a2_q_csr_selector_entry(
    root: Path,
    manifest_raw_path: str | Path,
    *,
    expected_input_sha256: str,
    consumer_execution_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind one exact Task41 q/twist CSR and its new consumer authorization."""
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import (
        V30_Q_CSR_MANIFEST_SCHEMA,
        V30_Q_CSR_NATIVE_SCHEMA,
        make_v31_q_csr_import_authorization,
    )

    manifest_path = _resolve(root, str(manifest_raw_path), "A2 q CSR manifest path")
    if not manifest_path.is_file() or not manifest_path.is_relative_to(root):
        raise Task41ContractError("Task41 A2 q manifest must be a repository artifact")
    manifest_sha = sha256_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 A2 q manifest is invalid JSON") from exc
    operator = manifest.get("operator_identity") if isinstance(manifest, dict) else None
    q = manifest.get("q_index") if isinstance(manifest, dict) else None
    twist = manifest.get("twist_index") if isinstance(manifest, dict) else None
    expected_twist = (
        q % TASK41_G13_A2_P6_PROFILE.replication_count
        if type(q) is int and 0 <= q < TASK41_G13_A2_P6_PROFILE.q_count
        else None
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != V30_Q_CSR_MANIFEST_SCHEMA
        or manifest.get("status") != "COMPLETE_CSR"
        or type(q) is not int
        or expected_twist is None
        or type(twist) is not int
        or twist != expected_twist
        or manifest.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not isinstance(operator, Mapping)
        or operator.get("scientific_input_sha256") != expected_input_sha256
        or manifest_path.name
        != f"task40_v30_q{q}_twist{expected_twist}_csr_manifest.json"
    ):
        raise Task41ContractError(
            "Task41 A2 saved receipt must match this DAT/profile's exact q-to-twist CSR map"
        )
    qualification_path = manifest_path.with_name(
        f"task40_v30_q{q}_twist{expected_twist}_native_qualification.json"
    )
    if not qualification_path.is_file() or not qualification_path.resolve().is_relative_to(root):
        raise Task41ContractError(f"Task41 A2 q{q} native qualification is missing")
    qualification_sha = sha256_file(qualification_path)
    try:
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 A2 native qualification is invalid JSON") from exc
    if (
        not isinstance(qualification, dict)
        or qualification.get("schema") != V30_Q_CSR_NATIVE_SCHEMA
        or qualification.get("status") != "PASS"
        or qualification.get("q_index") != q
        or qualification.get("twist_index") != expected_twist
        or qualification.get("csr_manifest_sha256") != manifest_sha
    ):
        raise Task41ContractError(f"Task41 A2 q{q} native qualification does not bind its manifest")
    artifacts = manifest.get("csr_artifacts")
    if not isinstance(artifacts, Mapping):
        raise Task41ContractError(f"Task41 A2 q{q} manifest omits its CSR arrays")
    authorization_artifacts = {}
    for name in ("data", "indices", "indptr"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise Task41ContractError(f"Task41 A2 q{q} manifest omits CSR {name}")
        raw = Path(str(record.get("path", "")))
        path = (raw if raw.is_absolute() else manifest_path.parent / raw).resolve(strict=False)
        if not path.is_relative_to(root):
            raise Task41ContractError(f"Task41 A2 q{q} CSR {name} escaped the repository")
        authorization_artifacts[name] = {
            "path": str(path),
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
    entry = {
        "q_index": q,
        "twist_index": expected_twist,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "shape": manifest.get("shape"),
        "operator_identity": operator,
        "matrix_source_identity": manifest.get("matrix_source_identity"),
        "execution_identity": manifest.get("execution_identity"),
        "csr_manifest": {"path": str(manifest_path), "sha256": manifest_sha},
        "native_qualification": {
            "path": str(qualification_path.resolve()),
            "sha256": qualification_sha,
            "status": "PASS",
        },
        "manifest_status": "COMPLETE_CSR",
        "qualification_status": "PASS",
        "manifest_sha256": manifest_sha,
        "native_qualification_sha256": qualification_sha,
    }
    authorization = make_v31_q_csr_import_authorization(
        q_index=q,
        twist_index=expected_twist,
        profile=TASK41_G13_A2_PRECONDITIONER,
        operator_identity=operator,
        matrix_source_identity=manifest.get("matrix_source_identity", {}),
        producer_identity=manifest.get("producer_identity", {}),
        producer_execution_identity=manifest.get("execution_identity", {}),
        native_execution_identity=qualification.get("execution_identity", {}),
        csr_manifest_sha256=manifest_sha,
        native_qualification_sha256=qualification_sha,
        csr_artifacts=authorization_artifacts,
        consumer_execution_identity=consumer_execution_identity,
    )
    return entry, authorization


def _prepare_task41_a2_q_csr_reuse(
    root: Path,
    manifest_paths: Sequence[str | Path],
    *,
    source_sha: str,
    window_sha256: str,
    expected_input_sha256: str,
) -> dict[str, Any]:
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import V30_Q_CSR_SELECTOR_SCHEMA

    q_indices = list(range(TASK41_G13_A2_P6_PROFILE.q_count))
    twist_indices_by_q = {
        str(q): q % TASK41_G13_A2_P6_PROFILE.replication_count for q in q_indices
    }
    if isinstance(manifest_paths, (str, bytes)) or len(manifest_paths) != len(q_indices):
        raise Task41ContractError("Task41 A2 q reuse requires one manifest for each of q=0..9")
    consumer = {"source_sha": source_sha, "window_sha256": window_sha256}
    entries, authorizations = [], {}
    for raw_path in manifest_paths:
        entry, authorization = _task41_a2_q_csr_selector_entry(
            root,
            raw_path,
            expected_input_sha256=expected_input_sha256,
            consumer_execution_identity=consumer,
        )
        q = int(entry["q_index"])
        if str(q) in authorizations:
            raise Task41ContractError("Task41 A2 q reuse repeats a manifest")
        entries.append(entry)
        authorizations[str(q)] = authorization
    entries.sort(key=lambda row: row["q_index"])
    if [row["q_index"] for row in entries] != q_indices or any(
        row["twist_index"] != twist_indices_by_q[str(row["q_index"])]
        for row in entries
    ):
        raise Task41ContractError("Task41 A2 q reuse must bind the exact ten-q twist map")
    selector = {
        "schema": V30_Q_CSR_SELECTOR_SCHEMA,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "q_csr_entries": entries,
    }
    selector_path = (
        root / TASK41_A2_CONTROLLER_RELATIVE
        / f"q_csr_reuse_selector_source_{source_sha}.json"
    )
    if not _write_json_no_replace(selector_path, selector):
        try:
            saved = json.loads(selector_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Task41ContractError("existing Task41 A2 q selector cannot be reopened") from exc
        if saved != selector:
            raise Task41ContractError("existing Task41 A2 q selector differs from this binding")
    bindings = [
        {"q_index": row["q_index"], **row["csr_manifest"]} for row in entries
    ]
    return {
        "schema": TASK41_A2_Q_CSR_REUSE_SCHEMA,
        "q_indices": q_indices,
        "twist_indices_by_q": twist_indices_by_q,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "manifest_bindings": bindings,
        "selector_path": selector_path.relative_to(root).as_posix(),
        "selector_sha256": sha256_file(selector_path),
        "consumer_import_authorizations": authorizations,
    }


def _validate_task41_a2_q_csr_reuse(
    root: Path,
    reuse: Any,
    *,
    source_sha: str,
    window_sha256: str,
    expected_input_sha256: str,
) -> None:
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import V30_Q_CSR_SELECTOR_SCHEMA

    if not isinstance(reuse, Mapping):
        raise Task41ContractError("Task41 A2 q reuse contract is malformed")
    schema = reuse.get("schema")
    if schema == TASK41_A2_Q_CSR_REUSE_SCHEMA_V1:
        q_indices = [0, 5]
        twist_indices_by_q = {"0": 0, "5": 0}
        required_keys = {
            "schema", "q_indices", "twist_index", "profile", "manifest_bindings",
            "selector_path", "selector_sha256", "consumer_import_authorizations",
        }
        if reuse.get("twist_index") != 0:
            raise Task41ContractError("Task41 A2 v1 q reuse must be q0/q5 at twist zero")
        legacy_v1 = True
    elif schema == TASK41_A2_Q_CSR_REUSE_SCHEMA:
        q_indices = list(range(TASK41_G13_A2_P6_PROFILE.q_count))
        twist_indices_by_q = {
            str(q): q % TASK41_G13_A2_P6_PROFILE.replication_count for q in q_indices
        }
        required_keys = {
            "schema", "q_indices", "twist_indices_by_q", "profile", "manifest_bindings",
            "selector_path", "selector_sha256", "consumer_import_authorizations",
        }
        legacy_v1 = False
    else:
        raise Task41ContractError("Task41 A2 q reuse contract has an unsupported schema")
    if (
        set(reuse) != required_keys
        or reuse.get("q_indices") != q_indices
        or (
            not legacy_v1
            and reuse.get("twist_indices_by_q") != twist_indices_by_q
        )
        or reuse.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not _is_sha256(reuse.get("selector_sha256"))
    ):
        raise Task41ContractError("Task41 A2 q reuse contract is malformed")
    selector_path = _resolve(root, reuse["selector_path"], "A2 q reuse selector path")
    expected_path = (
        root / TASK41_A2_CONTROLLER_RELATIVE
        / f"q_csr_reuse_selector_source_{source_sha}.json"
    ).resolve()
    if selector_path != expected_path or not selector_path.is_file() or sha256_file(selector_path) != reuse["selector_sha256"]:
        raise Task41ContractError("Task41 A2 q reuse selector path or hash changed")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    entries = selector.get("q_csr_entries") if isinstance(selector, Mapping) else None
    bindings = reuse.get("manifest_bindings")
    authorizations = reuse.get("consumer_import_authorizations")
    if (
        not isinstance(selector, Mapping)
        or selector.get("schema") != V30_Q_CSR_SELECTOR_SCHEMA
        or selector.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not isinstance(entries, list)
        or len(entries) != len(q_indices)
        or any(not isinstance(row, Mapping) for row in entries)
        or [row.get("q_index") for row in entries] != q_indices
        or not isinstance(bindings, list)
        or len(bindings) != len(q_indices)
        or any(not isinstance(row, Mapping) for row in bindings)
        or not isinstance(authorizations, Mapping)
        or set(authorizations) != {str(q) for q in q_indices}
    ):
        raise Task41ContractError("Task41 A2 q reuse selector or manifest bindings are incomplete")
    expected_consumer = {"source_sha": source_sha, "window_sha256": window_sha256}
    sorted_bindings = sorted(bindings, key=lambda row: row.get("q_index"))
    for q, entry, binding in zip(q_indices, entries, sorted_bindings):
        twist = twist_indices_by_q[str(q)]
        auth = authorizations[str(q)]
        manifest_ref = entry.get("csr_manifest")
        entry_profile_ok = (
            entry.get("profile") == TASK41_G13_A2_PRECONDITIONER
            if not legacy_v1
            else entry.get("profile") in (None, TASK41_G13_A2_PRECONDITIONER)
        )
        if (
            not isinstance(manifest_ref, Mapping)
            or binding.get("q_index") != q
            or binding.get("path") != manifest_ref.get("path")
            or binding.get("sha256") != manifest_ref.get("sha256")
            or not _is_sha256(binding.get("sha256"))
            or entry.get("twist_index") != twist
            or not entry_profile_ok
            or not isinstance(auth, Mapping)
            or auth.get("q_index") != q
            or auth.get("twist_index") != twist
            or auth.get("profile") != TASK41_G13_A2_PRECONDITIONER
            or auth.get("consumer_execution_identity") != expected_consumer
            or auth.get("csr_manifest_sha256") != binding.get("sha256")
        ):
            raise Task41ContractError(f"Task41 A2 q{q} reuse binding is not source-bound")
        manifest_path = _resolve(root, str(binding["path"]), f"A2 q{q} manifest path")
        if not manifest_path.is_file() or not manifest_path.is_relative_to(root) or sha256_file(manifest_path) != binding["sha256"]:
            raise Task41ContractError(f"Task41 A2 q{q} manifest hash changed")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        operator = manifest.get("operator_identity") if isinstance(manifest, Mapping) else None
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("q_index") != q
            or manifest.get("twist_index") != twist
            or manifest.get("profile") != TASK41_G13_A2_PRECONDITIONER
            or not isinstance(operator, Mapping)
            or operator.get("scientific_input_sha256") != expected_input_sha256
        ):
            raise Task41ContractError(f"Task41 A2 q{q} manifest no longer matches this DAT/profile")

def _utc_text_from_ns(value: int) -> str:
    seconds, nanoseconds = divmod(int(value), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + (
        f".{nanoseconds:09d}Z"
    )


def _write_json_no_replace(path: Path, payload: Mapping[str, Any]) -> bool:
    """Atomically create one JSON file without ever replacing an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _resolve(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or "\n" in raw:
        raise Task41ContractError(f"{label} must be a nonempty path")
    path = Path(raw)
    return (path if path.is_absolute() else root / path).resolve()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _task41_case(case_id: str) -> dict[str, Any]:
    if case_id == "A1":
        return {
            "case_id": "A1",
            "run_id": TASK41_RUN_ID,
            "input_relative": TASK41_INPUT_RELATIVE,
            "controller_relative": TASK41_CONTROLLER_RELATIVE,
            "window_relative": TASK41_WINDOW_RELATIVE,
            "method": "full3d_direct",
            "service_relative": TASK41_A1_SERVICE_RELATIVE,
        }
    if case_id == "A2":
        return {
            "case_id": "A2",
            "run_id": TASK41_A2_RUN_ID,
            "input_relative": TASK41_A2_INPUT_RELATIVE,
            "controller_relative": TASK41_A2_CONTROLLER_RELATIVE,
            "window_relative": TASK41_A2_WINDOW_RELATIVE,
            "method": "full3d_iterative",
            "service_relative": TASK41_A2_SERVICE_RELATIVE,
        }
    raise Task41ContractError("Task41 P0 case id must be A1 or A2")


def task41_case_id_for_run_id(run_id: str) -> str:
    if run_id == TASK41_RUN_ID:
        return "A1"
    if run_id == TASK41_A2_RUN_ID:
        return "A2"
    raise Task41ContractError("Task41 run id is not registered for P0")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _checked_binding_file(
    root: Path,
    record: Any,
    label: str,
    *,
    within: Path,
) -> Path:
    if not isinstance(record, Mapping):
        raise Task41ContractError(f"A1 comparison binding {label} record is missing")
    path = _resolve(root, record.get("path"), f"A1 binding {label}.path")
    if not path.is_relative_to(within):
        raise Task41ContractError(f"A1 comparison binding {label} escaped its registered tree")
    if (
        type(record.get("bytes")) is not int
        or record["bytes"] <= 0
        or not _is_sha256(record.get("sha256"))
        or not path.is_file()
        or path.stat().st_size != record["bytes"]
        or sha256_file(path) != record["sha256"]
    ):
        raise Task41ContractError(f"A1 comparison binding {label} file identity changed")
    return path


def require_task41_a1_comparison_binding(
    path: str | Path | None = None,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Reopen the immutable, checker-PASS A1 evidence used by the A2 case."""
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    binding_path = _resolve(
        root,
        str(path or TASK41_A1_COMPARISON_BINDING_RELATIVE),
        "A1 comparison binding path",
    )
    if binding_path != (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve():
        raise Task41ContractError("A1 comparison binding is outside the registered A2 controller")
    raw = binding_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Task41ContractError("A1 comparison binding SHA-256 differs from the A2 contract")
    binding = json.loads(raw)
    if not isinstance(binding, dict) or binding.get("schema") != TASK41_A1_COMPARISON_BINDING_SCHEMA:
        raise Task41ContractError("A1 comparison binding schema is invalid")
    if (
        binding.get("status") != "PASS"
        or binding.get("task_id") != TASK41_MODEL_ID
        or binding.get("comparison_group") != TASK41_COMPARISON_GROUP
    ):
        raise Task41ContractError("A1 comparison binding does not identify a passed Task41 comparison")
    a1 = binding.get("a1")
    if not isinstance(a1, Mapping):
        raise Task41ContractError("A1 comparison binding has no A1 identity")
    source_sha = a1.get("source_sha")
    if (
        a1.get("run_id") != TASK41_RUN_ID
        or a1.get("model_id") != TASK41_MODEL_ID
        or a1.get("method") != "full3d_direct"
        or a1.get("mpi_size") != 1
        or not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or a1.get("input_path") != str(TASK41_INPUT_RELATIVE)
        or not _is_sha256(a1.get("input_sha256"))
        or not _is_sha256(a1.get("physical_model_sha256"))
        or not _is_sha256(a1.get("resolved_config_sha256"))
    ):
        raise Task41ContractError("A1 comparison binding has an invalid run/input/physics identity")
    input_path = (root / TASK41_INPUT_RELATIVE).resolve()
    if not input_path.is_file() or sha256_file(input_path) != a1["input_sha256"]:
        raise Task41ContractError("A1 comparison binding does not match the registered A1 DAT")

    run_root = _resolve(root, a1.get("run_root"), "A1 binding run_root")
    registered_results = (root / "results" / TASK41_MODEL_ID).resolve()
    if not run_root.is_relative_to(registered_results) or not run_root.is_dir():
        raise Task41ContractError("A1 comparison run root is missing or outside Task41 results")
    manifest_path = _checked_binding_file(
        root, a1.get("run_manifest"), "run_manifest", within=run_root
    )
    summary_path = _checked_binding_file(
        root, a1.get("numerical_summary"), "numerical_summary", within=run_root
    )
    resolved_path = _checked_binding_file(
        root, a1.get("resolved_config"), "resolved_config", within=run_root
    )
    if (
        manifest_path != run_root / "run_manifest.json"
        or summary_path != run_root / "numerical_output" / "run_summary.json"
        or resolved_path != run_root / "resolved_config.json"
        or sha256_file(resolved_path) != a1["resolved_config_sha256"]
    ):
        raise Task41ContractError("A1 comparison run manifest/config paths are inconsistent")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    numerical = json.loads(summary_path.read_text(encoding="utf-8"))
    for key, expected in {
        "model_id": TASK41_MODEL_ID,
        "run_id": TASK41_RUN_ID,
        "method": "full3d_direct",
        "mpi_size": 1,
        "source_sha": source_sha,
        "input_sha256": a1["input_sha256"],
        "physical_model_sha256": a1["physical_model_sha256"],
        "resolved_config_sha256": a1["resolved_config_sha256"],
    }.items():
        if manifest.get(key) != expected:
            raise Task41ContractError(f"A1 run manifest {key} differs from its comparison binding")
    if numerical.get("official_result") is not True or numerical.get("case_status") != "completed":
        raise Task41ContractError("A1 numerical summary is not an official completed result")

    checker_dir = (
        root / _task41_case("A1")["service_relative"] / f"service_source_{source_sha}"
    ).resolve()
    checker_path = _checked_binding_file(
        root, a1.get("required_checker"), "required_checker", within=checker_dir
    )
    if checker_path != checker_dir / "task41_p0_checker_result.json":
        raise Task41ContractError("A1 required checker path is not the registered checker receipt")
    checker = json.loads(checker_path.read_text(encoding="utf-8"))
    if (
        a1["required_checker"].get("schema") != "task41.p0.direct_checker.v1"
        or checker.get("schema") != "task41.p0.direct_checker.v1"
        or checker.get("status") != "PASS"
        or checker.get("checker_passed") is not True
        or checker.get("full_pass") is not True
        or checker.get("official_result") is not True
        or checker.get("run_id") != TASK41_RUN_ID
        or checker.get("source_sha") != source_sha
        or checker.get("input_sha256") != a1["input_sha256"]
        or checker.get("physical_model_sha256") != a1["physical_model_sha256"]
        or checker.get("resolved_config_sha256") != a1["resolved_config_sha256"]
    ):
        raise Task41ContractError("A1 required checker is not a matching PASS receipt")

    discrete = a1.get("discrete_identity")
    if not isinstance(discrete, Mapping):
        raise Task41ContractError("A1 comparison binding omits discrete FE/mode identity")
    if (
        not _is_sha256(discrete.get("mesh_sha256"))
        or not _is_sha256(discrete.get("mode_manifest_sha256"))
        or not _is_sha256(discrete.get("ordered_mode_key_sha256"))
        or discrete.get("mode_count") != 168
        or discrete.get("full_fe_rows") != 934764
    ):
        raise Task41ContractError("A1 comparison binding has an invalid mesh/mode/FE identity")
    map_status = discrete.get("mpc_map_status")
    map_sha = discrete.get("mpc_map_sha256")
    comparison_ready = discrete.get("same_discrete_comparison_ready")
    if map_status == "PASS":
        if not _is_sha256(map_sha) or comparison_ready is not True:
            raise Task41ContractError("A1 MPC map identity status is internally inconsistent")
    elif map_status == "NOT_RECORDED":
        if map_sha is not None or comparison_ready is not False:
            raise Task41ContractError("A1 missing MPC map identity must remain explicitly unqualified")
    else:
        raise Task41ContractError("A1 MPC map identity must be PASS or explicitly NOT_RECORDED")
    abi = a1.get("abi_identity")
    if (
        not isinstance(abi, Mapping)
        or abi.get("scalar_type") != "complex128"
        or abi.get("int_type") != "int32"
        or abi.get("mpi_size") != 1
    ):
        raise Task41ContractError("A1 comparison binding does not identify the qualified numerical ABI")

    artifacts = a1.get("comparison_artifacts")
    required_artifacts = {
        "full_solution",
        "native_a6_residual",
        "airbox_fields",
        "full3d_samples_archive",
        "full3d_samples_metadata",
        "modal_amplitudes",
        "port_power_metrics",
        "volume_absorption",
        "diffraction_orders",
        "mesh_h5",
        "mesh_xdmf",
    }
    if not isinstance(artifacts, Mapping) or not required_artifacts.issubset(artifacts):
        raise Task41ContractError("A1 comparison binding omits required field/mode/power artifacts")
    checked_artifacts = {}
    for name in sorted(required_artifacts):
        artifact_path = _checked_binding_file(
            root, artifacts[name], f"comparison_artifacts.{name}", within=run_root
        )
        checked_artifacts[name] = {
            "path": str(artifact_path.relative_to(root)),
            "bytes": artifacts[name]["bytes"],
            "sha256": artifacts[name]["sha256"],
        }
    field_record = artifacts["full_solution"]
    if field_record.get("array_key") != "recovered_field" or field_record.get("rank") != 0:
        raise Task41ContractError("A1 full FE field binding must select rank-0 recovered_field")
    return binding, digest


def contract_relative_path(source_sha: str, case_id: str = "A1") -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 source SHA is invalid")
    case = _task41_case(case_id)
    return case["controller_relative"] / f"execution_contract_source_{source_sha}.json"


def require_task41_p0_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
    require_clean_source: bool = False,
    check_current_source: bool = False,
    case_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract_path = _resolve(root, str(path), "contract path")
    try:
        relative = contract_path.relative_to(root)
    except ValueError as exc:
        raise Task41ContractError("Task41 contract escaped the repository") from exc
    if case_id is None:
        if relative.parent == TASK41_A2_CONTROLLER_RELATIVE:
            case_id = "A2"
        elif relative.parent == TASK41_CONTROLLER_RELATIVE:
            case_id = "A1"
        else:
            raise Task41ContractError("Task41 contract is outside a registered P0 controller directory")
    case_spec = _task41_case(case_id)
    if relative.parent != case_spec["controller_relative"] or not re.fullmatch(
        r"execution_contract_source_[0-9a-f]{40}\.json", relative.name
    ):
        raise Task41ContractError("Task41 contract is not in the registered P0 controller directory")
    raw = contract_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Task41ContractError("Task41 contract SHA-256 differs from the launch binding")
    contract = json.loads(raw)
    if not isinstance(contract, dict) or contract.get("schema") != TASK41_P0_CONTRACT_SCHEMA:
        raise Task41ContractError("Task41 P0 execution contract schema is invalid")
    if contract.get("task_id") != TASK41_MODEL_ID or contract.get("branch") != TASK41_BRANCH:
        raise Task41ContractError("Task41 contract task or branch identity differs")
    source = contract.get("source")
    case = contract.get("case")
    runtime = contract.get("runtime")
    window = contract.get("window")
    resources = contract.get("resources")
    time_limits = contract.get("time")
    evidence = contract.get("evidence")
    if not all(
        isinstance(item, dict)
        for item in (source, case, runtime, window, resources, time_limits, evidence)
    ):
        raise Task41ContractError("Task41 contract sections must be JSON objects")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("sha", ""))):
        raise Task41ContractError("Task41 contract source SHA is invalid")
    if relative != contract_relative_path(str(source["sha"]), case_id):
        raise Task41ContractError("Task41 contract filename is not bound to its source SHA")
    if check_current_source:
        if _git(root, "rev-parse", "HEAD") != source["sha"]:
            raise Task41ContractError("Task41 source HEAD differs from the fixed contract")
        if _git(root, "branch", "--show-current") != TASK41_BRANCH:
            raise Task41ContractError("Task41 current branch differs from the fixed contract")
    if require_clean_source and _git(
        root, "status", "--porcelain", "--untracked-files=normal"
    ):
        raise Task41ContractError("Task41 formal execution requires a clean frozen source tree")

    input_path = _resolve(root, case.get("input_path"), "Task41 DAT path")
    if (
        input_path != (root / case_spec["input_relative"]).resolve()
        or not input_path.is_file()
        or sha256_file(input_path) != case.get("input_sha256")
        or case.get("model_id") != TASK41_MODEL_ID
        or case.get("run_id") != case_spec["run_id"]
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("physical_model_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("resolved_config_sha256", "")))
        or case.get("method") != case_spec["method"]
        or case.get("mpi_size") != 1
    ):
        raise Task41ContractError("Task41 contract does not bind the registered G13 direct input")

    for key in ("runtime_prefix", "abi_receipt_path", "jit_cache"):
        if not _resolve(root, runtime.get(key), f"runtime.{key}").exists():
            raise Task41ContractError(f"Task41 runtime.{key} does not exist")
    runtime_prefix = _resolve(root, runtime["runtime_prefix"], "runtime.runtime_prefix")
    if not (runtime_prefix / "bin" / "python").is_file() or not os.access(
        runtime_prefix / "bin" / "python", os.X_OK
    ):
        raise Task41ContractError("Task41 runtime prefix has no executable bin/python")
    abi_path = _resolve(root, runtime["abi_receipt_path"], "runtime.abi_receipt_path")
    if sha256_file(abi_path) != runtime.get("abi_receipt_sha256"):
        raise Task41ContractError("Task41 ABI receipt hash differs from the contract")
    if runtime.get("mpi_ranks") != 1 or runtime.get("math_threads") != 1:
        raise Task41ContractError("Task41 runtime must be MPI1 with one math thread")
    if runtime.get("profile") != "native_linux":
        raise Task41ContractError("formal Task41 P0 execution requires the registered native_linux runtime")
    window_path = _resolve(root, window.get("path"), "window.path")
    if window_path != (root / case_spec["window_relative"]).resolve():
        raise Task41ContractError("Task41 fixed window path is not registered")
    if not re.fullmatch(r"[0-9a-f]{64}", str(window.get("sha256", ""))):
        raise Task41ContractError("Task41 fixed window SHA-256 is invalid")
    if (
        resources.get("task_memory_max_bytes") != TASK41_TASK_MEMORY_MAX_BYTES
        or resources.get("host_reserve_bytes") != TASK41_HOST_RESERVE_BYTES
        or resources.get("memory_swap_max_bytes") != 0
    ):
        raise Task41ContractError("Task41 resource limits differ from the task ceiling")
    if (
        time_limits.get("total_seconds") != TASK41_TOTAL_SECONDS
        or time_limits.get("numerical_seconds") != TASK41_NUMERICAL_SECONDS
        or time_limits.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 contract time limits differ from the fixed P0 window")
    service_directory = _resolve(root, evidence.get("service_directory"), "evidence.service_directory")
    expected_service_directory = (
        root / case_spec["service_relative"] / f"service_source_{source['sha']}"
    ).resolve()
    if service_directory != expected_service_directory:
        raise Task41ContractError("Task41 service evidence directory differs from the registered case")
    comparison = contract.get("comparison")
    if case_id == "A2":
        if not isinstance(comparison, Mapping):
            raise Task41ContractError("Task41 A2 contract omits its immutable A1 comparison binding")
        binding_path = _resolve(root, comparison.get("a1_binding_path"), "comparison.a1_binding_path")
        if binding_path != (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve():
            raise Task41ContractError("Task41 A2 contract uses an unregistered A1 comparison binding path")
        binding, binding_digest = require_task41_a1_comparison_binding(
            binding_path,
            expected_sha256=comparison.get("a1_binding_sha256"),
            current_root=root,
        )
        if binding["a1"]["physical_model_sha256"] != case["physical_model_sha256"]:
            raise Task41ContractError("A1 and A2 comparison binding have different physical models")
        if comparison.get("same_discrete_comparison_ready") is not binding["a1"][
            "discrete_identity"
        ].get("same_discrete_comparison_ready"):
            raise Task41ContractError("Task41 A2 comparison readiness differs from the bound A1 evidence")
        if comparison.get("a1_binding_sha256") != binding_digest:
            raise Task41ContractError("Task41 A2 comparison binding hash changed")
    elif comparison is not None:
        raise Task41ContractError("A1 contract must not carry an A1/A2 comparison binding")
    q_csr_reuse = contract.get("q_csr_reuse")
    if q_csr_reuse is not None:
        if case_id != "A2":
            raise Task41ContractError("only Task41 A2 may bind saved q CSR reuse")
        _validate_task41_a2_q_csr_reuse(
            root,
            q_csr_reuse,
            source_sha=str(source["sha"]),
            window_sha256=str(window.get("sha256", "")),
            expected_input_sha256=str(case.get("input_sha256", "")),
        )
    return contract, digest


def load_task41_p0_fixed_window(
    contract: Mapping[str, Any], *, current_root: str | Path | None = None,
    require_current_boot: bool = True,
) -> FixedCampaignWindow:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case_spec = _task41_case(
        task41_case_id_for_run_id(str(contract.get("case", {}).get("run_id", "")))
    )
    window_info = contract["window"]
    path = _resolve(root, window_info["path"], "window.path")
    if path != (root / case_spec["window_relative"]).resolve():
        raise Task41ContractError("Task41 fixed window path differs from the registered case")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != window_info["sha256"]:
        raise Task41ContractError("Task41 fixed execution window hash changed")
    payload = json.loads(raw)
    expected_fields = {
        "schema", "task_id", "source_sha", "t0_utc", "numerical_deadline_utc",
        "deadline_utc", "total_seconds", "numerical_seconds", "closeout_seconds",
        "anchor", "accounting_path",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Task41ContractError("Task41 fixed execution window has an open or incomplete schema")
    if (
        payload.get("schema") != TASK41_P0_WINDOW_SCHEMA
        or payload.get("task_id") != TASK41_MODEL_ID
        or payload.get("source_sha") != window_info.get("entry_source_sha")
        or not re.fullmatch(r"[0-9a-f]{40}", str(window_info.get("entry_source_sha", "")))
        or payload.get("total_seconds") != TASK41_TOTAL_SECONDS
        or payload.get("numerical_seconds") != TASK41_NUMERICAL_SECONDS
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 execution window identity or time limits changed")
    anchor = payload.get("anchor")
    if not isinstance(anchor, dict) or set(anchor) != {
        "monotonic", "boottime", "utc_ns", "boot_id"
    }:
        raise Task41ContractError("Task41 execution window clock anchor is incomplete")
    try:
        t0_ns = _utc_ns(payload["t0_utc"])
        numerical_deadline_ns = _utc_ns(payload["numerical_deadline_utc"])
        deadline_ns = _utc_ns(payload["deadline_utc"])
    except ValueError as exc:
        raise Task41ContractError(f"Task41 execution window UTC value is invalid: {exc}") from exc
    if (
        anchor["utc_ns"] != t0_ns
        or numerical_deadline_ns != t0_ns + int(TASK41_NUMERICAL_SECONDS * 1e9)
        or deadline_ns != t0_ns + int(TASK41_TOTAL_SECONDS * 1e9)
        or not isinstance(anchor["boot_id"], str)
        or not anchor["boot_id"]
    ):
        raise Task41ContractError("Task41 execution window timestamps are inconsistent")
    if require_current_boot:
        current = clock_sample(include_boot_id=True)
        if current["boot_id"] != anchor["boot_id"]:
            raise Task41ContractError("Task41 execution window belongs to another boot")
        if current["utc_ns"] >= deadline_ns:
            raise Task41ContractError("Task41 fixed execution window has expired")
    accounting_path = _resolve(root, payload["accounting_path"], "accounting_path")
    if not accounting_path.is_relative_to(root / "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20"):
        raise Task41ContractError("Task41 accounting ledger escaped its artifact directory")
    return FixedCampaignWindow(
        path=path,
        sha256=digest,
        payload=payload,
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=deadline_ns,
        total_seconds=TASK41_TOTAL_SECONDS,
        bootstrap_seconds=0.0,
        closeout_seconds=TASK41_CLOSEOUT_SECONDS,
    )


def _task41_window_for_contract(
    root: Path, case_id: str = "A1"
) -> tuple[FixedCampaignWindow, str, dict[str, Any]]:
    case_spec = _task41_case(case_id)
    path = (root / case_spec["window_relative"]).resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 fixed execution window is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise Task41ContractError("Task41 fixed execution window must be a JSON object")
    entry_source = payload.get("source_sha")
    window_contract = {
        "case": {"run_id": case_spec["run_id"]},
        "window": {
            "path": str(case_spec["window_relative"]),
            "sha256": digest,
            "entry_source_sha": entry_source,
        },
    }
    window = load_task41_p0_fixed_window(
        window_contract, current_root=root, require_current_boot=True
    )
    return window, digest, payload


def _check_task41_native_receipt(
    abi_receipt_path: Path, runtime_prefix: Path
) -> str:
    try:
        receipt = json.loads(abi_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError(f"Task41 ABI receipt cannot be read: {exc}") from exc
    petsc = receipt.get("PETSc") if isinstance(receipt, dict) else None
    mpi = receipt.get("MPI") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
        or receipt.get("runtime_profile") != "native_linux"
        or Path(str(receipt.get("prefix", ""))).resolve() != runtime_prefix.resolve()
        or not isinstance(petsc, dict)
        or petsc.get("scalar_dtype") != "complex128"
        or petsc.get("int_dtype") != "int32"
        or not isinstance(mpi, dict)
        or mpi.get("size") != 1
        or mpi.get("rank") != 0
    ):
        raise Task41ContractError(
            "Task41 ABI receipt must bind native_linux, complex128/int32, and MPI1"
        )
    return hashlib.sha256(abi_receipt_path.read_bytes()).hexdigest()


def prepare_task41_p0(
    *,
    runtime_prefix: str | Path,
    abi_receipt: str | Path,
    jit_cache: str | Path,
    current_root: str | Path | None = None,
    case_id: str = "A1",
    a2_q_csr_manifests: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Register or reuse the one fixed P0 window, then write a source-bound contract.

    On first use the T0 record is durably created before runtime and input validation.
    Later calls reuse its exact bytes, including when the current source has changed.
    """
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case_spec = _task41_case(case_id)
    source_sha = _git(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 current HEAD is not a full Git SHA")
    if _git(root, "branch", "--show-current") != TASK41_BRANCH:
        raise Task41ContractError("Task41 P0 prepare requires the registered execution branch")
    if _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 P0 prepare requires a clean frozen source tree")

    window_path = (root / case_spec["window_relative"]).resolve()
    if not window_path.exists():
        anchor = clock_sample(include_boot_id=True)
        t0_ns = int(anchor["utc_ns"])
        window_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": source_sha,
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)
            ),
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (root / case_spec["controller_relative"] / "campaign_accounting_v10.jsonl").resolve()
            ),
        }
        _write_json_no_replace(window_path, window_payload)

    window, window_sha, window_payload = _task41_window_for_contract(root, case_id)

    runtime_path = _resolve(root, str(runtime_prefix), "runtime_prefix")
    abi_path = _resolve(root, str(abi_receipt), "abi_receipt")
    jit_path = _resolve(root, str(jit_cache), "jit_cache")
    python_path = runtime_path / "bin" / "python"
    if not runtime_path.is_dir() or not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise Task41ContractError("Task41 native runtime prefix must contain executable bin/python")
    if not abi_path.is_file() or not jit_path.is_dir():
        raise Task41ContractError("Task41 ABI receipt or JIT cache path is missing")
    abi_sha = _check_task41_native_receipt(abi_path, runtime_path)

    input_path = (root / case_spec["input_relative"]).resolve()
    try:
        from src.geometry.task41_phi90_profile import task41_payload_errors
        from src.io.execution_plan import resolved_config_bytes
        from src.io.input_validation import load_and_resolve

        specification = load_and_resolve(input_path)
        payload_errors = task41_payload_errors(specification.as_jsonable())
    except (OSError, ValueError, RuntimeError) as exc:
        raise Task41ContractError(f"Task41 registered DAT could not be resolved: {exc}") from exc
    if payload_errors:
        raise Task41ContractError(
            "Task41 registered DAT failed its native physics/profile gate: "
            + "; ".join(payload_errors)
        )
    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    case = {
        "input_path": str(case_spec["input_relative"]),
        "input_sha256": specification.input_sha256,
        "model_id": specification.identity.get("model_id"),
        "run_id": specification.identity.get("run_id"),
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "method": specification.method.get("kind"),
        "mpi_size": specification.execution.get("mpi_size"),
    }
    validate_task41_specification(specification, input_path, {"case": case}, current_root=root)

    comparison = None
    if case_id == "A2":
        binding_path = (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve()
        binding, binding_sha256 = require_task41_a1_comparison_binding(
            binding_path, current_root=root
        )
        if binding["a1"]["physical_model_sha256"] != case["physical_model_sha256"]:
            raise Task41ContractError("A1 and A2 comparison binding have different physical models")
        comparison = {
            "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
            "a1_binding_sha256": binding_sha256,
            "same_discrete_comparison_ready": binding["a1"][
                "discrete_identity"
            ]["same_discrete_comparison_ready"],
        }

    q_csr_reuse = None
    if case_id == "A2":
        if a2_q_csr_manifests is None:
            raise Task41ContractError(
                "Task41 A2 contract preparation requires all ten saved q CSR/native manifests"
            )
        q_csr_reuse = _prepare_task41_a2_q_csr_reuse(
            root,
            a2_q_csr_manifests,
            source_sha=source_sha,
            window_sha256=window_sha,
            expected_input_sha256=case["input_sha256"],
        )
    elif a2_q_csr_manifests is not None:
        raise Task41ContractError("saved q CSR reuse is available only for Task41 A2")

    if _git(root, "rev-parse", "HEAD") != source_sha or _git(
        root, "branch", "--show-current"
    ) != TASK41_BRANCH or _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 source changed while the P0 contract was being prepared")

    contract_path = root / contract_relative_path(source_sha, case_id)
    if contract_path.exists():
        raise Task41ContractError("a Task41 contract already exists for this source SHA")
    service_directory = case_spec["service_relative"] / f"service_source_{source_sha}"
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": case,
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime_path),
            "abi_receipt_path": str(abi_path),
            "abi_receipt_sha256": abi_sha,
            "jit_cache": str(jit_path),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": {
            "path": str(case_spec["window_relative"]),
            "sha256": window_sha,
            "entry_source_sha": window_payload["source_sha"],
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        },
        "evidence": {"service_directory": str(service_directory)},
    }
    if comparison is not None:
        contract["comparison"] = comparison
    if q_csr_reuse is not None:
        contract["q_csr_reuse"] = q_csr_reuse
    if not _write_json_no_replace(contract_path, contract):
        raise Task41ContractError("a Task41 contract was concurrently created for this source SHA")
    contract_sha = sha256_file(contract_path)
    return {
        "case_id": case_id,
        "contract_path": str(contract_path.relative_to(root)),
        "contract_sha256": contract_sha,
        "window_path": str(window_path.relative_to(root)),
        "window_sha256": window_sha,
        "window_t0_utc": window_payload["t0_utc"],
        "window_entry_source_sha": window_payload["source_sha"],
        "contract_source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "a1_comparison_binding_sha256": (
            comparison["a1_binding_sha256"] if comparison is not None else None
        ),
        "same_discrete_comparison_ready": (
            comparison["same_discrete_comparison_ready"] if comparison is not None else None
        ),
        "service_command": [
            "bash",
            "scripts/run_case_in_user_service.sh",
            str(case_spec["input_relative"]),
            "--task41-p0-execution-contract",
            str(contract_path.relative_to(root)),
        ],
    }


def validate_task41_specification(
    specification: Any, input_path: str | Path, contract: Mapping[str, Any],
    *, current_root: str | Path | None = None,
) -> None:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case = contract["case"]
    actual_input = Path(input_path).resolve()
    expected_input = _resolve(root, case["input_path"], "case.input_path")
    from src.io.execution_plan import resolved_config_bytes

    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    if (
        actual_input != expected_input
        or sha256_file(actual_input) != case["input_sha256"]
        or specification.identity.get("model_id") != case["model_id"]
        or specification.identity.get("run_id") != case["run_id"]
        or specification.method.get("kind") != case["method"]
        or specification.execution.get("mpi_size") != case["mpi_size"]
        or specification.physical_model_sha256 != case["physical_model_sha256"]
        or resolved_sha != case["resolved_config_sha256"]
    ):
        raise Task41ContractError("resolved Task41 input differs from the frozen P0 contract")


def launcher_values(contract_path: str | Path, *, current_root: str | Path | None = None) -> list[str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract, digest = require_task41_p0_contract(
        contract_path, current_root=root, check_current_source=True, require_clean_source=True
    )
    window = load_task41_p0_fixed_window(contract, current_root=root, require_current_boot=True)
    runtime = contract["runtime"]
    resources = contract["resources"]
    case = contract["case"]
    return [
        str(root),
        str(_resolve(root, runtime["runtime_prefix"], "runtime_prefix")),
        str(_resolve(root, runtime["abi_receipt_path"], "abi_receipt_path")),
        str(_resolve(root, runtime["jit_cache"], "jit_cache")),
        digest,
        str(window.path),
        window.sha256,
        str(resources["task_memory_max_bytes"]),
        str(resources["host_reserve_bytes"]),
        str(resources["memory_swap_max_bytes"]),
        str(_resolve(root, case["input_path"], "case.input_path")),
        str(contract["source"]["sha"]),
    ]


def qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    if environment.get("TASK41_P0_STRICT_EXECUTION") != "1":
        return None
    root = Path(__file__).resolve().parents[2]
    contract_path = environment.get("TASK41_P0_CONTRACT_PATH")
    contract_sha = environment.get("TASK41_P0_CONTRACT_SHA256")
    try:
        contract, digest = require_task41_p0_contract(
            contract_path or "",
            expected_sha256=contract_sha,
            current_root=root,
            check_current_source=True,
            require_clean_source=True,
        )
        runtime = _resolve(root, contract["runtime"]["runtime_prefix"], "runtime_prefix")
        if (
            digest != contract_sha
            or environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1"
            or environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != "native_linux"
            or environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
            != contract["runtime"]["abi_receipt_sha256"]
            or not Path(sys.executable).resolve().is_relative_to(runtime)
            or environment.get("TASK41_P0_EXPECTED_SOURCE_SHA")
            != contract["source"]["sha"]
        ):
            return None
        return f"task41_p0_native_complex:{contract['runtime']['abi_receipt_sha256']}"
    except (OSError, ValueError, RuntimeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--launcher-values", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--runtime-prefix", type=Path)
    parser.add_argument("--abi-receipt", type=Path)
    parser.add_argument("--jit-cache", type=Path)
    parser.add_argument("--case", choices=("A1", "A2"), default="A1")
    parser.add_argument("--a2-q-csr-manifest", action="append", type=Path)
    args = parser.parse_args(argv)
    if args.launcher_values:
        if args.contract is None:
            parser.error("--launcher-values requires --contract")
        for value in launcher_values(args.contract):
            print(value)
        return 0
    if args.prepare:
        missing = [
            name
            for name in ("runtime_prefix", "abi_receipt", "jit_cache")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error("--prepare requires --runtime-prefix, --abi-receipt, and --jit-cache")
        result = prepare_task41_p0(
            runtime_prefix=args.runtime_prefix,
            abi_receipt=args.abi_receipt,
            jit_cache=args.jit_cache,
            case_id=args.case,
            a2_q_csr_manifests=args.a2_q_csr_manifest,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
