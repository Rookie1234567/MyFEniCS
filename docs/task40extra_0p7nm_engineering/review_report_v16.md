# Review V16：保留已验证的 p6 参考 PC，降低构建成本并推进 E1 与目标端口能力

## 0. 本轮裁决

**V15 已取得真实进展：新四 q p6 参考预条件器完成了 Gx560 的目标求解、物理输出和同离散保存场比较。下一轮不再调整参考 PC 的数值准入门，主攻必要构建的耗时与同时内存，使新实现完成 Gx560 对照，并在资源允许时直接完成原 E1。E1 若仍不能容纳，继续完成本报告授权的有界端口构建和索引验证，不以一次资源停止结束全部工作。**

预条件器的作用是给外层迭代提供修正方向；最终求解对象仍是带真实三维缺口的 p6 Maxwell 方程。V15 用 3 次外层迭代得到真实 A6 残差约 4.70e-9，说明此参考 PC 在这个案例中有效。但它的 worker workflow 约 40.13 min，历史 p6 target 加 exact p4 correction 的对应记录约 32.10 min；树 RSS 由约 5.26 GB 增至 10.29 GB。**少迭代已经实现，端到端工程优势尚未实现。**

最终目标保持：真空波长 0.7 nm，50×25×140 nm 目标域，真实非可分三维材料/几何，complex128、Nédélec H(curl)、x/y 双 Floquet、z Fourier-DtN；约 2 TB 是整机物理内存，须保留系统余量，任务零 swap；单场必要构建、求解、恢复、输出及检查全过程不超过 172800 s。当前小模型成功没有授予目标尺寸的精度、容量或 48 h 资格。

| 审阅事项 | V16 裁决 | 适用范围 |
|---|---|---|
| V15 数值合同及 Gx560 实算 | pass_with_qualifications | 已测 Gx560 的完整目标、物理和同离散比较通过；新合同有实算支持 |
| B0 原 worker | 保留 WORKER_FAILED / exit 4 | 原负端口身份限值导致整组输出门失败，不能覆盖原失败 |
| B0 保存场恢复 | PASS | 未重建参考因子、未重跑 KSP；恢复结果独立保留 |
| E1 新参考 PC 路线 | RESOURCE_CONTROLLED_STOP | 四 q symbolic 完成；任何 numeric factor、KSP、新场之前停止 |
| 新路线完整速度与内存优势 | NOT_ESTABLISHED | 已记录的 Gx560 workflow 更长、RSS 更高 |
| 原尺寸、一般 Ny、完整端口及 2 TB / 48 h | NOT_QUALIFIED | 仍缺目标离散精度、实际增长和全过程证据 |
| 下一轮执行 | 按本报告 P0–P5 连续推进 | 既有本机主控/执行者分工；不逐阶段等待主审 |
| ordinary default / master | 不批准变更或合并 | 保持显式研究 opt-in |

本轮不是重写 V15。V15 及其失败、修复、耗时和验收标签保留；本报告明确下一项工程任务及继续执行条件。

## 1. 固定证据与执行边界

| 项目 | 身份 |
|---|---|
| repository | Rookie1234567/MyFEniCS |
| execution branch | task40extra_0p7nm_engineering |
| review base HEAD | f59884b1a98b329cfce2a3de8307dd3db8560520 |
| HEAD commit UTC | 2026-10-07T15:58:11Z |
| HEAD message | Task40 V15: close response, run index and cumulative ledgers |
| latest response | response_v15.md |
| reviewed numerical source | 40dbe138f53b9a2ee39399eac66dc4b0867a2d50 |
| B0 original solve source | 0201815c6b13f8456e9717ab93cc5023d4c946d1 |
| previous review commit | ffaf607384539e7d02bc35e1f685462e650abb21 |
| canonical worktree | /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering |
| actual latest execution ABI | WSL2、MPI1、数学线程1、PETSc complex128 / int32 |
| new report | docs/task40extra_0p7nm_engineering/review_report_v16.md |
| required response | response_v16.md |

审阅依据为固定 HEAD 的 response、四份 V15 compact records、run index、summary、test summary、任务书与规则，以及相关构建、PC、恢复和检查源码。审阅端未运行 FE/PDE，未重放本机 ignored 科学数组；compact 中绑定的原始数组/日志须由现有主控在本机继续核验。文档引用不能替代现场 PID、可用内存或当前账本。

