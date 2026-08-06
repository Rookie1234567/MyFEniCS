# G2.2 一个 slab 的 full-space identity 证据

本轮把同一个 slab residual 用两条路径计算：一条直接使用 condensed trace Schur action，另一条保留该 slab 的 full-space cell block，先从 trace 值恢复 interior，再计算 full-space action 并投影回 trace。这个检查解决的是“full-space 组装/恢复路径是否与现有 trace 路径代数一致”，避免在以后研究 full-space 或 LOR-HX 时把边界列、Floquet 展开或 interior recovery 接错。

它只证明两条代数应用路径对同一输入一致；不证明预条件器有效，不证明 contraction，不证明外层 FGMRES 收敛，也不证明物理 R/T/A 收敛。

## 结论边界

| lane | 状态 | 本轮含义 |
|---|---|---|
| G2.2 full-space/trace algebraic identity | `pass` | tiny 与真实 slab14 的 3 个 deterministic vector、1 个 iter20 residual direction 均通过 `<=1e-10` |
| G2.3 full-space p6 ILU inventory | `pending_not_run` | 没有构造 full-space ILU，也没有比较 payload/retained bytes |
| G2.4 LOR mesh 与 transfer | `pending_not_run` | 没有建立 LOR mesh 或 transfer |
| G2.5 LOR-HX/V-cycle | `pending_not_run` | 没有实现或运行 HX/V-cycle |
| G2.6 one/two V-cycle Gate | `pending_not_run` | 没有运行 1/2 V-cycle 对照 |

因此本轮不能写成整体 G2 通过，也不能声称 minimum contraction、full solve 或 production promotion。

## 正式 v2 运行身份

