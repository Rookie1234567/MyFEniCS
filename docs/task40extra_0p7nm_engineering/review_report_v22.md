# Task40extra Review V22：接通原尺寸生产端口，启动有界算子实测

## 0. 审阅结论与本轮行动

**V21 接收为 `PASS_WITH_QUALIFICATIONS`：真实原尺寸边界映射和缺省零块消除有价值；“原尺寸端口库存完成”只能指几何映射，生产 support、全边界作用、端到端内存收益仍为 `PARTIAL`。目标 0.7 nm、2 TB、48 h 仍为 `NOT_QUALIFIED`。下一轮主线是把已做出的生成式端口接到实际生产链，并在本机资源准入后测原尺寸算子。**

这里的端口是上下开放边界上的出射、反射和透射模式；Bα 把模式振幅变成有限元方程中的边界作用，Dx 把有限元场投影到模式。生成式端口在使用时分批计算这些耦合，减少永久保存的大数组，代价是每次作用可能增加计算。V21 验证了局部机制；V22 必须测到实际全边界的内存和时间，才能判断它是否帮助 48 h 目标。[V21 回应][S2]、[生成实现][S9]

本轮继续既有 p6 reference 数学路线及 `ROW_TILE_BOUNDED_CSR_V17 + ONE_Q_REFACTOR_V19`，不研发另一个预条件器。预条件器是帮助迭代更快接近解的辅助计算；迭代次数减少，不会自动降低矩阵、因子、端口或工作向量的峰值内存。下一轮的成功指标应同时包括**实际存储生命周期、完整作用时间、与原方程的一致性**。[既有裁决][S1]

| V22 决策 | 具体要求 |
|---|---|
| 主要交付 | 真实 geometry/mode/FE/MPC descriptor → 生成式 B/D → 原生残差及凝聚接口 → 有界 q 贡献块的生产链 |
| 主要实测 | 新增显式 opt-in `target_operator_probe`；准入后建立原尺寸 p6 空间、Floquet MPC 和少量工作向量，测全边界 Bα、Dx；相关资格齐备再测凝聚、RHS、恢复与原算子恒等式 |
| 资源不足时的独立进展 | 复用已保存网格和 54 个实际边界类，完成有界 native/模式扫描、方向资格和成本证据；保留其不是全局生产 support 的边界 |
| 普通问题处理 | 一次集中修好已定位的 residual、MPC、normalization、support、receipt 和窗口接线；最小相关复测后继续，不逐个问题停审 |
| 小模型/E2 | V19 小模型最低退出条件继续有效；本轮不默认重跑 B0、E1 或 E2 全场，不增加 E3/Ny16 |
| 时间合同 | 本次用户继续推进请求授权一个**新的、独立的 6 h V22 工作包**；这是审阅规定的工作上限，不是把最终 48 h 目标改成 6 h。旧 V19 窗口、历史费用和 unknown 原样保留 |
| 执行边界 | 现有本机、canonical worktree、同一分支；本轮不建全部目标 q CSR、不做目标全局 numeric factor/KSP/full field，不 SSH 或切工作站 |

**不要将 top 局部 forward 负结果、旧 E2 cleanup unknown 或旧窗口到期变成全部后续工作的共同 blocker。** B/D、几何和库存工作按其自身资格继续；需要局部求解的凝聚/恢复按相应门限推进。各项进度与依赖分别记录。

## 1. 审阅身份、资料与证据可信度

| 项目 | 身份 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 本次审阅 base HEAD | `6490389b2e6b7f9a4d47269e50acb93d61dc4c41` |
| base 日期 / 说明 | `2026-10-10T01:42:05Z` / `Task40 V21: close out complete boundary mapping and audited provenance` |
| 上轮 Review V21 提交 | `75273597809d2876f091a222b678f3af6756725c` |
| V21 主要实现提交 | `b91050bbe474123afd0e92b785c66f842b7f6bb7` |
| 映射 helper 源码冻结 | `ba897281f3b8ed227f73e645dc60b7210f46db73` |
| 本机执行目录 | `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` |
| 审阅日期 | 2026-10-10 UTC |

从 Review V21 到本次 base 为 4 个提交、20 个变更文件。本次读取 V21 response、三份 compact JSON、run index、summary/test summary，以及实际凝聚、native port、fullspace、worker、q 装配、MUMPS、stage runner、service、checker 和映射实现。结论依据冻结源码和保存结果，不把 response 中的完成措辞当作独立运行证明。[S2]、[S3]、[S4]、[S5]、[S6]

独立按远程原始 UTF-8 内容核验 17 个文件的 SHA-256，16 项与顶层索引一致。唯一差异是 `src/test/test_task40_v21_readonly_recheck.py` 的旧索引 SHA；当前文件与最新 targeted-test receipt 及 post-whitespace rerun 的 SHA 一致。它是索引字段未同步，不是发现未测试的数值源码。V22 更新该字段即可，不重跑 PDE。附录列出身份。

V21 最终联合 p6 action/streamed-port 测试为 28 passed / 129.61 s；mapper 为 5 passed / 0.08 s；最终文档合同为 29 passed、134 subtests / 0.23 s。另有 recheck 12 项、authorization route 3 项的定向回执。重复执行的计数不累加成新增覆盖。V21 没有 full repository pytest、MPI4、Ruff、CI 或新 PDE；本次远程 review 也没有代替执行者运行数值实验。[测试记录][S5]、[测试汇总][S7]

## 2. V21 已经取得什么，尚未取得什么

### 2.1 原尺寸边界已经定位，方向资格尚未补齐

目标仍为 50×25×140 nm、0.7 nm、Si/air 三维非可分缺口、既定入射与双 Floquet / Fourier-DtN。Ny8/Nz14 配置是原尺寸资源 pilot，其精度未获最终资格。[目标合同][S22]、[上轮审阅][S1]

| 项目 | V21 结果 | 数据身份与意义 |
|---|---:|---|
| 保存的原尺寸网格 | 30,464 hex cells；272×8×14 | 已有几何实测；V21 只读保存网格 |
| 实际 z-port facet 映射 | 4,352 条 | 每个 facet 恰有一个邻接 cell，并绑定精确 class |
| bottom / top | 各 2,176 facets、2,176 个不同邻接 cells | 全边界几何覆盖 |
| 边界类覆盖 | bottom 28、top 26，合计 54/60 | 只说明这些类出现在端口，不是方向资格新增 54 类 |
| 生产方向资格 | 仍 17/60 | 其余 43 类未资格化，不能统一判为数值失败 |
| ordered modes | 32,060；每侧 16,030 | manifest 已固定；不说明每个模式在每个单元上的实际 support |
| 全局 p6 / MPC / carrier | 均未创建 | 尚无实际全局自由度归并与生产 support |
| q CSR / factor / target field | 未创建 / 未运行 | 不授予目标求解资格 |

