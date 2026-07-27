# 开发阶段研究对象与计算结果总账

> **用途。** 本文是项目级“模型—方法—结果—资源—状态”总账。它不替代各 Task 的 `task.md`、`outcomes/summary.md`、`response_vN.md` 和正式 JSON record，而是把分散在不同任务中的重型计算统一登记，便于回答：已经算过什么、使用什么算法、得到什么物理结果、消耗多少资源、哪些结果可作为参考、哪些只是探索或负结果。
>
> **维护规则。** 从本文建立起，每次新增正式 PDE、QEP、Hybrid、迭代或自适应模型，都必须在对应 Task 收口时同步更新本文。历史记录没有保存的字段必须写“历史未记录”，当前未执行的字段写 `not_run`，不得猜测。

---

## 0. 阅读方法、物理对象与统一记号

### 0.1 本文区分的三类物理配置

不同软件或不同 Task 并不总是使用完全相同的几何、偏振和衍射级集合，因此不能把所有数值混为一个收敛序列。

| 配置 ID | 用途 | 周期单元 / 几何 | 波长与入射 | 偏振 | 边界与衍射级 | 主要来源 |
|---|---|---|---|---|---|---|
| `C-COMSOL-P0` | COMSOL 直接/迭代求解器对照 | 周期 `50×25 nm`；空气 `50×25×130 nm`；基底 `50×25×10 nm`；光栅 `16×25×120 nm` | `13.5 nm`；`80°`（相对法线） | P | 两周期端口 + 双 Floquet；仅 `(0,0)` 零级 | `task029/.../comsol_3d_direct_iterative_memory_report.md` |
| `F-STAGE4-S` | FEniCS Stage4 原始完整 FE 矩阵、Hybrid 和迭代主线 | 单元 `50×25×140 nm`；Si 块 `17×25×120 nm` | `13.5 nm`；`theta=80°`、`phi=0°`，即 `10°` 掠入射 | S | 双 Floquet + Fourier-DtN；top/bottom 各 40 个传播模态，共 80 个辅助量 | Task027–Task033 |
| `F-HO-S` | FEniCS 高阶、h/p、自适应、静态凝聚与Hybrid高阶闭合主线 | Task034 冻结规则矩形光栅；与 `F-STAGE4-S` 同一工程主点族 | `13.5 nm`；`10°` 掠入射 | S | 双 Floquet + DtN；显著衍射级使用 Task035b reference v1 | Task034–Task035c |

### 0.2 总量、自由度和资源字段

| 字段 | 通俗解释 |
|---|---|
| `FE DoF` / `Full3D-equivalent DoF` | 完整有限元场若全部作为未知量时的自由度。静态凝聚后，其中部分内部自由度不再进入全局求解器，但仍会在求解后恢复。 |
| `rows` / `active rows` | 实际送入 PETSc/MUMPS/Krylov 的全局未知量数量。 |
| `matrix NNZ` | 全局稀疏矩阵中实际非零元素个数。 |
| `factor NNZ` | MUMPS 或局部 ILU/LU 分解产生的因子非零元素；通常大于原矩阵 NNZ。 |
| `R00` | 零级反射功率；在 S 偏振单场模型中等同 `R(0,0)_s`。 |
| `Rtotal` / `Ttotal` | 所有已启用传播衍射级的总反射/总透射。 |
| `A_volume` | 材料体吸收；与 `1-R-T` 的闭合关系需要单独检查。 |
| `Aclosure` | `1-Rtotal-Ttotal`。它是能量闭合定义，不一定等于独立体积分得到的 `A_volume`。 |
| `complex amplitude` | 衍射通道的复振幅，包含幅值和相位；反演和弱衍射级比较时通常比只看功率更敏感。 |
| `peak memory` | 必须注明 RSS/PSS/cgroup、MPI 数和生命周期；不同口径不得直接相减。 |
| `build` | 有限元准备阶段；需要进一步区分 mesh、function space、单元 tensor、Schur、全局插入和 DtN。 |
| `MUMPS setup` | MUMPS symbolic analysis + numeric LU factorization，不是最终回代。 |
| `solve/backsolve` | 已有 LU 后的前后代入；直接法中通常很短。 |

### 0.3 固定登记的显著衍射通道

Task035b 在 `p6/h10` 高阶参考上，以功率阈值 `1e-8` 冻结了 12 个显著通道。后续能够输出完整衍射谱的模型，至少登记以下通道：

- 反射：`R(0,0)`、`R(-1,0)`、`R(-2,0)`、`R(-4,0)`、`R(-5,0)`、`R(-7,0)`；
- 透射：`T(0,0)`、`T(-1,0)`、`T(-2,0)`、`T(-4,0)`、`T(-5,0)`、`T(-7,0)`；
- 有复振幅时，再登记对应的 `r(m,0)` 和 `t(m,0)`；
- 其他新出现且超过当前显著性阈值的传播级必须追加，不能为了保持表格固定而省略。

### 0.4 状态枚举

| 状态 | 含义 |
|---|---|
| `success` | 完成正式求解并通过该模型合同规定的残差、物理和资源 Gate。 |
| `success_with_qualifications` | 主要目标通过，但仍有明确适用范围或工程限制。 |
| `controlled_negative` | 正式运行完成，结果可信，但没有达到研究目标；负结果必须保留。 |
| `failed` | 求解、实现或正式 Gate 失败，不能作为物理结果。 |
| `not_run` | 没有运行，通常由资源、能力或前置 Gate 阻止。 |
| `incomplete` | 已完成部分能力或组件测试，但尚无完整正式模型。 |

---

# 1. 已成功或已形成正式数值证据的模型

## 1.1 COMSOL 收敛与求解器参考

### 1.1.1 COMSOL 直接法

该模型使用自由四面体网格和默认二阶 curl-conforming Nédélec 电场单元。这里的 R/T 只包含零级，因为周期端口没有启用非零衍射级。

| 配置 | 软件/方法 | 网格 / 单元 | FE DoF | R00=Rtotal | T00=Ttotal | Atotal | 线性残差 | 峰值内存 | 求解器阶段 | 总时间 | 状态 | 证据 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `C-COMSOL-P0` | COMSOL 6.4；MUMPS direct | 182,393 tetra；`h=2.5 nm`；二阶 Nédélec | 1,178,238 | `8.2296654875e-4` | `0.6167277217` | `0.3824493118` | `6.3e-12` | `22.989 GB` | `269 s` | `282 s` | `success`，零级直接参考 | `docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md` |

**衍射级登记边界：**该 COMSOL 模型只保存 `(0,0)` 零级；`R/T(-1,-2,-4,-5,-7,0)` 和复振幅均没有计算，不能填入 0。

### 1.1.2 COMSOL 成功迭代法

| 案例 | 外层方法 / 预条件器 | R00=Rtotal | T00=Ttotal | Atotal | 相对直接法 `|Δ(R+T)|` | 峰值内存 | 迭代数 | 总时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `gmres_gmg_default` | 右 GMRES；restart 300；GMG；GCRO-DR on | `8.2297e-4` | `0.61672815` | `0.38244946` | `4.31e-7` | `13.376 GB` | 历史表未单列 | `232 s` | `success` |
| `gmres_gmg_restart100` | 右 GMRES；restart 100；GMG | `8.2297e-4` | `0.61672773` | `0.38244928` | `1.95e-8` | `11.699 GB` | `544` | `417 s` | `success`；推荐折中方案 |
| `gmres_gmg_restart50` | 右 GMRES；restart 50；GMG | `8.2297e-4` | `0.61672769` | `0.38244930` | `3.20e-8` | `10.547 GB` | 历史表未单列 | `750 s` | `success`；更省内存但更慢 |
| `gmres_gmg_left` | 左 GMRES；restart 300；GMG | `8.2203e-4` | `0.61673963` | `0.38245066` | `1.10e-5` | `11.994 GB` | 历史表未单列 | `152 s` | `success_with_qualifications`；最快但误差较大 |
| `fgmres_gmg_default` | 右 FGMRES；restart 300；GMG | `8.2297e-4` | `0.61672815` | `0.38244946` | `4.31e-7` | `18.290 GB` | 历史表未单列 | `236 s` | `success`；内存未优于 GMRES |
| `tfqmr_gmg_default` | 右 TFQMR；GMG | `8.2296e-4` | `0.61672783` | `0.38244933` | `1.06e-7` | `8.992 GB` | `1241` | `869 s` | `success`；筛选中最低内存 |
| `tfqmr_gmg_saved` | 右 TFQMR；保存模型复跑 | `8.2297e-4` | `0.61672768` | `0.38244931` | `3.72e-8` | `9.010 GB` | `1142` | `800 s` | `success` |
| `gmres_pc_directpre` | GMRES + DirectPreconditioner | `8.2297e-4` | `0.61672772` | `0.38244931` | `1.19e-13` | `23.110 GB` | 历史表未单列 | `337 s` | `success`，但本质仍依赖直接分解 |

**衍射级登记边界：**这些迭代结果与 COMSOL direct 使用同一个仅零级模型，所以非零衍射级和复振幅没有历史数据。

---

## 1.2 FEniCS 原始完整 FE 矩阵法：直接求解

这里的“原始完整矩阵法”指：由 UFL/FFCx/DOLFINx 组装包含全部边、面和 cell-interior 自由度的全局 FE 矩阵，再施加 Floquet 和 DtN；没有做 Task035b 的 cell-interior 静态凝聚。

### 1.2.1 Full 3D

| Task / 模型 | 配置 | 网格 / 阶次 | FE DoF | 求解 rows | matrix NNZ | factor NNZ | Rtotal | Ttotal | Avolume | true residual | 峰值内存 | 主要时间 | 状态 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Task032 full3D h5 | `F-STAGE4-S` | hexa；p2；h5 | 44,698 | 44,778 | 4,896,156 | 历史主表未保存 | `0.0890216029` | `0.4425882787` | `0.4683901184` | `9.7340e-12` | Task029 MPI4 baseline `2328.145 MiB` | Stage4 固定四核记录约 `18.311 s` | `success`；同网格 Hybrid 基线 |
| Task032 full3D h3 | `F-STAGE4-S` | hexa；p2；h3 | 198,438 | 198,518 | 21,317,860 | `266,127,836`（Task029 h3） | `0.0046130314` | `0.5836533572` | `0.4117336114` | `9.9234e-12` | Task029 MPI4 baseline `8651.098 MiB` | 历史总时间口径未统一 | `success`；同网格 Hybrid 基线 |
| Task033 full3D p3/h5 | `F-STAGE4-S` | hexa；p3；h5 | 145,863 | 145,943 | 35,566,727 | 历史未记录 | `0.001090107012` | `0.600622478293` | `0.398287414695` | `5.442e-12` | `7.781 GiB` | `103.59 s` | `success`；p3 same-degree closure |
| Task033 full3D p3/h7.5 | `F-STAGE4-S` | hexa；p3；h7.5 | 63,747 | 63,827 | 历史未记录 | 历史未记录 | `0.003090727450` | `0.591160863329` | `0.405748409221` | `6.449e-12` | `3.667 GiB` | `44.487 s` | `success_with_qualifications`；等精度压缩成功 |

**衍射级数据状态：**Task032 的总结早于 Task035b 12 通道 reference v1，缺失项统一为“历史未记录”。Task033 的逐级功率与幅值保存在 Case091 record 中，Task035b 的 fixed reference band 不能追溯性改写当时 Gate。

### 1.2.2 Hybrid FEM–Modal

Hybrid 把上下短 3D FEM 区保留为完整 FE 矩阵，中间长区域改用二维本征模态传播，因此行数和 NNZ 明显减少。该方法仍属于“原始完整 FE 局部矩阵”，因为上下 FEM 区尚未使用 cell-interior 静态凝聚。

| Task / 模型 | 配置 | local 3D FE DoF | 外部 DtN | 内部模态 `2M` | total rows | matrix NNZ | Rtotal | Ttotal | Avolume | true residual | 峰值内存 / 时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Task032 Hybrid h5 M160 | `F-STAGE4-S` | 6,826 bottom + 6,826 top | 80 | 320 | 14,052 | 2,000,624 | `0.0890210691` | `0.4425867427` | `0.4683921882` | `2.5455e-12` | 见 Case080 M160 record | `success`；相对 full3D 最大 R/T/A 差 `2.07e-6` |
| Task032 Hybrid h3 M160 | `F-STAGE4-S` | 34,198 bottom + 34,198 top | 80 | 320 | 68,796 | 8,594,673 | `0.0046128199` | `0.5836509402` | `0.4117362399` | `2.6036e-12` | 见 Case080 M160 record | `success`；相对 full3D 最大差 `2.63e-6` |
| Task033 Hybrid p3/h5 M160 | `F-STAGE4-S` | 21,847 bottom + 21,847 top | 80 | 320 | 44,094 | 10,313,006（两 local blocks） | `0.001090095685` | `0.600622368221` | `0.398287536096` | `2.343e-12` | `2.618 GiB`；`111.94 s` | `success`；16 项 Gate 通过 |
| Task033 Hybrid p3/h7.5 M160 | `F-STAGE4-S` | 13,299 bottom + 13,299 top | 80 | 320 | 26,998 | 历史主表仅保存 factor inventory 17,057,414 | `0.003090647382` | `0.591159679406` | `0.405749673156` | 历史 summary 未单列 | `2.008 GiB`；`74.908 s` | `success_with_qualifications`；固定 p 等精度压缩成功 |

---

## 1.3 FEniCS 原始完整 FE 矩阵法：迭代求解

