# MyFEniCS 开发模型与数值结果总账

> 作用：集中回答“研究对象是什么、已经计算过哪些模型、采用什么离散与求解方法、得到什么物理结果、付出多少内存与时间、最终是成功、失败还是尚未完成”。
>
> 本文不是某一个 Task 的总结，而是跨 Task 的项目总账。以后每次新增正式 PDE 模型、重型资源模型、成功迭代解或受控负结果，都必须更新本文；不得只把结果留在单个 `response_vN.md` 或 JSON record 中。

## 0. 阅读规则、数据口径与维护要求

### 0.1 状态定义

| 状态 | 通俗解释 | 使用条件 |
|---|---|---|
| `成功` | 模型完成求解，并通过该模型约定的残差、物理量、场和资源 Gate | 不能仅凭线性求解器返回成功判断 |
| `成功但有限定` | 主目标通过，但仍有明确适用边界 | 必须写清哪些能力没有证明 |
| `受控负结果` | 模型确实运行完成，但至少一个正式指标没有达到要求 | 必须列出具体失败数值，不能只写“10/12” |
| `失败` | 运行发生数值、实现或后处理失败，不能形成正式物理解 | 保留真实失败原因和证据 |
| `未完成` | 方法或代码只完成部分能力，还没有正式 PDE 候选 | 不能把 fixture/correctness 写成模型成功 |
| `未运行` | 因资源、安全、架构或任务 Gate 没有启动 | 必须说明停止原因 |

### 0.2 主要物理量

| 符号 | 含义 |
|---|---|
| `R00` | 零级反射功率；三维时应写清偏振，例如 `R(0,0)_s` |
| `R_total` | 所有纳入端口后处理的反射衍射级功率之和 |
| `T00` | 零级透射功率 |
| `T_total` | 所有透射衍射级功率之和 |
| `A_balance` | `1-R_total-T_total`，用于能量闭合 |
| `A_volume` | 由材料体吸收积分得到的吸收；有记录时与 `A_balance` 同列 |
| `r(m,n)` / `t(m,n)` | 复衍射振幅，包含幅值与相位；只有正式记录存在时才填写 |
| `DoF` | 完整有限元离散空间的自由度；静态凝聚模型还要另外报告实际求解 rows |
| `rows` | 真正送入全局线性求解器的矩阵行数 |
| `NNZ` | 稀疏矩阵非零元数量；直接法还应报告 LU factor NNZ |

### 0.3 当前固定目标模型的 12 个显著衍射通道

Task035b 在 `13.5 nm`、固定矩形块光栅、S 偏振目标上，以参考功率阈值 `1e-8` 冻结了 12 个显著通道。本文所有具备逐级数据的模型均优先报告这些通道：

```text
反射：R(0,0), R(-1,0), R(-2,0), R(-4,0), R(-5,0), R(-7,0)
透射：T(0,0), T(-1,0), T(-2,0), T(-4,0), T(-5,0), T(-7,0)
```

历史文档中若采用 `R10`、`T00` 等无括号写法，必须在表旁说明索引方向，避免把 `R(1,0)` 与 `R(-1,0)` 混淆。COMSOL 历史模型如果只保存 `R00/R/T/A`，逐级列必须写 `未记录`，不能由总量反推。

### 0.4 统一模型总表的最低字段

以后新增模型至少填写：

```text
模型 ID / Task / 物理模型 / 波长 / 入射角 / 偏振 / 边界条件
单元类型 / 几何阶次 / 场阶次 p / 网格尺度 h / 单元数
离散方法 / Full3D 或 Hybrid / 直接法或迭代法 / 求解器 / 预条件器
完整 DoF / active rows / matrix NNZ / factor NNZ / Hybrid M / QEP 或 modal rows
R00 / 12 个显著 R/T 通道 / R_total / T_total / A_balance / A_volume
复振幅（存在时）/ full explicit residual
组装时间 / symbolic / numeric factorization / backsolve / postprocess / 总时间
RSS/PSS/cgroup 峰值 / swap / 数据 SHA / evidence path / 最终状态 / 失败原因
```

---

# 1. 开发阶段的研究对象

## 1.1 Task034/Task035/Task035b 固定矩形块光栅主线

