# T40-4 bounded patch PC

## Status: not_run_by_gate

T40-4 原计划把人工截面 oracle 收缩为真正有固定局部行数上限的 patch/class factor，并
测试 owner routing。T40-3 的 mandatory rho 已失败（最小也为 14.24201480051629，最大为
28.316064601533686），所以该阶段没有运行，也没有产生 `max_local_rows`、局部 factor
容量或 patch residual 结果。

这不是 bounded local PC 已失败的证据；Task40 只证明冻结的 T40-3 transmission mechanism
不稳定。不得把该阶段写成算法负结果或据此要求 coarse space。
