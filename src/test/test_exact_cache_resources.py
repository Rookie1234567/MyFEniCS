from benchmarks.summarize_exact_cache_resources import summarize


def sample(timestamp, rss, worker_rss):
    return {
        "timestamp_ns": timestamp,
        "rss_bytes": rss,
        "swap_bytes": 0,
        "resource_policy_observations": {"effective_available_bytes": 10**12},
        "all_status_readable": True,
        "warning": False,
        "members": [
            {"cmdline": "parallel_tensor_cache.py --job a", "rss_bytes": n}
            for n in worker_rss
        ],
    }


def test_resource_summary_uses_simultaneous_samples_and_exact_interval():
    samples = [
        sample(0, 9999, [9999]),
        sample(10, 120, [100, 20]),
        sample(20, 120, [20, 100]),
        sample(30, 9999, [9999]),
    ]
    result = summarize(samples, 10, 20)
    assert result["simultaneous_tree_rss_peak_bytes"] == 120  # Not 100 + 100.
    assert result["maximum_live_exec_workers"] == 2
    assert summarize(samples, 11, 19)["status"] == "NOT_SAMPLED"


def test_monotonic_join_ignores_cached_numa_timestamps():
    first = {
        **sample(0, 10, []),
        "elapsed_seconds": 0.1,
        "node_memory_observation": {"sampled_monotonic": 100.1},
    }
    later = {
        **sample(1, 20, []),
        "elapsed_seconds": 2.1,
        "node_memory_observation": {"sampled_monotonic": 100.1},
    }
    result = summarize([first, later], 102.0, 102.2, monotonic=True)
    assert result["samples"] == 1
    assert result["simultaneous_tree_rss_peak_bytes"] == 20
