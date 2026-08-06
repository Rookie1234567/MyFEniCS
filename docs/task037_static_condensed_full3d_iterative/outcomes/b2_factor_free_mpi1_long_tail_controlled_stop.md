# B2 MPI1 长尾补充：受控停止

本记录描述一次唯一的 MPI1 B2 长时运行。这里的“静态凝聚”是先在每个单元内消去内部未知量，再把较小的 trace 系统交给全局求解器；“factor-free”表示运行时不保留全局 p6 矩阵或 p6 因子，而由局部动作计算完成细网格作用。此次运行验证了这种存储路径的 setup 事实，但没有得到收敛解。

## 身份与冻结配置

| 项目 | measured / frozen value |
|---|---|
| source | `7aa77ed3f38dc036df77166d74b9d9d18ff0dbf6` |
| branch / source-time state | `codex/20260803-task37-matrix-free-iterative-development`，运行时 clean，ahead/behind `0/0` |
| ABI | qualified activation `1`；repository `.venv`；PETSc `complex128/int32`；同一 Linux 栈；swap `0` |
| model | 13.5 nm；p6/h10；S；theta normal `80°`（10° grazing）；phi `0°`；252 cells |
| B2 | 16 slabs；overlap `0.125`；partition weighting；local Krylov fixed `2`；inner PC none |
| auxiliary / coarse | p2 exact-sequence auxiliary + one distributed MUMPS factor；75D wave coarse |
| outer solve | right FGMRES restart `90`；rtol `1e-6`；atol `0`；MPI1；canonical vector export |
| storage | p6 retained matrix/factor/NNZ `0/0/0`；global A/F `false/false` |
| long capability | max iterations `1,000,000`；parent technical timeout `604800 s`；普通模式未改变 |

实际 parent command 在已完成 qualification activation 的同一 shell 中执行：

```text
python -m benchmarks.run_task033_full3d_watchdog --degree 6 --h-nm 10 --polarization-kind s --run-kind full-solve --mpi-size 1 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --task035c-p6-h10-gate --task035c-p6-preflight-authority benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json --task035c-p6-preflight-sha256 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 --verified-clean-sha 7aa77ed3f38dc036df77166d74b9d9d18ff0dbf6 --task037-f3-full --task037-m2c-never-materialized --task037-m4-p2-auxiliary --task037-m4-factor-free-slab --task037-m4-factor-free-local-steps 2 --task037-m4-b2-long-full --task037-canonical-vector-export --poll-interval 0.25 --warning-gib 10 --terminate-gib 14 --timeout-seconds 604800 --run-dir benchmarks/artifacts/task037/b2_factor_free_mpi1_long_full_p6_h10_7aa77ed3
```

唯一运行一次；原始 ignored artifact 目录为：
`/home/Projects/MyFEniCS/benchmarks/artifacts/task037/b2_factor_free_mpi1_long_full_p6_h10_7aa77ed3`。

## 残差历史与停止门槛

下表逐条复制 `task037_f3_residual_history.jsonl`；最大记录为 `2500`，没有 `2600`。

| iteration | reported | condensed true |
|---:|---:|---:|
| 0 | `1.0` | `1.0` |
| 10 | `0.47868045163341444` | `0.4786804516334328` |
| 20 | `0.4293594862213914` | `0.4293594862214095` |
| 100 | `0.26146490762657354` | `0.26146490762657393` |
| 200 | `0.21018023180263032` | `0.21018023180262965` |
| 300 | `0.19618883359925818` | `0.19618883359925857` |
| 400 | `0.19190535949591242` | `0.1919053594959122` |
| 500 | `0.18921505123607335` | `0.1892150512360726` |
| 600 | `0.18729792917509558` | `0.18729792917509708` |
| 700 | `0.18571125199082208` | `0.18571125199082278` |
| 800 | `0.18292185134403108` | `0.18292185134403083` |
| 900 | `0.17840140040862232` | `0.17840140040862232` |
| 1000 | `0.17634971041470154` | `0.17634971041470165` |
| 1100 | `0.1745442797853203` | `0.1745442797853195` |
| 1200 | `0.1720313463453937` | `0.17203134634539313` |
| 1300 | `0.16980728409601523` | `0.16980728409601495` |
| 1400 | `0.16833743843826884` | `0.1683374384382691` |
| 1500 | `0.1662908175907153` | `0.16629081759071568` |
| 1600 | `0.16376503041757032` | `0.16376503041756993` |
| 1700 | `0.16251021869425375` | `0.1625102186942539` |
| 1800 | `0.16106820746152978` | `0.16106820746152978` |
| 1900 | `0.15997850338490638` | `0.15997850338490563` |
| 2000 | `0.15914911358132283` | `0.15914911358132228` |
| 2100 | `0.15858872457053275` | `0.15858872457053289` |
| 2200 | `0.15789115346822225` | `0.15789115346822155` |
| 2300 | `0.15734491550577387` | `0.15734491550577293` |
| 2400 | `0.15660187375232726` | `0.15660187375232723` |
| 2500 | `0.15630768102286882` | `0.15630768102286852` |

