"""Regression for the actual provider imported locally by the receiver."""

import runpy
import types
from pathlib import Path


def test_same_stage_provider_used_by_local_import(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(str(root / "scripts/resume_w1_preworker_admission.py"))
    provider = types.ModuleType("src.runners.w1_admission_budget")
    calls = []
    monkeypatch.setitem(__import__("sys").modules, provider.__name__, provider)

    def admitted(*args, **kwargs):
        calls.append(("admit", args, kwargs))
        return 24

    def pressure(*args):
        calls.append(("stable", args))
        return "same_completed_window"

    namespace["install_same_stage_admission"](provider, admitted, pressure)
    # Match _launch_w1's local import, which defeated receiver.admit assignment.
    from src.runners.w1_admission_budget import admit, stable

    assert admit("same_hash", "same_run", 2 * 2**30, inner=True) == 24
    assert stable("same_hash", "same_run", 2 * 2**30) == "same_completed_window"
    assert calls[0][2] == {"inner": True}
    assert len(calls) == 2
