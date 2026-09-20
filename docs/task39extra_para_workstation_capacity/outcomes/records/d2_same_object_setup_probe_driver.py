from dataclasses import replace
import json
import os
from pathlib import Path
import time

from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.runners.physical_retained_condensed_v20 import run_retained_condensed_workflow


class StopAfterSetup(RuntimeError):
    pass


class ProbeLedger:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.phase = "setup"
        self.last_stage = ""
        self.stop_signal = None
        self.events = []

    def marker(self, name, facts):
        self.last_stage = name
        self.events.append((name, facts))
        if name == "retained_same_object_setup_checks_complete":
            raise StopAfterSetup(name)

    def append(self, name, facts):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(facts, sort_keys=True, allow_nan=False) + "\n")

    def set_phase(self, phase):
        self.phase = phase


def main():
    out = Path(os.environ.get("TASK39EXTRA_PROBE_OUT", "/tmp/task39extra-retained-setup"))
    cfg = replace(
        target_stage4_config(degree=6, h_nm=100),
        period_x=20.0, period_y=15.0, grating_width_x=8.0, grating_width_y=15.0,
        grating_height=2.0, z_min=-1.0, z_max=3.0, air_height=3.0,
        substrate_thickness=1.0, mesh_cell_type="hexahedron",
        mesh_spacing_mode="boundary_fitted", mesh_axis_cell_counts=(3, 2, 3),
        incident_theta_deg=74.0, incident_phi_deg=17.0,
        n_substrate=1.4 + .05j, n_grating=.9 + .02j,
    )
    ledger = ProbeLedger(out)
    payload = {
        "provenance": {
            "input_sha256": "probe-input",
            "physical_model_sha256": "probe-physical",
        }
    }
    summary = {"probe": "same_retained_workflow_setup", "status": "STARTED"}

    def sample():
        return {
            "reference_memory_admission": "measured_rss",
            "resource_stop_policy": "measured_tree_rss_only_v3",
            "swap_policy": "observe_only",
            "rss_bytes": 0,
            "swap_bytes": 0,
            "all_status_readable": True,
            "launch_cap_bytes": 1_600_000_000_000,
            "icntl23": 0,
        }

    try:
        run_retained_condensed_workflow(
            payload,
            out,
            source_sha="probe-source",
            cfg=cfg,
            contract={},
            ledger=ledger,
            sample=sample,
            summary=summary,
        )
    except StopAfterSetup:
        print("PROBE_STOPPED_AFTER_SETUP", flush=True)
        print(json.dumps({"events": [name for name, _ in ledger.events], "summary": summary}, sort_keys=True), flush=True)
        return 0
    raise AssertionError("same-object setup probe did not stop at setup marker")


if __name__ == "__main__":
    raise SystemExit(main())