| 项目 | 当前主线设置 | 说明 |
|---|---|---|
| 波长 | `13.5 nm` | EUV 主目标 |
| 周期单元横向尺寸 | `50 nm × 25 nm` | x/y 双周期 |
| z 向计算域 | 约 `140 nm` | 下部基底、120 nm 光栅高度及上部空气区；具体边界以 Case093/095 配置为准 |
| 几何 | 固定矩形块光栅 | Task035b 明确排除斜侧壁、圆角、粗糙度和任意不规则几何 |
| 主偏振 | S polarization | Task034 以后收敛主线 |
| 入射 | `10° grazing` | 文档中也可能写成相对法线 `80°`，必须注明角度定义 |
| 横向边界 | x/y Floquet 双周期 | slave/master 具有复相位关系 |
| 上下边界 | 周期端口/DtN 辅助变量 | 当前正式系统增加 80 个外部辅助 rows |
| 核心输出 | `R00`、`R_total`、`T_total`、`A_balance/A_volume`、12 个显著通道和复振幅 | Task035b 的同误差 Gate 不允许只看总 R/T |

## 1.2 COMSOL 约 117.8 万 DoF 的迭代求解器基准

这是另一个历史基准族，不能与上面的 S 偏振逐级衍射模型直接混为同一个模型：

| 项目 | 设置 |
|---|---|
| 周期单元 | `50 nm × 25 nm` |
| 几何 | 上空气块 `50×25×130 nm`、下基底 `50×25×10 nm`、中心光栅块 `16×25×120 nm` |
| 波长/入射 | `13.5 nm`，P 偏振，相对法线 `80°` |
| 网格 | 182,393 个自由四面体，`h=2.5 nm` |
| 场单元 | COMSOL 默认二阶 curl-conforming Nédélec |
| DoF | 1,178,238 |
| 端口 | 只加入零级衍射；因此 `R_total=R00`、`T_total=T00` |
| 用途 | 比较 MUMPS 与成功 GMG 预条件迭代法的时间、内存和零级结果 |

---

# 2. 已验证成功模型

本章只放通过各自正式 Gate 的模型。精度受控负结果、资源停止和方法探索统一放到第 3 章。

## 2.1 COMSOL 收敛参考

### 2.1.1 COMSOL 直接法

方法：COMSOL 6.4 使用 curl-conforming 电场单元和 MUMPS。`编译`对应方程/单元组装准备，`求解`主要包含直接法分析和分解。以下为主目标固定矩形光栅的代表性收敛点；完整 p2–p6、四面体/六面体表见 `docs/COMSOL_direct_solver_report.md`。

| 模型 | 单元/场阶次 | h (nm) | DoF | R00 | R_total | T_total | A | R+T+A | 编译 s | 求解 s | 总时间 s | 物理/虚拟内存 GB | 逐级衍射 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| COMSOL-p4-hex-h5 | 六面体/p4 | 5.0 | 339,972 | 0.000757190 | 0.000766316 | 0.602677531 | 0.396652507 | 1.000096353 | 10 | 95 | 105 | 25.49 / 29.56 | 未记录 | 成功 |
| COMSOL-p4-hex-h3 | 六面体/p4 | 3.0 | 1,540,028 | 0.000753065 | 0.000762185 | 0.602706300 | 0.396540399 | 1.000008884 | 10 | 413 | 423 | 126.11 / 145.79 | 未记录 | 成功 |
| COMSOL-p4-hex-h2 | 六面体/p4 | 2.0 | 4,818,792 | 0.000752895 | 0.000762014 | 0.602707488 | 0.396531295 | 1.000000797 | 12 | 7,216 | 7,228 | 238.21 / 266.56 | 未记录 | 成功；收敛锚点 |
| COMSOL-p4-tet-h3 | 四面体/p4 | 3.0 | 4,323,924 | 0.000752897 | 0.000762016 | 0.602707468 | 0.396530921 | 1.000000405 | 10 | 7,014 | 7,024 | 132.70 / 181.82 | 未记录 | 成功；跨单元核验 |
| COMSOL-p6-hex-h7.5 | 六面体/p6 | 7.5 | 488,150 | 0.000752896 | 0.000762015 | 0.602707484 | 约0.3965305 | 约1 | 见源报告 | 见源报告 | 见源报告 | 见源报告 | 未记录 | 成功；高阶锚点 |
| COMSOL-p6-tet-h7 | 四面体/p6 | 7.0 | 950,924 | 0.000752895 | 0.000762014 | 0.602707512 | 约0.3965305 | 约1 | 见源报告 | 见源报告 | 见源报告 | 见源报告 | 未记录 | 成功；高阶锚点 |

当前跨软件标量收敛中心：

