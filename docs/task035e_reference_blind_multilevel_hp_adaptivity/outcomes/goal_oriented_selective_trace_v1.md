# Task035e goal-oriented selective-trace 单次验证报告

## 1. 最终结论

本批次严格只运行了一个 actual MPI8 selective-trace candidate。结果是：

```text
59-goal accuracy = 49/59 -> fail
whole-job peak   = 10.929794 GiB <= 11 GiB -> pass
swap             = 0 MiB -> pass
residual/energy/Floquet/hanging/MPI -> pass
final status     = CONTROLLED_NEGATIVE_GOAL_ORIENTED_SELECTIVE_TRACE
```

因此 Task035e 的 direct selective-trace 路线按用户规则正式关闭。没有扩大
projection threshold，没有运行第二个 goal-oriented batch，也没有在 actual
结果后修改 face 数量或排名公式。下一条路线只能在后续审阅授权后转向
iterative 或 Hybrid；本批次两者都没有运行。

这个负结果同时给出了一个很清楚的机制判断：

- DWR 排名所直接优化的 6 个独立物理目标全部从 M1 的失败状态恢复为通过；
- 与 `top:m0:n0:power` 重复的 `R00_total` 也通过；
- 但是 10 个原先通过、未进入这 6 个 adjoint 的旁路目标变成失败；
- 所以“只对当前失败目标求 adjoint”能准确修复目标本身，却不能保证完整
  59-goal 向量不发生 collateral error。

这不是求解器失败，也不是内存失败，而是完整多目标精度 Gate 的受控负结果。

## 2. 源码、环境与运行边界

| 项目 | authority |
|---|---|
| branch | `codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity` |
| numerical source SHA | `69cd41c74ba0dfc310d8631cf7bbd8103ec8fc73` |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python` |
| PETSc | `complex128` / `int32` |
| MPI | OpenMPI，8 ranks |
| mesh | frozen structured H10 `(6,3,14)`，252 cells |
| base space B | global p5 trace + global p6 cell interior |
| fine space F | global p6 trace + global p6 cell interior |
| reference-visible | 是 |
| reference-blind / hidden-audit credit | 否 |
| ordinary default changed | 否 |

正式数值 worker 位于独立 clean worktree，并固定在上述 numerical source
SHA。后续 compact 和本文档不会使 current、M1、fine factor/adjoint 或 actual
candidate 重跑。

## 3. 七个失败行如何去重为六个物理目标

M1 的 7 个失败行是：

```text
top:m0:n0:power
top:m0:n0:co_amp_imag
top:m-1:n0:power
bottom:m-1:n0:power
bottom:m-7:n0:co_amp_imag
scalar/R00_total
scalar/R_total
```

其中 `top:m0:n0:power` 和 `scalar/R00_total` 是同一物理量，因此只保留一个
adjoint。最终求解 6 个独立目标：

```text
top:m0:n0:power
top:m0:n0:co_amp_imag
top:m-1:n0:power
bottom:m-1:n0:power
bottom:m-7:n0:co_amp_imag
scalar/R_total
```

每个 adjoint 都复用同一个 global-p6 MUMPS factor。相对 adjoint residual
范围为 `1.675153e-13` 至 `1.729e-12`。

## 4. exact hierarchical trace complement

这里的“hierarchical complement”是把同一网格上的 trace 空间拆成嵌套层：

- B：p5 edge + p5 face；
- S：p5 edge + p6 face；
- F：p6 edge + p6 face。

这样能单独分析恢复 face 的 p6 模式会怎样改变目标，而不会先把完整 p6 trace
矩阵装入再把未选系数置零。

| audit | value |
|---|---:|
| B independent trace rows | 34,920 |
| S independent trace rows | 50,400 |
| F independent trace rows | 51,192 |
| face quotient rows | 15,480 = 774 × 20 |
| p6 edge complement rows | 792 |
| periodic physical face orbits | 774 |
| B→S→F composition max error | `1.776357e-14` |
| global coarse-cross max error | `6.277569e-15` |
| face residual norm | `1.617677883244` |
| unexplained residual norm | `6.603508e-10` |
| RHS restriction error | `1.426804e-13` |
| maximum operator-probe error | `2.245705e-11` |

global-p6 support run只做 factorization、6 个 transpose adjoint 和 DWR
pairing，没有重新求 global-p6 primal，也没有重新计算 p6/h10 reference。
该支持运行的 `19.107769 GiB` historical upper bound 是离线 estimator
成本，不是 actual candidate 的资源 Gate。

## 5. 774-orbit signed multi-goal DWR 与冻结 batch

对每个 physical face orbit，先计算其 20 维 p6-face complement 对 6 个目标的
signed DWR，再用冻结的 per-goal tolerance 归一化。贪心 score 是加入该 orbit
后 `sum((J-ref)/tau)^2` 的边际下降，并用既有 M1/200-orbit 实测资源增量作为
结构成本代理。

在预测 peak `<10.5 GiB`、另留 `100 MiB` safety margin 的约束下，排序在
16 个 orbit 时已经预测 6 个目标全部进入 tolerance，因此冻结：

```text
[748, 747, 605, 749, 603, 674, 682, 672,
 681, 683, 673, 751, 741, 606, 752, 742]
