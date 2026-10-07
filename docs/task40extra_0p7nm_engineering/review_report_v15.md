# Review V15：以独立原方程约束参考预条件器，完成 Gx560 并推进 E1 电尺寸

## 0. 本轮结论与首先消除的 blocker

**本轮首先消除的 blocker 是：四个 p6 参考因子已经能在本机同时建立，但参考逆的准入合同仍把“必须像精确逆一样通过每项微小误差检查”与“能够作为 FGMRES 的合格近似预条件器”混在一起，连续多轮在真实 target solve 之前停止。V15 用独立原生增广方程和可重算的非抵消误差预算明确约束近似参考 PC，取得 Gx560 完整解，并在同一轮推进已有 E1 的新 PC 对照。**

这里的预条件器是每次迭代提供一个修正方向的辅助求解器；它可以有受控误差，真实 Maxwell 方程必须由原 A6 残差和最终场、功率验收。V15 保留同一四 q 参考构造，不新增低内存 p4 逆、DD、AMG、NN 或另一套物理模型。

最终目标不变：真空波长 **0.7 nm**，当前目标周期域 **50×25×140 nm**，complex128、Nédélec H(curl)、x/y 双 Floquet、z 开放 Fourier-DtN，允许周期单胞内真实非可分三维材料/几何；约 **2 TB 是整机物理内存**，任务零 swap、保留系统余量；必要构建、全部因子、迭代、恢复、输出和独立检查的单场总墙钟不超过 **172800 s**。当前没有目标尺寸的精度、内存或 48 h 资格，也没有数学不可行性的证明。

| 审阅对象 | 本轮裁决 | 准确含义 |
|---|---|---|
| V14 四 q 构建及参考组件 | `pass_with_qualifications` | 四因子可同时存在；各因子准入探针严格通过；参考修正有真实正结果 |
| V14 新参考 PC 的 Gx560 主里程碑 | `fail / NUMERICAL_GATE_FAILED_BEFORE_TARGET_SOLVE` | 物理 RHS 准入失败，target KSP 未启动；不等于 target 迭代不收敛 |
| 已有旧路线 p6 完整解 | 保留既有资格 | Gx560、Gx784、E1 已有 p6 target + exact p4 correction 的结果；E2 另有保存场输出修复 |
| 原尺寸 / 任意三维 / 2 TB / 48 h | `NOT_QUALIFIED` | 缺少精度合格离散、规模和全过程证据 |
| V15 新合同 | `AUTHORIZED_CONDITIONAL_EXECUTION` | 允许按下述完整条件实现和运行；现在不预判 PASS |
| master / ordinary default | 不批准合并或变更 | 保持显式 opt-in 研究路线 |

V14 的数值负结果必须保留。V15 不是把 `1e-11` 改成 `2e-11`，也不是给近零分母增加 floor，而是前瞻定义一个**用途明确、以独立原方程裁决的近似 PC 合同**。旧 exact-reference 合同与新 PC 合同分开报告。

## 1. 仓库快照、角色及执行边界

```text
repository                  = Rookie1234567/MyFEniCS
branch                      = task40extra_0p7nm_engineering
review_base_SHA             = be77753320f4f5541ab014a398cd87eb19f0cc7b
latest_commit_UTC           = 2026-10-07T06:17:38Z
latest_commit_message       = docs(task40): archive V14 reference gate and full cost evidence
reviewed_numerical_source   = 6ac8cf7fd4697e575a4bf47a862c560ae290076b
latest_review_before_this   = review_report_v14.md
latest_response             = response_v14.md
readonly_dot_SHA            = 15713d3e09b63f65511c7b7f61fa043fdb23dca5
review_file                 = docs/task40extra_0p7nm_engineering/review_report_v15.md
response_required           = response_v15.md
canonical_worktree          = /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
execution                   = existing local_wsl2_authorized; MPI1; maththreads1
roles                       = 执行者实现/测试/运行；主控审查/冻结源码/commit/push
```

本次审阅实际读取了根与 docs/任务目录 AGENTS、仓库工作原则、任务书、最新 review/response、summary、V14 原始 compact records、相关历史 Gx/E1/E2 记录、最近提交以及求解器/入口源码。当前任务目录没有另列独立补充任务书；相关历史扩展通过 review 文件记录。

本报告只新增审阅文件，不修改数值源码或运行 FE。后续执行仍在既有 Task40 主控/执行协作和 canonical worktree 中；执行者不 commit/push，由主控集中处理。不得 SSH、切换工作站、修改 dot/Task042/其他项目、另建聊天/worktree、启用执行 subagents 或自动化。目录 AGENTS 中“本轮为 V10”是陈旧导航，本轮执行权威为 V15；这不恢复历史窗口或旧阶段限制。

dot 远端最新提交仍为 2026-10-05。只引用该固定 SHA；不把其他位置尚未推送的结果当作最新远端证据。主控先检查本机实时 PID/service/source/账本；审阅端没有本机实时进程信息。

## 2. 综合结果：已有能力和新路线的缺口都要保留

### 2.1 统一比较

下表内存为十进制 GB（10^9 B）。workflow 是对应 worker 的完整记录口径；独立离线 checker、开发修复和 campaign charge 另列，不互相替代。