```text
R00 ≈ 0.000752895
R_total ≈ 0.000762014
T_total ≈ 0.6027075
A ≈ 0.3965305
```

COMSOL 该报告没有保存 12 个显著通道的逐级功率和复振幅，因此不得把上述总量用于替代 Task035b 的逐级 Gate。

### 2.1.2 COMSOL 迭代法

以下模型属于第 1.2 节的 P 偏振、仅零级基准。成功的关键不是裸 Krylov，而是 `Krylov + 五层 GMG + 电场块平滑 + 粗层 MUMPS`。

| 模型 | 外层/预条件 | DoF | R00=R_total | T00=T_total | A | Δ(R+T) 对直接法 | 线性迭代 | 峰值内存 GB | 求解器/总时间 s | 非零衍射级 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| direct_mumps | MUMPS | 1,178,238 | 0.0008229665 | 0.6167277217 | 0.3824493118 | 0 | 不适用 | 22.989 | 269 / 282 | 未启用 | 成功；直接参考 |
| gmres-gmg-r300 | 右 GMRES+GMG，restart 300 | 1,178,238 | 约0.00082297 | 0.61672815 | 约0.38244946 | 4.31e-7 | 源记录 | 13.376 | 源记录 / 232 | 未启用 | 成功 |
| gmres-gmg-r100 | 右 GMRES+GMG，restart 100 | 1,178,238 | 约0.00082297 | 0.61672773 | 约0.38244928 | 1.95e-8 | 544 | 11.699 | 404 / 417 | 未启用 | 成功；推荐折中 |
| gmres-gmg-r50 | 右 GMRES+GMG，restart 50 | 1,178,238 | 约0.00082297 | 0.61672769 | 约0.38244930 | 3.20e-8 | 源记录 | 10.547 | 源记录 / 750 | 未启用 | 成功；更低内存 |
| tfqmr-gmg | 右 TFQMR+GMG | 1,178,238 | 约0.00082297 | 0.61672768 | 约0.38244931 | 3.72e-8 | 1,142 | 9.010 | 787 / 800 | 未启用 | 成功；最低成功内存 |
| gmres-directpre | GMRES+DirectPreconditioner | 1,178,238 | 0.00082297 | 0.61672772 | 0.38244931 | 1.19e-13 | 源记录 | 23.110 | 源记录 / 337 | 未启用 | 数值成功，但不节省内存 |

## 2.2 FEniCS 原始完整矩阵法直接法

通俗解释：由 UFL 的 `a(u,v)` 生成 FFCx 单元核，使用 DOLFINx/PETSc 直接组装包含 edge、face、cell-interior 全部未知量的全局稀疏矩阵，再施加 Floquet 和 DtN，最后由 MUMPS 求解。这里没有在单元内部先消去 cell-interior DoF。

### 2.2.1 Full3D

| 模型 | Task/目的 | p/h | 单元 | Full DoF/rows | matrix NNZ | factor NNZ | R00 | R_total | T_total | A | residual | 峰值 GiB | 组装/求解时间 | 逐级衍射 | 状态 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Full3D-p2-h5 | Task034 uniform benchmark | p2/h5 | structured hex | 44,698 / 44,778 | 历史表未统一 | 历史表未统一 | 0.0890130359 | 0.0890216029 | 0.442588279 | 0.468390118 | pass | 2.960 | 16.568 s total | 未统一登记 | 成功 |
| Full3D-p3-h5 | Task034 uniform benchmark | p3/h5 | structured hex | 145,863 / 145,943 | 历史表未统一 | 历史表未统一 | 0.00108058337 | 0.00109010701 | 0.600622478 | 0.398287415 | pass | 9.040 | 149.658 s total | 未统一登记 | 成功 |
| Full3D-p3-h3 | Task034 fine direct anchor | p3/h3 | structured hex | 656,325 / 656,405 | 历史表未统一 | 1,307,605,045 | 0.000780309834 | 0.000789467957 | 0.602514984 | 0.396695548 | pass | 44.069 | 1,726.362 s total | 未统一登记 | 成功 |
| Full3D-p4-h5 | Task034 p/h anchor | p4/h5 | structured hex | 339,892 / 339,972 | 历史表未统一 | 历史表未统一 | 0.000757187647 | 0.000766313377 | 0.602677531 | 0.396556156 | pass | 28.888 | 917.470 s total | 未统一登记 | 成功 |
| Full3D-p6-h10-full-A | Task035b 原始完整矩阵资源基线 | p6/h10 | 252 structured hex | 173,802 / 173,882 | 210,353,120 | 386,625,292 | 0.000753761 | 0.000762881 | 0.602701634 | 0.396535485 | 1.26e-11 | 35.024 | 历史 full-matrix control | 见第2.4逐级表 | 成功；资源基线 |