| 项目 | 值 |
|---|---|
| source SHA | `44f5931c479eba86c9d12c57109e3b052e2962e4` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_identity_mpi1_screen20_44f5931c_v2` |
| watchdog | `task037_extra_g2_slab14_identity_pass`；return code `0`；failures `[]` |
| source/working tree | verified clean；global A/F 均未物化 |
| solver boundary | 20 steps，`DIVERGED_MAX_IT(-3)`；`external_solver_not_converged` |
| official/RTA | `false / false`；postprocess skipped |
| memory policy | poll `0.25 s`、warning `10 GiB`、terminate `14 GiB`、timeout `1800 s`、no swap |

该 watchdog pass 只表示本轮 identity、materialization、有限 residual、资源和 source identity checks 通过；它不是 solver convergence 或 physical result pass。

## 两条路径的代数合同

真实 identity 比较的是 full-space cell action 经过 trace restriction 后的结果与 trace Schur action。它没有形成整个 Full3D uncondensed global matrix。

```math
S_j v = R_t\mathcal A_j
\begin{bmatrix}
-A_{ii}^{-1}A_{it}v\\
v
\end{bmatrix}.
```

slab 边界采用与既有 principal restriction 一致的语义：完整 local block 和 trace rows 保留，稀疏 trace expansion `C` 只保留属于 owner rows 的 active columns；外部 active trace 列等价于零延拓。这个边界语义是本轮修复的重点。

## slab 选择与 restriction 证据

primary 固定为 slab14，因为 G0 的 iter20 local residual 最大；control 固定为 slab5；slab13 只作为最大正 ablation-damage comparator，不替换 primary。

| 字段 | slab14 v2 实测 |
|---|---:|
| owner / cells / unique blocks | `0 / 54 / 6` |
| owner active rows | `8424` |
| source / retained / dropped active columns | `23328 / 17064 / 6264` |
| partial cells | `18` |
| sparse `C` NNZ / bytes | `17064 / 434808` |
| owner row SHA256 | `6f7c32c5fef8058a9c3a36deeaa65bce5f726c57c0d426220c065f683b57dade` |
| canonical cell ID SHA256 | `ac7e3532a1ecf55826a25a99b1f5197fb7c9952a084bf88f4ca15bad79511023` |

列计数闭合为 `23328 = 17064 + 6264`。这说明跨 slab parent cell 没有被丢弃，也没有把 full block 错误缩成只含 owner rows 的 block。

## identity 数值

相对误差阈值为 `1e-10`。三个 deterministic vectors 均 finite、deterministic 且通过：

| vector | relative error |
|---|---:|
| `canonical_affine_phase` | `2.9248960201709676e-15` |
| `canonical_complex_affine_phase` | `2.978578754981666e-15` |
| `canonical_sinusoidal_phase` | `2.6617554455542794e-15` |

iter20 使用 solver 内部真实 `r=b-Ax`，没有从 scalar residual 伪造向量：

| 字段 | 值 |
|---|---:|
| iteration | `20` |
| local residual norm2 | `0.42723143961943305` |
| residual vector SHA256 | `3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195` |
| identity relative error | `1.7721399154913289e-15` |
| true relative residual | `0.04474243612765` |
| current local shift norm2 | `475.7236793796778` |
| materialization | condensed trace `false`；action-only `true`；blocks.F `false` |

screen residual trajectory 为 `i0=1.0`、`i10=0.14446444295860594`、`i20=0.04474243612765`。其中 iter10 只有 core scalar history，本轮没有把它当作 raw vector。

## 第一次失败与修复边界

source `5bb270715d5610d7752d5d9f99e112c467765630` 的第一次 screen 在进入 solver 前受控失败，错误为：

```text
RuntimeError: cell active rows are not contained in slab owner rows
```

这不是普通调试噪声，也没有被覆盖。第一次 collector 错误地要求一个跨 slab cell 的全部 active IDs 都属于 owner rows。source `44f5931c...` 的修复与既有 principal restriction 对齐：完整 local block/trace rows 保留，`C` 的 active trace 列只取 owner rows，外部列作零延拓。v2 的 `partial_cell_count=18` 和 dropped-column 计数正是该边界语义被实际执行的证据。

## 资源与 solver 语义

| 指标 | v2 authority |
|---|---:|
| process-tree RSS | `4655.9453125 MB = 4.546821594238281 GiB` |
| worker RSS / PSS / USS | `4642.10546875 / 4590.4072265625 / 4545.5625 MB` |
| swap | `0` |
| wall | `335.08262702892534 s` |
| warning/termination/timeout | `false / false / false` |
| cgroup historical peak | `13279.546875 MB`，不是当前 authority |

20 步 solver 以 `DIVERGED_MAX_IT(-3)` 结束；这只说明本次 screen 达到固定步数上限。它不否定 G2.2 的代数 identity pass，也不允许把本轮写成收敛或 official RTA 结果。

正式 audit 仍是 action-only：global A/F 未物化，operator apply count=`140`，coarse apply count=`20`，one-level apply count=`120`，stored factor NNZ=`91415952`。本轮没有运行 G2.3 full-space ILU、LOR transfer、HX/V-cycle 或 one/two-cycle Gate。

## Evidence

compact tracked record：[g2_slab14_fullspace_identity.json](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_identity.json)。正式 v2 raw 文件均保留在 ignored artifact 目录，关键 SHA256 如下：

| 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `86f0acdbf48e2b10315e84f27622fa74f54f42b561e3a4cefc7e2a23762658e8` |
| `run_summary.json` | `13d8364450fcda99cf2f7912cfb8e3e3fe960ecb245e1e94fabe994c9f122156` |
| `task037_f3_core_audit.json` | `198e1575c8b7df71373d015eeb9ab6a5799ce403f2725986465e62eec8a972bc` |
| `memory_timeline.csv` | `f595dfaa9e933a1062de4b937f6e92bebe8bb4c648841dc2210a648b3642ba66` |
| `progress_3d.jsonl` | `9caab35a3390d206aa330fa1e4c0d51929a2b76f891a90ec2bc4dfe45fbf6847` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `worker_stdout.txt` | `33ad63683c44ecb4348a7f445ca276cd413d8a8d8a73defc3c64378f54a53c41` |
| `parent_launch_descriptor.json` | `a8ad6ee4a57d4b79ee36e6d8926e9599b1e1df0057cde83b6510a7d4c1461ff3` |

第一次受控失败的 run directory 和 hashes 也保存在 compact record 的 `negative_evidence` 中，确保修复后的通过没有抹去负结果。

## Pending

G2.3–G2.6 均保持 `pending_not_run`。当前唯一允许的结论是：已经具备一块 slab 的 full-space identity 实现与验证证据；尚未具备全局 candidate、minimum contraction、full solve 或 production promotion 的依据。
