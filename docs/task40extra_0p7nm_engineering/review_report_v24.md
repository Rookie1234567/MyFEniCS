# Task40extra Review V24：复用完整支撑证据，先跑真实 q，再解决重复生成成本

## 0. 本轮判断与推进决定

**V23 已经完成一项会改变原尺寸内存方案的工作：在原有两级生产筛选后，32,060 个模式的 B、D 均只保留真实端口面上的 trace 行，全部单元内部支撑为零。接下来应直接利用这个结果，运行已有 q-only 路径，并测清端口数据反复使用的成本。** 不再以相同定义的支撑扫描作为下一轮起点。[R1]、[R2]、[R3]

这里的 trace 是单元边、面上的自由度；单元内部自由度可通过局部消元消去。B 把端口幅值送入有限元方程，D 从有限元场提取端口作用，H_p 保存原始端口归一化。B、D 内部支撑为空，意味着当前生产算子的端口项无需内部逆作用修正；体积 Maxwell 算子的局部消元仍然需要。

| 问题 | 本 review 的决定 | 依据与范围 |
|---|---|---|
| V23 有没有实质进展 | 有：原尺寸全模式支撑闭合，紧凑边界路径有数值对照 | measured；32,060/32,060，24 个 compact/full 对照 [R2]–[R4] |
| 上轮要求的内部 m_c 是否完成 | 完成；接受 B、D、并集的零直方图与零二阶和 | 沿 Review V23 第 3 节的内部支撑定义 [R3]、[R13] |
| 是否重做完整扫描 | 默认不做；使用保存的终端 checkpoint | 旧证据完整，失败发生在其后的 q 叶子 [R2]、[R5] |
| 下一轮第一个数值交付 | 原尺寸真实 q0 的一列 C、一行 −D 和 H 的回读结果 | 复用已实现的 q helper，不等待体积 LU 或完整 q [R7] |
| 下一轮主要性能工作 | 32–64 模式块的首次生成、缓存复用、重新生成对照；消除逐行 Python 映射和重复 sweep | 已定位实际生产接口 [R8] |
| 是否换一个预条件器 | 不换；继续既定 p6 reference、V17 有界行块构建、V19 单 q 因子驻留路线 | 先使既有算法能在原尺寸上经济地执行 |
| 结果资格 | 阶段进展 PASS_WITH_QUALIFICATIONS；最终场、2 TB / 48 h 和精度仍未资格化 | q CSR 0/8，factor/KSP/完整场未运行 [R5] |

本报告声明一个新的 V24 固定工作包。完成第 7 节内已满足依赖的工作后集中收口；普通 axes、shape、schema、path 错误在包内修复并继续。第一份真实 q 回执不能再次被一遍已经完成的 2.45 h 扫描挤掉。

## 1. 冻结身份与审阅证据

| 项目 | 冻结值 |
|---|---|
| 仓库 / 分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 本次审阅 HEAD | `84dce5a39eb34a259166f34e063312a2cd86ef0c` |
| HEAD 时间 / 说明 | 2026-10-10T15:06:49Z；Task40 V23: record full-mode boundary scan and unfinished q-tile qualification |
| 完整扫描实际源码 | `1291aeef089e6c02c4b9e28125f60072aa769340` |
| 后续 axes / q-only 修复源码 | `43588de8275a1014375ab8d5fdd1d835b0bcee55`；修复后的真实 q 未运行 |
| 输入 SHA-256 | `33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff` |
| 物理模型 SHA-256 | `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` |
| 模式清单 SHA-256 | `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d` |
| 审阅日期 | 2026-10-10 UTC |

相对 Review V23 提交 `32a7293233985083ae5024b275b39fbdc7c56ab2`，最新结果包含 5 个提交、23 个变更文件。本次读取 response、四份数值/资源 compact、账本快照、run index、summary/test summary，以及实际 provider、probe、service、stage runner、campaign/checker 源码；8 份正文/compact 内容的 SHA-256 与提交索引一致。ordinary target worker 未在本轮修改，不能推断完整生产入口已经切换。[R1]–[R12]

大型 NPZ、原始日志和执行机目录没有在本次远程审阅中下载重算或运行。实测量引用已提交的 compact 及其主控读回记录，源码用于核对作用范围；本报告不将远程审核称为独立数值重跑。文件 hash 复核见附录 A。

## 2. V23 已经测清的内容，应当直接用于工程决策

### 2.1 全模式生产支撑完成

模型使用原尺寸 50×25×140 nm、0.7 nm、真实非可分 Si/air 几何。当前 272×8×14、p6 网格是原尺寸资源与算子 pilot，尚未取得最终 y/z 离散精度资格。

| 指标 | V23 数值 | 数据身份与含义 |
|---|---:|---|
| 单元数 | 30,464 | measured；原尺寸 FE 空间 |
| storage / independent rows | 20,181,348 / 19,897,344 | measured；原生向量与约束后自由度 |
| interior / trace rows | 13,708,800 / 6,188,544 | measured；体积内部与边面自由度 |
| finalized MPC slave rows | 284,004 | measured；全局周期约束已经施加 |
| 模式覆盖 | 32,060 / 32,060 | measured；bottom/top 各 16,030 |
| 每侧端口面数 | 2,176 | measured；每个模式覆盖其所在一侧的全部端口面 |
| 紧凑候选行数 | 3,177,132 | measured；storage rows 的约 15.74% |
| 每侧 B、D 各自保留模式行项 | 2,429,660,672 | measured；全部归入 actual_port_face_trace，按模式累计 |
| interior / other trace / slave / unknown 保留项 | 全部为 0 | measured；B、D、两侧分别统计 |