### 2.2.2 Hybrid

Hybrid 将上下局部三维 FE 与中间模态/QEP 区域耦合。`M` 是每个方向保留的模态规模参数；modal unknowns 为两端或双向模态未知量总数。

| 模型 | Task | p/h | M | local FE DoF | external aux | modal unknowns | total rows | R00 | R_total | T_total | A | peak GiB | total s | 逐级衍射 | 状态 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Hybrid-p2-h5 | Task034 | p2/h5 | 160 | 13,652 | 80 | 320 | 14,052 | 0.0890118197 | 0.0890210691 | 0.442586743 | 0.468392188 | 3.285 | 96.284 | 未统一登记 | 成功 |
| Hybrid-p3-h5 | Task034 | p3/h5 | 160 | 43,614 | 80 | 320 | 44,014 | 0.00108058359 | 0.00109009569 | 0.600622368 | 0.398287536 | 4.908 | 143.515 | 未统一登记 | 成功 |
| Hybrid-p3-h3 | Task034 | p3/h3 | 160 | 223,770 | 80 | 320 | 224,170 | 0.000780309829 | 0.000789467334 | 0.602514979 | 0.396695554 | 14.272 | 661.410 | 未统一登记 | 成功 |
| Hybrid-p4-h5 | Task034 | p4/h5 | 160 | 100,520 | 80 | 320 | 100,920 | 0.000757187631 | 0.000766313235 | 0.602677530 | 0.396556157 | 9.206 | 412.422 | 未统一登记 | 成功 |
| Hybrid-p3-h2 | Task034 | p3/h2 | 160 | 595,956 | 80 | 320 | 596,356 | 0.000755344038 | 0.000764466671 | 0.602690128 | 0.396545405 | 49.642 | 3,513.818 | 未统一登记 | 成功但无 Full3D closure/M funnel |

## 2.3 FEniCS 原始完整矩阵法迭代法

### 2.3.1 Full3D

| 模型 | Task | 全局矩阵方法 | Krylov | 预条件器 | DoF/rows | 收敛历史 | official R/T/A | 峰值/时间 | 状态 |
|---|---|---|---|---|---:|---|---|---|---|
| Task023 PETSc response-PC 样例 | Task023 | 原始完整矩阵 | GMRES/FGMRES | FE-response/研究型 PC | 见 Task023 record | 部分小模型成功 | 见对应 record | 见对应 record | 成功能力样例；待回填统一数值 |
| Task024 engineering fast-track | Task024 | 原始完整矩阵 | 多种 Krylov | ASM/RAS/ILU 等 | 见 Task024 | 大型目标多数不收敛 | 未形成统一成功主线 | 见对应 records | 探索；详见第3章 |

> 这里不能把 COMSOL 的 GMG 成功结果当作 FEniCS 成功结果。Codex 后续应从 Task023/024 原始 records 回填每个真正成功的 FEniCS 模型，而不是只保留上述概括行。

### 2.3.2 Hybrid

目前没有完成统一资格化的“原始完整矩阵 Hybrid + 迭代法”成功模型。

| 模型 | 状态 | 缺口 |
|---|---|---|
| Hybrid iterative mainline | 未完成 | 缺正式预条件器、残差历史、Full3D/Hybrid observable closure 和资源 authority |

## 2.4 静态凝聚法直接法

通俗解释：仍由 UFL/FFCx 计算每个单元的局部矩阵，但在单元内部先精确消去只属于该单元的 cell-interior DoF，只把 edge/face trace DoF 组装成全局矩阵；Floquet slave 也在插入前映射到 master。求解后再逐单元恢复完整场。它是精确块消元，不是删掉物理模式。

### 2.4.1 Full3D

#### 2.4.1-a 总量、资源和状态

