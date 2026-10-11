# Task40extra Review V25：进入完整原尺寸体积作用与单 q 消费者

## 0. 审阅结论与本轮决定

**V24 有真实进展：原尺寸 q0 端口的一列/一行已跑通，32 模式缓存确实避免了重复生成，一个真实内部边轨道的体积行块也通过了保存数据回读。但完整体积作用仍未运行，完整 reference q 矩阵仍为 0/8，不能据此判断 2 TB / 48 h 已经可达。V25 的主要交付改为完整原尺寸体积作用，以及完整单个 reference q 的消费者和容量产物。** 不再把增加一个有限 panel 作为下一轮的主要成果。[R1]、[R2]、[R5]

这里的预条件器是在每次迭代中提供近似修正的辅助求解器。q 是 y 周期相位分支；reference 是具有可分结构、可按这些分支处理的规则参考问题。真实非可分 target 的跨 q 耦合仍然存在。trace 是单元边、面上的未知量，内部未知量先通过单元局部消元去掉，最后再恢复。

| 决策项 | Review V25 决定 | 资格与依据 |
|---|---|---|
| V24 阶段成果 | pass_with_qualifications | 接受 B/C/D 各自有限范围，不撤销已保存的真实进展 [R1]–[R5] |
| 是否又换预条件器 | 不换 | 继续 p6 reference、ROW_TILE_BOUNDED_CSR_V17、ONE_Q_REFACTOR_V19 主线 |
| 是否先重复小模型/全模式扫描 | 不要求 | 复用 V23 完整支撑及 V24 已通过的局部证据；只补改动影响的范围 [R23] |
| V25 第一条主交付 | 全部 30,464 cells 的真实 target 体积 owner、作用、凝聚 RHS 与恢复见证 | 原尺寸完整对象；不要求先有全 q 或 PDE |
| V25 第二条主交付 | 一个真实 regular-reference q 的完整行域、完整端口消费者 | 与 target 体积分别准入；完整 CSR 条件构建，资源不足时保留完整流式/行块产物 |
| 普通 bug 如何处理 | 在同一固定窗口内修复、保留失败、继续后续依赖 | 不因 dtype、selector、checker、路径等修正再次等待一轮聊天审阅 |
| 最终工程能力 | not_qualified | 真实 incident RHS、全 reference inverse、全局 KSP/场、精度与 2 TB / 48 h 尚未闭合 |
| master / ordinary default | do_not_merge / not_approved | 本次只推进显式 Task40 研究入口 |

**小模型阶段的主要用途已经完成到足以向原尺寸算子推进。** 接下来需要回答“整台器件的一个完整算子是否能正确、经济地作用”，再回答“参考逆的一次完整调用多贵”，而不是继续以更小模型的迭代次数下降作为晋级条件。当前 272×8×14、p6 是原尺寸资源/算子 pilot；它的成功仍不自动证明最终 y/z 离散精度。

## 1. 冻结身份与审阅范围

| 身份 | 精确值 |
|---|---|
| repository / branch | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 审阅 HEAD | c1a77d362d852d864668dcf5d43957880a6788df |
| HEAD 时间 / 说明 | 2026-10-10T21:09:36Z；Task40 V24: preserve immutable accounting as-of and publication receipt |
| V24 最终数值源码 | 809d6a151eed7b4d0eca0430fee2782285e786e7 |
| 前一份 Review V24 | 92a59c167b53f828cc0408eca664d0eebc878428 |
| input SHA-256 | 33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff |
| physical model SHA-256 | ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241 |
| mode manifest SHA-256 | 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d |
| ABI receipt SHA-256 | ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426 |
| 审阅日期 | 2026-10-11 UTC |

相对前一份 review 提交，远程新增 8 个提交、28 个变更文件，其中 6 个是 V24 数值/接线源码提交，后续为文档和发布元数据。B 使用 eca24be972a0eca1480b6f1f2fb9d745fb823718；C 使用 a233ac49f84269265ddc684d31cb9b790864b018；D 使用 809d6a151eed7b4d0eca0430fee2782285e786e7。不能把三次运行都改记为最终源码上的重跑。[R1]、[R7]

本次读取 response、五份 compact、run index、summary/test summary、项目总账，以及 provider、体积凝聚、真实 edge panel、service、checker、stage、reference 和因子生命周期源码。**run index 列出的 12 份正文/compact/总账，远程文件内容的字节数与 SHA-256 全部复核一致**，详见附录 A。大型 NPZ、执行机原始日志和场文件未在本次审阅中下载重算；本报告的 measured 数值来自提交的回执，源码审查用于确定其范围。本次没有执行 PDE、FE 或因子计算。

V24 最终定向测试记录为 D 组件 6 项、route 兼容 4 项、文档合同 29 项通过；这不等于全仓 pytest、MPI2/MPI4、Ruff 或 CI 通过。V24 发布记录中的线上渲染仍是未确认；本次读取远程内容不把这项改写为已通过。[R7]、[R22]

## 2. V24 的有效结果与准确边界

### 2.1 B：真实 q0 单模式端口投影可以沿用

B 的模式为 [10, "top", -142, 0, "s"]，覆盖 top 全部 2,176 个 facets。q0 库存为 4,076 个 aliases，本次只计算 alias 0，对应 original mode 10 / local mode 2。原始 H_p 的**数值是 1250.0，模式索引是 10**；summary 中 “H_p original index 1250” 应在下一次文档收口顺手改正，不因此重跑 B。[R1]、[R5]、[R21]