来源：[R2]、[R3]。两级筛选均保持全局相对阈值 10⁻¹³、绝对 floor 为 0；第一层是 MPC 归并后的 component，第二层是加权组合后的 functional。24 个同场、同 α 的 compact/full 对照覆盖非平凡 MPC，其 component rows、第一层 masks、values 及该分量的 Bα、Dx 作用精确一致。这是每侧首/中/末及 s/p 的 12 个 mode 实例各测两个 component，共 24 个 component 级调用；不能写成 24 个独立完整 B/D functional 对照。后续加权组合沿旧代码，完整 32,060 模式的最终支撑另由全扫描统计。[R3]、[R4]、[R7]

**接受内部 m_c 这一门已经关闭。** 它表示一个边界相邻单元的 450 个内部行在多少个模式中出现保留 B 或 D 支撑。两侧分别 2,176 个单元，B、D、并集的直方图均只有 0-bin，Σm_c、Σm_c²、最大值均为零。response 后补的“全部 882 行的整单元 m_c 尚 UNKNOWN”是另一个统计量；不得用它撤销已完成的内部支撑结论，或要求下一轮重新扫描才能继续。[R3]、[R13]

该结论不等于原始积分严格为零。代表性未筛选 B 的内部最大绝对值约 8.92×10⁻¹⁶，原始 component 保留了 tiny nonzero 记录；旧字段 `raw_interior_row_memberships_by_side` 实际统计筛选后项，不能用来证明 raw zero。两侧代表模式的对照仍是共享生产内核的一致性检查，不能扩写为全部模式的独立原生积分资格。[R1]、[R3]

### 2.2 端口内部修正可以记为证书推出的零

对当前冻结的生产 functional，以 i 表示单元内部、t 表示 trace。全模式证据给出：

```math
B_i=0,\qquad D_i=0.
```

所以，按既有增广方程的消元符号，尚未施加 H_p 平衡缩放的端口凝聚项为：

```math
\widehat B=B_t,\qquad \widehat D=D_t,\qquad \widehat H=H_p.
```

体积 trace 算子仍然是：

```math
S=V_{tt}-V_{ti}V_{ii}^{-1}V_{it}.
```

端口作用本身仍然存在：进一步消去端口幅值，trace 方程的算子仍含下式中的 DtN 项。

```math
S_{\rm effective}=S+B_tH_p^{-1}D_t.
```

因此可将当前 target 的端口内部修正记为 `ZERO_BY_FROZEN_FULL_MODE_SUPPORT_CERTIFICATE`，同时保留 volume 为 `PARTIAL_NOT_RUN`。无需先做一遍局部 LU 来“测出零修正”；也不能因为端口修正为零而跳过体积凝聚、RHS、内部场恢复或原方程残差。

这一证书只覆盖冻结的 target 生产定义。向 filled-reference、twist/sector 迁移时，还须证明相应端口描述与变换等价：面、方向、外部材料、ordered keys、相位基准、H_p、全局 MPC、两级筛选，以及实际局部/全局归一化关系。现有 q helper 的 `PASS_COMPLETE_SAME_PORT_CELL_RECTANGLES` 只检查完整端口单元矩形一致，尚不构成这些条件的全部证明。该限定不阻止先运行 target 的真实 q0 端口投影；有限描述核对与代表性数值对照足以启动等价性证明，不默认再为每个 sector 做一遍 32,060 模式扫描。[R7]、[R8]

### 2.3 保留 q 负结果，同时保留完整扫描的成功

V23 前两次 attempt 分别在 0 模式时遇到 KeyError 和 checkpoint identity 错误。第三次在源码 1291aeef 上完成全部模式后，q helper 将单元数列表 `[272,8,14]` 当成 x/y/z 坐标映射，0.0892 s 后报 TypeError。worker exit 4 是真实 q 叶子失败，不能改成整条工作流 PASS；它也不应抹掉已经完成并保存的扫描输出。[R1]、[R5]

43588de8 已改读 resolved discretization 的 `mesh_axis_x_values/y_values/z_values`，并增加 q-only 入口。定向回执分别为 route/probe 19 passed、numeric stage 3 passed、q checker/readback 2 passed，py_compile 与 diff 检查通过；这些是代码与接口验证，修复后的实际 q 仍为 NOT_RUN。[R5]、[R12]

## 3. 重新计算内存账：内部条件项退出，端口复用值得实测

### 3.1 不能继续把旧条件情景当作内存下界

Review V22 的 2,471,268,925,440 B 是“每个边界单元耦合本侧全部模式，相关 Bi/Di、内部逆作用和凝聚端口项全部缓存”的条件情景。当前 target 的内部零证书使其中依赖内部耦合的条件项归零；B_t/D_t 应由全局 direct provider 负责，避免按相邻单元重复拥有。不能继续拿旧 2.47 TB 情景判定这条路线必然超预算。[R3]、[R13]、[R14]

