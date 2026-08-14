# Review V2：h5 Full3D direct readiness

## V2-1 结论

V2-1 是正式运行前的资格检查，不是 h5 求解结果。当前代码已提交于
`c26debf71d2a7b76bcf9b9715412063682b091b0`；validate-only、dry-run、ABI、资源、整数宽度和
轻量测试均通过，因此状态为 **conditional ready**。唯一正式 h5 PDE 仍未运行。

| Gate | 当前状态 | 证据口径 |
| --- | --- | --- |
| 输入身份 | pass | p6/h5、5 nm、S、10°、Full3D direct、MPI8 |
| external inventory | pass | 604 keys exact；bottom/top=300/304 |
| host capacity | pass | MemAvailable=224.432 GiB；disk free=772.330 GiB；swap used=0 |
| watchdog policy | pass | warning 170 GiB；critical 195 GiB；absolute termination=224000000000 bytes |
| integer-width audit | conditional | matrix rows/NNZ低于32位；factor NNZ预测超过32位，但 MUMPS 计数字段为64位 |
| h5 formal own Gate | pass | V2-2 唯一正式 run 完成；own residual、official dtn-port、604 keys、字段和资源 Gate 通过 |
| h5 grid comparison | pending / not_run | V2-3 尚未授权；不把 h5 与 h6 拼成收敛结论 |

完整机器字段与测试入口见 [V2-1 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_readiness_v1.json)。

## 资源与 watchdog 两条线

watchdog 同时观察进程树内存和交换空间。170 GiB 是 warning；195 GiB 是 critical
checkpoint。启用该路径后全程以不大于 0.25 秒的 poll interval 采样；跨越 195 GiB 只记录
crossing 并维持该频率，不自动停止。用户明确覆盖 Review
原 hard stop 后，真正的绝对终止线是精确的 224,000,000,000 bytes（约 208.6162567138672
GiB）；任何 swap 使用仍立即终止。启用这条 absolute-byte 路径时 poll interval 必须不大于
0.25 秒；旧输入缺少该字段时，原有 `min(terminate_memory_gib, 0.90 * selected limit)`
行为保持不变。

```math
\frac{224000000000\ \mathrm{bytes}}{2^{30}}
=208.6162567138672\ \mathrm{GiB}.
```

195 GiB 不再是自动终止并不代表资源安全；它是一个可审查的临界点，绝对终止线和 swap
规则仍然有效。

## 整数宽度风险的通俗解释

整数宽度决定程序能否给矩阵的行号、非零元数量和因子结构编号分配足够大的编号。当前
PETSc 使用 32-bit row/index；MUMPS 构建为 `MUMPS_INTSIZE32`，但其 `nnz` 与 `nnz_loc`
字段使用 64-bit `MUMPS_INT8`。因此 h5 预测的矩阵 rows/NNZ 低于 `INT32_MAX`，factor
NNZ 超过 `INT32_MAX` 本身不能直接判定失败；不过 factor 的所有内部索引、工作区和运行时
路径没有被正式 h5 factorization 证明，仍标为 `not_established`。这正是 conditional
ready 而不是 numerical pass 的原因。

## h5 capacity 证据

| 项目 | 值 | 分类 |
| --- | ---: | --- |
| cells / full FE DoFs | 1680 / 1,127,502 | measured mesh-only topology（E4 probe） |
| Floquet constraints / interior DoFs per cell | 34,542 / 450 | measured mesh-only topology |
| active trace / assembled rows (+604) | 336,960 / 337,564 | derived from measured topology |
| matrix NNZ range | 284,060,255–378,660,436 | predicted from h6 calibration |
| factor NNZ range | 2,336,792,702–3,115,011,438 | predicted；跨过 32-bit 上限 |
| factor values-only | 52.23–69.63 GiB | derived complex128 envelope；不含 indices/workspace |
| process-tree RSS prediction | 90.09–150.11 GiB | predicted；不是 formal peak |

