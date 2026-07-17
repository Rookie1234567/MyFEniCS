# P1：16-slab raw capture 与 LU teacher

## 结论

P1 Gate **通过（16/16）**。四次独立 clean baseline capture 的样本数、算子身份和
split 独立性均满足合同；16 个 slab 均以 one-factor/many-RHS、最大 64 RHS 的有界批次
生成 LU teacher，精度、资源、factor destroy 和 no-swap Gate 全部通过。

本结论只资格化离线数据与 teacher，不代表 learned local inverse、runtime 或全局
factor-removal Gate 已通过。下一阶段按任务书进入 P2 representative screen。

## Provenance 与执行合同

| 项目 | 结果 |
|---|---|
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |
| capture clean commit | `a141c8e41527609e51dcfe35af06382f05cc3463` |
| teacher implementation commit | `92dcc40` |
| capture runs | T1、T2、V、H 四次独立 clean baseline |
| baseline solve identity | 每次 852 iterations；reported residual `9.980248132e-7` |
| RTA closure | 每次 `-1.859745e-9` |
| teacher ordering / pivot | SuperLU `COLAMD` / diagonal pivot threshold `1.0` |
| teacher execution | slab 0→15 严格顺序；同一时刻一个 factor |
| RHS execution | 1536 RHS/slab；24 batches/slab；最多 64 RHS/batch |
| CPU thread policy | OMP/OpenBLAS/MKL/NumExpr 均为 1 |
| full teacher wall | 430.304 s |
| heavy artifact policy | `benchmarks/artifacts/cases/094/` 被 `.gitignore` 命中 |

## Capture 数量与独立性

| split | 采样规则 | 每 slab 数量 | 16 slabs 总数 | 角色 |
|---|---:|---:|---:|---|
| T1 | stride 8, offset 0 | 512 | 8192 | train |
| T2 | stride 8, offset 4 | 512 | 8192 | train |
| V | stride 16, offset 2 | 256 | 4096 | validation |
| H | stride 16, offset 6 | 256 | 4096 | holdout |
| 合计 | 互斥 apply-index schedules | 1536 | 24576 | — |

泄漏审计在 GPU 0 上使用 deterministic 256-dimensional complex JL screen，并对
screen argmax 做 exact check。审计结果如下。

| 检查 | 结果 | Gate |
|---|---:|---|
| 16 个 operator fingerprints 跨 T1/T2/V/H 精确稳定 | 16/16 | PASS |
| 期望样本数完整 | 16/16 | PASS |
| split 间 apply-index overlap | 0 | PASS |
| exact RHS duplicates | 0 | PASS |
| near-duplicate pairs（threshold `0.99999999`） | 0 | PASS |
| raw-only payload；无 ILU/current-PC correction | 是 | PASS |

## Teacher Gate 汇总

| 指标 | 实测 | 要求 | 结论 |
|---|---:|---:|---|
| datasets 完整 | 16/16 | 16/16 | PASS |
| finite targets | 16/16 | 16/16 | PASS |
| 全 slab 最坏 `median rho_teacher` | `5.905e-15` | `<= 1e-11` | PASS |
| 全 slab 最坏 `p95 rho_teacher` | `7.469e-15` | `<= 1e-10` | PASS |
| 全局 `max rho_teacher` | `1.050e-14` | `<= 1e-9` | PASS |
| fingerprint exact match | 16/16 | 16/16 | PASS |
| factor destroyed | 16/16 | 16/16 | PASS |
| swap in/out delta | 0 / 0 pages | 0 / 0 | PASS |
| heavy artifacts ignored | 是 | 必须 | PASS |

## 逐 slab 资源与精度

完整机器可读表见 `p1_teacher_summary.csv`。表中时间为每 RHS 的摊销时间；峰值 RSS
包含读取 1536 RHS、target、残差验证与压缩写盘，不等同于持久 runtime 模型内存。