这些模型不做 cell-interior 静态凝聚。外层真实算子使用完整 FE 矩阵 `F`，并以 auxiliary-free DtN Schur `F-C H^{-1}D` 处理 80 个端口辅助量。这里的“凝聚”只针对小型 DtN 辅助块，不是 Task035b 的单元内部自由度凝聚。

### 1.3.1 Full 3D

#### Task027：固定 75D 粗空间 + physical z-slab Schwarz

| h (nm) | FE DoF | F NNZ | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | solve / total | 峰值 RSS | 状态 |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | 4,840,396 | 右 FGMRES100；16 slab；ILU1；两步 shifted-F 平滑；75D coarse | 1,201 | `9.8395e-7` | `0.0890216032` | `0.4425882752` | `0.4683901190` | `91.10 / 110.91 s` | `1.957 GB` | `success` |
| 3 | 198,438 | 21,167,444 | 同一算法规则 | 993 | `9.9326e-7` | `0.0046130324` | `0.5836533646` | `0.4117336036` | `317.85 / 361.74 s` | `5.070 GB` | `success` |
| 2 | 615,108 | 65,122,664 | 同一算法规则 | 1,804 | `9.9974e-7` | `0.0013429363` | `0.5992132418` | `0.3994438284` | `2179.96 / 2328.13 s` | `12.958 GB` | `success_with_qualifications`；内存通过、物理尚未跨网格收敛 |

#### Task030：compact physical-slab low-memory profile

| h (nm) | FE DoF | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | 峰值 RSS | 相对 Task027 内存 | 状态 |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | FGMRES90；ILU0 对称 pre/post；local shift；factor-only；75D coarse | 855 | `9.924905e-7` | `0.0890216035` | `0.4425882732` | `0.4683901222` | `1.687653 GB` | `-15.24%` | `success` |
| 3 | 198,438 | 同一算法规则 | 962 | `9.903890e-7` | `0.00461303218` | `0.58365335775` | `0.41173361173` | `3.792912 GB` | `-25.37%` | `success` |
| 2 | 615,108 | 同一算法规则 | 1,873 | `9.972228e-7` | `0.00134293442` | `0.59921323601` | `0.39944383222` | `9.374729 GB` | `-28.33%` | `success_with_qualifications`；慢但低内存 |

#### Task031：assembled-F-free、overlap 0.125 与 compact lifecycle

| h (nm) | FE DoF | 外层方法 | iterations | full true residual | Rtotal | Ttotal | Avolume | solve / total | simultaneous peak | 状态 |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 44,698 | Task030 PC + public matrix-free form action + overlap0.125 + compact lifecycle | 1,157 | `9.959903e-7` | `0.089021602568` | `0.442588275323` | `0.468390124569` | `350.851 / 374.342 s` | `1.619598 GiB` | `success_with_qualifications` |
| 3 | 198,438 | 同一算法规则 | 1,994 | `9.973853e-7` | `0.004613031629` | `0.583653357934` | `0.411733610310` | `2311.581 / 2370.351 s` | `3.474346 GiB` | `success_with_qualifications` |
| 2 | 615,108 | 同一算法规则 | 1,977 | `9.998454e-7` | `0.001342934186` | `0.599213235569` | `0.399443835926` | `11982.581 / 12173.086 s` | `7.897675 GiB` | `success_with_qualifications`；强内存成功但约 3.33 h |

**显著衍射级状态：**Task027–031 的正式总结以 total R/T/A 和 80 模态身份为主，未在 summary 中保存 Task035b 的 12 通道表；后续需要从 heavy records 自动回填各级功率和复振幅。

### 1.3.2 Hybrid

当前没有“原始完整 FE 局部矩阵 + Hybrid + 正式迭代求解器”的成功资格化模型。

| 模型 | 当前状态 | 说明 |
|---|---|---|
| Hybrid iterative | `not_run / not_qualified` | Task032–033 的 Hybrid 主线采用直接法；迭代 Hybrid 需要独立接口/模态块预条件和完整通道闭合。 |

---

## 1.4 静态凝聚法：直接求解

静态凝聚先在每个高阶单元内部消去只属于本单元的 cell-interior 自由度，只把 edge/face trace 送入全局矩阵；求解后再逐单元恢复完整场。它不是近似删自由度，而是精确块消元。Task035b 当前正式实现只资格化规则、轴对齐、仿射六面体。

### 1.4.1 Full 3D：总量、矩阵与资源

| 模型 | 网格 / 空间 | Full3D-equivalent DoF | active rows incl. DtN | matrix NNZ | factor NNZ | R00 | Rtotal | Ttotal | Aclosure | true residual | 峰值 / 主要时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| p4/h10 global | `(6,3,14)`；global p4 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | `0.001872161` | `0.001882317` | `0.596619520` | `0.401498163` | `2.35e-11` | build `35.64 s`；MUMPS setup `13.36 s` | `success`，但未达高阶收敛 |
| p5/h10 global | `(6,3,14)`；global p5 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | `0.000785714` | `0.000794886` | `0.602483954` | `0.396721160` | `1.25e-11` | build/setup/solve `24.72/36.48/0.077 s` | `success`，接近 p6 |
| p6/h10 global reference | `(6,3,14)`；global p6 | 173,802 | 51,272 | 41,989,040 | 202,441,352 | `0.000753761` | `0.000762881` | `0.602701634` | `0.396535485` | `1.26e-11` | build/setup/solve `102.32/102.54/0.167 s`；隔离 direct peak `15.964 GiB` | `success`；best available same-code discrete reference |
| global p6/h15 | 粗化网格；global p6 | 84,492 | 24,704 | 19,207,136 | 59,616,320 | 见 record | 见 record | 见 record | 见 record | `7.87e-12` | pair peak `12.000 GiB`；build/setup/solve `396.93/21.53/0.057 s` | `controlled_negative`；弱通道不满足 |
| fixed p5-trace/p6-interior h15 | `(6,2,10)` | 74,890 | 16,880 | 9,195,812 | 27,916,600 | `0.000755888314` | `0.000765024318` | `0.602685146796` | `0.396549828886` | `8.83e-12` | canonical direct MPI8 peak `5.803 GiB`；cold/warm non-KSP `19.242/6.141 s` | `controlled_negative`；总量通过、通道失败 |
| fixed p5-trace/p6-interior h14 | `(6,2,11)` | 82,315 | 18,500 | 10,104,512 | 31,347,000 | 见 record | 见 record | 见 record | 见 record | `4.45e-12` | `6.376 GiB`；build/setup/solve `62.312/11.474/0.0315 s` | `controlled_negative`；z 方向正信号但不完整 |
| fixed p5-trace/p6-interior h13 | `(6,2,12)` | 89,740 | 20,120 | 11,013,212 | 36,273,200 | `0.000756117570` | `0.000765246512` | `0.602682451672` | `0.396552301816` | `5.81e-12` | accuracy peak `6.411 GiB`；canonical setup peak约 `5.03 GiB`；cold/warm non-KSP `19.410/6.696 s` | `controlled_negative`；当前预算内最强点 |

### 1.4.1.1 12 个显著通道功率

#### 反射功率

| 模型 | R(0,0) | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | Rtotal |
|---|---:|---:|---:|---:|---:|---:|---:|
| p6/h10 reference v1 | `7.53761220068e-4` | `6.66930965425e-6` | `1.47769085130e-6` | `2.67523960967e-7` | `7.45730053677e-8` | `6.26354242222e-7` | `7.62881475133e-4` |
| fixed h15 | `7.55888313624e-4` | `6.68359026100e-6` | `1.48261801533e-6` | `2.60181249500e-7` | `7.78127363894e-8` | `6.27007582029e-7` | `7.65024318140e-4` |
| fixed h13 | `7.56117570116e-4` | `6.67510914774e-6` | `1.47657836307e-6` | `2.72339140129e-7` | `7.35017831938e-8` | `6.26378308638e-7` | `7.65246511550e-4` |

#### 透射功率

| 模型 | T(0,0) | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | Ttotal | Aclosure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p6/h10 reference v1 | `6.02673872347e-1` | `2.17816739855e-5` | `2.95984139513e-6` | `4.37288897207e-7` | `2.11920825720e-7` | `2.36201044924e-6` | `6.02701633986e-1` | `3.96535484539e-1` |
| fixed h15 | `6.02657398112e-1` | `2.18040789857e-5` | `2.94463911877e-6` | `4.12666159013e-7` | `2.15875293566e-7` | `2.36220894231e-6` | `6.02685146796e-1` | `3.96549828886e-1` |
| fixed h13 | `6.02654698626e-1` | `2.17753807955e-5` | `2.95868518886e-6` | `4.35489199428e-7` | `2.12204228069e-7` | `2.36225288824e-6` | `6.02682451672e-1` | `3.96552301816e-1` |

### 1.4.1.2 显著通道复振幅

#### 反射复振幅 `r(m,0)`

| 模型 | r(0,0) | r(-1,0) | r(-2,0) | r(-4,0) | r(-5,0) | r(-7,0) |
|---|---|---|---|---|---|---|
| p6/h10 reference v1 | `-2.52523043536e-2 +1.07741517021e-2i` | `-1.03270771592e-3 +7.67833921753e-4i` | `4.94231617062e-4 -2.05515769764e-4i` | `2.10223336125e-4 -4.97304361281e-5i` | `-9.81780791859e-5 -6.53550324587e-5i` | `-5.05209111247e-4 -2.60888617007e-5i` |
| fixed h15 | `-2.52679489973e-2 +1.08360078947e-2i` | `-1.03216329353e-3 +7.70869059128e-4i` | `4.94645323058e-4 -2.06840346497e-4i` | `2.06054361758e-4 -5.41082464827e-5i` | `-1.00138975344e-4 -6.69829310030e-5i` | `-5.05459008402e-4 -2.63630100680e-5i` |
| fixed h13 | `-2.52711749561e-2 +1.08390629878e-2i` | `-1.03272204657e-3 +7.68751847368e-4i` | `4.93434424824e-4 -2.06901901623e-4i` | `2.12784701368e-4 -4.72186363878e-5i` | `-1.00926387945e-4 -5.93655036535e-5i` | `-5.05224210350e-4 -2.59847102187e-5i` |

#### 透射复振幅 `t(m,0)`

| 模型 | t(0,0) | t(-1,0) | t(-2,0) | t(-4,0) | t(-5,0) | t(-7,0) |
|---|---|---|---|---|---|---|
| p6/h10 reference v1 | `6.31378703348e-1 +4.73020981038e-1i` | `2.09101338530e-3 -1.02337986284e-3i` | `-6.97002780558e-4 +2.97942080721e-4i` | `-2.62132207531e-4 +8.74322690375e-5i` | `1.34032696607e-4 +1.47005784286e-4i` | `9.81221050834e-4 -8.72374996020e-5i` |
| fixed h15 | `6.31685464148e-1 +4.72593246678e-1i` | `2.09051124045e-3 -1.02712258858e-3i` | `-6.91980021337e-4 +3.04622473840e-4i` | `-2.49901308066e-4 +9.80178800675e-5i` | `1.39598241988e-4 +1.44313125131e-4i` | `9.81176181394e-4 -8.82042041001e-5i` |
| fixed h13 | `6.31731380082e-1 +4.72528917690e-1i` | `2.09015756157e-3 -1.02436264988e-3i` | `-6.96291673953e-4 +2.99225357519e-4i` | `-2.61125984121e-4 +8.86378025759e-5i` | `1.34725687090e-4 +1.46551622295e-4i` | `9.81167544398e-4 -8.84024041667e-5i` |

### 1.4.1.3 未通过项必须写具体数值

| 模型 | 未通过的功率 | 未通过的复振幅 | 结论 |
|---|---|---|---|
| fixed h15 | `R(-2)=1.482618e-6`、`R(-4)=2.601812e-7`、`R(-5)=7.781274e-8`、`T(-2)=2.944639e-6`、`T(-4)=4.126662e-7`、`T(-5)=2.158753e-7` 未落入 reference v1 band | `r(-4)`、`r(-5)`、`t(-2)`、`t(-4)`、`t(-5)` 未通过 | `controlled_negative`；总 R/T/A 接近参考不代表弱通道收敛 |
| fixed h13 | `T(-4)=4.354892e-7` 与 `R(-4)=2.723391e-7` 未通过 | `r(-4)=2.127847e-4-4.721864e-5i`、`r(-5)=-1.009264e-4-5.936550e-5i` 未通过 | `controlled_negative`；当前 `<=90k` 最强点仍非同误差候选 |

### 1.4.2 Hybrid

Review V3 已把 cell-interior 静态凝聚接入 Task032/033 Hybrid 的上下局部
三维 FEM 端区。static 路径与原始 Hybrid 路径达到逐通道等价，但 p2/h5
static Hybrid 没有与同离散 static Full3D 完成显著通道闭合。因此当前有
正式实测的工程能力和 controlled negative，没有 Hybrid 物理成功模型。

| 模型 | local FE / trace / total rows | matrix / factor NNZ | R00 / R / T / Aclosure | residual / fields | peak / total | 状态 |
|---|---:|---:|---|---|---:|---|
| p2/h5 static Hybrid M120 | 6,826 full FE/side；4,800 active trace/side；9,920 total | 976,400 / 5,968,912 pair | `0.089011819673 / 0.089021069106 / 0.442586742743 / 0.468392188151` | `3.18e-12`；full/interior residual pass | 2.747 GiB / 114.21 s | `controlled_negative`；static-equivalence 12/12+12/12，Full3D closure 3/12+2/12 |
| p2/h5 static Hybrid M160 | 6,826 full FE/side；4,800 active trace/side；10,000 total | 976,400 / 5,986,184 pair | `0.089011819673 / 0.089021069106 / 0.442586742743 / 0.468392188151` | `3.45e-12`；interface E/H 与 middle plane pass | 3.308 GiB / 186.36 s | `controlled_negative`；M120→M160 12/12+12/12，但 Full3D closure 3/12+2/12 |

