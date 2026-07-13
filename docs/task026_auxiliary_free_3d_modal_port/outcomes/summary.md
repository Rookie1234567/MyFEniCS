# Outcome Summary

## Review V1 收尾更新（2026-07-11）

### 最新结论

本轮解决了旧 h=2 运行无法回收、长任务无流式历史和实际 h=2 action 缺证据三个问题，并把 h=2 迭代残差从 `0.166485` 推进到 `7.05115e-4`。这是约 `236` 倍改善，但仍高于 production gate `1e-6`，因此准确状态为：

```text
architecture_success = true
h2_action_mpi1_mpi4 = pass
h2_iterative_strong_research_signal = true
h2_production_solver = unresolved
task026_status = architecture_success_solver_research_only
```

### h=2 最佳进展

| profile | 迭代 | 真残差 | 峰值 RSS | 结论 |
|---|---:|---:|---:|---|
| plain matrix-free ASM/ILU2 | 200 | `1.66485e-1` | `12.883 GB` | 旧基线，失败 |
| 16 slab + ILU1 + 24 层粗空间，100 步 | 100 | `5.02399e-3` | `10.436 GB` | strong gate 通过 |
| 同上，FGMRES(50) | 600 | `8.85195e-4` | `10.445 GB` | 明显进步，未 production |
| 同上，FGMRES(100) | 600 | **`7.05115e-4`** | `11.380 GB` | 当前最低残差 |
| `m=-1,0,1` 的 y 向 Floquet 谐波，100 步 | 100 | `2.58076e-3` | `10.924 GB` | 相对 76 维粗空间改善 49% |
| GCR + 126 维谐波粗空间 | 600 | `8.23530e-4` | `10.481 GB` | 恒定内存，但不优于 FGMRES |

`FGMRES(100)` 的最低残差来自 76 维基础粗空间；126 维 Floquet 谐波方案只完成了 100 步 gate，尚未证明其 600 步最终值更低。两者都保留为 research profile，不替换 production 默认。

### 旧 h=2 后台运行回收

原 `8 slab + ILU2 + overlap 0.25` 容器在约 3 小时后仍停在 setup：

| 指标 | 回收值 |
|---|---:|
| 进程 RSS | `13,020,148 kB` |
| 容器内存 | 约 `12.71 GiB / 13.65 GiB` |
| swap 使用 | 约 `7.2 GB` |
| 块 I/O | 约 `1.88 GB read / 7.36 GB write` |
| 已完成 Krylov 迭代 | `0` |
| 失败阶段 | 局部 ILU2 setup / swap thrashing |

该容器已按审查停止条件终止。新 runner 会在装配、每个子域因子和 Krylov checkpoint 后立即写 `progress.json`，并 append/flush `residual_history.csv`。

### 内存结构修复

1. 凝聚块提取后立即释放不再需要的 augmented 全局矩阵。
2. 粗矩阵按列复用单个 `A·Z` 向量，不再同时保留全部 action basis。
3. 局部因子逐个 setup，并在每个子域后记录 RSS/swap。
4. 粗矩阵使用 SVD 秩门和条件数门；禁止用 `pinv` 掩盖秩亏。
5. 新增显式 additive-Schwarz 研究 backend，可在因子建立后释放 shifted 父矩阵；h=5 正常，但 h=2 ILU2 仍因工作集过大被淘汰。

### h=2 实际 action 与 MPI Gate

| 向量 | MPI1 error | MPI4 error | 门限 | 状态 |
|---|---:|---:|---:|---|
| 随机复向量 | `4.497e-17` | `4.843e-17` | `1e-11` | pass |
| physical condensed RHS | `5.884e-16` | `6.920e-16` | `1e-11` | pass |
| selected modal trace | `7.401e-16` | `1.001e-15` | `1e-11` | pass |

显式 h=2 operator 有 `80,796,920` 个非零元，其中 port product 有 `15,769,728` 个非零元。MPI1 显式 action 峰值 RSS `6.411 GB`，MPI4 总峰值 RSS `8.449 GB`。

### PC 有限消融