| 模型 | Task/目的 | 空间与网格 | Full DoF | active rows含DtN | matrix/factor NNZ | R00 | R_total | T_total | A | residual | peak GiB | build / MUMPS setup / backsolve s | 状态 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| p6-h10 post-assembly Schur | Task035b 早期原型 | global p6/h10 | 173,802 | 60,482 | 52,058,162 / 243,270,308 | 与p6参考等价 | 0.000762881 | 0.602701634 | 0.396535485 | pass | 29.212 | 先组完整A再凝聚 | 成功但内存收益有限 |
| p6-h10 assembly-time condensed | Task035b 工程主线 | global p6/h10 | 173,802 | 51,272 | 41,989,040 / 约202–212M | 0.000753761 | 0.000762881 | 0.602701634 | 0.396535485 | 1.26e-11 | 15.964 isolated | 102.32 / 102.54 / 0.167 | 成功；best discrete reference |
| p5trace-p6interior-h15 | Task035b 压缩种子 | fixed p5 trace+p6 interior `(6,2,10)` | 74,890 | 16,880 | 9,195,812 / 27,916,600 | 0.000755888 | 0.000765024 | 0.602685147 | 0.396549829 | 8.83e-12 | 5.803 MPI8；1.295 MPI1资源点 | 61.61旧 / 6.56 / 0.036；新cold/warm build 19.24/6.14 | 受控负结果：逐级精度失败 |
| p5trace-p6interior-h14 | z方向加密判别 | `(6,2,11)` | 82,315 | 18,500 | 10,104,512 / 31,347,000 | 见record | 见record | 见record | 见record | 4.45e-12 | 6.376 | 62.31 / 11.47 / 0.032 | 受控负结果；有恢复信号 |
| p5trace-p6interior-h13 | 当前预算内最佳 | `(6,2,12)` | 89,740 | 20,120 | 11,013,212 / 36,273,200 | 0.000756118 | 0.000765247 | 0.602682452 | 0.396552302 | 5.81e-12 | 6.411 accuracy；5.030 setup profile | 59.86旧；新cold/warm 19.41/6.70；MUMPS 13.34 | 受控负结果；尚非同误差候选 |
| global-p6-h14 | full trace判别 | full p6 `(6,2,11)` | 92,850 | 27,080 | 21,110,096 / 67,325,792 | 见record | 见record | 见record | 见record | 1.47e-11 | 12.587 pair | 89.48 / 25.36 / 0.063 | 受控负结果且超90k |

#### 2.4.1-b 12 个显著衍射通道功率

`参考 p6/h10` 是当前冻结的 same-code 高阶离散参考，不代表严格连续真值。

| 模型 | R00 | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | T00 | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | 具体不满足项 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| p6/h10参考 | 7.53761220068e-4 | 6.66930965425e-6 | 1.47769085130e-6 | 2.67523960967e-7 | 7.45730053677e-8 | 6.26354242222e-7 | 6.02673872347e-1 | 2.17816739855e-5 | 2.95984139513e-6 | 4.37288897207e-7 | 2.11920825720e-7 | 2.36201044924e-6 | 无；reference v1 |
| p5trace/p6interior h15 | 7.55888313624e-4 | 6.68359026100e-6 | 1.48261801533e-6 | 2.60181249500e-7 | 7.78127363894e-8 | 6.27007582029e-7 | 6.02657398112e-1 | 2.18040789857e-5 | 2.94463911877e-6 | 4.12666159013e-7 | 2.15875293566e-7 | 2.36220894231e-6 | power失败：R/T(-2,-4,-5)，共6项 |
| p5trace/p6interior h13 | 7.56117570116e-4 | 6.67510914774e-6 | 1.47657836307e-6 | 2.72339140129e-7 | 7.35017831938e-8 | 6.26378308638e-7 | 6.02654698626e-1 | 2.17753807955e-5 | 2.95868518886e-6 | 4.35489199428e-7 | 2.12204228069e-7 | 2.36225288824e-6 | power失败：R(-4,0)、T(-4,0) |

#### 2.4.1-c 复衍射振幅

| 模型/通道 | r/t complex amplitude | 状态说明 |
|---|---|---|
| p6/h10 `r(0,0)` | `-2.52523043536e-2 + 1.07741517021e-2 i` | reference |
| p6/h10 `t(0,0)` | `6.31378703348e-1 + 4.73020981038e-1 i` | reference |
| h15 `r(-4,0)` | `2.06054361758e-4 - 5.41082464827e-5 i` | 不满足 reference band |
| h15 `r(-5,0)` | `-1.00138975344e-4 - 6.69829310030e-5 i` | 不满足 reference band |
| h15 `t(-2,0)` | `-6.91980021337e-4 + 3.04622473840e-4 i` | 不满足 reference band |
| h15 `t(-4,0)` | `-2.49901308066e-4 + 9.80178800675e-5 i` | 不满足 reference band |
| h15 `t(-5,0)` | `1.39598241988e-4 + 1.44313125131e-4 i` | 不满足 reference band |
| h13 `r(-4,0)` | `2.12784701368e-4 - 4.72186363878e-5 i` | 不满足 reference band |
| h13 `r(-5,0)` | `-1.00926387945e-4 - 5.93655036535e-5 i` | 不满足 reference band |