| 模型 | 实际方法与状态 | 原 A6 / 主要数值 | workflow / KSP | 树 RSS 峰 |
|---|---|---|---|---:|
| B0，80 cells，532 modes | 新四 q p6 参考 PC 已有完整归档结果，V14 复用 | 释放后 A6=1.608976231e-8；R/T/A_volume=0.9842736081/0.0142405181/0.00148587385 | workflow 1340.829 s；V14 未 fresh 重跑 | 3.24849 GB |
| Gx560，560 cells，340 modes，历史对照 | p6 target + exact p4 correction；已完整求解 | A6=9.733476895e-7；171 步 | workflow 1925.863 s；KSP 1499.305 s | 5.25568 GB |
| Gx560，V14 新参考 PC | 四个 p6 q 因子与 startup；target 未启动 | 因子准入探针通过；physical action identity=1.683457269e-11 > 1e-11 | workflow 2220.827 s；target KSP=NOT_RUN | 10.16850 GB |
| Gx784，784 cells，340 modes，历史对照 | p6 target + exact p4 correction；已完整求解 | A6=9.692115163e-7；有 x 细化保存场对照 | workflow 3431.623 s；另有离线跨网格 checker 1442.153 s | 7.78274 GB |
| E1，760 cells，588 retained modes，历史对照 | 0.7 nm，缩小几何放大 1.25 倍；p6 target + exact p4 correction | A6=9.781668526e-7；R/T/A_volume=0.0623565374/0.9159264755/0.0217169517 | workflow 4580.375 s；KSP 3722.193 s | 10.65034 GB |
| E2，880 cells，700 retained modes，历史记录 | 几何放大 1.5 倍；原 worker 输出失败，后用保存场修复 | 原 A6=9.793073227e-7；恢复后 R/T/A_volume=0.0511688616/0.9239410513/0.0248900536 | 原 workflow 7692.028 s；保存场恢复 process 74.154 s | 原运行 11.34920 GB |

B0 的 workflow/场来自 V14 formal record，其 3.24849 GB RSS 来自当前 summary 的 V14 表（原值 3,248,488,448 B）；本审阅未重放该 raw 资源时间线。B0 的复用记录与更早 worker 的 exit 4 / offline revalidation 是不同证据层，不能改写原运行状态。E2 同样保留 `ORIGINAL_WORKER_FAILED`，不得把离线输出修复写成 fresh PDE。

**这些历史“p4 对照”保存的是 p6 全场，p4 只是 PC。**因此新参考 PC 可以与它们作同离散场比较。Gx560→Gx784 已有八类场最大变化约 `6.41915e-4`、显著复模式最大变化约 `8.03006e-5`，支持已测 x 方向一致性；不是 y/z 或连续极限资格。E1/E2 是改变物理尺寸的诊断点，不是 h 收敛序列。

证据：[V14 formal results](outcomes/records/review_v14_formal_results.json)、[历史与当前 summary](outcomes/summary.md)、[Gx 四角接口](outcomes/records/review_v4_four_corner_interface_v1.json)、[Gx784 收口](outcomes/records/review_v6_gx784_postprocess_closeout_v1.json)、[E1/E2 实测](outcomes/records/electrical_size_v2.json)。

### 2.2 必须纠正的 E1 汇总遗漏

V14 [目标桥接 JSON](outcomes/v14_engineering_to_target.json) 将 E1 的实际网格/模式/成本写为 unknown、NOT_RUN。该表述只能指**新 p6 reference-PC 路线未运行**；相同原输入的历史 p6 target + p4 correction 已有上述结果。

```text
E1 historical source:
63dd2a7378153f2ab5094eb5e7a98d05758a39bf
input SHA256:
5c0aa01d1bb327f1331b69cfe359c6f775961398d316c2f88d3aeaff978af8fd
physical_model SHA256:
6ea7e95a9b415b3bcc97c67e3c4d3580c7a6999211fbfb3f15bc42fad2ce821d
mesh_plan SHA256:
b266e571b422d176521f42296739358092dc32d5c9b22a16c9f854d84c659e4e
native ordered-mode SHA256:
d1ea3dadce6e546ac7fce32493edb0fab09d7de22208850aca0a139a23b1e52b
```

E1 的 **588 是 retained modes，包含 136 传播模式与 452 倏逝模式**；不能叫作 588 个传播模式。保留原手动包络 m=-10…10、n=-3…3，不能切成 AUTO 136 后仍声称同离散对照。[模式清单](outcomes/records/electrical_size_auto_mode_envelopes_v1.json)已有依据。

本轮用新 current 段更正汇总、补明确 route/epoch，不改写旧 response/review。历史场数组在本机的存在性、哈希、dofmap 和相位约定仍须检查；上述输入和 manifest 身份不能替代 saved vector 身份。

## 3. V14 失败链：必须一次处理整组问题

[参考与装配原始记录](outcomes/records/review_v14_reference_and_assembly.json)给出了以下 physical regular incident RHS 数据。

| 检查 | 实际值 | 原合同及解释 |
|---|---:|---|
| sector/native action 相对差 | 1.6834572689277185e-11 | 原 1e-11 门失败 |
| action 绝对差 / 分母 | 4.13049706226925e-11 / 2.4535799859655354 | 不能凭“只超一点”直接宣布舍入或通过 |
| 原 global regular equation | 1.571386718821102e-9 | strict 1e-10 失败；在旧整体 inexact 1e-8 内 |
| local combined | 1.5713721062272218e-9 | strict 失败；在旧整体 inexact 内 |
| global alpha closure | 1.1280453648956473e-11 | strict 1e-11 失败；在旧 1e-9 内 |
| q0 本次 MatSolve | 1.105608031163589e-10 | 此 RHS strict 失败，per-call 1e-8 内；不等于因子准入探针失败 |
| twist1 RHS 范数 | 5.288411619304687e-16 | 几乎未激励 |
| twist1 residual 范数 / relative | 8.755475826665997e-14 / 165.55965111916072 | 原逐扇区 inexact 1e-8 失败 |
| internal recovery | 1.994570459286834e-16 | 原门通过 |
| native action recovery identity | 5.4534346300710764e-11 | 原 1e-10 门通过 |
| all port equations | 5.172410446630256e-13 | 原门通过 |