预测使用 h6 measured anchor 与网格拓扑比例，不能冒充 h5 实测。V2 用户规则明确不因
“预测峰值超过 195 GiB”单独阻止启动；本次 host 仍满足 MemAvailable≥200 GiB、disk≥20
GiB、604 keys、validate/dry-run、integer ABI、single-heavy 前置条件。

## h10 边界与后续阶段

h10 只能称 `historical_underresolved_stress_anchor_only`。它不得进入 Full3D 5 nm
reference、Hybrid physical authority、accuracy-qualified 结论或 0.7 nm mesh-scaling。
因此本页不把 h10 与 h5 拼成收敛证明。

| 阶段 | 状态 | 原因 |
| --- | --- | --- |
| V2-1 readiness | conditional pass | 本页及 compact record 已完成 |
| V2-2 h5 Full3D direct + own Gate | pass | h5 Full3D discrete authority 已建立；不等于网格收敛 |
| V2-3 h5 comparison / convergence | pending / not_run | 尚未授权，等待后续明确拆解 |

历史结论和 Review V2 inherited audit 仍见 [summary](summary.md)、[resource ledger](resource_ledger.md)
与 [V2-0 audit](review_v2_inherited_audit.md)。

## V2-2：h5 Full3D direct 正式 own-Gate

V2-2 按冻结的 p6/h5、5 nm、Full3D direct、MPI8 输入只运行一次。正式 worker 以
`exit_status=0` 完成；本节的 PASS 只表示这次 h5 离散运行自身的资格 Gate 通过，不能把
h5 称为 h6-vs-h5 convergence reference，也没有启动 V2-3。

| Gate / 观测 | measured 结果 | 状态与边界 |
| --- | ---: | --- |
| true relative residual | `1.1426908495328136e-10`（limit `1e-9`） | pass |
| official dtn-port R/T/A_balance/A_volume | `0.0020255498177907264 / 0.02845408887668467 / 0.9695203613055247 / 0.9695203613041327` | official；不使用 diagnostic EH Fourier/采样 net-flux 代替 |
| closure | `-1.3919976282750213e-12`（absolute limit `1e-5`） | pass |
| dynamic external inventory | `604` exact unique；bottom/top=`300/304`；beta 与 amplitudes 全部 finite | pass |
| selected E/H | 5 planes `[10,30,60,90,110]`；E/H shape=`[5,20,40,3]`；complex128、finite | pass；per-plane `finite_pass` 为数组重算状态 |
| canonical export | active trace `371502` packets；full FE `1127502` packets；各 8 shards、duplicates=0 | pass |
| official result identity | `official_result=true`、`case_status=completed`、classification=`worker_exit0` | run-level pass；`physical_benchmark_candidate=false` 仍保留 |

资源 watchdog 的 measured process-tree 峰值为 RSS/PSS/USS=`92491.328 / 90440.785 /
90103.539 MiB`，swap=`0 MiB`；warning=`170 GiB`、critical checkpoint=`195 GiB` 均未
cross，absolute hard=`224000000000 bytes`（约 `208.6162567138672 GiB`）未触发。数值耗时
为 `5330.2902718020005 s`，其中 KSP setup/factorization=`4748.209038352999 s`，KSP
solve=`2.743420086999322 s`，postprocess=`61.98816714599889 s`。

本次 measured mesh/矩阵口径为 cells=`1680`、full FE DoFs=`1127502`、active trace=`336960`、
assembled rows with auxiliary=`337564`，condensed matrix NNZ used/allocated=`283210150/298136764`。MUMPS
因子遥测保留 raw int32 溢出：raw INFOG(9)=`-2597`、raw matrix NNZ=`-1697967296`；修正显示
`factor_nnz_corrected=2597000000`，仅作为 telemetry，不修改运行结果、不触发重跑。

完整 compact authority、输入/源码/解析配置/物理身份和 artifact SHA 见
[V2-2 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_full3d_direct_v1.json)。