### 2.4.2 Hybrid

目前没有通过 `<=90k + 12/12 power + 12/12 complex amplitude` 的静态凝聚 Full3D 候选，所以没有资格进入 Hybrid closure。

| 模型 | 状态 | 原因 |
|---|---|---|
| Static-condensed Hybrid | 未运行 | Full3D selected candidate 为 `null`，继续运行会把 Full3D 空间误差、Hybrid接口误差和 M 截断混在一起 |

## 2.5 静态凝聚法迭代法

### 2.5.1 Full3D

以下是正式运行过的 MPI8 screen，但全部未收敛，因此属于第3章的受控负结果，不是成功模型：

| 模型 | Krylov/预条件 | rows | factor inventory | 200步后残差比 | explicit/full residual | peak GiB | 时间 s | official物理量 | 状态 |
|---|---|---:|---|---:|---:|---:|---:|---|---|
| condensed-jacobi | GMRES(30)+Jacobi | 16,880 | global factor 0 | 0.861662 | 0.861662 / 0.861661 | 3.921 | 39.534 | 未产生 | 受控负结果；不收敛 |
| condensed-asm-ilu | FGMRES(30)+ASM(1)/ILU(0) | 16,880 | local ILU active | 0.999661 | 0.999661 / 0.999659 | 4.462 | 46.073 | 未产生 | 受控负结果；不收敛 |
| condensed-zslab-dtn | FGMRES+z-slab ILU+DtN trace Galerkin | 16,880 | 22,280 local factor rows、9,576,512 ILU NNZ、80×80 coarse LU | 0.996265 | 0.996265 / 0.996263 | 3.885 | 49.946 | 未产生 | 受控负结果；不收敛 |

### 2.5.2 Hybrid

| 模型 | 状态 | 缺口 |
|---|---|---|
| Static-condensed Hybrid iterative | 待定/未运行 | 先需要成功的 Full3D静态凝聚候选和实质不同的 H(curl)/trace 预条件器 |

## 2.6 自适应求解

### 2.6.1 Full3D

目前没有达到“自动选择 h 或 p、生成合法新空间、重新求解并通过同误差 Gate”的成功生产模型。

| 模型 | Task | 自适应对象 | 目标量 | 结果 | 状态 |
|---|---|---|---|---|---|
| tetra one-local-h | Task035 | 周期四面体局部 h | R/T/A vector与 strict-R | refined p5 达101,210 DoF；vector误差6.3581e-4，strict-R误差4.3764e-4 | 方法可运行，但超90k且未闭合同误差 |
| tetra fixed-mesh p6 | Task035 | h细化后全局p提升 | 同上 | 167,784 DoF；vector误差1.0224e-4，strict-R误差5.1371e-5 | 精度改善，但超预算 |
| hexa classifier v3 | Task035b | 252 cells 的 p-up/p-keep分类 | DWR+投影/平滑性 | 102 p-up、150 p-keep、0 h-refine、0 p-down | 研究信号成功，production未资格化 |
| physical selective trace | Task035b | edge/face p6 trace orbit | 三个剩余失败通道 | fixture能省略inactive rows，但 actual DWR、runner、PDE均为0 | 未完成 |

### 2.6.2 Hybrid

| 模型 | 状态 | 缺口 |
|---|---|---|
| Adaptive Hybrid | 未运行 | 没有通过同误差 Gate 的自适应 Full3D空间，也没有自适应接口 trace 与 QEP/M 联合策略 |

---

# 3. 所有 Task 的探索模型

本章按 Task 记录探索目的、实际模型、具体结果和最终分类。完整逐行事实仍以各 Task 的 `outcomes/all_model_results.*` 或 `all_candidates.*` 为准；本文必须保持一眼可读，不隐藏失败数值。

## 3.1 Task023：PETSc/MPI FE-response 预条件探索

| 模型/目的 | 方法 | 主要结果 | 状态 |
|---|---|---|---|
| 验证复杂 Maxwell 系统可挂接自定义响应预条件器 | PETSc Krylov + FE-response PC | 小规模路径形成可执行能力；大型目标尚未形成统一生产结果 | 成功能力样例；数值待回填 |

