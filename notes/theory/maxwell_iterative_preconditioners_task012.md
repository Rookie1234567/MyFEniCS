# Maxwell 迭代求解器与预条件器路线笔记

本文是 task012 之后持续更新的理论性笔记。完整任务记录见：

```text
docs/task012_literature_review_maxwell_preconditioners/outcomes/
docs/task013_real_split_ams_hx_qualification/outcomes/
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/
docs/task015_boundary_aware_pc_diagnostic/outcomes/
docs/task016_zero_order_lifted_coarse_correction/outcomes/
docs/task017_petrov_adjoint_coarse_correction/outcomes/
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/
```

## 当前问题为什么难

本项目的 Stage 4 线性系统同时具备几种对迭代法不友好的结构：

| 因素 | 影响 |
|---|---|
| time-harmonic Maxwell | curl-curl - k0^2 mass 形式，频域波问题天然 indefinite |
| complex refractive index | 材料吸收让矩阵 complex/non-Hermitian |
| Nedelec H(curl) | 不能直接套普通 nodal AMG；需要 de Rham-compatible auxiliary space |
| Floquet x/y periodic | 侧边界带复相位，约束空间不是普通封闭盒子 |
| z 方向 Fourier-DtN port | 边界含 Rayleigh/Floquet modal unknowns 和非局部辐射条件 |
| 80 deg 斜入射 / 后续真实几何 | 传播方向接近掠入射，长程相位误差更难由局部 PC 消除 |

因此，普通 Jacobi、ILU、one-level ASM、generic GAMG/BoomerAMG 都不太可能成为最终答案。task009-task011 的实验结果已经支持这一点。

## 已有数值证据

| 任务 | 结论 | 对后续的约束 |
|---|---|---|
| task008 | p=2 h=2 direct 给出当前 best-effort official reference：R≈0.0013429，T≈0.5992132，A≈0.3994438 | 所有新迭代法都必须最终对齐该口径 |
| task009 | GMRES/FGMRES/BiCGStab + Jacobi/ASM/ILU/GAMG/FieldSplit 无 production candidate | 不再做黑盒 profile 微调 |
| task010 | MUMPS-BLR eps=1e-5 在 p=2 h=2 收敛并复现 R/T/A，但 h=1.5 仍失败 | BLR 是 fallback，不是最终低内存路线 |
| task011 | real FE-only AMS/HX 有强正信号；complex AMS 直接崩溃；matrix-free matvec 可行 | 下一步应绕开 complex AMS，做 real split；matrix-free 后置 |
| task013 | FE-only real-split AMS/HX p=2 h=5 same-H1 310 步到 9.96e-7，RSS≈1.32GB | AMS/HX 可作为 FE block 工具，但尚未进入 Stage4 |
| task014a | reduced Stage4 real split / MPC 后 AMS data 通过，但 FE-AMS + aux identity 在 default100 p=1 h=5 只改善约 1.60x | 单纯 blockdiag(P_FE_AMS^-1, I_aux) 太弱 |
| task015 | residual 几乎全在 aux block，并集中在 top,(0,0),y mode | 需要处理 FE/aux coupled modal slow direction |
| task016 | right-only lifted correction Z=[-P_FE^-1 C_j; e_j] 无效 | P_FE lift 太弱或集成形式不对 |
| task017 | Petrov/adjoint W 无效；true-FE sampled lift top_bottom_y one-shot 有 5.819x 正信号 | 模态方向对，FE response 质量关键；right additive PC 集成错误 |
| task018 | residual-corrected outer loop 把 residual 降到 1.6616e-3，改善 12.914x | p=1 strong gate 通过；下一步验证 p=2 h=5 |

## 主要方法比较

| 方法族 | 收敛潜力 | 内存潜力 | 与光栅物理贴合 | 实现难度 | 当前决策 |
|---|---:|---:|---:|---:|---|
| real-split AMS/HX + true-FE sampled Schur residual correction | 高 | 中高 | 高 | 高 | 当前第一主线，task019 进 p=2 h=5 |
| Rayleigh/Floquet modal deflation / augmentation | 中高 | 高 | 很高 | 中高 | 作为 sampled Schur 的可选集成形式 |
| layered-background / RCWA-like inverse | 很高 | 高 | 很高 | 很高 | 如果 p=2 h=5 失败，下一主线之一 |
| shifted Maxwell + AMS/DDM | 中 | 中 | 中 | 高 | 只作为 selected FE response 或辅助层 |
| two-level DDM/sweeping | 中高 | 中 | 中高 | 很高 | p=2 失败后的替代路线之一 |
| matrix-free A + physics PC | 依赖 PC | 很高 | 中高 | 高 | PC 成功后再做 |
| MUMPS-BLR/H-matrix | 高 | 低到中 | 低 | 低到中 | fallback |
| Jacobi/ASM/ILU/GAMG | 低 | 中到高 | 低 | 低 | 停止主攻 |

