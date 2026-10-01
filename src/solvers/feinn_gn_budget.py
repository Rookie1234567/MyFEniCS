"""Measured-cost work frontier; never accepts a partial, unverified GN step."""

from time import perf_counter


class GNWorkBudget:
    def __init__(
        self, problem, cutoff, caps, emit, stop_exception, *, initial_K_seconds=1.0
    ):
        self.problem, self.cutoff, self.caps = problem, cutoff, caps
        self.emit, self.stop_exception = emit, stop_exception
        self.recent_K = [max(initial_K_seconds, 0.001)]
        self.recent_trial = [1.0]
        self.events = {}
        self.costs = {}

    def observe(self, kind, seconds):
        target = self.recent_K if kind == "K" else self.recent_trial
        target.append(seconds)
        del target[:-16]

    def allow(self, *, K=0, trial=0):
        p = self.problem
        # The cutoff itself already reserves 150 s for audit and safe storage.
        reserve = (
            1.5 * max(self.recent_K) * K + 1.5 * max(self.recent_trial) * trial + 5
        )
        return bool(
            perf_counter() + reserve < self.cutoff
            and p.counts["K"] + K <= self.caps["K"]
            and sum(p.jac.counts.values()) + 2 * K <= self.caps["JVP_VJP"]
            and p.counts["trial_loss"] + trial <= self.caps["trial"]
        )

    def event(self, kind, phase, **facts):
        now = perf_counter()
        seconds = None
        if phase == "begin":
            self.events[kind] = now
        elif kind in self.events:
            seconds = now - self.events.pop(kind)
            self.costs[kind] = self.costs.get(kind, 0) + seconds
        self.emit(
            dict(
                kind="WORK_EVENT", operation=kind, phase=phase, seconds=seconds, **facts
            )
        )

    def record(self):
        return dict(
            incomplete=list(self.events),
            costs_nested_seconds=self.costs,
            conservative_recent_K_seconds=max(self.recent_K),
            recent_trial_seconds=max(self.recent_trial),
            cutoff_monotonic=self.cutoff,
        )