M160 的相对 `1e-3` 失败功率为
`T(-5,0)=1.667074e-7`、`T(-4,0)=3.172633e-7`、
`T(-2,0)=4.723171e-7`、`T(-1,0)=5.146400e-6`、
`R(-7,0)=2.232991e-6`、`R(-5,0)=1.984830e-7`、
`R(-4,0)=9.446546e-8`、`R(-2,0)=7.121444e-8`、
`R(-1,0)=6.647511e-6`；复振幅还在 `T(-7,0)` 失败。对应 Full3D
值、复振幅、绝对差和冻结限值见
`benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json`。
H1-B p2/h3 为 `not_run_by_review_prerequisite`，不是普通待运行项。

---

## 1.5 静态凝聚法：迭代求解（待定）

当前没有成功模型。三条 Task035b MPI8 screen 均达到 200 步上限且残差几乎不下降，因此只能登记为探索负结果，详见第 2.9 节。

### 1.5.1 Full 3D

| 状态 | 说明 |
|---|---|
| `no_successful_model_yet` | 需要实质不同的 H(curl) 辅助空间、谱、block-Schur 或 Fourier/DtN harmonic 预条件器；简单 Jacobi、ASM/ILU 和 z-slab/DtN coarse 已被正式负结果关闭。 |

### 1.5.2 Hybrid

| 状态 | 说明 |
|---|---|
| `not_run` | 需先有合格的静态凝聚 Full3D 候选和可收敛的 condensed-trace 预条件器。 |

---

## 1.6 自适应求解

### 1.6.1 Full 3D

当前没有达到 production qualification 的完整自动 h/p 自适应模型。

| 路线 | 已完成内容 | 未完成内容 | 状态 |
|---|---|---|---|
| Task035 tetra local-h | 真实 DWR、周期闭合、一次局部 h 细化和固定细化网格 p6 对照 | 同一 patch 上 h/p 公平竞争、`<=90k` 最终候选 | `research evidence / incomplete` |
| Task035b structured-hexa directional-h | h15→h14→h13 的 z 向全共形细化，h13 达到 89,740 DoF | 12/12 通道闭合；局部 hanging-node hexa h 路径 | `controlled_negative` |
| selective p6 trace | fixture 中 active-row 省略、Floquet pullback、MatShell action | actual enriched residual、channel DWR、orbit selection、正式 PDE | `incomplete` |

### 1.6.2 Hybrid

| 状态 | 说明 |
|---|---|
| `not_run / incomplete` | 只有 Full3D 自适应候选通过完整通道和资源 Gate 后，才可研究 Hybrid 局部 h/p 与 M 联合自适应。 |

---

# 3. Task000–Task035d 逐任务统一总账

> 本节编号固定为 `3.1 Task000` 至 `3.39 Task035d`。每个 Task 先用通俗语言回答“研究什么、为什么研究、改变了哪段流程、最终结论是什么”，再用同一表头登记身份、物理、离散、算法、规模、总量、逐级结果、资源和处置。历史没有保存的字段统一写“历史未记录”，不填 0、不由功率反推复振幅。早期 `linear_system_relative_residual` 明确标成 legacy explicit residual，不冒充 Task035b/035c/035d 的 full explicit true residual。

统一表头如下，后续 checker 会检查每个 Task 都存在这一表头：

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `schema_only` | source SHA、record/hash | 几何、材料、波长、入射、cell、p/h | Full3D/Hybrid、direct/iterative、DoF/rows/NNZ | R00/R/T/A/residual、12 通道/幅值、时间/内存 | 实际未通过值与状态 | tracked path |

## 3.1 Task000

研究对象是仓库结构和任务留痕流程，目的不是求解 PDE，而是建立 `task → outcomes → review` 闭环。它改变了协作、审查和轻量证据入库方式；最终形成可追溯工作流，但没有物理 benchmark。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task000_review_code_workflow` | branch=`codex/review_code`；精确 source SHA 历史未记录 | 无物理模型；离散不适用 | 无 PDE；DoF/rows/NNZ 不适用 | R/T/A、残差、逐级、时间和内存均 `not_run` | `documentation_success`；早期代码判断被 Task001–004 取代 | `docs/task000_review_code/outcomes/summary.md` |

## 3.2 Task001

研究对象是早期 Stage4 flat-layer 与 zero-contrast 小模型，目的是固定 13.5 nm 和 Si 复折射率入口并区分 sanity 与 benchmark。流程加入 `numerical_sanity_only`、材料标签和功率来源说明；两个极粗网格模型一致，只能算工程 smoke。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `Stage4A_flat_layer` | source SHA/geometry hash 历史未记录 | 13.5 nm normal-s；Si substrate；p1 h50 hexa，12 cells | 原始 Full3D direct；75 FE DoF | R/T/A=`0.999843746435/0.000132382785/2.387078e-5`；只启用零级，复振幅历史未记录；8.981 s，281.125 MB | `engineering_success; numerical_sanity_only` | `docs/task001_stage4_validation_cleanup/outcomes/summary.md` |
| `Stage4B_zero_contrast` | 同一历史数据族 | block tag 保留但 `n_grating=1+0j`；27 cells | 原始 Full3D direct；144 FE DoF | 与 flat-layer 同一 R/T/A；8.537 s，280.5 MB；residual 历史未记录 | `engineering_success; numerical_sanity_only` | `docs/task001_stage4_validation_cleanup/outcomes/metrics.csv` |

## 3.3 Task002

研究对象是 flat-layer、zero-contrast 与 real-Si block 的 R/T/A、probe、net-flux 和体吸收接口。目的是建立多口径一致性 Gate；九个模型全部暴露错误归一化/参考面，物理数值不可用，但成功定位了问题并推动 Task003/007 修正 official 口径。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `flat_layer_h5` | source SHA 历史未记录；Task002 raw summary | 13.5 nm normal-s；p1 h5 hexa；尺寸历史表见 evidence | Full3D direct | port R/T/A=`0.0184287/1.0440977/-0.0625264`，Avolume=`0.0291011`，closure mismatch=`0.0916275`；逐级/幅值历史未记录 | `diagnostic_success; physical_gate_failed`；R/T 口径被 Task003/007 取代 | `docs/task002_rta_output_volume_absorption/outcomes/summary.md` |
| `real_si_block_h3` | 同一数据族 | Si substrate+block；62,475 cells，197,136 DoF | Full3D direct | R/T/Aport=`0.00188633/1.09051232/-0.0923987`，Avolume=`0.0430043`，mismatch=`0.135403`；2623 s，13,213 MB | `diagnostic_success; physical_gate_failed`；失败值不得作参考 | `docs/task002_rta_output_volume_absorption/outcomes/metrics.csv` |

## 3.4 Task003

研究对象是 lossy flat layer 的解析闭合和 10 nm 小单元收敛，目的是修复 Task002 的吸收归一化、透射参考面和 DtN traction 符号。流程确立 DtN port R/T 与 Avolume 主口径，probe/net-flux 降为诊断；小单元机器精度闭合，但不是目标光栅基准。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `flat_layer_auto_h5` | source SHA 历史未记录 | 100×100×150 nm；13.5 nm normal-s；p1 h5 hexa | Full3D direct；39,270 FE + 708 modal rows | R/T/A=`0.0216956/0.918733/0.0595716`，closure `-5.1e-14`，legacy residual `9.26e-11`；12 通道/幅值历史未记录 | `engineering_success; not_converged_reference`；仍约2.17%伪反射 | `docs/task003_stage4_power_consistency/outcomes/summary.md` |
| `small_cell_h1` | 同一算法版本 | 10×10×10 nm；p1 h1；1000 cells | Full3D direct；3630 FE + 4 modal rows | R/T/A=`6.61569e-5/0.99167204/0.00826180`，closure `-2.22e-15`，legacy residual `6.61e-14`；19.9 s | `engineering_success`；仅零级传播 | `docs/task003_stage4_power_consistency/outcomes/small_cell_metrics.csv` |

## 3.5 Task004

研究对象是 10 nm flat-layer 的 p1/p2 收敛、MPI1/4/8 一致性和 Stage1–4 smoke。目的是冻结小规模回归基线；流程加入统一 residual、MPI delta 和阶段 smoke，最终成为长期基础设施，但不代表目标光栅收敛。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `conv_p2_h1p5` | source SHA 历史未记录 | 13.5 nm normal-s；10 nm flat layer；p2 h1.5 hexa | Full3D direct；10,740 DoF | R/T/A=`1.240889e-6/0.991537318/0.008461442`；legacy residual `2.997e-13`；21.60 s，548.5 MB；仅零级 | `production_success`（回归基线） | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/metrics.csv` |
| `mpi_p1_h1p5_and_p2_h3` | 同一 tracked metrics | 同一小单元 | MPI1/4/8 direct | official R/T/A delta `<1e-8`，closure `<1e-10`；PSS/cgroup 历史未记录 | `infrastructure_success` | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/mpi_consistency.csv` |
| `stage1_to_stage4_smoke` | regression metrics | 极粗阶段模型 | serial/MPI staged smoke | 全路径通过；Stage2B/2C 不是精度 benchmark | `infrastructure_success` | `docs/task004_small_cell_p_convergence_mpi_regression/outcomes/regression_metrics.csv` |

## 3.6 Task005

研究对象是 100×100×150 nm、50×50×50 nm Si block 的 p2 full-matrix direct/OOC 资源边界，目的是区分矩阵存储与 LU fill。流程新增 assemble-only、default direct、OOC 和失败边界；h5 可完成，h4 在 factorization 失败。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `assemble_p2_h2` | source SHA 历史未记录 | 13.5 nm normal-s；规则 hexa p2；195,075 cells | MPI8 Full3D assemble-only；4,764,870 rows，523,627,904 NNZ | 无 official R/T/A；AIJ估计11.74 GiB | `diagnostic_success`；direct/OOC RAM 仅预测，未实测 | `docs/task005_stage4_real_grating_memory_estimation/outcomes/assemble_matrix_scale.csv` |
| `direct_p2_h5` | Task005 record family | 同一模型；p2 h5 | MPI8 MUMPS；301,648 rows | legacy residual `8.90e-12`；R/T/A=`0.00019604/0.90542068/0.09438328`；RSS upper 18.67 GiB，698.63 s；逐级历史未记录 | `diagnostic_success`；非最终 benchmark | `docs/task005_stage4_real_grating_memory_estimation/outcomes/direct_default_scale.csv` |
| `direct_or_ooc_p2_h4` | failure boundary | p2 h4 | direct / OOC | direct factor stage signal 9；OOC `INFOG(1)=-90`，调参90 min超时且 scratch约30.09 GiB | `controlled_negative`；fill-in主导 | `docs/task005_stage4_real_grating_memory_estimation/outcomes/failure_boundary.md` |

## 3.7 Task006

研究对象是同一 100 nm-period block 的 70 nm reduced-height 资源模型，目的是检验缩短端口距离并测真实 process-tree memory。流程加入独立采样、MPI1/8 与 tuned OOC；资源诊断成功，但物理量不能代替 150 nm 模型。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `reduced70_p2_h5_np8_direct` | source SHA 历史未记录 | 70 nm reduced-height；p2 h5；5,600 hexa cells | Full3D direct；142,188 FE，142,896 rows，18,803,220 NNZ | R/T/A=`0.000707967/0.964603346/0.034688687`；legacy residual `1.21e-12`；process-tree peak 13.646 GiB，119.94 s | `diagnostic_success` | `docs/task006_reduced_height_grating_convergence_memory/outcomes/memory_profile_summary.csv` |
| `reduced70_p2_h3_ooc` | failure record | p2 h3；759,698 rows，91,259,656 NNZ | MUMPS OOC | `INFOG(1)=-90`，无 official R/T/A | `controlled_negative` | `docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md` |
| `reduced_vs_original` | comparison CSV | 70 vs 150 nm domain | direct comparison | R `0.000708 vs 0.000196`，T `0.964603 vs 0.905421`，A `0.034689 vs 0.094383` | `negative_result_success`；证明 reduced-height 非物理替代 | `docs/task006_reduced_height_grating_convergence_memory/outcomes/reduced_vs_original_domain_comparison.csv` |

## 3.8 Task007

研究对象是 100 nm-period Si block 在 70/110/130/150 nm 域高下的 official DtN modal R/T，目的是替换不可靠 probe 并量化端口参考面影响。流程正式冻结 modal amplitudes + Avolume；能量闭合通过，但域高依赖说明这些不是 continuum 解。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `height70_p2_h5_np8` | source SHA 历史未记录 | 13.5 nm normal-s；p2 h5；5,600 cells | Full3D direct；142,188 FE + 708 aux | R/T/A=`0.0007079669/0.9646033456/0.0346886875`；closure `7.55e-15`；legacy residual `1.84e-12`；89.70 s，max-rank RSS 2.207 GB | `production_success`（当时口径） | `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_official_rta.csv` |
| `height150_p2_h5_np8` | 同一数据族 | 12,000 cells | Full3D direct；300,940 FE，301,648 rows，35.634M NNZ | R/T/A=`0.0001960416/0.9054206822/0.0943832762`；closure `-3.08e-14`；617.12 s，max-rank RSS 2.620 GB | `success_with_qualifications`；R00/12通道/幅值历史未记录 | `docs/task007_dtn_port_modal_official_rta/outcomes/height_scan_resource.csv` |

## 3.9 Task008

研究对象是实际 `F-STAGE4-S` 固定目标：50×25×140 nm、17×25×120 nm Si block、13.5 nm、80°斜入射 s 偏振。目的是冻结 direct reference；流程加入双 Floquet 相位、p1/p2 h 扫描和内存 Gate，p2/h2 成为 best available discrete reference。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `target_p2_h2_direct_reference` | source SHA/geometry hash 历史未记录；raw summary tracked | `F-STAGE4-S`；hexa p2 h2；24,570 cells | MPI8 MUMPS；615,108 FE，615,188 rows，65,448,472 NNZ | R/T/A=`0.001342932846/0.599213229444/0.399443837710`；closure `-1.066e-14`；legacy residual `1.345e-11`；1665.78 s，RSS upper 20.533 GiB；12通道/幅值历史未记录 | `production_success; best_available_discrete_reference`，非 continuum | `docs/task008_70nm_official_convergence_benchmark/outcomes/raw_runs/direct_p2_p2_h2p0/run_summary.json` |
| `target_p2_h1p5_direct` | failure record | 1,347,314 rows，142.656M NNZ | MPI8 MUMPS | KSP setup signal 9；最后 RSS upper 14.37 GiB；无 official output | `controlled_negative` | `docs/task008_70nm_official_convergence_benchmark/outcomes/failure_boundary.csv` |
| `target_p2_h1_assemble` | failure record | 4,379,752 rows，459.939M base NNZ | assemble-only | base assembly后2400 s超时并大量 swap | `controlled_negative` | `docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md` |

## 3.10 Task009

研究对象是目标系统上的黑盒 PETSc Krylov/PC 组合，目的是找 factor-free 低内存法。流程建立 profile 筛选和“不收敛不输出 official R/T/A”；所有组合失败。最终 review 纠正了一个关键口径：`0.00355849` 是 KSP ratio，true relative residual 是 `0.161741`。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `iter_gmres_jacobi_p2_h1p5` | source SHA 历史未记录；final review 纠偏 | `F-STAGE4-S`；p2 h1.5；1,347,314 rows，142.656M NNZ | MPI8 assembled GMRES/Jacobi，1000步 | terminal KSP ratio `0.00355849`，true relative residual `0.161741`（limit `1e-6`）；solve/total `360.86/551.03 s`，RSS upper 13.992 GiB；无 official R/T/A/通道 | `controlled_negative`；不得再写成 true residual `3.558e-3` | `docs/task009_iterative_solver_profile_screening/outcomes/iterative_failure_cases.csv` |
| `black_box_profile_family` | profile summary | p2 h5/h4 | GMRES/FGMRES/BiCGStab + Jacobi/BJacobi/ASM/ILU/LU/GAMG/FieldSplit | 多数1000步停滞或恶化；无 official output | `negative_result_success`；排除黑盒 lane | `docs/task009_iterative_solver_profile_screening/outcomes/summary.md` |

## 3.11 Task010

研究对象是 MUMPS-BLR 和 shifted/positive Maxwell 原型，目的是检验近似直接法与最小物理 PC。BLR 可控但仍持有 MUMPS factors；shifted lane 失败，不能称低内存 iterative。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `fgmres_mumps_blr_1e-5_p2_h2` | source SHA 历史未记录 | `F-STAGE4-S`；615,188 rows，65.448M NNZ | MPI8 FGMRES + MUMPS-BLR，4 iterations | true residual `2.08534e-8`；R/T/A=`0.001342932839/0.599213228940/0.399443837551`；closure `-6.701e-10`；17.853 GiB，1357.57 s | `engineering_success; explicit_fallback`；不是 factor-free | `docs/task010_shifted_maxwell_preconditioner/outcomes/blr_profile_summary.csv` |
| `blr_p2_h1p5` | failure record | 1.347M rows级 | MUMPS-BLR | setup signal 9，最后RSS upper 13.805 GiB | `controlled_negative` | `docs/task010_shifted_maxwell_preconditioner/outcomes/preconditioner_failure_cases.csv` |
| `shifted_positive_asm_ilu` | profile summary | p2 h5/h4 | assembled FGMRES | 1000步失败；最佳 h4 positive+ASM/LU true residual约`0.1978` | `negative_result_success` | `docs/task010_shifted_maxwell_preconditioner/outcomes/shifted_positive_profile_summary.csv` |

## 3.12 Task011

研究对象是低-restart Krylov、FE-only AMS/HX 和 matrix-free action，目的是分离“低内存但不收敛”“AMS 可行性”和“矩阵存储可消除性”。流程引入 FE-only 正定代理与 matvec 等价 smoke；只得到研究信号，没有完整 Stage4 solver。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `low_memory_gmres40_p2_h4` | source SHA 历史未记录 | `F-STAGE4-S`；p2 h4 | MPI8 assembled Jacobi-GMRES | 1000步 true residual `0.234320`；RSS upper 3.284 GiB；无 official R/T/A | `controlled_negative` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/low_memory_krylov_summary.csv` |
| `real_fe_only_ams_p2_h5` | FE-only tracked CSV | 50×25×140 nm positive Maxwell；p2 h5 | MPI2 AMS；规模细节见 evidence | 7步 residual `4.024e-7`，RSS 6.930 GiB；无 Floquet/DtN/通道 | `research_only_positive` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_summary.csv` |
| `complex_fe_only_ams_p1_h10` | failure record | complex FE-only | hypre AMS setup | `malloc invalid size` + PETSc signal 11 | `failed` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md` |
| `matrix_free_fe_action_p2_h5` | feasibility record | p2 h5 | UFL action vs assembled matvec | relative action error `7.563e-16`，RSS约0.445 GiB；不是 solver residual | `research_only_positive` | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md` |

## 3.13 Task012

研究对象是周期 H(curl) Maxwell 预条件文献，目的是停止盲扫黑盒 PETSc profiles。流程形成 real/imag split AMS/HX、p-coarsened auxiliary、DtN/Floquet coarse 与 matrix-free 路线图；本 Task 没有运行 PDE。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task012_literature_route_registry` | 文献表与 scorecard；source SHA 不适用 | 周期 H(curl) 方法综述；无具体模型 | 无 PDE；DoF/rows/NNZ 不适用 | R/T/A、残差、通道、时间、内存均 `not_run/not_applicable` | `documentation_success`；理论建议需由后续实验限定 | `docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md` |

