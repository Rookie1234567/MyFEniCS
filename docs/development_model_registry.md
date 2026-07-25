# 开发阶段研究对象与计算结果总账

> **用途。** 本文是项目级“模型—方法—结果—资源—状态”总账。它不替代各 Task 的 `task.md`、`outcomes/summary.md`、`response_vN.md` 和正式 JSON record，而是把分散在不同任务中的重型计算统一登记，便于回答：已经算过什么、使用什么算法、得到什么物理结果、消耗多少资源、哪些结果可作为参考、哪些只是探索或负结果。
>
> **维护规则。** 从本文建立起，每次新增正式 PDE、QEP、Hybrid、迭代或自适应模型，都必须在对应 Task 收口时同步更新本文。历史记录没有保存的字段必须写“历史记录未保存”或“待回填”，不得猜测。

---

## 0. 阅读方法、物理对象与统一记号

### 0.1 本文区分的三类物理配置

不同软件或不同 Task 并不总是使用完全相同的几何、偏振和衍射级集合，因此不能把所有数值混为一个收敛序列。

| 配置 ID | 用途 | 周期单元 / 几何 | 波长与入射 | 偏振 | 边界与衍射级 | 主要来源 |
|---|---|---|---|---|---|---|
| `C-COMSOL-P0` | COMSOL 直接/迭代求解器对照 | 周期 `50×25 nm`；空气 `50×25×130 nm`；基底 `50×25×10 nm`；光栅 `16×25×120 nm` | `13.5 nm`；`80°`（相对法线） | P | 两周期端口 + 双 Floquet；仅 `(0,0)` 零级 | `task029/.../comsol_3d_direct_iterative_memory_report.md` |
| `F-STAGE4-S` | FEniCS Stage4 原始完整 FE 矩阵、Hybrid 和迭代主线 | 单元 `50×25×140 nm`；Si 块 `17×25×120 nm` | `13.5 nm`；`theta=80°`、`phi=0°`，即 `10°` 掠入射 | S | 双 Floquet + Fourier-DtN；top/bottom 各 40 个传播模态，共 80 个辅助量 | Task027–Task033 |
| `F-HO-S` | FEniCS 高阶、h/p、自适应和静态凝聚主线 | Task034 冻结规则矩形光栅；与 `F-STAGE4-S` 同一工程主点族 | `13.5 nm`；`10°` 掠入射 | S | 双 Floquet + DtN；显著衍射级使用 Task035b reference v1 | Task034–Task035b |

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
| Task033 full3D p3/h5 | `F-STAGE4-S` | hexa；p3；h5 | 历史主表待回填 | 历史主表待回填 | 历史主表待回填 | 历史主表待回填 | 见 Task033 record | 见 Task033 record | 见 Task033 record | `5.442e-12` | `7.781 GiB` | 历史主表待回填 | `success`；p3 same-degree closure |
| Task033 full3D p3/h7.5 | `F-STAGE4-S` | hexa；p3；h7.5 | 历史主表待回填 | 历史主表待回填 | 历史主表待回填 | 历史主表待回填 | 见 Task033 Phase D record | 见 Task033 Phase D record | 见 Task033 Phase D record | `6.449e-12` | `3.667 GiB` | `44.487 s` | `success_with_qualifications`；等精度压缩成功 |

**衍射级数据状态：**Task032/Task033 的任务总结主要冻结 R/T/A、接口场和同网格 Hybrid 闭合；本文初版尚未从各 heavy JSON 逐项回填 12 个显著级。不得把缺失项视为零。后续 registry checker 应从原始 record 自动抽取。

### 1.2.2 Hybrid FEM–Modal

Hybrid 把上下短 3D FEM 区保留为完整 FE 矩阵，中间长区域改用二维本征模态传播，因此行数和 NNZ 明显减少。该方法仍属于“原始完整 FE 局部矩阵”，因为上下 FEM 区尚未使用 cell-interior 静态凝聚。