## real-split AMS/HX 的核心想法

原 complex 系统：

```text
A x = b
A = Ar + i Ai
x = xr + i xi
b = br + i bi
```

等价 real block：

```text
[ Ar  -Ai ] [xr] = [br]
[ Ai   Ar ] [xi]   [bi]
```

最小 FE-only 预条件器：

```text
P0^-1 = blockdiag(B_AMS^-1, B_AMS^-1)
```

其中 `B_AMS` 是 positive H(curl) Maxwell-like operator，例如：

```text
B = curl-curl + k0^2 |eps| mass
```

这个设计的意义是：

1. 保留 complex Maxwell 的等价实形式；
2. 避开当前 PETSc/hypre complex AMS 崩溃；
3. 使用 H(curl) 兼容的 auxiliary space，而不是普通 nodal AMG。

风险在于 `Ai` 交叉项、DtN auxiliary block 和 Floquet MPC 可能让 `blockdiag(B,B)` 太弱。task014a 已经证明单纯 blockdiag 太弱。

## Stage4 DtN-aware block structure

Stage4 auxiliary DtN 装配的未知量天然分块：

```text
[ FE Nedelec field unknowns ]
[ DtN auxiliary modal unknowns ]
```

对应矩阵：

```text
[ A_FE   C     ]
[ D      A_aux ]
```

精确 auxiliary Schur complement 是：

```text
S_aux = A_aux - D A_FE^-1 C
```

这解释了为什么 task015-task018 都围绕 `A_FE^-1 C_j` 做文章。真正要处理的是 DtN/Rayleigh modal unknown 和 FE trace/volume 的 coupled response，不是 `A_aux` diagonal 自身。

## task015 后的定位

task015 做了 boundary-aware diagnostic，结论比 task014a 更明确：

| 问题 | task015 结果 |
|---|---|
| FE-AMS 后 residual 在哪里 | `aux_residual_fraction = 0.999`，FE residual 只占约 `0.043` |
| `A_aux` exact/diag 是否有用 | 无改善，residual 仍为 `2.147e-2` |
| Schur_diag 是否有用 | 明显变差到 `4.427e-1` |
| aux-space modal correction 是否有用 | zero-order / propagating 都无改善 |
| modal residual 是否集中 | `top,(0,0),y` 占 aux residual 约 `0.999999999` |
| tiny10 exact FE 上界 | 可到 `1e-15`，但 tiny10 不代表 default100 主瓶颈 |

新的判断是：

```text
blockdiag(P_FE_AMS^-1, I_aux) 失败不是因为 I_aux 本身不够精确，
而是因为 dominant Rayleigh/Floquet auxiliary mode 没有和 FE trace/volume 一起进入 coarse/Schur correction。
```

因此不要做 full 708 x 708 Schur，也不要只做 aux-space modal exact。更合适的是低维 lifted correction：

| 方案 | 目的 |
|---|---|
| `Z = [FE trace lift of top (0,0,y), aux coordinate]` | 直接捕获 dominant coupled slow mode |
| `Z^T A Z` 或 `min ||r-AZ alpha||` coarse correction | 用很低维代价处理 global modal error |
| sampled Schur for 1-4 zero-order modes | 避免 full Schur_diag 的错误近似和成本 |

## task016 后的排除结论

task016 对上述 lifted correction 做了实现和排查，结论是否定当前 right-only 形式：

| 问题 | task016 结果 |
|---|---|
| mode mapping | 与 task015 一致，default100 dominant mode 为 `top,(0,0),y`，mode id `177` |
| lifted vector 是否含 FE component | 是，`pfe_lift` 的 FE/aux norm ratio 约 `83`；balanced 版本也测试到 ratio `1` |
| coarse matrix 是否病态 | 否，condition 约 `1` 到 `1.05` |
| one-shot `Z^T A Z` | 无效，甚至常轻微变差 |
| one-shot minres `min ||r-AZ alpha||` | 最好仅 `1.000045x` 改善 |
| KSP lifted PC | 阻尼后稳定但无改善；未阻尼可能 PETSc FPE |
| p=2 h5 gate | 关闭 |

