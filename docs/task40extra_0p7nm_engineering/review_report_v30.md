# Task40extra Review V30：接受 q0 分解资格，推进全 q 驻留参考逆与原尺寸 pilot

**审阅结论：接受 V29 的单 q0 准确分解、同因子两组 RHS 求解及保存数据独立复核。下一轮主线是补齐 q1–q7 的完整 CSR/native 资格，在同一轮全 q 构建中完成分解资格并保留准确因子，随后完成完整参考逆接线；资格、资源和剩余窗口允许时，直接在同一进程进入原尺寸工程 pilot。**

因子是矩阵经过昂贵分解后得到的可重复求解对象。V29 已测得“建立并检查一个新因子”与“使用现成因子求解”的成本差别，下一步应把这种复用落实到完整预条件器中。准确因子驻留会增加同时占用的内存，其价值要由完整共驻账和真实业务成本共同证明。

## 0. 冻结依据与审阅边界

| 项目 | 本次依据或决定 |
|---|---|
| 审阅日期 | 2026-10-12，Asia/Singapore |
| 仓库 / 唯一执行分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 正式交付完整远端 HEAD | `5823faf26e5425974645c2b1fc2b4004552b4324`；已回读分支确认 |
| V29 实际数值源码 | `bee9a1f0e33076e372607581f790bda3a4a0072f` |
| V29 修复后 checker 源码 | `9a9a9d31f4aebf1564d5f09177c1d3481d64371f` |
| V29 review 入口 | `e85992c79d7e2b3f41cd1396ffb06edccdd93421` |
| 延续的 V28 资格 | q0 COMPLETE CSR、三数组 hash、匹配 native PASS；不重新 producer/FE/MPC/pattern/fill |
| 本轮正式判断 | q0 生命周期 PASS，保留 `full_pass=false`、`official_result=false` 的全任务边界 |
| 下一主候选 | 复用现成 `ALL_Q_RESIDENT`；全 q symbolic 后统一准入，再逐 q numeric 并保留 |
| 新资源提案 | 同一工作站，1.5 TiB task cap、64 GiB host reserve、task swap0、12 h 固定窗口；**待用户批准，不是现有许可** |
| 合并状态 | 不批准 master 合并，不修改 ordinary default |

依据包括正式 response、operator/resource compact、run index、原始 checkpoint、失败 checker、两份后续审计及其脚本、执行合同和独立交接文件。数值源码到 checker 源码的差异只涉及 service checker 和两份测试；checker 源码到正式 HEAD 的差异是 40 份文档/证据文件，没有再次改变科学求解源码。[R1]、[R2]、[R3]、[R4]、[C1]、[C2]

本 Chat 审阅远端轻量证据及冻结源码，并核对已读取快照的 Git blob 身份和原始收据索引 hash。工作站上的大 CSR、NPZ 和 timeline 由发布的精确路径/hash 与独立审计绑定；本 Chat 没有重新运行分解、项目测试、FE 或大数组残差计算。下文“独立重算通过”指 V29 已保存的独立审计证据，不声称本 Chat 另做了一次数值重算。

## 1. V29 q0 资格闭合：可以作为下一轮的已接受起点

### 1.1 接受的数值范围

| 检查对象 | 原始结果 | 审阅判断 |
|---|---|---|
| 源矩阵 | 777,644 × 777,644；577,061,168 个结构槽；complex128/int32 | 复用 V28 COMPLETE CSR/native 身份 |
| CSR 有效载荷 | 11,544,333,940 B | 源三数组载荷；不等于求解峰值 |
| 首次 factor probe | 完整 CSR 真残差 `1.977628323114713e-14` | ≤ 1e-10，PASS |
| 同因子第二 RHS | 完整 CSR 真残差 `1.6069609784650353e-14` | ≤ 1e-10，PASS |
| 调用次数 | 一次 numeric、两次实际 MatSolve；不同非零 RHS | 同因子复用得到实证 |
| 独立 metadata 审计 | 28/28 PASS | 证明身份、路径、两代 window 和 payload 绑定 |
| 独立保存向量审计 | 7/7 PASS；两组全部 777,644 行 | 重算 RHS 与 residual 均逐位重现 |
| 审计新增计算 | 4 次完整 CSR MatVec；factor/MatSolve/FE/MPC/旧 native replay 均为 0 | 修复后的复核没有再次分解 |
| 结束清理 | factor/matrix/vector 当前计数均为 0，destroy 成功，后代清场通过 | 原生对象已释放 |

两组保存向量使用种子 260001、260101，包含 `input_x/rhs/solution/residual`；V29 采用 `rhs=A@input_x`。独立脚本从三数组打开完整 CSR，对全部行重算 `A@input_x` 和 `A@solution-rhs`，检查 NPZ/数组 hash、dtype/shape/finite、非零且不同 RHS 及源 CSR hash 未变。它是独立于 MUMPS 求解的保存数据复核；原算子的 native 独立性来自此前 V28 资格链。[R5]、[R6]、[R7]、[R8]

关键延续身份如下；后续 loader 应从原始收据读取全部字段，本表不替代完整 manifest。

| 对象 | SHA-256 |
|---|---|
| COMPLETE CSR manifest | ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290 |
| 匹配 native PASS | 63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81 |
| CSR data | 457b946f8e08557d82df38683a884d25ff58413f17ad1bb7f7e04a7296698c27 |
| CSR indices | 9279c5dbfb8921c61dc229ea6a99d30bb76f8b31d005076796d4504a1e7d0d6e |
| CSR indptr | 6d24828a2cd820601fedf92c5b6575fc2dd95a905c2533677f3a3367648a7819 |
| 原始 factor checkpoint | 0b9f892ffc81ff44a3a6ce3fa4796fd41d12e21e414fbe3bbda0a27f1e7a26bd |
| fresh NPZ | c737fadbb1df3a9ce1f9a9c5e1f23e9d8cade0e7bc1747769a02a21d13050b76 |
| 第二 RHS NPZ | 30d747721243858c030a5a77f5bdff30cef2e4ffae0c7e13d03ac28fed46f191 |

**V29 的 q0 因子已经销毁。** 新 worker 建立全 q 驻留组时，必须从现成 CSR 新建一次 q0 factor，并做本次 live factor 的资格检查；这笔必要成本正常计入 V30。保存 NPZ、manifest 或 Git commit 都不能恢复已经销毁的 MUMPS 原生因子。免重跑的是 q0 的矩阵生产及旧 native 资格，不是免除新进程的真实分解成本。[R5]、[R9]

### 1.2 时间结果与可以得出的工程结论