主控先核对实时进程、service、HEAD、工作树和 artifact。执行者实现、测试及运行，不 commit/push；主控审查、冻结数值源码并集中提交推送。审阅文档沿既有流程写入同一执行分支。不得另建项目、聊天、checkout/worktree，不启用 collaboration subagents 或定时任务，不 SSH、不操作工作站、dot、Task042 或其他项目，不合并 master。任务目录中“本轮为 V10”是陈旧导航，当前执行顺序以本报告为准。

## 2. V15 结果及其含义

### 2.1 统一结果表

时间为对应 worker 的 workflow monotonic，内存为十进制 GB。单独启动的 checker、同离散场比较、恢复过程及开发 campaign charge 不能自动视为已经包含在该 workflow 中；须按第 7 节补齐归属。

| 模型/路线 | 实际离散 | 原 A6 或阶段 | worker workflow | 树 RSS / cgroup 峰 | 状态 |
|---|---|---|---:|---:|---|
| B0 原 V15 | 80 cells；p6；532 retained modes | A6 1.608977439e-8；负端口身份限值 -1 触发失败 | 1052.751 s | 2.777 / 3.216 GB | 原 WORKER_FAILED 保留 |
| B0 保存场恢复 | 同一保存场，恢复源码 40dbe138 | 独立 A6 重算、物理输出、checker 通过 | 10.719 s | 0.770 / 0.911 GB | KSP=0；无参考因子重建 |
| Gx560 历史对照 | 560 cells；p6 target；exact p4 correction；340 modes | A6 9.733476895e-7；171 步 | 1925.863 s | 5.256 / 未在本表重列 | 历史完整解保留 |
| Gx560 V15 | 560 cells；p6 target；四 q p6 reference PC；340 modes | 释放后 A6 4.704401351e-9；3 步 | 2407.572 s | 10.295 / 11.675 GB | target、physics、同离散比较 PASS |
| E1 历史对照 | 760 cells；p6 target；exact p4 correction；588 modes | A6 9.781668526e-7 | 4580.375 s | 10.650 / 未在本表重列 | 历史完整解，不等于 V15 新路线 |
| E1 V15 | 760 cells；p6；588 retained modes | 四 q symbolic 完成；numeric/KSP/field NOT_RUN | 5671.918 s | 12.234 / 12.346 GB | 资源受控停止 |
| E2 历史路线 | 880 cells；p6 target；exact p4 correction；700 modes | A6 9.793073227e-7；保存场已恢复输出 | 原 7692.028 s；恢复另计 74.154 s | 原 11.349 GB | 保留原 worker 失败及离线恢复身份 |

Gx560 V15 物理量为 R=0.0761240670863，T=0.905769220100，A_volume=0.0181067125773；能量闭合绝对误差 2.3694e-10。释放后的独立 native witness 为 4.704257056e-9。R00_s=0.0761235935066，R00_p≈7.36e-22，二者不能混成未说明极化的单项。

Gx560 与历史同离散 p6 场比较：八类场最大相对 L2 差 3.9851e-7；冻结显著模式集的最大复振幅相对差 8.6047e-7；全部 340 模式功率最大绝对差 2.2271e-8。这个对照支持同离散一致性，不能当作连续极限或目标尺寸精度。

B0 与 Gx560 的输入、网格、模式及入射方位并非单一 h 变化；E1/E2 又改变物理尺寸。不能从这些记录直接拟合网格收敛阶或渐近资源增长。

证据：[V15 正式结果][S2]、[V15 回应][S1]、[V15 成本][S4]、[历史目标与 E1 身份][S10]。

### 2.2 新合同已经在哪些方面得到验证

Gx560 的三次 PC apply 均采用 initial candidate 0，没有使用增广修正。每次实际使用四 q；初始 factor admission probes 为 4 次，startup reference q MatSolve 为 16 次，target PC 为 12 次，共 32 次 q MatSolve。

| 三次 PC 中的最大指标 | 实测最大值 | V15 条件 |
|---|---:|---:|
| 每 q 实际 MatSolve 真残差 | 1.6729e-10 | 1e-8 |
| 独立 global native 消元 FE 残差 | 2.4692e-9 | 1e-8 |
| 独立完整增广 FE 残差 | 1.9232e-10 | 1e-8 |
| 非抵消误差预算 eta | 4.9657e-9 | 1e-8 |
| alpha closure | 1.7789e-11 | 1e-9 |

逐次指标和原始状态见 [V15 native PC compact][S3]。

前两次实际 q solve 的旧 strict 1e-10 标签仍为 FAIL，但新合同对应项目均通过；初始因子探针仍严格通过 1e-10。此结果支持 V15 对“受控近似 PC”的用途区分。FGMRES 允许变化或非线性的右预条件器，但这个算法性质本身不保证目标问题收敛，实际收敛仍由本案例给出。[PETSc FGMRES][P1]

