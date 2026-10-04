"""V36-only immutable component scope; historical ledgers are never consulted."""

import hashlib
import json
import signal
import time
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.bounded_diagnostic_window import DiagnosticWindow

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp/task042/v36"


class PreparationWindow(DiagnosticWindow):
    def __init__(self, folder):
        super().__init__(folder, {"actions": 0}, "V36")

    def probe_wall(self):
        return sum(
            json.loads(p.read_text())["elapsed_seconds"]
            for p in self.TMP.glob("probe_*.json")
        )

    def charged_wall(self):
        return (
            self.probe_wall()
            + sum(r["elapsed_seconds"] for r in self.ledger()["runs"])
            + 0.326941663
        )

    def require_ready(self):
        self.require_live(margin=60)
        book = self.ledger()
        if book["closed"] or book["active"] is not None:
            raise RuntimeError("V36 closed/active scope")
        wait = self.TMP / "resource_wait.json"
        if (
            wait.exists()
            and time.monotonic() < json.loads(wait.read_text())["next_probe_monotonic"]
        ):
            raise RuntimeError("V36 RESOURCE_WAIT minimum 120s interval")
        if self.charged_wall() >= 1740:
            raise RuntimeError("V36 paid wall reserve reached")

    def remaining(self, role):
        self.require_ready()
        used = sum(
            r["elapsed_seconds"]
            for r in self.ledger()["runs"]
            if r["role"] == "COMPONENT"
        )
        return min(
            900 - used if role == "COMPONENT" else 300,
            1740 - self.charged_wall(),
            self.snapshot()["heavy_remaining_seconds"],
        )

    def admission(self, probe, *, receipt_path, **kwargs):
        self.require_ready()
        began = time.monotonic()
        seconds = min(30 - self.probe_wall(), 1740 - self.charged_wall())
        if seconds <= 0:
            raise RuntimeError("V36 paid probe budget exhausted")
        old = signal.getsignal(signal.SIGALRM)

        def expired(*_):
            raise TimeoutError("V36 paid probe wall cap")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        error = None
        try:
            return probe(receipt_path=receipt_path, **kwargs)
        except Exception as exc:
            error = repr(exc)
            if Path(receipt_path).exists():
                raw = json.loads(Path(receipt_path).read_text())
                if any(v == "FAIL" for v in raw.get("gates", {}).values()):
                    write_json(
                        self.TMP / "resource_wait.json",
                        {
                            "next_probe_monotonic": time.monotonic() + 120,
                            "cause": error,
                        },
                    )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            path = (
                self.TMP
                / f"probe_{len(list(self.TMP.glob('probe_*.json'))) + 1:03d}.json"
            )
            write_json(
                path,
                {
                    "elapsed_seconds": time.monotonic() - began,
                    "receipt_path": str(receipt_path),
                    "error": error,
                },
            )

    def begin(self, role, folder, source):
        self.require_ready()
        book = self.ledger()
        book["active"] = {
            "role": role,
            "folder": str(folder),
            "source_sha": source,
            "before_clock": self.snapshot(),
        }
        write_json(self.LEDGER_PATH, book)

    def settle(self, summary, folder):
        book = self.ledger()
        active = book["active"]
        if active is None or active["folder"] != str(folder):
            raise ValueError("V36 stage ownership")
        row = dict(
            active,
            elapsed_seconds=summary["elapsed_seconds"],
            classification=summary["classification"],
            exit_code=summary["leader_exit_code"],
            descendants_cleared=summary["descendants_cleared"],
            peak_bytes=summary["sampled_process_tree_rss_peak_bytes"],
            swap_bytes=summary["sampled_process_tree_swap_peak_bytes"],
        )
        book["runs"].append(row)
        book["active"] = None
        write_json(self.LEDGER_PATH, book)
        self.journal("stage_settled", row=row, charged_seconds=self.charged_wall())


def implementation_hashes():
    paths = [
        "src/solvers/bounded_port_provider.py",
        "src/solvers/bounded_port_surface.py",
        "src/solvers/target_port_preparation.py",
        "src/solvers/port_component_study.py",
        "src/solvers/port_preparation_window.py",
        "src/io/port_preparation.py",
        "src/runners/port_preparation.py",
        "scripts/run_case.py",
        "benchmarks/check_port_preparation.py",
        "src/test/test_task042_v36_ports.py",
        "src/test/port_provider_mpi_fixture.py",
        "input/task042_neural_coarse_inverse/port_preparation_v36.json",
    ]
    paths += [
        "benchmarks/qualify_port_preparation.py",
        "src/test/test_task042_v35_cache.py",
        "src/test/test_task042_v36_checker.py",
    ]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


window = PreparationWindow(TMP)
