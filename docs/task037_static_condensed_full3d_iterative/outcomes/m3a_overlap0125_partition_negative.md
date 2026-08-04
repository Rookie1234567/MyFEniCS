# M3a overlap-0.125 partition-weighted Screen-20：资源负证据

## 结论

本记录对应唯一一次 p6/h10、S 偏振、MPI8、20-step Screen-20。它是
Task37 执行分支上的 research-only screen，不是 production/full solver success，
也不是正式物理结果。结构、no-global 和早期数值下降 Gate 通过；唯一失败是
process-tree memory authority 超过 10.30 GiB。因此 official RTA 为 `not_run`，
不得将本次结果称为 production-qualified。

| Gate | 结果 | 证据 |
|---|---|---|
| source/branch/clean | pass | `89f3b745`，执行后 source clean |
| no-global A/F/direct factor | pass | runtime nested audit |
| overlap/partition/slab structure | pass | 16 slabs，overlap `0.125` |
| factor NNZ reduction | pass | `91,415,952 < 103,336,560` |
| residual decline | pass | reported 与 condensed true 均严格下降 |
| resource `<=10.30 GiB` | **fail** | `11.736686706542969 GiB` |
| official RTA | not run | 20 步未收敛，`DIVERGED_MAX_IT` |

## 身份、authority 与 artifact

| 项目 | 值 |
|---|---|
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| source/verified clean SHA | `89f3b7459e0e4ec8e8abbf73b3d3cd2de1327e7a` |
| source after | clean，HEAD/upstream 一致，ahead/behind `0/0` |
| model | p6 / h10 / 13.5 nm / theta normal 80° / phi 0° / S |
| MPI/backend | MPI8 / `assembly_time_static_condensed` |
| run | `--task037-f3-screen 20 --task037-m2c-never-materialized --task037-m3a-overlap0125-partition` |
| limits | warning 10 GiB / terminate 14 GiB / timeout 1800 s / swap 0 |
| Task035c authority | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json` |
| authority SHA256 | `96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8` |
| artifact | `benchmarks/artifacts/task037/m3a_overlap0125_partition_screen20_p6_h10_mpi8_89f3b745` |
| worker return code | `0` |
| watchdog status/outer code | `task037_m3a_overlap0125_partition_screen_not_pass` / `2` |

实际 worker 命令由 `watchdog_summary.json` 固化；其核心身份为：

```text
mpiexec -n 8 /home/Projects/MyFEniCS/.venv/bin/python -m
benchmarks.run_task033_full3d_watchdog --degree 6 --h-nm 10
--polarization-kind s --run-kind full-solve --mpi-size 8
--stage4-full3d-assembly-backend assembly_time_static_condensed
--task035c-p6-h10-gate --task037-f3-screen 20
--task037-m2c-never-materialized --task037-m3a-overlap0125-partition
--verified-clean-sha 89f3b7459e0e4ec8e8abbf73b3d3cd2de1327e7a
```

原始记录包括 `watchdog_summary.json`、`run_summary.json`、
`task037_f3_core_audit.json`、`progress_3d.jsonl`、`memory_timeline.csv`、
`task037_f3_residual_history.jsonl` 与 `worker_stdout.txt`；未修改 raw evidence。

## 结构与 no-global 结果

| 项目 | 实测值/状态 |
|---|---|
| solver profile | `never_materialized_owner_local_overlap0125_partition` |
| global A/F | `false / false` |
| global direct factor | `0` |
| global Schur materialized | `false` |
| slab count | `16` |
| overlap | `0.125` |
| interpolation | `partition` |
| partition unity max error | `0.0` |
| partition weight min/max | `0.25 / 0.5` |
| assembly order | `two_color` |
| smoother | 2-step GMRES，ILU(0)，factor-only |
| coarse | 75D wave coarse，rank `75` |
| swap | `0 MiB` |

以上证明了本次路径按 M3a 结构合同运行；它不证明资源 Gate 或正式收敛。

## 残差与收敛状态

| iteration | reported relative residual | condensed true residual |
|---:|---:|---:|
| 0 | `1.0000000000000000` | `1.0000000000000000` |
| 10 | `0.1334151607017441` | `0.1334151607017439` |
| 20 | `0.04000947850823184` | `0.040009478508230854` |

final full-augmented true residual 为 `0.040009478508230854`，KSP reason 为
`-3 / DIVERGED_MAX_IT`。20 步有可信的早期下降，但没有达到正式 residual
收敛，因此 `official_result=false`、official RTA 为 `not_run`。

## Factor 与资源

| 项目 | M3a 实测值 |
|---|---:|
| factor rows | `127,656` |
| stored factor NNZ | `91,415,952` |
| unique factor classes | `15` |
| exact duplicate factor count | `1` |
| derived factor CSR payload lower bound | `1,828,829,728 bytes` |
| setup / KSP solve / recovery | `123.778 / 13.271 / 0.026 s` |
| whole wall | `244.141 s` |
| worker RSS/PSS/USS maximum | `12003.746 / 10707.472 / 10513.863 MiB` |
| process-tree memory authority | `11.736686706542969 GiB` |
| memory Gate | **negative**：超过 `10.30 GiB` |

M2c Screen-20 的同口径 process-tree authority 为 `12.1816520691 GiB`。
本次实际下降为约 `0.4449653626 GiB / 3.65275%`，说明 overlap 缩小和
partition weighting 确实降低了峰值，但仍留下约 `1.4366867065 GiB` 的
缺口，不能关闭 resource Gate。14 GiB termination 未触发，warning 已触发。

## 决策边界

1. 禁止继续 Screen-100/200；本次不是 full solver success。
2. 禁止在未获批准前重复扫描 overlap、slab 数、restart 或 shift 参数。
3. M3b exact duplicate 当前只有 1 份，理论收益不足以单独关闭约 1.44 GiB 缺口。
4. M3c 的 sequential factor-only setup 已经是当前实现路径，不能把它冒充为
   未做路线或作为新的资源解法。
5. 下一候选路线由主线程另行批准；本记录不开发新算法、不写 fallback、不启动
   MPI4/8 第二次 screen、不进入 Hybrid、Task037b 或 0.7 nm。