停止判据使用 condensed true residual：

| quantity | value |
|---|---:|
| `r2400` | `0.15660187375232723` |
| `r2500` | `0.15630768102286852` |
| absolute drop | `0.00029419272945871433` |
| relative improvement | `0.0018786028698736588` = `0.18786028698736587%` |
| user limit | `<=0.5%` |

因此 `i=2500` 停止门槛通过。该结果不是达到 `rtol=1e-6` 的 positive convergence，也不是非有限值或明确数值崩溃。

## 终止、资源与官方结果边界

原 persistent session `3735` 通过 Ctrl-C 安全停止，return code `1`；session 已关闭，随后按进程过滤没有 orphan 的 `mpiexec` 或 watchdog 进程。分类固定为 `controlled_stop_by_user_i2500_improvement_gate`。

| 资源/结果 | value | 口径 |
|---|---:|---|
| setup wall | `318.10704500298016 s` | progress 最后可见 `stage4_dtn_augmented_matrix_finalized` |
| time to i2500 | `22974.670897739 s` | derived：parent descriptor mtime 到 residual-history mtime |
| rank historical RSS | `661.76171875 MiB` = `0.6462516784667969 GiB` | setup 阶段历史上界，不是最终峰值 |
| rank current RSS | `662.01171875 MiB` | setup 最后记录 |
| swap | `0` | measured |
| PSS / USS | not_generated | 没有相应最终 authority |
| final process-tree RSS / normal watchdog summary | not_generated | 受控 Ctrl-C 后未形成 final summary |
| whole-run final wall | not_generated | 不把 derived time 冒充 whole-run wall |

`ksp_positive_convergence`、final KSP reason、official R/T/A、canonical vectors 和 full-FE recovery 均为 `not_generated`；`official_result=false`。`0.6462516784667969 GiB` 只表示 setup 阶段 rank historical RSS upper bound，不能用于正式目标模型的最终内存结论。

## 原始证据绑定与结论

| artifact file | size | SHA256 |
|---|---:|---|
| `parent_launch_descriptor.json` | `1458` | `c9d867bdf507352eec4b6db3e56a13f604bc6123edeae1793b4490eb71d8cf19` |
| `task037_f3_residual_history.jsonl` | `3273` | `4a36766628b5d06a7d482f17767db669afb1f140373ffe598118ede722a867bd` |
| `progress_3d.jsonl` | `29215` | `65c5f87846107d767d45b794df73fd15a03b5804ef29827b61d6d07367463ccb` |
| `worker_stdout.txt` | `3111` | `30f0b6c6bc0943bc5b5a3581a031e17e1a366e09db668c48577692eb4be30188` |

完整 compact record 见 [task37_b2_factor_free_mpi1_long_tail_v1.json](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_b2_factor_free_mpi1_long_tail_v1.json)。raw artifact 保留在 ignored 目录，不复制进 Git。

结论是：factor-free 的“少存一个全局 p6 矩阵/因子”机制在 setup 审计中成立，但 B2 预条件器在长尾阶段明显缓慢；在用户停止门槛下没有产出可用解。不能据此断言它数学上永不收敛，也不能称为 production-qualified。