## 3.14 Task013

研究对象是 FE-only complex Maxwell 的 real-split AMS，目的是绕过 complex hypre AMS 崩溃。流程把复矩阵转成实 2×2 块并比较 H1 auxiliary；same-H1 有 B 档正信号，但没有 Floquet/DtN/R/T/A。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `fe_only_p2_h5_same` | source SHA 历史未记录 | 50×25×140 nm FE-only；hexa p2 h5 | serial FGMRES + same-H1 AMS；37,446 complex DoF，74,892 real rows，14,233,968 NNZ | 310 iterations，true residual `9.964e-7`，RSS 1.323 GiB；R/T/A/12通道不适用 | `research_only_positive`；不可推广为 Stage4 | `docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_summary.csv` |
| `fe_only_p2_h4_same_equivalence` | equivalence CSV | p2 h4 | real split action；82,878 complex / 165,756 real rows | matvec error `1.671e-16`，assembly RSS 1.924 GiB；solve未运行 | `incomplete; equivalence_only` | `docs/task013_real_split_ams_hx_qualification/outcomes/real_split_equivalence.csv` |

## 3.15 Task014a

研究对象是 default100 p1/h5 Stage4 的 real-split FE/aux block PC，目的是把 Task013 信号接入 Floquet MPC + DtN。流程验证 split、索引与 AMS 数据；最小 `FE-AMS + aux identity` 太弱，p2 Gate 关闭。这里的 reduced 不是 cell-interior static condensation。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `tiny10_p1_h5` | source SHA 历史未记录 | tiny10 Stage4；p1 h5 | real-split FGMRES；144 FE+4 aux complex，296 real rows，18,600 NNZ | 37步 true residual `9.601e-7`，RSS 0.261 GiB；问题过小，无权威通道 | `diagnostic_success` | `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_summary.csv` |
| `default100_p1_h5` | tracked CSV | 100×100×150 nm；p1 h5 | FE-AMS+aux identity；39,270 FE+708 aux complex，79,956 real rows，9,390,960 NNZ | 1000步 true residual `0.0214656`，limit `1e-6`，RSS 0.786 GiB；无 official R/T/A | `controlled_negative` | `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/summary.md` |

## 3.16 Task015

研究对象是 Task014a 残差的 FE/aux、port、衍射级和 Schur 分解，目的是定位停滞。流程从强化 FE AMS 转向边界慢模态审计；确认残差集中在 top `(0,0),y` aux mode，但简单 correction 无效。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `default100_boundary_diagnostic` | source SHA 历史未记录 | 同 Task014a default100；79,956 real rows | FE-AMS+aux identity + residual decomposition | true residual `0.0214655595`；FE/aux fraction=`0.04331/0.999062`；top `(0,0),y` 占 aux `0.9999999989`；无 official R/T/A | `diagnostic_success` | `docs/task015_boundary_aware_pc_diagnostic/outcomes/boundary_residual_decomposition.csv` |
| `aux_exact_diag_modal` | combined diagnostic | 同一模型 | aux exact/diag/modal corrections | residual仍约`0.02146556`；Schur-diag反而`0.442726` | `controlled_negative` | `docs/task015_boundary_aware_pc_diagnostic/outcomes/combined_boundary_pc_diagnostic.csv` |

## 3.17 Task016

研究对象是 top/bottom 零级模式的 right-only lifted coarse correction，目的是检验 Task015 dominant mode 能否形成低秩 PC。流程构造1–4维 coarse space；改善只有万分之几，关闭 right-only lane。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `top_y_diag_minres_one_shot` | source SHA 历史未记录 | default100 reduced Stage4 | right basis `[-P_FE^-1 C_j;e_j]` | residual `0.0214655595→0.0214645967`，improvement `1.00004486×`；目标≤0.002或≥10× | `controlled_negative` | `docs/task016_zero_order_lifted_coarse_correction/outcomes/one_shot_coarse_correction.csv` |
| `lifted_ksp` | KSP summary | 同一规模 | additive/residual/minres，300步 | best residual `0.0214656363`，improvement `<1`；无 official R/T/A | `negative_result_success` | `docs/task016_zero_order_lifted_coarse_correction/outcomes/lifted_coarse_ksp_summary.csv` |

## 3.18 Task017

研究对象是 Petrov/adjoint left space 与 true-FE sampled lift，目的是判断 Task016 缺左空间还是 FE lift 不准。Petrov 无效，但 two-mode true-FE one-shot 把残差降约5.8倍，形成研究正信号，KSP 集成仍失败。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `true_fe_sampled_top_bottom_y` | source SHA 历史未记录 | default100 p1/h5 | SciPy GMRES近似解2个 selected FE RHS | residual `0.0214655595→0.00368878394`，5.819×，RSS约1.802 GiB；未达≤0.002或≥10× | `research_only_positive` | `docs/task017_petrov_adjoint_coarse_correction/outcomes/true_fe_sampled_lift_diagnostic.csv` |
| `true_fe_lift_ksp` | KSP summary | 同一系统 | right-preconditioned FGMRES | 300步 residual `0.0235498770`，反而恶化；PETSc AMS RHS另报 error 101 | `controlled_negative / failed` | `docs/task017_petrov_adjoint_coarse_correction/outcomes/petrov_ksp_summary.csv` |

## 3.19 Task018

研究对象是把 Task017 one-shot 变成 residual-corrected solver-like 过程，目的是决定 sampled-Schur lane 是否继续。交替 FE-AMS 段和 selected correction 得到约12.9倍改善，但离 production `1e-6` 仍约1662倍。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `residual_outer_zero` | source SHA/artifact hash 历史未记录；轻量CSV保留 | default100；79,956 real rows，9.391M NNZ | bounded FE-AMS + sampled correction，3 cycles | residual `0.0214588→0.001661623468`，12.914×；limit `1e-6`；RSS upper 1.571 GiB，wall约21.7 min；无 official R/T/A | `research_only_positive; incomplete_for_production` | `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/residual_corrected_loop_summary.csv` |
| `projected_gmres` | prototype record | 同一系统 | projected prototype | residual约`0.00170842`，350.2 s；不是最优 | `research_only_positive_not_best` | `docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/summary.md` |

## 3.20 Task019

研究对象是把 p1 sampled-Schur 信号迁移到目标 p2/h5，目的在于验证可扩展性。流程执行严格同口径比较；改善仅 `1.0018×/1.0804×`，因此关闭低维 sampled-Schur 主线。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_sampled_schur` | source SHA 历史未记录 | `F-STAGE4-S` p2/h5 | sampled response/coarse；规模见 evidence | two comparison ratios `1.0018×/1.0804×`，远低于研究 Gate；无合格 official R/T/A | `negative_result_success`；路线不迁移 | `docs/task019_p2_h5_true_fe_sampled_schur_qualification/outcomes/summary.md` |

## 3.21 Task020

研究对象是 default100 算法沙盒的四条 wave-aware route，目的是在分支卫生约束下快速排序。p1 Route C 达到 `1e-6`，但目标 p2 仅约 `0.0525`，所以只是路线排序，不能作为目标物理结论。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `route_c_p1_and_p2` | branch=`codex/20260709-task20-wave-solver-search`；精确 SHA 历史未记录 | default100 algorithm sandbox；p1/p2 | wave-aware route C | p1 residual达到`1e-6`；p2 residual约`0.0525`；official R/T/A与12通道历史未记录 | `research_only_positive`（p1）/`controlled_negative`（p2） | `docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_progress.csv` |

## 3.22 Task021

研究对象是目标 p2/h5 的 DtN residual selector 与 FE-response Schur，目的是验证边界响应机制。serial SciPy h5 达到 `1e-6`，证明机制，但尚非 MPI 且 h2 未资格化。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_spilu_full_schur` | Task020 research branch；精确 SHA 历史未记录 | `F-STAGE4-S` p2/h5 | serial SciPy SPILU/full Schur | residual达到`1e-6`；资源与12通道历史未记录 | `research_only_positive`；证明机制，不是 production | `docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/summary.md` |

