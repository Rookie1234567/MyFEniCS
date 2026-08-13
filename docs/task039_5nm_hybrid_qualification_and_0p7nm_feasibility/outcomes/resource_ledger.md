# Task39 T3 资源账本

本账本区分三种不同口径：RSS 是同时进程树的 resident memory；PSS 是按共享页
分摊后的进程树占用；USS 是进程树独占页。三者的峰值可以出现在不同采样点，
所以不能把它们当成同一时刻的一个向量。T3 使用既有 0.25 s watchdog sampling；
PSS/USS 只作诊断，不参与 hard-stop。

## 1. T3 measured authority

| 指标 | measured 值 | 口径/判定 |
| --- | ---: | --- |
| simultaneous process-tree RSS peak | 15965.453125 MiB | authority peak |
| independent process-tree PSS peak | 13932.458984375 MiB | complete smaps samples |
| independent process-tree USS peak | 13611.3515625 MiB | complete smaps samples |
| attempted/complete smaps samples | 920 / 918 | 2 个边缘 sample 不完整，但 complete>0 |
| telemetry status | measured | per-metric independent peaks |
| process-tree swap peak | 0 MiB | zero-swap requirement pass |
| warning triggered / termination | false / none | 未触发资源终止 |

当前运行前 capacity 为 228.0657501220703 GiB；warning=180 GiB，configured
hard=220 GiB，derived effective hard=min(220,0.90*228.0657501220703)
=205.2591751098633 GiB。T3 的 process-tree RSS 峰值远低于该硬停止边界。

solver rank 的 sum_rank_historical_peaks_upper_bound 为 15438.6640625 MiB；
这是跨 rank 历史峰值求和的上界，不是 simultaneous process-tree RSS，不能和
上表混称或用于声称节省比例。

## 2. 线性代数与阶段时间

| 项目 | 值 | 分类 |
| --- | ---: | --- |
| condensed matrix NNZ | 43283050 used / 47719324 allocated | measured raw summary |
| MUMPS factor NNZ | 217041864 | measured factor inventory |
| DtN assembly | 91.268220 s | measured |
| KSP setup/factor phase | 129.608784 s | measured |
| KSP solve | 0.199135 s | measured |
| postprocess | 8.928812 s | measured |
| total numerical elapsed | 283.036048 s | measured |
| outer run wall | 290.480347 s | measured from manifest |

## 3. Evidence boundary

T3 compact record 为
[task039_t3_full3d_direct_mpi8_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json)。
原始资源/进度文件仍在 ignored results 目录，不进入 Git。outer summary SHA 为
c8b4d0ab14b96665cb07e8a51bd479f3f26c14be552a98acf80f5b250df697cb，
numerical summary SHA 为
8e99f51fab57a184b393927c22a4be0b2b48b45939be480540c3f0fbf1c01ce0，
progress timeline SHA 为
05405559b994476c905be0a9a749a9b60bdacc911426c990ca84e40e956f1ba5。

前两次尝试仍按 configuration failure 和 evidence incomplete 保留，不能用本次
measured resource 覆盖其历史边界。

## 4. T4 Full3D iterative：数值负结果资源记录

T4 的正式迭代运行在 4000 步达到 `DIVERGED_MAX_IT(-3)`，因此下面的资源是
一次真实负结果运行的 measured telemetry，不是成功求解的资格化资源上限。

| 指标 | measured 值 | 口径/判定 |
| --- | ---: | --- |
| simultaneous process-tree RSS peak | 12031.03125 MiB | 进程树同时 RSS 峰值 |
| independent process-tree PSS peak | 10738.3857421875 MiB | complete smaps samples；独立 per-metric peak |
| independent process-tree USS peak | 10534.84765625 MiB | complete smaps samples；独立 per-metric peak |
| attempted/complete smaps samples | 8259 / 8257 | complete>0，telemetry status measured |
| process-tree swap peak | 0 MiB | zero-swap pass |
| warning / termination | false / none | 未触发资源终止 |
| effective hard stop | 205.2591751098633 GiB | derived `min(220, 0.90 × 228.0657501220703)` |
| solver-rank historical peak sum | 11984.98828125 MiB | 历史上界，不是 simultaneous process-tree RSS |

RSS、PSS、USS 的峰值可能出现在不同完整 sample，不能合并成同一时刻的
内存向量。T4 的 `task039_m3a_core_audit.json` 是独立 raw audit；其未嵌入
summary 的证据缺口单独记录，不改变数值负分类。详细 raw 路径和 SHA 见
[T4 negative record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json)。

## 5. T5 Hybrid direct M-convergence measured resources

T5 四次正式候选均使用既有 0.25 s watchdog。下表的 RSS/PSS/USS 是同一进程树在
完整可读 sample 上分别取出的独立峰值；它们可能来自不同 sample。PSS/USS 是诊断
覆盖，不参与 hard-stop。四次候选均 `swap=0`，没有发生 warning 或资源终止。

| M | outer wall (s) | simultaneous process-tree RSS (MiB) | independent PSS (MiB) | independent USS (MiB) | swap (MiB) | smaps attempted/complete |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 432.931447 | 8929.0625 | 7154.639648 | 6870.980469 | 0 | 1443/1439 |
| 240 | 815.862600 | 10999.851563 | 9222.426758 | 8938.285156 | 0 | 2642/2640 |
| 480 | 1468.884482 | 22798.082031 | 21039.913086 | 20758.953125 | 0 | 4368/4365 |
| 960 | 4812.858962 | 22536.339844 | 21407.276367 | 21222.859375 | 0 | 12594/12592 |

M960 在 canonicalized negative trace authority 处以
`raw_relative_error=1.678e-11 > 1e-12` 停止；其资源是一次真实 authority negative
run 的 measured telemetry，不是成功求解的资源上限。T5 的完整身份、阶段时间和每次
raw file SHA 见
[T5 Hybrid direct convergence record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)。