| B 检查量 | measured | 解释 |
|---|---:|---|
| 真实 q trace map | 50,048×773,568；222,946 nnz | 有限支撑行上的实际映射 |
| C 投影相对误差 | 4.8436017086968805e-17 | 限值 1e-11 |
| −D 投影相对误差 | 4.690516209749925e-17 | 限值 1e-11 |
| H 投影相对误差 | 0 | 限值 1e-11 |
| 完整 q 矩阵 | 0/8 | 一列/一行不等于完整 q |

原 required checker 曾以退出码 2 失败，涉及 typed raw C/−D/H payload 和投影 NPZ 回读。4d4942fb69c6bac4342f1f024d2d9b08e52803f1 对旧原始数据做离线 postfix，22 项通过；保留原失败和 postfix，接受有限投影资格。其 PARTIAL_RECEIPT_CHECKED、full_pass=false、official_result=false 与有限成功不矛盾。无需为修正表示/回读再次生成 FE 数据。[R5]

### 2.2 C：复用节省的是生成成本，尚未证明整机内存下降

| C 的同一 32 模式样本 | 时间或容量 | 数据身份 |
|---|---:|---|
| 首次生成 | 6.768845 s | measured |
| 首次生成后的 apply | 0.491496 s | measured；数据已生成 |
| 两次 warm apply | 0.482975 / 0.488801 s | measured；生成次数为 0 |
| 释放后再生成 | 6.561613 s | measured |
| 再生成后的 apply | 0.468682 s | measured |
| cache write | 0.295019 s | measured；单独计费 |
| B/D rows + values payload | 180,373,760 B | measured；不含所有 maps/FE/owner/工作数组 |
| backing 释放 | 两次均 128/128 | measured；对象生命周期，不是等量 RSS 降幅 |

来源：[R3]、[R4]。正确比较是“每次重生成后作用”与“保留数据后作用”：

```math
t_{\mathrm{regen+apply}}=6.561613+0.468682=7.030295\ \mathrm{s},\qquad
\overline t_{\mathrm{warm}}=0.485888\ \mathrm{s}.
```

样本对应约 **14.47 倍**的这部分耗时比；两次 warm 的范围约 14.38–14.56 倍。首次数据已经就绪后的 apply 与 warm 均值只相差约 1.012 倍。因此收益主要来自避免重生成，而不是作用内核突然快了十四倍。写盘、装载、FE setup、q 投影和完整求解成本仍应各自入账。

源码中的 cached factory 确实复用已保留 entries。独立 replay 从这些同一缓存数组重新累加 Bα/−Dx，并用两个不同非零输入检查；这是缓存和映射接线的独立线代回读，未采用另一套表面积分，也未完成 32 模式各自的 q 投影。[R8]

**不能把一个 32/64 模式缓存轮流扫描全部 32,060 模式称为全量 warm reuse。** 若顺序扫描的工作集超过缓存，每轮仍会重新生成。下一步优先在实际 selected-q 构建过程中分块生成、投影并持久化该 q 的完整端口数据，测投影后的实际大小和 replay 成本。不能假定压到 q 坐标后恰好缩小 8 倍，也不能因 B/D 计数相同就擅自共享其 values/maps。[R8]、[R12]

### 2.3 D：真实体积行块通过，完整体积仍未运行

D 是器件内部 y 方向边轨道，不是外部 DtN 边界 panel。8 个轨道各取 4 个 incident cells，共 32 cells，覆盖 6 个 oriented classes；每 cell 为 450 个内部行、432 个 trace 行。实际 MPC 触及 312 个 slave rows、8,688 个 active trace columns。[R2]、[R9]

| D 量 | measured | 可以支持的结论 |
|---|---:|---|
| q 行投影块 | 48×8,688；417,024 nnz；误差 0 | 左侧 q 行投影，右侧仍为 active trace 列 |
| edge-self 双侧 q×r 子块 | 48×48；2,304 nnz；误差 1.3236785363666466e-16 | 仅该 self 子块完成双侧投影；限值 1e-11 |
| off-diagonal q 最大范数 | 7.651965843602257e-14 | 实际评估的局部交叉项 |
| diagonal 最大范数 | 109.95379046015648 | 不能由此宣布全 target 按 q 对角化 |
| 局部 full-equation residual | 1.1482096831726816e-15 | 局部见证；不是全局 PDE residual |
| 局部恢复前向误差 | 6.3309899286681456e-12 | 只覆盖本次 6 类 |
| 局部 condensed residual | 4.8468962492704906e-14 | 只覆盖本次局部方程 |
| 新 LU / 同 LU 修正 | 6 / 0 | 每个已覆盖 class 一次 LU |

D checker 的 34 项保存数据回读有实际数值内容：重算保存局部张量/恢复向量对应的方程误差，并按 32 cells 的 MPC expansion 和 class Schur 重新累加行块。它没有重新运行 FFCx 或重新做六类 LU；主控 audit 也没有独立重跑这套计算。接受其有限范围，不因独立性边界再重跑相同 D FE。[R9]、[R15]

D 没有投影其余非 edge-self q 列，没有建立全体积、完整 q、全局 RHS 或恢复。D 是 S-only，C/−D/H 数据由 C artifact 的 hash 绑定而非在 D 中重算。复制到 D run 的 C payload 仍属于 C 的原运行。[R1]、[R7]

### 2.4 资源记录和停止原因

以下单位均为 B / s；RSS 为同时进程树采样峰，cgroup 为专用任务组峰，两者不是同一口径。