新的认识是：

```text
Task015 的 top zero-order aux residual 是正确的现象定位，
但用 right basis Z=[-P_FE^{-1}C_j; e_j] 仍然不能构成有效 coarse correction。
```

这说明当前 `P_FE^{-1}C_j` 不是足够准确的 FE response，或者 right-only Galerkin/minres coarse space 缺少合适的 left/test space。

## task017 后的路线修正

Task017 证明了一个重要区分：

```text
Petrov / adjoint-aware W 本身没有挽救 right-only lifted coarse correction；
但 true-FE sampled lift 能把 default100 p=1 h=5 residual 从 2.1466e-2 降到 3.6888e-3。
```

这说明 `top/bottom,(0,0),y` modal slow direction 不是误判；真正的问题是 Task016 的 `P_FE^{-1}C_j` 使用 positive same-H1 AMS 近似，太偏离 indefinite Maxwell `A_FE^{-1}C_j`。换言之，coarse space 的物理方向是对的，但 FE lift 不能用当前 positive proxy 草率替代。

| 路线 | Task017 证据 | 后续判断 |
|---|---|---|
| Petrov W / adjoint W | best improvement 仅 `1.000045x` 或变差 | 暂停 |
| true-FE sampled lift one-shot | `3.6888e-3`，`5.819x` | 继续 |
| true-FE lift right additive PC | KSP residual `2.3550e-2`，差于 baseline | 当前集成方式错误 |
| p=2 h=5 | strong gate 未过，KSP 未稳定 | task018 前继续关闭 |

下一步最值得尝试的不是继续扩大 W，而是把 true-FE sampled correction 换一种进入 Krylov 的方式：initial correction、augmented/recycled GMRES、left-preconditioned residual correction，或 small selected Schur solve。目标是保留 one-shot 的物理校正效果，而不是把它直接作为 right additive PC。

## task018 后的路线修正

Task018 已经把 Task017 的 one-shot 正信号转化为稳定的 solver-like process。

关键结果：

| 路线 | residual | improvement | 判断 |
|---|---:|---:|---|
| baseline FE-AMS + aux identity | `2.145878536e-2` | `1.000x` | reproduced |
| one-shot top_bottom_y, SciPy GMRES rtol `1e-2` | `1.732413109e-3` | `12.387x` | strong positive |
| initial correction omega `1.0` + 200-step continuation | `1.680968603e-3` | `12.766x` | stable positive |
| residual outer loop from zero | `1.661623468e-3` | `12.914x` | best, strong gate pass |
| projected residual GMRES + final coarse | `1.708423696e-3` | `12.561x` | positive but costlier |

新的判断是：

```text
The useful object is not a right additive PC.
The useful object is a low-dimensional residual-correction space built from top_bottom_y selected FE responses.
```

最有效流程是：

```text
repeat:
    run bounded FE-AMS segment
    compute true residual r = b - A x
    solve min_alpha ||r - A Z alpha||
    update x <- x + Z alpha
until stagnation
```

当前 best `Z` 应理解为 filtered selected FE response：

```text
Z_filtered = [ -A_FE_filtered^-1 C_J ; I_J ]
J = {top,(0,0),y; bottom,(0,0),y}
```

而不是越精确越好的 exact FE response。Task018 发现 selected FE RHS solve 收紧到 `1e-4/1e-6` 反而弱于 loose `1e-2`。因此后续 p=2 h=5 首轮应使用：

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

而不是盲目追求更精确 selected FE solve。

## Task018 暴露的工程化风险

### 风险 B：SciPy selected FE RHS 不是并行 production 路径

当前最强 selected FE response 来自：

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

它是：

```text
single-process / exported-matrix / research runner path
```

不是：

```text
MPI-distributed PETSc production path
```

因此：

```text
数学路线可以继续；
当前实现不能直接作为并行 production solver。
```

如果 p=2 h=5 也通过，后续工程化必须单独解决 selected FE RHS 的 production 形态，例如：

```text
1. MPI-distributed PETSc selected RHS solve；
2. isolated-process selected FE response service；
3. offline/cache selected response construction；
4. 或其他不污染 ordinary Stage4 solve 的 safe service layer。
```

### 风险 C：PETSc selected FE-AMS 同进程生命周期风险

Task018 重新尝试 PETSc selected FE-AMS opt-in path，结果：

```text
KSPSetUp/PCSetUp error 101
invalid communicator behavior risk
can poison later AMS communicator setup
```