| 时间口径 | 实测秒数 | 使用方式 |
|---|---:|---|
| 原生 conversion | 10.592528 | conversion 父段 14.997011 的子计时 |
| 原生 symbolic | 19.370445 | symbolic 父段 19.504676 的子计时 |
| 原生 numeric | 625.776310 | numeric 父段 625.862622 的子计时 |
| 原生首次 MatSolve | 17.544153 | fresh 测试父段 22.092013 的子计时 |
| `F_q`，含严格初始 loader | **742.097546** | loader 30.286357 + 已加载后 fresh 资格父段 711.811189 |
| 原生同因子重复 MatSolve | **12.919099** | 纯回代样本；第二 RHS 完整测试父段为 17.433398 |
| eviction | 原生 3.352984；父段 3.863306 | 在 F_q 和第二 RHS 测试之外 |
| lifecycle 父段 | 758.410191 | 不含初始 loader，包含第二 RHS 和清理；不是 F_q |
| 原完整 service 父段 | **834.108298** | 含入口、运行和原失败 checker |
| 新 metadata checker 父段 | 31.717409 | 修复后只读复核 |
| 独立向量审计父段 | 73.240248 | 内部 70.666563 已包含 |

`F_q/S_q≈57.44` 是本次定义下“新建并资格化”与“原生重复回代”的成本比；numeric 约占 F_q 的 84.3%。这支持优先保留已建因子的工程选择，不能称完整预条件器或目标 PDE 已提速 57 倍。真实 PC 还包含折叠、映射、内部恢复、原生残差检查和可能的有界修正。[R1]、[R3]、[R5]

两次前置失败 32.873265、42.121692 秒与上述原 service、metadata、向量审计三个不重叠父段相加为 **1,014.060912 s**；这是已记录服务父段的和，不能冒充连续冷流程。最终工作包观测计费 **15,444.751283 s** 包括实现、转移、修复、测试、等待及审查；早期 14,195.026549 s 是同一账的旧快照，不再次相加。准备父区间 7,676.157757 s 包含较早 4,008.509563 s；历史冷流程中未记录的必要准备项、缺失前缀和未单测尾部仍保留 UNKNOWN。V28 已测的 q0 fill 等阶段继续有效，不因完整冷账尚未闭合而重新变成未知。[R3]、[R9]、[R10]、[R24]

### 1.3 内存结果与仍未知的对象分解

| 口径 | 实测或原始值 | 判断 |
|---|---:|---|
| 任务 cgroup 历史峰值 | **84,891,103,232 B，约 79.061 GiB** | 本次任务峰值 |
| 同时进程树 RSS 峰值 | **84,767,309,824 B** | 身份采样完整；不是各进程历史峰值之和 |
| task swap | 0 B | 任务范围通过 |
| PSS | null，未采样 | 不填 0 |
| 销毁前 cgroup current 样本 | 73,340,047,360 B | 同时存活对象的一个时刻 |
| 销毁后 cgroup current 样本 | 12,075,479,040 B | 文件页和其他残留仍计入任务 |
| INFOG19 | raw 63958；保守上界 63,959,000,000 B | MUMPS allocated 口径 |
| INFOG22 | raw 55242；保守上界 55,243,000,000 B | MUMPS used 口径 |
| INFOG9 | raw −2599；约 2.599×10⁹ 因子条目 | 百万粒度近似，不能按 MB 解读 |

销毁前后的差额包含 factor、PETSc 输入及相关对象的联合释放，不能称 factor 独占驻留字节。mmap 文件页也进入 cgroup；不以“数组来自文件”将它从内存账删除。INFOG19/22、RSS、cgroup 不同口径不能相减推独占所有者，INFOG9 的负值编码也不能直接当作 CSR int32 越界证据。[R3]、[R5]、[R9]

宿主初始已有 swap 20,787,200 B，原始记录继续保留。task swap0 不扩展为整机历史 swap0。V28 的约 80.885 GB 分解 envelope 原为派生预算；现在有 V29 实测，仍不能把旧预算说成永久下界或其余 q 的统一预测值。

## 2. 轻量问题直接修正，不重跑已接受的计算

| 问题 | 影响与处理 |
|---|---|
| `v29_execution_receipt.json` 中旧失败 checker hash 有一处抄录错误 | `partial_checker_sha256` 写了 `…c4929e9ff8994…`，实际原文件、收据索引和审计绑定为 `…c4929e7ff8994…`。在 V30 compact/勘误中给出正确权威指针；冻结 V29 原件保留。 |
| cleanup 子对象的 `status` 仍为 `IN_PROGRESS` | 顶层 `phase=cleanup_complete`、`destroy_succeeded=true`、计数归零和后代清场足以接受本次清理。下一版代码补终态字段，不为该字段重做 factor。 |
| resource compact 的旧 `mumps_units` 文字错误地把 INFOG9 并入 decimal MB | 与同文件后来新增的正确解释矛盾；规范化派生说明，保留 raw INFOG。 |
| 批准前字段与实际结果混列 | `proposed_resources_not_applied`、`target_runtime_copy_plan` 等明确标成历史快照，当前权威指向实际合同/执行回执；不再呈现“尚未部署”的旧结论。 |
| 原 run_summary 的 global swap 标签仍叫 WSL-global | 实际是 native Linux；未来输出改为 host-global，原始收据不改写，不扩大归因。 |
| 两个后续 audit parent 还带旧 16 GiB 树 cap、600 s closeout 等监督元数据 | 本次审计实际低于该容量且已结束，不推翻 q0 PASS。V30 必须把新合同传播到 service、launcher、worker、watchdog、所有 checker；在轻量 preflight 核对实际有效值，不能让完整参考逆 checker 被旧隐藏上限截断。 |

正确的旧失败 checker SHA-256 是 `3321692553c25c4929e7ff8994194ea45fbee80a7e4dc6fd3e134e7bf7c86015`。这些是记录一致性或下一轮监督接线问题；它们没有改变本次矩阵、两次解或独立向量审计。[R3]、[R5]、[R9]、[R11]、[R12]、[R13]

## 3. 其余 q 的完整 CSR/native：按真实 twist 成对推进

### 3.1 原尺寸工程配置的实际覆盖范围

当前 profile 的全局工程配置为 272×8×14=30,464 cells；两格 y 的局部参考 sector 为 272×2×14=7,616 cells。全局独立 FE 行 19,897,344，其中 interior 行 13,708,800、trace 行 6,188,544；全模式数 32,060。q0 只覆盖其中一个凝聚后的参考分块。原尺寸 parent 的几何为 50×25×140 nm，Ny8/p6 配置仍是工程 pilot，未获得最终网格或模式精度资格。[R14]、[R24]

这里的 q 是按周期相位拆开的模态分块；一个 twist sector 包含两个 q。不同 q 的端口数量不同，不能直接改 q 标签就复制矩阵。