| Task / 模型 | 配置 | local 3D FE DoF | 外部 DtN | 内部模态 `2M` | total rows | matrix NNZ | Rtotal | Ttotal | Avolume | true residual | 峰值内存 / 时间 | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Task032 Hybrid h5 M160 | `F-STAGE4-S` | 6,826 bottom + 6,826 top | 80 | 320 | 14,052 | 2,000,624 | `0.0890210691` | `0.4425867427` | `0.4683921882` | `2.5455e-12` | 见 Case080 M160 record | `success`；相对 full3D 最大 R/T/A 差 `2.07e-6` |
| Task032 Hybrid h3 M160 | `F-STAGE4-S` | 34,198 bottom + 34,198 top | 80 | 320 | 68,796 | 8,594,673 | `0.0046128199` | `0.5836509402` | `0.4117362399` | `2.6036e-12` | 见 Case080 M160 record | `success`；相对 full3D 最大差 `2.63e-6` |
| Task033 Hybrid p3/h5 M160 | `F-STAGE4-S` | 历史主表待回填 | 80 | 320 | 历史主表待回填 | 历史主表待回填 | 见 Task033 record | 见 Task033 record | 见 Task033 record | `2.277e-12`（Phase C M160） | 新 SHA `2.618 GiB`；Phase C 约 `106.98 s` | `success`；16 项 Gate 通过 |
| Task033 Hybrid p3/h7.5 M160 | `F-STAGE4-S` | 历史主表待回填 | 80 | 320 | 历史主表待回填 | 历史主表待回填 | 见 Task033 Phase D record | 见 Task033 Phase D record | 见 Task033 Phase D record | 见 record | `2.008 GiB`；`74.908 s` | `success_with_qualifications`；固定 p 等精度压缩成功 |

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

当前没有使用 cell-interior 静态凝聚的正式 Hybrid Full3D–Modal 成功模型。

| 模型 | 状态 | 原因 |
|---|---|---|
| Static-condensed Hybrid | `not_run` | Task035b 没有获得 `<=90k` 且 12/12 功率、12/12 复振幅全部通过的 Full3D 候选，因此 Hybrid、M 漏斗和 external DtN 漏斗未解锁。 |

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

# 2. 各 Task 的重型探索模型与处置

> 本节按 Task 记录“为什么算、实际算了什么、得到什么、为什么成功或失败”。Task000–026 的逐任务历史已有 Task028 归档表；本文初版先登记与当前 3D direct/iterative/Hybrid/hp 主线直接相关的 Task027–Task035b。旧 Task 的重型数值将由后续自动回填工具从 `task000_task027_progress.csv` 和历史 records 补齐。

## 2.1 Task027：mesh-independent physical-slab Schwarz

**探索目的：**在 14 GB 工作站内，用同一 MPI4 迭代算法求解 h5/h3/h2，并使最大/最小迭代数比小于 2。

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| owner-slab + 一步平滑 | h5/h3/h2 迭代数 `2765/1836/3682`；比值 `2.0054` | 只差严格门槛约 10 步；h2 更快但不满足 `<2` | `controlled_negative` |
| owner-slab + 两步全局平滑 | `1201/993/1804`；比值 `1.8167`；h2 RSS `12.958 GB`；h2 R/T/A=`0.0013429363/0.5992132418/0.3994438284` | 同一规则跨三网格通过；物理 R 跨网格仍未收敛 | `success_with_qualifications` |
| spectral / GenEO / interface harmonic coarse | h5 100 步真残差约 `0.2187–0.2504`，远差于固定 75D coarse `6.272e-3` | 谱子空间代数正确，但没有捕获非正规 Floquet-DtN 慢误差 | `controlled_negative` |

## 2.2 Task029：原始完整矩阵直接法内存剖析

**探索目的：**确定 full3D p2 direct 的内存峰值，并测试 rank、对象生命周期、OOC、BLR、ordering 和线程。

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

## 2.3 Task030：H(curl) 低内存迭代与层级基础设施

**探索目的：**在保持 h5/h3/h2 真残差和 R/T/A 的同时，进一步压低 Task027 的迭代内存。

| 模型/候选 | 结果 | 具体原因 | 最终状态 |
|---|---|---|---|
| p/h multilevel coarse（5 类） | 100 步真残差 `0.374864–0.680155`，比 Task027 基线差 145–264 倍 | 792D p1 coarse 未包含 Maxwell 梯度/近核和掠入射慢误差 | `controlled_negative` |
| symmetric pre/post + ILU0 + factor-only + local shift + restart90 | h5/h3/h2 full pass；内存 `1.688/3.793/9.375 GB`；R/T/A 见第 1.3 节 | 对称平滑是关键；不是 p/h multigrid 成功 | `success_with_qualifications` |
| restart80 | weak-positive Gate 未过 | Krylov 内存继续下降不足以抵消收敛恶化 | `controlled_negative` |

## 2.4 Task031：assembled-F-free 极限内存路线

**探索目的：**不在 Krylov 过程中常驻 assembled `F`，并压缩 overlap 和对象生命周期。