| 运行 | sample/panel wall | 进程树 RSS peak | cgroup peak | cgroup cap / swap |
|---|---:|---:|---:|---|
| B | 23.758030 s | 2,939,039,744 B | 3,120,656,384 B | 17,179,869,184 B / 0 |
| C | 19.169655 s | 3,170,832,384 B | 3,470,761,984 B | 同上 / 0 |
| D | 42.859896 s | 2,950,139,904 B | 3,557,376,000 B | 同上 / 0 |

来源：[R4]。watchdog 嵌在 workflow/parent 计时内，不重复相加。PSS 为 disabled/null；后代清场通过不等于 native owner 全生命周期通过。当前数字不能作为完整 worker 的资源峰值。

V24 固定窗口为 T0=2026-10-10T16:33:11Z，数值 cutoff=22:13:11Z，总 deadline=22:33:11Z。worker_end 的 seq 938 在 20:26:17.265Z，离数值 cutoff 约 **106.9 min**；seq 941 在 21:09:35.510Z，仍约 **63.6 min**。可选单 q 的 NOT_ADMITTED 来自“实现/资格未闭合、完整共驻容量未知”，而 resource_gate_triggered=false。[R6]

这不证明余时一定能完成下一对象，却明确不是已经测得内存或时间资源不足。V24 有界工作包按其有限目标得到结果；V25 必须把下一消费者的实现本身列为主交付。旧窗口已经到期，不能恢复旧余额、刷新 T0 或改写历史收费。

## 3. 完整体积的具体缺口：先压实全局映射和 owner

### 3.1 已有可复用核心，不需要另造预条件器

完整网格 census 为 **30,464 cells、29 raw classes、60 oriented classes**。raw class 复用相同材料和精确几何的原始单元张量；oriented class 再区分有限元方向。复用类别的目的，是避免每个 cell 重复积分、重复存储/分解同样的局部矩阵。[R2]、[R10]

D 中 raw kernel generation 为 39.128757 s，占 panel wall 约 **91.3%**；LU+Schur 只有 0.381517 s。下一步首先计量全部 29 个真实 raw class 的一次生成及 60 个有方向类别的复用，不应先优化已经很小的 LU 时间，也不能拿 32-cell panel 时间线性乘到全网格。[R4]

已有 `build_unconstrained_assembly_time_condensation` 支持不建立全局矩阵、保留 class Schur 的 action-only 路径。已有 P6 action 支持全 cell gather、局部乘法、scatter，以及 RHS 凝聚和内部恢复。需要接通完整 owner，而不是再复制一个 task-numbered panel 求解器。[R10]、[R11]

### 3.2 2.20 GB 只是部分上界，全局小对象是实际风险

C 的 2,199,609,160 B 可分为以下整数容量项。这是 derived class/metadata 上界，不是完整阶段实测峰值：

| 组成 | B |
|---|---:|
| retained class 数据 | 748,535,040 |
| raw 张量缓存 | 360,956,736 |
| oriented 张量 | 746,807,040 |
| retained Schur | 179,159,040 |
| 局部 working upper | 52,774,920 |
| cell metadata upper | 111,376,384 |
| 合计 | 2,199,609,160 |

来源：[R4]、[R8]、[R10]。其中 cell metadata 估算为 30,464×(882×4+128)，不涵盖全局约束容器。

源码的 `_owned_trace_numbering`、`_trace_constraint_map` 会建立数百万项 Python dict；尤其为每个 active trace 建一个 tuple 和两个单元素 NumPy arrays。全 cell DOF/expansion 也在 class-cache allocation gate 之前生成，P6 action 构造还可能再拥有 cell expansion。这些对象和临时集合不能被“class cache gate 已通过”覆盖。[R10] 263–305、358–556、1528–1562、1678 起；[R11] 1353–1364。

| 补充容量事实 | 数值 | 身份/条件 |
|---|---:|---|
| raw trace rows | 6,472,548 | derived；20,181,348 storage − 13,708,800 interior |
| active trace rows | 6,188,544 | measured；差额为 284,004 MPC slaves |
| cell expansion CSR 纯数组 | 315,972,608 B | conditional；每 local trace 行恰一 master，int32 indices、complex128 values |
| 各 cell active_ids 纯数组 | 52,641,792 B | conditional；每 cell 至多 432 项的该布局估算 |
| 一个 full storage complex128 向量 | 322,901,568 B | derived；20,181,348×16 |
| 一个 active trace complex128 向量 | 99,016,704 B | derived；6,188,544×16 |
| 两个 active trace scratch | 198,033,408 B | derived；另计其余调用者向量 |

不能简单把上表相加作为峰值；应按实际共享、复制、临时重叠计量。若每行 master 数大于 1，expansion entries 按实际数上调；向量也按各阶段实际同时存活数量计。

**V25 首小时要把这些未知项转为对象数量、数组字节数、qualified runtime 下 Python 对象开销和生命周期的明确预算。** 在大 dict/set、全 expansion 和原生 callback 工作区分配之前设置 phase gate。若旧表示不能准入，沿现有映射接口做局部紧凑实现：identity rows 隐式表示，slave coefficients 单独保存，original→active 使用带 sentinel 的整型数组或有界批量映射，共享既有 expansion；不另开预条件器项目。行号可用 int32 不代表累计 nnz/offsets 也能用 int32，必须逐项检查。

此处的运行上限仍为本机 16 GiB 专用 cap、动态可用内存和 host reserve 共同约束；终极机器的 2 TB 总物理内存不能被用来给本机超额分配授权。

## 4. V25 主交付一：完整原尺寸体积作用、RHS 凝聚和恢复

### 4.1 实现范围