| q | 同 sector 的配对 | trace 行 | port 行 | 增广矩阵行 | 现成数据起点 |
|---:|---|---:|---:|---:|---|
| 0 | 0 / 4 | 773,568 | 4,076 | 777,644 | 完整 CSR/native 和 V29 分解资格已接受 |
| 4 | 0 / 4 | 773,568 | 3,856 | 777,424 | 可复用 twist0 共同保存贡献及部分 native 见证 |
| 1 | 1 / 5 | 773,568 | 4,052 | 777,620 | 需要该实际 twist 的共同 producer/native |
| 5 | 1 / 5 | 773,568 | 3,984 | 777,552 | 与 q1 共用同 sector 准备 |
| 2 | 2 / 6 | 773,568 | 4,028 | 777,596 | 需要该实际 twist 的共同 producer/native |
| 6 | 2 / 6 | 773,568 | 4,028 | 777,596 | 与 q2 共用同 sector 准备 |
| 3 | 3 / 7 | 773,568 | 3,984 | 777,552 | 需要该实际 twist 的共同 producer/native |
| 7 | 3 / 7 | 773,568 | 4,052 | 777,620 | 与 q3 共用同 sector 准备 |

增广 q 行数合计 6,220,604。此行数表由冻结 profile 派生并可逐项核对；其余 q 的 NNZ、payload、因子峰值和成本仍待实际构建，不用 q0 代填。相同行数也不证明矩阵相同；tau、mode/alias、复材料系数、H 与映射均须绑定。[R14]、[R15]

### 3.2 最短的矩阵生产顺序

1. **先完成 q4。** 现有 twist0 保存包已有完整 volume Schur/cell expansion、7,932-mode surface B/D、active lookup、原始 H 和 q0/q4 map。复用这些字节；生成 q4 自己的 pattern、prefix/int32 证明、数值 CSR、COMPLETE manifest 和资格。q4 不能消费 q0 的行偏移或 777,644 行 CSR。
2. **再按 (q1,q5)、(q2,q6)、(q3,q7) 推进。** 每个实际 twist 的必要 FE/MPC、mode/map、surface/native 和共同 producer 只准备一次，保存后供两份 q CSR 使用。未做过的三个 twist 的准备是下一轮必要新工作；“不重跑 q0 producer/FE”不应被误用为禁止生产这些新算子。
3. **先沿用单个选定 q 的高速填值。** V28 的 sparse_local 投影和 direct-H 路径可窄化泛化显式 q/twist 身份；当前 direct-H 只接受一个 (0,0) block，并读取 `q0_hhat_sparse_term`。同一 sector 的两份 CSR 轮流消费保存流即可，不把批量双 q 填值重构设为前置。三个新 twist 在首次共同 surface 生产时同步保存内部 B/D 支持审计；只有既有 direct-only 前提 `internal_B_nnz=internal_D_nnz=0` 通过才采用 direct-H。若出现非零内部耦合，保留原值，使用既有准确凝聚的内部 port coupling/完整 Hhat 修正并重新按实际库存准入；禁止丢弃、置零或将修正后的 Hhat 直接替换成原 H。该检查随首次流完成，不新增一轮重复 FE。
4. 每个 q 单独绑定 shape、pattern/NNZ、dtype、科学输入、ordered modes、q map、原 H、producer、native、COMPLETE 三数组 hash。已有 COMPLETE 不再次累加 fill；中断的部分数组不能当成完成品继续无条件累加。统计总量用 Python/int64，不将八份 CSR 强拼为单一 int32 大矩阵。
5. 允许经过精确结构/支持集合证明后的共享，但不以待证明的共轭、镜像或结构相似性作为必须先实现的优化。先获得各 q 的真实可消费矩阵。[R15]、[R16]、[R17]

### 3.3 延续 V28 的独立 native 检查范围

每个新 q 保存两组不同、全非零 complex 输入及其 native 完整输出；对第一组输入另保存 trace-only 和 port-only 的原生分量。执行四次完整 CSR 作用，比较两次 total、volume/−D 与 C/Hhat、重组一致性，维持既有 **≤1e-11** 门。对同一 sector 的两个 q 检查双方向泄漏，按各自 native 对角作用尺度归一化。[R16]、[R18]

q4 已有一组 native total 和 q4→q0 泄漏见证；仅补第二组输入和缺失的 native 分量等必要见证。V26 saved replay 虽有四个分量，但它们来自将用于填 CSR 的同一保存贡献流，**不能改名为独立 native 证据**。原生对照应继续使用真实 FE 恢复、原生 volume action、原始 B/D/H 及投影路径，先保存并绑定身份，再与 CSR 比较。[R16]

上述泄漏是完整向量作用检查，不宣称未测量的全 off-diagonal CSR Frobenius norm。也不要求先构造巨大非对角 CSR 才能推进。补 native 所需的真实 local/recovery owner 尽量直接留给完整参考逆使用，避免同一窗口重复准备。

## 4. 用同一次全 q 构建取得资格和驻留因子组

### 4.1 复用现有 AllQExactMumps 的正确主结构

`src/solvers/task40_v10_p6_mumps.py` 的 `AllQExactMumps` 已具备全 q 路线：收齐 profile 全部矩阵，对每个 q conversion/symbolic；在任何 numeric 前汇总各 q 实际 INFOG16/17 和共驻工作区；准入后逐 q numeric、fresh probe 并保留前面已建的因子；后续 `solve(q,rhs)` 使用 repeated solve。[R19]

本轮在这个 backend 上补齐 V29 的原生分阶段时间、父段时间、逐阶段资源、第二个不同非零 RHS、保存向量审计和清理证据。**不将七次 factor→evict 当作 ALL_Q 的前置验收。** 全部 CSR/native 通过后，这一轮 ALL_Q numeric/probe/第二 RHS 就同时构成 q1–q7 的分解资格和新的 live 因子组。

保留原 complex128/int32、MPI1、数学线程1、exact MUMPS 控制：ICNTL(35)=0、(10)=0、(2)=0、(3)=6、(4)=2，并读回实际参数。排序、主元、其他存储参数、OOC/BLR 及 ABI 不做新扫描，不把 task cap 当作 ICNTL23。

新建因子的两个资格 RHS 均使用完整 CSR 真残差 **≤1e-10**。保留 AllQ 当前直接指定的 cos/sin RHS fresh probe，另用事先冻结的不同非零 RHS 验证同因子回代，保存实际 RHS/solution/residual。V29 的 `b=A x` 通过不能预定直接给定 RHS 也会通过；遇到真实残差失败，保留原 RHS 和结果，不换容易通过的 RHS。[R5]、[R19]

### 4.2 驻留通过必须有数值和对象的同时证据

全 q resident 的通过条件包括：

