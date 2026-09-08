"""Small, explicit clock gate for bounded physical diagnostics."""
import math
import time


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


def checked_interval(start, end):
    """Compare the same interval; UTC remains diagnostic, never a replacement."""
    if start.get('boottime') is None or end.get('boottime') is None:
        raise TimebaseInconsistency('CLOCK_BOOTTIME unavailable; dual budget unqualified')
    elapsed = {k: end[k]-start[k] for k in ('monotonic', 'boottime')}
    elapsed['utc'] = (end['utc_ns']-start['utc_ns'])/1e9
    if not all(math.isfinite(v) and v >= 0 for v in elapsed.values()):
        raise TimebaseInconsistency(f'nonfinite/backwards clock interval: {elapsed}')
    tolerance = max(5., .01*max(elapsed.values()))
    if max(elapsed.values())-min(elapsed.values()) > tolerance:
        raise TimebaseInconsistency(f'unexplained clock disagreement: {elapsed}; tolerance={tolerance}')
    return dict(elapsed_seconds=elapsed, budget_seconds=budget_elapsed(start,end),
                discrepancy_seconds=max(elapsed.values())-min(elapsed.values()),
                tolerance_seconds=tolerance)