## 3.23 Task022

研究对象是 p2/h2 Schur 资源 preflight，目的是在分解前判定内存。流程把 CSR 装配与 SPILU 估计分开；CSR在6.277 GB内完成，但 SPILU 估计27.79 GB，因此受控阻断，无 field/RTA 回填。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h2_csr_preflight` | Task020 research branch；source SHA 历史未记录 | `F-STAGE4-S` p2/h2 | CSR assemble + serial SPILU estimate | assembly/CSR peak 6.277 GB；SPILU estimated 27.79 GB；R/T/A、residual和通道 `not_run` | `diagnostic_success; controlled_negative`（内存 Gate） | `docs/task022_p2_h2_schur_pc_preflight/outcomes/summary.md` |

## 3.24 Task023

研究对象是 PETSc MPI FE-response PC，目的是把 Task021 serial 机制迁入 MPI 并建立 field/RTA 回填。h5 residual 和 official RTA 闭合，h2 residual约1失败；AMS auxiliary 接口未完成。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p2_h5_petsc_fe_response` | Task020 research branch；source SHA 历史未记录 | `F-STAGE4-S` p2/h5 | PETSc MPI FieldSplit/selected response | h5 residual与 official R/T/A 闭合；精确数值/资源见 evidence；12通道历史未记录 | `infrastructure_success; diagnostic_success` | `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md` |
| `p2_h2_petsc_fe_response` | 同一数据族 | p2/h2 | 同算法 | terminal residual约`1`，limit `1e-6`；无 official output | `controlled_negative` | `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md` |

## 3.25 Task024

研究对象是 p2 h2/h1.5 的低内存 FE-response 工程原型，目的是修复 complex dot、MPI CSR 导出并评估 manual FGMRES。基础设施可复现，但算法收益 Gate 失败，也不是完整80-aux production 解。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `manual_fgmres_fe_response_h2_h1p5` | branch=`codex/20260709-task20-wave-solver-search`；SHA历史未记录 | `F-STAGE4-S` p2 h2/h1.5 | manual FGMRES + MPI CSR export | complex-dot与导出回归通过；算法收益 Gate失败；official totals/12通道不合格 | `infrastructure_success; negative_result_success` | `docs/task024_engineering_iterative_solver_fast_track/outcomes/summary.md` |

## 3.26 Task025

研究对象是参数鲁棒 multilevel H(curl) 与 cached-Q augmented Schur，目的是跨 h5/h2 稳定。h5 有强信号，但 h2 residual `0.1185`，远超 `1e-6`，且 response 质量不足；后由 Task026 exact auxiliary condensation 取代架构。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `cached_q_augmented_schur_h5_h2` | branch=`codex/20260710-task25-parameter-robust-hcurl-pc`；精确 SHA 历史未记录 | `F-STAGE4-S` p2 h5/h2 | cached-Q multilevel H(curl) | h5 strong signal；h2 terminal residual `0.1185`，limit `1e-6`；无合格 official通道 | `research_only_positive / controlled_negative`；被 Task026取代 | `docs/task025_parameter_robust_multilevel_hcurl_pc/outcomes/summary.md` |

## 3.27 Task026

研究对象是 auxiliary-free 3D modal port，目的是精确消去80个 DtN auxiliary 并建立 matrix-free `F-C H^-1D`。h5 达到 `1e-9` 且 h2 action 等价通过，但初始 two-level PC 不鲁棒；精确算子基础进入后续稳定模块。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `auxiliary_free_h5` | branch=`codex/20260711-task26-auxiliary-free-3d-modal-port`；精确 SHA 历史未记录 | `F-STAGE4-S` p2/h5 | exact auxiliary Schur + matrix-free action | full residual达到`1e-9`；official R/T/A闭合；逐级和资源详见 evidence | `production_success; infrastructure_success` | `docs/task026_auxiliary_free_3d_modal_port/outcomes/summary.md` |
| `auxiliary_free_h2_two_level` | 同一数据族 | p2/h2 | initial two-level PC | action/transpose等价通过，但 solver Gate 未过 | `controlled_negative`；PC仍不鲁棒 | `docs/task026_auxiliary_free_3d_modal_port/outcomes/summary.md` |

## 3.28 Task027：mesh-independent physical-slab Schwarz

**探索目的：**在 14 GB 工作站内，用同一 MPI4 迭代算法求解 h5/h3/h2，并使最大/最小迭代数比小于 2。

它改变了迭代主线：以 owner-computes physical slabs、固定75维 coarse 和两步 shifted-F smoothing 替代失败的 spectral/GenEO 假设。三网格残差与资源 Gate 通过，但迭代数不单调，准确结论是 mesh-robust workstation candidate。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task027_h5_h3_h2_sm2` | branch=`codex/20260711-task27-mesh-independent-spectral-schwarz`；精确 SHA 历史未记录 | `F-STAGE4-S` p2 h5/h3/h2 | MPI4 right FGMRES100，16 slabs，ILU1，75D coarse；DoF `44,698/198,438/615,108` | iterations `1201/993/1804`，full residual `9.8395e-7/9.9326e-7/9.9974e-7`；h2 R/T/A=`0.0013429363/0.5992132418/0.3994438284`，RSS 12.958 GB；12通道/幅值历史未记录 | `success_with_qualifications`；spectral/GenEO residual `0.2187–0.2504` 为 controlled negative | `docs/task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| owner-slab + 一步平滑 | h5/h3/h2 迭代数 `2765/1836/3682`；比值 `2.0054` | 只差严格门槛约 10 步；h2 更快但不满足 `<2` | `controlled_negative` |
| owner-slab + 两步全局平滑 | `1201/993/1804`；比值 `1.8167`；h2 RSS `12.958 GB`；h2 R/T/A=`0.0013429363/0.5992132418/0.3994438284` | 同一规则跨三网格通过；物理 R 跨网格仍未收敛 | `success_with_qualifications` |
| spectral / GenEO / interface harmonic coarse | h5 100 步真残差约 `0.2187–0.2504`，远差于固定 75D coarse `6.272e-3` | 谱子空间代数正确，但没有捕获非正规 Floquet-DtN 慢误差 | `controlled_negative` |

## 3.29 Task028：阶段整合、master 迁移与 benchmark 冻结

研究对象是 Task000–027 的生产能力、研究负结果与依赖边界，目的是把历史分支中真正稳定的算子、回归和证据选择性迁入 master。流程建立 progress CSV、依赖分组和 selective-merge 规则；本 Task 主要是整合，不新增物理 PDE。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task000_task027_consolidation` | base/master 与 manifest 身份见 Task028 outcomes；逐历史 SHA 多数未记录 | 汇总 Task000–027 多种模型 | read-only audit + selective integration；无新增 PDE | 冻结 Task007 official RTA、Task026 exact auxiliary Schur、Task027 workstation iterative；本 Task R/T/A/资源 `not_run` | `documentation_success; integration_success`；失败 spectral/sampled-Schur 不进 ordinary API | `docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_summary.md` |

## 3.30 Task029：原始完整矩阵直接法内存剖析

**探索目的：**确定 full3D p2 direct 的内存峰值，并测试 rank、对象生命周期、OOC、BLR、ordering 和线程。

流程把 assembly、MUMPS setup/factor、solve 与生命周期分开采样，证明 h3 峰值来自 LU fill，而非 RHS 或 postprocess；ordinary direct default 保持不变。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task029_h3_mpi4_direct` | Task029 fresh WSL record；source SHA见 outcomes | `F-STAGE4-S` p2/h3 | MPI4 MUMPS；198,518 rows，matrix/factor NNZ `21,317,860/266,127,836` | true residual `1.382e-11`，R/T/A Gate通过；worker RSS 8651.098 MiB；12通道/幅值历史未冻结 | `success`；MPI2只降15.119%、release只降5.462%、BLR residual `4.704e-3` 均为负结果 | `docs/task029_stage4_direct_memory_forensics/outcomes/summary.md` |

| 模型/候选 | rows / NNZ | 数值结果 | 资源/时间 | 最终状态 |
|---|---|---|---|---|
| h5 MPI4 MUMPS baseline | p2 h5；详细 rows 见 Task032 | full solve 与 R/T/A Gate 通过 | worker RSS `2328.145 MiB` | `success`，冻结基线 |
| h3 MPI4 MUMPS baseline | 198,518 rows；matrix/factor NNZ `21,317,860/266,127,836` | true residual `1.382e-11`；R/T/A Gate 通过 | worker RSS `8651.098 MiB`；主峰来自 KSPSetUp LU fill | `success`，诊断基线 |
| h3 MPI2 | 同一物理 | 数值等价 | `7343.137 MiB`，仅下降 `15.119%`，未达 20% | `controlled_negative` |
| release base matrix | 同一物理 | 数值等价 | h3 仅下降 `5.462%` | `controlled_negative`；生命周期非主因 |
| OOC | h5 | 数值通过 | 内存 `-13.744%`，Stage4 时间 `1.539×`，scratch 559.7 MB | `controlled_negative` |
| BLR `1e-5` | h5 | true residual `4.704e-3`；R/T/A 最大偏差 `1.073e-3` | 返回码为 0 但数值错误 | `failed` |
| MPI1×4 threaded | h5 | residual/RTA 通过 | KSPSetUp 仍约 1 核；Stage4 `48.273 s` | `controlled_negative`；当前镜像无线程因子化收益 |
| h2 direct | 预测 `18.882–27.913 GiB` | 未启动 | 超安全 Gate | `not_run` |

## 3.31 Task030：H(curl) 低内存迭代与层级基础设施

**探索目的：**在保持 h5/h3/h2 真残差和 R/T/A 的同时，进一步压低 Task027 的迭代内存。

流程用 symmetric pre/post、ILU0、factor-only、local shift 和 restart90 压缩内存；p/h multilevel coarse 五类试验 residual `0.374864–0.680155` 失败，真正成功来自更紧凑的 physical-slab 配置。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `compact_physical_slab_h5_h3_h2` | Task030 records，source SHA见 outcomes | `F-STAGE4-S` p2 h5/h3/h2 | FGMRES90 + ILU0 symmetric pre/post + 75D coarse | iterations `855/962/1873`，residual `9.924905e-7/9.903890e-7/9.972228e-7`；RSS `1.688/3.793/9.375 GB`；h2 R/T/A=`0.00134293442/0.59921323601/0.39944383222` | `success_with_qualifications`；restart80 与 p/h coarse为 controlled negative | `docs/task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md` |

| 模型/候选 | 结果 | 具体原因 | 最终状态 |
|---|---|---|---|
| p/h multilevel coarse（5 类） | 100 步真残差 `0.374864–0.680155`，比 Task027 基线差 145–264 倍 | 792D p1 coarse 未包含 Maxwell 梯度/近核和掠入射慢误差 | `controlled_negative` |
| symmetric pre/post + ILU0 + factor-only + local shift + restart90 | h5/h3/h2 full pass；内存 `1.688/3.793/9.375 GB`；R/T/A 见第 1.3 节 | 对称平滑是关键；不是 p/h multigrid 成功 | `success_with_qualifications` |
| restart80 | weak-positive Gate 未过 | Krylov 内存继续下降不足以抵消收敛恶化 | `controlled_negative` |

## 3.32 Task031：assembled-F-free 极限内存路线

**探索目的：**不在 Krylov 过程中常驻 assembled `F`，并压缩 overlap 和对象生命周期。

