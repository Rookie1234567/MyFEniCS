# Memory report

| run | external simultaneous worker GiB | internal peak GiB | warning/stop GiB | swap in/out | stage |
|---|---:|---:|---:|---:|---|
| baseline | 1.6070 | 1.5987 | 9.5 / 11.0 | 0 / 0 | true residual |
| G4 | 2.0172 | 2.0103 | 9.5 / 11.0 | 0 / 0 | outer solve |
| G8 | 2.4192 | 2.4087 | 9.5 / 11.0 | 0 / 0 | RTA/outer plateau |
| G16 two-step | 3.2748 | 3.2682 | 9.5 / 11.0 | 0 / 0 | outer solve |
| G16 one-step | 3.2622 | 3.2523 | 9.5 / 11.0 | 0 / 0 | outer solve |

Baseline ILU storage estimate为 141,220,416 B；formal G16 exact factor为 916,096,012 B，net factor payload增加 774,875,596 B（738.98 MiB）。External peak增加约1.668 GiB还包含 portable CSR、SuperLU allocator/working storage与进程级缓存。

Census保守地把 baseline所有worker同时RSS当作单worker上界，再加最大owner exact bytes，得到1,946,000,716 B；相对约241.1 GB可用内存的50% stop line安全。该预测故意保守，正式external peak仍作为权威实测。

Exact factor memory不是未来 neural model memory。Memory-neutral learned storage参考上限为被移除的 ILU：global 134.678 MiB、每rank 33.670 MiB。