- q0–q7 各有一次成功 numeric、两组规定 RHS 的完整残差 PASS；每 q 原始 INFOG、时间、向量 hash 齐全。
- 全八个 **numeric 已通过**的因子与其仍需保留的 PETSc 输入同时存活，并记录源 CSR、wrapper/owner 身份、当前 cgroup/RSS 和对象账。
- 完整参考逆的多次实际调用复用同一 owner，numeric 计数不增加；每次实际经过的 q、MatSolve 数、修正次数均记录。
- 终止时统一销毁所有因子、PETSc/向量及自有恢复/映射缓存，验证引用释放、swap 和后代清场。

`max_simultaneous_factors=8` 单独不能证明全因子驻留成功：当前两阶段实现会先创建八个 symbolic factor 对象，这时尚未全部 numeric。保存数组也不能证明下一服务仍有 live factor。[R19]

### 4.3 全 q 两阶段调度需要新的可加时间口径

旧 q0 的 F_q 是一个连续区间。ALL_Q 先做完所有 symbolic 后才 numeric；若仍按“该 q 开始 loader 到该 q fresh 完成”计 F_q，这些跨度会覆盖其他 q 的工作，彼此重叠。

| 必需字段 | 定义 |
|---|---|
| `T_bank_parent_seconds` | 从本次 live bank 构建入口到八 q 均完成两 RHS 资格并 READY 的单调钟总父段 |
| `F_q_active_seconds` | 本 q loader/必要身份检查、conversion、symbolic、numeric、fresh 资格的排他父阶段累计 |
| `q_ready_span_seconds` | 本 q 开始到 READY 的跨度，含其他 q/共享工作；不可跨 q 相加 |
| `second_rhs_parent_seconds` | 第二 RHS 完整资格父段；不混入 fresh F_q，不与其原生 solve 子计时双计 |
| `T_bank_shared_seconds` | 全 q 准入、共同 donor/hash、公共初始化和 bookkeeping 的排他时间 |
| `T_bank_unattributed_seconds` | 总父段中尚未分配的余额，按实保留 |
| `S_q_native_seconds` | 每 q 真实业务 repeated MatSolve 的原生时间，按调用类别保存 |
| `T_PC_apply_parent_seconds` | 一次完整参考逆/PC 作用，含所有映射、q solve、内部恢复及检查 |

`F_q_active` 只累计 `T_bank` 边界内实际发生的排他步骤。若 CSR 已在 P1/P2 打开并直接借给 bank，前置 loader/身份费用留在原阶段，不复制进 F_q_active；bank 内再次实际执行的必要 hash 正常计入。未在本阶段发生的步骤填 0 并注明复用依据，不能复制 V29 历史计时。

串行且阶段互斥时核对以下账；若某项已在父段中，不能另加：

```math
T_{\mathrm{bank}}
=
T_{\mathrm{shared}}
+
\sum_{q=0}^{7}
\left(F_{q,\mathrm{active}}+T_{q,\mathrm{second}}\right)
+
T_{\mathrm{unattributed}}.
```

“包含其他 q 工作的跨度”不能自动记作 idle。factor cache 新建与文件页缓存冷暖也应分别记录；被前面的 hash/native 读取预热过的 CSR loader，不能冒称首次冷磁盘导入。V29 F_q 与 V30 排他活动累计的定义不同，不能不说明边界就给提速比。

## 5. 完整参考逆：补上局部恢复和全空间接线

### 5.1 八份 CSR 还缺少什么

完整参考逆要把完整 FE/端口 RHS 变换到各 sector/q，消去局部内部未知量，调用 q 因子，再恢复完整内部场与端口幅值。`CompleteTwoCellInverse.apply_augmented` 已实现这条路线，但需要真实的 global/local FE 布局、primal/dual 变换、tau/alias、原 H、局部凝聚 action、interior LU 和恢复缓存。[R15]

V25 保存的 volume 数据只有 Schur classes 和 cell expansion，没有完整 interior LU/recovery bank。因此下一轮明确允许准备这些**尚缺的完整参考逆所有者**并计时计内存。它们用于完整空间 RHS/恢复；q0 的原矩阵资格继续沿用，不因新建这些所有者就自动重装配 q0。[R16]

当前 `build_task40_v10_p6_reference_inverse` 会准备 global/local FE/action，然后重新调用 sector assembly，尚无直接注入已资格 CSR 的接口。最小改动是：

1. 在 sector assembly 边界增加严格的 qualified CSR provider，显式接受 q/twist、科学输入、mode/map/H 身份和 manifest/PASS。
2. q0 只允许返回已接受的原 CSR；身份不符即拒绝，禁止 assembly/fill fallback。其他已 COMPLETE 的 q 同样复用；只生产缺项。旧 q0 的科学 source/window 与本轮 execution source/window 分字段绑定，沿用 V29 已修复的两代身份处理，不要求旧矩阵被改写成 V30 科学身份。
3. 新 sector 在 producer/native 阶段生成的 local LU、mapping、transport 等 owner，能复用时直接保留给 reference；跨进程无法复用的对象如实重建计费。
4. 把 target 准备与求解尾段改成可接收现成 `reference_owner` 的阶段，使 reference 先通过，再进入 target。当前 worker 在 reference 前已经准备 target，不能只改状态文字声称完成了这种阶段顺序。
5. 在 heavy 前完成上述接线、最小 fixture 和源码冻结。reference→pilot 不经过会销毁因子的 return/finally，不在 live 因子等待期间热改代码。[R15]、[R20]

### 5.2 用独立全空间原生作用检查，保留不同资格名称

沿用 `_verify_regular_inverse` 的四类 startup RHS：完整 independent FE、全部 interior、全部模式非零 port、regular physical incident。再增加两组 FE 与全部 port 同时非零的 mixed RHS，检查折叠、恢复与增广接线在同一次调用中均参与。保存完整恢复场、alpha、native 输出、原始残差、每 q solve 记录及身份。[R20]

现有实现的 case 白名单和最终 `len(records)==4` 需要同步改成显式必需 case 集合；不能仅追加用例后留下错误的汇总门。沿用 profile 的实际 q_count/twist/mode 覆盖，不把旧“四 q”文案或常量误作当前八 q 的许可。

独立 oracle 继续使用 global physical action、sector 原生作用、原始 H 与 DtN auxiliary recovery；不能只用已组装 q CSR 的逆前后相乘来证明完整参考逆。不在原尺寸上强行建立只为小 B0 fixture 设计的独立 global CSR oracle。

以下门有不同用途，应分别报告，禁止通过改名混淆：