映射 artifact SHA-256 为 `e5a38b003e3d061b04934a3158346a21448b6b2c6f884749c0182380676c3320`，规范 mapping digest 为 `164e1bf13f08beafc933528ace76315416e4be37bf10b97a03629cca53ab74b6`。geometry JSON 为 `491dac32b7e3ba927ce44444f834ff1e27406c3dfe95a9438fac8cae45adce34`；HDF5 为 2,839,728 B，SHA-256 `0bcc83dea1fb912a88612732f088467b7cb2fd2e152e19370d98342709be1dba`。[库存][S3]

后端 1,047 ms 是整条 readback 命令的工具计时，纯读回与完整准备 wall time 未知。reader PID、CPU、process-tree RSS、cgroup peak、任务 swap 均未知。PID 2179667 是只读 campaign API 观察者，不是 reader；进程名筛选没有匹配项也不能证明历史 detached descendants 已清场。此前“约 5.8 s”没有回执支持，不再用于速度论证。[S2]、[S3]

### 2.2 缺省零块消除正确，但本次只测到很小的逻辑节省

`None` 现在继续表示明确缺省的零块，不再创建稠密 Bt/Dt/Hlocal 零数组。实际非零 Hlocal 的 legacy/research 检查保留；Bhat、Dhat、端口 Schur 修正和非零 RHS 语义不能随之省略。[凝聚实现][S8]

| 同一保存局部单模式数据 | 旧显式零 | 新 None | 结论 |
|---|---:|---:|---|
| 每侧 raw logical payload | 28,240 B | 14,400 B | 每侧减少 13,840 B |
| 两侧总逻辑节省 | — | 27,680 B | 不是全目标峰值节省 |
| action / RHS / recovery / full B / full D 差 | — | 全部 0 | 该局部表示等价 |
| RSS / cgroup 节省 | 无独立同口径对照 | 无可归因证据 | 不声称内存峰值下降 |

两侧对照顺序运行在同一进程，VmHWM 含此前历史；共享 cgroup 的 14,030,671,872 B peak 和 145,637,376 B swap current 不能归因本次任务。它们既不能证明此次省了内存，也不能证明此次任务 swap 为零或违反 zero-swap。[S3]

### 2.3 生成式动作只验证了两个模式，有一个局部 forward 超限

两份见证分别是 top/bottom 的 `(-142,-5,s)`，对应 full-order index 0 和 16,030；每个局部块 882 行，其中 interior 450、trace 432，只用了 identity local mapping。实际 witness 的目标 cell/facet/class ID 仍为 UNKNOWN，不能把几何表中示例 cell/facet 自动认作它。[S3]

| 指标 | bottom | top | 正确解释 |
|---|---:|---:|---|
| 已知状态 interior forward 相对误差 | 9.173378724262687e-12 | 1.488391772882517e-11 | 门限 1e-11；bottom PASS，top 保留 controlled negative |
| dense Schur reduced-action 对照 | 8.403467657525055e-24 | 7.881403676908346e-25 | 局部代数对照 |
| dense Schur reduced-RHS 对照 | 2.402222099692621e-13 | 2.2722526003307062e-13 | 不是全局求解残差 |
| dense full-vector recovery 对照 | 1.3184435811031027e-11 | 8.827070070530074e-12 | 不能把 interior-only forward 门限直接套在不同范数上 |
| 新 generated 模式覆盖 | 1/16,030 | 1/16,030 | 总计 2/32,060，不是全模式资格 |

回执里的 generated-versus-native B/D 来自同一生成方法；自造 RHS 也使用候选 B/D，因而主要证明自洽。新 callback 尚未直接对照保存的独立全 882 行 native 积分。保存数组名中的 `q30` 是历史键名，实际 V20 `PORT_QUADRATURE_DEGREE=60`，应读回 JSON 的实际积分规则，不能再称“本次 degree-30 资格”。[局部生成][S9]、[独立积分保存代码][S10]

## 3. 影响最终 2 TB / 48 h 的核心判断

### 3.1 删除零数组后，完整缓存仍可能超过预算

如果全部 4,352 个边界邻接 cell 都关联本侧 16,030 个模式，则有 69,762,560 个 cell-mode 关联、1,118,293,836,800 个局部模式平方项。这是**条件场景**，不是实测 support 或必需内存下界。[S3]

| 条件库存项 | complex128 字节数 | V21 零块优化后的状态 |
|---|---:|---|
| Bi + Di | 1,004,580,864,000 | 仍需表示或按需计算 |
| 缺省 Bt + Dt 零块 | 964,397,629,440 | 可移除 |
| XiB + Bhat + Dhat | 1,466,688,061,440 | cached 路径仍存在 |
| 缺省 Hlocal 零块 | 17,892,701,388,800 | 可移除 |
| 删除零块后的上述非零/派生缓存合计 | **2,471,268,925,440** | 约 2.471 TB；尚不含 carrier、q、因子、向量、系统余量 |

这说明**只做 None 优化不足以支撑最终预算，应继续接通按需生成和有界贡献块**；它不证明真实目标必然需要 2.471 TB，更不证明 2 TB 目标不可能。实际 m_c 应由生产 support 的真实行归并和筛选得到。

### 3.2 全局算子测试比全 q 装配轻，应该有独立入口

当前 Ny8 profile 给出的计划规模如下；全局 FE/MPC 尚未建立，因此本表均为源码派生值。[profile][S18]

| 计划项 | 数值 | 用途 |
|---|---:|---|
| 原始 p6 storage rows | 20,181,348 | 全局原生向量长度 |
| independent FE rows | 19,897,344 | 周期约束后计划行数 |
| interior / trace rows | 13,708,800 / 6,188,544 | 局部恢复与外层量 |
| q_count | 8 | 不能沿用 E2 的 4-q checker 常量 |
| 一份全 FE complex128 向量 | 322,901,568 B | 约 0.323 GB |
| 一份 trace+port 向量 | 99,529,664 B | 6,188,544 trace + 32,060 ports |
| FGMRES32 的 65 份主要向量 | 6,469,428,160 B | 约 6.469 GB；operator probe 无需创建 |
| 16 份全 FE 向量 | 5,166,425,088 B | 局部 batch=16 不能直接变成 16 个全局向量 |
| 两个切向分量各 16 份全 FE 向量 | 10,332,850,176 B | 未计 FE/MPC/runtime 已很大 |

