"""Run the fixed, serial J3 split cold-staged parent workflow.

The parent owns the fresh cache and is the process-tree authority.  It starts
the seven form-precompile children in order, waits for each
child and its descendants, then starts one cache-hit solver-bundle child.
Only raw lifecycle facts are written; qualification remains checker-owned.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from benchmarks.task038_full3d_jit_staging import (
    MARKER_ORDER,
    MARKER_SCHEMA,
    SAMPLE_SCHEMA,
    append_jsonl,
    cache_manifest,
    create_fresh_cache,
    marker_manifest as _marker_manifest,
    prepare_fresh_root,
    process_tree_snapshot,
    sha256_file,
    write_marker,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_jit_staged_parent"
CHILD_MODULE = "benchmarks.run_task038_full3d_jit_precompile"
SOLVER_MODULE = "benchmarks.run_task038_full3d_jit_solver_bundle"
RECORD_SCHEMA = "task038.v14.j3.split-cold-staged.parent-record.v1"
CHILD_RECORD_SCHEMA = "task038.full3d.jit-split.child-record.v1"
SOLVER_RECORD_SCHEMA = "task038.v14.j3.split-cold-staged.solver-record.v1"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_PROFILE = {
    "model_id": "euv_grazing1_phi0",
    "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
    "comparison_group": "euv_grazing1_phi0",
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "incident_theta_deg": 89.0,
    "incident_phi_deg": 0.0,
    "polarization": "s",
    "nedelec_degree": 6,
    "mesh_target_size_nm": 10.0,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}
JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
PRECOMPILE_MARKERS = {
    "positive-p6": ("precompile_positive_p6_started", "precompile_positive_p6_complete"),
    "positive-p3": ("precompile_positive_p3_started", "precompile_positive_p3_complete"),
    "positive-p1": ("precompile_positive_p1_started", "precompile_positive_p1_complete"),
    "dtn-surface": ("precompile_dtn_surface_started", "precompile_dtn_surface_complete"),
    "incident-rhs": ("precompile_incident_rhs_started", "precompile_incident_rhs_complete"),
    "physical-volume-curl": (
        "precompile_physical_volume_curl_started",
        "precompile_physical_volume_curl_complete",
    ),
    "physical-volume-mass": (
        "precompile_physical_volume_mass_started",
        "precompile_physical_volume_mass_complete",
    ),
}
POLL_SECONDS = 0.05
TERMINATION_GRACE_SECONDS = 0.5
RSS_HARD_LIMIT = 2_000_000_000
COMPILER_NAMES = frozenset(
    {"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"}
)


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _write_json(path: Path, value: Any) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _validate_identity(root: Path, source_sha: str, input_path: Path) -> dict[str, Any]:
    if len(source_sha) != 40 or any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source SHA must be a full lowercase Git SHA")
    if not input_path.is_file():
        raise FileNotFoundError(f"input file does not exist: {input_path}")
    actual_sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if actual_sha != source_sha or branch != BRANCH or status:
        raise RuntimeError(
            f"source identity is not clean: sha={actual_sha}, branch={branch}, status={status!r}"
        )
    executable = Path(sys.executable)
    prefix = Path(sys.prefix)
    expected_executable = root / ".venv" / "bin" / "python"
    expected_prefix = root / ".venv"
    if (
        executable != expected_executable
        or prefix != expected_prefix
        or not executable.is_file()
        or not prefix.is_dir()
    ):
        raise RuntimeError("parent interpreter must be the current checkout lexical .venv")
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation is required")
    input_sha256 = sha256_file(input_path)
    if input_sha256 != INPUT_SHA256:
        raise RuntimeError("input is not the frozen Task038 profile")
    return {
        "source_sha": actual_sha,
        "branch": branch,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(executable),
        "python_prefix": str(prefix),
        "input_path": str(input_path),
        "input_sha256": input_sha256,
    }


def _parent_command(args: argparse.Namespace) -> list[str]:
    return [str(Path(sys.executable)), "-m", MODULE, *sys.argv[1:]]


def _child_command(
    group: str, cache_dir: Path, record_path: Path, input_path: Path, source_sha: str
) -> list[str]:
    return [
        str(Path(sys.executable)),
        "-m",
        CHILD_MODULE,
        "--group",
        group,
        "--cache-dir",
        str(cache_dir),
        "--record",
        str(record_path),
        "--expected-source-sha",
        source_sha,
        "--input",
        str(input_path),
    ]


def _solver_command(
    cache_dir: Path,
    record_path: Path,
    marker_dir: Path,
    input_path: Path,
    source_sha: str,
) -> list[str]:
    return [
        str(Path(sys.executable)),
        "-m",
        SOLVER_MODULE,
        "--cache-dir",
        str(cache_dir),
        "--record",
        str(record_path),
        "--marker-dir",
        str(marker_dir),
        "--expected-source-sha",
        source_sha,
        "--expected-mpi-size",
        "1",
        "--input",
        str(input_path),
    ]


def _marker(
    marker_dir: Path,
    root: Path,
    cache_dir: Path,
    source_sha: str,
    name: str,
    **facts: Any,
) -> Path:
    common = {
        "stage": "j3-split-cold-staged-parent",
        "artifact_root": str(root),
        "cache_dir": str(cache_dir),
        "source_sha": source_sha,
    }
    common.update(facts)
    return write_marker(marker_dir, name, common)


def _compiler(fact: dict[str, Any], root_pid: int) -> bool:
    if int(fact["pid"]) == int(root_pid):
        return False
    names = {str(fact["comm"])}
    names.update(Path(token).name for token in str(fact["cmdline"]).split())
    return bool(names & COMPILER_NAMES)


def _sample(sample_path: Path, stage: str, exit_code: int | None = None) -> dict[str, Any]:
    value = process_tree_snapshot(os.getpid(), stage, exit_code=exit_code)
    append_jsonl(sample_path, value)
    return value


def _send_group_signal(
    process: subprocess.Popen[Any], signum: signal.Signals, signals: list[str]
) -> None:
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        return
    signals.append(signum.name)


def _proc_identity(pid: int) -> tuple[str, int] | tuple[()] | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = text.rfind(")")
        tail = text[close + 2 :].split() if close >= 0 else []
        if len(tail) < 3:
            return None
        return tail[0], int(tail[2])
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeError, ValueError):
        return None


def _group_alive(process_group_id: int, observed_pids: set[int]) -> bool:
    for pid in sorted(observed_pids):
        identity = _proc_identity(pid)
        if identity is None:
            return True
        if identity and identity[0] not in {"Z", "X", "x"}:
            return True
    try:
        entries = list(os.scandir("/proc"))
    except OSError:
        return True
    try:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            identity = _proc_identity(int(entry.name))
            if identity is None:
                return True
            if identity and identity[0] not in {"Z", "X", "x"}:
                if identity[1] == process_group_id:
                    return True
    except OSError:
        return True
    return False


def _monitor_child(
    process: subprocess.Popen[Any], sample_path: Path, stage: str
) -> dict[str, Any]:
    process_group_id = int(process.pid)
    observed_pids: set[int] = set()
    sample_count = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    peak_rss_bytes: int | None = None
    max_swap_bytes: int | None = None
    compiler_peak = 0
    all_status_readable = True
    last_sample: dict[str, Any] | None = None
    stop_reason: str | None = None

    def observe(value: dict[str, Any]) -> None:
        nonlocal sample_count, first_timestamp_ns, last_timestamp_ns
        nonlocal peak_rss_bytes, max_swap_bytes, compiler_peak
        nonlocal all_status_readable, last_sample
        sample_count += 1
        timestamp = int(value["timestamp_ns"])
        if first_timestamp_ns is None:
            first_timestamp_ns = timestamp
        last_timestamp_ns = timestamp
        all_status_readable = all_status_readable and value.get("all_status_readable") is True
        rss = value.get("rss_bytes")
        swap = value.get("swap_bytes")
        if rss is not None:
            peak_rss_bytes = int(rss) if peak_rss_bytes is None else max(peak_rss_bytes, int(rss))
        if swap is not None:
            max_swap_bytes = int(swap) if max_swap_bytes is None else max(max_swap_bytes, int(swap))
        root_pid = int(value["root_pid"])
        observed_pids.update(
            int(fact["pid"])
            for fact in value.get("members", [])
            if int(fact["pid"]) != root_pid
        )
        compiler_peak = max(
            compiler_peak,
            sum(_compiler(fact, root_pid) for fact in value.get("members", [])),
        )
        last_sample = value

    def gate(value: dict[str, Any]) -> str | None:
        if value.get("all_status_readable") is not True:
            return "authority_unreadable"
        if int(value.get("swap_bytes") or 0) > 0:
            return "process_tree_swap"
        if value.get("rss_bytes") is not None and int(value["rss_bytes"]) >= RSS_HARD_LIMIT:
            return "process_tree_rss_limit"
        return None

    signals: list[str] = []
    required_sigkill = False
    while True:
        value = _sample(sample_path, stage)
        observe(value)
        if stop_reason is None:
            stop_reason = gate(value)
        if stop_reason is not None:
            if not signals:
                _send_group_signal(process, signal.SIGTERM, signals)
            break
        if process.poll() is not None:
            break
        time.sleep(POLL_SECONDS)

    returncode = process.poll()
    if returncode is None:
        try:
            returncode = process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            if stop_reason is None:
                stop_reason = "process_exit_timeout"
            if "SIGTERM" not in signals:
                _send_group_signal(process, signal.SIGTERM, signals)
    if returncode is None and _group_alive(process_group_id, observed_pids):
        _send_group_signal(process, signal.SIGKILL, signals)
        required_sigkill = True
        try:
            returncode = process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            returncode = process.poll()

    value = _sample(sample_path, stage, exit_code=None if returncode is None else int(returncode))
    observe(value)
    deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    process_group_gone = not _group_alive(process_group_id, observed_pids)
    while not process_group_gone and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        value = _sample(sample_path, stage, exit_code=None if returncode is None else int(returncode))
        observe(value)
        process_group_gone = not _group_alive(process_group_id, observed_pids)
    if not process_group_gone:
        if "SIGTERM" not in signals:
            _send_group_signal(process, signal.SIGTERM, signals)
        deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
        while not process_group_gone and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            value = _sample(sample_path, stage, exit_code=None if returncode is None else int(returncode))
            observe(value)
            process_group_gone = not _group_alive(process_group_id, observed_pids)
        if not process_group_gone:
            _send_group_signal(process, signal.SIGKILL, signals)
            required_sigkill = True
            deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
            while not process_group_gone and time.monotonic() < deadline:
                time.sleep(POLL_SECONDS)
                value = _sample(sample_path, stage, exit_code=None if returncode is None else int(returncode))
                observe(value)
                process_group_gone = not _group_alive(process_group_id, observed_pids)

    return {
        "pid": int(process.pid),
        "process_group_id": process_group_id,
        "started_ns": first_timestamp_ns,
        "ended_ns": last_timestamp_ns,
        "returncode": None if returncode is None else int(returncode),
        "natural_exit": stop_reason is None and returncode == 0 and process_group_gone and not required_sigkill,
        "stop_reason": stop_reason or ("natural_exit" if returncode == 0 else "child_exit_nonzero"),
        "sample_count": sample_count,
        "peak_rss_bytes": peak_rss_bytes,
        "max_swap_bytes": max_swap_bytes,
        "all_status_readable": all_status_readable,
        "compiler_descendant_peak": compiler_peak,
        "observed_descendant_pids": sorted(observed_pids),
        "last_sample": last_sample,
        "signals": signals,
        "required_sigkill": required_sigkill,
        "process_group_gone": process_group_gone,
        "descendants_gone": process_group_gone,
    }


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _save_manifest(cache_dir: Path, path: Path) -> dict[str, Any]:
    manifest = cache_manifest(cache_dir)
    _write_json(path, manifest)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "artifact_count": int(manifest["artifact_count"]),
        "manifest": manifest,
    }


def _manifest_delta(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old = {item["relative_path"]: item["sha256"] for item in previous["manifest"]["artifacts"]}
    new = {item["relative_path"]: item["sha256"] for item in current["manifest"]["artifacts"]}
    if any(path not in new or new[path] != digest for path, digest in old.items()):
        raise RuntimeError("J3 cache artifacts are not monotonically preserved")
    return [
        item
        for item in current["manifest"]["artifacts"]
        if item["relative_path"] not in old
    ]


def _module_basenames(artifacts: list[dict[str, Any]]) -> list[str]:
    return sorted(
        Path(item["relative_path"]).name
        for item in artifacts
        if str(item["relative_path"]).endswith(".so")
    )


def _process_summary(path: Path) -> dict[str, Any]:
    sample_count = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    parent_pid: int | None = None
    all_status_readable = True
    peak_rss_bytes: int | None = None
    max_swap_bytes: int | None = None
    compiler_peak = 0
    observed_pids: set[int] = set()
    last_sample: dict[str, Any] | None = None
    stages: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            value = json.loads(line)
            sample_count += 1
            timestamp = int(value["timestamp_ns"])
            if first_timestamp_ns is None:
                first_timestamp_ns = timestamp
            last_timestamp_ns = timestamp
            parent_pid = int(value["root_pid"])
            all_status_readable = all_status_readable and value.get("all_status_readable") is True
            rss = value.get("rss_bytes")
            swap = value.get("swap_bytes")
            if rss is not None:
                peak_rss_bytes = int(rss) if peak_rss_bytes is None else max(peak_rss_bytes, int(rss))
            if swap is not None:
                max_swap_bytes = int(swap) if max_swap_bytes is None else max(max_swap_bytes, int(swap))
            root_pid = int(value["root_pid"])
            descendants = {
                int(fact["pid"])
                for fact in value.get("members", [])
                if int(fact["pid"]) != root_pid
            }
            observed_pids.update(descendants)
            compiler_count = sum(_compiler(fact, root_pid) for fact in value.get("members", []))
            compiler_peak = max(compiler_peak, compiler_count)
            stage = str(value["stage"])
            stage_fact = stages.setdefault(
                stage,
                {
                    "sample_count": 0,
                    "first_timestamp_ns": None,
                    "last_timestamp_ns": None,
                    "peak_rss_bytes": None,
                    "max_swap_bytes": None,
                    "all_status_readable": True,
                    "compiler_descendant_peak": 0,
                    "observed_descendant_pids": set(),
                    "last_sample": None,
                },
            )
            stage_fact["sample_count"] += 1
            if stage_fact["first_timestamp_ns"] is None:
                stage_fact["first_timestamp_ns"] = timestamp
            stage_fact["last_timestamp_ns"] = timestamp
            stage_fact["peak_rss_bytes"] = (
                int(rss)
                if stage_fact["peak_rss_bytes"] is None and rss is not None
                else stage_fact["peak_rss_bytes"] if rss is None
                else max(stage_fact["peak_rss_bytes"], int(rss))
            )
            stage_fact["max_swap_bytes"] = (
                int(swap)
                if stage_fact["max_swap_bytes"] is None and swap is not None
                else stage_fact["max_swap_bytes"] if swap is None
                else max(stage_fact["max_swap_bytes"], int(swap))
            )
            stage_fact["all_status_readable"] = (
                stage_fact["all_status_readable"] and value.get("all_status_readable") is True
            )
            stage_fact["compiler_descendant_peak"] = max(
                stage_fact["compiler_descendant_peak"], compiler_count
            )
            stage_fact["observed_descendant_pids"].update(descendants)
            stage_fact["last_sample"] = value
            last_sample = value
    for stage_fact in stages.values():
        stage_fact["observed_descendant_pids"] = sorted(stage_fact["observed_descendant_pids"])
    return {
        "sample_path": str(path),
        "sample_sha256": sha256_file(path),
        "sample_count": sample_count,
        "parent_pid": parent_pid,
        "first_timestamp_ns": first_timestamp_ns,
        "last_timestamp_ns": last_timestamp_ns,
        "all_status_readable": all_status_readable,
        "peak_rss_bytes": peak_rss_bytes,
        "max_swap_bytes": max_swap_bytes,
        "compiler_descendant_peak": compiler_peak,
        "observed_descendant_pids": sorted(observed_pids),
        "last_sample": last_sample,
        "stage_summaries": stages,
    }


def _run_child(
    command: list[str], stdout_path: Path, stderr_path: Path, sample_path: Path, stage: str
) -> dict[str, Any]:
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            cwd=Path(__file__).resolve().parents[1],
            start_new_session=True,
        )
        return _monitor_child(process, sample_path, stage)


def _partial_record(
    *,
    root: Path,
    cache_dir: Path,
    marker_dir: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    command: list[str],
    identity: dict[str, Any] | None,
    children: list[dict[str, Any]],
    solver: dict[str, Any] | None,
    sample_path: Path,
    error: str,
) -> dict[str, Any]:
    partial: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "stage": "j3-split-cold-staged-parent",
        "source_sha": source_sha,
        "branch": BRANCH,
        "command": command,
        "identity": {
            "input_sha256": INPUT_SHA256,
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": MODE_MANIFEST_SHA256,
            "profile": EXPECTED_PROFILE,
            "input_path": str(input_path),
            **({} if identity is None else {"observed": identity}),
        },
        "paths": {
            "artifact_root": str(root),
            "cache_dir": str(cache_dir),
            "marker_dir": str(marker_dir),
            "record": str(record_path),
            "process_samples": str(sample_path),
        },
        "children": children,
        "solver": solver,
        "error": error,
        "raw_facts_only": True,
        "partial": True,
    }
    if sample_path.is_file():
        partial["process"] = _process_summary(sample_path)
    if (cache_dir / "").is_dir():
        partial["cache_observed"] = cache_manifest(cache_dir)
    marker_manifest_path = root / "marker_manifest.json"
    if marker_dir.is_dir() and not marker_manifest_path.exists():
        try:
            _write_json(marker_manifest_path, _marker_manifest(marker_dir))
        except (OSError, ValueError):
            pass
    if marker_manifest_path.is_file():
        partial["markers"] = {
            "manifest_path": str(marker_manifest_path),
            "manifest_sha256": sha256_file(marker_manifest_path),
        }
    return partial


def run_parent(args: argparse.Namespace) -> None:
    root = _absolute(args.artifact_root)
    cache_dir = root / "jit_cache"
    record_path = _absolute(args.record)
    input_path = _absolute(args.input)
    if record_path != root / "parent_record.json":
        raise ValueError("parent record must be artifact_root/parent_record.json")
    if record_path.exists():
        raise FileExistsError(f"parent record already exists: {record_path}")
    repo = Path(__file__).resolve().parents[1]
    identity = _validate_identity(repo, args.source_sha, input_path)
    paths = prepare_fresh_root(root, cache_dir)
    sample_path = root / "parent_process.jsonl"
    parent_command = _parent_command(args)
    children: list[dict[str, Any]] = []
    solver_info: dict[str, Any] | None = None
    observed_identity: dict[str, Any] | None = None
    try:
        _marker(paths["marker_dir"], root, cache_dir, args.source_sha, "parent_started", pid=os.getpid())
        create_fresh_cache(paths["cache_dir"])
        if cache_manifest(cache_dir)["artifact_count"] != 0:
            raise RuntimeError("fresh cache is not empty")
        _marker(paths["marker_dir"], root, cache_dir, args.source_sha, "fresh_cache_created", artifact_count=0)
        children_dir = root / "children"
        solver_dir = root / "solver"
        manifests_dir = root / "cache_manifests"
        for directory in (children_dir, solver_dir, manifests_dir):
            directory.mkdir(exist_ok=False)
        initial_manifest = _save_manifest(cache_dir, manifests_dir / "initial.json")
        previous_manifest = initial_manifest
        for index, group in enumerate(JIT_GROUPS):
            started, complete = PRECOMPILE_MARKERS[group]
            child_record = children_dir / f"{index:02d}-{group.replace('-', '_')}.json"
            stdout_path = children_dir / f"{index:02d}-{group.replace('-', '_')}.stdout"
            stderr_path = children_dir / f"{index:02d}-{group.replace('-', '_')}.stderr"
            command = _child_command(group, cache_dir, child_record, input_path, args.source_sha)
            if group == "physical-volume-curl":
                _marker(
                    paths["marker_dir"],
                    root,
                    cache_dir,
                    args.source_sha,
                    "precompile_physical_volume_started",
                    group="physical-volume",
                    command=command,
                )
            _marker(
                paths["marker_dir"],
                root,
                cache_dir,
                args.source_sha,
                started,
                group=group,
                command=command,
            )
            monitor = _run_child(
                command,
                stdout_path,
                stderr_path,
                sample_path,
                f"precompile:{group}",
            )
            child_entry = {
                "group": group,
                "command": command,
                "pid": monitor["pid"],
                "returncode": monitor["returncode"],
                "natural_exit": monitor["natural_exit"],
                "stop_reason": monitor["stop_reason"],
                "descendants_gone": monitor["descendants_gone"],
                "record_path": str(child_record),
                "record_sha256": sha256_file(child_record) if child_record.is_file() else None,
                "stdout_path": str(stdout_path),
                "stdout_sha256": sha256_file(stdout_path) if stdout_path.is_file() else None,
                "stderr_path": str(stderr_path),
                "stderr_sha256": sha256_file(stderr_path) if stderr_path.is_file() else None,
                "process": monitor,
            }
            children.append(child_entry)
            try:
                current_manifest = _save_manifest(
                    cache_dir, manifests_dir / f"{index:02d}-{group.replace('-', '_')}.json"
                )
                child_entry.update(
                    {
                        "cache_manifest_path": current_manifest["path"],
                        "cache_manifest_sha256": current_manifest["sha256"],
                        "cache_artifact_count": current_manifest["artifact_count"],
                    }
                )
                added = _manifest_delta(previous_manifest, current_manifest)
                module_names = _module_basenames(added)
                child_entry.update(
                    {
                        "added_artifacts": added,
                        "new_module_basenames": module_names,
                    }
                )
            except Exception as error:
                child_entry["manifest_error"] = str(error)
                raise
            if (
                not monitor["natural_exit"]
                or not monitor["all_status_readable"]
                or not monitor["process_group_gone"]
                or monitor["required_sigkill"]
                or monitor["max_swap_bytes"] != 0
                or monitor["peak_rss_bytes"] is None
                or monitor["peak_rss_bytes"] >= RSS_HARD_LIMIT
            ):
                raise RuntimeError(f"precompile child failed: {group}")
            if not child_record.is_file():
                raise RuntimeError(f"precompile child record is missing: {child_record}")
            child_payload = _read_json(child_record)
            observed_identity = child_payload.get("runtime", observed_identity)
            _marker(
                paths["marker_dir"],
                root,
                cache_dir,
                args.source_sha,
                complete,
                group=group,
                returncode=monitor["returncode"],
                descendants_gone=monitor["descendants_gone"],
                cache_manifest_sha256=current_manifest["sha256"],
                new_module_basenames=module_names,
            )
            if group == "physical-volume-mass":
                _marker(
                    paths["marker_dir"],
                    root,
                    cache_dir,
                    args.source_sha,
                    "precompile_physical_volume_complete",
                    group="physical-volume",
                    returncode=monitor["returncode"],
                    descendants_gone=monitor["descendants_gone"],
                    cache_manifest_sha256=current_manifest["sha256"],
                    new_module_basenames=module_names,
                )
            previous_manifest = current_manifest
        tail_sample = _sample(sample_path, "precompile:parent-only")
        if (
            tail_sample.get("all_status_readable") is not True
            or int(tail_sample.get("swap_bytes") or 0) != 0
            or tail_sample.get("rss_bytes") is None
            or int(tail_sample["rss_bytes"]) >= RSS_HARD_LIMIT
        ):
            raise RuntimeError("precompile parent-only authority sample failed")
        _marker(
            paths["marker_dir"],
            root,
            cache_dir,
            args.source_sha,
            "all_precompile_children_gone",
            child_count=len(children),
            compiler_descendant_count=int(tail_sample["compiler_descendant_count"]),
        )
        before_solver = _save_manifest(cache_dir, manifests_dir / "before_solver.json")
        solver_record = solver_dir / "solver_record.json"
        solver_command = _solver_command(
            cache_dir, solver_record, paths["marker_dir"], input_path, args.source_sha
        )
        _marker(
            paths["marker_dir"],
            root,
            cache_dir,
            args.source_sha,
            "solver_child_started",
            command=solver_command,
            pid_expected="child_process",
        )
        solver_process = _run_child(
            solver_command,
            solver_dir / "solver.stdout",
            solver_dir / "solver.stderr",
            sample_path,
            "solver",
        )
        solver_info = {
            "command": solver_command,
            "process": solver_process,
            "record_path": str(solver_record),
            "stdout_path": str(solver_dir / "solver.stdout"),
            "stderr_path": str(solver_dir / "solver.stderr"),
        }
        solver_info["record_sha256"] = sha256_file(solver_record) if solver_record.is_file() else None
        solver_info["stdout_sha256"] = sha256_file(Path(solver_info["stdout_path"]))
        solver_info["stderr_sha256"] = sha256_file(Path(solver_info["stderr_path"]))
        after_solver = _save_manifest(cache_dir, manifests_dir / "after_solver.json")
        solver_info["before_solver_manifest_sha256"] = before_solver["sha256"]
        solver_info["after_solver_manifest_sha256"] = after_solver["sha256"]
        solver_info["cache_unchanged"] = (
            Path(before_solver["path"]).read_bytes() == Path(after_solver["path"]).read_bytes()
        )
        if (
            not solver_info["process"]["natural_exit"]
            or not solver_info["process"]["all_status_readable"]
            or not solver_info["process"]["process_group_gone"]
            or solver_info["process"]["required_sigkill"]
            or solver_info["process"]["max_swap_bytes"] != 0
            or solver_info["process"]["peak_rss_bytes"] is None
            or solver_info["process"]["peak_rss_bytes"] >= RSS_HARD_LIMIT
        ):
            raise RuntimeError("solver-bundle child failed")
        if not solver_record.is_file():
            raise RuntimeError(f"solver-bundle record is missing: {solver_record}")
        if not solver_info["cache_unchanged"]:
            raise RuntimeError("solver phase changed the formal cache")
        _marker(
            paths["marker_dir"],
            root,
            cache_dir,
            args.source_sha,
            "parent_complete",
            solver_returncode=solver_info["process"]["returncode"],
            cache_unchanged=True,
            before_solver_manifest_sha256=before_solver["sha256"],
            after_solver_manifest_sha256=after_solver["sha256"],
            compiler_descendant_count=0,
        )
        marker_path = root / "marker_manifest.json"
        marker_entries = _marker_manifest(paths["marker_dir"])
        _write_json(marker_path, marker_entries)
        samples = _process_summary(sample_path)
        all_modules = sorted(
            {
                module
                for child in children
                for module in child["new_module_basenames"]
            }
        )
        deferred = next(
            child["new_module_basenames"]
            for child in children
            if child["group"] == "incident-rhs"
        )
        record = {
            "schema": RECORD_SCHEMA,
            "stage": "j3-split-cold-staged-parent",
            "source_sha": args.source_sha,
            "branch": BRANCH,
            "command": parent_command,
            "identity": {
                "input_path": str(input_path),
                "input_sha256": INPUT_SHA256,
                "physical_model_sha256": PHYSICAL_MODEL_SHA256,
                "mode_manifest_sha256": MODE_MANIFEST_SHA256,
                "profile": EXPECTED_PROFILE,
                "runtime": observed_identity or identity,
            },
            "paths": {
                "artifact_root": str(root),
                "cache_dir": str(cache_dir),
                "marker_dir": str(paths["marker_dir"]),
                "record": str(record_path),
                "process_samples": str(sample_path),
                "marker_manifest": str(marker_path),
                "children_dir": str(children_dir),
                "solver_dir": str(solver_dir),
                "cache_manifests_dir": str(manifests_dir),
            },
            "marker_schema": MARKER_SCHEMA,
            "sample_schema": SAMPLE_SCHEMA,
            "markers": {
                "names": [entry["name"] for entry in marker_entries],
                "manifest_path": str(marker_path),
                "manifest_sha256": sha256_file(marker_path),
            },
            "process": samples,
            "children": children,
            "solver": solver_info,
            "cache": {
                "initial_empty": True,
                "initial_manifest": initial_manifest,
                "group_manifests": [
                    {
                        "group": child["group"],
                        "path": child["cache_manifest_path"],
                        "sha256": child["cache_manifest_sha256"],
                        "artifact_count": child["cache_artifact_count"],
                        "new_module_basenames": child["new_module_basenames"],
                    }
                    for child in children
                ],
                "before_solver": before_solver,
                "after_solver": after_solver,
                "precompiled_module_basenames": all_modules,
                "deferred_incident_module_basenames": deferred,
                "solver_unchanged": True,
            },
            "architecture": {
                "same_physical_mesh": True,
                "levels": [6, 3, 1],
                "p6_matrix_free": True,
                "p6_global_aij": False,
                "high_order_global_aij": False,
                "global_dense_transfer": False,
                "numeric_allgather": False,
                "p3_sparse_matrix_built": True,
                "p1_sparse_matrix_built": True,
                "p1_direct_factor_built": True,
                "same_mesh_pmg_built": True,
                "streaming_dtn_action_built": True,
                "dtn_carrier_built": True,
                "dtn_carrier_lifetime": "transient_released",
                "volume_component_count": 2,
                "volume_components": ["curl_curl", "complex_material_mass"],
                "monolithic_physical_volume": False,
                "physical_volume_action_built": True,
                "rhs": False,
                "ksp": False,
                "solve": False,
                "recovery": False,
                "bundle_destroyed_before_record": True,
            },
            "raw_facts_only": True,
        }
        _write_json(record_path, record)
    except Exception as error:
        if not record_path.exists():
            partial = _partial_record(
                root=root,
                cache_dir=cache_dir,
                marker_dir=paths["marker_dir"],
                record_path=record_path,
                source_sha=args.source_sha,
                input_path=input_path,
                command=parent_command,
                identity=observed_identity or identity,
                children=children,
                solver=solver_info,
                sample_path=sample_path,
                error=str(error),
            )
            _write_json(record_path, partial)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-mpi-size", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_mpi_size != 1:
        raise ValueError("J3 parent is fixed to MPI1")
    run_parent(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "CHILD_MODULE",
    "JIT_GROUPS",
    "MARKER_ORDER",
    "MODULE",
    "RECORD_SCHEMA",
    "RSS_HARD_LIMIT",
    "SOLVER_MODULE",
    "build_parser",
    "main",
    "run_parent",
)
