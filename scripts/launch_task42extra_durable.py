"""Explicit reviewed stages in distinct durable namespaces; no restart."""

import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io.feinn_pilot import ROOT, load_pilot
from src.runners.durable_terminal import launch_tmux


def main():
    if len(sys.argv) not in (2, 4) or (
        len(sys.argv) == 4 and sys.argv[2] != "--attempt"
    ):
        raise SystemExit(
            "usage: launch_task42extra_durable.py <one-run.dat> [--attempt 2|3|4]"
        )
    spec = load_pilot(sys.argv[1])
    stages = {
        "v7_p_transfer_checks": ("v7_p_transfer_checks", "task42extra-v7-checks"),
        "v7_p4_reference": ("v7_p4_reference", "task42extra-v7-reference"),
        "v7_p3_p4_compare": ("v7_p3_p4_compare", "task42extra-v7-compare"),
        "v6_operator_readout_checks": (
            "v6_operator_readout_checks",
            "task42extra-v6-checks",
        ),
        "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT": (
            "v6_frozen_feature_residual",
            "task42extra-v6-readout",
        ),
        "v6_residual_readout_reconstruct": (
            "v6_residual_readout_reconstruct",
            "task42extra-v6-reconstruct",
        ),
        "v6_residual_readout_compare_only": (
            "v6_residual_readout_compare_only",
            "task42extra-v6-compare",
        ),
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
    from src.runners.feinn_campaign import STAGES
    from src.runners.feinn_gn_campaign import STAGES as GN_STAGES

    from src.runners.feinn_cached_gn_campaign import STAGES as CACHED_STAGES

    from src.runners.feinn_metric_campaign import STAGES as METRIC_STAGES

    STAGES = STAGES | GN_STAGES | CACHED_STAGES | METRIC_STAGES
    stages.update(
        {name: (name, "task42extra-" + name.replace("_", "-")) for name in STAGES}
    )
    if spec is None or spec.derived["stage"] not in stages:
        raise ValueError("ONLY_EXPLICIT_REVIEWED_DURABLE_STAGES_ARE_AUTHORIZED")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("DURABLE_LAUNCH_REQUIRES_CLEAN_SOURCE")
    namespace, session = stages[spec.derived["stage"]]
    if len(sys.argv) == 4:
        attempt = int(sys.argv[3])
        if not spec.derived["stage"].startswith(
            ("v9_", "v10_", "v11_")
        ) or attempt not in (
            2,
            3,
            4,
        ):
            raise ValueError("ONLY_REVIEW_V8_EVIDENCED_RETRIES")
        if spec.derived["stage"].startswith("v11_phase_") and attempt != 2:
            raise ValueError("V11_ONLY_ONE_COMPLETE_STATE_RECOVERY")
        # A prior attempt must be closed and cleared; never replace its files.
        previous = sorted(
            (ROOT / "results/task42extra").glob(spec.identity["run_id"] + "_*")
        )
        if not previous:
            raise ValueError("RETRY_WITHOUT_PRIOR_ATTEMPT")
        for old in previous:
            summary = old / "run_summary.json"
            if not summary.exists() or not json.loads(summary.read_text()).get(
                "descendants_cleared"
            ):
                raise ValueError("PRIOR_ATTEMPT_NOT_CLEARED")
        namespace += "_attempt" + str(attempt)
        session += "-attempt" + str(attempt)
    os.environ["TASK42EXTRA_DURABLE_NAMESPACE"] = namespace
    directory = ROOT / "tmp/task42extra/durable" / namespace
    command = [
        "/bin/bash",
        "-lc",
        "source scripts/activate_task42extra.sh "
        + spec.derived["environment_mode"]
        + " && export TASK42EXTRA_DURABLE_NAMESPACE="
        + namespace
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