本轮 `actual_cached_bytes_deleted=0`，完整 carrier 从未分配；这是纠正方案和容量模型，不是实测释放了 2.47 TB，也不是实测 RSS 下降 155 GB。

### 3.2 direct 数据量已有依据，缓存应由时间收益决定

| 条件缓存组成 | 字节数 B | 数据身份与限定 |
|---|---:|---|
| B 的 complex128 值 | 77,749,141,504 | derived；4,859,321,344 个保留项 × 16 |
| D 的 complex128 值 | 77,749,141,504 | derived；独立计数，不假定 D=B 的共轭转置 |
| B+D 值合计 | 155,498,283,008 | derived；约 155.5 GB，尚未分配 |
| 每个 B/D 项各存一个 int32 original row | 38,874,570,752 | conditional；不假定可共享索引 |
| 每个 B/D 项再存一个 int32 active row | 38,874,570,752 | conditional；取决于映射布局 |
| 值 + 上述两种行号合计 | 233,247,424,512 | conditional；约 233.2 GB，另计 offsets、元数据、工作区和其他常驻对象 |

来源及算术：[R3]。两种 maps 本身合计 77.75 GB，233.2 GB 是值与 maps 三项之和。若沿用 int64 original rows，后两项组合会改变。每个全局行号虽可小于 2³¹，累计条目超过 2³¹；全量 offsets/indptr 的整数宽度必须另审，不能据行号范围选择全部 int32。

155.5 GB 约占十进制 2 TB 的 7.77%，并不能单独证明整机不够，也不能证明可以容纳全部 reference、CSR 和因子。应比较三种表示：只生成当前块、保留有界热块、在资源允许时保留更多可复用值或投影后数据。相同 B/D 条目数不证明每个模式的支撑完全相同；共享 maps 或其他压缩必须有对应等价性证据，不改变数值阈值。

按本轮平均支撑估算，64 模式的 B+D 值约 310.4 MB，连同两种独立 int32 行号约 465.6 MB。这只是试验规划量，实际仍按所选模式的条目、FE/MPC、q map、临时数组和 checker 共驻量准入；不能把全量 155.5 GB 缓存搬进当前 16 GiB 运行上限。

## 4. V24 首先运行 q-only，解决已经明确的接续断点

### 4.1 旧证据窗口与新执行窗口分别绑定

当前源码的 q-only 仍绑定过期 V23 window。只注册一个新窗口就运行，会再次在身份 Gate 前失败：

| 位置 | 当前耦合 | 最小处理 |
|---|---|---|
| service 696–716 | selector 要求当前 registration 等于 V23 固定 hash | 当前执行核验明确的 V24 scope；旧扫描仍核验 V23 hash |
| probe 4961–4979 | 要求 is_v23_campaign，且旧 scan window 等于当前执行 window | 分开 execution campaign 与 artifact campaign |
| probe 5036–5040 | 旧 checkpoint loader 使用当前 window hash | 传入冻结的旧 V23 artifact window hash |
| q helper 3733–3737、4353–4355 | 开始/结束都以 V23 固定窗口作执行权限 | 读取本次明确注册的新执行窗口并守时 |
| service 1183–1199 与 evidence root | partial checker 和路径仍按 V23/旧默认推断 | 新 run 验证 V24；附上旧 evidence 双链；新输出落到 V24 |

源码依据：[R7]、[R9]。不修改旧 checkpoint、旧 manifest、旧截止时间或旧失败；保留数值身份校验、当前资源门和当前执行截止。新增一个受限的 V24 注册与最小 resolver/loader 适配即可，不写通用历史恢复框架，不删除全部 window 校验。

新执行记录同时携带：本 review 身份、新 T0/scope/window/accounting、当前冻结源码，以及旧 scan source/input/model/modes/MPC、旧 window、manifest、checkpoint metadata/payload hashes。旧 source 与新 q source 可以不同，必须明确兼容范围及本次实际改变；不能把旧结果改写成由新源码计算。

### 4.2 复用已存在的启动入口和原输入

补齐上述接线后，沿用 `scripts/run_case_in_user_service.sh` 和既有 q-only selector。原 stage input 为：

```text
benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/target_operator_probe/target_original_ny8_operator_probe_v22.dat
```

追加既有 `--task40-v10-campaign-window` 指向登记的新 V24 window，`--v23-q-only-scan-checkpoint` 指向：

```text
results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261010T114302.254770Z
```

selector 的 v23 名称表示旧扫描格式，可以保留。首个 q-only 运行保持该 input 的精确 SHA，stop 为 `target_operator_probe`、`operator_probe_authorized=true`、`target_heavy_authorized=false`；不要为换窗口更改旧输入，或改用另一个 preflight case。这是修复后可执行的入口说明，当前 HEAD 尚未完成新窗口适配，不能直接声称上述续跑已可用。[R9]、[R10]

### 4.3 首个真实 q 交付的准确范围

