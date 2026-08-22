"""Real subprocess contracts for N2 worker/watchdog directory ownership."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from benchmarks import run_task038_full3d_n2 as runner


ROOT = Path(__file__).parents[2]
RUNNER_PATH = ROOT / "benchmarks" / "run_task038_full3d_n2.py"

_CHILD = textwrap.dedent(
    """
    import json
    import sys
    import time
    from pathlib import Path
    from benchmarks import run_task038_full3d_n2 as n2

    class Comm:
        rank = 0

        def bcast(self, value, root=0):
            return value

        def barrier(self):
            return None

    values = {
        sys.argv[index]: sys.argv[index + 1]
        for index in range(1, len(sys.argv), 2)
    }
    raw = Path(values["--raw-dir"])
    record = Path(values["--record"])
    markers = Path(values["--marker-dir"])
    comm = Comm()
    time.sleep(0.12)
    worker_owned_paths_preexisting = raw.exists() or markers.exists()
    n2._prepare_paths(raw, record, markers, comm)
    n2._write_marker(
        markers, "preflight", "ownership-fixture", comm, stage="e2e"
    )
    time.sleep(0.12)
    record.write_text(
        json.dumps(
            {
                "schema": "ownership-e2e",
                "worker_created_paths": True,
                "worker_owned_paths_preexisting": worker_owned_paths_preexisting,
            }
        )
        + "\\n",
        encoding="utf-8",
    )
    """
).strip()


def _watchdog_command(base: Path, *, overlap: bool = False) -> tuple[list[str], dict[str, Path]]:
    raw = base / "raw"
    markers = raw / "markers"
    record = base / "record.json"
    output_root = raw if overlap else base / "watchdog"
    paths = {
        "raw": raw,
        "markers": markers,
        "record": record,
        "watchdog_raw": output_root / "watchdog.raw.json",
        "watchdog_compact": output_root / "watchdog.compact.json",
        "watchdog_log": output_root / "worker.log",
    }
    command = [
        sys.executable,
        "-m",
        "benchmarks.run_task038_full3d_n2",
        "--watchdog",
        "--watchdog-record",
        str(paths["record"]),
        "--watchdog-raw",
        str(paths["watchdog_raw"]),
        "--watchdog-compact",
        str(paths["watchdog_compact"]),
        "--watchdog-log",
        str(paths["watchdog_log"]),
        "--watchdog-marker-dir",
        str(paths["markers"]),
        "--watchdog-poll-seconds",
        "0.05",
        "--watchdog-timeout-seconds",
        "0",
        "--watchdog-command",
        sys.executable,
        "-c",
        _CHILD,
        "--raw-dir",
        str(paths["raw"]),
        "--record",
        str(paths["record"]),
        "--marker-dir",
        str(paths["markers"]),
    ]
    return command, paths


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )


def _snapshot_files(paths: list[Path]) -> dict[Path, str]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(item for item in path.rglob("*") if item.is_file())
    return {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


def test_watchdog_worker_ownership_is_a_real_subprocess_contract(tmp_path: Path) -> None:
    command, paths = _watchdog_command(tmp_path / "first")
    assert not paths["raw"].exists()
    assert not paths["markers"].exists()

    result = _run(command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert paths["raw"].is_dir()
    assert paths["markers"].is_dir()
    assert (paths["markers"] / "preflight.json").is_file()
    for name in ("record", "watchdog_raw", "watchdog_compact", "watchdog_log"):
        assert paths[name].is_file()

    raw = json.loads(paths["watchdog_raw"].read_text(encoding="utf-8"))
    compact = json.loads(paths["watchdog_compact"].read_text(encoding="utf-8"))
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    stages = [sample["stage"] for sample in raw["samples"]]
    assert "startup" in stages
    assert "preflight" in stages
    assert stages.index("startup") < stages.index("preflight")
    marker = json.loads(
        (paths["markers"] / "preflight.json").read_text(encoding="utf-8")
    )
    assert marker["marker"] == "preflight"
    assert marker["details"]["stage"] == "e2e"
    assert raw["worker_returncode"] == 0
    assert compact["natural_exit"] is True
    assert record["worker_created_paths"] is True
    assert record["worker_owned_paths_preexisting"] is False
    assert str(paths["raw"]) in raw["command"]
    assert str(paths["markers"]) in raw["command"]

    snapshots = _snapshot_files(list(paths.values()))
    second = _run(command)
    assert second.returncode != 0
    assert snapshots == _snapshot_files(list(paths.values()))


def test_watchdog_rejects_output_inside_worker_owned_raw_before_spawn(
    tmp_path: Path,
) -> None:
    command, paths = _watchdog_command(tmp_path / "overlap", overlap=True)
    result = _run(command)
    assert result.returncode != 0
    assert not paths["raw"].exists()
    assert not paths["markers"].exists()
    assert not paths["record"].exists()


def test_watchdog_ownership_contract_is_explicit_and_no_cleanup_reuse_exists(
    tmp_path: Path,
) -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_extract_worker_owned_paths" in function_names
    assert "_validate_watchdog_ownership" in function_names
    assert "shutil.rmtree" not in source
    assert "raw_dir.exists() or record.exists() or marker_dir.exists()" in source
    assert runner._extract_worker_owned_paths(
        ("python", "--raw-dir", "raw", "--marker-dir", "markers"), ROOT
    ) == ((ROOT / "raw").resolve(), (ROOT / "markers").resolve())
    with pytest.raises(ValueError):
        unique_base = tmp_path / "owned"
        runner._validate_watchdog_ownership(
            (
                "python",
                "--raw-dir",
                str(unique_base / "raw"),
                "--marker-dir",
                str(unique_base / "raw/markers"),
            ),
            (unique_base,),
            ROOT,
        )
