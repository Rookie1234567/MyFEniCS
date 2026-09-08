"""Small, explicit clock gate for bounded physical diagnostics."""
import math
import time

STRICT = 'strict'
CONSERVATIVE_REALTIME = 'conservative_realtime'
POLICY_VERSION = 1


class TimebaseInconsistency(RuntimeError):
    pass


def clock_sample():
    return dict(monotonic=time.monotonic(),
                boottime=time.clock_gettime(time.CLOCK_BOOTTIME)
                if hasattr(time, 'CLOCK_BOOTTIME') else None,
                utc_ns=time.time_ns())


def clock_info():
    return dict(monotonic=vars(time.get_clock_info('monotonic')),
                utc=vars(time.get_clock_info('time')),
                boottime=dict(available=hasattr(time, 'CLOCK_BOOTTIME'),
                    implementation='clock_gettime(CLOCK_BOOTTIME)',
                    resolution=time.clock_getres(time.CLOCK_BOOTTIME)
                    if hasattr(time, 'CLOCK_BOOTTIME') else None))


def budget_elapsed(start, end):
    """Use both monotone clocks for deadlines, including stop grace."""
    return max(end[k]-start[k] for k in ('monotonic', 'boottime')
               if start.get(k) is not None and end.get(k) is not None)


def checked_interval(start, end, *, policy=STRICT):
    """Keep strict semantics; diagnostic opt-in charges adjustable UTC conservatively."""
    if policy not in (STRICT, CONSERVATIVE_REALTIME):
        raise ValueError('unknown clock policy')
    if start.get('boottime') is None or end.get('boottime') is None:
        raise TimebaseInconsistency('CLOCK_BOOTTIME unavailable; dual budget unqualified')
    elapsed = {k: end[k]-start[k] for k in ('monotonic', 'boottime')}
    elapsed['utc'] = (end['utc_ns']-start['utc_ns'])/1e9
    monotone = [elapsed[k] for k in ('monotonic', 'boottime')]
    if (not all(math.isfinite(v) for v in elapsed.values()) or
            min(monotone) < 0 or (policy == STRICT and elapsed['utc'] < 0)):
        raise TimebaseInconsistency(f'nonfinite/backwards clock interval: {elapsed}')
    compared = list(elapsed.values()) if policy == STRICT else monotone
    tolerance = max(5., .01*max(compared))
    if max(compared)-min(compared) > tolerance:
        raise TimebaseInconsistency(f'unexplained clock disagreement: {elapsed}; tolerance={tolerance}')
    charge = budget_elapsed(start, end)
    if policy == CONSERVATIVE_REALTIME:
        charge = max(charge, elapsed['utc'], 0.)
    return dict(elapsed_seconds=elapsed, budget_seconds=charge,
                discrepancy_seconds=max(elapsed.values())-min(elapsed.values()),
                tolerance_seconds=tolerance, policy=policy, policy_version=POLICY_VERSION,
                utc_minus_monotonic_seconds=elapsed['utc']-elapsed['monotonic'])


class ClockBudget:
    """Accumulate adjacent intervals; forward UTC adjustments are never refunded."""

    def __init__(self, start, *, policy=STRICT):
        self.start = self.previous = start
        self.policy = policy
        self.seconds = 0.
        self.utc_positive_excess_seconds = 0.

    def update(self, end):
        total = checked_interval(self.start, end, policy=self.policy)
        step = checked_interval(self.previous, end, policy=self.policy)
        self.seconds = (self.seconds + step['budget_seconds']
                        if self.policy == CONSERVATIVE_REALTIME else total['budget_seconds'])
        dt = step['elapsed_seconds']
        self.utc_positive_excess_seconds += max(0., dt['utc']-max(dt['monotonic'], dt['boottime']))
        self.previous = end
        # Both the cumulative and adjacent monotone gates remain active.
        return dict(total, budget_seconds=self.seconds, step=step,
                    utc_positive_excess_seconds=self.utc_positive_excess_seconds)