在 Task40 显式 opt-in 路由下，使用同一原尺寸 target FE、真实材料和 finalized MPC，复用以下核心配置：

```python
build_unconstrained_assembly_time_condensation(
    compiled_actual_curl_plus_mass_form,
    actual_target_space,
    actual_target_cell_tags,
    mpc=actual_finalized_mpc,
    materialize_global_matrix=False,
    retain_local_schur_for_matrix_free=True,
    share_identity_cache=True,
    preserve_exact_geometry=True,
    sum_duplicate_cell_integrals=True,
    strict_local_checks=True,
    allocation_gate=whole_owner_phase_gate,
)
```

这是需要接入 V25 stage 的实现合同，不表示当前 HEAD 已有可执行的 complete-volume CLI。保留相同积分的全部 kernel 项，使用精确几何类别；不只消去 curl 或 mass 之一后再相加。直接消费已有 core，不把数值逻辑继续堆进 probe/service。[R10]

由全体 cell 的局部 Schur 和实际 MPC expansion 形成：

```math
Sx_t=\sum_c E_c^{H}S_cE_cx_t,\qquad
S_c=V_{tt,c}-V_{ti,c}V_{ii,c}^{-1}V_{it,c}.
```

其中 E_c 把独立 trace 向量映到该 cell 的真实接口行，并包含约束相位。此阶段允许明确的 S-only 体积诊断；未加入完整端口作用前不能登记为完整 A6。无需先建立全局 CSR、全 8 q、KSP 或物理 incident RHS。为取得纯 S 作用，不调用会额外建立全 carrier/全 interior Python 映射的 from-carrier 工厂；选择现有 S-only 核心或直接 action owner 接口。[R11]

### 4.2 全网格见证必须来自独立原生体积作用

在完整目标网格使用两个不同的非零 trace 输入，其中至少一个同时包含全 cell 的非零内部见证。它们是用于验证已有全局方程的 manufactured witness，不是新的缩小 PDE。

使用现成 `FullspaceSplitVolumeAction` 直接从实际 curl/mass forms 构造原生体积 callback；它沿已有 `fem.assemble_vector` 和 MPC 汇集作用，无需完整 DtN carrier 或全局体积矩阵。避开会隐式建立全 carrier 的高层 physical-bundle/reference 入口。[R19]、[R20]

对完整见证 x*：

1. 从独立原生体积 callback 生成并冻结 b=V_native x*，不能由候选 Schur 自己造 b。
2. 用实际全局映射和所有 cell 凝聚 RHS，比较 Sx*_t 与 b_cond。
3. 用实际局部 LU/recovery 恢复全 cell 内部场，保留独立 trace。
4. 再由原生 callback 计算恢复后的全体积方程残差，并报告恢复前向误差。
5. 输出全部 cell/class/MPC/active rows 覆盖、非零输入 hash、各分项范数、时间、共驻峰与释放结果。

**防止产生假通过的两个现成接口细节：**原生 apply 返回借用的内部输出 buffer，必须复制并冻结第一次 b，再做下一次 apply；输入/恢复 storage 保持 slave 严格为零，原生 action 自己只做一次 MPC backsubstitution。原生输出已经是 MPC dual 时，使用 `reduce_rhs(..., rhs_is_mpc_dual=True)`，恢复使用 `recover_storage(..., expand_trace=False)`。不默认使用带 1e-14 筛选的 unconstrained-vector helper，也不二次施加 MPC。[R11] 2853–2979；[R19]、[R20]

| 全体积验收项 | V25 数值门 | 资格含义 |
|---|---:|---|
| 全部实际 cells/classes | 30,464 / 29 raw / 60 oriented，按冻结身份核对 | 完整目标覆盖；不是 D 的 32/6 |
| 局部 LU | 有限、非奇异，保持现有 1e-11 identity/backward guard | 每实际 class 一次新 LU |
| Schur 作用与凝聚 RHS 相对误差 | ≤1e-10 | 全网格作用/凝聚一致性 |
| 独立原生体积方程相对残差 | ≤1e-10 | 真实全网格体积方程见证 |
| 内部恢复相对前向误差 | ≤1e-11 | 恢复前向资格，单独报告 |
| slave storage | 严格为 0 | 保持现有存储约定 |

上述方程/恢复界沿用 D 的分工，是 V25 完整体积诊断合同；不改变 q 投影 1e-11 或最终 A6/PDE 的既有门。零分母使用明确规则，各分项不能用另一较大范数掩盖。

若某类前向误差略超门，保留原负结果，允许至多 3 次同一 LU 的修正；分别报告 action、原生 residual 与 forward 资格。**前向资格未通过不自动禁止记录全局 S 作用和独立原生体积诊断。** 非有限值、奇异因子或原 LU stability guard 失败才直接影响局部消元本身。不得为“补齐 60 类资格”再单独耗一轮扩大的小 panel。

## 5. V25 主交付二：真正的 selected-reference-q 完整消费者

### 5.1 不能把单 q 因子槽误当作单 q 构建入口

当前 `build_task40_v10_p6_reference_inverse` 没有 selected-q 参数，仍遍历全部 contexts；sector 层默认生成四个 q×r blocks，最后要求全部 q matrices 齐备。旧 one-q 生命周期控制的是因子驻留，不能阻止高层先构造全部 reference、carrier 和 CSR。[R13] 2049–2080、2964–2992、3485–3502、3731、3942–3944。

当前 ordinary target worker 仍先拿完整 carrier，再进入 cached p6 action；V24 的有界缓存没有将这条完整调用链替换为可复用、受控的 provider。因此不能把“helper 已有”写成“完整生产入口已接通”。[R14] 5355–5395；[R11]