旧逐扇区规则对 twist1 实际要求绝对残差约 `5.29e-24`。不能由此数学断言 complex128 永远做不到，但只修第一项 action 或机械加一次 refinement，并不能合理保证后续准入。

源码还表明，当前 local residual 包含多段计算：各局部解先 lift/sum 成 global u；再 extract；再根据 trace/alpha/RHS 重建内部场；再作用 native 算子。该指标混合了原局部求解、传输、恢复、作用与近零 RHS 放大，不能现在单独归因于 MUMPS、普通 bug 或无害舍入。

关键位置：[worker](../../src/runners/task40_v10_worker.py)中的 `_sector_native_forward_action`、`_regular_local_recovery_facts`、`_verify_regular_inverse`；[原恢复与残差](../../src/solvers/p6_cell_condensed_action.py)；[y-orbit 传输](../../src/solvers/task40_v10_p6_yorbit.py)。

V14 在 action 结构门失败时禁止 correction，随后退出 target 之前。下轮不再只重算同一个失败比值，也不只修第一道门后再付出约 2221 s 构建成本碰下一道门。

## 4. V15 核心决定：独立 native 增广残差约束的不精确参考 PC

### 4.1 什么改变，什么是验收依据

新增显式策略身份：

```text
NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
```

这是同一四 q 参考逆的**新的准入合同**，不是新的全局求解算法。保留旧 `STRICT_ONLY`、`STRICT_THEN_BOUNDED_INEXACT_V13` 及其原始结果，不把历史失败改成通过。

新合同可以允许参考 sector/native 的小作用差和近零扇区的大 RHS-relative ratio，但必须把它们对完整参考方程的影响纳入下面的独立误差预算。真实 target A6、材料、非可分缺口、约束、全部模式和最终物理 Gate 均不改变。

FGMRES 允许变化或非线性的右预条件器；这解释了为什么不必要求每次辅助逆都满足 exact-reference 的全部精度标签。它不保证收敛，仍须实测原 target。[PETSc FGMRES 官方说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)。

### 4.2 从原增广方程推导预算

参考问题保留原矩阵含义和原 H 归一化：

```math
\begin{bmatrix}V_r&B\\-D&H_p\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=
\begin{bmatrix}f\\g\end{bmatrix}.
```

消去端口未知量后，定义：

```math
A_r=V_r+B H_p^{-1}D,\qquad
b_{\mathrm{eff}}=f-BH_p^{-1}g.
```

对于**同一个实际累计 global u**，令 E_s 为既有 primal extraction、L_s 为既有 dual lift，b_s 是实际 folded effective RHS，A_s 是对应独立 local native 作用：

```math
e_s=b_s-A_sE_su,\qquad
d_b=b_{\mathrm{eff}}-\sum_sL_sb_s,\qquad
d_A=\sum_sL_sA_sE_su-A_ru.
```

因此：

```math
r_{\mathrm{elim}}=b_{\mathrm{eff}}-A_ru
=d_b+\sum_sL_se_s+d_A.
```

返回的 alpha 也必须是同一完整状态。令：

```math
\delta\alpha=\alpha-H_p^{-1}(Du+g).
```

则实际增广 FE 残差和 port 残差为：

```math
r_{\mathrm{FE}}=f-V_ru-B\alpha
=d_b+\sum_sL_se_s+d_A-B\delta\alpha,\qquad
r_{\mathrm{port}}=-H_p\delta\alpha.
```

使用已有、由原 RHS 决定的尺度，而不是候选解幅值或某个几乎为零的扇区 RHS：

```math
S=\lVert f\rVert_2+\lVert BH_p^{-1}g\rVert_2.
```

新合同的非抵消 FE 预算是：

```math
\eta_{\mathrm{budget}}=
\frac{\lVert d_b\rVert_2+\sum_s\lVert L_se_s\rVert_2+
\lVert d_A\rVert_2+\lVert B\delta\alpha\rVert_2}{S}
\le 10^{-8}.
```

由三角不等式，它直接控制**实际返回 (u, alpha)** 的完整增广 FE 残差，并阻止多个大误差互相抵消后“总残差看起来很小”。近零扇区的误差仍逐项计入全局预算，没有删除 q 或增加 floor。

同时直接用独立 global native 算子重算原消元 FE 和完整增广 FE；不得只凭预算推导授予 PASS。当前 compact 尚缺这个预算及 physical witness 完整增广 FE 的明确字段，**本审阅没有据已有小数值预判新合同通过**。

### 4.3 实现时必须保留的数学细节