V16 保持 NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15 的公式、尺度、阈值、逐调用检查与最多一次完整增广修正不变。旧 sector/native 检查及旧逐扇区 ratio 原值继续保留；不将历史差异改称已证实的无害舍入。本轮 Gx560 成功直接覆盖的是未修正路径，不能把 correction_count=0 的生产轨迹说成修正路径也已完整实算验证。修正实现既有测试保留，遇到实际调用时仍独立核验完整状态。

## 3. 真正的工程瓶颈

### 3.1 不能把全部希望寄托在 CSR 累加

CSR 是保存稀疏矩阵的一种数组布局。现有 legacy 装配每得到一个局部贡献，就把它加进越来越大的全局稀疏矩阵，反复分配和复制矩阵数组。改为分块或预先确定位置后累加，可以减少这类复制，收益与临时内存都必须实测。

Gx560 V15 已记录：

| 阶段 | 秒数 | 解释 |
|---|---:|---|
| 全部 worker workflow | 2407.572 | 父口径 |
| 纯 target KSP | 155.863 | 约占 workflow 6.47% |
| 非 KSP 时间差额 | 2251.709 | 约 93.53%；是未细分总差额，不把它全部命名为装配 |
| 两 sector q assembly 父计时合计 | 422.540 | 已含局部贡献、投影和稀疏累加 |
| 其中 sparse accumulation 合计 | 275.837 | 约占 workflow 11.46% |
| 四 q factor setup 父计时 | 54.227 | numeric 子计时已经包含在内 |

在假设其余阶段全部不变的理想扣除中，若 275.837 s 累加成本降为零，workflow 仍为 2131.736 s，约 35.53 min；即使整个 422.540 s 的 q assembly 都降为零，仍为 1985.032 s，略长于历史 1925.863 s。**这些只是对当前非重叠计时的算术上限，不是实际性能预测，也不证明跨历史版本的因果关系。**

因此，bounded-staging CSR 候选仍值得做，但它必须与真实的构建内存、重复表示和其他主要父阶段一起评价。不得在只节省几十秒或只报告迭代次数后称 2 TB / 48 h 有资格。

每次 PC 完整耗时目前没有独立计时；native evaluation 的 13.98/8.30/8.76 s 只是子阶段。V16 在必要的新运行中补全完整 PC 计时，不能为补一个旧计时重新求解旧 PDE。

### 3.2 E1 是本机容量停止，需要约 6.72 GB 的实际差额解释

| E1 all-q symbolic 后项目 | 字节/数值 |
|---|---:|
| live process-tree RSS | 12,064,264,192 B |
| dynamic total cap | 12,474,302,464 B |
| projected process-tree RSS | 19,192,602,560 B |
| physical available | 544,256,000 B |
| evidence reserve | 134,217,728 B |
| 四 q INFOG16/17 symbolic 估算合计 | 6,530,000,000 B |
| projected 减 total cap | 6,718,300,096 B |

最后一项是当时预测与动态上限的差额，不能写成已经分配的超额内存，也不能宣布省去这么多逻辑数组就必然通过下一次资源门。后续还要重新读取现场系统余量和对象生命周期。

E1 实际 q CSR 总 NNZ 为 84,935,314，rows 合计 153,948。若只按 complex128 数值、int32 列索引和行指针计算，一套四 q CSR 纯数组约 1,699,322,088 B。即使确实消除一整套这样的重复数组，也不能单独填平约 6.72 GB 的历史缺口。

这次停止不是 2 TB 主机上的容量实测，更不是 2 TB 不可行的证据。也不能直接把笔记本 cap 改成 2 TB，或删 q、删倏逝模式来进入 numeric。四 q numeric 尚未发生，6.53 GB 是 symbolic 估算，19.19 GB 是继续执行预测，二者均不是 numeric 因子的实际峰值。

E1 workflow 5671.918 s、watchdog 5671.578 s、UTC wall interval 6275.443 s 分列。任务/cgroup swap 为零；WSL-global pswpin/pswpout 分别增加 315/55203 页，归属仍未知，不能据此声称宿主全程无 swap，也不能把它自动归因给本任务。

### 3.3 源码给出的具体改进位置