V25 应新增一个**明确选择 regular-reference sector/branch 的 build-only 消费者**，复用 V17 row-tile core，只处理指定 q 所需的完整数据；不要为此运行旧 all-q builder，也不改变 ordinary default。

### 5.2 对象、端口与完整覆盖合同

reference sector 是规则参考问题的 272×2×14、7,616 cells，带其自己的材料、twist/MPC、trace 坐标和 aliases；它不是非可分 target 的 30,464-cell volume。**不能把 target 的 q0 trace slice 直接当成 block-diagonal reference inverse。** 两条主线分别准入，target full-volume PASS 不是 reference q 构建的数学前置门。[R13]

选择 q0 作为首个完整消费者，绑定实际 sector/branch 与完整 alias inventory。V24 target q0 的 4,076 aliases 是已知库存；实际 reference 的 local/global modes 对应关系和 H_p 缩放必须显式登记，不能把 target 数量或 original index 硬填为 reference 数值身份。

完整消费者需完成：

- 全部所需 reference cells/classes、全部目标 q trace 行和列；D 的 48×8,688 左投影不构成双侧完整 q。
- 该 q 全部对应端口 aliases、实际 B/C、−D、原 H_p 和局部/全局平衡缩放。按完整 inventory 推导需要生成的模式子集，不截成 32/64 个。
- 在本来就必须生成的该 q entries 上，分别检验最终 B、D 内部支撑为空；绑定端口面、外部材料、ordered keys、gauge、MPC 和两级生产筛选，形成 reference 自身的 direct-only 适用证据。无需重扫每个 sector 的全部 32,060 模式。
- 对非零 q 输入完成双侧投影/作用对照，volume、C、−D、H 分别给出误差，沿既有 1e-11 投影门；不只看合并后可能掩盖小分项的范数。
- 对同一次真实 two-cell reference 原生作用，同时投影并回读 paired branch 输出（q0 对应 q4），沿既有 off-diagonal 门检查相位/分支泄漏；不要求建立其他完整 q 矩阵。

如 reference 实际产生非零内部 B/D，不得删条目或改阈值使其通过；保留该分支的真实缺口，同时继续另一条已独立准入的 target 体积主线。

### 5.3 完整 CSR 条件构建；资源受限仍要留下完整可消费产物

按以下顺序执行，并对磁盘、计数宽度、临时重叠和执行 deadline 同时准入：

| 阶段 | 应交付的真实产物 | 不能替代为 |
|---|---|---|
| selected-q 完整映射/结构遍历 | 全行域覆盖、实际/精确推导 nnz、每行/块 counts、所需 mode 完整清单 | 另一块 48 行或一列端口 |
| 完整数据消费者 | 全体积与全端口的分块生成、双侧投影、累加；完整流式作用或可恢复 row-tile/spool | 32 模式 warm 数据乘比例 |
| CSR 准入通过 | 一个完整 selected-q CSR，shape/nnz/bytes/hash、独立作用回读 | 只给预计内存 |
| CSR 准入失败 | 保存完整覆盖的行块/流式作用及结构、磁盘/内存缺口，明确 CSR NOT_BUILT | 因一个大数组不能分配而退出所有可做工作 |

流式完成必须覆盖该 q 的全部行、列及端口，并绑定顺序、去重规则、tile offsets、dtype、hash 和重载入口。磁盘产物记入 ignored artifacts，不提交大矩阵。若只能完成前缀，如实标为 PARTIAL，不把完整 counts 与部分数值填充混称完整 q。

complex128 values 与 int32 indices/indptr 的单份 CSR payload 为 20×nnz+4×(n+1) B；这不是构建峰值。分别统计 structural slots、真实数值非零和保留的 exact-zero slots。累计 nnz 超过 2,147,483,647 时，不能通过窄化转换假装符合当前 int32 ABI；保留宽计数/行块，并明确后续完整 CSR/后端所需整数宽度。[R13]

有完整流式作用而没有 CSR/因子时，可以关闭“完整 q 消费者”与构建资源问题，**仍不具备直接交给 MUMPS 求解的资格**。若完整 CSR 在当前实际 cap 内可容纳且剩余时间充足，本包继续完成，不能仅因它在上一轮是 optional 就再停审。全 q 或数值 factor/KSP 不在本包自动启动范围。

缓存策略随此消费者计量：保存投影后 selected-q 数据，测一次生成/写出、实际重载、至少两次不同非零输入 replay；记录每次 provider generation 次数。若不能共驻，就测顺序磁盘读取，而不是默认每次 apply 再做 native 积分。热缓存是否能与完整 target volume 共驻，须由真实 owner 峰值判定；分别运行通过不等于合并运行已通过。

## 6. 2 TB / 48 h 应如何得到可判断的预算

### 6.1 内存降低和迭代降低需要分开判断

V24 没有新的完整 KSP，因此没有本轮“新旧预条件器迭代次数”对照。当前路线仍是既定 p6 reference。V23 内部零证书排除了旧条件情景中不必要的内部端口缓存；V24 证明了一种有限复用方式。它们改变了可实现的内存方案，尚未证明完整 solver 的 RSS 下降。[R1]、[R23]

2 TB 是 **2,000,000,000,000 B 整机总物理内存**，需留 OS/其他进程余量并保持 task swap=0。应统计实际同时存活的 FE/MPC、class cache、全局 maps/expansions、端口表示、reference CSR、当前因子及其 workspace、Krylov 向量、恢复/输出/checker：