| 模型/候选 | 实际结果 | 代价/不足 | 最终状态 |
|---|---|---|---|
| public form-action + overlap0.125 + compact lifecycle | h5/h3/h2 full pass；峰值 `1.620/3.474/7.898 GiB` | h2 solve `11982.581 s`，约 3.33 h；每次 MatMult 重新做 form action 和通信 | `success_with_qualifications`；强内存成功、速度很慢 |
| restart50 | 内存约 `-1.89%`，残差和时间更差 | 收益低于停止阈值 | `controlled_negative` |
| fixed Richardson linear PC | 200 步 residual `0.7703` | 恢复线性但失去有效平滑 | `controlled_negative` |
| boundary Jacobi selective local solver | residual 恶化到 `0.0118`，RSS 无收益 | 破坏物理 slab 修正 | `controlled_negative` |

## 2.5 Task032：Hybrid FEM–Modal direct baseline

**探索目的：**用上下两个短 3D FEM 区 + 中间二维模态传播，降低 Full3D 行数和 NNZ，并验证与同网格 Full3D 一致。

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| full3D h5/h3 | R/T/A 分别见第 1.2 节 | h5 与 h3 物理结果差异明显，不能称连续收敛 | `success`，同网格基线 |
| Hybrid h5 M160 | rows `44,778→14,052`；NNZ `4,896,156→2,000,624`；最大 R/T/A 差 `2.07e-6` | QEP h5 beta 离散误差仍大 | `success_with_qualifications` |
| Hybrid h3 M160 | rows `198,518→68,796`；NNZ `21,317,860→8,594,673`；最大差 `2.63e-6` | 只证明同离散一致 | `success_with_qualifications` |
| QEP air h5 | beta 相对误差 `29.5323%`，但多项式 residual `<=1.82e-15` | 代数求解正确不等于横截面离散收敛 | `controlled_negative`（离散精度） |
| h2 Hybrid | 中心/上界资源 Gate 未满足 | 未运行 | `not_run` |
| 0.7 nm current direct layout | 预测不满足资源 | 当前显式模态、多 RHS 和 local LU 不可扩展 | `predicted negative` |

## 2.6 Task033：高阶 Floquet、Hybrid fixed-p 与 p4 资源 Gate

| 模型/候选 | 实际结果 | 具体不足或收益 | 最终状态 |
|---|---|---|---|
| p3/h5 full3D | peak `7.781 GiB`；true residual `5.442e-12` | 成功建立同阶 Hybrid 对照 | `success` |
| p3/h5 Hybrid M80/120/160 | M160 true residual `2.277e-12`；M120→160 R/T/A 差 `7.216e-14`；显著功率/幅值差 `3.676e-10/1.925e-10` | fixed-p M 漏斗闭合 | `success` |
| p3/h7.5 full3D | `3.667 GiB`、`44.487 s`、residual `6.449e-12` | 相对 p2/h3 全部物理误差不劣 | `success_with_qualifications` |
| p3/h7.5 Hybrid M160 | `2.008 GiB`、`74.908 s`；16项 Gate 通过 | 等精度压缩成功 | `success_with_qualifications` |
| p4/h5 full3D assembly | 339,892 rows；155,205,040 base NNZ；12.616 GiB 时停止 | 未进入 factorization；目标资源 Gate 失败 | `controlled_stop` |
| variable-p / hp | native cellwise variable-p H(curl) 未资格化 | 没有 target PDE | `not_run / incomplete` |

## 2.7 Task034：WSL、高阶固定几何与 graded-h

**探索目的：**在工作站 WSL 环境资格化固定几何高阶 Full3D/Hybrid，并检查高阶 p 与 graded-h。

| 模型/候选 | 已知结果 | 具体不足 | 最终状态 |
|---|---|---|---|
| Case093 WSL baseline | WSL complex ABI、MPI、MUMPS 和固定几何链通过 | 仅是环境/基线，不是自适应成功 | `success` |
| p3/h3 + p4/h5 closure | 高阶 fixed-p 和同网格 Hybrid closure 通过 | 资源和连续收敛仍有限 | `success_with_qualifications` |
| graded-h | 正式记录为受控负结果 | 没有得到更优物理/资源综合点 | `controlled_negative` |
| 0.7 nm / 2 TiB | 形成 stress model v2.1 | 当前 modal core 与 explicit layout 仍不可宣称 production feasible | `predicted / unknown` |

> Task034 的逐通道和完整资源明细需从 Case093 records 自动回填到本文，初版不复制未核对数字。

## 2.8 Task035：H(curl) goal-oriented adaptivity

| 模型/候选 | 实际结果 | 具体不足 | 最终状态 |
|---|---|---|---|
| tetra h50 base p5 | 180 cells；15,405 DoF；vector error `2.2032e-2`；strict-R error `1.5130e-3` | 基础误差较大 | `research baseline` |
| one-local-h p5 | 1,248 cells；101,210 DoF；vector error `6.3581e-4`；strict-R `4.3764e-4` | 超 90k；不是同 patch h/p 公平竞争 | `controlled_negative`（预算） |
| refined mesh global p6 | 167,784 DoF；vector error `1.0224e-4`；strict-R `5.1371e-5` | 精度更高但远超 90k | `controlled_negative`（预算） |
| classifier/DWR | multi-goal DWR 和周期标记通过 | structured hexa 无 hanging-node transition；selected tetra p6 架构缺失 | `incomplete` |