| 位置 | 当前行为 | V16 处理 |
|---|---|---|
| task40_v10_p6_yorbit.py 的 legacy sector assembly | 对每个局部贡献执行全局 CSR 加法；同时生成对角及非对角 q 块以验证分解 | 实现有界临时空间的精确累加；保留非对角验证及全部 q |
| 同文件的 V13 preallocated 路径 | pattern 使用逐行 Python set；填值对每个 term 扫全局行；仅 B0 有完整对照 | 不直接把它贴到 Gx 当成熟方案；替换无界 set/全局扫描，证明实际 staging 上界 |
| p6_cell_condensed_action.py 的 iter_reduced_contributions | reference contribution 仍调用 _materialize_Hhat() | 对高模式端口使用精确分块贡献，避免先构造整个 mode² 中间块 |
| task40_v10_p6_mumps.py | 持有 source/canonical CSR，并显式复制数据交给 PETSc createAIJ | 区分别名、实际 backing 与 PETSc/MUMPS 内部复制；若减少复制，验证存活期和不修改输入 |
| target、global reference、两个 sector 的构建 | 多套 carrier、凝聚/恢复、变换及原生作用需要共存 | 列清 owner 和最后使用阶段；只释放真实不再需要的对象，保持独立 native 检查 |
| target condensation 的 share_identity_cache 未显式开启 | 该选项默认 false，只涉及相同 interior shape 的实恒等矩阵共享 | 可采用既有只读共享能力，但收益必须实测；不能说它共享所有局部 LU/Schur 或解决全部容量 |
| allocation_gate_records 与事件/检查载荷 | 大量逐项收据被记录并在内存中保留 | 检查 Python 记录库存；可流式归档完整收据并保留有界摘要，安全检查频率和内容不减少 |

上述代码行为可由 [q 装配][S6]、[MUMPS 输入与生命周期][S7]、[Hhat 贡献][S8]、[worker 构建顺序][S9] 及恒等矩阵缓存实现逐项定位；哪些对象实际主导 E1 仍须用本机库存确认。

PETSc 提供以 CSR 数组建立顺序 AIJ、避免该接口复制数据的能力；数组须活到矩阵销毁之后，不能新增稀疏位置。[PETSc arrays 接口][P2] 这只是一个可验证的选项，不要求立即采用。当前 API 使用 createAIJ，不能根据另一接口的文档就把现有路径记为零复制。执行者必须检查本机已资格化 petsc4py/PETSc 版本的实际语义，保留因子前后输入哈希与独立 native 作用；不得为了省一份复制让残差检查和被测对象共同被修改。

## 4. V16 的工程合同

### 4.1 有界装配与正确性

主候选解决现有参考构建的复制和中间库存，不引入另一套 PC 数学。允许新增明确的装配策略身份，例如 BOUNDED_STAGING_CSR_V16；名字由源码/schema 一次统一登记，旧输入及 ordinary default 保留。

执行者选择最小可实现的分块累加方案，至少满足：

1. 不能为整个 Gx/E1 pattern 保留无界 Python set、全量贡献 COO 列表或所有局部稠密块。工作缓冲按块/行区间/批次有界，flush 及合并临时区也计入。
2. 256 MiB 可作为初始总 staging 上限，但须与现场余量及已存活数组共同准入；它不是每 q 各自再乘四的免费额度。实际峰值、allocator/Python 开销、最终 CSR 和旧结果比较用的第二份对象分开报告。
3. 局部贡献、投影、符号和端口左右作用保持。保留所有值及原覆盖范围，不能截去“小数值”或跳过旧非对角验证。不同累加顺序可产生浮点差异，不能要求字节相同，也不能凭“舍入”自动通过。
4. 在真实 B0/Gx contribution 上检验每个 q 的 shape、canonical CSR、全 mode 覆盖、独立 native 作用、非对角指标和完整恢复。原 operator/mapping 门不变；新旧矩阵差及范数保留，不能只比较 NNZ 或几个随机标量。
5. 上层计数先用安全宽整数。检查 rows、columns、实际 NNZ、indptr[-1] 及中间 offset 后才转 PETSc.IntType；不能只看行数，也不能溢出后再检测。
6. 用相关小型组件和实际入口测试一次接通 dat/schema、allowlist、profile、ABI、dispatcher、worker、输出/checker。不得等完整构建完成才发现新策略入口未注册。

### 4.2 构建对象的存活期

在首次必要候选运行中，记录以下阶段的同一进程树/cgroup 采样，以及对应唯一 backing buffer 库存：target 构建后、global reference 后、每个 sector 后、q CSR 后、all-q symbolic 后、每个 numeric 后、startup 后、KSP 后、reference 释放后、输出/checker 完成后。

每个主要对象列 owner、来源、字节、alias 关系、最后使用阶段、是否必要。源码中的多个引用不等于多个 payload；删除一个 Python 名字也不等于操作系统立即回收 RSS。既有 5.935 GB 的 Gx560 reference-PC cleanup 降幅只属于整套清理观察，不能全部归给 MUMPS 或当作任意阶段都能释放的容量。