```math
M_{\mathrm{host,other}}+
\max_t\left\{
M_{\mathrm{FE,MPC}}+
M_{\mathrm{volume,maps}}+
M_{\mathrm{ports}}+
M_{\mathrm{reference,CSR}}+
M_{\mathrm{factor,work}}+
M_{\mathrm{Krylov}}+
M_{\mathrm{recovery,output}}
\right\}(t)
\le 2{,}000{,}000{,}000{,}000\ \mathrm{B}.
```

主 FGMRES 只按当前 active trace 数估算，restart m=30 的 2m+1 个 complex128 向量约 6,040,018,944 B，m=60 约 11,981,021,184 B；这是主向量组的 derived 容量，尚不含 ports、额外 scratch 或未来精度网格增长。不能只核对一个因子是否放得下。

### 6.2 ONE_Q_REFACTOR 当前用时间换因子驻留

源码已明确：ONE_Q_REFACTOR_V19 保留全部不可变 q CSR；初始化对全部 q 逐个做 symbolic preflight 后销毁；cache miss 时从 CSR 重新建立 PETSc 输入矩阵、symbolic、numeric 和 fresh factor probe。[R25] 949–956、1106–1123、1364–1505。

上层每次 PC apply 固定遍历 sector/branch。q 数大于 1 时，上一次最后驻留的 q 不等于下一次首 q，随后每次切换又驱逐旧槽，所以一轮通常对每个 q 都重新分解。只有紧邻重复求解同一个 q RHS 才可能命中该单槽。[R13] 846–869；[R25]

因此 48 h 预算必须至少写成：

```math
T_{\mathrm{field}}=
T_{\mathrm{prepare,JIT,build}}+
T_{\mathrm{symbolic\ preflight}}+
N_A t_A+
N_{\mathrm{PC}}t_{\mathrm{PC}}+
T_{\mathrm{Krylov,other}}+
T_{\mathrm{recover,output,check}}
\le172{,}800\ \mathrm{s}.
```

```math
t_{\mathrm{PC}}\simeq
t_{\mathrm{transform,other}}+
\sum_{q=0}^{7}
\left(
t_{\mathrm{convert},q}+
t_{\mathrm{symbolic},q}+
t_{\mathrm{numeric},q}+
t_{\mathrm{fresh\ probe},q}+
t_{\mathrm{solve},q}+
t_{\mathrm{evict,identity},q}
\right).
```

各项按不重叠的实际计时口径汇总，不同时加 parent 与 nested timers。N_A、N_PC 分别统计真实调用数，不默认等于外层迭代次数。准备、JIT、构建、恢复、完整场输出和 checker 都属于单场预算，不只算 KSP 时间。

目前没有完整原尺寸 q/factor 或 PC 调用实测，**不能给出可信的“还需多少小时”预测**。V25 应先交出真实全体积作用成本与单 q 构建/数据大小。后续单 q 生命周期实测再决定：既定单槽重复分解能否满足时间；若不行，按真实 2 TB 共驻账选择可负担的保留/复用方式，优先减少重复构建，不先另换数学预条件器。未测剩余 q 的最坏填充和成本也必须保留为预测范围，不能将 q0 默认复制八次当实测。

### 6.3 向最终大模型推进的明确退出条件

| 里程碑 | 应结束的问题 | 下一步 |
|---|---|---|
| V25 完整体积 + 完整单 q 消费者 | 全 target S 是否正确；全局 maps 多贵；一个完整 q 的行/端口构建多贵 | 用实际数据准入 selected-q factor 生命周期 |
| 完整单 q 生命周期、其余 q 覆盖与一次 reference PC 调用 | CSR/因子共驻、重复分解、整个 PC 成本 | 闭合原尺寸 target+PC+RHS/recovery 调用链 |
| 有资源依据的原尺寸 pilot 完整场 | 真正的迭代数、全 A6 explicit true residual、恢复/输出耗时 | 校准总内存/48 h 预算，进入真实目标离散精度闭合 |
| 最终准确 0.7 nm 工程解 | 原尺寸真实材料/几何、规定 observable/场精度、2 TB/48 h 全账 | 才可宣布最终目标达成 |

第一份真实原尺寸完整求解的准入需要正确算子/RHS/恢复和有余量的资源证据；**成功求解后的 A6/物理结果门不能反过来成为“先有一份成功原尺寸解，才准许第一次原尺寸解”的循环条件。** 首次场求出后，仍必须用完整原方程 residual 和已有物理门决定是否接受。当前 Ny=8、Nz=14 的 pilot 也不能越过最终精度验证。

## 7. V25 新固定工作包：一次接通路由，在窗口内持续推进

V25 使用独立新窗口。旧 V24 的 source/window/raw payload/checker 和收费记录保持不变。V24 seq 941 的不可变前缀共 942 行，SHA-256 为 31f2d474dccc11a5385bf0da6aef7f0a4b66c80af30751fb2330e71105005bb3，累计 16,584.51095769209 s；该前缀之后 live ledger 仍可追加发布费用，不能将快照称作全部最终费用。[R6]、[R7]

### 7.1 最小路由修复属于本包工作，不作为下一轮等待项

当前 campaign/service/worker 只登记了旧窗口及 B/C/D operation。仅创建 campaign_window_v25.json 然后启动，会被固定路径、hash 或 operation 拒绝。需要同一次改动贯通：