流程改为 public form action、overlap0.125 和 compact lifecycle。它把 h2 simultaneous peak 压到7.898 GiB，但每次 MatMult 重做 form action/通信，h2耗时约3.33小时。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `assembled_F_free_h5_h3_h2` | Task031 records，source SHA见 outcomes | `F-STAGE4-S` p2 h5/h3/h2 | matrix-free form action + Task030 PC | iterations `1157/1994/1977`，residual `9.959903e-7/9.973853e-7/9.998454e-7`；peak `1.620/3.474/7.898 GiB`；h2 total `12173.086 s` | `success_with_qualifications`；强内存成功、速度负担很大 | `docs/task031_compact_physical_slab_memory_optimization/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 代价/不足 | 最终状态 |
|---|---|---|---|
| public form-action + overlap0.125 + compact lifecycle | h5/h3/h2 full pass；峰值 `1.620/3.474/7.898 GiB` | h2 solve `11982.581 s`，约 3.33 h；每次 MatMult 重新做 form action 和通信 | `success_with_qualifications`；强内存成功、速度很慢 |
| restart50 | 内存约 `-1.89%`，残差和时间更差 | 收益低于停止阈值 | `controlled_negative` |
| fixed Richardson linear PC | 200 步 residual `0.7703` | 恢复线性但失去有效平滑 | `controlled_negative` |
| boundary Jacobi selective local solver | residual 恶化到 `0.0118`，RSS 无收益 | 破坏物理 slab 修正 | `controlled_negative` |

## 3.33 Task032：Hybrid FEM–Modal direct baseline

**探索目的：**用上下两个短 3D FEM 区 + 中间二维模态传播，降低 Full3D 行数和 NNZ，并验证与同网格 Full3D 一致。

流程建立同离散 Full3D–Hybrid closure 和 M160 基线；h5/h3 都把 rows/NNZ 显著压缩且 R/T/A 最大差约2–3e-6，但不等于跨网格 continuum convergence。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `hybrid_h5_h3_M160` | Case080 authority；source SHA见 Task032 summary | `F-STAGE4-S` p2 h5/h3 | direct Hybrid M160；rows `14,052/68,796`，NNZ `2,000,624/8,594,673` | h5 R/T/A=`0.0890210691/0.4425867427/0.4683921882`，residual `2.5455e-12`；h3=`0.0046128199/0.5836509402/0.4117362399`，residual `2.6036e-12`；same-grid max delta `2.07e-6/2.63e-6` | `success_with_qualifications`；QEP h5 beta误差29.5323%为离散负结果 | `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| full3D h5/h3 | R/T/A 分别见第 1.2 节 | h5 与 h3 物理结果差异明显，不能称连续收敛 | `success`，同网格基线 |
| Hybrid h5 M160 | rows `44,778→14,052`；NNZ `4,896,156→2,000,624`；最大 R/T/A 差 `2.07e-6` | QEP h5 beta 离散误差仍大 | `success_with_qualifications` |
| Hybrid h3 M160 | rows `198,518→68,796`；NNZ `21,317,860→8,594,673`；最大差 `2.63e-6` | 只证明同离散一致 | `success_with_qualifications` |
| QEP air h5 | beta 相对误差 `29.5323%`，但多项式 residual `<=1.82e-15` | 代数求解正确不等于横截面离散收敛 | `controlled_negative`（离散精度） |
| h2 Hybrid | 中心/上界资源 Gate 未满足 | 未运行 | `not_run` |
| 0.7 nm current direct layout | 预测不满足资源 | 当前显式模态、多 RHS 和 local LU 不可扩展 | `predicted negative` |

## 3.34 Task033：高阶 Floquet、Hybrid fixed-p 与 p4 资源 Gate

研究对象是高阶 p3 Floquet、同阶 Hybrid 和固定-p等精度压缩，目的在于证明高阶 local FEM 与 modal coupling 可共同工作。流程完成 p3/h5 closure、M80/120/160 漏斗和 p3/h7.5 等精度点；p4/h5 Full3D 在12.616 GiB assembly Gate受控停止。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `p3_h5_full_vs_hybrid_M160` | Task033 record identities | `F-STAGE4-S` hexa p3/h5 | Full3D direct vs Hybrid M160 | Full residual `5.442e-12/2.343e-12`；Full rows 145,943、NNZ 35,566,727、7.781 GiB、103.59 s；Hybrid local rows `21,847×2+320`、NNZ `5,156,503×2`、2.618 GiB、111.94 s；R/T/A与16项Gate通过 | `success` | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/hybrid_vs_full3d_summary.md` |
| `p3_h7p5_hybrid_M160` | Phase D authority | 同物理 p3/h7.5 | Hybrid direct M160 | 26,998 rows，factor inventory 17,057,414，2.008 GiB，74.908 s；相对 p2/h3 物理误差不劣 | `success_with_qualifications`；固定-p等精度压缩 | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md` |
| `p4_h5_full_assembly_gate` | controlled-stop record | p4/h5 | Full3D assembly-only Gate | 339,892 rows，155,205,040 base NNZ，12.616 GiB停止；未factor、无official物理 | `controlled_stop` | `docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md` |

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| p3/h5 full3D | peak `7.781 GiB`；true residual `5.442e-12` | 成功建立同阶 Hybrid 对照 | `success` |
| p3/h5 Hybrid M80/120/160 | M160 true residual `2.277e-12`；M120→160 R/T/A 差 `7.216e-14`；显著功率/幅值差 `3.676e-10/1.925e-10` | fixed-p M 漏斗闭合 | `success` |
| p3/h7.5 full3D | `3.667 GiB`、`44.487 s`、residual `6.449e-12` | 相对 p2/h3 全部物理误差不劣 | `success_with_qualifications` |
| p3/h7.5 Hybrid M160 | `2.008 GiB`、`74.908 s`；16项 Gate 通过 | 等精度压缩成功 | `success_with_qualifications` |
| p4/h5 full3D assembly | 339,892 rows；155,205,040 base NNZ；12.616 GiB 时停止 | 未进入 factorization；目标资源 Gate 失败 | `controlled_stop` |
| variable-p / hp | native cellwise variable-p H(curl) 未资格化 | 没有 target PDE | `not_run / incomplete` |

## 3.35 Task034：WSL、高阶固定几何与 graded-h

**探索目的：**在工作站 WSL 环境资格化固定几何高阶 Full3D/Hybrid，并检查高阶 p 与 graded-h。

流程资格化 complex128 WSL/MPI/MUMPS、Case093 fixed rectangular anchor、高阶 same-grid Hybrid 与 resource model v2.1。graded-h 为受控负结果；0.7 nm / 2 TiB 仍是预测模型，不是 production feasibility。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `case093_fixed_geometry_high_p` | Case093 records；geometry/source identity见 summary | `F-HO-S` fixed rectangular；p3/p4及Hybrid | Full3D/Hybrid direct | p4/h5 Full3D 339,892 FE、339,972 rows、28.888 GiB、917.47 s；Hybrid M160 100,920 rows、9.206 GiB、412.42 s；R/T/A/通道详见 Case093 | `success_with_qualifications`；fixed geometry authority | `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md` |
| `graded_h_and_resource_v2p1` | controlled-negative + prediction | fixed rectangular | graded-h + analytic resource model | graded-h未得到更优综合点；0.7 nm explicit layout仍超2 TiB；精确预测区间见 summary | `controlled_negative / predicted_unknown` | `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md` |

| 模型/候选 | 已知结果 | 具体不足 | 最终状态 |
|---|---|---|---|
| Case093 WSL baseline | WSL complex ABI、MPI、MUMPS 和固定几何链通过 | 仅是环境/基线，不是自适应成功 | `success` |
| p3/h3 + p4/h5 closure | 高阶 fixed-p 和同网格 Hybrid closure 通过 | 资源和连续收敛仍有限 | `success_with_qualifications` |
| graded-h | 正式记录为受控负结果 | 没有得到更优物理/资源综合点 | `controlled_negative` |
| 0.7 nm / 2 TiB | 形成 stress model v2.1 | 当前 modal core 与 explicit layout 仍不可宣称 production feasible | `predicted / unknown` |

> Task034 的逐通道与完整资源权威仍是 Case093 records；本总账保留其 evidence identity，不把未逐项复核的 heavy artifact 数字二次手抄为新 authority。

## 3.36 Task035：H(curl) goal-oriented adaptivity

研究对象是 periodic tetra 上真实 discrete adjoint/DWR、一次 local-h 与固定网格 p-up，目的是建立目标导向 h/p 判别而非无限 h-refine。流程完成周期闭合、normalized R/T/A multi-goal 与 strict-R audit；选定 p4/p5、theta0.7、每初始网格最多一次local-h，但预算内仍未获得 strict same-error 候选。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `h50_p4p5_one_local_h` | Case094 hash-bound record；source SHA见 summary | `F-HO-S` periodic tetra；base180 cells，p5 15,405 DoF | strict-R DWR theta0.7，一次 local-h；refined1,248 cells，101,210 DoF | base vector/strict-R error `2.2032e-2/1.5130e-3`；refined `6.3581e-4/4.3764e-4`；>90k | `controlled_negative`（预算与strict-R） | `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` |
| `refined_mesh_global_p6` | same-origin Case094 | 同refined mesh；p6 | fixed-mesh global p+1；167,784 DoF | vector/strict-R error `1.0224e-4/5.1371e-5`；精度正信号但远超90k | `controlled_negative`（预算） | `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json` |

| 模型/候选 | 实际结果 | 具体不足 | 最终状态 |
|---|---|---|---|
| tetra h50 base p5 | 180 cells；15,405 DoF；vector error `2.2032e-2`；strict-R error `1.5130e-3` | 基础误差较大 | `research baseline` |
| one-local-h p5 | 1,248 cells；101,210 DoF；vector error `6.3581e-4`；strict-R `4.3764e-4` | 超 90k；不是同 patch h/p 公平竞争 | `controlled_negative`（预算） |
| refined mesh global p6 | 167,784 DoF；vector error `1.0224e-4`；strict-R `5.1371e-5` | 精度更高但远超 90k | `controlled_negative`（预算） |
| classifier/DWR | multi-goal DWR 和周期标记通过 | structured hexa 无 hanging-node transition；selected tetra p6 架构缺失 | `incomplete` |

## 3.37 Task035b：高阶 local-hp、静态凝聚、通道恢复和资源

研究对象是 fixed rectangular hexa 的高阶 DoF 分解、assembly-time static condensation、setup/cache、方向性 h 和 local-p/selective-trace 研究。流程取得精确物理消元、显著内存/rows压缩与 setup 加速；但 `<=90k` 最强 h13 仍只通过10/12功率和10/12幅值，不能宣称 same-error 成功。selective trace与condensed iterative均不得提升为production。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `global_p6_h10_reference_v1` | Case095 source/geometry/tensor hashes见 record | `F-HO-S`；(6,3,14) hexa；global p6 | MPI8 assembly-time exact static-condensed direct；173,802 FE，51,272 active rows，41,989,040 NNZ，202,441,352 factor NNZ | R00/R/T/A=`7.537612e-4/7.628815e-4/0.602701634/0.396535485`，true residual `1.26e-11`；12 powers/amplitudes见1.4；direct peak15.964 GiB，build/setup/solve `102.32/102.54/0.167 s` | `success; best_available_same_code_reference` | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json` |
| `fixed_p5trace_p6interior_h13` | Case095 hash-bound record | `(6,2,12)`；89,740 Full3D-equivalent DoF | MPI8 assembly-time static-condensed direct；20,120 rows，11,013,212 NNZ，36,273,200 factor NNZ | R00/R/T/A=`0.000756117570/0.000765246512/0.602682451672/0.396552301816`，residual `5.81e-12`；`T(-4)=4.354892e-7`、`R(-4)=2.723391e-7`、`r(-4)=2.127847e-4-4.721864e-5i`、`r(-5)=-1.009264e-4-5.936550e-5i`失败；peak 6.411 GiB | `controlled_negative`；10/12+10/12，不是same-error | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json` |
| `condensed_iterative_three_profiles` | Case095 negative records | h15 condensed trace | Jacobi GMRES30、ASM/ILU0 FGMRES30、z-slab/DtN coarse，均200步 | terminal residual ratios `0.861662/0.999661/0.996265`；peak `3.921/4.462/3.885 GiB`；无official R/T/A/channel | `controlled_negative`；不得提升production | `docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md` |
| `selective_p6_trace` | fixture/capability v2；无PDE record | p5trace/p6interior storage + research orbit | MatShell/action-only fixtures | actual DWR、row plan、正式PDE数量均0；资源/物理 `not_run` | `incomplete; research_only` | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json` |
| `hybrid_static_h1a_p2_h5` | source `148729c28c3f9aefec8e5646cc644c5c4e2332da`；raw SHA 绑定 compact record | `F-STAGE4-S`；p2/h5 hexa；Full3D 44,698 FE；Hybrid local 6,826 FE/side | MPI8 direct；local static condensation；M120/M160；M160 10,000 total rows、976,400 matrix NNZ pair、5,986,184 factor NNZ pair | M160 R00/R/T/A=`0.089011819673/0.089021069106/0.442586742743/0.468392188151`，residual `3.45e-12`；static-vs-standard 12/12+12/12；Full3D-vs-Hybrid 3/12+2/12；peak 3.308 GiB，186.36 s | `controlled_negative`；H1-A channel Gate fail，H1-B not run | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json` |

### 3.37.1 精度候选

| 模型 | 目的 | 具体结果 | 未满足项 | 状态 |
|---|---|---|---|---|
| global p6/h15 | 以更粗 h 压缩 p6/h10 | 84,492 DoF；24,704 rows；12 GiB pair；总量/场通过 | 仅 6/12 功率、8/12 幅值；弱衍射级未收敛 | `controlled_negative` |
| fixed p5-trace/p6-interior h15 | 降低共享 trace 阶次并保留 p6 interior | 74,890 DoF；16,880 rows；5.803 GiB；R/T/A 接近参考 | 具体失败通道见第 1.4.1.3 | `controlled_negative` |
| directional-z h14 | 只增加 z 分辨率 | 82,315 DoF；功率/幅值通过数 7/12、9/12 | `R/T(-4,-5)` 等仍超 reference band | `controlled_negative`，有正信号 |
| directional-z h13 | 使用接近 90k 的 z 分辨率 | 89,740 DoF；R/T/A 和场通过 | `T(-4)`、`R(-4)` 功率及 `r(-4),r(-5)` 幅值失败，数值见第 1.4.1 | `controlled_negative`；预算内最强 |
| h13 top-two z redistribution | 固定 DoF 移动内部 z 平面 | 8/12 功率、8/12 幅值 | 比原 h13 退化 | `controlled_negative` |
| h14 exact reverse | 验证相反节点移动 | 7/12 功率、8/12 幅值 | 没有支持该机制 | `controlled_negative`；z-node lane closed |
| global p6/h14 trace discriminator | 判断 full p6 trace 是否有帮助 | 92,850 DoF；9/12 功率、12/12 幅值 | 超预算 2,850 DoF，且功率仍非12/12 | `diagnostic controlled_negative` |
| selective p6 trace | 只激活关键 p6 edge/face orbit | fixture 中 inactive rows=0、Floquet pullback和MatShell action通过 | actual channel DWR、正式 row plan、runner 和 PDE 均为 0 | `incomplete` |