现有 q helper 从完整模式表和原尺寸 profile 建立实际 sector/alias，选择 q0 的第一个实际模式；检查全域 edge/face orbit 的 trace 列序，对这个模式所在一侧全部 2,176 个端口面的支撑建立有限 q map。它不是任意两个局部 selector；但也只是一列/一行端口块，不是完整 q0 矩阵。profile 预期每 q 有 773,568 个 trace 行，q0 有 4,076 个 ports、增广维数 777,644；这些完整维数是派生预期，实际有限 q map 的 shape/nnz 要由运行回读。[R5]、[R7]

验收保存实际 q/r、twist、原始 mode key、alias、map shape/nnz/字节/hash、H_p、C、−D、H 的数值与逐项误差，报告生成/映射/投影/回读 wall、共驻峰值与释放。沿现有各项相对误差 10⁻¹¹ 门，H 的归一化保持原门；不让大体积范数掩盖端口漏项。

该 helper 用冻结 production B/D/H 后的 fresh provider replay，再对比逐实体求和与 CSR 乘法。两边仍共享 surface production iterator 和部分变换构造，因此验收名称应限于生产接口重放、投影代数与回读一致性；不能称为独立原生积分 oracle 或完整 reference inverse 通过。B 投影采用 Q 的共轭转置，D 的列式存储对应 Q 的转置，H_p 两侧缩放后为 1，不能给 D 额外增加共轭。[R7]

首个模式通过后，在同一 FE/MPC/orbit inventory 上扩展有限模式块。可按 side×q 的 16 个分组各选一对真实 s/p 模式，形成 32 个；余量至 64 个用于 alias 端点、H_p 极值或适用的近截断模式，覆盖四个 sector 的两种 branch，兼顾相邻模式的复用。完整 32,060 模式的 metadata/q/H_p 分配可以轻量全查，数值投影只测上述有限集合。每个选定模式仍包含其完整原尺寸前驱端口面，至少做一次多模式联合 Bα/Dx，并保存实际 base/slot/transform 身份；不用先分配完整 global q map 才允许该试验。[R7]

## 5. 48 h 主线：让真实生产作用可以反复使用

### 5.1 目前测得的时间不能直接当作一次 Krylov 迭代

| 指标 | 实测 | 正确解释 |
|---|---:|---|
| full-mode scan wall | 8,817.046 s，约 2.45 h | 包含支撑库存/审计的扫描阶段 |
| process CPU | 9,642.056 s | 与 wall 不同口径 |
| workflow monotonic | 8,866.383 s | 工作流计时 |
| watchdog conservative | 9,703.518 s，约 2.70 h | 含 UTC/monotonic 正差的保守计费 |
| component timer | 1,802.561 s；32,084 calls | 含主扫描 32,060 次与 24 个选样调用 |
| 24 对照 compact/full wall | 1.782 / 3.016 s | 1.692 倍仅属于这 24 个 component 级样本 |
| process-tree RSS peak | 3,060,957,184 B | 全部任务后代同时 RSS 采样峰 |
| dedicated cgroup peak / cap | 3,238,825,984 / 17,179,869,184 B | 约 3.24 GB 实测峰，16 GiB 上限 |
| task process-tree / cgroup swap | 0 / 0 B | PSS disabled；外部 descendants 已清场 |

来源：[R4]。component 的 integral/MPC/filter 桶也包含 scatter、abs/count、hash 等不同工作；约 1.8 ks 与约 8.8 ks 的差额不能全部归到纯积分或某个 Python 函数。下一步只需在有限代表模式上做互不重叠的计时，把生成、组合/筛选、分类/映射、作用/投影、hash/checkpoint 区分开，避免为测性能再跑完整诊断扫描。

### 5.2 已找到会重复付费的实际接口

`P6GlobalDirectCarrierProvider` 已实现，且 reduced/full B/D 与 contribution seam 已接入；应使用它，不重写一个新 provider。[R8]

但它每次调用都重新遍历 `entry_factory`。其 `_direct_component` 在 461–464 行为每个 retained row 做 Python 标量 original→active 查表；按本次总条目数，一次完整 B+D 消费最多涉及约 97.19 亿次这样的映射操作，尚未包括积分和其他处理。当前 q helper 的查表还逐项调用 searchsorted。这个实现可以先证明正确接口，但需要测量和向量化才可能支持反复迭代。

此外，`iter_reduced_contribution_layouts` 的 2375–2390 行虽然只产出布局，也调用生成 B/D 的 iterator；随后 numerical contributions 又遍历一次。分开 `add_B_full`、`add_D_full` 还可能再次生成。按已有 operation/sweep 计数记录实际调用，不能把“metadata”“单 q”标签当成零生成成本；8 个 q consumer、symbolic/numeric 两阶段和每次 PC 的重复成本都要算。[R8]

### 5.3 在同一真实模式块上做三种对照

| 路径 | 要测什么 | 工程决定 |
|---|---|---|
| cold generate | 首次生产 B/D、rows/active map、投影与必要分配 | 构建费与峰值 |
| warm reuse | 保留同一有界块，至少两次用不同非零输入重新作用 | 确认真的复用数据，测重复使用收益 |
| regenerate | 释放块并重新生成，再用同一测试输入作用 | 测流式节内存的时间代价与数值一致性 |