| 位置 | 当前断点 | V25 应有行为 |
|---|---|---|
| campaign 注册 | V24 固定 path/hash/scope | 唯一 V25 registration 绑定本 review、source_at_entry、window 与明确 operation scope |
| service resolver / stop-stage | 仅旧版本注册与旧 probe scope | 新完整体积/selected-q build-only scope，沿现有监督入口 |
| 旧 scan loader / q execution 校验 | 只接受 V23/V24 execution hash | 分开当前执行身份与旧 artifact 身份 |
| C artifact 复用 | 当前部分 loader 要求 C window 等于 execution window | C 保留 V24 window；V25 只验证其适用性及 raw hashes |
| worker dispatch / stage PASS / checker | 仅 B/C/D 状态 | 新 operation 的完整覆盖、资源、数值与 partial 分类一致 |

源码依据：[R15] 163–234、780–822、894–900、1370–1401；[R16] 122–164；[R8] 5203、5447–5466、6055–6069；[R17] 1054–1089。可将新 operation 命名为 COMPLETE_TARGET_VOLUME_ACTION 和 SELECTED_REFERENCE_Q_CONSUMER；这是本轮待实现的接口示例，不能声称当前 CLI 已支持。

使用一个明确 V25 登记对象贯穿 service、worker、watchdog、checker，避免多处各自猜当前版本；不删除 identity/window 校验，也不扩成任意路径均可授权。登记时冻结 source_at_entry、review/window/scope；每次实际运行另行冻结 run_source_sha。在包内修复并提交新源码后，可继续同一 V25 窗口，不改变 T0/deadline/历史费用，也不改写旧 artifact 身份。target 原输入保持其 SHA；reference 派生输入独立登记其 source/input/model/twist/mode 关系，不覆盖原输入。V23 scan、V24 B/C/D 各保留原 source、window、payload hash 和独立 postfix。

### 7.2 时间与资源合同

| 项目 | V25 合同 |
|---|---|
| canonical worktree / branch | /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering / task40extra_0p7nm_engineering |
| T0 | 本包第一项实际实现、测试或准备开始时一次冻结；不等 FE 启动才计时 |
| 总窗口 | 21,600 s，包含实现、测试、运行、提交/推送/回读 |
| 收口预留 | 1,200 s；数值最晚于 T0+20,400 s 停止，总 deadline=T0+21,600 s |
| 本机资源 | 保持已资格化 runtime、complex128/int32/MPI1、动态 host reserve、16 GiB 专用 hard cap、task swap=0 |
| 并发/角色 | 一次一个 heavy case；沿既有主控/本机执行者和 watchdog，不新增执行聊天或工作树 |
| 新数值范围 | 本报告完整 target volume 与一个完整 reference q build-only；不自动启动 factor、全 q KSP 或 PDE |
| 提交边界 | 主控集中提交/推送同一任务分支；不改 ordinary default，不合并 master |

这是顺序计划，不是由有限样本预测的运行承诺：前约 45–60 min 贯通路由、关闭 maps/owner 容量并尽早启动完整对象；随后约 90 min 完成全体积构建与见证，同时按实际成本决定另一主线的次序；余下数值窗口推进 selected-q 全行/全端口消费者和条件 CSR，最后 20 min 集中收口。两条主线各自准入，不能让 target 的未完成自动冻结 reference，或反过来。

若旧 maps 已有可信上界并通过当前资源准入，直接跑全体积，不把 compact 重构变成必做前置。若不通过，仅修复导致超限的表示/owner；准入包含首次作用的 coefficient packing、临时数组与原生 callback，不只包含 constructor。一次完整对象的受控前缀可以提供实际成本，不必另开一个 sample campaign 才决定能否继续。

**普通 bug 在本包内处理。** 保存真实失败 source/run/耗时，修复后冻结新 source，只复验受影响的数值或接口范围，继续已满足依赖的工作。表示/回读修正可对旧 raw 做独立 postfix；数学、MPC、索引或归一化真正改变时补相应数值验证。不得把更换 source 自动解释为所有旧证据失效。

仅在真实 input/ABI 不一致、数学检查失败、明确资源/磁盘门或固定截止时停止受影响路径。未实现应明确写 IMPLEMENTATION_INCOMPLETE，资源上界仍不完整应列出具体未计对象，不能用 NOT_QUALIFIED 同时替代原因、容量和行动。新数值代码放在可复用 src core，service/checker 保持编排和回读，不另堆一份完整 solver。

## 8. Response V25 的实质完成标准

下一份 response 必须先回答以下问题，再列测试和行政信息：

1. **全 target volume 是否实际覆盖全部 30,464 cells 和 29/60 类？** 给 S 作用、凝聚 RHS、全域恢复和独立原生 residual；若失败，逐项列出数值与门，不能只给总 PASS/FAIL。
2. **完整 owner 的内存与构建/作用时间是多少？** 列真实 maps/expansions、class 借用/复制、原生 packing、provider、向量及 cleanup；区分 derived upper 与 simultaneous peak，说明最贵阶段。
3. **selected-reference-q 实际是哪一个 sector/branch、多少行、多少 aliases？** 全行列、全端口及双侧 q 投影是否完成；target 与 reference 身份分别给出。
4. **交付到哪个层级？** counts、完整 streamed action、完整数值 row tiles、完整 CSR 分别报告。给实际 nnz、dtype、字节、磁盘、hash 和可恢复入口；不将前一层写成后一层。
5. **缓存到底省去什么？** 给 selected-q 的生成、写盘、重载、两次不同非零输入 replay、实际 generation 次数与共驻峰，不再用 32-mode 比例替代完整对象。
6. **生产调用链是否接通？** 指明真实 caller/owner、哪一层还保留 full carrier/all-q 默认；有限 helper 通过不等于完整 target+PC+RHS 路径已完成。
7. **离 2 TB/48 h 还缺哪些实测？** 用本轮真实数据更新容量与时间账，显式计入 V19 每次 PC 的重建生命周期；未测 factor、其他 q 和原尺寸迭代数继续标 unknown/predicted。
8. **为什么继续或停止？** 给具体 gate、剩余时间、可直接复用产物和下一条执行入口。两条主线均为主交付；只完成一条应明确部分完成，不能以另一个有限 panel 宣布全包完成。