| 方向 | 最好证据 | 决定 |
|---|---:|---|
| 16 slab 替代 8 slab | setup 从 3 小时未完成降到约 5 分钟 | 保留 |
| ILU1 替代 ILU2 | RSS `10.44 GB`，100 步 `5.02e-3` | 保留 |
| `m=±1` y 谐波 | 100 步 `2.58e-3` | 保留为研究增强 |
| 全传播阶次 `m=-7...0` | `1.95e-3`，但 PC cost `2.75 s/apply` | 成本收益不足，淘汰 |
| coarse 24 -> 32 | `2.52e-3` | 改善不足，淘汰 |
| 内层 GMRES 两步 | `1.59e-3`，但 cost 增至 `2.62 s/apply` | 改善不足，淘汰 |
| shift `0.1 -> 0.3` | 约 90 步 `6.27e-3` | 不优，淘汰 |
| FGMRES restart 300 | 140 步 `1.79e-3`，RSS 已约 `12.8 GB` | 内存效率失败 |
| BiCGStab(2) | h=5 残差放大到 `32.2` | 发散，淘汰 |
| TFQMR | h=5 20 步 `0.924` | 淘汰 |
| GCR | h=2 600 步 `8.24e-4` | 低内存但未突破 |
| 缺陷校正/在线残差粗向量 | h=5 无可测收益 | 淘汰 |

### 尚未关闭

| Gate | 状态 | 原因 |
|---|---|---|
| h=2 真残差 `<=1e-6` | fail | 当前最低 `7.05e-4` |
| h=2 official R/T/A | pending | 仅在 residual gate 通过后发布 |
| h=2 direct/OOC reference | pending | 本轮优先关闭 action 与迭代诊断，未反复消耗 swap |
| MPI topology two-level | pending | 串行 PC 尚未达到 production，不提前工程化 |
| h=5 angle/wavelength 局部鲁棒性 | pending | h=2 solver gate 未关闭 |

因此本轮不能标记 `completed_production_candidate`，也不修改普通 production 默认或 auxiliary reference path。

## 任务

Task026 将现有 3D auxiliary DtN 系统精确静态凝聚为仅含 FE unknown 的系统：

```math
A_{cond}=F-CH^{-1}D,
\qquad
b_{cond}=b_F-CH^{-1}b_H.
```

现有 auxiliary 路径未删除、未改默认行为，继续作为代数、物理和 official R/T/A 参考。

## 分支

```text
codex/20260711-task26-auxiliary-free-3d-modal-port
```

## 阶段结论

本轮已取得两个实质突破，但因自动执行额度到达本时段上限，Task026 尚未最终闭环：

1. h=5 auxiliary、explicit condensed 与 matrix-free 三条路径达到机器精度等价。
2. 新 topology-aware two-level PC 在无 auxiliary unknown、无 Q cache 条件下，把 h=5 真残差推进到 `9.9992e-10`，并通过 official R/T/A。
3. h=2 plain matrix-free ASM/ILU2 已完成，残差 `0.16649`、峰值 RSS `12.883 GB`，未突破 Task025。
4. h=2 topology two-level 100 步资格测试已启动并稳定运行在约 `12.7 GB`；停止写报告时容器仍在后台计算，结果尚未落盘，禁止推断其 Gate。

## 关键结果总表

| case | operator / PC | iterations | full true residual | peak RSS | official R/T/A |
|---|---|---:|---:|---:|---|
| h=5 direct | auxiliary MUMPS | 1 | `7.82e-12` | `1.315 GB` | pass |
| h=5 direct | explicit condensed MUMPS | 1 | `5.99e-12` | `1.346 GB` | pass |
| h=5 iterative upper bound | matrix-free + exact FE LU | 24 | `3.16e-12` | `1.191 GB` | pass |
| h=5 plain | matrix-free + shifted global ILU1 | 250 | `1.363e-1` | `0.943 GB` | fail |
| h=5 plain | matrix-free + shifted global ILU2 | 300 | `4.360e-2` | `1.259 GB` | fail |
| h=5 COMSOL-style prototype | corrected two-level, overlap `0.25` | 795 | `9.999e-10` | `1.829 GB` | pass |
| h=2 plain | matrix-free + shifted global ILU2 | 200 | `1.6649e-1` | `12.883 GB` | fail |
| h=2 two-level | overlap `0.25`, restart 50 | running | pending | observed about `12.7 GB` | pending |

## 2D 回归

2D `p=2, h=5 nm` 的真实 auxiliary/explicit 直接法对照通过：