1. e_s 必须在 E_su 上计算。不能直接使用会再次 `recover_storage` 的旧 local residual 代替；那是另一个内部场。可复用 `_sector_native_forward_action` 已计算的 local native action，旧恢复检查继续单独保留。
2. 先对每块误差执行实际 `lift_dual`，再取范数并求和；不得假设 native moment 变换是 Euclidean unitary，也不得用 local norm 或平方和替代。
3. d_A 独立取 global native action 与 local native 合成之差；不得用 q CSR 自洽作用、目标近似算子或从最终残差倒算替代。
4. 现有四 q、两 twist 的端口关系为 H_s=H_g[ids]/2、g_s=g[ids]/sqrt(2)、alpha_s=sqrt(2) alpha[ids]。b_s 必须用实际 fold(f)−B_s H_s^{-1}g_s 构造，使用原 H；不得额外乘除 sqrt(2)。
5. 原 FE/port 尺度分别保留。不要把单位或行尺度不同的 FE 与 port 向量无依据拼接后只报告一个 norm。
6. S=0 单独处理，FE 预算及 FE 残差的分子必须精确为零，否则拒绝；端口仍按原 g 和原 closure 检查。只有完整 (f,g) 都精确为零才返回完整零状态，不能把 S=0 但 g 非零的载荷删除。非零极小 RHS 保留稳定范数和真实尺度，不以全局常数或经验 floor 代替。
7. B delta-alpha 优先直接作用小差向量：offset=alpha−recover(u)，delta-alpha=offset−g/H，再调用已有 `apply_modal_rhs`。不相减两份大 B 作用。旧 alpha closure 的运算次序与指标仍原样保存，两个数学等价次序不强求 byte equality。
8. 从历史 NPZ 读残差时核对符号；某些旧 storage 是 `A u+B g/H−f`，即负的 r_elim。新的分解 closure 必须以清楚定义的符号独立重算。
9. 分解恒等式 closure 采用原作用尺度、门槛 1e-10；分母由所比较动作/原 RHS 的范数和形成，不能用近零最终残差范数。这个 closure 是分解和记账检查，不能称为新的独立算子正确性证明。

### 4.4 准入表与执行范围

| 项目 | V15 要求 |
|---|---|
| 独立 global native 原 FE 残差 | 所有候选检查、采用者 <=1e-8 |
| 独立 global native 完整增广 FE 残差 | 使用同一 u/alpha；所有候选检查、采用者 <=1e-8 |
| 非抵消预算 eta_budget | 每个 startup witness、每次 PC 均检查；采用者 <=1e-8 |
| global alpha closure | 原尺度 <=1e-9 |
| 每 q、每次实际 MatSolve | 真实残差 <=1e-8；因子初次准入探针继续原 strict 1e-10 |
| mapping、覆盖、伴随工作恒等式、mode/RHS identity | 原门与完整覆盖要求，禁止弱化 |
| internal recovery、native recovery identity、Schur-port identity、saved-field representation | 沿原执行范围、频率和门槛；不借 PC 合同掩盖恢复或表示错误 |
| 旧 sector/native 1e-11 和逐扇区原 ratio | 原数值、分母、旧 PASS/FAIL 均保留；只在新策略下另作 PC 近似预算判定 |
| 最终真实 target | 原 A6/释放后 <=1e-6；target identity <=1e-10；原物理与场比较门不变 |

所有候选均保存原始检查结果；初次仅新数值预算超限不立即 raise，允许下面授权的一次 correction，再决定是否可采用。S 按原 RHS 冻结；alpha closure 同时记录初次冻结尺度和候选原尺度，两套尺度均须满足所采用合同，不能靠修正后 alpha 变大获得更宽分母。q 的每次实际调用按自身真实 RHS 检查，另保留原/冻结尺度记录。

每次 PC 的新增两个 local action、传输和 B delta-alpha 作用必须真实执行并计入 PC 时间。复用有界 workspace；逐 call 保存指标、source、计数和候选状态 hash，只对 startup、首末、失败和已有 checkpoint 保存完整向量包，避免每次调用生成大 NPZ。不得只在 startup 算预算，却在结果中声称每次 PC 均受其约束。

候选选择顺序：

- 在 V15 模式下，所有实际采用的候选，包括旧 strict 已通过者，都必须先满足 V15 的完整预算、独立原方程和其他准入；strict 只是附加标签。初次新合同已通过即可使用，不为更漂亮的数值强制 refinement。
- 未满足新数值预算、但其他真实结构和资源条件合格时，至多一次完整增广残差修正：FE/alpha 一起更新，同一四 q 因子，最多四次额外 MatSolve，无新 factor、无递归 correction、无隐藏内层 Krylov。
- 初次/修正后完整状态均保存并独立重判。不得拼接不同候选中最好的 u、alpha 或单项指标。
- 不把 NaN/Inf、错误映射、损坏因子、错误模式或资源停止吞为“返回较好候选”。
- 两个候选均未通过新合同则明确拒绝该 PC 调用；保存完整状态。不是以改阈值继续。

## 5. 有界诊断、自修复与真实入口：先消除下一次可预见的停机

### 5.1 复用失败载荷，而不是重新确认失败比值

使用 V14 physical witness NPZ，SHA256：

```text
ecb2fecc6cd4b7cca29b1378c757fad7df6dd3da51e3d442995d0de8e3507adc
```

原目录和各 JSON/hash 见 [V14 reference record](outcomes/records/review_v14_reference_and_assembly.json)。先验证现存数组身份，列齐旧 strict/inexact 和 V15 所需全部字段。不能从 compact 缺失项补造数组。

允许在本轮内完成固定物理下的数值稳定实现：按 curl、material_mass、DtN、twist 和内/trace 行分解 action；有需要时仅对 startup 保存原 sector solution 与 lift→extract 后状态，定位传输/恢复影响。已有 `FullspaceSplitVolumeAction.component_actions` 可复用。

保存材料不足时，允许**一个必要的无四 q 数值分解的真实 operator/保存场 replay**，只重建上述比较必需的原生作用与几何，不做另一个新 PDE，不重复建立所有因子后才收集同一个失败载荷。其内存、JIT、时间和 source 仍计账。