| 资格 / 指标 | 既有或本轮固定门 | 对后续的意义 |
|---|---|---|
| 每 q CSR/native 对照 | ≤1e-11 | 当前 q 的离散算子与独立 native 作用一致 |
| 每 q 新 factor 的两 RHS 资格 | **≤1e-10** | 本轮准确分解资格，不能用 V15 业务默认 1e-8 放宽 |
| strict reference：full equation、complete augmented FE、local combined、q solve | ≤1e-10 | 原 strict 全参考逆指标分别报告 |
| strict reference：alpha closure | ≤1e-11 | 严格端口幅值闭合 |
| 已注册 V15 PC：eliminated FE、complete augmented FE、noncancelling budget、业务 q solve | ≤1e-8 | 现有原生残差合格预条件器的准入，不等于 strict inverse PASS |
| V15 alpha closure | ≤1e-9 | 原有 PC 准入门 |
| V15 decomposition closure | ≤1e-10 | 分解出的残差各项必须闭合 |
| native action / recovery / map 等结构身份门 | 沿用各自既有门及完整覆盖 | 不能借 V15 数值门跳过错误接线 |

“noncancelling budget”把各 sector 引入的误差幅度分别计入，避免正负误差在总和中相互抵消后掩盖问题。已有 V15 frozen-scale、有限一次非递归增广修正及选择规则保持；所有附加 q solve 正常计费，q_count 应取实际 8。[R20]、[R21]

若 strict 全参考逆指标未通过，但既有 V15 完整原生准入通过，可按原合同作为 qualified reference PC 进入获准 target pilot；必须同时保留 strict 未通过的数值和状态。若 V15 结构或数值准入也不通过，则不进入 target。每 q 本轮两 RHS 的严格资格仍是独立前置，不因这个分级而放宽。

### 5.3 参考资格通过后，同进程进入原尺寸工程 pilot

沿用冻结的真实非分离 0.7 nm、50×25×140 nm、Nx272/Ny8/Nz14/p6 工程配置和已有 A6/FGMRES 路线，不把 regular reference 的对称性强加给 target。确认 target/reference 行布局及映射真实匹配后，在同一 factor owner 下记录：

- target 构建、真实一次 PC 作用、每 q 业务 RHS 回代、A6、Krylov、修正和局部恢复成本；
- 原 A6 真残差历史、各次检查的归一化、全部 q 调用与 numeric 累计计数；
- 收敛或受控截止时的场/checkpoint，完整恢复及释放后的独立原 A6 检查；
- 只有通过冻结的最终原 A6 和物理门，才输出正式 R00_s/R00_p/R00_total、R/T/A、A_volume、全部有序衍射级和复 E/H。

本任务既有原 A6 与释放后残差门为 ≤1e-6，能量/体吸收闭合为 ≤1e-5；若当前有效冻结输入或后续已批准合同更严格，执行其更严格值并在收据列明。它们与 q 分解的 1e-10 是不同对象的门，不能相互替代。[R23]

本轮不附加网格/模式扫描。即使工程 pilot 收敛，仍需后续单独核验网格、模式截断、场与各显著衍射级精度，不能宣布连续解或最终器件精度已通过。

## 6. 一次具体的新资源包：沿用现有工作站，不重新迁移

### 6.1 提案与授权边界

V29 已经在 `fenics-ws` / `fenics-ws01`、`/home/fenics/Projects/laptop_share` 成功运行；实际 private runtime 为 native Linux、PETSc 3.25.6 complex128/int32、MPICH 5.0.1。下一轮沿用这个位置和现成数据，不再询问已经确定的 SSH 别名/目录，不重新迁移 V28 大数组或重装相同环境。[R1]、[R9]、[R22]

| 项目 | V30 拟批准值 |
|---|---|
| scope | `V30_ALL_Q_REFERENCE_WITH_CONDITIONAL_TARGET_PILOT`，是待实现的新合同范围 |
| 主机 / 目录 | fenics-ws / fenics-ws01，/home/fenics/Projects/laptop_share |
| 单任务固定 MemoryMax | **1.5 TiB = 1,649,267,441,664 B** |
| 宿主 reserve | **64 GiB = 68,719,476,736 B**，在 host 可用量中单独保留一次 |
| MemorySwapMax / task swap | 0；不改系统全局 swap 设置 |
| ABI / 并行 | 当前已资格 complex128/int32、MPI1、数学线程1、原 MUMPS 控制 |
| 窗口 | 唯一 T0；总 **43,200 s**，数值 cutoff **T0+42,000 s**，收口 **1,200 s** |
| 允许主线 | 七个新 q CSR/native、全八 q 分解与驻留、完整参考逆、门通过后同进程原尺寸工程 pilot |
| 受控容量后备 | 见 6.3；不自动改变求解算法或进入 target |
| 范围限制 | 不自动扩大 cap/窗口，不新增精度扫描，不修改其他项目，不合并 master |

**该包目前为 PENDING_USER_APPROVAL。** V29 合同明文是 `V29_Q0_FACTOR_ONLY`、512 GiB、6 h，并排除 all-q/target 和自动提 cap；其窗口也已结束。因此一次新的范围/cap/window 批准是实际执行前唯一必要的外部决定。报告提交不等于该授权已经发生。用户批准后，Codex 按本包连续推进，不在 q4、每个 sector、每个 factor 或 reference 通过后逐次停审。[R22]、[R25]

选择 1.5 TiB 是为了将真实 FE/局部恢复、全因子和 target pilot 的同时占用纳入同一个批准包，减少 reference 通过后再次停下来申请资源、销毁重建因子的机会。它是上限，不预分配，不是已证明的实际需求或成功保证。仅做全 q reference 时 1 TiB 是较窄的备选；本报告主方案包含后续同进程 target。

作为规划量级，8×q0 的本次 cgroup 峰值为 **679,128,825,856 B**。这是明确标记的情景乘法，不能称全 q 实测，更不能据此断言任一 cap 必定成功/失败。实际准入仍使用各 q 自己的 symbolic 与完整对象账。

cap+reserve 为 **1,717,986,918,400 B < 2,000,000,000,000 B**。实际宿主 MemTotal 为 2,163,100,385,280 B，不能利用超出十进制 2 TB 的部分后宣称达成 2 TB 目标。正式判断还要核对实际系统、其他任务和所有未进入本任务 cgroup 的必要所有者，不用配置上限之和代替实测。[R3]、[R9]

### 6.2 全部同时对象入账，并在每个增长阶段重新准入

| 对象组 | 必须记录的内容与常见漏项 |
|---|---|
| 各 q 源 CSR | data/indices/indptr 的实际 bytes、文件页、共享 backing；不可变 hash |
| conversion / PETSc 输入 | 实际复制、排序/canonical 化、临时 Vec/索引和保留矩阵；只在证明共享时去重 |
| symbolic / numeric factors | 各 q 原始 INFOG16/17/19/22/9、对象状态、真实同时驻留；分清 allocated/used/预测 |
| reference FE / local owners | global/local FE、MPC、transport、mode/alias/H、interior LU、耦合和恢复 bank |
| target / reference 映射 | 双方 FE/trace/port 布局、primal/dual、共享 transform bank、各 borrower 的实际唯一 owner |
| 生产与构建暂存 | producer/Schur/surface、pattern、row tile、投影、fill、native 验证和 JIT/compiler |
| Krylov 与运行暂存 | V/Z、残差、解、检查点、完整一次 PC 暂存、额外增广修正 |
| 恢复、独立检查与输出 | full-storage E/H、旋度、原生 A6、alpha、原始向量保存/读回、释放前后检查及写盘 staging |
| 系统与监督 | watchdog/checker 全后代、任务文件页、宿主 reserve 和实际其他占用；磁盘空间另列 |

