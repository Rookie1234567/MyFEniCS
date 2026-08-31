"""Small Linux-only lifecycle and cache facts used by the J1b contract lane."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


EXPECTED_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
MARKER_SCHEMA = "task038.v14.j1b.marker.v1"
SAMPLE_SCHEMA = "task038.v14.j1b.process-sample.v1"

# J1/J2/J4 may stop after any valid strict subsequence.  The contract lane
# uses the parent/cache/complete subsequence; later stages retain one ordering.
MARKER_ORDER = (
    "parent_started",
    "fresh_cache_created",
    "precompile_positive_p6_started",
    "precompile_positive_p6_complete",
    "precompile_positive_p3_started",
    "precompile_positive_p3_complete",
    "precompile_positive_p1_started",
    "precompile_positive_p1_complete",
    "precompile_dtn_surface_started",
    "precompile_dtn_surface_complete",
    "precompile_incident_rhs_started",
    "precompile_incident_rhs_complete",
    "precompile_physical_volume_started",
    "precompile_physical_volume_complete",
    "all_precompile_children_gone",
    "solver_child_started",
    "positive_setup_started",
    "positive_setup_complete",
    "mode_inventory_started",
    "mode_inventory_complete",
    "surface_assemblers_started",
    "surface_assemblers_complete",
    "dtn_carrier_started",
    "dtn_carrier_complete",
    "dtn_action_complete",
    "physical_volume_action_started",
    "physical_volume_action_complete",
    "bundle_built",
    "source_built",
    "one_action_complete",
    "one_pc_complete",
    "solve_started",
    "solve_complete",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "recovery_started",
    "recovery_complete",
    "parent_complete",
)
_COMPILER_NAMES = frozenset(
    {"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"}
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def prepare_fresh_root(root: Path | str, cache_dir: Path | str) -> dict[str, Path]:
    root = _absolute(root)
    cache_dir = _absolute(cache_dir)
    if cache_dir != root / "jit_cache":
        raise ValueError("cache directory must be root/jit_cache")
    if root.exists() or cache_dir.exists():
        raise FileExistsError("root or cache path already exists")
    if not root.parent.is_dir():
        raise FileNotFoundError("root parent must already exist")
    root.mkdir(exist_ok=False)
    marker_dir = root / "markers"
    marker_dir.mkdir(exist_ok=False)
    return {"root": root, "cache_dir": cache_dir, "marker_dir": marker_dir}


def create_fresh_cache(cache_dir: Path | str) -> Path:
    cache_dir = _absolute(cache_dir)
    if cache_dir.name != "jit_cache" or not cache_dir.parent.is_dir() or not (cache_dir.parent / "markers").is_dir():
        raise ValueError("cache parent is not the prepared fresh root")
    cache_dir.mkdir(exist_ok=False)
    return cache_dir


def _marker_parts(path: Path) -> tuple[int, str]:
    prefix, separator, name = path.stem.partition("_")
    if not separator or not prefix.isdigit() or not name:
        raise ValueError(f"invalid marker filename: {path.name}")
    return int(prefix), name


def marker_files(marker_dir: Path | str) -> list[Path]:
    marker_dir = _absolute(marker_dir)
    paths = sorted(marker_dir.glob("*.json"), key=lambda p: _marker_parts(p)[0])
    last_position = -1
    seen: set[str] = set()
    for path in paths:
        index, name = _marker_parts(path)
        if name in seen or name not in MARKER_ORDER:
            raise ValueError(f"invalid or duplicate marker: {path.name}")
        expected_index = MARKER_ORDER.index(name)
        if index != expected_index or expected_index <= last_position:
            raise ValueError(f"marker order is not a strict subsequence: {path.name}")
        seen.add(name)
        last_position = expected_index
    return paths


def write_marker(marker_dir: Path | str, name: str, facts: dict) -> Path:
    marker_dir = _absolute(marker_dir)
    if name not in MARKER_ORDER:
        raise ValueError(f"unknown marker: {name}")
    existing = marker_files(marker_dir)
    position = MARKER_ORDER.index(name)
    if existing and position <= MARKER_ORDER.index(_marker_parts(existing[-1])[1]):
        raise ValueError(f"marker is not later than the previous marker: {name}")
    path = marker_dir / f"{position:03d}_{name}.json"
    payload = {
        "schema": MARKER_SCHEMA,
        "name": name,
        "marker_index": position,
        "timestamp_ns": time.time_ns(),
        "facts": facts,
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def _status_text(pid: int) -> dict[str, str]:
    values: dict[str, str] = {}
    with Path(f"/proc/{pid}/status").open(encoding="utf-8") as stream:
        for line in stream:
            key, separator, value = line.partition(":")
            if separator:
                values[key] = value.strip()
    return values


def _kib(value: str | None) -> int | None:
    if value is None or not value.endswith(" kB"):
        return None
    number = value[:-3].strip()
    if not number.isdigit():
        return None
    return int(number) * 1024


def _pss_bytes(pid: int) -> int | None:
    try:
        values = _status_text_from(Path(f"/proc/{pid}/smaps_rollup"))
    except (OSError, ValueError):
        return None
    return _kib(values.get("Pss"))


def _status_text_from(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            key, separator, value = line.partition(":")
            if separator:
                values[key] = value.strip()
    return values


def _process_fact(pid: int, stage: str) -> dict | None:
    try:
        values = _status_text(pid)
        ppid_text = values.get("PPid")
        state = values.get("State", "").split(maxsplit=1)[0]
        rss = _kib(values.get("VmRSS"))
        swap = _kib(values.get("VmSwap"))
        if state in {"Z", "X", "x"}:
            rss = 0 if rss is None else rss
            swap = 0 if swap is None else swap
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            errors="replace"
        ).strip()
        if not ppid_text or not ppid_text.isdigit() or not state or rss is None or swap is None:
            return None
        comm = values.get("Name", "")
        if not comm:
            return None
        return {
            "pid": pid,
            "ppid": int(ppid_text),
            "comm": comm,
            "state": state,
            "cmdline": cmdline,
            "stage": stage,
            "rss_bytes": rss,
            "pss_bytes": _pss_bytes(pid),
            "swap_bytes": swap,
            "timestamp_ns": time.time_ns(),
            "exit_code": None,
        }
    except (OSError, UnicodeError, ValueError):
        return None


def _pid_vanished(pid: int) -> bool:
    try:
        Path(f"/proc/{pid}/stat").stat()
    except (FileNotFoundError, ProcessLookupError):
        return True
    except OSError:
        return False
    return False


def _live_parent_map() -> dict[int, list[int]]:
    parents: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            values = _status_text(int(entry))
            ppid = values.get("PPid")
            if ppid is not None and ppid.isdigit():
                parents.setdefault(int(ppid), []).append(int(entry))
        except (OSError, ValueError):
            continue
    return parents


def _is_compiler(fact: dict) -> bool:
    names = {fact["comm"]}
    names.update(Path(token).name for token in fact["cmdline"].split())
    return bool(names & _COMPILER_NAMES)


def process_tree_snapshot(root_pid: int, stage: str, exit_code: int | None = None) -> dict:
    parents = _live_parent_map()
    pids = [int(root_pid)]
    cursor = 0
    while cursor < len(pids):
        pids.extend(sorted(parents.get(pids[cursor], [])))
        cursor += 1
    members: list[dict] = []
    unreadable: list[int] = []
    vanished: list[int] = []
    retry_count = 0
    for pid in sorted(set(pids)):
        fact = _process_fact(pid, stage)
        if fact is None:
            retry_count += 1
            fact = _process_fact(pid, stage)
        if fact is None:
            if _pid_vanished(pid):
                vanished.append(pid)
            else:
                unreadable.append(pid)
        else:
            members.append(fact)
    readable = not unreadable
    pss_all_readable = readable and all(fact["pss_bytes"] is not None for fact in members)
    return {
        "schema": SAMPLE_SCHEMA,
        "root_pid": int(root_pid),
        "stage": stage,
        "timestamp_ns": time.time_ns(),
        "exit_code": exit_code,
        "members": members,
        "unreadable_pids": sorted(unreadable),
        "vanished_pids": sorted(vanished),
        "all_status_readable": readable,
        "readability_retry_count": retry_count,
        "compiler_descendant_count": sum(
            _is_compiler(fact) for fact in members if fact["pid"] != int(root_pid)
        ),
        "rss_bytes": sum(fact["rss_bytes"] for fact in members) if readable else None,
        "swap_bytes": sum(fact["swap_bytes"] for fact in members) if readable else None,
        "pss_all_readable": pss_all_readable,
        "pss_bytes": sum(fact["pss_bytes"] for fact in members) if pss_all_readable else None,
    }


def append_jsonl(path: Path | str, value: dict) -> Path:
    path = _absolute(path)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with path.open("ab") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def cache_manifest(cache_dir: Path | str) -> dict:
    cache_dir = _absolute(cache_dir)
    artifacts: list[dict] = []
    for base, _directories, files in os.walk(cache_dir, followlinks=False):
        for filename in files:
            path = Path(base) / filename
            if path.suffix not in {".c", ".o", ".so"} or not path.is_file():
                continue
            relative = path.relative_to(cache_dir).as_posix()
            artifacts.append(
                {
                    "relative_path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    artifacts.sort(key=lambda item: item["relative_path"])
    return {"cache_dir": str(cache_dir), "artifacts": artifacts, "artifact_count": len(artifacts)}


def marker_manifest(marker_dir: Path | str) -> list[dict]:
    return [
        {"name": _marker_parts(path)[1], "path": str(path), "sha256": sha256_file(path)}
        for path in marker_files(marker_dir)
    ]