在第一份真实 q 回执之后进行最小优化：将行映射改为有界数组查找/向量化，复用冻结支撑和 mode metadata，避免布局预审无意生成同一数值载荷，联合需要的 B/D 消费。保留两级筛选、累加次序的适用等价要求、原 H_p 与独立 D；若改变了浮点顺序，报告原门下的实际误差，不用新容差掩盖差异。

记录每个 owner 的 unique backing、alias 与同时存活生命周期；有限 block 结束后检查借用对象释放，防止 provider 闭包或消费者留住全模式数值。尤其将 provider 接入长寿命 action 时，应在 destroy/release 中明确断开新 owner/closure 引用并检查实际存活对象；worker 退出和外部清场不等于内部释放已证明。现有“streamed”或“cached”字段名不作为内存证据；direct-only 构造路径中空 local cache 合法，实际拥有对象才决定成本。

是否缓存，用实测重复次数和成本决定：

```math
\Delta T_{\rm build}
<
K\bigl(t_{\rm regenerate}-t_{\rm warm}\bigr).
```

K 是完整路径预计真实使用次数；该不等式只是时间决策，还必须同时满足峰值内存。先缓存昂贵且会复用的 maps/投影后块或热模式块，是否保留全量值留给真实整机预算判断。不要先验禁止缓存，也不要将磁盘/OOC/swap 当作未计价内存。

## 6. 真实 q 之后，连续推进体积、生产接线与完整 q 成本

### 6.1 一个端口块通过后，进入真实体积作用

先复用 `assembly_time_geometry_class_counts` 在实际 mesh/tag/permutation 上取得 raw/oriented class 整数，使用 `preserve_exact_geometry=True` 与既有物理 action 一致的精确几何 key。它不生成局部 tensor；沿 `assembly_time_condensation_capacity_facts` 计算完整 class cache 与临时空间，不新建另一套容量公式。[R18]

例如 p6 的 882 总行、450 内部行、432 trace 行，在 complex128、4 B 局部 pivot 索引、8 B real 且保留 Schur 的条件下：一个 raw tensor 为 12,446,784 B，一个 oriented class 的 LU/两块 cross/Schur 保留量为 12,448,584 B，单 identity 为 1,620,000 B，局部工作窗为 52,774,920 B。这些是源码公式的条件值，实际必须读回 dtype/class 数，并另计 raw cache、oriented tensor cache、Schur workspace、FE/maps 与共驻对象，不能只乘保留量。[R18]

若真实容量允许，可用已有 `materialize_global_matrix=False`、`retain_local_schur_for_matrix_free=True` 的凝聚入口建立完整原尺寸 volume class cache，并完成一次有界原尺寸 volume action；该推进不需要全 q CSR 或全局 MUMPS 因子。若完整 cache 不准入，有限 panel 需要一个小 seam 复用原生 FFCx 882 行 cell kernel、orientation、局部 LU 和 Schur primitive；现有 builder 没有 cell-subset 开关，不假称直接传一个参数即可完成。有限 450×450 局部 LU 明确属于本包 volume 工作范围。体积构造继续使用 `sum_duplicate_cell_integrals=True`，或等价地累加全部 default/tag kernels，并保留原 quadrature 与 `preserve_exact_geometry=True`；不得覆盖同一 subdomain 的多个积分 kernel。现有 builder 的该 flag 默认 False，不能让新 panel 误用默认值。[R18]、[R19]

继续用实际映射和已经资格化的局部体积数据，产出一个有意义的原尺寸体积凝聚行块。行块指完整矩阵的一组真实行列；可选择一个真实 canonical edge 的 6 行或 face 的 60 行，收集其八个 y orbit/MPC 前驱的全部 incident cells；每个 cell 完成 curl+mass、原方向与局部凝聚，保留其完整 432 个 trace 列后再投影和累加。所选元素必须累加全部前驱 cell/轨道贡献，不能只放几个局部矩阵后称作全局块。target 非可分材料在 q 基下可能有 q≠r 耦合，分析 target 时保留实际交叉块；reference 的可分结构不能直接套到 target。

对该行块分别报告 S、C、−D、H 的覆盖与误差。端口内部修正按第 2.2 节记证书零；volume 需要实际局部消元资格。旧 top known-forward 的 1.488391772882517×10⁻¹¹ 大于 10⁻¹¹，仍保留原负结果；沿已有 same-LU 最多 3 次有界修正处理，不放宽门。它影响对应恢复/逆资格，不阻断已经独立的 q 端口块、支撑复用和吞吐试验。[R7]、[R13]

### 6.2 完整生产 worker 仍须替换实际拥有数据的入口

当前 ordinary worker 仍先构建 same-mesh carrier，再遍历 `carrier.entries` 得到支撑，并以 `from_carrier(..., port_coupling_mode="cached")` 构造 action。本轮改动没有消除这条路径的全量驻留。q helper 使用有限 selected-row owner，只能证明该 tile 的接线，不能称整个 target action 已有界。[R8]、[R13]

