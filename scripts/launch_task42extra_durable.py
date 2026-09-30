"""Only Review V3's unique Adam500 boundary replay; no automatic restart."""

import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io.feinn_pilot import ROOT, load_pilot
from src.runners.durable_terminal import launch_tmux


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: launch_task42extra_durable.py <one-run.dat>")
    spec = load_pilot(sys.argv[1])
    if spec is None or spec.derived["stage"] != "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY":
        raise ValueError("ONLY_V4_BOUNDARY_REPLAY_IS_AUTHORIZED")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("DURABLE_LAUNCH_REQUIRES_CLEAN_SOURCE")
    directory = ROOT / "tmp/task42extra/durable/v4_formal_replay"
    command = [
        "/bin/bash",
        "-lc",
        "source scripts/activate_task42extra.sh ml && exec python scripts/run_case.py "
        + str(spec.source_path.relative_to(ROOT)),
    ]
    result = launch_tmux(directory, "task42extra-v4-replay", command, ROOT)
    print(
        json.dumps(
            {k: result[k] for k in ("socket", "session", "output", "scope")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
