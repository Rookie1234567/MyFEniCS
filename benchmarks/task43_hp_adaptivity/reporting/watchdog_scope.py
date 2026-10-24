"""Small identity gate for historical watchdog coverage in Task43 reports."""

from pathlib import Path

_R8_RUN_ROOT = Path("benchmarks/artifacts/task43/round8_p_up_attempt1/run")


def watchdog_resource_qualification(
    model_attempt: str,
    has_terminal_summary: bool,
    run_root: Path,
    repo_root: Path,
) -> str:
    """Classify summary coverage without copying R8 gaps to other attempts."""
    if has_terminal_summary:
        return "complete_supervisor_record"
    if (
        model_attempt == "round8_p"
        and Path(run_root).resolve() == (Path(repo_root) / _R8_RUN_ROOT).resolve()
    ):
        return "R8_supervisor_terminal_absent_partial_window_only"
    raise ValueError(
        "missing watchdog summary is only documented for the exact historical "
        f"round8_p run root; got attempt={model_attempt!r}, run_root={run_root!s}"
    )