V24 在相同 profile 的显式 opt-in 路径中推进真实连接：完整模式 metadata 与内部零证书 → 实际 condensed trace constraints → global direct provider → reduced action / B/D → 非零 RHS、恢复与原方程残差接口。先以已存在的真实有限数据做贯通验证，避免为接口测试另建一场小 PDE；不要求等待完整目标矩阵全部装好才开始改调用者。reference consumer 的完整 q/sector 变换与 H_p 局部归一化分别核实。当前合法 direct-only 路径不需要混合 generated/cached cell；对尚未资格化的混合配置明确拒绝或局部补齐，不能声称任意混合已通过，也不为此拖延零内部主线。[R8]

### 6.3 将 V17 有界行块构建推进到可决策的容量结果

取得实际 q map 和有限数值块后，测 V17 row-tile consumer 的真实索引宽度、去重后 nnz、同时存活 CSR/临时 COO/映射、跨阶段数据持有和 build 时间。按结构类别及轨道覆盖记录“已测/可精确推导/仍未知”，不能由一个容易的 tile 直接线性外推全部因子。

约 T0+150 min 做一次可选晋级判断。旧高层 reference builder 会先建立全局 physical bundle/carrier，再遍历 twists 建 local carrier；不能直接调用它并把运行标作“只建一个 q”。先确认已存在真正的 selected-q 流式入口、全部所需 port modes/H_p/volume 覆盖、局部资格和全阶段整数容量上界，且实测成本支持在截止前完成；否则按计划完成 volume panel 与 V17 行块，不为这一可选项重构整个 reference inverse。[R19]

本包允许在上述资格与实测保守容量支持下继续到**一个完整 reference q CSR 的构建**，作为可选进阶，不作为本包完成硬指标：当前执行机的动态 cap、host reserve、16 GiB 专用上限与剩余窗口均须覆盖构建峰值及收口；采用任务专用、明确登记的 build-only scope，不能把 q-only 的 `target_heavy_authorized=false` 偷换成通用重型授权。准备相应 stage input/manifest，绑定与原物理模型一致的身份，由既有主控按本 review 登记即可，不逐阶段再请求聊天审阅。

若完整单 q 无法安全容纳，交付有界 V17 行块、结构计数和具体缺口：矩阵/转换峰值多少、哪项尚未知、完整单 q 需要什么容量或表示改动。不要尝试 OOM 来找边界，也不要只写一句 NOT_QUALIFIED。当前包不默认启动全 8 q、MUMPS symbolic/numeric、KSP 或完整 PDE；完整单 q 的构建条件没有满足时，继续独立的有限数据工作，不耗光窗口等待它。

三个 MUMPS lifecycle fixtures、one-q inventory producer/wrapper 层级与 native cleanup 是进入相应 factor/完整运行前的必要工作，可按真实依赖集中修复；它们不是首个 q-only 的先决条件。profile 驱动的 q_count 已在新 checker 路径修复，不再把历史 E2 的 4-q 兼容代码一概当成新 target bug。外部 descendants 清场不能代替 worker 原生 owner 的释放证明。[R9]–[R12]

## 7. 新 V24 工作包：结果顺序与固定窗口

旧 V23 T0 为 2026-10-10T09:00:51Z，数值 cutoff 14:40:51Z，总 deadline 15:00:51Z。seq 34907 已记 closeout-only/no-q-launch；seq 34908 在 15:06:15.543465Z 的行政快照已超总截止 324.543 s。保留原账与 ADMINISTRATIVE_CLOSEOUT_OVERRUN，不续用旧余额或重命名旧 attempt。[R1]、[R6]