这不是 selected Schur 数学路线失败，而是 PETSc/hypre AMS/KSP lifecycle 和 communicator 管理问题。

后续工程化必须注意：

```text
1. 避免在同一进程中 late/repeated setup/destroy 多个 hypre AMS helper；
2. 若使用 PETSc selected FE-AMS，需要 early setup and reuse；
3. 更稳妥方案是 isolated process / subprocess service；
4. MPI production 需要重新设计 communicator ownership、PC lifetime、destroy order；
5. 不要在 ordinary Stage4 solve 中默认启用当前 opt-in PETSc selected FE-AMS path。
```

## 当前推荐路线

Task019 应开启：

```text
p=2 h=5 qualification for residual-corrected true-FE sampled Schur
```

优先顺序：

```text
1. p=2 h=5 complex export / memory preflight；
2. p=2 h=5 baseline FE-AMS + aux identity, max_it=1000；
3. top_bottom_y SciPy GMRES diag rtol=1e-2 one-shot；
4. residual_outer_zero, segment_max_it=120, cycle 1 first；
5. if positive, continue cycles 2/3/4；
6. if still positive, compare segment_max_it=500/1000；
7. only if p=2 h=5 strong positive, discuss productionization and p=2 h=2 preflight。
```

继续关闭：

```text
full p=2 h=2
h=1.5
full 708-mode Schur
Petrov W expansion
right additive PC with true-FE basis
PETSc selected FE-AMS same-process RHS solve as main path
```

## 一句话总结

真正值得继续的路线已经从“real-split AMS/HX block PC”升级为：

```text
real-split AMS/HX FE block smoother
+ top_bottom_y filtered true-FE sampled Schur residual correction
+ adaptive outer loop / selected-mode coarse correction
```

这条线在 p=1 h=5 上已经通过 strong gate；下一步必须验证 p=2 h=5 可扩展性，并把 SciPy selected FE RHS 与 PETSc selected FE-AMS lifecycle 两个工程风险作为后续 productionization 的核心问题。

## Task019 后的 p=2 h=5 判断

Task019 对 `default100 p=2 h=5` 做了 gated qualification。结论是否定的：Task018 在 `p=1 h=5` 上成功的 `AMS/HX + top_bottom_y true-FE sampled Schur residual correction` 没有直接扩展到 p=2。

关键数据：

| 测试 | residual | improvement | 判断 |
|---|---:|---:|---|
| FE-AMS + aux identity, 120 steps | `1.6386e-2` | `1.000x` | baseline |
| FE-AMS continuation 到约 240 steps | `1.5816e-2` | `1.036x` | 下降太慢 |
| required `top_bottom_y` selected FE sampled Schur one-shot | `1.6357e-2` | `1.0018x` | gate fail |
| best low-dimensional enrichment | `1.5166e-2` | `1.0804x` | 弱正反馈，不足以继续作为主线 |

失败点不是 `top_bottom_y` mode mapping。p=2 baseline residual 的约 `92.7%` 仍位于 selected `top_bottom_y` auxiliary scalar components；问题在于低维 FE lift / sampled Schur 空间不能同时消除 auxiliary residual 和 FE coupling 后效应。

这把路线判断往文献里的另一类方法推：time-harmonic Maxwell 的 p=2 高阶、周期、DtN-port 不定系统需要 impedance transmission / sweeping / two-level Schwarz / adaptive coarse space，而不是只依赖正定 Maxwell AMS/HX 作为 FE lift。后续 Task020 应优先设计：

| 候选路线 | 与当前问题的关系 |
|---|---|
| optimized Schwarz / impedance DDM | 直接针对 time-harmonic Maxwell 不定传播，能处理子域间 outgoing 信息传递 |
| sweeping / moving PML / layered Schur | 当前结构是 z 分层 grating + top/bottom port，天然适合 sweep |
| two-level weighted Schwarz + adaptive coarse space | 文献中对带吸收 Maxwell 有鲁棒 GMRES 分析，可能比固定 `top_bottom_y` 空间更强 |
| matrix-free high-order FE matvec + DDM preconditioner | p=2 组装矩阵和 Python/PETSc PC 已接近 14GB 内存上限，matrix-free 是后续工程方向 |

一句话：Task019 后，低维 selected Schur 可以保留为诊断工具，但不应继续作为 p=2 生产求解器主线；下一步应从“模态低秩校正”转为“传播方向感知的区域分解/扫掠预条件器”。
