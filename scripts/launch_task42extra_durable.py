"""Explicit reviewed stages in distinct durable namespaces; no restart."""

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
    stages = {
        "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY": (
            "v4_formal_replay",
            "task42extra-v4-replay",
        ),
        "v5_readout_checks": ("v5_readout_checks", "task42extra-v5-checks"),
        "FEINN-FROZEN-HIDDEN-READOUT-G": (
            "v5_frozen_hidden_readout",
            "task42extra-v5-readout",
        ),
        "v5_readout_reconstruct": (
            "v5_readout_reconstruct",
            "task42extra-v5-reconstruct",
        ),
        "v5_readout_compare_only": (
            "v5_readout_compare_only",
            "task42extra-v5-compare",
        ),
    }
    if spec is None or spec.derived["stage"] not in stages:
        raise ValueError("ONLY_EXPLICIT_REVIEWED_DURABLE_STAGES_ARE_AUTHORIZED")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("DURABLE_LAUNCH_REQUIRES_CLEAN_SOURCE")
    namespace, session = stages[spec.derived["stage"]]
    directory = ROOT / "tmp/task42extra/durable" / namespace
    command = [
        "/bin/bash",
        "-lc",
        "source scripts/activate_task42extra.sh "
        + spec.derived["environment_mode"]
        + " && exec python scripts/run_case.py "
        + str(spec.source_path.relative_to(ROOT)),
    ]
    result = launch_tmux(directory, session, command, ROOT)
    print(
        json.dumps(
            {k: result[k] for k in ("socket", "session", "output", "scope")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