允许修复真实重复持有、采用现成只读 identity 共享、减少安全可验证的 CSR 转换副本、复用同一次检查中的有界 workspace，以及流式保存收据。**不允许销毁下一次 PC 仍需使用的 local recovery/native action，或删除独立 global native 方程来制造省内存。**改变构建先后顺序只能消除确实不重叠的阶段，不能把最终仍须共存的 target/PC 隐藏到不同账表。

先按对象账本给出预期可释放量，再在同一必要流程验证实际 RSS/cgroup 的变化。若收益远小于 E1 约 6.72 GB 的历史差额，须明确说明；不能反复用同一未改变的构建重试 E1。

### 4.3 mode² 端口构建

原目标已有 32,060 个 AUTO 传播模式的清单。一个完整 32,060² complex128 稠密矩阵为 16,445,497,600 B；这是派生单对象 payload，既非整机峰值，也非“已经消除了端口瓶颈”的证据。32,060 还不是倏逝截断已收敛的完整最终模式数。

允许在现有 original-H、左右 C/D 和单元凝聚关系内，实现有界端口 tile/贡献迭代。数学上仍须包含 H 原项和全部内部消元修正，不能先物化完整 Hhat 再切片，不能把左右耦合假设为共轭对称。有限工作缓冲之外，最终 q CSR 中真正存在的端口块仍然要存储并可能使因子增长；**取消稠密临时数组不等于取消 mode² 的最终复杂度。**

用真实 p6 单元及端口数据验证：保留 450 internal、432 trace 的完整行空间及原 mode indexing；先在小模式可直接对照的情形检验全部相关块/作用，再在目标模式清单上完成一个有界构建/作用组件。不能用 2×2 玩具或未经资格化的 84-row 压缩代替完整原生行空间。目标模式组件不是目标全域 FE/PDE，也不授予截断精度。

若直接模式规模组件因真实容量/时间不准入，保留最大完整通过规模及精确阻塞数组、索引或时间，并完成第 6 节的参数化库存；不得为得到成功而悄悄减少模式清单。

### 4.4 数值与物理验收保持

| 项目 | V16 要求 |
|---|---|
| PC 策略 | 保持 V15；消元 FE、完整增广 FE、非抵消预算及每 q 实际 MatSolve 对应限值均为 1e-8 |
| factor 初始探针 | 仍为 strict 1e-10 |
| alpha closure | 1e-9；保留原尺度及冻结尺度 |
| 增广修正 | 每次 PC 至多一次完整修正，复用同四 q 因子，最多额外四次 q MatSolve |
| 最终真实 A6 | 原方程及释放后均不超过 1e-6；target identity 原 1e-10 门保留 |
| 物理输出 | E/H/curl 和全部模式有限；能量及体吸收一致性绝对门 1e-5 |
| 同离散保存场比较 | 沿原 FE L2/scaled-curl、E/H 和显著复模式 1e-4，R/T/A 绝对 1e-5，逐模式功率绝对 1e-6；近零量另报绝对误差，不拟合相位 |
| 外层与环境 | 零初值、FGMRES restart=32、max_it=2048、MPI1/数学线程1、complex128 |
| MUMPS | 后端、排序、主元、BLR、OOC 及线程沿既有设置；本轮不作参数扫描 |

每 8 步中间 A6 大于终态门是尚未收敛的正常状态，不触发提前失败；继续到真正终态、max_it 或真实安全/结构错误。新装配引起的误差必须经过现有门判断，不能另加经验 floor 或移动阈值。

## 5. 连续执行 P0–P5

| 阶段 | 实际任务 | 完成后行动 |
|---|---|---|
| P0 | 核对 V15 三类结果、保存场/输入/源码身份、现场进程和窗口；从已有原始事件提取可得父阶段与 E1 库存 | 缺少旧分项保持 unknown；不为了重建旧计时重跑 PDE |
| P1 | 实现有界 CSR 累加；依据对象账本修复构建复制/重复持有；必要的 Hhat 分块纳入同一构建路径 | 完成真实贡献/原生作用及入口资格；主控冻结新源码 |
| P2 | 同一原 Gx560 输入上完成一次新构建路线的 p6 target；与 V15 保存场比较 | 数值、物理与完整成本一起收口；通过且 E1 安全时直接 P3 |
| P3 | 原 E1，760 cells、588 retained modes、四 q，新构建路线 | 两个资源不等式和剩余全过程预算均通过后，在同次必要流程继续 numeric→startup→KSP→恢复/输出/checker |
| P4 | 完成目标模式端口组件、索引/库存桥接；有余量时完成一般 Ny 的小型原生映射组件 | 独立于 E1 是否可容纳；不启动全尺寸 PDE |
| P5 | response_v16、紧凑结果、成本/库存、readiness、run index 与项目账本；主控提交推送 | 回答明确工程问题后等待主审，不在单个普通 bug 后提前整轮收口 |