## 3.2 Task024：工程迭代求解器快速路线

| 模型/目的 | 方法 | 主要结果 | 状态 |
|---|---|---|---|
| 降低 Full3D MUMPS 内存 | GMRES/FGMRES + Jacobi/ASM/RAS/ILU 等 | 多个大型复数非Hermitian Maxwell目标出现残差停滞；未形成可替代MUMPS的生产模型 | 受控负结果/未完成 |
| COMSOL成功迭代参照 | GMRES/TFQMR + GMG | 约117.8万DoF下9–13.4GB成功，证明“强多层H(curl)预条件”可行 | 外部软件成功参照，不是FEniCS能力 |

## 3.3 Task029：Full3D 直接法内存取证

| 模型/探索目的 | 具体结果 | 最终状态 |
|---|---|---|
| h3 MPI4 MUMPS baseline，找峰值来源 | 198,518 rows；21,317,860 matrix NNZ；266,127,836 factor NNZ；峰值约8.65GiB；峰值主要在KSPSetUp分析/LU，KSPSolve增量约7MB | 诊断成功 |
| 提前释放A_base/b_base | h3内存约下降5.46% | 工程正结果，但不是独立低内存profile |
| MPI2 MUMPS | h3内存下降约15.12% | 诊断正结果，未提升默认 |
| OOC | h5内存下降约13.74%，以磁盘换RAM | fallback，非推荐主线 |
| BLR 1e-5 | 内存反增且残差/RTA失败 | 受控负结果 |
| SuperLU_DIST | 当前目标内存增加约14.46% | 受控负结果 |
| MPI1×4线程 | factorization有效CPU约1核，未获得线程加速 | 当前镜像能力负结果 |

## 3.4 Task032：Hybrid、场恢复与低存储组件

| 模型/探索目的 | 方法与结果 | 状态 |
|---|---|---|
| real-QEP Hybrid integration | Full3D局部FE + QEP模态耦合，形成正式Hybrid流程 | 成功 |
| Hybrid field reconstruction | 恢复体场、接口场、R/T/A与A_volume | 成功 |
| Schur/生命周期研究 | 为后续Task035b静态凝聚和低存储路径提供基础 | 成功但需按后续任务重新资格化 |

## 3.5 Task033：高阶 Floquet、Hybrid 与 hp 路线

| 模型/探索目的 | 结果 | 状态 |
|---|---|---|
| 高阶N1curl Floquet配对 | p2 hexa面内部DoF需Basix entity transform，不能按点值一一配对 | 架构结论成功 |
| Hybrid高阶接口 | 形成高阶trace/模态耦合研究路线 | 部分成功/持续研究 |
| hp规划 | 明确face-interior local-p、exact-sequence和周期闭包需求 | 规划成功，production未完成 |

## 3.6 Task034：工作站、Full3D/Hybrid、M与MPI扩展

| 模型/探索目的 | 关键数值 | 状态 |
|---|---|---|
| p2/p3/p4 Full3D uniform ladder | 代表行见2.2.1；p4/h5为339,972 rows、R=0.000766313377、T=0.602677531、28.888GiB、917.47s | 成功 |
| Hybrid uniform ladder | 代表行见2.2.2；p4/h5 M160为100,920 rows、9.206GiB、412.42s | 成功 |
| p3/h3 M funnel | M80/120/160时间529.56/567.57/661.41s；完整逐行见Task034表2 | 成功，M收敛按原Gate |
| Full3D/Hybrid MPI identity | MPI1/8/16通过，MPI32 exploratory | 成功但有限定 |
| graded mesh机制 | 网格/Floquet/标记可运行 | 机制成功 |
| equal-accuracy graded compression | 三档均未通过固定Full3D同误差Gate | 受控负结果 |
| p2/h1 Full3D | assembly后因资源Gate停止；无official解 | 未运行完整求解 |
| p2/h1 Hybrid | field recovery 7200s timeout；无official解 | 失败/未完成 |
| 0.7nm资源模型 | 当前布局存在单组件超2TiB；production feasibility unknown | 工程压力测试，不是可行性证明 |

## 3.7 Task035：目标驱动 h/p 自适应研究