已分配对象进入 current/base，尚未分配的实际工作区进入 future delta，不能同一对象算两次。只有生命周期证明确实互斥的阶段才取 max；同时存活的 bank、local LU、target、CSR/PETSc 必须相加。即使退化为内存映射，驻留文件页仍不能漏计。

沿用现有 `all_q_symbolic_before_any_numeric`，但新 reference-first 接线需要补足未来 target、映射和局部缓存的预算；不能沿用“target 已在 current 中”的旧隐含假设。构建期间也需逐大分配 Gate，不等到八份 symbolic 都完成才第一次检查资源。[R19]、[R20]

reference 资格和后续 target 分别给出完整阶段账。若 reference 自身的同时对象/暂存已经准入，而 future target 的可信预算尚未闭合或不准入，仍可先完成获准的全 q 与完整参考逆资格；target 保持 NOT_RUN/预算未闭合。不能把未知 target 项填 0，也不能根据 reference 通过就声称已有 pilot 容量。

共享 transform bank 的旧门要求 `actual_target_and_reference_full_rows_match_required=True`，原来此时 target 已构建。新接线应将冻结 target profile 的未来尺寸/预算与实际匹配分开：factor 前按可信布局上界预留并标记为计划；target 建立后、首次 PC 前验证实际 target/reference 布局。不能提前把计划值标 actual=True，也不能让旧门反过来强迫先建 target。[R20]

每次请求同时检查 task cap、宿主 MemAvailable−64 GiB 和全部有限 ancestor cgroup 余量；不把 host 与 cgroup 的缺口相加。历史 MemAvailable 曾为 1.414 TB、factor 启动时 2.117 TB、后续审计入口约 1.896 TB，它们不是当前可用量。不得停止其他项目作业来取得通过。[R3]、[R9]、[R13]

现有 restart32 的 72 个 complex128 retained 向量，按 6,220,604 行派生为 **7,166,135,808 B**；这只是一个向量库存分项，不能替代完整内存预算，也不适用于未核实的 full-storage 向量数量。[R19]

新合同要显式传播到 prepare/selector、service、launcher、worker、watchdog 和所有 checker，保存每层实际 cap/reserve/window/ABI/hash 回读。`task40_v29_contract.py` 硬绑定旧 scope 和 21,600/20,400/1,200 s，不能改旧批准 JSON 后继续沿用其身份；应注册独立 V30 合同，旧入口行为保留。[R25]、[R26]

### 6.3 全驻留不准入时，仍交付可复用的新成果

若实际完整账超过固定 cap 或可用量，保存各 q 实际 symbolic、当前对象、future delta、缺口和阶段状态，释放 bank；不能 OOM 试探、自动升 cap、换 BLR/OOC/ABI，不能据此宣布 2 TB 不可行。

在同一已批准窗口内，先确保已经完成的其余 q CSR/native 证据持久化。若仍有实际资源/时间，且现成单 q 后备接线已在本轮冻结和验证，可仅对**尚无本轮分解实测**的新 q 逐个做一次 factor/两 RHS/evict，补齐真实成本；不重做已经合格的 q0 或其他 q，不把它伪称为全驻留成功。这是容量受控后备，不是主路线的预验收。

后续固定保留高重建成本因子加一个流转槽的决策，须使用已测各 q 成本和实际 RHS 访问序列。固定 8q 循环里，小于 8 槽的普通 LRU 可能每轮全 miss，不能按槽数线性宣称收益。未资格化的新缓存策略不在本窗口临时升级为 target 默认。

## 7. 从完整 PC 成本推进 48 小时目标

V30 要有一个覆盖准备、q/参考构建、bank、reference 资格、target pilot、恢复/检查/清理的连续顶层父钟。阶段边界原子保存证据并继续，不通过开启新 service 隐藏因子重建。窗口从获准执行包第一项实际准备开始冻结；源码修复、重启、等待和 checker 不刷新 T0，授权前实现成本也如实单列。

最终保留两个口径：

1. **本轮开发/执行工作包经过时间与保守计费。** 包含本轮真实准备、工程修复、测试和等待，不扣除失败。
2. **同一目标实例完整冷流程的必要成本。** 包含冷输入/JIT、首次 producer/pattern/fill、target/reference 构建、所有必要分解及重建、完整业务 PC/A6/Krylov、恢复输出、独立 checker 和清理。复用旧 artifact 的本次 warm 执行不是完整冷流程实测；缺失历史项继续 UNKNOWN。

不将历史全部工程等待硬算成算法成本，也不把单场必须的准备包装成免费历史。完整 PC 父段已包含各 q 回代，不能再叠加其 S_q；全因子总父段与逐 q native 子计时同样不能双计。

取得原尺寸 pilot 的真实完整 PC/A6/Krylov 成本后，再给有条件的 48 h 预测：

```math
T_{\mathrm{cold}}
=
T_{\mathrm{required\ setup}}
+
T_{\mathrm{bank}}
+
T_{\mathrm{reference\ qualification}}
+
T_{\mathrm{target\ iteration}}
+
T_{\mathrm{recovery,\ output,\ check,\ cleanup}}.
```

其中各项必须划成不重叠阶段；必要首次 producer/pattern/fill 属于 setup，实际 cache miss 重建按所在阶段记一次。预测剩余迭代预算可写为：

```math
N_{\mathrm{remaining}}
\le
\left\lfloor
\frac{172800-T_{\mathrm{spent}}-T_{\mathrm{remaining\ fixed}}}
     {C_{\mathrm{iteration}}}
\right\rfloor.
```

这个式子只有在完整已花费用、剩余固定费用和真实迭代成本均有依据时才有意义；分子非正则无剩余预算。`C_iteration` 使用包含 PC、A6、Krylov 与定期检查的实测区间，并报告早/晚迭代差异和停滞，不从 q0 S_q×8 或首一步推出整场时间。48 h 的最终资格仍需要目标实例完整必要冷流程与精度同时闭合。

## 8. 下一轮执行任务与停止条件