如果发现明确算术问题，可采用有界补偿/成对累加、等价但更稳定的局部变换等修复。高精度只作为局部诊断时，要读回实际 mantissa；把 complex128 数据转成高精度不恢复已丢失的积分精度。不能预先宣布补偿求和一定修好本问题；有关方法的适用性须由实际误差定位判断。[Higham 的原始研究](https://nhigham.com/wp-content/uploads/2023/10/high93s.pdf)。

**诊断服务于本轮求解，不要求先证明全部误差均为 roundoff 才能评估 V15 PC 合同。**只要独立原方程与完整预算满足新合同，参考近似可以合法用于 FGMRES；若真实物理、映射或恢复错误则必须修复，不能借预算绕过。

### 5.2 新合同一次接通真实执行链

复用一个明确、参数化的 case/strategy registry，覆盖：

```text
src/io/input_schema.py
src/io/input_validation.py
src/io/physical_intermediate_profile.py
src/geometry/task40_nonseparable_plan.py
src/solvers/task40_v10_p6_periodic_profile.py
src/solvers/augmented_reference_correction.py
scripts/run_case.py
src/runners/task038_launcher.py
src/runners/task038_full3d_iterative.py
src/runners/task40_v10_worker.py
parent / independent checker / manifest routing
```

文件列表是影响审计入口，不要求全部文件都改。数值预算和候选选择进入可复用 `src/solvers`；runner 只编排和取原始数据。避免复制新的巨型 worker。

必须修正新增 case 会落入 `else: gx784` 的标签兜底；未知 case 拒绝，E1 精确识别。旧 dat/旧策略不覆盖；新 run/source/profile 身份显式。继续使用已验证的 `LEGACY_GLOBAL_CSR_SUM`，本轮不同时追逐预分配候选或修改 MUMPS 参数。

测试采用一批针对性正负例：

- 近零扇区绝对误差在新预算可接受，但旧 ratio 仍记录 FAIL；把该误差放大，新预算必须拒绝。
- 两个较大 local residual 抵消导致 global residual 小，非抵消预算仍必须拒绝。
- q 矩阵被扰动而独立 native 不变，实际输出残差超标时必须拒绝。
- 非零 all-mode g 的 H/sqrt(2)/符号错配、遗漏模式/q、错误伴随、NaN/Inf 必须拒绝。
- 初次合格、修正变差或修正失败时只允许返回合法完整状态；不吞结构异常。
- 正式 CLI→dispatcher→worker→startup→PC apply→parent/checker 的新合法 tuple 通过，旧策略语义不变，未知策略/错误物理仍拒绝。
- 在同一失败载荷上检查全部下游指标，不只检查触发的第一个 if。

### 5.3 顺手消除一个真实规模风险

[四 q MUMPS 入口](../../src/solvers/task40_v10_p6_mumps.py)在把 CSR indptr/indices cast 为 PETSc.IntType 前，必须统一检查 rows、columns、NNZ、indptr 单调/末值、indices 范围和目标整数上限。当前 legacy 与预分配路线检查不一致，不能在大 NNZ 时先截断再提交后端。

这是小范围可复用正确性修复；用小数组和边界元数据测试，不生成巨型矩阵。它不授权升级本机 ABI 或安装 int64 栈。PETSc 整数宽度需由实际配置确认，[官方 PetscInt 说明](https://petsc.org/release/manualpages/Sys/PetscInt/)。

## 6. 本轮连续里程碑

| 顺序 | 动作 | 必须形成的实质结果 |
|---|---|---|
| P0 | 核对 source/进程/固定窗口；复用旧 Gx/E1/E2 与 V14 失败包；补 route/epoch 区分 | 已有结果不清零；需要重跑的理由明确 |
| P1 | V15 预算、候选选择、失败载荷检查、正式路由与 CSR 安全转换 | 全准入链可运行，定向正负例通过；不是只新增 helper |
| P2 | B0 最小真实新策略锚 | oblique phi=5°、80 cells、532 modes、四 q，全 RHS 与完整 target/输出；已有适用证据可按影响复用 |
| P3 | Gx560 完整新 PC 求解 | 原真实缺口、560 cells、340 modes；同进程从合格 startup 直接接 target FGMRES；完整场/功率/旧 p6 场比较/成本 |
| P4 | 条件 E1 新 PC | Gx560 合格且 E1 资源安全后，固定 0.7 nm、几何×1.25、760 cells、588 retained modes，完成同离散旧 p6 场对照与完整成本 |
| P5 | 目标与下一阶段准入 | 基于新实测和已有 E2 保存场，说明单一主瓶颈、E2/Y方向资格与原尺寸资源/精度缺口，交 response_v15 |

这里“Gx560 合格”指新 PC 准入、真实 A6/恢复/物理与资源门通过。仅因旧参考数组确实缺失而为 AUTHORITY_LIMITED，不单独阻止 E1，也不重跑旧 p4；若存在可比数组且实际场差超门，则保留该真实冲突、定位并处理，不能标为“数组缺失”绕过。

**Gx784 不再是 E1 的机械前置条件。**已有 x 一致性证据继续使用。只有新核的必要回归、E1 不准入但 Gx784 安全，或明确的成本校准需要时，选择 Gx784 替代一个增长运行；不能把它无条件加到所有 case 之前。

正常 fresh 数量由缺失/失效里程碑决定，通常为 B0、Gx560、E1，最多三场，不是每轮固定重跑配额。无四 q factor 的必要保存场 replay 单独分类；有实际代码/机制修复的受影响重放单列原因和成本，不靠改 run_id 重复原样 heavy。

新策略第一次真实资格不能只引用旧 B0：若尚无满足 V15 的 real startup/PC 证据，必须用必要 B0 锚验证；以后字段或可选输出修复不再自动重跑该锚。合格参考因子在同进程中继续供 target 使用，不为“阶段完成”销毁后等审阅。

E2 本轮复用已有 p6 保存场/恢复记录并准备下一输入与资源准入，不新增 E2 heavy。P3/P4 完成后有余量，可完成下面的热点定位和可复用的小型工程修复；不在同轮再开新的求解算法或最大尺寸计算。

## 7. E1 的具体冻结与安全准入

原 E1 输入 `input/task40extra_0p7nm_engineering/nonseparable_e1_p6_q4_manual_m2_growth.dat` 保留。新输入建议为 `input/task40extra_0p7nm_engineering/nonseparable_e1_p6_reference_v15.dat`；这是**待 Codex 创建**的明确入口，当前不声称已经可执行。

新 B0/Gx560 也采用显式 V15 run/strategy 身份。所有正式计算仍经：

```bash
python scripts/run_case.py input/path/to/one_case.dat
```

E1 保留原解析轴、0.7 nm 材料、1° grazing/phi=0、s 入射、非可分缺口、全部 588 ordered modes。reference 可以使用原规则背景，target 和 RHS 不填平、不平均化。

| E1 库存 | 原始实测或计数推导 | 本轮要求 |
|---|---:|---|
| global full / independent rows | 514710 / 495360 | 前者有历史实测；新运行全部 runtime 核验 |
| global interior / active trace | 342000 / 153360 | 全部内部行与实际 trace 参与 |
| local full / independent rows | 264282 / 247680 | 新 p6 reference profile 的派生期望 |
| local interior / trace | 171000 / 76680 | 实际构建回读，不假称已测 |
| q port counts | 84 / 168 / 168 / 168 | 按原完整 588-mode 清单派生并独立核验 |
| augmented q rows | 38424 / 38508 / 38508 / 38508 | 实际 Basix/dofmap/模式确认后才准入 |

E1 的模式比 Gx784 更多，不能由 `760<784` 宣布更省内存。先检查当前可用内存和完整前缀库存，在监督下装配及逐 q symbolic；只有全部因子、numeric workspace、Krylov、恢复/输出余量安全才执行 numeric/solve。旧 p4 的 10.65 GB RSS 不给新 PC 授予资源资格。

旧 E1 场本机 hash/dofmap/相位桥齐备时直接比较，不重跑旧 p4。新 run 因 solver/profile 变化具有新 input SHA；必须同时记录原输入、变化字段和规范化 physical identity，不能强求两个完整 dat byte-equal，也不能据“都是 E1”跳过物理比较。

## 8. 结果、精度与性能 Gate

### 8.1 每个完整 target

- 零初值，FGMRES restart=32、max_it=2048，MPI1/数学线程1、complex128；现有 MUMPS 排序/主元/OOC/BLR 不扫描。
- 保留每 8 步原 A6、每 32 步完整解 checkpoint；终态与释放后原 A6 <=1e-6，target identity <=1e-10。
- 记录真实 target retained residual 与完整 A6 各自尺度，不互换。
- 完整 finite E/H、散射 E/H、curl、全部 ordered 复模式与功率、R/T/A_balance/A_volume、材料区域吸收和衍射级。
- R+T+A_volume−1、A_balance−A_volume 绝对值 <=1e-5；通道求和与原专用物理门全部满足。
- 采用已有 release_before_recovery 生命周期思想，保留必要的 pre-release 全场恢复与 full-A6 检查；随后及时释放参考 PC/factor/无用矩阵，实测确认内存下降，保留最小恢复与核验对象，再执行正式输出。避免 pre/post 大数组不必要同存；不把“一切恢复都必须延后”引入为新的架构重写前置门，释放后原方程检查保持。

同离散新旧 p6 场沿已有更严格专用门；共同默认要求 FE L2/scaled-curl、同坐标 E/H、显著复模式相对差 <=1e-4，R/T/A/A_volume 绝对差 <=1e-5，逐模式功率绝对差 <=1e-6。近零模式并列绝对差；不拟合全局相位；global-z 与 boundary-plane 必须通过已验证的坐标/相位转换。缺少旧 raw 只记 `AUTHORITY_LIMITED`，不抹掉新场的真实 residual/physics PASS，也不擅自重跑旧 PDE。

E1/E2 不继承 Gx 的 h 或通道精度；同离散一致也不等于连续精度。

### 8.2 完整成本，而不是少量 MatSolve 或 outer 步数

V14 已测：

| 阶段 | 时间 | 解释 |
|---|---:|---|
| 两 sector q 装配 | 444.9667 s | 局部贡献、投影、稀疏累加父阶段 |
| 其中 sparse accumulation | 293.5454 s | 约占装配 66%；不是全部 workflow |
| 四 q setup / numeric | 30.4288 / 18.4832 s | numeric 约占 workflow 前缀 0.83% |
| 停止前 workflow | 2220.8270 s | 已长于旧 Gx560 完整 1925.8629 s |
| policy charge | 2420.1657 s | 保守记账，不能代替 solver 墙钟 |

新路线可能随着电尺寸增长获得收益，但目前没有完整速度优势证据。下次必要运行中补齐不重叠的父阶段计时：

```text
mesh/MPC/JIT
target/reference/local operators and carriers
q assembly and temporary storage
all-q symbolic/numeric/probes
startup qualification and I/O
target KSP: native action, PC, checks, orthogonalization
factor release
recovery/output/independent checks
entire supervised workflow
```

原始父计时与子计时分列，不能重复相加；未知差额保持 unallocated，不从 2221 s 减几个子项后命名为某个热点。每个 PC 的 native/sector action、预算、全部 4 或 8 次 MatSolve 和保存成本都必须计入；没有纯 MatSolve 计时就明确 unknown。

至少报告 Gx560 和条件 E1 的：完整秒数、全部因子同时 live 内存、树/cgroup 峰值、task swap、outer 步数、所有 PC 调用与修正次数、PC 完整秒数、每次有效残差降低的成本。跨历史版本比较说明环境/检查范围；不能包装成严格受控速度比。

只有实测完整成本有收益，或有清楚的增长趋势与资源依据，才称新路线带来工程优势。若仅 outer 变少而总时间变长，完整 PDE PASS 仍保留，下一候选聚焦实测最大对象；不再继续同一小模型的 PC 名称/参数试验。

## 9. 从这些结果到 2 TB / 48 h：还要关闭哪些问题

### 9.1 先得到精度合格的目标离散

现有 `272×4×14=15232 cells` 是计数候选，不能直接作为最终准确网格；原尺寸 mode inventory 的 `32060` 是传播模式清单实测，不是完整倏逝截断资格。

但也不能只凭 k0*h_z 很大就否定网格。1° grazing、phi=0 的入射主要沿 x：真空入射 kx≈8.97461、ky=0、|kz|≈0.156652 nm^-1，名义 hz=10 nm 的入射 z 相位约 1.57 rad。另一方面 |n|=35 的外部 y 模式在名义 hy=6.25 nm 上可有约 54.98 rad 相位变化。后者不表示每个高阶模式都显著；二者共同说明精度应由方向、实际散射谱和近场决定，不能只看自由空间 k0h 或入射场。

下一资源包必须以精确轴/界面、总场及散射场 E/H/curl、显著复模式/全部功率和有针对性的 y/z/p 误差证据为依据。保持解析几何；不能只精化 x 就声称任意三维精度。没有 y/z 资格的目标容量填写 `DISCRETIZATION_UNQUALIFIED`。

### 9.2 现有源码不是改一个 dat 就能上目标规模

本轮源码审阅确认：

| 对象 | 当前事实 | 面向目标的要求 |
|---|---|---|
| 四 q 分解 | 当前 p6 实现锁定 Ny=4、local Ny=2 | y 细化需要显式更一般 orbit/映射资格，不能静默增加 Ny |
| 并行与索引 | 当前实现要求 MPI1、PETSc int32，使用全局 NumPy vectors | 单节点分布、int64/MPI ABI 须有专门资格与实际资源收益 |
| reference Hhat | `iter_reduced_contributions` 仍调用 `_materialize_Hhat()` | compact target action 不代表 reference 装配没有 mode² 临时库存 |
| DtN 端口耦合 | 仍有每 mode 的 rows/values、carrier/cache 和投影对象 | 逐对象/生命周期统计，不能因叫 matrix-free 就记零 |
| q CSR / factor | 原尺寸实际 NNZ、indptr、fill、全部 q workspace 未测 | symbolic、索引、安全容量逐级准入，不用单个最大 q 代总和 |

原账本的 Krylov 约 3.70 GB、scratch 约 4.43 GB、一个 32060² complex128 稠密 H 约 16.45 GB 仅是派生 payload，既不是同时 RSS，也不能单凭这些数字判定 2 TB 可行或不可行。精度导致 Ny/Nz/通道增长后，全部 q 因子、C/D/投影、Hhat 和恢复可能重新改变主导项。

### 9.3 本轮后续优先级

先用 Gx560/E1 的真实完整结果选主导对象：

- 若 setup 主导，优先消除最大一项重复构建/全 CSR 累加或端口物化；不为 B0 仅 6.37 s 的预分配收益再阻断求解。
- 若 PC 每次检查/传输主导，先复用同一次原生动作与有界数组；维持本轮合同和独立性，不把必要验证悄悄移出时间账。
- 若 q 因子增长主导，后续才考虑 q 内有界/多层求解；不恢复已失败的低内存高精度全局 p4 逆。
- 若真实三维差异导致 outer 增长，才为同一 target 引入更强全局纠错；不缩小缺口或增大损耗。
- y/z 资格和 general-Ny 能力必须作为单独未关闭 blocker 写清，不能让强参考 PC 的小迭代数替代它们。

dot 的 p4 Ny6/K3/六 q 校准及 K 相关归一化修复可作为后续迁移线索；不是主线 p6、任意 Ny 或目标资格。dot 的原尺寸边界完整 882-row 选定模式路线可参考；84-row 压缩未资格化，不能恢复为加速结论。相关证据固定于 [dot V15](https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/response_v15.md)，本轮不操作 dot。

## 10. 自主修复、资源与窗口

本轮明确授权的不仅是“已知 NameError 可修”，还包括 §4–5 的数值稳定实现、前瞻 PC 合同和固定失败载荷检查。执行者在这些范围内定位、实现、定向验证并继续，不逐阶段等待 ChatGPT。

| 事件 | 执行动作 |
|---|---|
| 路径、参数、schema、标签、序列化、计数、可选图等常规 bug | 最小修复、targeted rerun、按影响重用既有场后继续 |
| 新 PC 预算或数值稳定实现有具体修复 | 按本 review 数学范围修复；主控冻结新 source 后重放受影响项，不重新开整轮审批 |
| 旧 exact-reference 门失败，新 V15 合同完整通过 | 同时保留旧 FAIL 与新 PC 资格，继续 target；不是临场放宽旧门 |
| 新预算在允许 correction 后仍失败，或 target 终态/max_it 耗尽未达标 | 保存全部指标，定位是否有具体实现原因；无实际修复不原样 heavy 重跑 |
| 输出/checker bug，合格完整场已经保存 | 修复并从保存场恢复，不重新求解 PDE |
| 错误材料/模式/布局、NaN/Inf、因子损坏、swap、OOM 风险或失联 | 停止受影响运行并清理完整进程树；保留真实负结果 |
| E1 资源不准入 | 不抬 cap、删 q/模式或改物理；保留 Gx560 结果，完成目标包和条件 Gx784/后续准入 |
| 一阶段正常完成且下阶段已授权可行 | 连续执行；阶段收据不是新的停审点 |

每 8 步的中间 A6 大于 1e-6 是正常未收敛状态，不是自动停止事件；继续到真正收敛、max_it=2048、明确的结构错误或真实安全停止。不要把中间监测门误写为终态验收门。

保持本机 **16 GiB 与实际动态准入较小值**、系统余量、task zero-swap、快速 RSS、PID/start_ticks 身份、独立 watchdog、完整后代清理。PSS 未采写 null；tree/cgroup/backend allocation 各自标明，不能相加或互相替代。

若原 V13/V14 固定窗口仍有效，V15 沿用原 T0/deadline/账本。已归档 T0 为 2026-10-06T23:21:33.326800586Z，deadline 为 2026-10-07T23:21:33.326800586Z；主控以本机实时记录核对，不把旧 “remaining” 数字当现在余量。若原窗口已经真实终态或自然结束且里程碑未完成，先保留 terminal receipt，再启用本 review 授权的**一个**最长 24 h 补完窗口，收口预留 600 s；不重叠、不反复刷新、不清零旧费用。

开发窗口、单场 PDE 墙钟、campaign charge 和最终 48 h 生产目标必须分列。旧已知费用与 unknown 不清零；不能把历史诊断搬到账外制造速度收益。正常计算不能因为短外层 timeout、无输出或阶段结束而被重启；先检查进程树、CPU、日志和真实资源。

## 11. 提交和证据要求

主控在同一执行分支完成三类小型提交：

1. 新合同/稳定实现/入口与 CSR 安全修复及必要 tests；
2. B0/Gx560/E1 的冻结输入和实际完整结果；
3. summary、response、模型总账、完整成本与目标 readiness。

实际 commit 顺序可按源码冻结需要细分；运行时 source 必须已冻结且身份清楚。无 amend、强推、master merge、其他分支写入。执行者不 commit/push。

不要增加一大套互相覆盖的说明书。优先以下紧凑证据，并更新原 run_index/summary/test_summary、README 当前入口、development_progress 和 development_model_registry：

```text
response_v15.md
outcomes/records/review_v15_native_pc_contract.json
outcomes/records/review_v15_failure_witness_and_repairs.json
outcomes/records/review_v15_formal_results.json
outcomes/records/review_v15_cost_and_readiness.json
outcomes/records/run_index.json
outcomes/summary.md
outcomes/test_summary.md
```

每份实际运行绑定：branch/base/source、环境/ABI、MPI/线程、原 dat、resolved config、input/physical/mode/mesh/field hash、命令、watchdog、全程资源、所有 residual/physics、初次/修正/selected 完整状态和 checker。保存原始值后由 checker 重算结论，不能只读取 status。

大矩阵、场、NPZ、timeline 和缓存仍在 ignored artifact 中，Git 仅放 compact、hash 和路径。保留原失败材料不可覆盖规则。采用 GitHub math fenced blocks、完整表格；本报告只新增文档，不把审阅端的静态检查写成本机 FE/CI 通过。

## 12. V15 验收与发给 Codex 的执行要点

本轮成功的主要问题是：

1. Gx560 是否在新参考 PC 下得到完整真实 p6 target 解，并与旧 p6 场相符？
2. E1 是否完成新 PC 的同离散电尺寸对照；若未运行，真正的数值/资源阻塞是什么？
3. 新 PC 的所有 native 检查、预算和修正计入之后，完整耗时、内存和增长趋势是否有实际收益？
4. 目标精度/一般 Ny/端口与索引还缺什么，下一唯一工程改动消除哪个 blocker？

测试数、文档数、修复数量、startup PASS 数均不能替代这四个回答。出现不能安全克服的真实 blocker 时，交付完整负结果与已完成独立工作，不虚构成功；常规 bug、历史导航或已被本 review 明确解决的合同冲突不能成为整轮停审理由。

可交给既有主控/执行协作的指令：

> 在现有 Task40 canonical worktree 和 task40extra_0p7nm_engineering 分支读取 Review V15。先核对活跃进程、HEAD、工作树、固定窗口与 V14 失败包；没有活跃旧运行时由主控 fast-forward 同分支 review。按 P0–P5 连续执行，不每阶段等主审。实现显式 NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15：保留旧 exact-reference 失败，按独立原生增广 FE 残差、alpha、全部 q 和含 B delta-alpha 的非抵消预算判断近似 PC，真实 target 原 A6/物理门不变。一次检查完整失败载荷和真实入口，必要 B0 后同进程完成 Gx560；通过且资源安全直接进入原 760-cell/588-mode E1 新 PC 对照，不把 Gx784 作为机械前置门。旧 p6 target+p4 correction 的 Gx/E1/E2 场按身份复用，不重跑旧 p4，也不研究低内存 p4 逆。全部检查成本计入实测；常规 bug 和本 review 范围内数值实现问题自行定位修复，输出问题从保存场恢复。执行者不提交，主控冻结源码并集中提交/推送；交 response_v15、统一结果/成本和目标未关闭项。保持本机资源门、零 swap，不操作工作站、dot、其他项目或 master。

## 13. 审阅证据边界

本报告依据远端固定 SHA 的源码、实际 compact records 及其原始字段索引形成。审阅端没有重新运行 FE/PDE，也没有取得或重放本机 ignored 科学数组；没有将 V14 控制端的 NPZ 重算说成审阅端实测。传输/舍入等根因目前仍是待检验解释；V15 新预算尚未计算、尚未授予通过。

公开资料只支持通用数值与 API 语义，不替代本机 ABI 或工程实测：PETSc FGMRES、PetscInt，以及 Higham 关于浮点求和的原始论文。推导的非抵消预算来自本报告明确写出的原增广方程与三角不等式；它的实际实现和每次调用资格必须由新证据验证。