| metric | auxiliary | explicit | absolute difference |
|---|---:|---:|---:|
| field relative L2 | reference | reference | `1.696e-14` |
| R | `0.00631755208546589` | `0.006317552085465258` | `6.32e-16` |
| T | `0.9936824479145326` | `0.9936824479145313` | `1.33e-15` |
| R+T | `0.9999999999999986` | `0.9999999999999966` | `2.00e-15` |

两条路径共享现有 trace/mode selector；非单位 H、复共轭和矩阵 action 由新增 synthetic block tests 覆盖。真实 2D matrix action 尚未单独导出，不能用场等价冒充 action Gate。

## 3D h=5 代数与物理等价

| 检查 | 结果 |
|---|---:|
| random action error | `3.311e-17` |
| physical-RHS action error | `3.244e-16` |
| direct-solution action error | `3.639e-15` |
| auxiliary vs condensed FE field error | `3.712e-13` |
| delta R | `3.009e-14` |
| delta T | `-8.332e-14` |
| delta A_volume | `-2.565e-14` |
| delta closure | `-7.894e-14` |

显式 port product 只有 `460800` 个非零；condensed 矩阵为 `44698 x 44698`、`5284876` nnz。matrix-free 1000 次 apply 的当前 RSS 前后均为 `0.65961 GB`，无持续增长。

## h=5 新迭代器

最终通过的 profile：

```text
FGMRES(restart=300)
+ exact matrix-free F-CD action
+ shifted FE smoother, beta=0.1
+ 8 个 topology z-slab ASM / local ILU2
+ overlap = 0.25 slab
+ 24 个 z coarse intervals
+ 76 维 Floquet-phase vector-hat Galerkin coarse solve
+ pre/coarse correction，无不稳定 post-smooth
```

official 结果：

| R | T | A_volume | sum | closure error |
|---:|---:|---:|---:|---:|
| `0.08902160293472974` | `0.442588278660677` | `0.46839011840325523` | `0.999999999998662` | `-1.338e-12` |

## 关键缺陷与修复

最初 Galerkin prototype 使用了错误的 petsc4py complex dot 方向。`left.dot(right)` 在这里需要取共轭才能得到 `left^H right`。修复范围包括：

```text
modified Gram-Schmidt
Z^H A Z
Z^H r
```

修复前 76 维 coarse profile 残差为 `0.2591`；修复后同 profile 200 步残差为 `0.0010455`，改善约 248 倍。新增实现保留该显式共轭，后续必须补专门回归测试。

## COMSOL 映射

COMSOL 的可迁移原则不是“普通 AMG”：

| COMSOL 原则 | Task026 实现 |
|---|---|
| vector-element smoother | topology z-slab ASM / ILU |
| lower order / coarse hierarchy | Floquet-phase vector-hat Galerkin coarse space |
| coarse grid 满足波长分辨率 | 24 intervals，z 间距约 `5.83 nm < lambda/2` |
| CSL 只进入 PC | shifted FE smoother，原 operator 不变 |
| Krylov smoother/可变 PC 使用 FGMRES | outer FGMRES |

8 个 coarse intervals 的间距 `17.5 nm` 违反 Nyquist；24 个 intervals 修复了粗尺度分辨率。当前仍是定制两层 prototype，不应称为完整非匹配网格 h-GMG。

## 内存结论

Task026 已彻底删除迭代路径中的：

```text
80 个 auxiliary global unknown
Q = F^-1 C
80-response Q cache
approximate auxiliary Schur
```

h=2 plain ILU2 峰值 `12.883 GB`，比 Task025 cached-Q `13.006 GB` 略低，但释放的内存被更强 coarse basis/PC 使用。正在运行的 h=2 two-level 观测峰值约 `12.77 GB`，暂未出现持续增长。

## 未完成项

1. 等待并读取后台 h=2 100-step two-level 结果。
2. 若 h=2 有正斜率，减少 swap 成本后延长至 strong/production Gate。
3. 完成 h=2 explicit vs matrix-free action；当前只有 h=5 actual 与 MPI4 synthetic。
4. 尝试 h=2 auxiliary/condensed MUMPS OOC direct，或明确记录资源失败阶段。
5. h=2 达到 `<=1e-6` 后才允许 official R/T/A 与参数 sweep。

## 停止原因

```text
automatic execution/escalation usage limit reached
retry window reported by system: after 14:00
h2 background container was still running when this summary was written
```

因此本文件是可续跑阶段总结，不是 Task026 最终完成声明。