| 阶段 | 连续执行内容 | 可审查交付 / 准入门 |
|---|---|---|
| P0：准备可执行包 | 在既有分支实现 q/twist 泛化、qualified CSR 注入、AllQ 第二 RHS/计时、reference-first→pilot owner 复用、新版本合同和完整监督传播；只修本轮相关问题 | 源码干净冻结、最小相关 fixture、无分配/无 factor 的合同与依赖 preflight；用户一次批准新包 |
| P1：q4 | 复用 twist0 保存 producer/map/H，生成 q4 自己的 pattern/CSR，补缺失 native 见证 | q4 COMPLETE 三数组 hash、四作用 native PASS、双方泄漏与真实成本 |
| P2：其余三 sector | (q1,q5)→(q2,q6)→(q3,q7)，每 sector 一次必要共同生产，逐 q 填值、检查、持久化 | q1–q7 全部真实资格，q0 旧资格继续匹配；没有用 q0 填充未知 NNZ/时间 |
| P3：完整 reference owner 与 bank | 复用已准备 owner，补缺失恢复/全局 action；注入八份 CSR；全 q conversion/symbolic，联合准入后逐 q numeric/两 RHS并保留 | T_bank、各 q 排他时间/INFOG/向量/峰值、八个 numeric PASS 同时存活 |
| P4：完整参考逆资格 | 四个原 startup case＋两个 mixed case，独立全空间 native 检查，保留 strict 与 V15 的不同状态 | 全 q/全部 interior/全部 modes、原 H/恢复/映射闭合；多次作用 numeric 计数不增 |
| P5：条件原尺寸 pilot | P4 准入、完整资源账和剩余窗口允许时，同 owner 准备 target 并沿已有 FGMRES/A6 求解 | 真实完整 PC/迭代成本、A6 历史、场/checkpoint、实际物理与终态状态 |
| P6：收口 | cutoff 后不新开 numeric，保留 best/checkpoint，统一释放并独立审计 | 原始正负证据、task swap0/清场、连续父钟与冷账缺项、正式 response/index/总账 |

不因 ordinary path/schema/metadata/显示 bug 提前回到“等待下一 review”。在冻结窗口和已有权限内做最小定向修复：审计问题只重读保存数据，身份文件漏部署只补经批准的同范围文件，算法相关修改只重新资格化真正受影响的阶段。旧 attempt、旧 SHA、原始失败和费用全部保留。

真实身份不符、CSR/native 不一致、规定残差失败、资源不准入、窗口截止仍按合同停止受影响阶段。接近 cutoff 且已知来不及完整 reference 资格时，先持久化 CSR/native；不明知将立即销毁仍无意义启动整组 bank。原尺寸 pilot 未获门通过则保持 NOT_RUN 或 CONTROLLED_STOP，不为“有结果”输出 official 字段。

### 8.1 最小而有意义的软件验证

复用已有 phase/duality/augmentation/recovery 和 AllQ retention/gate-order fixture，只增加本轮行为变化对应检查：

- 不等 port 数、真实非零 complex twist 下的 q 选择与绑定；q0 错误 hash/map 必须拒绝，不能 fallback。
- saved replay 分量不被误标为 native；配对 q 都走完整独立作用范围。
- 所有 symbolic 先于任何 numeric；每 q 一次 numeric、两个资格 MatSolve；reference/pilot 多次作用不再 numeric。
- shared owner、未来 target、Krylov/恢复/输出的共驻预算正确；失败时全部 native owner 清理。
- reference 新必需 case 集合、实际八 q 修正计数、新合同 cap/window 在每层一致；超范围批准/旧合同仍拒绝。

按仓库已有阶段门执行必要 targeted/Task-focused 验证；不把无关 full suite、MPI2/4 或环境重装放到每个 q 前，不宣称未运行的检查通过。所有生产代码在正式 heavy 前冻结；本 Chat 不代执行这些测试。

### 8.2 接续指令必须与实现相符

当前 `target_stage_handoff_v29.md` 中的 factor-only 命令只用于已结束的 V29 单 q0 工作，**不能直接作为 V30 全 q 命令重放**。当前源码也没有本报告拟新增的完整 V30 CLI；本报告不虚构一个尚未存在的参数组合。[R4]、[R25]

Codex 从自己的既有 canonical 控制 worktree 读取本 review、实现上述薄接线并发布 clean 科学源码；批准后只向现有 Task40 工作站根目录同步必要增量。以下是在已有工作站 Task40 shell 中可直接执行的只读入口核对，不启动数值任务：

```bash
cd /home/fenics/Projects/laptop_share
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
git rev-parse HEAD
git log -1 --format='%H%n%s'
```

核对分支、工作树、实际部署 SHA 与新冻结源码；不自动 reset/checkout/创建新项目。P0 必须生成并在 `outcomes/target_stage_handoff_v30.md` 保存**实际实现、已做轻量解析验证**的一条 service 启动命令、一个 read-only checker 命令，包含实际 activation/runtime、输入/selector/contract 路径及 hash、T0/cutoff/deadline。新实现优先复用现有 generic service/worker；不复制一个含独立科学内核的新 task runner。

输出时以实际根目录和 artifact 路径替换占位项。授权前可完成实现、fixture、依赖/合同草案；不能把 `PENDING_USER_APPROVAL` 写成 `USER_APPROVED` 后试启动。用户对第 6.1 节包批准后，freeze T0 并按 P1–P6 连续执行，不再要求相同范围的逐阶段确认。

## 9. 正式交付清单与本轮成功标准

下一份 `response_v30.md` 连同以下轻量证据提交同一分支；大矩阵/向量/场继续位于 ignored artifacts，并发布精确路径、字节数和 hash：

| 交付 | 必含内容 |
|---|---|
| 每 q 算子资格表 | q/twist/shape/NNZ/三数组 hash/native 范围与最大误差；明确新建、复用、缺项 |
| 每 q 分解表和 live bank 收据 | actual INFOG、严格两 RHS、T_bank/F_q_active/S_q、numeric 计数、同时 live numeric 集合 |
| 完整 reference 收据 | 全空间 case、q/interior/mode 覆盖、raw strict 指标、V15 独立准入、恢复/原 H 与调用证据 |
| 完整对象账 | 实际 owner、共享依据、生命周期/current/future、峰值、swap、清理；UNKNOWN 明列 |
| pilot 收据 | 实际是否启动、输入/源码、PC/A6/Krylov 成本与原 A6 历史；正式场/物理资格按实际判断 |
| 统一时间账 | 连续父钟、各阶段互斥分解、失败/修复/等待、冷流程已知与 UNKNOWN |
| run index / handoff / summary / 总账 | 实际 attempt、source/checker SHA、有效合同、命令、所有正负结果及下一缺口；同步仓库模型总账 |

本轮实质性进展的递进标准是：七个新 q 的合格持久化 CSR → 全 q 实际分解和可用因子组 → 完整原生参考 PC 资格 → 原尺寸 target 的真实迭代/场证据。报告每一层实际到达的位置，不能让数个 record bug 把已完成的数值层重新变成“未通过”。

**全 q / 完整参考逆 / 原尺寸 target / 网格与模式精度 / 2 TB 及 48 h 冷流程仍是不同结论。** V29 只关闭第一块 q0 的分解问题；V30 应尽可能在同一授权包内连续推进后面的真实工作，不再围绕已接受 q0 做重复证明。