表中的 65 份仅是 FGMRES32 主要基向量的派生示例，不是现有 gate 的完整向量预算；MUMPS `_static_future_reserve` 采用的 72 份（66+6）及其用途沿原实现核算，不能用 65 份示例调低 reserve。[S15]

因此新增 `target_operator_probe`，使用一个或少数全局向量、紧凑边界行累加器和有界局部模式 tile。必须以实际 FE/MPC/临时对象库存和当前 cap 准入，不能用“一份向量很小”保证整个阶段可容纳；也不能用 176,839,493,968 B 的全部目标 q CSR 结构上界拒绝根本不建 q CSR 的算子阶段。[S1]、[S18]

### 3.3 48 h 必须由实际单次成本和重复次数共同决定

```math
T_{\rm field}
=
T_{\rm prepare/JIT}
+T_{\rm build/setup}
+T_{\rm Krylov/PC}
+T_{\rm recover/output}
+T_{\rm checker}
\le 172800\ {\rm s}.
```

```math
M_{\rm task,peak}
=
\max_t\left(
M_{\rm mesh/FE/MPC}
+M_{\rm local/ports}
+M_{\rm q/conversion/factors}
+M_{\rm vectors/output/runtime}
\right)(t).
```

任务峰值与同一时点 OS/其他占用余量之和须不超过 **2,000,000,000,000 B**，任务 swap=0。矩阵库存、RSS、后端 allocated/used、共享 cgroup 历史峰值分别记录，不能互相替代。[资源合同][S22]

V22 应提供首次与后续 Bα/Dx/凝聚作用耗时、独立核验耗时、重复生成和类缓存复用成本。将来取得目标单次 PC、完整迭代和实际 numeric cache-miss 次数后，再用扣除固定开销的时间预算推导允许的迭代次数。小例的少步数不能预先代入原尺寸；删除缓存后的“省内存、反复生成很慢”也必须暴露。现有证据还不能作出 48 h 可行/不可行的可靠定量裁决。


## 4. 把生成式端口接到生产链：本轮必须解决的具体断点

### 4.1 首先建立真实 descriptor，不再用单面 helper 冒充工厂

descriptor 是一份轻量、可核验的连接说明：每个实际 facet 属于哪个 cell/class，局部行怎样进入全局自由度，周期约束怎样归并，使用哪份 mode 表和相位约定。它应来自保存几何和实际 FE/MPC，而不是先生成完整 carrier 后再包装成“流式”。[S8]、[S12]、[S20]

当前 `build_p6_cell_condensed_action_from_carrier` 没有 `generated_port_actions` 参数，仍把全部 carrier entries 转为 tuple、建立 interior_locations 与 B/D 字典，再为局部 cell 分配 dense Bi/Di。fullspace builder 还持有 component cache、所有 entries、direct maps 及 staging；`bounded_direct_term_build=True` 只限制部分构建批次，并未消除最终持有的全部端口数据。Task40 target worker 和 y-orbit reference 构造仍走 cached factory。[S8]、[S12]、[S13]、[S14]

V22 将生成式适配接入可复用 `src/`，由薄 runner 调用；target 与 filled-reference/twist 的实际支持范围分别记录。只接通 target 时，不写整个 reference-PC 已有界，并把仍存活的 cached reference 内存计入总账。不要为 4,352 个面逐一调用 V21 单面验证包装器：该 helper 会重新计算 solved Vit、恢复、RHS projection/Schur 等；应借用已资格化的类数据并记录共享 backing，避免按 facet 重做 LU 或完整局部缓存。

descriptor 同时列明 canonical preflight input、saved staged input、resolved config、geometry physical-model 与目标 inventory 物理身份的作用域。现有 `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` 与 `a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f` 名称相近但作用域不同，尚无逐字段等价回执。核对波长、尺寸/原点、材料/缺口、入射、BC、p、axes、modes、gauge 后记录映射；**hash 不同本身不证明物理输入错误**。首次误用 canonical 文件被身份门拒绝的历史保留，不需重建几何。[S3]、[S6]

### 4.2 修好 generated native residual 的确定性接口错误

`evaluate_native_residual` 仍直接使用 `cell.Bi @ alpha[cell.ports]` 及 `cell.Di @ solved_error`；generated cell 的 Bi/Di 是零宽占位而 ports 非空，会形成维度不匹配。V21 新测试覆盖了 action/RHS/recovery/full B/D，却未调用此 residual 入口。[S8]、[S21]

修复应复用同一受控的 `_generated_B_action/_generated_D_action`，保持原生完整方程的 residual correction 意义。用既有真实局部 fixture 加一项 generated native-residual 回归，以及一个非零 interior/trace/port RHS 恒等式。比较对象来自独立原生作用或保存的独立数组，不能由候选 callback 同时制造两边。无需新增 PDE、全局 CSR 或因子。

### 4.3 冻结 MPC 的行语义，验证真实非零 slave 贡献

MPC 将周期两侧的自由度按 Floquet 相位对应起来。若 P 把独立量展开为原始 FE 量，则需要一致地处理 P 的展开与共轭转置归并；原始 cell rows 和已归并的 dual rows 不能混用。

当前 generated reduced action 做局部展开/共轭 scatter；`apply_B_full` 只写 active original trace rows，而 `apply_D_full` 在 callback 前把 slave rows 清零。V21 MPC fixture 又事先把 Bt/Dt 的 slave 项设零，因此未覆盖真实非零 slave 耦合。[S8]、[S21]

V22 明确选择并记录接口约定：可以由 descriptor 提供 raw rows、在统一层做 P*B 与 DP，也可提供已归并的 production-dual rows；整个 B/D/full/reduced/residual 路径必须一致。复测使用非平凡复 Floquet phase、非零 slave 行及共享 edge/facet，核实贡献恰好累计一次。B 与 D 按各自定义验证，不额外假设 D=B*。

### 4.4 保持 production 的 raw D + Hp，显式处理 gauge/normalization