本报告对 V24 的阶段判定为 **pass_with_qualifications**；完整原尺寸 solver、最终精度、2 TB / 48 h 和 master 合并资格继续为 **not_qualified / do_not_merge**。V25 的职责是把已经证明有用的局部机制接成完整原尺寸对象，尽快得到下一次因子/整场准入所需的真实数据。

## 附录 A：本次远程内容 SHA-256 复核

下表 12 份文件按本次 HEAD 读取的精确 UTF-8 内容复核，字节数与 run index 登记全部一致。该复核证明已审阅版本的内容身份，不替代大型 raw artifact 数值重算。[R7]

| 文件 | bytes | SHA-256 |
|---|---:|---|
| response_v24.md | 15,257 | 35a1dd87038e6ff887a40899f675abc246e6f66feeebabd3c64c2c4ac2182dc2 |
| README.md | 22,566 | d4be9a81076f59653567e4dd4fe9fe3e58f8cacb3bdf73dffe6580bc6ae32385 |
| outcomes/summary.md | 170,747 | adfe22724ec04f84b41a8b3a7014ede983dff50fab73b44783d5cf10c7320400 |
| outcomes/test_summary.md | 73,401 | 0b340ab02be0aa243b540653f67068a63b8cbacd6bbdf750e336442e30a9ba77 |
| outcomes/records/target_operator_probe_v24.json | 23,405 | e6bf6ca501f4b982c03692164aec1f5e293b644a11c327776afa288e1d7ad2ab |
| outcomes/records/production_support_v24.json | 8,794 | b5adee195c5a0fd1d2983a39b66a5b6c5051581a2d375126f68e9c820e4afda0 |
| outcomes/records/performance_v24.json | 9,596 | 0efb983e7d7ff3798d64ad843864bbb915e02cd9be85fb501d918e23c3e26d68 |
| outcomes/records/review_v24_incremental_workflow_ledger.json | 14,385 | f9756a2e335ae4d734ac9fe8c508cc62589e35ac4f8342fd8c8a862ddca65175 |
| outcomes/records/q_tile_v24.json | 12,568 | 918896011ecf9fc9179db0f430b515867ccac3c0611070a1eca2be9bb6d07f7e |
| docs/development_progress.md | 273,018 | 1921b6e00151d790b41882571e4a4e1d1d96eb183d59f39eeeb0c2ea55389927 |
| docs/development_model_registry.md | 291,753 | 687a0ff53af8c4863192a233ec9987191b2bf00f14ef9eea566620d4b8b81f0a |
| docs/README.md | 31,668 | 4b532e8119b427177a9932fa3d6253149c57b2058a1aeb0eb4ff590314ba4036 |

## 附录 B：冻结来源

除 R23 指向上一份 review 的原提交外，以下来源均固定于本次审阅 HEAD。正文行号只用于定位当前实现，不把源码推断标为实测。

- [R1] V24 响应
- [R2] V24 operator compact
- [R3] V24 support/reuse compact
- [R4] V24 性能与资源
- [R5] V24 q tile
- [R6] V24 账本与停止决定
- [R7] 运行及文件索引
- [R8] 真实端口、缓存与 probe
- [R9] 真实 edge panel
- [R10] 体积凝聚与约束映射
- [R11] P6 action/RHS/recovery
- [R12] 原生端口 iterator
- [R13] reference/sector/V17 构建与 PC
- [R14] 完整 worker 调用
- [R15] service 与独立回读
- [R16] 窗口登记
- [R17] stage 结果分类
- [R18] 只读 checker 入口
- [R19] 独立原生体积组合
- [R20] 原生 form action/MPC
- [R21] 历史及 V24 结果总表
- [R22] 测试与未运行范围
- [R23] 前一份 Review V24
- [R24] 任务目标
- [R25] 单 q 因子生命周期

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/response_v24.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v24.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/production_support_v24.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/performance_v24.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/q_tile_v24.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/review_v24_incremental_workflow_ledger.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/task40_v22_operator_probe.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/task40_v24_real_edge_panel.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/hcurl_assembly_time_condensation.py
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/p6_cell_condensed_action.py
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/fullspace_dtn_action.py
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/task40_v10_p6_yorbit.py
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/runners/task40_v10_worker.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/scripts/task40_v20_service_workflow.py
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/runners/task40_v10_campaign.py
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/runners/task40_v20_stage_runner.py
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/scripts/task40_v21_readonly_recheck.py
[R19]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/fullspace_physical_action.py
[R20]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/fullspace_mpc_action.py
[R21]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/summary.md
[R22]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[R23]: https://github.com/Rookie1234567/MyFEniCS/blob/92a59c167b53f828cc0408eca664d0eebc878428/docs/task40extra_0p7nm_engineering/review_report_v24.md
[R24]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/docs/task40extra_0p7nm_engineering/task.md
[R25]: https://github.com/Rookie1234567/MyFEniCS/blob/c1a77d362d852d864668dcf5d43957880a6788df/src/solvers/task40_v10_p6_mumps.py