| V24 项目 | 合同 |
|---|---|
| 新 scope | 旧终端扫描的受限复用、真实 q 端口与模式块吞吐、bounded provider 生产接线、volume class/局部凝聚/有界原尺寸作用、实际 V17 行块与第 6.3 节条件单 q build |
| window 建议路径 | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl/campaign_window_v24.json` |
| T0 | 本包第一项实际实现/测试/准备开始时一次冻结；不等到数值启动才计时 |
| 总窗口 / 收口 | 21,600 s；预留 1,200 s，数值最晚于 T0+20,400 s 停止 |
| 计费 | 准备、修复、测试、等待、失败、运行、文档、提交/推送和回读均计；UTC/monotonic/保守计费分列 |
| 资源 | 同时一个 heavy；同一已资格化本机 ABI；16 GiB 专用上限、动态 cap、host reserve、任务 swap=0 |
| 到期 | 保存真实前缀、清场、集中回应；不刷新 T0，不用行政收口延长数值时间 |

以下是计划分配，不是强制中断正在正常完成的合格短任务；主控按已测成本调整顺序，并保留固定总截止：

1. **前约 45–60 min：最小修复与第一份 q-only 实跑。** 旧/新窗口分离、原输入/axis/身份、定向测试、读取完整旧 checkpoint，尽早启动实际 q。不要先做全扫描、全测试或泛化重构。
2. **随后约 60–90 min：真实模式块与复用对照。** 复用 FE/MPC/orbit，扩展 q/mode 范围；记录 cold/warm/regenerate、生成次数、row mapping、投影成本与内存，并取得 volume class census。明确改完一个热点的实际收益；约 T0+150 min 决定是否具备完整单 q 的可选晋级条件。
3. **其余数值时段：推进生产接线、体积与 V17 行块。** 按依赖交错开展短验证；volume 容量足够可完成原尺寸 volume action，完整单 q 晋级条件满足则做第 6.3 节 build，否则完成真实完整依赖 panel 并给具体下一阶段预算。对应局部数值未通过只暂停依赖部分。
4. **最后 1,200 s：提交与回读。** 预留真实文档/索引工作量，避免再把整个工作包拖到总截止后才开始行政收口。

同一 canonical worktree `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`、同一分支、同一 Codex 聊天连续执行。执行者负责实现、测试、运行和证据，不 commit/push；既有主控冻结源码并集中提交/推送。显式 `/bin/bash`、`login:false`，同一 shell 中 activation 与 ABI preflight。不开新 checkout/worktree，不 SSH、不迁移工作站、不改 master、不使用执行侧 collaboration subagents 或自动化。[R15]

正式 attempt 绑定冻结源码，不热改运行中代码。普通 bug 保存旧失败，局部修正后只复验实际受影响范围并继续；真实 input/ABI/数值不等价/资源门保持有效。不要以增加一项无关统计、修饰日志或等待下一轮 review 替代已经可执行的数值交付。

## 8. 下一份 Response V24 必须回答的实质问题

| 必答问题 | 可核验交付 |
|---|---|
| 复用了哪些旧成果 | 旧 source/window/checkpoint 的双身份回读；未重复全扫描；内部零证书适用范围 |
| 真实 q 到了哪里 | 首个真实模式与扩展模式块的 q/r/alias、完整前驱覆盖、C/−D/H、map/nnz/bytes/time/hash；完整 q 计数单列 |
| 重复端口作用多贵 | 同一块 cold/warm/regenerate、不同非零输入、sweep 计数、映射/生成/投影分项、实际优化前后结果 |
| 内存实际改善什么 | 真实省掉或避免的对象、unique backing 和共驻峰值；155.5/233.2 GB 条件估计与实测分开 |
| 生产入口还差什么 | caller→provider→consumer/RHS/recover/residual 的实际覆盖；ordinary/reference 未接入部分逐项列清 |
| 完整单 q 下一步是否可做 | 实际 volume class census、局部凝聚/action 或完整依赖 panel、V17 行块结果，完整 q build 实测或具体容量缺口；不将 tile 通过记成 q 矩阵通过 |
| 原尺寸求解何时可启动 | 明确已闭合与未闭合的原方程、reference 逆、q/因子容量及时间依赖；给一个具体后续执行对象 |

提交 `response_v24.md`，必要 compact、outcomes summary/test summary/run index、模型总账与项目进展。大数组和日志留 ignored artifacts，compact 记录路径/hash/命令/source/ABI 与真实负结果。优先复用既有 schema，避免为每个计时桶新造一个权威文件。按依赖组说明 production core、service/checker、compact/docs、research-only、do-not-merge；保持 ordinary default 的 opt-in 边界。

数值/接口改动做最小有意义的测试：新旧窗口分离、旧 checkpoint 不可变、真实 provider 的 B/D/H、重复作用、映射和回读、改变的 contribution/cleanup 路径。未受影响的昂贵 PDE/完整回归不重跑；不能以 fixture PASS 替代原尺寸 q 的实际运行。主控给精确完整 HEAD/base、工作树、变更文件、最终 hash 索引与账本 as-of，并核验 GitHub 公式和表格。

## 9. 从当前结果走到 2 TB / 48 h 的明确条件

小模型的最低退出条件已经在前期关闭，V23 又完成原尺寸全部端口面的生产作用。后续不需要通过“再减少几次小模型迭代”才能进入真实 q/算子阶段。当前重点是同一预条件器的内存表示、重复执行成本和生产完整性。[R13]

整机预算按时间上的共驻峰值计算：

```math
\max_t\left\{M_{\rm task}(t)+M_{\rm OS+other}(t)\right\}
\le 2{,}000{,}000{,}000{,}000\ {\rm B}.
```

M_task 包含 FE/MPC、体积局部数据、端口、reference/q/因子、Krylov、恢复/输出/checker 及其临时对象。单 q 因子驻留减少同时存活因子，但如果每次 PC 重做 numeric，就必须把重分解时间按实际次数计入。

完整单场时间为：

```math
T_{\rm total}
=T_{\rm prepare+setup}
+N_A t_A+N_P t_P+N_R t_R
+T_{\rm vectors+recover+output+checker}
\le172{,}800\ {\rm s}.
```

这里 A 是实际 target action，P 是完整 PC apply，R 是额外原残差检查；相互嵌套的时间只能记一次。由端口扫描不能确定这些量，也不能用 24 个样本的 1.69 倍速度或小模型迭代数预测 48 h。完成真实完整路径的计时后，才可计算可容许的迭代次数，并识别需要缓存还是减少因子重建。

首次原尺寸受控求解的前置条件是：原尺寸算子、RHS、恢复与残差接线完整，reference 逆具备适用资格，实际 q/因子/向量工作集和时间可以准入，资源监控与停止可用。**完整 A6 通过是求解后的成功门，不是允许第一场原尺寸求解的前置成功记录。**

最终目标仍要求原 50×25×140 nm、0.7 nm、complex128、非可分材料、完整 Floquet/DtN 合同下的复 E/H、官方功率/体吸收与原 A6 门通过，任务 swap=0，整机物理内存不超十进制 2 TB，必要全流程不超 48 h，并取得任务要求的网格/阶次/模式精度证据。当前 Ny8/Nz14 pilot 即使解出，也只能先关闭该离散的工程可计算性；精度资格另由相应证据推进。[R16]

## 附录 A. 文件与接续证据身份

下表 8 份远程 UTF-8 内容已重新计算 SHA-256，并与 V23 run index 对照一致。[R2]–[R6]、[R11]、[R12]、[R17]

| 文件 | SHA-256 |
|---|---|
| response_v23.md | `cd25a0262240b1060f87485123b45e5f5fd9973b3ee70ebfd32f90d1e27e0f5d` |
| target_operator_probe_v23.json | `4f3a8e4564eda345a998fb61a1aa95596619fe58695b93060b7e5652280935b0` |
| production_support_v23.json | `938cba5bee9f3e55a267c8c1d348d9cbe845133105d6580f2502102b32a2db69` |
| performance_v23.json | `8b258c244b4105157852cea7a4e21ecb44b43d0c4dd73d489340f26b046c1ca3` |
| q_tile_v23.json | `ead1d1a0ea3db56b96e71348275f1d860495a460b2e3e38547a7b0dd125021da` |
| review_v23_incremental_workflow_ledger.json | `6134a015616983a26fe66aace548fd8031d34418d76c5b6a3b3cca34f702dd02` |
| outcomes/summary.md | `4cf553bad5188105a2d3c2699b07c7eaf6949fac8976a4f2e6b84e0c45f23872` |
| outcomes/test_summary.md | `3c0bb4a19525fb1da131d84ba53959539d13babb669a4fcf81432711a4fe237a` |

旧 artifact window SHA-256：`e77793e53542c6094da819456457910893b33c9be5ca3b548482be6bfc3dbdfb`。旧 finalized MPC coefficient SHA-256：`9312e5f0ad152e517ffc5b7050951fe33ea75f2066bd2e6e7a40639e70366411`。

接续 checkpoint 目录：

```text
benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/operator_checkpoints/1045d9a34bd857e3e68a92258c485195d76986366aa23f410f79fe91d24fcc77/
```

metadata `v23_mode_sweep_checkpoint.json` 为 25,510 B，SHA-256 `f362583c0d34e8a37cb6077f8b244363b33f4f6dcc32de535c3c39b30b80eea7`；终端 payload `v23_mode_sweep_checkpoint_1.npz` 为 8,503,402 B，SHA-256 `63fb295da67b209a6eef7ed5d16df91c687aaa0e5e6860c6d391a5ca6a1a40f3`。原始 probe receipt SHA-256 为 `ca5df369e1d2464a78a63c76b3694d95cd8bd485d23754700cbb20ffeacb1c30`。这些大型/ignored 原始文件 hash 来自提交回执，供执行机实际读取验证；本次远程审核没有冒称重新下载核算。[R2]、[R3]

## 附录 B. 冻结证据与源码入口

除旧 review 外，下列链接均冻结到本次已审阅 HEAD；源码行号以该 HEAD 为准。

| 引用 | 内容 |
|---|---|
| [R1][R1] | Response V23 |
| [R2][R2] | 完整模式扫描 compact |
| [R3][R3] | 内部支撑、direct 库存与证书范围 |
| [R4][R4] | 时间、资源与 compact/full 对照 |
| [R5][R5] | q 负结果、修复与 NOT_RUN |
| [R6][R6] | 固定窗口与累计账本快照 |
| [R7][R7] | 原尺寸 probe、q map/helper 与 checkpoint 接续源码 |
| [R8][R8] | P6 global direct provider 与 contribution 源码 |
| [R9][R9] | service selector、注册与 partial checker |
| [R10][R10] | stage runner |
| [R11][R11] | 结果摘要 |
| [R12][R12] | 测试摘要 |
| [R13][R13] | Review V23：内部 m_c 定义、已有局部门与 worker 缺口 |
| [R14][R14] | Review V22：旧条件缓存情景与路线 |
| [R15][R15] | 本机执行边界与主控分工 |
| [R16][R16] | 原始任务物理、数值和精度合同 |
| [R17][R17] | 完整 run index 与文件内容 hash |
| [R18][R18] | volume class census、容量公式与装配时凝聚 |
| [R19][R19] | 现有 reference 高层构建、sector 与 q 路径 |

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/response_v23.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v23.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/production_support_v23.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/performance_v23.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/q_tile_v23.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/review_v23_incremental_workflow_ledger.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/src/solvers/task40_v22_operator_probe.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/src/solvers/p6_cell_condensed_action.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/scripts/task40_v20_service_workflow.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/src/runners/task40_v20_stage_runner.py
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/summary.md
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/32a7293233985083ae5024b275b39fbdc7c56ab2/docs/task40extra_0p7nm_engineering/review_report_v23.md
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/review_report_v22.md
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/AGENTS.md
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/task.md
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/src/solvers/hcurl_assembly_time_condensation.py
[R19]: https://github.com/Rookie1234567/MyFEniCS/blob/84dce5a39eb34a259166f34e063312a2cd86ef0c/src/solvers/task40_v10_p6_yorbit.py