```

这 16 个 orbit 对应 16 个 physical geometry keys；没有 periodic duplicate
copy，也没有 edge orbit、local-h 或第二批 face。

| 目标 | M1 normalized error | DWR predicted | actual |
|---|---:|---:|---:|
| `top:m0:n0:power` | 1.980611 | 0.558207 | 0.538301 |
| `top:m0:n0:co_amp_imag` | 1.964978 | 0.964973 | 0.951948 |
| `top:m-1:n0:power` | 2.054809 | 0.108827 | 0.045748 |
| `bottom:m-1:n0:power` | -1.238903 | -0.079675 | -0.029489 |
| `bottom:m-7:n0:co_amp_imag` | -1.181839 | 0.027212 | 0.062617 |
| `scalar/R_total` | 1.981824 | 0.558552 | 0.540889 |

对这 6 个被显式优化的目标，预测方向和 actual 结果都正确，而且全部通过。
这说明 signed DWR、嵌套注入和 orbit pairing 本身得到了强的局部验证。

## 6. 唯一 actual MPI8 candidate

### 6.1 结构与资源预测

| metric | predicted | actual | actual - predicted |
|---|---:|---:|---:|
| augmented rows | 35,320 | 35,320 | 0 |
| matrix NNZ | 20,505,347.84 | 20,492,976 | -12,371.84 |
| factor NNZ | 102,357,746 | 93,656,300 | -8,701,446 |
| whole-job peak | 10,331.039 MiB | 11,192.109 MiB | +861.071 MiB |

预测满足用户规定的 `<10.5 GiB` selection budget；actual peak 高于这个
selection budget，但仍以 `71.891 MiB` 裕量满足最终 `<=11 GiB` Gate。
因此本次失败不能归因于资源 Gate。

actual candidate 的离散规模为：

| metric | value |
|---|---:|
| active exact-sequence FE DoF | 155,055 |
| storage-carrier p6 FE DoF | 173,802 |
| independent trace rows | 35,240 |
| augmented rows | 35,320 |
| matrix NNZ | 20,492,976 |
| factor NNZ | 93,656,300 |

### 6.2 物理与求解 Gate

| Gate | actual | result |
|---|---:|---|
| full explicit true relative residual | `9.865452e-11` | pass |
| `abs(R+T+A_volume-1)` | `1.864064e-13` | pass |
| max Floquet mismatch | 0 | pass |
| hanging patches/slave rows | 0 / 0 | pass |
| MPI ranks | 8 | pass |
| whole-job peak | 10.929794 GiB | pass |
| swap | 0 MiB | pass |
| solver released before field output | true | pass |

正式总量为：

```text
R_total = 0.0007629447233931936
T_total = 0.6026812189588464
A_volume = 0.39655583631757396
```

### 6.3 完整 59-goal 结果

| category | pass | normalized L2 | normalized Linf |
|---|---:|---:|---:|
| power | 10/16 | 9.128770 | 6.938178 |
| complex amplitude | 28/32 | 4.741561 | 2.438820 |
| totals | 5/5 | 0.913679 | 0.540889 |
| fields | 6/6 | 0.104456 | 0.070919 |
| all | **49/59** | **10.327757** | **6.938178** |

M1 的 all-goal normalized L2 是 `5.397523`；该 candidate 增加
`91.342535%`。10 个失败项全部是 M1 中原先通过、但未进入 6-adjoint
目标集的旁路量：

| failed goal | value | reference | tau | signed normalized error |
|---|---:|---:|---:|---:|
| `top:m-2:n0:power` | `1.476652303e-06` | `1.477697676e-06` | `1.0e-09` | -1.045373 |
| `top:m-4:n0:power` | `2.726651425e-07` | `2.675889822e-07` | `1.0e-09` | 5.076160 |
| `top:m-4:n0:co_amp_real` | `2.125864429e-04` | `2.102622291e-04` | `1.0e-06` | 2.324214 |
| `top:m-6:n0:co_amp_real` | `-7.723437794e-06` | `-9.070910081e-06` | `1.0e-06` | 1.347472 |
| `top:m-7:n0:power` | `6.280917941e-07` | `6.265105241e-07` | `1.0e-09` | 1.581270 |
| `top:m-7:n0:co_amp_imag` | `-2.521027236e-05` | `-2.622959340e-05` | `1.0e-06` | 1.019321 |
| `bottom:m-2:n0:power` | `2.957898090e-06` | `2.959762349e-06` | `1.479881174e-09` | -1.259735 |
| `bottom:m-4:n0:power` | `4.303890574e-07` | `4.373272354e-07` | `1.0e-09` | -6.938178 |
| `bottom:m-4:n0:co_amp_real` | `-2.597319736e-04` | `-2.621707932e-04` | `1.0e-06` | 2.438820 |
| `bottom:m-7:n0:power` | `2.357625552e-06` | `2.361105282e-06` | `1.814051896e-09` | -1.918209 |

### 6.4 内存生命周期与计时

本次没有 PSS/USS sampler，因此不伪造这两个字段；正式口径是 8-rank
sum-RSS historical upper bound，同时保存每个阶段的 sum-current RSS。

| stage | sum-current RSS | historical upper bound |
|---|---:|---:|
| before MUMPS setup | 9,388.207 MiB | 9,362.789 MiB |
| after factorization | 11,203.984 MiB | 11,176.117 MiB |
| after solver/factor release | 6,905.094 MiB | 11,192.109 MiB |
| after field output | 8,018.770 MiB | 11,192.109 MiB |

在 field output 前销毁 KSP/MUMPS factor、system matrix、RHS 和 solution，
并调用 PETSc garbage cleanup 与 `malloc_trim`。release audit 实测：

```text
sum RSS before release = 11,123.977 MiB
sum RSS after release  =  6,905.078 MiB
released               =  4,218.898 MiB
```

因此真正的 current-RSS 高点仍在 MUMPS factorization，而不是场输出。历史
peak 字段是单调上界，释放后不会下降。

主要时间字段如下；这些 solver 内部字段可能嵌套，不能相加冒充总时间：

| phase | seconds |
|---|---:|
| base matrix assembly | 194.119 |
| assembly-time condensed build | 117.786 |
| MUMPS setup | 37.677 |
| solve | 0.071 |
| cell recovery | 0.780 |
| full true residual | 3.078 |
| runner elapsed through field output | 286.620 |
| progress through final postprocess | 289.541 |

## 7. p6/h5 factor telemetry 的离线修正

p6/h5 没有重跑 PDE。原 PETSc `MatInfo` 把超过 signed int32 的 factor NNZ
记录成：

```text
-2017967296
```

同一 raw run 的 MUMPS `INFOG(9)=-2277` 使用“负值绝对值 × 一百万 entries”
语义，因此离线修正为：

```text
factor_nnz = 2,277,000,000
factor_fill = 8.160347349109193
```

修正保留 raw overflow 值、MUMPS raw 值、解释语义与 source
`run_summary.json` SHA-256；没有把旧负数删除，也没有以修正文档为理由重跑
p6/h5。

## 8. 最终测试

最终源码与文档状态上：

```text
targeted serial:
    38 passed, 5 skipped in 103.72 s

