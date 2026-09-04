"""Independent checker for the V18 eventual restart-64 lane.

The checker reads only the parent/worker JSON, NumPy descriptors, checkpoint
manifest, cache inventory, and process timeline.  It deliberately does not
import the runner, PETSc, MPI, or a solver, so a numerical negative remains
valid evidence while a damaged raw record is an infrastructure failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
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
    "267a933e1f85cd8685efcfc14a2fc8a50b352d6573a19e9781655c19d3f0be31"
)
CHECKPOINT_SOLUTION_SHA256 = (
    "5ab1ec46b588e1a1c38945ceaf5d41b61f066785ff08ccdd493735a01b45ee79"
)
CHECKPOINT_SOURCE_SHA = "a20008734c8bf0df03890bf35576c697eb0967f0"
CHECKPOINT_INPUT_IDENTITY_SHA256 = (
    "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
)
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = (
    "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
)
CHECKPOINT_EXPLICIT_RESIDUAL = 0.27299642739429014
CHECKPOINT_RELATIVE_LIMIT = 1.0e-11
RESIDUAL_LIMIT = 1.0e-6
RESTART = 64
ABSOLUTE_ORIGIN = 1000
E1_BASE_OFFSET = 1024
E1_MAX_STEPS = 31744
E2_MAX_STEPS = 32768
CHECKPOINT_INTERVAL = 1024
STAGNATION_BLOCK_SIZE = 4096
STAGNATION_RATIO_LIMIT = 0.95
DIVERGED_ITS = -3
RSS_HARD = 2_000_000_000
SWAP_HARD = 0
JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
PARENT_SCHEMA = "task038.v18.restart64.eventual.parent.v1"
WORKER_SCHEMA = "task038.v18.restart64.eventual.worker.v1"
CHECKER_SCHEMA = "task038.v18.restart64.eventual.checker.v1"
COMPLETION_SCHEMA = "task038.v18.restart64.eventual.completion.v1"
WORKFLOW = "task038-v18-restart64-eventual-physical"
MARKER_SCHEMA = "task038.v18.restart64.eventual.marker.v1"
MARKER_ORDER = {
    "e1": (
        "paths_ready",
        "abi_ready",
        "case_built",
        "checkpoint_restored",
        "e1_complete",
        "record_written",
        "release_complete",
    ),
    "e2": (
        "paths_ready",
        "abi_ready",
        "case_built",
        "e2_complete",
        "record_written",
        "release_complete",
    ),
}
REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_DIR = (
    REPO_ROOT
    / "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm"
    / "v18_restart64_physical_v1"
    / "a20008734c8bf0df03890bf35576c697eb0967f0"
    / "mpi1/raw/screen/solution_checkpoints/solution-2024"
)
CHECKPOINT_RELATIVE = str(CHECKPOINT_DIR.relative_to(REPO_ROOT))


def _reject_constant(value: str) -> Any:
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


def _load_json_line(line: str) -> Any:
    return json.loads(line, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _array_sha(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values)
    return hashlib.sha256(memoryview(values).cast("B")).hexdigest()


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gates: list[str], message: str) -> None:
    gates.append(message)


def _load_array(
    root: Path,
    descriptor: Any,
    label: str,
    errors: list[str],
    gates: list[str],
) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        _error(errors, f"schema:{label} descriptor missing")
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
        values.dtype != np.dtype(np.complex128)
        or descriptor.get("dtype") != "complex128"
        or values.ndim != 1
        or descriptor.get("shape") != [int(values.size)]
    ):
        _error(errors, f"schema:{label} dtype or shape mismatch")
    if descriptor.get("array_sha256") != _array_sha(values):
        _error(errors, f"provenance:{label} array SHA mismatch")
    if not np.all(np.isfinite(values)):
        _gate(gates, f"numerical:{label}.nonfinite")
    return values


def _cache_snapshot(cache: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if cache.is_dir():
        for base, _directories, files in os.walk(cache, followlinks=False):
            for filename in files:
                path = Path(base) / filename
                if path.suffix not in {".c", ".o", ".so"} or not path.is_file():
                    continue
                artifacts.append(
                    {
                        "relative_path": path.relative_to(cache).as_posix(),
                        "bytes": int(path.stat().st_size),
                        "sha256": _sha256(path),
                    }
                )
    artifacts.sort(key=lambda item: item["relative_path"])
    manifest = {
        "cache_dir": str(cache.resolve()),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"artifact_count": len(artifacts), "manifest_sha256": hashlib.sha256(encoded).hexdigest()}


def _source(source: Any, expected_sha: str, errors: list[str], label: str) -> None:
    if not isinstance(source, dict):
        _error(errors, f"schema:{label} source missing")
        return
    expected = {
        "commit_sha": expected_sha,
        "branch": BRANCH,
        "upstream": f"origin/{BRANCH}",
        "upstream_sha": expected_sha,
        "input_sha256": INPUT_SHA256,
        "template_sha256": INPUT_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
    }
    for key, value in expected.items():
        if source.get(key) != value:
            _error(errors, f"provenance:{label}.{key} mismatch")


def _check_process_result(result: Any, label: str, errors: list[str], gates: list[str]) -> bool:
    if not isinstance(result, dict):
        _error(errors, f"schema:{label} process result missing")
        return False
    if not _integer(result.get("returncode")):
        _error(errors, f"schema:{label}.returncode invalid")
    for key in ("sample_count", "peak_rss_bytes", "max_swap_bytes"):
        if not _integer(result.get(key)) or result[key] < 0:
            _error(errors, f"schema:{label}.{key} invalid")
    if result.get("rss_watchdog_bytes") != RSS_HARD:
        _error(errors, f"provenance:{label}.rss watchdog mismatch")
    resource_stop = result.get("stop_reason") in {"process_tree_rss_watchdog", "process_tree_swap"}
    if result.get("stop_reason") is not None and not resource_stop:
        _error(errors, f"lifecycle:{label} unexpected stop reason")
    if result.get("returncode") != 0 and not resource_stop:
        _error(errors, f"lifecycle:{label} nonzero returncode")
    if result.get("process_group_gone") is not True or result.get("lifecycle_failure") is not False:
        _error(errors, f"lifecycle:{label} process group did not close")
    if result.get("all_status_readable") is not True:
        _error(errors, f"lifecycle:{label} status was not readable")
    if result.get("max_swap_bytes") != SWAP_HARD:
        _gate(gates, f"resource:{label}.swap")
    if result.get("peak_rss_bytes", 0) >= RSS_HARD:
        _gate(gates, f"resource:{label}.rss")
    if resource_stop:
        _gate(gates, f"resource:{label}.{result['stop_reason']}")
    return resource_stop


def _check_record_hash(
    root: Path, result: Any, label: str, errors: list[str], *, allow_missing: bool = False
) -> bool:
    if not isinstance(result, dict):
        return False
    relative = result.get("record")
    if not isinstance(relative, str):
        if allow_missing and relative is None:
            return False
        _error(errors, f"provenance:{label} record path missing")
        return False
    path = (root / relative).resolve()
    if not _inside(root.resolve(), path):
        _error(errors, f"provenance:{label} record escapes root")
        return False
    if not path.is_file():
        if allow_missing:
            return False
        _error(errors, f"provenance:{label} record missing")
        return False
    if result.get("record_sha256") != _sha256(path):
        _error(errors, f"provenance:{label} record SHA mismatch")
        return False
    return True


def _effective_sample(sample: dict[str, Any]) -> bool:
    return sample.get("all_status_readable") is True or (
        sample.get("all_status_readable") is False
        and sample.get("process_tree_exit_race_observed") is True
        and sample.get("worker_exit_code_observed_after_sample") == 0
        and sample.get("rss_bytes") is None
        and sample.get("swap_bytes") is None
    )


def _check_process(root: Path, parent: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    relative = parent.get("paths", {}).get("process_samples") if isinstance(parent.get("paths"), dict) else None
    path = (root / relative).resolve() if isinstance(relative, str) else None
    if path is None or not _inside(root.resolve(), path) or not path.is_file():
        _error(errors, "provenance:parent process timeline missing")
        return {"sample_count": 0, "peak_rss_bytes": 0, "max_swap_bytes": 0, "all_status_readable": False}
    samples: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    item = _load_json_line(line)
                    if not isinstance(item, dict):
                        raise ValueError("process sample is not an object")
                    samples.append(item)
    except (OSError, ValueError) as exc:
        _error(errors, f"lifecycle:parent process timeline invalid: {exc}")
        return {"sample_count": 0, "peak_rss_bytes": 0, "max_swap_bytes": 0, "all_status_readable": False}
    if not samples:
        _error(errors, "lifecycle:parent process timeline empty")
    peak = 0
    swap = 0
    readable = True
    stage_names: list[str] = []
    for index, sample in enumerate(samples):
        stage = sample.get("stage")
        if not isinstance(stage, str):
            _error(errors, f"schema:process sample {index} stage missing")
        elif not stage_names or stage_names[-1] != stage:
            stage_names.append(stage)
        rss = sample.get("rss_bytes")
        sample_swap = sample.get("swap_bytes")
        if rss is None or sample_swap is None:
            if not _effective_sample(sample):
                _error(errors, f"lifecycle:process sample {index} unreadable")
        elif not _integer(rss) or rss < 0 or not _integer(sample_swap) or sample_swap < 0:
            _error(errors, f"schema:process sample {index} RSS/swap invalid")
        else:
            peak = max(peak, int(rss))
            swap = max(swap, int(sample_swap))
            if sample.get("all_status_readable") is not True:
                _error(errors, f"lifecycle:process sample {index} readability mismatch")
        compiler_count = sample.get("compiler_descendant_count")
        if not _integer(compiler_count) or compiler_count < 0:
            _error(errors, f"schema:process sample {index} compiler count invalid")
        elif stage == "worker" and compiler_count != 0:
            _error(errors, "lifecycle:worker compiler descendant remained")
        readable = readable and _effective_sample(sample)
    phase = str(parent.get("phase"))
    expected = [f"precompile:{group}" for group in JIT_GROUPS] + ["worker"]
    resource_stop = any(
        isinstance(item, dict)
        and item.get("stop_reason") in {"process_tree_rss_watchdog", "process_tree_swap"}
        for item in (*parent.get("children", ()), parent.get("worker"))
    )
    if stage_names != expected and not (resource_stop and stage_names == expected[: len(stage_names)]):
        _error(errors, f"lifecycle:{phase} process stage order mismatch")
    if peak >= RSS_HARD:
        _gate(gates, "resource:parent.rss")
    if swap != SWAP_HARD:
        _gate(gates, "resource:parent.swap")
    summary = {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": readable,
    }
    if parent.get("process") != summary:
        _error(errors, "provenance:parent process summary mismatch")
    return summary


def _check_completion(
    root: Path,
    parent: dict[str, Any],
    expected_source_sha: str,
    errors: list[str],
    gates: list[str],
) -> bool:
    paths = parent.get("paths")
    relative = paths.get("completion") if isinstance(paths, dict) else None
    if not isinstance(relative, str):
        return False
    completion_path = (root / relative).resolve()
    if not _inside(root.resolve(), completion_path) or not completion_path.is_file():
        return False
    try:
        completion = _load_json(completion_path)
    except (OSError, TypeError, ValueError) as exc:
        _error(errors, f"provenance:completion unreadable: {exc}")
        return False
    if not isinstance(completion, dict) or completion.get("schema") != COMPLETION_SCHEMA:
        _error(errors, "schema:completion identity mismatch")
        return False
    parent_path = root / "parent_record.json"
    if (
        completion.get("parent_record") != parent_path.name
        or completion.get("parent_record_sha256") != _sha256(parent_path)
    ):
        _error(errors, "provenance:completion parent binding mismatch")
    checker_relative = completion.get("checker")
    checker_path = (root / checker_relative).resolve() if isinstance(checker_relative, str) else None
    checker_exists = checker_path is not None and _inside(root.resolve(), checker_path) and checker_path.is_file()
    if not checker_exists:
        if completion.get("checker_process", {}).get("stop_reason") not in {"process_tree_rss_watchdog", "process_tree_swap"}:
            _error(errors, "provenance:completion checker output missing")
    elif completion.get("checker_sha256") != _sha256(checker_path):
        _error(errors, "provenance:completion checker SHA mismatch")
    checker_process = completion.get("checker_process")
    resource_stop = _check_process_result(
        checker_process, "checker", errors, gates
    )
    if completion.get("status") != ("FAIL" if resource_stop else "PASS"):
        _error(errors, "provenance:completion status mismatch")
    if checker_exists and not resource_stop:
        try:
            checker = _load_json(checker_path)
        except (OSError, TypeError, ValueError) as exc:
            _error(errors, f"provenance:completion checker unreadable: {exc}")
        else:
            if (
                not isinstance(checker, dict)
                or checker.get("schema") != CHECKER_SCHEMA
                or checker.get("record") != str(parent_path)
                or checker.get("record_sha256") != _sha256(parent_path)
                or checker.get("expected_source_sha") != expected_source_sha
                or checker.get("status") != "PASS"
                or checker.get("evidence_valid") is not True
            ):
                _error(errors, "provenance:completion checker authority mismatch")
    return resource_stop


def _check_checkpoint_authority(errors: list[str]) -> dict[str, Any] | None:
    manifest_path = CHECKPOINT_DIR / "manifest.json"
    if not manifest_path.is_file():
        _error(errors, "provenance:immutable checkpoint manifest is missing")
        return None
    if _sha256(manifest_path) != CHECKPOINT_MANIFEST_SHA256:
        _error(errors, "provenance:immutable checkpoint manifest SHA mismatch")
    try:
        manifest = _load_json(manifest_path)
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"provenance:immutable checkpoint unreadable: {exc}")
        return None
    expected = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 2024,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
    }
    if not isinstance(manifest, dict):
        _error(errors, "schema:immutable checkpoint manifest is not an object")
        return None
    for key, value in expected.items():
        if manifest.get(key) != value:
            _error(errors, f"provenance:immutable checkpoint {key} mismatch")
    if set(manifest.get("forbidden_vector_roles", ())) != {"action", "residual", "krylov_basis"}:
        _error(errors, "schema:immutable checkpoint forbidden vector roles mismatch")
    rank_facts = manifest.get("ranks")
    descriptor = (
        rank_facts[0].get("solution")
        if isinstance(rank_facts, list)
        and len(rank_facts) == 1
        and isinstance(rank_facts[0], dict)
        else None
    )
    relative = descriptor.get("relative_path") if isinstance(descriptor, dict) else None
    shard_path = (CHECKPOINT_DIR / relative).resolve() if isinstance(relative, str) else None
    if shard_path is None or not _inside(CHECKPOINT_DIR.resolve(), shard_path) or not shard_path.is_file():
        _error(errors, "provenance:immutable checkpoint solution shard is missing")
        return None
    try:
        values = np.asarray(np.load(shard_path, allow_pickle=False))
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"provenance:immutable checkpoint solution unreadable: {exc}")
        return None
    if values.dtype != np.dtype(np.complex128) or values.ndim != 1 or not np.all(np.isfinite(values)):
        _error(errors, "schema:immutable checkpoint solution array invalid")
    if _sha256(shard_path) != CHECKPOINT_SOLUTION_SHA256:
        _error(errors, "provenance:immutable checkpoint solution file SHA mismatch")
    if not isinstance(rank_facts, list) or len(rank_facts) != 1:
        _error(errors, "schema:immutable checkpoint rank facts invalid")
    else:
        ownership = rank_facts[0].get("ownership") if isinstance(rank_facts[0], dict) else None
        expected_ownership = {
            "rank": 0,
            "ownership_range": [0, int(values.size)],
            "local_size": int(values.size),
            "global_size": int(values.size),
        }
        if ownership != expected_ownership:
            _error(errors, "provenance:immutable checkpoint ownership mismatch")
        descriptor = rank_facts[0].get("solution") if isinstance(rank_facts[0], dict) else None
        if not isinstance(descriptor, dict):
            _error(errors, "schema:immutable checkpoint solution descriptor missing")
        else:
            if descriptor.get("sha256") != _sha256(shard_path):
                _error(errors, "provenance:immutable checkpoint solution SHA mismatch")
            if descriptor.get("bytes") != shard_path.stat().st_size:
                _error(errors, "provenance:immutable checkpoint solution bytes mismatch")
            if descriptor.get("dtype") != "complex128" or descriptor.get("shape") != [int(values.size)]:
                _error(errors, "schema:immutable checkpoint solution descriptor mismatch")
    return {
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
        "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
        "array_sha256": _array_sha(values),
    }


def _check_parent_e0_binding(
    root: Path, parent: dict[str, Any], phase: Any, errors: list[str]
) -> None:
    """Bind the parent E0 facts to the independently checked checkpoint."""

    paths = parent.get("paths")
    if not isinstance(paths, dict):
        _error(errors, "schema:parent paths missing for E0 binding")
        return
    if phase == "e2":
        if (
            paths.get("e0_checkpoint_preflight") is not None
            or paths.get("e0_checkpoint_preflight_sha256") is not None
            or parent.get("e0") is not None
        ):
            _error(errors, "provenance:e2 E0 fields must be null")
        return
    if phase != "e1":
        return
    relative = paths.get("e0_checkpoint_preflight")
    recorded_sha = paths.get("e0_checkpoint_preflight_sha256")
    if not isinstance(relative, str) or not isinstance(recorded_sha, str):
        _error(errors, "provenance:e1 E0 path or SHA missing")
        return
    e0_path = (root / relative).resolve()
    if not _inside(root.resolve(), e0_path) or not e0_path.is_file():
        _error(errors, "provenance:e1 E0 preflight file missing or escapes root")
        return
    actual_sha = _sha256(e0_path)
    if recorded_sha != actual_sha:
        _error(errors, "provenance:e1 E0 preflight SHA mismatch")
    try:
        e0 = _load_json(e0_path)
    except (OSError, TypeError, ValueError) as exc:
        _error(errors, f"provenance:e1 E0 preflight unreadable: {exc}")
        return
    if parent.get("e0") != e0:
        _error(errors, "provenance:e1 parent E0 facts mismatch")
    authority_errors: list[str] = []
    authority = _check_checkpoint_authority(authority_errors)
    for message in authority_errors:
        _error(errors, f"provenance:e1 checkpoint authority: {message}")
    if authority is None or authority_errors or not isinstance(e0, dict):
        return
    expected = {
        "relative_path": CHECKPOINT_RELATIVE,
        "manifest_relative_path": f"{CHECKPOINT_RELATIVE}/manifest.json",
        "manifest_sha256": authority["manifest_sha256"],
        "solution_sha256": authority["solution_sha256"],
        "dtype": "complex128",
        "shape": [173802],
        "finite": True,
        "ownership": {
            "rank": 0,
            "ownership_range": [0, 173802],
            "local_size": 173802,
            "global_size": 173802,
        },
        "valid": True,
        "errors": [],
    }
    for key, value in expected.items():
        if e0.get(key) != value:
            _error(errors, f"provenance:e1 E0 {key} mismatch")


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


def _relative_values(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right)) / max(float(np.linalg.norm(right)), np.finfo(float).tiny)


def _check_probe(
    root: Path,
    probe: Any,
    label: str,
    facts_key: str,
    errors: list[str],
    gates: list[str],
) -> None:
    if not isinstance(probe, dict):
        _error(errors, f"schema:{label} probe missing")
        return
    first = _load_array(root, probe.get("first"), f"{label}.first", errors, gates)
    second = _load_array(root, probe.get("second"), f"{label}.second", errors, gates)
    if first is not None and second is not None:
        repeat = _relative_values(first, second)
        if not _finite(probe.get("repeat_relative")) or not math.isclose(float(probe["repeat_relative"]), repeat, rel_tol=1.0e-12, abs_tol=1.0e-15):
            _error(errors, f"provenance:{label}.repeat mismatch")
        if repeat > 1.0e-12:
            _gate(gates, f"numerical:{label}.repeat")
    if probe.get("input_before_sha256") != probe.get("input_after_sha256"):
        _gate(gates, f"numerical:{label}.input_unchanged")
    _check_facts(probe.get(facts_key), f"{label}.{facts_key}", errors, gates)
    if label == "probe.pc":
        if probe.get("input_role") != "dual_residual":
            _error(errors, "provenance:probe.pc input role mismatch")
        _check_facts(probe.get("input_facts"), "probe.pc.input_facts", errors, gates)


def _stagnation_facts(initial: float, cycles: list[dict[str, Any]], base_offset: int) -> dict[str, Any]:
    previous = float(initial)
    boundary = STAGNATION_BLOCK_SIZE
    blocks: list[dict[str, Any]] = []
    for cycle in cycles:
        if cycle.get("end_iteration") != boundary:
            continue
        residual = cycle.get("explicit_true_residual")
        value = float(residual) if _finite(residual) else float("nan")
        q = value / max(abs(previous), np.finfo(float).tiny)
        blocks.append(
            {
                "start_iteration": boundary - STAGNATION_BLOCK_SIZE,
                "end_iteration": boundary,
                "start_residual": previous,
                "end_residual": value,
                "q": q,
                "complete": True,
                "finite": bool(math.isfinite(previous) and math.isfinite(value) and math.isfinite(q)),
                "start_additional_iteration": base_offset + boundary - STAGNATION_BLOCK_SIZE,
                "end_additional_iteration": base_offset + boundary,
                "start_absolute_iteration": ABSOLUTE_ORIGIN + base_offset + boundary - STAGNATION_BLOCK_SIZE,
                "end_absolute_iteration": ABSOLUTE_ORIGIN + base_offset + boundary,
            }
        )
        previous = value
        boundary += STAGNATION_BLOCK_SIZE
    return {
        "block_size": STAGNATION_BLOCK_SIZE,
        "ratio_limit": STAGNATION_RATIO_LIMIT,
        "blocks": blocks,
        "complete_block_count": len(blocks),
        "triggered": bool(len(blocks) >= 2 and all(item["finite"] and item["q"] >= STAGNATION_RATIO_LIMIT for item in blocks[-2:])),
        "base_offset": base_offset,
        "absolute_origin": ABSOLUTE_ORIGIN,
    }


def _check_stage(
    root: Path,
    stage: Any,
    phase: str,
    errors: list[str],
    gates: list[str],
) -> tuple[dict[str, Any], str]:
    if not isinstance(stage, dict):
        _error(errors, f"schema:{phase} stage missing")
        return {}, f"{phase.upper()}_NOT_RUN"
    base = stage.get("base_offset")
    expected_base = E1_BASE_OFFSET if phase == "e1" else 0
    expected_cap = E1_MAX_STEPS if phase == "e1" else E2_MAX_STEPS
    if base != expected_base:
        _error(errors, f"provenance:{phase} base offset mismatch")
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
        "absolute_iteration_origin": ABSOLUTE_ORIGIN,
        "stage_base_offset": expected_base,
    }
    if not isinstance(settings, dict) or any(settings.get(key) != value for key, value in expected_settings.items()):
        _error(errors, f"schema:{phase} solver settings mismatch")
    cycles = stage.get("cycles")
    if not isinstance(cycles, list):
        _error(errors, f"schema:{phase} cycles missing")
        cycles = []
    local_iterations = stage.get("local_iterations")
    if not _integer(local_iterations) or local_iterations < 0:
        _error(errors, f"schema:{phase} local iteration count invalid")
        local_iterations = 0
    if local_iterations > expected_cap:
        _error(errors, f"schema:{phase} local iteration cap exceeded")
    expected_cycle_count = 1 if local_iterations == 0 else (local_iterations + RESTART - 1) // RESTART
    if len(cycles) != expected_cycle_count:
        _error(errors, f"lifecycle:{phase} cycle count mismatch")
    sums = {"iterations": 0, "matvec_count": 0, "pc_apply_count": 0}
    previous = 0
    rss_values: list[int] = []
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, dict):
            _error(errors, f"schema:{phase}.cycle[{index}] missing")
            continue
        expected_iterations = (
            0 if local_iterations == 0 else min(RESTART, local_iterations - index * RESTART)
        )
        start = cycle.get("start_iteration")
        end = cycle.get("end_iteration")
        if (
            start != previous
            or end != start + expected_iterations
            or cycle.get("iterations") != expected_iterations
        ):
            _error(errors, f"lifecycle:{phase}.cycle[{index}] boundary mismatch")
        previous = end if _integer(end) else previous
        if cycle.get("additional_iteration") != base + (end if _integer(end) else -1) or cycle.get("absolute_iteration") != ABSOLUTE_ORIGIN + base + (end if _integer(end) else -1):
            _error(errors, f"provenance:{phase}.cycle[{index}] iteration identity mismatch")
        reason = cycle.get("reason")
        if not _integer(reason):
            _error(errors, f"schema:{phase}.cycle[{index}] reason invalid")
        elif reason < 0 and reason != DIVERGED_ITS and index != len(cycles) - 1:
            _error(errors, f"lifecycle:{phase}.cycle[{index}] nonfinal breakdown")
        elif expected_iterations < RESTART and reason == DIVERGED_ITS:
            _error(errors, f"lifecycle:{phase}.cycle[{index}] partial DIVERGED_ITS")
        for key in ("matvec_count", "pc_apply_count"):
            if not _integer(cycle.get(key)) or cycle[key] < 0:
                _error(errors, f"schema:{phase}.cycle[{index}] {key} invalid")
            else:
                sums[key] += int(cycle[key])
        if _integer(cycle.get("iterations")) and cycle["iterations"] >= 0:
            sums["iterations"] += int(cycle["iterations"])
        if cycle.get("ksp_destroyed") is not True:
            _error(errors, f"lifecycle:{phase}.cycle[{index}] KSP not destroyed")
        if not _finite(cycle.get("explicit_true_residual")):
            _gate(gates, f"numerical:{phase}.cycle[{index}].residual")
        resource = cycle.get("resource")
        tree = resource.get("process_tree") if isinstance(resource, dict) else None
        rss = tree.get("rss_bytes") if isinstance(tree, dict) else None
        swap = tree.get("swap_bytes") if isinstance(tree, dict) else None
        if not _integer(rss) or not _integer(swap):
            _error(errors, f"schema:{phase}.cycle[{index}] resource sample invalid")
        else:
            rss_values.append(int(rss))
            if rss >= RSS_HARD:
                _gate(gates, f"resource:{phase}.cycle[{index}].rss")
            if swap != SWAP_HARD:
                _gate(gates, f"resource:{phase}.cycle[{index}].swap")
    for key, stage_key in (("iterations", "local_iterations"), ("matvec_count", "matvec_count"), ("pc_apply_count", "pc_apply_count")):
        if stage.get(stage_key) != sums[key]:
            _error(errors, f"provenance:{phase}.{stage_key} ledger mismatch")
    if stage.get("additional_iterations") != base + local_iterations:
        _error(errors, f"provenance:{phase} additional iteration mapping mismatch")
    if stage.get("explicit_action_count") != len(cycles) + 1 or stage.get("ksp_destroy_count") != len(cycles):
        _error(errors, f"provenance:{phase} action/KSP count mismatch")
    if cycles:
        if stage.get("final_true_residual") != cycles[-1].get("explicit_true_residual"):
            _error(errors, f"provenance:{phase} final residual mismatch")
    if stage.get("absolute_end_iteration") != ABSOLUTE_ORIGIN + base + local_iterations:
        _error(errors, f"provenance:{phase} absolute end mapping mismatch")
    expected_checkpoints = [base + local for local in range(CHECKPOINT_INTERVAL, local_iterations + 1, CHECKPOINT_INTERVAL)]
    checkpoint_facts = stage.get("checkpoint_facts")
    actual_checkpoints = [item.get("additional_iteration") for item in checkpoint_facts] if isinstance(checkpoint_facts, list) and all(isinstance(item, dict) for item in checkpoint_facts) else []
    if actual_checkpoints != expected_checkpoints:
        _error(errors, f"lifecycle:{phase} checkpoint cadence mismatch")
    elif isinstance(checkpoint_facts, list):
        for index, item in enumerate(checkpoint_facts):
            if item.get("absolute_iteration") != ABSOLUTE_ORIGIN + expected_checkpoints[index]:
                _error(errors, f"provenance:{phase} checkpoint absolute mapping mismatch")
            relative = item.get("manifest_relative_path")
            path = (root / relative).resolve() if isinstance(relative, str) else None
            if path is None or not _inside(root.resolve(), path) or not path.is_file() or item.get("manifest_sha256") != _sha256(path):
                _error(errors, f"provenance:{phase} checkpoint manifest mismatch")
    initial = stage.get("initial_true_residual")
    if not _finite(initial):
        _gate(gates, f"numerical:{phase}.initial_residual")
    stagnation = _stagnation_facts(float(initial) if _finite(initial) else float("nan"), cycles, int(base))
    if stage.get("stagnation") != stagnation:
        _error(errors, f"provenance:{phase} stagnation facts mismatch")
    if rss_values:
        rss_trend = {
            "sample_count": len(rss_values),
            "first_rss_bytes": rss_values[0],
            "last_rss_bytes": rss_values[-1],
            "min_rss_bytes": min(rss_values),
            "max_rss_bytes": max(rss_values),
            "linear_slope_bytes_per_cycle": (rss_values[-1] - rss_values[0]) / max(len(rss_values) - 1, 1),
        }
    else:
        rss_trend = {
            "sample_count": 0,
            "first_rss_bytes": None,
            "last_rss_bytes": None,
            "min_rss_bytes": None,
            "max_rss_bytes": None,
            "linear_slope_bytes_per_cycle": None,
        }
    final = stage.get("final_true_residual")
    last_reason = cycles[-1].get("reason") if cycles else None
    last_breakdown = (
        _integer(last_reason)
        and last_reason < 0
        and (last_reason != DIVERGED_ITS or cycles[-1].get("iterations", RESTART) < RESTART)
    )
    if last_breakdown:
        classification = f"{phase.upper()}_PHYSICAL_BREAKDOWN"
    elif _finite(final) and float(final) <= RESIDUAL_LIMIT:
        classification = "E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS" if phase == "e1" else "E2_FRESH_PHYSICAL_NUMERICAL_PASS"
    elif stagnation["triggered"]:
        classification = "E1_PHYSICAL_STAGNATION" if phase == "e1" else "E2_FRESH_PHYSICAL_STAGNATION"
    elif local_iterations >= expected_cap:
        classification = "E1_PHYSICAL_MAXIT_FAIL" if phase == "e1" else "E2_FRESH_PHYSICAL_MAXIT_FAIL"
    else:
        classification = f"{phase.upper()}_PHYSICAL_BREAKDOWN"
    return {"cycles": cycles, "stagnation": stagnation, "rss_trend": rss_trend}, classification


def _check_worker(root: Path, worker: dict[str, Any], expected_sha: str, errors: list[str], gates: list[str]) -> dict[str, Any]:
    phase = worker.get("phase")
    if worker.get("schema") != WORKER_SCHEMA or phase not in {"e1", "e2"} or worker.get("workflow") != WORKFLOW:
        _error(errors, "schema:worker identity mismatch")
    _source(worker.get("source"), expected_sha, errors, "worker.source")
    input_facts = worker.get("input")
    if not isinstance(input_facts, dict) or input_facts.get("template_sha256") != INPUT_SHA256 or input_facts.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        _error(errors, "provenance:worker input identity mismatch")
    if phase == "e1":
        checkpoint_facts = worker.get("checkpoint")
        expected_checkpoint = {
            "iteration": 2024,
            "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
            "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
            "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
            "source_sha": CHECKPOINT_SOURCE_SHA,
            "mpi_size": 1,
            "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
            "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
        }
        if not isinstance(checkpoint_facts, dict) or any(checkpoint_facts.get(key) != value for key, value in expected_checkpoint.items()) or checkpoint_facts.get("relative_path") != CHECKPOINT_RELATIVE:
            _error(errors, "provenance:e1 checkpoint facts mismatch")
        checkpoint_authority = _check_checkpoint_authority(errors)
    elif worker.get("checkpoint") is not None:
        _error(errors, "schema:e2 checkpoint must be absent")
    same = worker.get("same_start")
    if not isinstance(same, dict):
        _error(errors, "schema:worker same_start facts missing")
        return {}
    same_gates: list[str] = []
    rhs = _load_array(root, same.get("rhs"), "same_start.rhs", errors, same_gates)
    initial = _load_array(root, same.get("initial_solution"), "same_start.initial_solution", errors, same_gates)
    if phase == "e1" and initial is not None and checkpoint_authority is not None and _array_sha(initial) != checkpoint_authority["array_sha256"]:
        _gate(same_gates, "numerical:e1 restored solution differs from checkpoint")
    pre_failures: list[str] = []
    same_input_changed = False
    for name in ("rhs", "initial_solution"):
        descriptor = same.get(name)
        before = same.get(f"{name}_before_sha256")
        after = same.get(f"{name}_after_sha256")
        actual = descriptor.get("array_sha256") if isinstance(descriptor, dict) else None
        if before != actual or after != actual:
            same_input_changed = True
    if same.get("input_unchanged") is not True or same.get("finite") is not True:
        if same.get("input_unchanged") is not True:
            same_input_changed = True
        _gate(same_gates, "numerical:same_start.input")
    restore = worker.get("restore")
    restore_gates: list[str] = []
    action = residual = None
    if isinstance(restore, dict):
        action = _load_array(root, restore.get("action_descriptor"), "restore.action", errors, restore_gates)
        residual = _load_array(root, restore.get("residual_descriptor"), "restore.residual", errors, restore_gates)
        if rhs is not None and action is not None and residual is not None and (rhs.shape != action.shape or residual.shape != rhs.shape):
            _error(errors, "schema:restore vector shapes mismatch")
        elif rhs is not None and action is not None and residual is not None:
            expected_residual = rhs - action
            closure = _relative_values(residual, expected_residual)
            if closure > 1.0e-12:
                _gate(restore_gates, "numerical:restore.rhs_action_closure")
            actual = float(np.linalg.norm(residual)) / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
            if not _finite(restore.get("actual")) or not math.isclose(float(restore["actual"]), actual, rel_tol=1.0e-12, abs_tol=1.0e-15):
                _error(errors, "provenance:restore residual norm mismatch")
            if phase == "e1":
                if restore.get("expected") != CHECKPOINT_EXPLICIT_RESIDUAL or restore.get("relative_limit") != CHECKPOINT_RELATIVE_LIMIT:
                    _error(errors, "provenance:e1 checkpoint Gate constants mismatch")
                reproduction = abs(actual - CHECKPOINT_EXPLICIT_RESIDUAL) / max(abs(CHECKPOINT_EXPLICIT_RESIDUAL), np.finfo(float).tiny)
                if reproduction > CHECKPOINT_RELATIVE_LIMIT:
                    _gate(restore_gates, "numerical:e1.checkpoint_reproduction")
                    pre_failures.append("checkpoint_reproduction")
                if restore.get("relative_difference") != reproduction:
                    _error(errors, "provenance:e1 checkpoint reproduction mismatch")
            elif restore.get("expected") is not None or restore.get("relative_difference") is not None:
                _error(errors, "schema:e2 restore checkpoint fields must be null")
        if restore.get("finite") is not True:
            _gate(restore_gates, "numerical:restore.finite")
    else:
        _error(errors, "schema:restore facts missing")
    probes = worker.get("probes")
    if not isinstance(probes, dict):
        _error(errors, "schema:worker probes missing")
    else:
        _check_probe(root, probes.get("action"), "probe.action", "dual_facts", errors, gates)
        _check_probe(root, probes.get("pc"), "probe.pc", "primal_facts", errors, gates)
        for label, probe, facts_key in (
            ("action", probes.get("action"), "dual_facts"),
            ("pc", probes.get("pc"), "primal_facts"),
        ):
            facts = probe.get(facts_key) if isinstance(probe, dict) else None
            if not isinstance(facts, dict) or facts.get("finite") is not True or facts.get("owned_slave_max") != 0.0 or facts.get("owned_slave_count") != 0:
                pre_failures.append(f"{label}.facts")
            repeat = probe.get("repeat_relative") if isinstance(probe, dict) else None
            if not _finite(repeat) or float(repeat) > 1.0e-12:
                pre_failures.append(f"{label}.repeat")
            if not isinstance(probe, dict) or probe.get("input_before_sha256") != probe.get("input_after_sha256"):
                pre_failures.append(f"{label}.input_unchanged")
        pc_probe = probes.get("pc")
        input_facts = pc_probe.get("input_facts") if isinstance(pc_probe, dict) else None
        if not isinstance(input_facts, dict) or input_facts.get("finite") is not True:
            pre_failures.append("pc.input_finite")
        if not isinstance(input_facts, dict) or input_facts.get("owned_slave_max") != 0.0 or input_facts.get("owned_slave_count") != 0:
            pre_failures.append("pc.input_slave")
    rhs_facts = worker.get("rhs")
    if not isinstance(rhs_facts, dict) or rhs_facts.get("finite") is not True:
        pre_failures.append("rhs.finite")
    if initial is None or not np.all(np.isfinite(initial)):
        pre_failures.append("initial_solution.finite")
    if same_input_changed:
        pre_failures.append("same_start.input_unchanged")
    expected_same_finite = (
        isinstance(rhs_facts, dict)
        and rhs_facts.get("finite") is True
        and initial is not None
        and bool(np.all(np.isfinite(initial)))
    )
    if same.get("finite") != expected_same_finite:
        _error(errors, "provenance:same_start finite fact mismatch")
    _check_facts(rhs_facts, "rhs", errors, gates, require_slave=False)
    architecture = worker.get("architecture")
    expected_architecture = {
        "physical_operator": "p6_matrix_free_split_volume_plus_streaming_dtn",
        "global_physical_aij": False,
        "global_schur": False,
        "dense_dtn": False,
        "factor": False,
        "numeric_allgather": False,
        "phase_once": True,
        "restart_basis_storage": "petsc_in_memory",
        "restart": RESTART,
    }
    if not isinstance(architecture, dict) or any(architecture.get(key) != value for key, value in expected_architecture.items()):
        _error(errors, "provenance:worker architecture mismatch")
    gates.extend(same_gates)
    gates.extend(restore_gates)
    recorded_gates = worker.get("gates")
    if not isinstance(recorded_gates, dict) or recorded_gates.get("pre_stage") != pre_failures:
        _error(errors, "provenance:worker pre-stage Gate facts mismatch")
    stage = worker.get("stage")
    stage_facts: dict[str, Any] = {}
    stage_classification = f"{phase.upper()}_NOT_RUN"
    if pre_failures:
        if stage is not None:
            _error(errors, "lifecycle:pre-stage Gate failed but solve stage exists")
    else:
        stage_facts, stage_classification = _check_stage(root, stage, str(phase), errors, gates)
        expected_initial = restore.get("actual") if isinstance(restore, dict) else None
        if _finite(expected_initial) and _finite(stage.get("initial_true_residual") if isinstance(stage, dict) else None):
            if not math.isclose(float(stage["initial_true_residual"]), float(expected_initial), rel_tol=1.0e-12, abs_tol=1.0e-15):
                _error(errors, "provenance:stage initial residual does not match restored residual")
    recorded_classification = recorded_gates.get("classification") if isinstance(recorded_gates, dict) else None
    if pre_failures:
        expected_classification = f"{phase.upper()}_NUMERICAL_GATE_FAIL"
    else:
        expected_classification = stage_classification
    if recorded_classification != expected_classification:
        _error(errors, "provenance:worker classification mismatch")
    return {
        "phase": phase,
        "pre_stage_gate_failures": pre_failures,
        "stage": stage_facts,
        "stage_classification": expected_classification,
        "same_start_gate_failures": same_gates,
        "restore_gate_failures": restore_gates,
    }


def _classification(errors: list[str], gates: list[str], metrics: dict[str, Any]) -> str:
    if errors:
        return "INFRASTRUCTURE_FAILURE_RETRYABLE"
    if any(item.startswith("resource:") for item in gates):
        return f"{str(metrics.get('phase', 'e1')).upper()}_RESOURCE_GATE_FAIL"
    if gates:
        return f"{str(metrics.get('phase', 'e1')).upper()}_NUMERICAL_GATE_FAIL"
    return str(metrics.get("stage_classification", "E1_NOT_RUN"))


def check_artifact(record_path: str | Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record_path = Path(record_path).resolve()
    metrics: dict[str, Any] = {}
    try:
        parent = _load_json(record_path)
        if not isinstance(parent, dict):
            raise ValueError("parent record is not an object")
        phase = parent.get("phase")
        if parent.get("schema") != PARENT_SCHEMA or parent.get("workflow") != WORKFLOW or phase not in {"e1", "e2"}:
            _error(errors, "schema:parent identity mismatch")
        _source(parent.get("source"), expected_source_sha, errors, "parent.source")
        contract = parent.get("resource_contract")
        if not isinstance(contract, dict) or contract.get("rss_watchdog_bytes") != RSS_HARD or contract.get("rss_hard_gate_bytes") != RSS_HARD or contract.get("swap_hard_gate_bytes") != SWAP_HARD:
            _error(errors, "provenance:parent resource contract mismatch")
        if parent.get("expected_mpi_size") != 1:
            _error(errors, "schema:parent MPI size mismatch")
        metrics["phase"] = phase
        _check_parent_e0_binding(record_path.parent, parent, phase, errors)
        process = _check_process(record_path.parent, parent, errors, gates)
        children = parent.get("children")
        child_rows = children if isinstance(children, list) else []
        resource_child_indices = [
            index
            for index, child in enumerate(child_rows)
            if isinstance(child, dict)
            and child.get("stop_reason") in {"process_tree_rss_watchdog", "process_tree_swap"}
        ]
        worker_candidate = parent.get("worker")
        worker_resource_stop = (
            isinstance(worker_candidate, dict)
            and worker_candidate.get("stop_reason")
            in {"process_tree_rss_watchdog", "process_tree_swap"}
        )
        resource_stop = bool(resource_child_indices or worker_resource_stop)
        if parent.get("jit_groups") != list(JIT_GROUPS):
            _error(errors, "schema:JIT group order mismatch")
        if resource_stop:
            if len(child_rows) > len(JIT_GROUPS):
                _error(errors, "lifecycle:resource stop has too many JIT children")
            if any(
                isinstance(child, dict) and child.get("group") != JIT_GROUPS[index]
                for index, child in enumerate(child_rows)
            ):
                _error(errors, "lifecycle:resource stop JIT prefix mismatch")
            if resource_child_indices and resource_child_indices[-1] != len(child_rows) - 1:
                _error(errors, "lifecycle:resource stop is not the final JIT child")
            if worker_resource_stop and len(child_rows) != len(JIT_GROUPS):
                _error(errors, "lifecycle:worker resource stop before JIT staging completed")
            if resource_child_indices and worker_candidate is not None:
                _error(errors, "lifecycle:worker exists after JIT resource stop")
        elif len(child_rows) != len(JIT_GROUPS):
            _error(errors, "schema:seven JIT children missing")
        for index, child in enumerate(child_rows):
            child_is_resource_stop = (
                isinstance(child, dict)
                and child.get("stop_reason") in {"process_tree_rss_watchdog", "process_tree_swap"}
            )
            resource_stop = _check_process_result(child, f"child[{index}]", errors, gates) or resource_stop
            if isinstance(child, dict) and child.get("group") != JIT_GROUPS[index]:
                _error(errors, f"lifecycle:child[{index}] group order mismatch")
            _check_record_hash(
                record_path.parent,
                child,
                f"child[{index}]",
                errors,
                allow_missing=child_is_resource_stop,
            )
        worker_result = worker_candidate
        if isinstance(worker_result, dict):
            worker_is_resource_stop = worker_result.get("stop_reason") in {
                "process_tree_rss_watchdog",
                "process_tree_swap",
            }
            resource_stop = _check_process_result(worker_result, "worker", errors, gates) or resource_stop
            _check_record_hash(
                record_path.parent,
                worker_result,
                "worker",
                errors,
                allow_missing=worker_is_resource_stop,
            )
            worker_relative = worker_result.get("record")
            worker_path = (record_path.parent / worker_relative).resolve() if isinstance(worker_relative, str) else None
        else:
            worker_path = None
            if not resource_stop:
                _error(errors, "schema:worker process result missing")
        if parent.get("error") is not None and not resource_stop:
            _error(errors, "infrastructure:parent reported an unexpected error")
        cache = parent.get("cache")
        if not isinstance(cache, dict):
            _error(errors, "schema:parent cache facts missing")
        else:
            if not isinstance(cache.get("initial"), dict) or cache["initial"].get("artifact_count") != 0:
                _error(errors, "provenance:initial cache is not empty")
            if not resource_stop and (cache.get("before_worker") is None or cache.get("after_worker") is None or cache["before_worker"] != cache["after_worker"]):
                _error(errors, "provenance:worker changed cache")
            after = cache.get("after_worker")
            if isinstance(after, dict) and after != _cache_snapshot(record_path.parent / "jit_cache"):
                _error(errors, "provenance:current cache does not match record")
        paths = parent.get("paths")
        markers = parent.get("markers")
        marker_relative = paths.get("marker_manifest") if isinstance(paths, dict) else None
        if not isinstance(paths, dict) or not isinstance(markers, dict) or not isinstance(marker_relative, str):
            if not resource_stop:
                _error(errors, "schema:marker manifest facts missing")
        else:
            manifest_path = (record_path.parent / marker_relative).resolve()
            if not _inside(record_path.parent, manifest_path) or not manifest_path.is_file():
                if not resource_stop:
                    _error(errors, "provenance:marker manifest missing")
            else:
                if markers.get("sha256") != _sha256(manifest_path):
                    _error(errors, "provenance:marker manifest SHA mismatch")
                rows = _load_json(manifest_path)
                names = [row.get("name") for row in rows] if isinstance(rows, list) else []
                expected_names = list(MARKER_ORDER.get(str(phase), ()))
                if names != expected_names and not (resource_stop and names == expected_names[: len(names)]):
                    _error(errors, "lifecycle:marker order mismatch")
                if markers.get("rows") != rows:
                    _error(errors, "provenance:marker rows mismatch")
        if worker_path is not None and worker_path.is_file() and not resource_stop:
            worker = _load_json(worker_path)
            if not isinstance(worker, dict):
                _error(errors, "schema:worker record is not an object")
            else:
                metrics = _check_worker(record_path.parent, worker, expected_source_sha, errors, gates)
        elif not resource_stop:
            _error(errors, "provenance:worker record cannot be loaded")
        completion_resource_stop = _check_completion(
            record_path.parent, parent, expected_source_sha, errors, gates
        )
        resource_stop = resource_stop or completion_resource_stop
        metrics["process"] = process
        metrics["resource_stop"] = resource_stop
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"infrastructure:checker boundary failed: {exc}")
    result = {
        "schema": CHECKER_SCHEMA,
        "status": "PASS" if not errors else "FAIL",
        "evidence_valid": not errors,
        "classification": _classification(errors, gates, metrics),
        "errors": errors,
        "metrics": {**metrics, "gate_failures": gates},
        "record": str(record_path),
        "record_sha256": _sha256(record_path) if record_path.is_file() else None,
        "expected_source_sha": expected_source_sha,
    }
    return result


def _write_output(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
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
