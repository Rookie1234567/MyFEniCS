from pathlib import Path

import pytest

from src.runners import exact_cache_admission as admission


def simulated_host(monkeypatch, *, available_kib=100_000_000):
    original = Path.read_text

    def read(path, *args, **kwargs):
        if str(path) == "/proc/meminfo":
            return f"MemAvailable: {available_kib} kB\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(admission.time, "sleep", lambda _: None)
    monkeypatch.setattr(admission.os, "sched_getaffinity", lambda _: set(range(12)))
    # Two hardware threads per physical core. CPU 2/3 is busy.
    monkeypatch.setattr(admission, "physical_core", lambda cpu: (0, cpu // 2))
    samples = iter(
        [
            {cpu: [0] * 8 for cpu in range(12)},
            {
                cpu: [
                    90 if cpu in (2, 3) else 1,
                    0,
                    0,
                    10 if cpu in (2, 3) else 99,
                    0,
                    0,
                    0,
                    0,
                ]
                for cpu in range(12)
            },
        ]
    )
    monkeypatch.setattr(admission, "_cpu_sample", lambda: next(samples))


def test_cpu_admission_excludes_neighbor_sibling_and_busy_core(monkeypatch):
    simulated_host(monkeypatch)
    receipt = admission.choose_idle_physical_cpus(4, excluded_cpus=[0])
    selected = [entry["cpu"] for entry in receipt["selected"]]
    assert len(selected) == 4
    assert not set(selected) & {0, 1, 2, 3}
    assert len({cpu // 2 for cpu in selected}) == 4


def test_cpu_admission_rejects_insufficient_physical_cores(monkeypatch):
    simulated_host(monkeypatch)
    with pytest.raises(RuntimeError, match="requested 8"):
        admission.choose_idle_physical_cpus(8, excluded_cpus=[0])


def test_cpu_admission_rejects_host_floor(monkeypatch):
    simulated_host(monkeypatch, available_kib=1)
    with pytest.raises(RuntimeError, match="floor"):
        admission.choose_idle_physical_cpus(4)