新局部生成器的 D 已除以 h，Hp 取 I；生产 fullspace builder 保存 raw D 和原 Hp。两种写法在相同 mode、gauge 和同步 RHS 变换下可等价，但不能直接把两个接口拼接。[S9]、[S12]

```math
\begin{bmatrix}V&B\\-D&H_p\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=
\begin{bmatrix}f\\g\end{bmatrix},
\qquad
\begin{bmatrix}V&B\\-H_p^{-1}D&I\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=
\begin{bmatrix}f\\H_p^{-1}g\end{bmatrix}.
```

```math
A_{\rm native}=V+B H_p^{-1}D.
```

最小改法是让生产 adapter 输出原 raw D，继续使用原 Hp、RHS 与 KSP 停止语义。若在局部检查用归一化写法，同时变换 g、误差和 residual 度量；不能只替换 D。

global-z 与 boundary-plane gauge 之间还含模式相位。优先使用已有 `raw_plane_D_action_from_global_normalized`：先经 `solver_amplitudes_from_global(...BOUNDARY_PLANE)`，再用 original_h；不能只乘一个 h。冻结实际生产调用的 phase gauge。生产采用 boundary-plane 时，B 使用以端口面为中心的稳定指数，并对 global-z 见证做显式桥接；若该调用仍为 global-z，本轮保持其约定，不因接入 callback 静默更换 gauge。保留原非有限值/病态 normalization 防护，避免先生成巨大指数再与其倒数抵消。[S8]

### 4.5 纠正“精确零筛选”理解，复现生产两级相对筛选

**这是生产一致性与真实 support 计数的关键。** 当前 `dtn_port_3d.py` 的 `_vec_nonzero_owned_entries` 默认 `relative_tol=1e-13`：在向量装配、共享行及 MPC 处理后，用全局最大幅值确定阈值，保留严格大于阈值的项。调用中的 `absolute_floor=0.0` 没有关闭相对阈值。`_combine_owned_entries` 在 e/traction 分量合成、排序/归并后再次按全局最大幅值做同类筛选。[S11]、[S12]

```math
|v_i|>\max\left(a_{\rm floor},10^{-13}\max_j|v_j|\right),
\qquad a_{\rm floor}=0\ \text{at the current production call}.
```

因此 V21 response/inventory 的“精确零筛选”描述需要修正。raw 全 882 行 native 资格仍保留 tiny Bi/Di；生产等价性则须复现**既有两级全局筛选及其顺序**，不能逐 cell、facet 或 batch 用局部最大值替代。每个 mode 的 component 合并、MPI reduction、MPC、共享行顺序，以及 B/D 候选键并集的语义，都应能追溯。

实现可采用一个模式的全局工作向量或紧凑全局边界行累加器：完成全局归并、取阈值，按原阶段筛选，再消费/释放或有界重放。不保留所有模式的全局向量；需要两遍时计入时间。改变累计顺序若触发近阈值 support 差异，记录最坏项并定位原因，不放宽或提高阈值来换内存。

记录 raw tiny count/error、每级 dropped count/norm、global maxima、支持行 digest、最终每 cell 的 B/D 并集与 Σm_c、Σm_c²。部分元数据仍写 `absolute_sparse_floor=1e-30`，应校准到真实生产调用，不能反过来按旧标签改变算子。未建立实际 global MPC 的类扫描只输出 local candidate support，不授予 production-exact support。[S3]、[S11]

### 4.6 q 装配必须真正消费有界贡献，不能只接 matvec

q 是现有周期分块中的子问题。其稀疏矩阵仍需端口/凝聚项贡献；只让目标 Bα/Dx 可用，尚不能让既有 q 预条件路径可执行。[S14]

目前 `iter_sparse_matrix_layout_contributions` 与 numeric contribution iterator 要求 cached Bi/Di/Bhat/Dhat，generated 会被拒绝；`C_hat/D_hat` 也需要缓存数组，generated `materialize_Hhat` 未实现。既有 y-orbit row-tile CSR consumer 正在使用这些接口。[S8]、[S14]

V22 提供有界 mode/column tile 的结构和数值贡献，送入已有 `ROW_TILE_BOUNDED_CSR_V17` 后释放；包含 C_hat、D_hat 和真实 Hhat Schur 修正，不能把 Hhat 当零，也不能悄悄回退到全缓存。验证同一真实局部/模式数据的若干实际 q tiles，覆盖跨 mode 耦合、非零 RHS 与原 cached 公式。**本轮只需证明实际贡献接口和有界存储，不要求先建全部目标 q CSR 或做 symbolic。**

同一 kernel/descriptor 可为 Bα/Dx、凝聚和 q tiles 服务，但分别记录调用次数、临时存活量和等价范围。检查 q tiles 的局部参考只在已准入的有界数据上构建，不为测试分配完整目标 carrier。

### 4.7 修正 top forward 时利用已有稳定求解，不改门限

V20 `stream_boundary_correction` 内已有同 LU、最多三次的有界 residual correction；矩阵/解保持 complex128，可在原许可范围用更宽的 residual 累加。新 `build_generated_boundary_side_action` 的 LU 回调以及 split recovery 没有沿用这条稳定处理。[S9]、[S8]

按保存的**同一** top/bottom arrays：

1. 独立记录 RHS 制造、消去和相减的 roundoff，区分已知解问题与求解误差。
2. 比较 combined RHS 一次 solve 和现有分开消元/恢复的差异。
3. 复用既有同因子有界修正，重算原局部方程 1e-10、known-state forward 1e-11、直接 trace carrier 1e-14 等适用门；不把不同范数混用，也不以 q solve 的 1e-8 取代局部门限。
4. 保留 V21 top=1.488391772882517e-11 的负记录，新结果另建 receipt。修复不保证必然通过；未通过只阻止依赖它的资格声明。

独立端口资格优先复用保存的 `20261009T175922.461391Z/v20_port_bottom/top.json/.npz`，其中 `witness_direct_q30_B_native/D_native` 等键保存实际 degree-60 native 见证，连同 rule、coords、orientation、mode/gauge/hash 读回。只在缺必要数组或身份不合时做一次有界原生积分补证，不启动完整小 PDE。[S9]、[S10]