## 2.9 Task035b：高阶 local-hp、静态凝聚、通道恢复和资源

### 2.9.1 精度候选

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

### 2.9.2 Setup/cache 与 direct rank

| 研究点 | 实际结果 | 解释 | 状态 |
|---|---|---|---|
| h15 cold/warm setup | non-KSP build `19.242/6.141 s`，相对旧 `61.61 s` cold 加速 `3.202×` | 缓存复用 tensor、Aii factor 和 local Schur；warm 仍需全局矩阵和 MUMPS numeric | `engineering success` |
| h13 cold/warm setup | `19.410/6.696 s` | 无同 h13 旧 cold baseline，不能宣称 cold-code 2.9× | `engineering success_with_qualification` |
| h15 MPI1/2/4/8 direct | RSS `1.295/2.158/3.100/4.711 GiB`；总时间 `76.007/74.913/61.849/53.901 s` | MPI1 是最低实测 direct 内存；MPI8 最快，但不是最低内存 | `engineering success` |

### 2.9.3 静态凝聚迭代负结果

| Profile | 200步后 residual ratio | 内存 | 具体结论 | 状态 |
|---|---:|---:|---|---|
| GMRES30 + Jacobi | `0.861662` | `3.921 GiB` | 没有 global factor，但残差只下降约14%，未产生 official R/T/channel | `controlled_negative` |
| FGMRES30 + ASM(1)/ILU0 | `0.999661` | `4.462 GiB` | 几乎完全停滞；含局部 ILU | `controlled_negative` |
| FGMRES + z-slab ILU0 + DtN trace coarse | `0.996265` | `3.885 GiB` | 物理分块和80D coarse仍未改善谱；不是严格 factorless | `controlled_negative` |
| matrix-free selective trace MatShell | fixture action正确，不构造 global matrix/LU | 无正式 PDE、KSP 和内存 authority | 只降低存储不会自动解决预条件器问题 | `incomplete` |

---

# 3. 今后新增模型的登记模板

每次正式计算至少新增一行主表，并按可用性新增衍射级和复振幅表。

## 3.1 主模型表模板

| Task | Model ID | 配置 ID | 研究目的 | Full3D/Hybrid | 原始完整矩阵/静态凝聚/自适应 | direct/iterative | 网格类型 | p/h | cells | FE DoF | active rows | matrix NNZ | factor NNZ | MPI/threads | residual | R00 | Rtotal | Ttotal | Avolume | Aclosure | peak RSS/PSS/cgroup | build | MUMPS setup | iterations/solve | total | status | evidence |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 3.2 显著衍射功率模板

| Model ID | R(0,0) | R(-1,0) | R(-2,0) | R(-4,0) | R(-5,0) | R(-7,0) | Rtotal | T(0,0) | T(-1,0) | T(-2,0) | T(-4,0) | T(-5,0) | T(-7,0) | Ttotal | Avolume | Aclosure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 3.3 显著衍射复振幅模板

| Model ID | r(0,0) | r(-1,0) | r(-2,0) | r(-4,0) | r(-5,0) | r(-7,0) | t(0,0) | t(-1,0) | t(-2,0) | t(-4,0) | t(-5,0) | t(-7,0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 3.4 失败或未完成模型模板

| Task / Model ID | 探索目的 | 实际运行到哪一步 | 实际数值 | 未满足的具体物理量/资源 Gate | 直观原因 | status | 下一步或停止理由 | evidence |
|---|---|---|---|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 不得只写“10/12”或“失败”，必须列具体通道和数值 | 待填写 | 待填写 | 待填写 | 待填写 |

---

# 4. 当前数据缺口与后续自动化

1. Task000–026 的逐 Task 重型模型尚未从 Task028 归档 CSV 自动回填；本文初版只登记了与当前 3D 主线直接相关的 Task027–Task035b。
2. Task032–034 的 heavy JSON 中包含比 summary 更细的衍射级、场误差和资源字段，需要后续编写只读 registry aggregator 自动抽取，避免人工复制错误。
3. COMSOL 参考只计算零级；非零衍射级不能写 0。
4. 不同物理配置、偏振、网格和软件之间的数值只能做标注清楚的横向参考，不能混成单一收敛序列。
5. 本文任何“待回填”均表示历史 summary 未提供该字段，不代表模型没有该结果。