### 3.37.2 Setup/cache 与 direct rank

| 研究点 | 实际结果 | 解释 | 状态 |
|---|---|---|---|
| h15 cold/warm setup | non-KSP build `19.242/6.141 s`，相对旧 `61.61 s` cold 加速 `3.202×` | 缓存复用 tensor、Aii factor 和 local Schur；warm 仍需全局矩阵和 MUMPS numeric | `engineering success` |
| h13 cold/warm setup | `19.410/6.696 s` | 无同 h13 旧 cold baseline，不能宣称 cold-code 2.9× | `engineering success_with_qualification` |
| h15 MPI1/2/4/8 direct | RSS `1.295/2.158/3.100/4.711 GiB`；总时间 `76.007/74.913/61.849/53.901 s` | MPI1 是最低实测 direct 内存；MPI8 最快，但不是最低内存 | `engineering success` |

### 3.37.3 静态凝聚迭代负结果

| Profile | 200步后 residual ratio | 内存 | 具体结论 | 状态 |
|---|---:|---:|---|---|
| GMRES30 + Jacobi | `0.861662` | `3.921 GiB` | 没有 global factor，但残差只下降约14%，未产生 official R/T/channel | `controlled_negative` |
| FGMRES30 + ASM(1)/ILU0 | `0.999661` | `4.462 GiB` | 几乎完全停滞；含局部 ILU | `controlled_negative` |
| FGMRES + z-slab ILU0 + DtN trace coarse | `0.996265` | `3.885 GiB` | 物理分块和80D coarse仍未改善谱；不是严格 factorless | `controlled_negative` |
| matrix-free selective trace MatShell | fixture action正确，不构造 global matrix/LU | 无正式 PDE、KSP 和内存 authority | 只降低存储不会自动解决预条件器问题 | `incomplete` |

### 3.37.4 Review V3 static Hybrid H1-A

| 研究点 | 实际结果 | 未满足项 | 状态 |
|---|---|---|---|
| Full3D standard/static 等价 | 12/12 power、12/12 amplitude；rows `44,778→30,800`；peak `2.960→2.763 GiB` | 无 static-equivalence 失败 | `engineering success` |
| Hybrid standard/static M160 等价 | 12/12 + 12/12；rows `14,052→10,000`；NNZ pair `1,454,248→976,400` | factor 只降6.3%，peak升0.7%，total升93.6% | `engineering mixed_negative` |
| static Hybrid M120→M160 | 12/12 + 12/12；总量和场几乎不变 | 增大 M 没有修复 Full3D channel closure | `converged discriminator` |
| static Full3D↔Hybrid M160 | 相对口径3/12 power、2/12 amplitude；strict absolute 2/12+2/12 | 9个功率和10个幅值失败，逐项值/限值见 compact record | `controlled_negative` |
| H1-B/H1-C/H1-D | PDE 均未启动 | Review V3 要求 H1-A 全通过后才能进入 H1-B | `not_run_by_review_prerequisite` |

## 3.38 Task035c：Hybrid逐通道与高阶静态内存闭合

Task035c先用p2/h5解释“总R/T接近但弱衍射级不对”的原因，再在p6/h10上
正式比较Full3D与Hybrid、standard与static。Hybrid把中间均匀长段替换成二维
模态传播；static condensation再精确消去上下局部三维单元内部自由度。最终
12通道物理与正式15%/25%内存Gate通过，但用户期望的50%峰值下降没有达到。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task035c_p2_h5_continuous_symbol_baseline` | Task035b H1-A + Case096 root-cause ledger | `F-STAGE4-S`；p2/h5；MPI8 | Hybrid continuous QEP phase + continuous traction；M120/M160 | M160 对 same-source Full3D 仅 `3/12 powers + 2/12 amplitudes`；提高 M 未修复 | `controlled_negative_root_cause_baseline`；不是 M 截断不足 | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p2_h5_root_cause_v1.json` |
| `task035c_p2_h5_discrete_phase_only` | source/record hash见 Case096 compact | 同一 fixed rectangular p2/h5 | 只启用 scalar-CG discrete phase，traction仍连续 | `4/12 powers + 4/12 amplitudes`；相对原始有改善但未闭合 | `controlled_negative_discriminator`；phase必要但不充分 | same compact record |
| `task035c_p2_h5_discrete_phase_traction` | source `8a1e40c...`；Case096 compact | `F-STAGE4-S`；p2/h5；MPI8 | Hybrid M120/M160；`full3d_uniform_cg` + `scalar_cg_discrete_derivative` opt-in | 两点均12/12 powers+12/12 boundary amplitudes；phase-only仅4/12+4/12 | `diagnostic_success`；root cause closed | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p2_h5_root_cause_v1.json` |
| `task035c_p6_h10_full_standard` | source `244b62e1...`；clean MPI8 | `F-HO-S`；global p6/h10；173,802 FE | standard Full3D direct；173,882 rows；210,353,168 matrix NNZ；438,050,956 factor NNZ | R/T/A=`0.000762881475133/0.602701633983338/0.396535484541529`；residual`1.709e-11`；peak34.041GiB；2581.55s；12/12+12/12 | `success; discrete_reference` | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json` |
| `task035c_p6_h10_full_static` | same source/mesh/MPI | `F-HO-S`；p6/h10 | exact cell-interior static；51,272 rows；41,989,040 NNZ；212,343,992 factor NNZ | R/T/A=`0.000762881475126/0.602701633985538/0.396535484539337`；residual`3.092e-11`；14.722GiB；260.74s；12/12+12/12 | `engineering_success`；peak -56.75% | same compact record |
| `task035c_p6_h10_hybrid_standard_M120_M160` | same source；MPI8 | local p6/h10 ends + discrete modal middle | M120/M160；52,292/52,372 total rows；60,434,236 NNZ；141,010,528 factor NNZ | peaks11.077/11.247GiB；times942.03/1014.71s；两点12/12+12/12 | `success baselines` | same compact record |
| `task035c_p6_h10_hybrid_static_M120` | same source；MPI8 formal authority | local exact static + modal middle；17,168 rows | 12,313,232 matrix NNZ；45,293,792 factor NNZ | R/T/A=`0.000762881475142/0.602701633984217/0.396535484540641`；residual`2.079e-12`；RSS7.544GiB；PSS/USS `5.769862/5.491413 GiB`；322.78s；12/12+12/12 | `success; selected`；RSS -31.89%，PSS/USS -38.88%/-40.31%；用户50%目标仍open | six-path + PSS/USS compact records |
| `task035c_p6_h10_hybrid_static_M160` | same source；MPI8 | 17,248 rows；same local matrix/factor inventory | RSS7.929GiB；PSS/USS `6.169376/5.888676 GiB`；393.84s；12/12+12/12；相对M120无物理收益 | `success_not_selected`；RSS -29.50%，PSS/USS -35.81%/-37.16% | same compact records |
| `task035c_static_rank_MPI1` | source `244b62e1...`；measured | Full static formal pass；Hybrid static M120 | Hybrid measured1.752GiB、1328.72s | 12/12+12/12但positive QEP biorthogonality `1.197600e-6 > 1e-6` | `controlled_negative_numerical`；非内存floor | `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_static_rank_study_v1.json` |
| `task035c_static_rank_MPI2` | same source；measured | Full static formal pass；Hybrid numeric pass | Hybrid measured3.142GiB、798.20s | terminal launcher-drain RSS/swap readability失败 | `controlled_negative_resource_authority`；MPI4 not run by stop rule | same rank record |

### 3.38.1 Task035c 选择、内存口径与能力边界

M120 被选择是因为它与 M160 都通过 12/12 功率、12/12 physical-boundary
complex amplitudes、R/T/A/场/残差 Gate，而 M160 没有可测物理收益，却使 static
RSS增加 `5.1052%`、modal coupling 增加 `38.9106%`、总时间增加
`22.0146%`；因此停止 M160 lane，不运行 M240。用户提出的 `>=50%` static
Hybrid RSS 降幅仍为 `not_achieved/open_engineering_gap`。

PSS/USS 来自原始 MPI8 timeline 中逐 rank `/proc/<pid>/smaps_rollup` 的历史
回填。只使用 8 个 rank 同时可读的样本，不由 RSS 推算且没有重跑 PDE。正式
Task035c relative-memory authority 仍为 simultaneous process-tree/live-worker
RSS；PSS/USS 是共享页/私有页诊断。compact authority 为
`benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_pss_uss_ledger_v1.json`。

| qualified scope | not qualified / must fail closed |
|---|---|
| fixed rectangular block grating；structured tensor-product；axis-aligned first-order affine hexa；modal middle uniform z；single axial h；p1–p6；complex128；Floquet；sparse auxiliary DtN；direct standard/static Full3D/Hybrid | nonuniform z；local-h/hanging hexa；curved/distorted/high-order geometry；tetra static；hexa/tetra/prism/pyramid mixed；sloped/rounded/rough/defect或任意 irregular geometry；production automatic hp adaptivity |

---

## 3.39 Task035d：exact-sequence local-p 与 true local-h 自适应

Task035d 固定使用 Task034 矩形块光栅、p6/h10 Full3D static reference-v1、
MPI8 direct MUMPS 和冻结的 12 个显著功率/复振幅 Gate。首批只检验真实
assembly-time variable-p active space：inactive 高阶模式不生成 global row，
并继续使用 exact cell-interior static condensation。两个正式 p-only 候选均为
结构与资源成功、同精度失败的 controlled negative；不能把资源压缩写成物理
成功，也不能据此放宽 12/12 Gate。

| Model ID | 身份/数据身份 | 物理与离散 | 算法/规模 | 总量/逐级/资源 | 结论/status | evidence |
|---|---|---|---|---|---|---|
| `task035d_case097_closeout` | source、plan、MPI identity 与 checker SHA 均冻结 | Task034 fixed rectangular grating；p4/p5/p6 exact-sequence local-p；balanced-hexa local-h | MPI8 direct static；最佳资源点76,205 DoF/18,470 rows；最终判别点88,915/21,650 | 最佳通道6/12+6/12；最终4/12+6/12；峰值最低7.29866 GiB；Hybrid未运行 | `PARTIAL_WITH_CONTROLLED_NEGATIVES`；无 production hp candidate | `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md` |

| Model ID | source / plan identity | p4/p5/p6 cells | FE DoF / active rows | matrix / factor NNZ | residual / peak | strict physics | status / evidence |
|---|---|---:|---:|---:|---:|---|---|
| `task035d_t30_h10_mpi8` | solver `c3768cf4723c2ae949c82d1ce8b18a56f5ab0f7b`；checker `5f960f912809b162e363259b0896af25ef3b0018` | `144/56/52` | `87,600 / 28,990` | `15,253,176 / 63,564,300` | `1.410e-11 / 10.0929 GiB` | `0/12 power + 0/12 amplitude`；R/T/A L2 `21.214`；volume/interface `9.337%/9.884%` | `controlled_negative_accuracy`；`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_h10_mpi8_controlled_negative_v1.json` |
| `task035d_sidewall_z0_guard_h10_mpi8` | solver/checker source `a6f2d8a3b88efda581aa0e36f5ebcd9d6776e0cf`；plan SHA `31922411775580b2f44b474897dbf877d96b7887f74d22e02b3f0e410c205bc2` | `72/168/12` | `89,870 / 31,064` | `16,490,572 / 76,721,484` | `7.560e-12 / 8.38265 GiB` | `1/12 power + 0/12 amplitude`；R/T/A L2 `13.271`；volume/interface `3.733%/4.016%` | `controlled_negative_accuracy`；`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/sidewall_z0_guard_h10_mpi8_controlled_negative_v1.json` |

相对 global-p6 static baseline（173,802 FE DoF、51,272 rows、
41,989,040 matrix NNZ、212,343,992 factor NNZ、14.72176 GiB），T30 的
rows/matrix/factor/peak 分别下降 `43.46%/63.67%/70.07%/31.44%`；
sidewall guard 分别下降 `39.41%/60.73%/63.87%/43.06%`。这些是正式实测
的资源正信号，但两条精度结果连续为负，因此 T25、T15 和第三条 p-only PDE
均不运行，研究转向 true local-h。

`sidewall_z0_guard_v1` 冻结通道误差如下。误差与 tolerance 均来自独立
checker；只有 `top(-1,0)` power 通过，所有 complex amplitude 均失败。