随后将新 adapter 的实际输出接到已有 `verify_analytic_full_rows=True` 独立解析检查；沿 Review V21 的 1e-10 门限，目标为每侧 16,030 keys × 882 原生行，保存已检次数、最坏 key/row、参数、方向和 digest。高精度资格检查不进入每次 production matvec。实际目标方向变换按真实代表类核验，先覆盖所用 54 个边界类，再补其余体类至 60/60；部分结果 checkpoint，不重做同身份已通过数据。[S1]

### 4.8 生成器的“有界”需要真实计数和完整工作区

V21 helper 把 max_batch/max_live_pair 写为 1，但循环中旧 B/D pair 的引用可能在调用下一次生成时仍存活；单模式见证看不见这个重叠。记录的 35,456 B callback workspace 只涵盖命名向量，不含 FacetPolynomial、Basix/native 积分和其他临时对象。[S9]

用既有 multi-mode fixture 修正并观测生成、消费、释放顺序，报告实际最大同时存活 pair、unique backing、完整 workspace 与 process-tree peak。B callback 不应为每次调用完整生成又丢弃 D，D callback 也不应重复同一积分而丢弃 B；可复用有界公共积分中间量或只算所需输出，仍保持左右独立定义。不将完整 mode cache 藏进闭包，也不将单面验证包装器的成本直接乘 4,352 当 production 时间。

## 5. 阶段与资源接口：集中修复，继续主线

### 5.1 V21 footer 尚未与真实 worker 产物完全对齐

V21 增加了 V2 partial receipt，方向正确，但静态检查仍存在如下真实 producer/consumer 断点。[S13]、[S16]、[S17]、[S19]

| 断点 | 当前表现 | V22 最小修复与验证 |
|---|---|---|
| q keys | readonly checker 硬编码 0–3；目标 q_count=8 | 从 hash-bound profile 生成实际 keys；4-q/8-q 完整、缺一项、重复项 fixture |
| one-q inventory | worker 放在 `physical_rhs_stage`；wrapper 只读顶层 | 统一生产 schema，或按版本显式解析，不能用 UNKNOWN 代替已有真实字段 |
| cleanup | worker 在 `v20_stage_result.cleanup`，wrapper 读顶层；内容仅 slot facts | worker finally 写实际 native/temp/factor 生命周期；launcher/watchdog 在退出后写进程树事实；按 run/PID/starttime/cgroup 身份拼接 |
| cleanup 字段含义 | wrapper 期待三个 release 布尔值，worker 未提供 | 不把 factor slot 数改名成 native owners/descendants/temporary 全部释放 |
| failure stage | 请求阶段与提前失败阶段被混同 | 分别写 requested、attempted、completed、actual failure stage；早失败保留真实前缀 |
| target full | stage runner 无条件挡住，service 尚无该 full route | 本轮新 operator_probe 独立可达；未来 full 按运行前/中/后门限实现，不声称改一个 heavy flag 即可 |
| campaign | service 硬编码旧 V19 manifest path/SHA | 按第 7 节显式注册本次 V22 path/hash/scope；保留旧读取规则，不取消校验 |

单元测试应包含真实 worker summary 的结构，不仅是理想化手写成功字典。自身尚未退出的 worker 不能证明未来 descendants 已清场。旧 E2 footer 缺失和 cleanup UNKNOWN 保留；本轮新进程用自己的 launcher/watchdog 获得清理证据，不追写旧记录。

### 5.2 E2 的资源停止成立，不能靠减掉一份仍共存的数组变成通过

V21 从 97,311 条保存事件重算 E2：4 个 q CSR、98,440,612 stored slots、98,334,635 numeric nonzeros、105,977 retained exact-zero slots，总 unique backing 1,969,523,536 B。每 q 内容 hash 未保存；q0 symbolic 尚未开始，numeric/KSP/field/official R/T/A 均 NOT_RUN。旧外层 exit 4、WORKER_FAILED、NO_PARTIAL_FOOTER 保留。[E2 复核][S4]

| q0 原 admission 项 | B |
|---|---:|
| 当时 process-tree RSS | 10,079,617,024 |
| 新 matrix payload | 486,803,844 |
| 同时 conversion workspace | 486,803,844 |
| future co-resident reserve | 2,481,665,040 |
| 固定 headroom | 134,217,728 |
| 投影 / 当时 cap | 13,669,107,480 / 13,519,601,664 |
| 超额 | 149,505,816 |

两份 486,803,844 B 在转换期间确实共存，原 gate 没有依据直接合并它们。可改进的是**按实际生命周期分阶段准入**：转换前覆盖 matrix+conversion+适用余量；完成转换并释放临时对象后，读真实 RSS，再做原 symbolic/numeric guard。native backing 或 allocator 没有释放的页仍算 live。两个 phase gate 均保留原 pending-transform reserve、选定 future co-resident phase reserve 和 fixed headroom；只按经实测确认的生命周期调整 matrix/conversion/symbolic 或 numeric 同存项，不能删掉整项 future reserve。[S15]

MUMPS 文件在 V21 未修改；initial symbolic、post-eviction next-q、numeric cache-miss 三条路都需由同一生命周期 helper 一致处理，保留原 guard 语义、后端/排序/主元/BLR/OOC/线程。仅做算术“减去 conversion”会得到 13,182,303,636 B、margin 337,298,028 B，但这只是条件推导，不是新的 admission 实测或成功结果。

该项用原事件和最小生命周期 fixture 验证；不能为修 footer 或索引默认再花一轮 E2 全场成本。原 E2 父区间 monotonic 5,608.418476 s、UTC 6,232.118781 s、保守预算 6,232.119266 s，只到停止与必要 checker；不是冷完整场时间。V22 首先完成端口主线，再在本包内完成这个有限生命周期修复，不因附属修复未完阻止独立 B/D 工作。[S1]、[S4]


## 6. V22 原尺寸 operator probe：必须产生的实质进展

### 6.1 建立独立可达的阶段，直接测试目标规模对象

新增显式输入/profile（建议 `target_original_ny8_operator_probe_v22.dat`）和 `target_operator_probe` selector/service/receipt 注册。数值核心放 `src/`，现有 `run_case`、activation、ABI 与 watchdog 继续使用；新 runner 仅编排。旧 ordinary default 和原 preflight-only 配置保持原行为，不用全局关闭 heavy gate 的方式取得入口。

**本 review 新授权的本机资源阶段只包含：**保存的原尺寸 geometry 读回、真实 p6 space/dofmap、Floquet MPC、已资格化局部类缓存、少量作用/校验向量、模式/边界分批生成及有界 q 贡献 tiles。用明示 stage scope 区别旧 heavy=false；禁止绕到 `build_and_symbolic/full` 以免顺带建立全部 q、reference factor 或 FGMRES basis。