| 模型/目的 | DoF/rows/NNZ | 具体误差结果 | 状态 |
|---|---:|---|---|
| tetra h50 base p5 | 15,405/15,485/3,726,879 | R/T/A vector L2误差2.2032e-2；strict-R误差1.5130e-3 | 基线成功 |
| one-local-h p5 | 101,210/101,290/23,913,006 | vector误差6.3581e-4；strict-R误差4.3764e-4 | 精度改善但超90k |
| refined mesh p6 | 167,784/167,864/57,609,056 | vector误差1.0224e-4；strict-R误差5.1371e-5 | 精度改善但超预算 |
| h-vs-p竞争 | local-h的vector gain/DoF更好；p-up的strict-R gain/DoF更好 | 没有单一winner；不是same-patch决策authority |
| structured-hexa local-h | 无hanging-node/transition约束路径 | 未运行/架构缺失 |

## 3.8 Task035b：高阶局部 hp、静态凝聚、通道恢复和资源包络

| 模型/探索目的 | 具体结果 | 不满足项 | 最终状态 |
|---|---|---|---|
| global p4/p5/p6 h10参考 | p4/p5/p6 R00分别0.001872161/0.000785714/0.000753761；p6 R/T/A=0.000762881/0.602701634/0.396535485 | p6只作为best available discrete reference | 成功参考 |
| post-assembly Schur | rows降至60,482但峰值仍29.212GiB | full A与Schur生命周期重叠 | 工程正结果但不足 |
| assembly-time Schur | rows 51,272，峰值约15.964GiB isolated | trace系统更宽，迭代预条件更难 | 工程成功 |
| p5trace/p6interior h15 | 74,890 DoF、16,880 rows、5.803GiB；总量通过 | power具体失败R/T(-2,-4,-5)；复振幅失败r(-4,-5)、t(-2,-4,-5) | 受控负结果 |
| directional-z h14 | 82,315 DoF；power/amplitude 7/12、9/12 | power失败T(-4,-5)、R(-2,-4,-5)；幅值失败T(-4,-5)、R(-5) | 受控负结果，有正信号 |
| directional-z h13 | 89,740 DoF；R/T/A=0.000765247/0.602682452/0.396552302 | power失败R(-4)、T(-4)；幅值失败r(-4)、r(-5) | 当前预算内最佳，仍受控负结果 |
| full-p6 trace h14 | 92,850 DoF；power 9/12、amplitude 12/12 | power失败R(-4)、T(-4,-5)；超预算2,850 DoF | 诊断正信号，非候选 |
| z-node top2 redistribution | h13同DoF，实际8/12+8/12 | 比unchanged h13退化 | 受控负结果，lane关闭 |
| selective p6 trace | fixture中inactive rows=0，MatShell action正确 | actual DWR=0、runner=false、PDE=0 | 未完成 |
| setup cold/warm | h15 non-KSP 61.61→19.24s，warm 6.14s；h13 cold/warm19.41/6.70s | same-RHS在线路径和symbolic reuse未形成authority | 工程成功但仍有缺口 |
| direct MPI rank study | h15 MPI1/2/4/8峰值1.295/2.158/3.100/4.711GiB；MPI8最快53.90s | MPI1最低内存但较慢；affinity/ordering未记录 | 成功资源研究 |
| 三条condensed iterative | 残差比0.8617/0.9997/0.9963 | 200步均不收敛，无official物理输出 | 三个受控负结果 |
| Hybrid/M/0.7nm v3 | selected candidate=0 | Full3D逐级Gate未通过 | 未运行 |

---

# 4. 后续维护模板

每个新 Task 应在本文件新增一节，并至少增加以下两类表：

## 4.1 模型总量与资源表模板

| 模型ID | Task | 目的 | 物理模型 | 方法 | p/h/M/MPI | DoF/rows/NNZ/factor | R00/R/T/A/Avol | residual | memory | phase time | status | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## 4.2 逐级衍射表模板

| 模型ID | R00 | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | T00 | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | R_total | T_total | A | 复振幅记录 | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

若未来显著通道集合因波长、角度、偏振或几何改变而变化，应为该模型族定义新的 channel set，不得强行沿用本文件的 12 通道。

---

# 5. 当前主要证据索引

- COMSOL p2–p6直接法：`docs/COMSOL_direct_solver_report.md`
- COMSOL 117.8万DoF直接/迭代对照：`docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md`
- Task029：`docs/task029_stage4_direct_memory_forensics/outcomes/summary.md`
- Task034统一40行事实表：`docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、`all_model_results.json/csv`
- Task035：`docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md`
- Task035b：`docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md`、`all_candidates.json/csv`
- 12通道参考：`benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`
- Task035b Response V3：`docs/task035b_high_order_local_hp_resource_envelope/response_v3.md`
