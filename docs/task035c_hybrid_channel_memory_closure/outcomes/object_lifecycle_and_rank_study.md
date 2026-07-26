# Task035c 对象生命周期与 MPI rank 研究

## 1. 为什么“少了67% rows”不等于“少67%峰值内存”

矩阵行数只描述进入全局代数系统的未知量。实际进程还同时保存：

- 二维 QEP 的右/左本征向量；
- 上下三维 local FEM matrix 与 MUMPS factors；
- trace projection 与 modal coupling；
- Schur contribution；
- full-field recovery cache；
- 五个 selected planes、volume integration 和 record serialization 对象。

只要这些对象在同一时刻仍存活，峰值就不会按 rows 线性下降。Task035c 的
stage ledger 证明 static Hybrid 的峰值不是 modal Schur 本体，而是
`record_and_release` 收尾阶段。

## 2. M120/M160 stage peak

| stage | standard M120 | static M120 | standard M160 | static M160 | 解释 |
|---|---:|---:|---:|---:|---|
| cross-section eigen solve | 2.432 GiB | 2.435 GiB | 2.895 GiB | 2.891 GiB | QEP基本不受local static影响 |
| local FEM/DtN assembly | 7.244 GiB | 4.959 GiB | 7.257 GiB | 4.982 GiB | static不构造完整local p6矩阵 |
| interface projection/coupling | 7.371 GiB | 5.756 GiB | 7.858 GiB | 6.494 GiB | M增加会扩大模态/projection存储 |
| top local factor/Schur | 10.582 GiB | 6.817 GiB | 10.807 GiB | 7.215 GiB | static factor显著变小 |
| field recovery/oracle | 10.734 GiB | 7.203 GiB | 10.904 GiB | 7.599 GiB | factor与恢复对象重叠 |
| middle-plane reconstruction | 10.953 GiB | 7.421 GiB | 11.246 GiB | 7.818 GiB | selected-plane临时数组叠加 |
| record and release | 11.077 GiB | 7.544 GiB | 11.247 GiB | 7.929 GiB | 最终authority peak |

数据单位为 simultaneous worker RSS GiB，来自0.25 s采样。容器 cgroup current
在共享桌面环境中包含不属于本次 job 的进程，不能代替 dedicated-job peak；正式
authority 使用 job process tree/live worker RSS。所有正式 MPI8 路径的 job swap
均为0。

## 3. Modal coupling 的内存与时间

| M | standard coupling stage peak | static coupling stage peak | reduction | standard time | static time | time ratio |
|---:|---:|---:|---:|---:|---:|---:|
| 120 | 7.370823 GiB | 5.756237 GiB | 21.9051% | 34.714218 s | 37.340495 s | 1.075654× |
| 160 | 7.857563 GiB | 6.494362 GiB | 17.3490% | 48.192441 s | 51.869917 s | 1.076308× |

用户明确要求尽可能降低 modal coupling 内存，并取消旧 `1.25×` 时间硬限制。
当前 coupling 内存已下降，但只下降17–22%，仍低于用户希望的50%。后续优先级
应是流式/分块 interface projection 和 QEP/projection cache 生命周期，而不是
盲目增加 M。

## 4. 50%缺口的具体来源

M120 static 的 coupling stage为5.756 GiB，最终峰值7.544 GiB，两者相差
1.788 GiB。这个增量发生在 local factor保留、field recovery、middle-plane
sampling和record构造期间。因而下一轮若继续压内存，应按以下顺序：

| 优先级 | 改进 | 为什么 |
|---:|---|---|
| 1 | compact observables生成后立即销毁MUMPS KSP/factor native objects | peak出现在solve后，不需要继续为只读后处理保留全部factor |
| 2 | selected planes逐平面、modal volume逐z-block streaming | 避免完整middle reconstruction数组与factor/QEP共存 |
| 3 | record写出采用增量compact serializer | 避免末端同时保留完整嵌套Python record和large native payload |
| 4 | QEP right/left modes与projection分批/cache-on-disk | M160 coupling stage比M120增加0.738 GiB |
| 5 | 在现有per-rank PSS/USS上增加native-object release事件 | PSS/USS已可拆分shared/private pages，但仍缺native对象创建/销毁时间 |

同 M120 standard 的50%目标是 `<=5.538446 GiB`。static coupling阶段本身
已经高出该值约`0.218 GiB`，factor/Schur阶段又高出约`1.278 GiB`。所以
`record_and_release`前的简单释放只能降低最终7.544 GiB峰值，不能让完整运行
达到50% Gate。真正可行的下一步至少要同时实现：