所有将用于 Gx560/E1 的构建核心改动，包括实际采用的 Hhat 分块，应尽量集中在 P1 后一次冻结；P4 的规模组件使用同一实现。若后续修改影响已经测过的真实数值入口，应重新资格化受影响部分，不能把不同源码的最好结果拼成最终源码 PASS；无关文档或元数据修改不触发 PDE 重跑。

**B0 不作为机械重复全求解门。**V15 的新合同已有 B0/Gx560 证据；若新改动只改变装配/存储且真实 B0 组件等价性足够，可直接做必要 Gx560 完整候选。若改动触及映射、归一化、target 作用或恢复语义，则在既有 B0 做一场必要完整 anchor，再继续 Gx560，不额外要求主审批准。

Gx560 新结果优先与 V15 的同输入 p6 场比较；旧 p6 target+p4 correction 结果按身份继续复用，不重跑旧 PC 路线。Gx784 不是前置门，E2 新参考路线本轮也不是必需项。

E1 保持原物理/网格/模式：10×4×19，588 retained modes=136 propagation+452 evanescent，手动 m=-10…10、n=-3…3。不得改为 AUTO 136 或减小缺口后仍叫同离散 E1。输入字段确有输出错误时，先修正确输出配置及 checker，不重做已经有效的场。

P3 没有资源许可时，只停止受影响的 numeric/PDE；保留 symbolic 与模式/矩阵身份，继续 P4。已取得 q CSR 时，可在 ignored artifact 保存可复用数组及独立 hashes，避免无意义重建；首次构建、写盘、后续读回、重建 native 检查所需对象和实际求解成本都要计入相应账本。只存在 hash 而没有数组时不能冒称已有可复用矩阵；复用运行不能写成 cold build。

### 一般 Ny 的边界

当前 p6 源码多处明确要求 global Ny=4、local Ny=2；只改 profile 常数或删除 assert 不能授予一般 Ny。P4 可在同一分支做一个小型 p6 原生映射/端口覆盖组件，优先选择 Ny=8，以保持现有缺口四分之一边界的精确几何位置；与 Ny=4 共用解析几何，不能通过移动缺口取得网格对齐。

只在组件中检验实际 Basix/dofmap、所有内部自由度、primal/dual 传递、伴随工作恒等式、完整 mode 分配和 K 相关 H/RHS/alpha 归一化。归一化从实际局部/全局关系推导，并验证，不能机械把所有数字 2 改成 K。该组件不自动改变已验证的四 q V15 PC 合同，不自动授权八 q 的正式 target 求解；全部 q 计数、预算和修正调用上限在正式扩展前还要整体资格化。

已有 dot 的 Ny6/K3/p4 校准只是迁移线索；其 Y 点移动了缺口，不能作为主线不变几何的 y 收敛或 p6 资格。[固定 dot V15][S11] 若 P4 Ny 组件不能完成，应明确失败的具体恒等式或覆盖项，不把“待研究”替代实际可执行的小型验证。

## 6. 目标尺寸的下一层资格

V16 至少产出一份可计算、字段有来源的 target readiness 包，不重复照抄 NOT_QUALIFIED 清单。

| 项目 | 本轮应补出的具体内容 | 仍不能声称 |
|---|---|---|
| 目标离散 | 候选精确 x/y/z 轴、接口/缺口平面；标明派生或实际构建；列下一次固定物理 y/z 误差对照 | 15,232 cells 已准确 |
| 方向精度 | 保留已有 x 对照；y/z 计划比较 E/H、散射场、curl、显著复模式及全部功率 | 小残差或能量闭合证明 h 收敛 |
| 一般 Ny | 当前硬编码清单与小型 p6 组件的实际输出；若未过写出具体项 | Ny4 成功等于任意 Ny 成功 |
| 外部模式 | 已有 32,060 AUTO 传播清单、ordered keys/hash、传播/倏逝资格边界 | 32,060 已是最终截断合格清单 |
| 端口中间数组 | C/D、原 H、Hhat、投影和每类 tile 的维度、copies、峰值阶段 | 单个 diagonal H 小就无端口问题 |
| CSR 和索引 | 每 q rows/NNZ/indptr 的实测或可靠结构计数；整数边界与未计部分 | rows 能放进 int32 就足够 |
| 局部缓存 | 各类 LU/Schur/恢复及变换唯一 backing；重复类与每 cell 独立类两种增长情景 | 规则矩形类共享收益对任意材料/几何都成立 |
| 因子 | 实际 all-q symbolic/numeric 分开；不能把最大 q 或 symbolic 数当总峰值 | 线性 cells 外推证明 2 TB |
| 全过程 | cold/reuse 口径、必需检查、恢复、I/O、同时内存及系统余量 | Gx 3 步证明目标 48 h |

