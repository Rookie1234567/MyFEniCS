"""Independent raw checker for the V18 fixed restart-64 qualification.

Only JSON, NumPy arrays, cache files, and the recorded process timeline are
read here.  The checker does not import the runner, solver, PETSc, MPI, or
DOLFINx; numerical and resource Gate failures remain valid evidence when the
raw contract is intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
MODE_MANIFEST_SHA256 = (
    "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
)
CHECKPOINT_MANIFEST_SHA256 = (
    "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139"
)
CHECKPOINT_SOLUTION_SHA256 = (
    "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
)
CHECKPOINT_SOURCE_SHA = "ee5920b9fa977a39fea7bc09cfbe155303acdb2d"
CHECKPOINT_INPUT_IDENTITY_SHA256 = (
    "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
)
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = (
    "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
)
CHECKPOINT_EXPLICIT_RESIDUAL = 0.4837947981092168

JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "checkpoint_restored",
    "qualifier_complete",
    "screen_complete",
    "continuation_complete",
    "record_written",
    "release_complete",
)
MARKER_ENDPOINTS = (
    (*MARKER_ORDER[:5], "record_written", "release_complete"),
    (*MARKER_ORDER[:6], "record_written", "release_complete"),
    MARKER_ORDER,
)
RSS_WARNING = 1_800_000_000
RSS_HARD = 2_000_000_000
RSS_WATCHDOG = RSS_HARD
SWAP_HARD = 0
RESTART = 64
CHECKPOINT_INTERVAL = 256
SCREEN512_LIMIT = 0.25
SCREEN1024_LIMIT = 0.10
SCREEN_RATIO_LIMIT = 0.85
LONG_RESIDUAL_LIMIT = 1.0e-6
RESOURCE_STOP_REASONS = {"process_tree_rss_watchdog", "process_tree_swap"}
WORKER_SCHEMA = "task038.v18.restart64.worker.v1"
PARENT_SCHEMA = "task038.v18.restart64.parent.v1"


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _array_sha(values: np.ndarray) -> str:
    return hashlib.sha256(
        memoryview(np.ascontiguousarray(values)).cast("B")
    ).hexdigest()


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gates: list[str], message: str) -> None:
    gates.append(message)


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _load_array(
    root: Path,
    descriptor: Any,
    errors: list[str],
    gates: list[str],
    label: str,
) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        _error(errors, f"provenance:{label} descriptor missing")
        return None
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        _error(errors, f"provenance:{label} relative path missing")
        return None
    path = (root / relative).resolve()
    if not _inside(root.resolve(), path) or not path.is_file():
        _error(errors, f"provenance:{label} array path missing or escapes root")
        return None
    if not _integer(descriptor.get("bytes")) or path.stat().st_size != descriptor["bytes"]:
        _error(errors, f"provenance:{label} byte count mismatch")
    if descriptor.get("sha256") != _sha256(path):
        _error(errors, f"provenance:{label} file SHA mismatch")
    try:
        values = np.asarray(np.load(path, allow_pickle=False))
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"provenance:{label} array cannot be read: {exc}")
        return None
    if (
        descriptor.get("dtype") != "complex128"
        or values.dtype != np.dtype(np.complex128)
        or values.ndim != 1
        or list(values.shape) != descriptor.get("shape")
    ):
        _error(errors, f"schema:{label} dtype or shape mismatch")
    if not np.all(np.isfinite(values)):
        _gate(gates, f"numerical:{label} nonfinite")
    if descriptor.get("array_sha256") != _array_sha(values):
        _error(errors, f"provenance:{label} array SHA mismatch")
    return values


def _cache_snapshot(cache: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if cache.is_dir():
        for base, _directories, files in __import__("os").walk(cache, followlinks=False):
            for filename in files:
                path = Path(base) / filename
                if path.suffix not in {".c", ".o", ".so"} or not path.is_file():
                    continue
                artifacts.append(
                    {
                        "relative_path": path.relative_to(cache).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )
    artifacts.sort(key=lambda item: item["relative_path"])
    manifest = {
        "cache_dir": str(cache.resolve()),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return {"artifact_count": len(artifacts), "manifest_sha256": digest}


def _source(source: Any, expected_sha: str, errors: list[str], label: str) -> None:
    if not isinstance(source, dict):
        _error(errors, f"schema:{label} source is missing")
        return
    expected = {
        "commit_sha": expected_sha,
        "branch": BRANCH,
        "input_sha256": INPUT_SHA256,
        "template_sha256": INPUT_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
    }
    for key, value in expected.items():
        if source.get(key) != value:
            _error(errors, f"provenance:{label}.{key} mismatch")


def _check_process(root: Path, parent: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    paths = parent.get("paths")
    if not isinstance(paths, dict) or not isinstance(paths.get("process_samples"), str):
        _error(errors, "schema:parent process path missing")
        return {}
    timeline = root / paths["process_samples"]
    if not timeline.is_file():
        _error(errors, "provenance:parent process timeline missing")
        return {}
    samples: list[dict[str, Any]] = []
    try:
        with timeline.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    item = _load_json_from_text(line)
                    if not isinstance(item, dict):
                        raise ValueError("process sample is not an object")
                    samples.append(item)
    except (OSError, ValueError) as exc:
        _error(errors, f"lifecycle:process timeline is invalid: {exc}")
        return {}
    if not samples:
        _error(errors, "lifecycle:process timeline is empty")
        return {}
    peak = 0
    swap = 0
    all_readable = True
    stage_names: list[str] = []
    resource_stop = any(
        isinstance(item, dict)
        and item.get("stop_reason") in RESOURCE_STOP_REASONS
        for item in (*parent.get("children", ()), parent.get("worker"))
    )
    for index, sample in enumerate(samples):
        stage = sample.get("stage")
        if not isinstance(stage, str):
            _error(errors, f"schema:process sample {index} stage missing")
        elif not stage_names or stage_names[-1] != stage:
            stage_names.append(stage)
        rss = sample.get("rss_bytes")
        sample_swap = sample.get("swap_bytes")
        readable = sample.get("all_status_readable")
        race = sample.get("process_tree_exit_race_observed")
        observed = sample.get("worker_exit_code_observed_after_sample")
        valid_race = (
            readable is False
            and race is True
            and _integer(observed)
            and observed == 0
            and rss is None
            and sample_swap is None
        )
        if rss is None or sample_swap is None:
            if not valid_race:
                _error(errors, f"lifecycle:process sample {index} terminal race is invalid")
        else:
            if not _integer(rss) or rss < 0 or not _integer(sample_swap) or sample_swap < 0:
                _error(errors, f"schema:process sample {index} RSS/swap is invalid")
            if readable is not True or race is True or observed is not None:
                _error(errors, f"lifecycle:process sample {index} readability race is invalid")
            peak = max(peak, int(rss))
            swap = max(swap, int(sample_swap))
        compiler_count = sample.get("compiler_descendant_count")
        if not _integer(compiler_count) or compiler_count < 0:
            _error(errors, f"schema:process sample {index} compiler count is invalid")
        if stage == "worker" and _integer(compiler_count) and compiler_count != 0:
            _error(errors, "lifecycle:worker has compiler descendants")
        all_readable = all_readable and (readable is True or valid_race)
    expected_stages = [f"precompile:{group}" for group in JIT_GROUPS] + ["worker"]
    if stage_names != expected_stages and not (
        resource_stop and stage_names == expected_stages[: len(stage_names)]
    ):
        _error(errors, "lifecycle:process stage order mismatch")
    if peak >= RSS_HARD:
        _gate(gates, "resource:parent process RSS >= 2000000000")
    if swap != SWAP_HARD:
        _gate(gates, "resource:parent process swap != 0")
    process = parent.get("process")
    recomputed = {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": all_readable,
    }
    if not isinstance(process, dict) or process != recomputed:
        _error(errors, "provenance:parent process summary does not match timeline")
    return recomputed


def _load_json_from_text(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _check_stage_result(result: Any, label: str, errors: list[str], gates: list[str]) -> None:
    if not isinstance(result, dict):
        _error(errors, f"schema:{label} result missing")
        return
    if not _integer(result.get("returncode")):
        _error(errors, f"schema:{label}.returncode invalid")
    for key in ("sample_count", "peak_rss_bytes", "max_swap_bytes"):
        if not _integer(result.get(key)) or result[key] < 0:
            _error(errors, f"schema:{label}.{key} invalid")
    if result.get("rss_watchdog_bytes") != RSS_WATCHDOG:
        _error(errors, f"provenance:{label} watchdog mismatch")
    resource_stop = result.get("stop_reason") in RESOURCE_STOP_REASONS
    if result.get("stop_reason") is not None:
        if resource_stop:
            _gate(gates, f"resource:{label}.{result['stop_reason']}")
        else:
            _error(errors, f"lifecycle:{label} stopped unexpectedly")
    if result.get("returncode") != 0 and not resource_stop:
        _error(errors, f"lifecycle:{label} returncode is nonzero")
    if result.get("process_group_gone") is not True or result.get("lifecycle_failure") is not False:
        _error(errors, f"lifecycle:{label} process group is not gone")
    if result.get("all_status_readable") is not True and not resource_stop:
        _error(errors, f"lifecycle:{label} process readability failed")
    if result.get("max_swap_bytes") != 0:
        _gate(gates, f"resource:{label} swap != 0")
    if result.get("peak_rss_bytes", 0) >= RSS_HARD:
        _gate(gates, f"resource:{label} RSS >= 2000000000")


def _check_parent(root: Path, parent: dict[str, Any], expected_sha: str, errors: list[str], gates: list[str]) -> dict[str, Any]:
    if parent.get("schema") != PARENT_SCHEMA:
        _error(errors, "schema:parent schema mismatch")
    if parent.get("phase") != "restart64" or parent.get("workflow") != "task038-v18-restart64-physical-krylov":
        _error(errors, "schema:parent workflow mismatch")
    _source(parent.get("source"), expected_sha, errors, "parent.source")
    contract = parent.get("resource_contract")
    expected_contract = {
        "warning_bytes": RSS_WARNING,
        "rss_watchdog_bytes": RSS_WATCHDOG,
        "rss_hard_gate_bytes": RSS_HARD,
        "swap_hard_gate_bytes": SWAP_HARD,
    }
    if not isinstance(contract, dict) or any(contract.get(key) != value for key, value in expected_contract.items()):
        _error(errors, "provenance:parent resource contract mismatch")
    if parent.get("expected_mpi_size") != 1:
        _error(errors, "schema:parent MPI size mismatch")
    _check_process(root, parent, errors, gates)
    children = parent.get("children")
    child_rows = children if isinstance(children, list) else []
    resource_stop = any(
        isinstance(item, dict)
        and item.get("stop_reason") in RESOURCE_STOP_REASONS
        for item in (*child_rows, parent.get("worker"))
    )
    if not isinstance(children, list) or len(children) > len(JIT_GROUPS) or (
        len(children) != len(JIT_GROUPS) and not resource_stop
    ):
        _error(errors, "schema:seven JIT children are not present")
    else:
        if parent.get("jit_groups") != list(JIT_GROUPS):
            _error(errors, "schema:JIT group order mismatch")
        for index, child in enumerate(children):
            label = f"child[{index}]"
            _check_stage_result(child, label, errors, gates)
            if not isinstance(child, dict) or child.get("group") != JIT_GROUPS[index]:
                _error(errors, f"lifecycle:{label} group order mismatch")
            if not (
                isinstance(child, dict)
                and child.get("stop_reason") in RESOURCE_STOP_REASONS
            ):
                _check_record_hash(root, child, errors, label)
    worker = parent.get("worker")
    if isinstance(worker, dict) or not resource_stop:
        _check_stage_result(worker, "worker", errors, gates)
    worker_resource_stop = isinstance(worker, dict) and worker.get("stop_reason") in RESOURCE_STOP_REASONS
    if not worker_resource_stop:
        _check_record_hash(root, worker, errors, "worker")
    cache = parent.get("cache")
    if not isinstance(cache, dict):
        _error(errors, "schema:parent cache facts missing")
    else:
        initial = cache.get("initial")
        before = cache.get("before_worker")
        after = cache.get("after_worker")
        if not isinstance(initial, dict) or initial.get("artifact_count") != 0:
            _error(errors, "resource:initial JIT cache is not empty")
        if not resource_stop and (before is None or after is None or before != after):
            _error(errors, "provenance:worker cache changed")
        cache_path = root / "jit_cache"
        if after is not None and after != _cache_snapshot(cache_path):
            _error(errors, "provenance:current JIT cache does not match record")
    markers = parent.get("markers")
    paths = parent.get("paths")
    if not isinstance(paths, dict) or not isinstance(markers, dict):
        _error(errors, "schema:marker manifest facts missing")
    else:
        marker_path = paths.get("marker_manifest")
        if not isinstance(marker_path, str) and not resource_stop:
            _error(errors, "provenance:marker manifest path missing")
        elif isinstance(marker_path, str):
            manifest_path = (root / marker_path).resolve()
            if not _inside(root.resolve(), manifest_path) or not manifest_path.is_file():
                _error(errors, "provenance:marker manifest missing")
            else:
                if markers.get("sha256") != _sha256(manifest_path):
                    _error(errors, "provenance:marker manifest SHA mismatch")
                try:
                    rows = _load_json(manifest_path)
                except (OSError, ValueError) as exc:
                    _error(errors, f"schema:marker manifest unreadable: {exc}")
                    rows = None
                names = [row.get("name") for row in rows] if isinstance(rows, list) else []
                expected_names = _expected_marker_names(root)
                allowed_names = [list(item) for item in MARKER_ENDPOINTS]
                if resource_stop:
                    allowed_names.extend(
                        list(MARKER_ORDER[:index])
                        for index in range(1, len(MARKER_ORDER) + 1)
                    )
                if names != expected_names or names not in allowed_names:
                    _error(errors, "lifecycle:marker order or completion mismatch")
                if markers.get("rows") != rows:
                    _error(errors, "provenance:parent marker rows mismatch")
    return {
        "worker": worker,
        "process": parent.get("process"),
        "resource_stop": resource_stop,
    }


def _check_record_hash(root: Path, record: Any, errors: list[str], label: str) -> None:
    if not isinstance(record, dict):
        return
    relative = record.get("record")
    if not isinstance(relative, str):
        _error(errors, f"provenance:{label} record path missing")
        return
    path = (root / relative).resolve()
    if not _inside(root.resolve(), path) or not path.is_file():
        _error(errors, f"provenance:{label} record missing")
    elif record.get("record_sha256") != _sha256(path):
        _error(errors, f"provenance:{label} record SHA mismatch")


def _expected_marker_names(root: Path) -> list[str]:
    marker_dir = root / "markers"
    if not marker_dir.is_dir():
        return []
    names = []
    for path in sorted(marker_dir.glob("*.json")):
        stem = path.stem
        if "_" in stem:
            names.append(stem.split("_", 1)[1])
    return names


def _check_checkpoint_facts(root: Path, facts: Any, errors: list[str], label: str) -> None:
    if not isinstance(facts, dict):
        _error(errors, f"schema:{label} checkpoint facts missing")
        return
    expected = {
        "iteration": 1000,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
        "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
    }
    for key, value in expected.items():
        if facts.get(key) != value:
            _error(errors, f"provenance:{label}.{key} mismatch")


def _check_same_start(root: Path, worker: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    same = worker.get("same_start")
    if not isinstance(same, dict):
        _error(errors, "schema:same_start facts missing")
        return {}
    rhs = same.get("rhs")
    initial = same.get("initial_solution")
    rhs_values = _load_array(
        root,
        rhs.get("descriptor") if isinstance(rhs, dict) else None,
        errors,
        gates,
        "same_start.rhs",
    )
    initial_values = _load_array(
        root,
        initial.get("descriptor") if isinstance(initial, dict) else None,
        errors,
        gates,
        "same_start.initial_solution",
    )
    for label, item, values in (("rhs", rhs, rhs_values), ("initial_solution", initial, initial_values)):
        if not isinstance(item, dict) or values is None:
            continue
        if item.get("array_sha256") != _array_sha(values):
            _error(errors, f"provenance:same_start.{label} top SHA mismatch")
    checks = (
        ("rhs_before_sha256", rhs.get("array_sha256") if isinstance(rhs, dict) else None),
        ("rhs_after_sha256", rhs.get("array_sha256") if isinstance(rhs, dict) else None),
        ("initial_solution_before_sha256", initial.get("array_sha256") if isinstance(initial, dict) else None),
        ("initial_solution_after_sha256", initial.get("array_sha256") if isinstance(initial, dict) else None),
    )
    for key, expected in checks:
        if same.get(key) != expected:
            _error(errors, f"provenance:same_start.{key} mismatch")
    if same.get("input_unchanged") is not True or same.get("finite") is not True:
        _gate(gates, "numerical:same_start input/finite")
    first = same.get("initial_true_residual")
    if not _finite(first):
        _gate(gates, "numerical:same_start initial residual")
    elif worker.get("screen") is None:
        if same.get("screen_initial_true_residual") is not None:
            _error(errors, "provenance:same_start unexpected screen residual")
    else:
        second = same.get("screen_initial_true_residual")
        if not _finite(second) or first != second:
            _gate(gates, "numerical:same_start initial residual")
    return {"rhs": rhs_values, "initial_solution": initial_values}


def _check_facts(
    facts: Any,
    label: str,
    errors: list[str],
    gates: list[str],
    *,
    require_slave: bool = True,
) -> None:
    if not isinstance(facts, dict):
        _error(errors, f"schema:{label} facts missing")
        return
    if facts.get("finite") is not True:
        _gate(gates, f"numerical:{label}.finite")
    if require_slave and (
        facts.get("owned_slave_max") != 0.0
        or facts.get("owned_slave_count") != 0
    ):
        _gate(gates, f"numerical:{label}.owned_slave")


def _check_probe(
    probe: Any,
    label: str,
    errors: list[str],
    gates: list[str],
    facts_key: str,
) -> None:
    if not isinstance(probe, dict):
        _error(errors, f"schema:{label} probe missing")
        return
    if probe.get("finite") is not True or probe.get("repeat_relative") is None or not _finite(probe.get("repeat_relative")):
        _gate(gates, f"numerical:{label}.finite")
    elif float(probe["repeat_relative"]) > 1.0e-12:
        _gate(gates, f"numerical:{label}.repeat")
    if probe.get("input_before_sha256") != probe.get("input_after_sha256"):
        _gate(gates, f"numerical:{label}.input_unchanged")
    if "input_facts" in probe:
        _check_facts(probe.get("input_facts"), f"{label}.input_facts", errors, gates)
    _check_facts(probe.get(facts_key), f"{label}.{facts_key}", errors, gates)


def _check_stage(root: Path, stage: Any, label: str, expected_iterations: int | None, errors: list[str], gates: list[str]) -> dict[str, Any]:
    if not isinstance(stage, dict):
        _error(errors, f"schema:{label} stage missing")
        return {}
    settings = stage.get("settings")
    expected_settings = {
        "ksp_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": RESTART,
        "cycle_max_it": RESTART,
        "start_iteration": 0,
        "residual_replacement": True,
        "checkpoint_interval": CHECKPOINT_INTERVAL,
        "additional_iteration_origin": 0,
        "absolute_iteration_origin": 1000,
    }
    if not isinstance(settings, dict) or any(settings.get(key) != value for key, value in expected_settings.items()):
        _error(errors, f"schema:{label} solver settings mismatch")
    base_offset = stage.get("base_offset")
    if not _integer(base_offset) or base_offset < 0:
        _error(errors, f"schema:{label} base offset invalid")
        base_offset = 0
    iterations = stage.get("additional_iterations")
    if not _integer(iterations) or iterations <= 0 or iterations % RESTART != 0:
        _error(errors, f"schema:{label} additional iteration count invalid")
        iterations = 0
    if expected_iterations is not None and iterations != expected_iterations:
        _error(errors, f"schema:{label} fixed iteration count mismatch")
    if expected_iterations is None and iterations > 9216:
        _error(errors, f"schema:{label} continuation exceeds fixed cap")
    cycles = stage.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != iterations // RESTART:
        _error(errors, f"schema:{label} cycle count mismatch")
        cycles = []
    sums = {"iterations": 0, "matvec_count": 0, "pc_apply_count": 0}
    previous = 0
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, dict):
            _error(errors, f"schema:{label}.cycle[{index}] missing")
            continue
        start = cycle.get("start_iteration")
        end = cycle.get("end_iteration")
        if start != previous or end != start + RESTART or cycle.get("iterations") != RESTART:
            _error(errors, f"lifecycle:{label}.cycle[{index}] boundary mismatch")
        previous = end if _integer(end) else previous
        additional_end = int(base_offset) + int(end)
        if cycle.get("additional_iteration") != additional_end or cycle.get("absolute_iteration") != 1000 + additional_end:
            _error(errors, f"provenance:{label}.cycle[{index}] iteration identity mismatch")
        for key in ("matvec_count", "pc_apply_count"):
            if not _integer(cycle.get(key)) or cycle[key] < 0:
                _error(errors, f"schema:{label}.cycle[{index}] {key} invalid")
            else:
                sums[key] += cycle[key]
        sums["iterations"] += RESTART
        if cycle.get("ksp_destroyed") is not True:
            _error(errors, f"lifecycle:{label}.cycle[{index}] KSP not destroyed")
        if not _finite(cycle.get("explicit_true_residual")):
            _gate(gates, f"numerical:{label}.cycle[{index}] residual")
        resource = cycle.get("resource")
        if not isinstance(resource, dict):
            _error(errors, f"schema:{label}.cycle[{index}] resource sample missing")
        else:
            process_tree = resource.get("process_tree")
            rss = process_tree.get("rss_bytes") if isinstance(process_tree, dict) else None
            swap = process_tree.get("swap_bytes") if isinstance(process_tree, dict) else None
            if not _integer(rss) or rss < 0 or not _integer(swap) or swap < 0:
                _error(errors, f"schema:{label}.cycle[{index}] resource RSS/swap invalid")
            else:
                if rss >= RSS_HARD:
                    _gate(gates, f"resource:{label}.cycle[{index}].rss")
                if swap != SWAP_HARD:
                    _gate(gates, f"resource:{label}.cycle[{index}].swap")
    for key in ("iterations", "matvec_count", "pc_apply_count"):
        stage_key = "additional_iterations" if key == "iterations" else key
        if stage.get(stage_key) != sums[key]:
            _error(errors, f"provenance:{label}.{key} ledger mismatch")
    if stage.get("explicit_action_count") != len(cycles) + 1 or stage.get("ksp_destroy_count") != len(cycles):
        _error(errors, f"provenance:{label} explicit/KSP count mismatch")
    if cycles and stage.get("final_true_residual") != cycles[-1].get("explicit_true_residual"):
        _error(errors, f"provenance:{label} final residual is not last cycle residual")
    if cycles and stage.get("absolute_end_iteration") != 1000 + int(base_offset) + int(cycles[-1]["end_iteration"]):
        _error(errors, f"provenance:{label} absolute end mismatch")
    expected_checkpoints = [
        int(base_offset) + local_iteration
        for local_iteration in range(CHECKPOINT_INTERVAL, iterations + 1, CHECKPOINT_INTERVAL)
    ]
    checkpoint_facts = stage.get("checkpoint_facts")
    if not isinstance(checkpoint_facts, list) or [item.get("additional_iteration") for item in checkpoint_facts if isinstance(item, dict)] != expected_checkpoints:
        _error(errors, f"lifecycle:{label} solution checkpoint cadence mismatch")
    else:
        for index, item in enumerate(checkpoint_facts):
            if not isinstance(item, dict):
                continue
            if item.get("absolute_iteration") != 1000 + expected_checkpoints[index]:
                _error(errors, f"provenance:{label} checkpoint absolute iteration mismatch")
            manifest_relative = item.get("manifest_relative_path")
            if not isinstance(manifest_relative, str):
                _error(errors, f"provenance:{label} checkpoint manifest path missing")
            else:
                manifest_path = (root / manifest_relative).resolve()
                if not _inside(root.resolve(), manifest_path) or not manifest_path.is_file():
                    _error(errors, f"provenance:{label} checkpoint manifest missing")
                elif item.get("manifest_sha256") != _sha256(manifest_path):
                    _error(errors, f"provenance:{label} checkpoint manifest SHA mismatch")
    return {"rows": cycles, "base_offset": int(base_offset), "iterations": int(iterations)}


def _screen_metrics(screen: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    rows = {int(row["additional_iteration"]): row for row in screen.get("cycles", []) if isinstance(row, dict) and _integer(row.get("additional_iteration"))}
    values = {step: (float(rows[step]["explicit_true_residual"]) if step in rows and _finite(rows[step].get("explicit_true_residual")) else None) for step in (512, 768, 1024)}
    failures: list[str] = []
    if values[512] is None or values[512] > SCREEN512_LIMIT:
        failures.append("step512")
    if values[1024] is None or values[1024] > SCREEN1024_LIMIT:
        failures.append("step1024")
    ratio = None if values[768] is None or values[1024] is None else values[1024] / max(abs(values[768]), np.finfo(float).tiny)
    if ratio is None or not math.isfinite(ratio) or ratio > SCREEN_RATIO_LIMIT:
        failures.append("r1024_over_r768")
    if any(
        isinstance(row, dict)
        and isinstance(row.get("resource"), dict)
        and isinstance(row["resource"].get("process_tree"), dict)
        and isinstance(row["resource"]["process_tree"].get("rss_bytes"), int)
        and row["resource"]["process_tree"]["rss_bytes"] >= RSS_HARD
        for row in screen.get("cycles", ())
    ):
        failures.append("resource_rss")
    if any(
        isinstance(row, dict)
        and isinstance(row.get("resource"), dict)
        and isinstance(row["resource"].get("process_tree"), dict)
        and isinstance(row["resource"]["process_tree"].get("swap_bytes"), int)
        and row["resource"]["process_tree"]["swap_bytes"] != SWAP_HARD
        for row in screen.get("cycles", ())
    ):
        failures.append("resource_swap")
    recomputed = {
        "step512": {"value": values[512], "limit": SCREEN512_LIMIT},
        "step1024": {"value": values[1024], "limit": SCREEN1024_LIMIT},
        "r1024_over_r768": {"value": ratio, "limit": SCREEN_RATIO_LIMIT},
        "gate_failures": failures,
        "passed": not failures,
    }
    if screen.get("gates") != recomputed:
        _error(errors, "provenance:screen Gate facts do not match raw cycles")
    return recomputed


def _check_worker(
    root: Path,
    worker: dict[str, Any],
    expected_sha: str,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    if (
        worker.get("schema") != WORKER_SCHEMA
        or worker.get("phase") != "restart64"
        or worker.get("stage") != "worker"
    ):
        _error(errors, "schema:worker identity mismatch")
    _source(worker.get("source"), expected_sha, errors, "worker.source")
    input_facts = worker.get("input")
    if (
        not isinstance(input_facts, dict)
        or input_facts.get("template_sha256") != INPUT_SHA256
        or input_facts.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256
    ):
        _error(errors, "provenance:worker input identity mismatch")
    _check_checkpoint_facts(root, worker.get("checkpoint"), errors, "worker")
    gate_start = len(gates)
    _check_same_start(root, worker, errors, gates)
    high_space = worker.get("high_space_primal")
    if (
        not isinstance(high_space, dict)
        or high_space.get("role") != "upper_cycle_pc_correction"
    ):
        _error(errors, "provenance:high_space_primal is not the PC correction")
    _check_facts(high_space, "high_space_primal", errors, gates)
    probes = worker.get("probes")
    if not isinstance(probes, dict):
        _error(errors, "schema:worker probes missing")
    else:
        _check_probe(
            probes.get("action"), "probe.action", errors, gates, "dual_facts"
        )
        pc_probe = probes.get("pc")
        _check_probe(
            pc_probe, "probe.pc", errors, gates, "primal_facts"
        )
        if not isinstance(pc_probe, dict) or pc_probe.get("input_role") != "dual_residual":
            _error(errors, "provenance:probe.pc input is not the dual residual")
    _check_facts(worker.get("rhs"), "rhs", errors, gates, require_slave=False)
    architecture = worker.get("architecture")
    expected_architecture = {
        "p6_matrix_free": True,
        "global_physical_aij": False,
        "global_schur": False,
        "dense_dtn": False,
        "factor": False,
        "numeric_allgather": False,
        "phase_once": True,
        "restart": RESTART,
        "restart_basis_storage": "petsc_in_memory",
        "restart_basis_bound": "fixed_restart_64",
    }
    if not isinstance(architecture, dict) or any(
        architecture.get(key) != value
        for key, value in expected_architecture.items()
    ):
        _error(errors, "provenance:worker architecture contract mismatch")
    qualifier = _check_stage(
        root, worker.get("qualifier"), "qualifier", 64, errors, gates
    )
    qualifier_gate_failures = gates[gate_start:]
    gate_facts = worker.get("gates")
    recorded_qualifier = (
        gate_facts.get("qualifier") if isinstance(gate_facts, dict) else None
    )
    if not isinstance(recorded_qualifier, dict):
        _error(errors, "provenance:qualifier Gate facts missing")
    else:
        recorded_failures = recorded_qualifier.get("gate_failures")
        if not isinstance(recorded_failures, list) or bool(recorded_failures) != bool(
            qualifier_gate_failures
        ):
            _error(errors, "provenance:qualifier Gate facts mismatch")
        if recorded_qualifier.get("passed") is not (not qualifier_gate_failures):
            _error(errors, "provenance:qualifier Gate status mismatch")

    if qualifier_gate_failures:
        if worker.get("screen") is not None or worker.get("continuation") is not None:
            _error(errors, "lifecycle:qualifier failed but later stage was run")
        if _expected_marker_names(root) != list(MARKER_ENDPOINTS[0]):
            _error(errors, "lifecycle:qualifier-stop marker endpoint mismatch")
        return {
            "qualifier": qualifier,
            "screen": {},
            "screen_gates": {"status": "not_run_qualifier_gate_failed"},
            "continuation": {},
        }

    screen_value = worker.get("screen")
    if not isinstance(screen_value, dict):
        _error(errors, "schema:screen stage missing after qualifier")
        return {
            "qualifier": qualifier,
            "screen": {},
            "screen_gates": {},
            "continuation": {},
        }
    screen_gate_start = len(gates)
    screen = _check_stage(root, screen_value, "screen", 1024, errors, gates)
    screen_metrics = _screen_metrics(screen_value, errors)
    for failure in screen_metrics["gate_failures"]:
        prefix = "resource" if failure.startswith("resource_") else "numerical"
        _gate(gates, f"{prefix}:screen.{failure}")
    recorded_screen = gate_facts.get("screen") if isinstance(gate_facts, dict) else None
    if recorded_screen != screen_metrics:
        _error(errors, "provenance:screen Gate facts mismatch")
    screen_gate_failures = gates[screen_gate_start:]
    continuation = worker.get("continuation")
    if screen_gate_failures or not screen_metrics["passed"]:
        if continuation is not None:
            _error(errors, "lifecycle:screen failed but continuation was run")
        if _expected_marker_names(root) != list(MARKER_ENDPOINTS[1]):
            _error(errors, "lifecycle:screen-stop marker endpoint mismatch")
        return {
            "qualifier": qualifier,
            "screen": screen,
            "screen_gates": screen_metrics,
            "continuation": {},
        }

    if not isinstance(continuation, dict):
        _error(errors, "lifecycle:screen passed but continuation is missing")
        continuation_facts: dict[str, Any] = {}
    else:
        continuation_facts = _check_stage(
            root, continuation, "continuation", None, errors, gates
        )
        gate = continuation.get("gate")
        if (
            not isinstance(gate, dict)
            or gate.get("final_true_residual") != continuation.get("final_true_residual")
            or gate.get("limit") != LONG_RESIDUAL_LIMIT
        ):
            _error(errors, "provenance:continuation Gate facts mismatch")
        elif not _finite(gate.get("final_true_residual")) or gate.get(
            "final_true_residual"
        ) > LONG_RESIDUAL_LIMIT:
            _gate(gates, "numerical:continuation.final_true_residual")
    if _expected_marker_names(root) != list(MARKER_ENDPOINTS[2]):
        _error(errors, "lifecycle:full marker endpoint mismatch")
    return {
        "qualifier": qualifier,
        "screen": screen,
        "screen_gates": screen_metrics,
        "continuation": continuation_facts,
    }


def _classification(errors: list[str], gates: list[str]) -> str:
    if errors:
        return "INFRASTRUCTURE_FAILURE_RETRYABLE"
    if any(item.startswith("resource:") for item in gates):
        return "V18_RESTART64_RESOURCE_GATE_FAIL"
    if gates:
        return "V18_RESTART64_NUMERICAL_GATE_FAIL"
    return "V18_RESTART64_PHYSICAL_KRYLOV_PASS"


def check_artifact(record_path: str | Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record_path = Path(record_path).resolve()
    metrics: dict[str, Any] = {}
    try:
        parent = _load_json(record_path)
        if not isinstance(parent, dict):
            raise ValueError("parent record is not an object")
        context = _check_parent(record_path.parent, parent, expected_source_sha, errors, gates)
        worker = context.get("worker")
        worker_path = None
        if isinstance(worker, dict) and isinstance(worker.get("record"), str):
            worker_path = (record_path.parent / worker["record"]).resolve()
        if context.get("resource_stop"):
            metrics = {"controlled_stop": True}
        elif worker_path is None or not worker_path.is_file():
            _error(errors, "provenance:worker record cannot be loaded")
        else:
            worker_record = _load_json(worker_path)
            if not isinstance(worker_record, dict):
                _error(errors, "schema:worker record is not an object")
            else:
                metrics = _check_worker(record_path.parent, worker_record, expected_source_sha, errors, gates)
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"infrastructure:raw checker boundary failed: {exc}")
    classification = _classification(errors, gates)
    return {
        "schema": "task038.v18.restart64.checker.v1",
        "status": "PASS" if not errors else "FAIL",
        "evidence_valid": not errors,
        "classification": classification,
        "errors": errors,
        "metrics": {**metrics, "gate_failures": gates},
        "record": str(record_path),
    }


def _write_output(path: Path, value: dict[str, Any]) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        import os

        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = check_artifact(args.record, args.expected_source_sha)
    _write_output(Path(args.output), result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