| side/order | power error / tolerance | amplitude error / tolerance |
|---|---:|---:|
| bottom -7 | `7.25323e-7 / 2.15869e-9` | `1.23293e-3 / 1.21657e-5` |
| bottom -5 | `7.92214e-9 / 3.89127e-10` | `9.95785e-6 / 1.28065e-6` |
| bottom -4 | `4.38440e-9 / 5.25100e-10` | `2.07690e-5 / 2.54166e-6` |
| bottom -2 | `4.61647e-8 / 4.65105e-9` | `2.99641e-5 / 4.58081e-6` |
| bottom -1 | `1.84990e-6 / 1.11441e-7` | `2.06358e-4 / 1.27290e-5` |
| bottom 0 | `1.86466e-3 / 2.17577e-4` | `5.08728e-2 / 6.77963e-3` |
| top -7 | `2.28277e-7 / 1.24944e-9` | `6.72145e-4 / 7.99504e-7` |
| top -5 | `8.23809e-9 / 1.19430e-9` | `7.92162e-6 / 1.11321e-6` |
| top -4 | `1.58210e-8 / 1.08649e-9` | `1.60124e-5 / 1.88152e-6` |
| top -2 | `3.03981e-9 / 1.24228e-9` | `2.03888e-5 / 3.18649e-6` |
| top -1 | `4.78904e-8 / 5.11184e-8` pass | `8.61368e-5 / 7.41338e-6` |
| top 0 | `1.21288e-4 / 3.19529e-5` | `2.83493e-3 / 8.33027e-4` |

该段登记的是当时的阶段状态。后续 Attempt 2 已补齐 compiled tensor、
PETSc ownership、full recovery/residual 和 MPI1/2/8 production identity，
并启动最小正式 local-h/hp PDE；最终结果登记在 3.39.2–3.39.6。Attempt 1
记录仍保留为能力演进证据，不回写成当时已经具备 PDE credit。

### 3.39.1 True local-h Attempt 1 component authority

source `b12b1887ca3acb534f36186c93e9e5efb10cf2ad` 已完成前述 Gate
中的几何与纯约束图部分：

| capability | measured authority | status |
|---|---|---|
| true local split | 2-cell fixture `2→9` leaves；全局坐标平面 control 需12 cells | pass |
| broken carrier boundary identity | 42 facets；30 topological exterior = 25 physical + 5 catalogued hanging；unexplained=0 | pass |
| H(curl)/H1 face restriction | p4 `144x40`、p5 `220x60`、p6 `312x84`；full rank/commuting | pass |
| 3D orientation | 6 hexa faces；每阶 `4×8×8=256` child/D4 组合 | pass |
| static Schur exchange | local-condense-then-hanging 与 one-shot 误差 `<=2e-12` | pass |
| periodic+hanging graph | 37 cells、8 patches、raw 5,120→independent 3,384、chain depth2、residual `1.4621e-15` | pass |
| MPI identity | MPI1/2/8 stable physical authority SHA `19e032d3...96afa8` | pass |
| compiled cell tensor / PETSc ownership / PDE | 未绑定、未运行 | `in_progress/no_PDE_credit` |

MPI comparison authority 为
`benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi_identity_v1.json`
（SHA256 `d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44`）。
该记录明确保持 `heavy_pde_started=false`、`pde_accuracy_credit=false`。
因此 Attempt 1 是结构正信号；下一步必须完成实际 cell-oriented
`C_K`、compiled FFCx tensor、RHS/recovery、PETSc row ownership 与 MPI2
matrix/action identity，才能进入 local-h PDE。

### 3.39.2 Attempt 2、正式 local-h 与 combined-hp 总账

Attempt 2 将 physical geometry-key graph 绑定到 compiled FFCx tensor、
`C_K^H S_K C_K`、RHS/recovery、DtN、PETSc owner-routed rows 和完整
active-space residual。MPI1/2/8 production identity 通过；inactive p6 mode、
hanging slave 和 periodic slave 不生成 global row。

正式模型均为 Task034 fixed rectangular block grating、13.5 nm、S 偏振、
MPI8 direct MUMPS、assembly-time static condensation、zero swap：

| Model ID | numerical source | local-h / p plan | FE DoF / rows | matrix / factor NNZ | residual / peak / total | strict physics | status / evidence |
|---|---|---|---:|---:|---:|---|---|
| `task035d_h15_top_air_local_h_mpi8` | `ed9c8fc6002bf086f19bef94492b23d7c24b7287` | 120 roots→134 leaves；p5 trace/p6 interior | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `5.740e-12 / 7.50068 GiB / 202.762 s` | R/T/A、Avolume、fields pass；`6/12 power + 6/12 amplitude` | `controlled_negative_accuracy`；`h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json` |
| `task035d_h15_symmetric_remote_p5_mpi8` | `54cb665e05e72027d8e617b1a1c546413c127f0e` | 120→148 leaves；p5 trace；p5/p6 interiors `32/116` | `84,240 / 20,060` | `11,176,430 / 32,658,700` | `2.124e-11 / 7.50883 GiB / 208.766 s` | scalar/energy/fields pass；`4/12 + 4/12` | `controlled_negative_accuracy`；`h15_symmetric_top_air_remote_p5_interior_mpi8_candidate_check_v2.json` |
| `task035d_h15_factorial_bridge_mpi8` | `d194075dda0aceef8bf566dd76412c9517fe4bb3` | 120→134 leaves；p5 trace；p5/p6 interiors `32/102` | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `3.433e-12 / 7.29866 GiB / 198.400 s` | scalar/energy/fields pass；`4/12 + 4/12` | `controlled_negative_accuracy`；`h15_top_air_remote_p5_interior_bridge_mpi8_candidate_check_v1.json` |
| `task035d_h15_selective_ten_face_mpi8` | `0ecd914b246f433614252f6f3c0513b06b078542` | 120→134 leaves；10 physical p6 faces；其他 trace p5 | `83,125 / 18,670` | `10,406,108 / 32,683,000` | `1.287e-11 / 8.06898 GiB / 279.206 s` | scalar/energy/fields pass；`5/12 + 6/12` | `controlled_negative_accuracy`；`selective_face_selection_compact_v1.json` |
| `task035d_h15_left_grating_single_root_mpi8` | `333cb7e437906c78c95c94788abb76e2f263bc80` | 120→162 leaves；p5 trace；p5/p6 interiors `48/114` | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `3.267e-11 / 8.06120 GiB / 297.114 s` | scalar/energy/interface pass；volume max fail；`4/12 + 6/12` | `controlled_negative_accuracy`；`h15_left_grating_top_closure_p5fine_mpi8_controlled_negative_compact_v1.json` |

相对 p6/h10 Full3D static，实测压缩：

| Model ID | rows | matrix NNZ | factor NNZ | peak RSS | PSS / USS |
|---|---:|---:|---:|---:|---:|
| h15 top-air local-h | `-63.9764%` | `-75.7410%` | `-85.4645%` | `-49.0504%` | `6.41306 / 6.25235 GiB` |
| symmetric remote-p5 | `-60.8753%` | `-73.3825%` | `-84.6199%` | `-48.9950%` | `6.42191 / 6.26128 GiB` |
| factorial bridge | `-63.9764%` | `-75.7410%` | `-85.4645%` | `-50.4227%` | `6.21633 / 6.05586 GiB` |
| ten-face selective trace | `-63.5864%` | `-75.2171%` | `-84.6085%` | `-45.1901%` | `6.98143 / 6.83401 GiB` |
| left-grating single-root | `-57.7742%` | `-70.5106%` | `-82.4574%` | `-45.2430%` | `6.92657 / 6.77756 GiB` |

最小 `76,205` DoF 候选仍高于 preferred `75,000` 上界，并且物理 Gate
失败；不得因资源正信号将其登记为 same-error hp success。

Task035d `task.md` §3.2 的统一控制组没有遗漏：global p6/p5 h10、
Task035 p4→p5 DWR theta0.7、Task035b fixed h15/h14/h13，以及 Task035d
p-only、h-only、combined resource best 和 final discriminator 的
DoF/rows/NNZ/peak/channel/status 对照集中登记在 Task035d
`outcomes/summary.md` §4.1。Task035 tetra DWR 与 global p5 缺少同一
Case095 12-channel/peak 口径的字段均明确写为未记录，不由其他量推断。

### 3.39.3 弱通道失败总账

下表列出所有失败通道身份；每行最后给出该候选最大超限的实际
error/tolerance，完整 12 行保存在对应 checker。

| Model ID | power failures | amplitude failures | 最大 power error/tol | 最大 amplitude error/tol |
|---|---|---|---:|---:|
| h15 top-air local-h | bottom `-5,-4,-2`；top `-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.333561e-8/5.251003e-10` | bottom -4 `1.589564e-5/2.541658e-6` |
| symmetric remote-p5 | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `1.008269e-7/2.158694e-9` | top -7 `2.285933e-5/7.995039e-7` |
| factorial bridge | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `9.977858e-8/2.158694e-9` | top -7 `2.371900e-5/7.995039e-7` |
| ten-face selective trace | bottom `-7,-5,-4`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.221993e-8/5.251003e-10` | bottom -4 `2.051506e-5/2.541658e-6` |
| left-grating single-root | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `1.204267e-8/5.251003e-10` | top -4 `1.087300e-5/1.881525e-6` |

### 3.39.4 DWR 与 h/p 归因

| Authority | measured conclusion | credit boundary |
|---|---|---|
| `h15_top_air_nested_p_dwr_mpi8_checker_v2.json` | 12 unit-channel、36 real-goal closure pass；16 periodic p-down pairs 无 conservative-safe action | 不授权继续 remote p-down |
| selective-face raw DWR `bd19254a...76bf1` | independent checker `36/36`；ten-face contribution 可重算 | posthoc attribution；不授予 causal selection credit |
| `hp_factorial_bridge_attribution_v1.json` | local-h、symmetric combined、factorial bridge 三点实测归因 | factorial attribution pass；combined-hp accuracy false |
| `bounded_single_seed_top_air_hp_selection_v2.json` | compact-DWR location oracle；left-grating cost-normalized score最高 | actual local-h DWR unavailable；success forecast false |

### 3.39.5 Final left-grating observables

| R00 | Rtotal | Ttotal | Aclosure | Avolume | normalized R/T/A L2 |
|---:|---:|---:|---:|---:|---:|
| `0.000755218940191` | `0.000764349909195` | `0.602685528512531` | `0.396550121578274` | `0.396550121578974` | `0.117446` |

volume weighted relative L2 `0.01229361` 通过，但 maximum point error
`0.04688675 > 0.04102079`；interface relative L2/max
`0.00788774/0.02208509` 均通过。最终 raw watchdog/full/compact checker
SHA256 分别为：

```text
7d4c7a1efa0068c7a6c478ad4cef4b88fdfa1f5acbd10532d4c2794a356f7165
1b9dd3cdb931f5fe69da5a0a567ff278a47416f7082d47cef2e0b5e4109e2492
d6e03061465b29ce4e958bfd6ac7972f245130fdf66de197541caed09e8e4225
```

### 3.39.6 Lane closure 与 Task035d 分类

| item | final status |
|---|---|
| p-only | closed after T30 and guard formal negatives |
| remote p5 interior | closed controlled negative |
| frozen ten-face selective subset | closed controlled negative |
| whole top-port selective trace | incomplete/not run；未运行 modes 未被证伪 |
| bounded single-root top-air local-h | closed after top-air and left-grating formal negatives |
| outer-periodic | `not_run_by_lane_stop`；不是 PDE failure |
| multi-seed | `not_evaluated_by_stop_rule` |
| automatic cycles 1–4 | `not_completed`；只有 manual bounded discriminators，没有 per-cycle authority |
| Hybrid Phase F | `not_run_full3d_hp_gate_failed` |

Task035d 最终登记：

```text
classification = PARTIAL_WITH_CONTROLLED_NEGATIVES
production_hp_candidate = none
phase_e = partial_manual_bounded_discriminators
ordinary_default_changed = false
```

重新开启该 lane 前，必须先在新 candidate space 上产生 actual per-channel
local-h 或 trace-orbit DWR；当前 compact location oracle 不足以授权继续扫描。

---

# 4. 今后新增模型的登记模板

每次正式计算至少新增一行主表，并按可用性新增衍射级和复振幅表。

## 4.1 主模型表模板

| Task | Model ID | 配置 ID | 研究目的 | Full3D/Hybrid | 原始完整矩阵/静态凝聚/自适应 | direct/iterative | 网格类型 | p/h | cells | FE DoF | active rows | matrix NNZ | factor NNZ | MPI/threads | residual | R00 | Rtotal | Ttotal | Avolume | Aclosure | peak RSS/PSS/cgroup | build | MUMPS setup | iterations/solve | total | status | evidence |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.2 显著衍射功率模板

| Model ID | R(0,0) | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | Rtotal | T(0,0) | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | Ttotal | Avolume | Aclosure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.3 显著衍射复振幅模板

| Model ID | r(0,0) | r(-1,0) | r(-2,0) | r(-4,0) | r(-5,0) | r(-7,0) | t(0,0) | t(-1,0) | t(-2,0) | t(-4,0) | t(-5,0) | t(-7,0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 4.4 失败或未完成模型模板

| Task / Model ID | 探索目的 | 实际运行到哪一步 | 实际数值 | 未满足的具体物理量/资源 Gate | 直观原因 | status | 下一步或停止理由 | evidence |
|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 不得只写“10/12”或“失败”，必须列具体通道和数值 | 待填写 | 待填写 | 待填写 | 待填写 |

---

# 5. 当前数据缺口与后续自动化

1. Task000–035d 已逐项回填；早期没有保存的 source SHA、geometry hash、12 通道、factor NNZ 或 PSS/cgroup 明确标成“历史未记录”。
2. Task032–034 的 heavy JSON 包含比总账更细的衍射级、场误差和资源字段；总账保留权威 evidence path，不建立第二份易漂移的逐字段副本。
3. COMSOL 参考只计算零级；非零衍射级不能写 0。
4. 不同物理配置、偏振、网格和软件之间的数值只能做标注清楚的横向参考，不能混成单一收敛序列。
5. 新任务不得以未填写占位词收口；历史缺口必须说明“历史未记录”，当前未运行项必须写 `not_run`。