- interface projection/coupling 的 mode-block streaming；
- bottom factor→Schur contribution→释放与 top factor 的错峰，或可复算的
  顺序 recovery；
- 在不保留两个local factor的条件下完成modal solve和完整场恢复。

这些属于资源算法重构，不是无数值影响的收尾清理。它会改变六路径的同源码
资源身份，需要重新运行Full3D standard/static及Hybrid M120/M160
standard/static；本轮不以低风险优化名义无依据重复整批heavy authority。

## 5. 历史 PSS/USS 回填与口径

原始六条 MPI8 timeline 实际保存了逐 rank `/proc/<pid>/smaps_rollup`。
本次 compact 回填没有重跑 PDE，也没有从 RSS 推算 PSS/USS。生成器只接受
rank 0–7 同一时刻全部可读的样本，排除启动/退出阶段的部分可读记录，并分别在
各自时间序列上选取 PSS 与 USS 峰值：

| path | qualified samples | PSS GiB | USS GiB |
|---|---:|---:|---:|
| Full3D standard/static | 7,617 / 818 | 32.298626 / 12.806003 | 32.047173 / 12.602608 |
| Hybrid standard/static M120 | 2,990 / 1,071 | 9.440656 / 5.769862 | 9.200600 / 5.491413 |
| Hybrid standard/static M160 | 3,215 / 1,294 | 9.610866 / 6.169376 | 9.370529 / 5.888676 |

对应 Hybrid M120 的 PSS/USS 降幅为 `38.8828%/40.3146%`，M160 为
`35.8083%/37.1575%`。这是诊断性共享页/私有页分解；正式 Task035c 相对内存
Gate 仍以原 campaign 的 simultaneous process-tree/live-worker RSS 为权威，
以保持冻结的采样合同。ledger 见
[`p6_h10_mpi8_pss_uss_ledger_v1.json`](../../../benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_pss_uss_ledger_v1.json)。

## 6. MPI1/2/8 rank结果

### Full3D static

| MPI | peak GiB | base build s | linear solve s | total s | numerical/resource status |
|---:|---:|---:|---:|---:|---|
| 1 | 6.165108 | 475.615703 | 733.060727 | 1256.061048 | formal pass |
| 2 | 8.159409 | 282.173065 | 384.547361 | 701.613428 | formal pass |
| 8 | 14.721756 | 92.631094 | 143.372679 | 260.736180 | formal pass |

更少 rank 降低进程复制内存，但显著增加装配和MUMPS时间。MPI1是本批
Full3D static最低实测峰值，不是理论下限。

### Hybrid static M120

| MPI | measured peak | total | physical observables | Gate failure | status |
|---:|---:|---:|---|---|---|
| 1 | 1.751698 GiB | 1328.717195 s | 12/12+12/12、residual/field pass | positive QEP biorthogonality `1.1975997613e-6 > 1e-6` | controlled numerical negative |
| 2 | 3.141788 GiB | 798.201321 s | numeric chain、12/12+12/12 pass | terminal worker drain RSS/swap readability false | controlled resource-authority negative |
| 8 | 7.544262 GiB | 322.781788 s | all pass | none | formal authority |

MPI1失败的是明确数值Gate，MPI2失败的是明确资源采样Gate。两点都不能被后续
MPI8成功追溯性覆盖。连续两个独立负信号后关闭rank lane，MPI4按停止规则不运行。

## 7. Raw/compact evidence

| 记录 | SHA-256 / status |
|---|---|
| `p6_h10_full_static_mpi1_244b62e.json` | `36cde9b87732277d91d9f9924e7a9a91671bc98ec74d949c0c1d14adce11a894` |
| `p6_h10_hybrid_static_m120_mpi1_244b62e.json` | `e99cda1de21e6bbe7a8787eda268d4498565420f8a32d662f6456a919d6ca27e`；numeric fail |
| `p6_h10_full_static_mpi2_244b62e.json` | `6b045a1475e1f9d4b9d6e7b2e3bd41c6501f7312879228df3fb5b4fdfdcd225c` |
| `p6_h10_hybrid_static_m120_mpi2_244b62e.json` | `5a0ef31775d307c09ccf6b7e3fcb5fc523c6b9cba0531f9b298a938901e2bf5b`；resource nonformal |
| compact rank ledger | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_static_rank_study_v1.json` |
| compact PSS/USS ledger | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_pss_uss_ledger_v1.json`；historical smaps backfill pass |

没有运行MPI4、没有删除任何失败记录、没有把非正式峰值写成资源下限。