| slab | n | matrix nnz | fill | factor MiB | factor s | solve mean / p95 ms | rho max | peak RSS MiB |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 3670 | 354148 | 4.537 | 30.705 | 0.254 | 2.570 / 2.653 | `7.508e-15` | 600.08 |
| 1 | 5248 | 526696 | 7.783 | 78.267 | 0.983 | 6.536 / 6.662 | `1.031e-14` | 900.52 |
| 2 | 5248 | 526696 | 7.783 | 78.267 | 0.902 | 6.518 / 6.657 | `1.009e-14` | 900.87 |
| 3 | 3670 | 354148 | 4.595 | 31.091 | 0.223 | 2.609 / 2.661 | `7.727e-15` | 599.93 |
| 4 | 3670 | 354148 | 4.520 | 30.588 | 0.203 | 2.510 / 2.604 | `7.430e-15` | 600.32 |
| 5 | 5248 | 526696 | 7.783 | 78.267 | 0.913 | 6.442 / 6.613 | `1.050e-14` | 901.24 |
| 6 | 5248 | 526696 | 7.783 | 78.267 | 1.106 | 6.905 / 9.694 | `1.010e-14` | 900.68 |
| 7 | 3670 | 354148 | 4.595 | 31.094 | 0.234 | 2.497 / 2.770 | `7.553e-15` | 599.78 |
| 8 | 3670 | 354148 | 4.562 | 30.872 | 0.256 | 2.683 / 3.620 | `7.498e-15` | 600.70 |
| 9 | 5248 | 526696 | 7.783 | 78.267 | 0.959 | 7.273 / 9.217 | `1.031e-14` | 901.25 |
| 10 | 5248 | 526696 | 7.783 | 78.267 | 0.842 | 8.431 / 12.654 | `1.016e-14` | 901.10 |
| 11 | 3670 | 354148 | 4.595 | 31.096 | 0.204 | 2.561 / 2.994 | `7.739e-15` | 599.20 |
| 12 | 3670 | 354148 | 4.579 | 30.985 | 0.215 | 2.325 / 2.553 | `7.757e-15` | 601.08 |
| 13 | 5248 | 526696 | 7.783 | 78.267 | 0.950 | 7.337 / 10.419 | `9.875e-15` | 900.62 |
| 14 | 5248 | 526696 | 7.783 | 78.267 | 0.809 | 7.186 / 9.487 | `9.943e-15` | 900.90 |
| 15 | 3670 | 354148 | 4.594 | 31.089 | 0.146 | 2.218 / 2.797 | `9.378e-15` | 600.07 |

## 汇总统计

| 指标 | min | median | max |
|---|---:|---:|---:|
| factorization, s | 0.146 | 0.533 | 1.106 |
| amortized solve mean, ms/RHS | 2.218 | 4.562 | 8.431 |
| solve p95, ms/RHS | 2.553 | 5.116 | 12.654 |
| factor storage, MiB | 30.588 | 54.682 | 78.267 |
| factor nnz | 1,600,779 | 2,863,324.5 | 4,099,256 |
| dataset, MiB | 151.90 | 184.62 | 217.28 |
| process peak RSS, MiB | 599.20 | 750.80 | 901.25 |

## 卡住事件与处置

首次 teacher 实现逐 RHS 调用 SuperLU，slab 1 呈现长时间高 CPU，属于算法粒度过细而非
死锁。该运行被安全停止并保存在
`teacher/datasets_rejected_scalar_rhs_slow`；随后改为 Fortran-order 多 RHS、最大 64
的有界批次。slab 0 探针将 1536 RHS 的 solve 总时降至约 4.00 s，且批量/逐条结果在
`rtol=atol=1e-14` 下相符。正式 16-slab 构建随后连续完成，没有 swap 或 stalled
process。

另一次 WSL 启动故障由两条旧诊断进程持有 VM 引起。清理明确的旧 `grep`/SCOTCH
probe 进程并重启 WSL 服务后，原有 `C:\WSL\Ubuntu-24.04\ext4.vhdx` 原地恢复；
未重装环境、未复制或删除虚拟磁盘。

## 产物位置

| 内容 | Git 策略 | 路径 |
|---|---|---|
| T1/T2/V/H captures | ignored | `benchmarks/artifacts/cases/094/captures/` |
| leakage audit | ignored | `benchmarks/artifacts/cases/094/audits/capture_leakage.json` |
| 16 teacher datasets | ignored | `benchmarks/artifacts/cases/094/teacher/datasets/` |
| all-slab raw summary | ignored | `benchmarks/artifacts/cases/094/teacher/datasets/summary.json` |
| rejected slow run | ignored | `benchmarks/artifacts/cases/094/teacher/datasets_rejected_scalar_rhs_slow/` |
| lightweight P1 CSV | tracked | `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/p1_teacher_summary.csv` |

## Gate 决策

`P1 = PASS`。允许开始 P2：在冻结的 R4 representative slabs 上执行 D0/D1、
Lane A/Lane B、CPU/GPU、independent/owner-like batch screen。P2 结果不得外推为
16-slab 或 full-solve 成功。