MPI8 key contracts:
    4 passed, 39 deselected on each of 8 ranks

documentation contract:
    14 passed

Ruff:
    pass

compileall:
    pass

all tracked-style JSON parse:
    pass

compact canonical payload SHA:
    c2d330551b85a0505056e5289a35d1ffc8468404ead9928b328ddd71b1e4b14f
```

MPI8 key contracts 覆盖 zero-h exact anchor、factorization observer 的
transpose-adjoint 生命周期，以及 periodic face quotient 的 signed pairing。
测试没有启动新的 Maxwell PDE。

## 9. 证据与停止边界

- [compact evidence](../../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/h10_goal_oriented_selective_trace_v1.json)
  保存 774 个 orbit 的 signed DWR、6 个 adjoint、完整 59-goal actual、
  资源生命周期与所有 raw SHA。
- [exact actual plan](../../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/h10_goal_oriented_selective_trace_plan_v1.json)
  与运行时 plan 的 SHA-256 完全相同：
  `dcd41faa3a09bcdc30a47934866c02e3c36c8518f880a9e85e52eaacacb86fa1`。

冻结处置：

```text
direct selective trace = closed
second batch = not_run / not_authorized
threshold expansion = not_run / not_authorized
ranking formula retune = not_run / not_authorized
iterative = not_run
Hybrid = not_run
ordinary default = unchanged
```