目标候选 272×4×14=15,232 cells、约 10,228,620 full-storage rows、32,060 AUTO 传播模式来自既有计数/清单，保留其证据等级。y/z 名义网格不能只用自由空间 k0h 判死：1° grazing 的入射 z 分量较小，但三维散射谱和倏逝近场可能要求更细分辨率。应据固定几何的方向误差与真实谱决定 Ny/Nz，不能只加 Nx。

PETSc 的索引宽度是构建配置；仅将某个 NumPy 数组转 int64 不会令当前 int32 ABI 变成 64 位。[PetscInt][P3] 本轮不重装本机环境、不远程修改工作站。若计数证明当前 ABI 不足，产出所需 ABI 和最小迁移资格清单，保留当前分支的可运行小规模工程结果。

## 7. 成本与资源的报告方式

生产目标的单场时间应覆盖必要 JIT/构建、四 q setup、全部 startup/native 检查、KSP、恢复、输出、释放和最终必需 checker。父子阶段不能重复相加；独立启动的 checker 如果不在 worker 区间内，应另计实际区间，再给总关键路径或完整起止时间。**当前 2407.572 s 是 worker workflow，不应无证据地扩写成所有离线检查已经包含的最终 48 h 口径。**

至少同时报告：

- T_worker、T_required_checker、T_recovery、T_single_field_complete，以及 development/campaign charge；外部历史场比较属资格成本还是每场必要成本要说明。
- cold build 与缓存复用各自必要成本。比较同一问题使用相同 solver、模式、精度和检查范围；不能只扣除新路线检查。
- 同时 process-tree RSS peak、cgroup memory peak、task/cgroup swap、系统余量及峰值阶段。树 RSS 可能含共享页重复计数，cgroup 包含的页缓存也可能影响容量；两者分列，不相加。
- 四 q 同时 numeric 因子数、MUMPS 原始字段及当前版本可解释的 allocated/used；INFOG9 无合格解码依据则继续 raw/unknown。
- 每次完整 PC 时间和内部 q MatSolve/修正次数；最多一次增广修正的全部成本不得隐藏。
- 对未归属时间和内存保留 unknown；新运行补直接计时，不用差额强行给某个阶段命名。

Gx560 优化是否采用，以完整成本和容量趋势判断。没有预定必须更快的秒数门，不通过挑快样本反复运行；若速度基本不变但确实减少必要同时内存、使更大案例安全完成，应作为容量进展报告。若只减少测试数、日志字数或外层步数，而目标场/构建能力未提高，不能作为本轮主要成功。

## 8. 自主修复与窗口

本报告前瞻授权上述阶段内的必要实现和常规修复。普通 NameError、schema/allowlist/ABI 注册遗漏、checker 路由、序列化、输出尺寸、已可定位的数组存活期问题，先一起检查真实调用链、修复并做相关验证，然后继续剩余授权阶段。不得因一次 bug、进入新阶段或旧文档导航就停在 WAITING_FOR_REVIEW。

但以下是真实边界：错误材料/几何/模式身份、NaN/Inf、损坏因子、原数值/物理门未达、task swap、真实资源不足或窗口终态。它们不能通过改阈值、抬 cap、删模式、增加真实损耗或伪装结果绕过。受影响路径停止后，继续不依赖它的 P4/P5。

已经保存有效解时，输出/checker 修复默认从保存场恢复；先独立重算 A6/身份，再恢复物理输出。旧聚合 map hash 不一致仍未解释，但九个组成数组及 MPC 的已归档精确比较保留；以完整身份向量核验，不能只为修聚合哈希重新求解。新的逐项身份不一致则是真实阻塞。

E1 曾有一次 102.788 s 的执行协调中断，raw USER_CONTROLLED_STOP 标签与“并非用户要求终止”的派生原因均保留。后续主控发状态或审阅沟通不构成 kill 指令；只在明确用户停止或真实 watchdog/safety 条件下终止运行。运行期间不热改冻结数值源码。