按真实对象布局做 allocation 前准入，每次进入新大对象阶段读回 live RSS、系统余量、专用任务计数与 task-scope swap。cleanup 与 descendant watchdog 随该新 attempt 建立，累计 compiler/JIT/reader/checker 子进程。准入失败保存具体对象、预测与 cap，退到已经安全的独立阶段，不靠 OOM 判定容量。

### 6.2 数值与资源工作按真实依赖推进

| 层次 | 可做的实际工作 | 进入条件 / 结论边界 |
|---|---|---|
| A：真实边界与类 | 4,352 facets 的 descriptor；实际 cell/facet/class/方向绑定；保存 native witness 读回 | 不依赖 top LU forward，也不依赖全局 q factor |
| B：局部全模式资格 | 新 adapter 接独立 full-882-row 检查、真实方向；保留 tiny 项 | 按每侧 16,030 modes 和实际类计数；未完成为 PARTIAL |
| C：全局端口作用 | 真实 p6/MPC 的 Bα、Dx，两级 production support 与归并 | FE/MPC/向量实际准入；MPC/gauge/积分桥接最小测试通过 |
| D：凝聚/RHS/恢复/native identity | 使用实际映射与合格类，比较原生完整作用和生成式凝聚作用 | 相关局部 forward、方向、非零 RHS 与恢复门通过 |
| E：q 接口 | bounded layout/numeric tiles 与 cached 公式对照 | 不建全 q CSR；逐项报告结构和值资格 |

研究用 C 阶段诊断不要求先完成所有昂贵独立解析扫描，但必须标明当时已验证的 mode/类覆盖；未获全覆盖不能授予 production-qualified 或首次 full 运行资格。B 阶段独立核验可以按 checkpoint 接续。D 的原算子对照不能只是同一 callback 在两边重用；可采用独立 native cell/facet action，无需全局原矩阵。

operator probe 的输入可以是固定种子的非零 trace/interior/port 向量。检查的是两种正确表示的作用是否一致，而不是宣称任意向量的 Maxwell 方程残差接近零；RHS 制造的恒等式与真实入射场求解分别标识。本轮不生成 official R/T/A。

### 6.3 全边界作用的验收和成本必须具体

完成目标为 top 2,176 facets × 16,030 active modes、bottom 同样规模，full-order table 为 32,060；潜在 cell-mode 访问数为 69,762,560，不能误用 4,352×32,060 重复计算侧别。class 常量可以共享，facet 相位、global rows 和 MPC 仍按真实对象处理。

先用必要的短批次校准每侧/实际 class 的 kernel 与散射累加成本，再决定在剩余预算内完成 full sweep。保存 side/class/mode 范围、已完成实际键数/行数、streaming digest、最大误差与最坏项。checkpoint 避免修元数据后从第一个 key 重启；源码/输入改变导致旧计算不再适用时，明确哪些覆盖失效。

全局作用至少记录 Bα 与 Dx 的首次成本及一次同身份后续成本；需要比较不同表示时，顺序复用工作区，不让两套不必要的大对象共存。报告 payload、shared backing、generator/积分类缓存、global vectors、FE/MPC、temporary/native ownership、process-tree peak 和对应时间点；RSS 采样缺失时不能用逻辑总字节补写实测峰值。

若全局 FE/MPC 未获准入，执行 A/B 及有界 q 接口工作，优先当前实际 54 个边界类和完整侧别 mode 表。提供方向变化、mode 数增长和重计算成本的可复核结果；**不因缺全局矩阵就退回同一缩小模型，也不把 local support 乘 cell 数包装成 global-exact inventory**。六小时容纳不了完整扫描时准确交付 PARTIAL、剩余 key 范围与成本，不刷新窗口。

## 7. 新的独立 6 h 工作包、执行秩序与交付

### 7.1 旧 V19 窗口已结束，不能继续使用旧余额

旧窗口 T0 为 `2026-10-09T01:45:00.727771902Z`，deadline 为 `2026-10-10T01:45:00.727771902Z`。manifest SHA-256 为 `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0`。本次审阅时它已到期。[S2]、[S6]

其账本最后持久化为 83,032 行、seq 83031，累计 66,919.72841801553 s，SHA-256 `7ea9e880520accf2fd87d8ee63b894c7e3e1ec366308dd0c8bb4492abd705a11`。01:17:38.378013Z 的只读 projected cumulative 为 84,757.65806652053 s、当时 numerical remaining 为 1,042.3419334794744 s；它不是现在余额，也不是最终结算。历史未结算区间、clock discrepancy 与 cleanup unknown 均保留，不清零。

本次用户再次要求继续向原尺寸推进，故本 review **明确建立新的 V22 有限工作包**。它不延长或重写 V19，不把同一旧运行换名字重开，也不以旧窗口过期为由把所有新工作停住。

### 7.2 V22 窗口一次登记，不因问题刷新