## 10. 可直接发给 Codex 的接续文本

以下是执行任务正文；资源状态由用户对第 6.1 节的一次实际批准决定，不能仅因复制报告就伪造批准记录。

> 请按同一执行分支的 review_report_v30.md 续作 Task40extra。审阅基线为 5823faf26e5425974645c2b1fc2b4004552b4324。V29 q0 分解、同因子两 RHS 与独立保存数据审计已接受；旧 checker 失败和费用保留。先修正报告所列轻量记录问题，不为它们重新 producer、FE/MPC、pattern、fill、native 或 q0 分解。
>
> 先完成 P0 的实际可执行包：严格 selected-q/twist 泛化、qualified CSR 注入、AllQ 两 RHS/计时/资源证据、完整 reference owner 及 reference-first→target 的同进程接线、新版本资源合同与全层监督。沿用现有通用实现，做最小相关 fixture，冻结 clean 源码，给出真实 service/checker 命令。
>
> 新资源包尚须用户一次批准：沿用 fenics-ws 和 /home/fenics/Projects/laptop_share；固定 task cap 1,649,267,441,664 B、host reserve 68,719,476,736 B、task swap0、MPI1、数学线程1、原 complex128/int32/MUMPS；唯一 T0，总 43,200 s，数值 cutoff 42,000 s，收口 1,200 s。旧 V29 的 512 GiB/q0/6 h 许可不能扩写。若用户已经在本会话明确批准此包，记录批准后直接执行，不重复询问主机/目录或逐阶段确认。
>
> 批准后，先 q4：复用 twist0 保存贡献，建立 q4 自己的 pattern/CSR，补足缺失 native 见证；再按 (q1,q5)、(q2,q6)、(q3,q7) 每实际 sector 一次必要共同生产，形成并保存各 q COMPLETE CSR/native。其余 twist 的必要 FE/MPC/native 是允许的新工作；不能复制 q0 或将 saved replay 当独立 native。各新 q 延续四次完整 CSR 作用及 ≤1e-11 门。
>
> 八 q CSR/native 齐全后，复用现成 ALL_Q_RESIDENT：全部 conversion/symbolic、完整共驻准入、逐 q numeric/fresh probe/第二非零 RHS，维持两 RHS ≤1e-10 并保留准确因子。不要先七次 factor→evict 再全部重建。V29 q0 factor 已销毁，本次为 live bank 新建一次 q0 必须计费；q0 CSR/native 仍复用。
>
> 完整账包含所有 q CSR、PETSc 输入、因子、target/reference FE/映射/local LU/缓存、构建、Krylov、恢复、输出、checker 和系统余量。reference-first 后未来 target 必须明确预留。按实际 INFOG 和实时 host/ancestor/cgroup 准入，不能用 q0×8 当全 q 实测，不能自动提 cap、换 ABI/MUMPS/OOC/BLR。
>
> 同一进程完成原四类 full-reference startup 加两组 mixed FE/port RHS，保存独立全空间 native 残差、恢复、原 H 和全 q 覆盖。每 q 严格分解资格与既有 V15 业务 PC 准入分开；保留 strict 未通过指标，不将 V15 PASS 改名为严格完整逆 PASS。资格、完整资源账和剩余时间允许时，复用 live reference owner 直接进入原尺寸非分离 target pilot，不逐阶段停审，不在交接时销毁再假称复用。
>
> 使用 T_bank 总父段、各 q 排他活动累计和真实整次 PC 父成本；跨 q 的 ready 时间跨度不可相加，native 子计时不可再加到父段。普通路径/元数据 bug 定向修复并保留失败，窗口不刷新；真实身份/残差/资源/cutoff 按报告停止受影响阶段。容量不准入时按第 6.3 节保存成果和实际缺口，不临时发明新默认算法。
>
> 按报告提交 response_v30、逐 q/operator/resource/reference/pilot 收据、完整时间与对象账、run index、真实 handoff、summary 和模型总账。大数组留 ignored artifact，发布路径/hash。结果仍按实际层级区分，未闭合完整冷流程及网格/mode 精度前不宣称 2 TB/48 h 或最终精度达标。不改其他项目，不合并 master。

## 11. 冻结证据与源码入口

以下文件引用均固定在本次正式交付 HEAD；下一轮新增源码和结果另列自己的实际身份。

- [R1]：V29 正式回应。
- [R2]、[R3]：operator 与资源/时间 compact。
- [R4]：V29 原始独立续作交接；仅作历史命令依据。
- [R5]–[R8]：factor 原始 checkpoint、metadata PASS、保存向量 PASS 与独立审计脚本。
- [R9]–[R13]：执行回执、最终工作包观测、原始收据索引及两份审计父段。
- [R14]–[R21]：实际 profile、参考逆、保存贡献/CSR、stage runner、AllQ MUMPS、worker 和严格/V15 准入源码。
- [R22]–[R26]：批准的旧合同、原任务科学门、此前 review、新合同接线依据和 service。
- [C1]、[C2]：实际数值源码→checker 源码→正式交付的远端差异。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/response_v29.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v29.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v29.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/target_stage_handoff_v29.md
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_original_factor_checkpoint.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_metadata_checker_fix02_result.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_saved_factor_vector_audit_result.json
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_main_factor_saved_vectors_audit.py.txt
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_execution_receipt.json
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_final_delivery_cost_observation.json
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_published_receipt_index.json
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_metadata_checker_fix02_parent.json
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_saved_factor_vector_audit_parent.json
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/task40_v10_p6_periodic_profile.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/task40_v10_p6_yorbit.py
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/task40_v25_selected_q0.py
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/task40_v27_saved_q0.py
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/runners/task40_v20_stage_runner.py
[R19]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/task40_v10_p6_mumps.py
[R20]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/runners/task40_v10_worker.py
[R21]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/solvers/augmented_reference_correction.py
[R22]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/outcomes/records/v29_approved_execution_contract_fix01.json
[R23]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/task.md
[R24]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/docs/task40extra_0p7nm_engineering/review_report_v29.md
[R25]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/src/runners/task40_v29_contract.py
[R26]: https://github.com/Rookie1234567/MyFEniCS/blob/5823faf26e5425974645c2b1fc2b4004552b4324/scripts/run_case_in_user_service.sh
[C1]: https://github.com/Rookie1234567/MyFEniCS/compare/bee9a1f0e33076e372607581f790bda3a4a0072f...9a9a9d31f4aebf1564d5f09177c1d3481d64371f
[C2]: https://github.com/Rookie1234567/MyFEniCS/compare/9a9a9d31f4aebf1564d5f09177c1d3481d64371f...5823faf26e5425974645c2b1fc2b4004552b4324