旧固定窗口 T0=2026-10-06T23:21:33.326800586Z，deadline=2026-10-07T23:21:33.326800586Z。最新归档收费观察为 59474.428829 s，但主控必须读本机当前值，不能把旧 remaining 当实时余量。若原窗口仍有效，先沿用；若已自然结束或有真实 terminal receipt，本报告授权主控建立一个独立、最长 24 h 的 V16 工程窗口，预留 600 s 收口。不得重叠、修改旧 T0/deadline、清零历史费用或反复刷新新窗口。窗口到期只停止依赖计算，已有结果和后续可完成的收口保留。

开发窗口与最终单场 48 h 是不同口径。最新主审授权的连续推进优先于已完成旧轮的阶段上限；不因此增加主机或解除零 swap/物理验收要求。

## 9. 交付及下一次主审要回答的问题

新增 response_v16.md，并同步当前 summary、test summary、run index、development_model_registry、development_progress。历史段落及原失败不可覆盖。建议只用四份紧凑 records，避免再扩散平行权威：

| 文件 | 关键内容 |
|---|---|
| review_v16_build_and_memory.json | 构建实现、父阶段、staging、backing/owner、E1 准入差额与源身份 |
| review_v16_formal_results.json | Gx560、条件 E1、必要 B0；全部 residual/physics/field/模式比较与完整成本 |
| review_v16_target_components.json | 目标模式端口组件、实际索引、一般 Ny 组件、资格边界 |
| review_v16_cost_and_readiness.json | 冷/复用、checker、窗口费用、目标未关闭项与下一项明确工作 |

重型数组、q CSR、场、timeline 和 raw evidence 留在 ignored artifact，Git 只放 compact、路径和 hashes。测试按本次改动做最小相关集合和既有必要门；最终记录实际源码/ABI。既有 61 passed 是路由、恢复与增广修正 targeted suite，不是 full repository pytest、MPI4、Ruff 或 CI 通过。

response 首先回答：

1. 新构建路线是否完整解通原 Gx560，场和全部模式与 V15 是否一致？
2. 同时内存实际减少多少，哪些对象释放/共享，完整必要时间改善还是恶化？
3. 原 E1 是否取得新参考 PC 的完整场？若仍不能，两个不等式缺多少，哪项必要库存主导？
4. 目标模式端口构建是否完成真实有界组件，哪些 mode²/NNZ/int32 风险已经用数据关闭？
5. y/z、一般 Ny 和目标精度还缺什么；下一轮选择哪一个具体阻塞，不再回到已验证的 PC 准入门调整？

**期望的实质结果是：一个完成过目标场验证的构建改进，以及 E1 完整解或带明确容量原因的停止；同时取得目标端口/索引的真实组件进展。不能只交新的预测表、测试计数或更少的迭代步数。**

## 10. 证据入口

以下仓库链接固定在本次审阅基线，避免后续 summary 更新改变本报告依据。外部官方资料只支持通用 API/算法语义，不替代本机 ABI 与容量实测。

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/response_v15.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/outcomes/records/review_v15_formal_results.json
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/outcomes/records/review_v15_native_pc_contract.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/outcomes/records/review_v15_cost_and_readiness.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/outcomes/records/review_v15_failure_witness_and_repairs.json
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/src/solvers/task40_v10_p6_yorbit.py
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/src/solvers/task40_v10_p6_mumps.py
[S8]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/src/solvers/p6_cell_condensed_action.py
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/src/runners/task40_v10_worker.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/f59884b1a98b329cfce2a3de8307dd3db8560520/docs/task40extra_0p7nm_engineering/outcomes/v14_engineering_to_target.json
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/15713d3e09b63f65511c7b7f61fa043fdb23dca5/docs/task40extra_dot_parallel_cloud/response_v15.md
[P1]: https://petsc.org/release/manualpages/KSP/KSPFGMRES/
[P2]: https://petsc.org/release/manualpages/Mat/MatCreateSeqAIJWithArrays/
[P3]: https://petsc.org/release/manualpages/Sys/PetscInt/

- [V15 实算回应][S1]、[正式结果与同离散比较][S2]、[逐次 native PC 合同][S3]、[成本与目标 readiness][S4]、[失败及恢复见证][S5]。
- [q 装配及 reference builder][S6]、[all-q 因子与存储][S7]、[p6 原生贡献与 Hhat][S8]、[完整 target worker][S9]。
- [Review V15](review_report_v15.md)、[任务书](task.md)、[最新测试摘要](outcomes/test_summary.md)、[恒等矩阵缓存实现](../../src/solvers/hcurl_assembly_time_condensation.py)。