| 字段 | V22 合同 |
|---|---|
| manifest 建议路径 | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v22_wsl/campaign_window_v22.json` |
| T0 | 主控接收并登记本 review 后，开始本包第一项实际工作时一次冻结；实现/测试也计入，不等到 PDE 启动才计时 |
| deadline | T0 + 21,600 s |
| 收口预留 | 600 s；到剩余预算不足以完成动作及收口时不新开该动作 |
| ledger | 新建 V22 append-only 账本，绑定 manifest SHA、review SHA、旧窗口/账本及其截至状态 |
| 时钟 | UTC、monotonic、boot identity 与保守扣账分别记；等待、修复、复测、冻结、提交计入本包 |
| service 接线 | 本次 exact path/hash/stage scope 纳入合法 route；旧 V19 path/hash 对历史读回继续有效 |
| 并发 | 一次一个 heavy/resource attempt，按 side/class/mode 保存进度 |
| 到期 | 必要安全终止与收口，报告已完成和未完成；不以重启/改名刷新 T0 |

六小时是本轮实现、验证和有界测量的上限，不是最终 target field 的 48 h 定义，也不是承诺六小时一定完成全边界高精度扫描。

### 7.3 连续推进，不逐个 bug 请求下一次审阅

先处理生产 bridge 与 stage/window 接线，使原尺寸独立入口真实可达；最小相关测试后由主控冻结源码，执行者继续原尺寸 descriptor/模式资格和 operator probe。B/D 的独立工作不等待 top 局部求解通过；凝聚/恢复等待其适用门。MUMPS 生命周期修复用已有证据/fixture 完成，不抢占端口主线去重复 E2。

普通 shape/schema/import/索引/路径/元数据问题，在原 scope 内局部修复、保留失败、定向复测后继续。数值 kernel 改动只重新资格化实际受影响的 witness/anchor；不重跑全部旧任务。真实身份或资源失败停止受影响阶段；独立安全工作继续。源码冻结后的正式 attempt 不热改，修复用新 source/attempt 绑定。

现有角色保持：执行者负责实现、测试、运行与证据，**不 commit/push**；既有主控负责审查、冻结源码、集中提交和推送。仍在 canonical worktree 和 `task40extra_0p7nm_engineering`，不创建新的聊天/checkout/worktree，不切 Task37/Task042/dot，不 SSH，不动 master，不使用执行侧 collaboration subagents 或定时自动化。必要的跨既有窗口授权沟通和独立 watchdog 保留。[本机执行规则][S23]

### 7.4 response_v22 必须首先回答的六个问题

1. **生产链是否真的接通？** 列 target/reference、factory、native residual、MPC/gauge/support、q tile consumer 的实际状态；给首次进入真实 production call 的源码和 receipt。
2. **原尺寸是否已创建 p6/MPC，是否做完 Bα/Dx？** 若未准入，给实际 cap、预计/已存活对象、阻止的具体分配及已完成替代工作。
3. **memory 真正减少多少，代价多少？** logical payload、unique backing、完整 process-tree/cgroup/task-swap 与时间分别列；没有同比 RSS 就明说。
4. **实际 support 与资格覆盖多少？** 每侧 mode、882 rows、boundary classes、全 60 类、worst error/key/row、生产两级筛选与 Σm_c/Σm_c²；UNKNOWN 不替换为估计值。
5. **已定位的断点关了哪些？** top forward、native residual、MPC 非零 slave、raw D/Hp/gauge、真实 8-q receipt/cleanup、q tiles、MUMPS 生命周期分别回答；旧负结果保留。
6. **离 2 TB/48 h 下一步只缺什么？** 用最新测量给下一次 target q build/symbolic/one-q numeric 的具体需求和成本界限，避免再列多个新 PC 名称。

提交 `response_v22.md`、更新 outcomes summary/test summary/run index，新增必要的轻量 `target_operator_probe_v22.json`、`target_port_inventory_v22.json`、`targeted_tests_v22.json`；可按实际复用 schema 合并，避免空壳文件。大数组、模式逐行明细、timeline、matrix/factor 留 ignored artifact，提交 hash、可复现命令和 compact 统计。新正式资源运行/受控停止同步模型总账；项目级回顾按现有合同维护，不反向改写历史。

测试集中覆盖新增真实断点及数值路径，不为纯文档反复运行昂贵测试；记录未运行项，保持 Markdown 和文档合同。收口由主控提供完整 HEAD、审阅 base、工作树状态、文件清单及 evidence index，然后等待下一次 review。

## 8. 小模型何时退出，何时可以算最终大模型

| 里程碑 | 当前裁决 | 下一项必要证据 |
|---|---|---|
| 缩小 0.7 nm 的基础离散/求解可靠性与最低退出门 | 沿 V19 已获准的退出结论，不重新开启默认扫参 | 只因相关数值变化重跑对应 anchor |
| 原尺寸几何/完整 boundary mapping | 已有 | 把几何类、实际 FE/MPC、mode 与 production rows 连起来 |
| 原尺寸端口与凝聚生产表示 | V21 PARTIAL | V22 完成 bridge、独立作用、实际内存与时间 |
| 原尺寸 q 资源与可运行 PC | 未资格化 | 目标实际 q 结构/填充、转换、symbolic 与受控 one-q numeric 的峰值和重复成本 |
| 第一场原尺寸 Ny8 resource pilot | 尚未运行 | 在获准机器/阶段上具备可达 full、前置身份/组件/资源门、完整进程监督；运行后做原 A6 与物理检查 |
| 最终准确 0.7 nm、2 TB、48 h | 未资格化 | 目标尺寸精度、全原方程/物理检查、完整场及全部计时/内存证据 |

**原尺寸第一场的原 A6 PASS 是运行后的验收，不能拿“还没有原尺寸 A6 PASS”禁止启动第一场。** 运行前检查 ABI、输入、方向/组件资格、可达入口和资源准入；运行中检查 residual、非有限值、资源/时间；运行后才验收原 A6、恢复、官方 R/T/A/体吸收与完整输出。这避免循环门限，同时不把诊断作用包装成 solver pass。[S1]、[S22]

最终准确目标仍沿任务书的 complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN；原 A6 相对残差及释放后检查 ≤1e-6，能量/吸收闭合等适用门按冻结合同。E/H、scaled-curl、散射场、全部衍射级、体吸收和近场需要完整输出及实际 h/p/模式截断资格。Ny8/Nz14 的一次解，即使很快并且残差很小，也只是该离散的原尺寸资源结果，不能自动称最终工程精度通过。

后续研究可以先获得原尺寸 pilot 再按误差证据细化，不要求把所有精度研究先做完才能碰原尺寸；最终交付却必须把“方程解得对”“离散足够准”“总内存与完整单场时间合格”三件事同时证明。本 review 不给 master merge approval；V22 主线是在现有方法上形成可测、可接入下一阶段的生产能力。


## 附录 A. 远程文件 SHA-256 复核

以下均为本次 base 的原始 UTF-8 内容摘要。文件名路径见相应来源或 run index；这是文件完整性核验，不是重新运行数值实验。

| 文件 | 本次独立 SHA-256 | 顶层索引 |
|---|---|---|
| `task40_v20_service_workflow.py` | `7eb3762c82b0da17574fa7082ce7a182e7f77fd4a9594696b057e0f659b687ef` | 一致 |
| `task40_v21_readonly_recheck.py` | `1c10c023934ec41c145d56cb06a22c14368a7b082c3dc42101ca147f85bfd658` | 一致 |
| `task40_v20_stage_runner.py` | `c3d20e4d98d3d12b0f9da8c3dcaf2e2d7684f8f1bcd7278248522763cbcfb2b8` | 一致 |
| `p6_cell_condensed_action.py` | `77a7c61a862a9329e86bb67c2ed8d9d89ff7965a2a095e81f83d7d655eaae66e` | 一致 |
| `task40_w1_local_probe.py` | `13d97a07e2d1e35a9ee5abd1b5604201766734410f738728142f88ad023936cd` | 一致 |
| `test_task39extra_v19_p6_cell_condensed_action.py` | `dc596e523075d85f123ff4085caf60532aac33342f3604bcdb13e48859c7f244` | 一致 |
| `test_task40_v21_readonly_recheck.py` | `4a63c3c1784d3b4238c20f4ded0e01f2dcfb3edd51e8abe881d30def5b749484` | 旧字段未同步 |
| `task40_v21_boundary_inventory.py` | `0b0d4ebe9d9238c449a6fc5cf1764bec8c563c2c7cb7fedfed4847938fc92905` | 一致 |
| `test_task40_v21_boundary_inventory.py` | `6f2c3cc190b22067b69e7984d4751e84befca348770447afe259b9c2bc281be7` | 一致 |
| `response_v21.md` | `a49974e92f070c4e5b4bcf5e02b404e3273a2354b3de5902619515ead15d1d6a` | 一致 |
| `outcomes/summary.md` | `56646cdbbb85fe2c2207d5fe08d16e9e583b693ae7f0aa278a9278a26124cbc9` | 一致 |
| `outcomes/test_summary.md` | `b82ea24cb29278a8eea0464d0958e57fdd01bb50126395dfe072c89b481b4a8c` | 一致 |
| `README.md` | `75b702a435274f3c2faa8eeabcff1212f3a4fd3d726e1a98e94c0db5fc35168a` | 一致 |
| `docs/README.md` | `782bc46bfad3076f576b991faf5dcf40cc8de7fdb91f0d05daa37f49026b57bd` | 一致 |
| `outcomes/records/targeted_tests_v21.json` | `1441335942d878623919efc61cbc3fc3f2a25b4d56c4fdfab361c3acf39173b8` | 一致 |
| `outcomes/records/target_port_inventory_v21.json` | `968436b51955a27af82068a28c7996f76de7289bfc8033684d8bf4cb808d5f3e` | 一致 |
| `outcomes/records/e2_partial_recheck_v21.json` | `92c7c93cd2f0b7061357358df8ab43f1899deb5b2ef98fa403e64de918b821a2` | 一致 |

唯一旧索引值为 `6e65a3098b6a6214e70e85d38bbd6a39dbaadd193c43f0d9c473de264af602c4`；实际 `4a63c3c1784d3b4238c20f4ded0e01f2dcfb3edd51e8abe881d30def5b749484` 与最新 targeted_tests 的 source_file_sha256 和主控最终对应复测记录一致。V22 同步 index，不改历史 tested-source 身份。[S5]、[S6]

## 附录 B. 冻结源码和结果入口

全部来源固定到本次审阅 base，后续分支更新不改变本报告引用对象。

| 来源 | 内容 |
|---|---|
| [S1][S1] | 上轮裁决、小模型退出、目标和原适用门限 |
| [S2][S2] | V21 完整回应 |
| [S3][S3] | 真实边界、局部见证、存储与身份 |
| [S4][S4] | E2 原事件只读复核 |
| [S5][S5] | 最终定向测试及源码 SHA |
| [S6][S6] | V21 evidence index、窗口与 ledger |
| [S7][S7] | 测试范围、重复回执和未运行项 |
| [S8][S8] | 生成式/缓存凝聚、MPC、native residual、q 贡献接口 |
| [S9][S9] | 局部生成、稳定求解、独立解析检查与保存数组 |
| [S10][S10] | V20 实际 degree-60 独立积分调用 |
| [S11][S11] | 原生产两级 support 筛选和归并 |
| [S12][S12] | raw D/Hp、component cache、carrier/direct 生命周期 |
| [S13][S13] | 实际 worker 工厂和 stage/cleanup 产物 |
| [S14][S14] | reference 工厂、row-tile q consumer |
| [S15][S15] | 转换、symbolic/numeric 三条资源准入路径 |
| [S16][S16] | 阶段路由和 partial receipt 消费 |
| [S17][S17] | service 范围与旧 campaign path/hash 硬编码 |
| [S18][S18] | Ny8 计划 FE/trace 行数及 8-q 结构 |
| [S19][S19] | 4-q checker、失败阶段与 cleanup 核验 |
| [S20][S20] | 保存网格 facet → cell → class 映射 |
| [S21][S21] | V21 generated、MPC、RHS/recovery 测试范围 |
| [S22][S22] | 最终数值/物理、精度、资源和角色合同 |
| [S23][S23] | 本机执行者/主控及当前 worktree 边界 |

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/review_report_v21.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/response_v21.md
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/outcomes/records/target_port_inventory_v21.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/outcomes/records/e2_partial_recheck_v21.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/outcomes/records/targeted_tests_v21.json
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[S8]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/p6_cell_condensed_action.py
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/task40_w1_local_probe.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/task40_v20_local_components.py
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/dtn_port_3d.py
[S12]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/fullspace_dtn_action.py
[S13]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/runners/task40_v10_worker.py
[S14]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/task40_v10_p6_yorbit.py
[S15]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/task40_v10_p6_mumps.py
[S16]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/runners/task40_v20_stage_runner.py
[S17]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/scripts/task40_v20_service_workflow.py
[S18]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/solvers/task40_v10_p6_periodic_profile.py
[S19]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/scripts/task40_v21_readonly_recheck.py
[S20]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/geometry/task40_v21_boundary_inventory.py
[S21]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/src/test/test_task39extra_v19_p6_cell_condensed_action.py
[S22]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/task.md
[S23]: https://github.com/Rookie1234567/MyFEniCS/blob/6490389b2e6b7f9a4d47269e50acb93d61dc4c41/docs/task40extra_0p7nm_engineering/AGENTS.md

## 附录 C. 本次审阅交付核验

本报告仅新增同分支 review，不修改数值代码、输入、旧 response、结果、窗口或历史账本。正文的数值复核、源码缺口与未来执行要求已经分开；本次审阅没有启动 PDE 或 q factor。交付前检查公式围栏、表格列数和来源引用；提交后按完整 commit 回读正文及父提交/文件清单，并检查 GitHub rendered view。具体提交 SHA、内容 SHA-256 与渲染结果在本轮最终审阅回执给出，不预写尚未发生的提交结果。
