# Task40extra Review V27：完成完整数值 CSR，进入可执行的单 q 分解阶段

## 0. 审阅结论与本轮决定

**V26 有实质进展：完整 q0 保存流消费者、q0/q4 配对检查及完整行计数结构均通过。下一步的主交付应是同一个完整 q0 的数值 CSR，不再重复已有 native 资格，也不再扩大有限面板。** CSR 是把矩阵每一行的列编号和复数值按紧凑数组保存的表示；目前只知道这些数组需要多大，还没有填出完整矩阵值。[R1]、[R2]

本次接受 V26 的受控资源停止。它说明当前执行路径在本机 16 GiB 限制下无法分配完整 CSR，并未说明 2 TB 目标失败。源码审阅已找到可以直接推进的工程改动：**让保存数据到 CSR 的路径脱离 FE/MPC/native 重建，真正只装 q0 必需映射；先用已知全量规模准入，再做完整结构和填值，并保存可恢复的成果。**[R5]、[R6]

同时，现有单 q 分解入口已经实现。当前完整结构表示下，仅源 CSR 与明确的转换副本合计就有 23.09 GB；现行分解入口的保守准入预算约为 80.88 GB，尚不含其他对象和系统余量。释放 FE 对 CSR 有意义，但不能据此承诺现行 factor 路径会在 16 GiB 内完成。V27 必须交付独立的 CSR 续作/分解入口和具体资源交接包，让下一份完整分解成本可以直接取得。[R7]、[R8]

本轮总体判断：**partial_with_material_progress；批准下述同分支、有界连续推进范围。** 完整 8-q、真实 target 全解、最终离散精度、2 TB / 48 h 和 master merge 继续未资格化。本报告不新增预条件器，不改变已冻结数学模型或 ordinary solver default。

## 1. 审阅身份、范围与证据强度

| 项目 | 冻结身份或范围 |
|---|---|
| 仓库 / 执行分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 本次最新结果 HEAD | `399787abc991e0e30975bc694bd18a9a30c5470e`，2026-10-11 12:29:53 UTC |
| V26 最终科学源码 | `f9093c87f81d52b75fbc156e562b3745df45ccf4`；结果 HEAD 是其后文档与证据提交 |
| 上一份 Review V26 | `83c4fed6e29ea19f0a70a92a403b867851f3ef35` |
| 本次审阅增量 | 上一 review 至结果 HEAD 共 4 个提交、21 个文件；包括完整消费者、行结构保全、受限单 q 分解和监督/回读代码 |
| 新运行 input SHA-256 | `134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b` |
| 旧 producer source | `9d0f4dbfc730dd620b709d048e33e9da6c77520c` |
| native 数据实际生成源码 | `3a61e61caf638678d483b6fa06f36374abeef67d`；最终源码只读恢复这三组数据 |
| 本次 Chat 工作 | 读取远端 tracked 结果、run index、源码及相关测试；独立复核内容 hash 和容量算术；没有启动 FE、PDE、工作站或新的执行者 |

本次独立复核的三个 V26 compact record 与 response、summary、test summary、README 共七项，均与 run index 的 SHA-256 一致，见附录 A。重型原始数组位于执行机 ignored artifacts；本次 Chat 没有下载重跑它们。数值接受依据是冻结原始数据身份、执行机已完成的独立数组 checker，以及本次对实际生成/恢复/检查代码的审阅，不能表述为 Chat 又运行了一次独立 Maxwell 求解。[R1]、[R2]、[R9]、[R13]

### 1.1 三种模型范围必须继续分开

| 对象 | 物理与离散范围 | 当前能证明的内容 |
|---|---|---|
| 既有缩小 0.7 nm 模型 | 保留非分离三维缺口、缩小物理长度的小电尺寸模型 | 已有完整离散求解和部分对照；它是方法资格与误差研究的起点 |
| 原尺寸 target pilot | 50×25×140 nm，Nx272 / Ny8 / Nz14 / p6，30,464 cells，真实非分离 Si/air | V25 完整体积作用、凝聚 RHS 与保存见证恢复通过；完整 target 场尚未求出 |
| 本轮 q0/q4 regular reference | 原尺寸父问题对应的规则参考，去掉 notch/void；实际局部参考网格 272×2×14，7,616 cells | 完整保存流与配对投影通过，q0 行计数完成；数值 CSR 和 factor 尚未完成 |

q 表示参考问题利用周期结构拆出的一个分支块；计算这个块是为完整三维 target 的求解提供参考逆作用，不是把真实缺口器件改成规则几何。当前 q0 的 777,644 行也不能当成完整 target 的未知量总数。既有 `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` 是 parent target 身份，不能仅凭它声称实际 reference 几何完全等于 target。[R2]、[R11]、[R12]

## 2. V26 哪些成果接受，哪些尚未完成

### 2.1 完整消费者通过：这一关已经可以关闭

下表数值来自 V26 保存数据/原数组 checker 的记录，属于 measured 证据；门限沿用 1e-11。对角响应是同一 q 输入产生的同 q 输出；跨 q 输出理论接近零，必须用对应非零对角响应作尺度。[R2]

| 检查 | 实际数值 | 判断与范围 |
|---|---:|---|
| q0 非零输入 1：保存流与 native 对角输出 | 1.9111641039085683e-14 | PASS，完整 q0 消费者 |
| q0 非零输入 2：保存流与 native 对角输出 | 1.9037676533525363e-14 | PASS，两组不同输入 |
| volume 分量 | 1.9111718756701163e-14 | PASS，保存 Schur/约束/投影与 native 体积路径一致 |
| C、−D、Hhat 分量 | 各 0 | PASS；共同使用已保存 surface 数据，不是新做第二套表面积分 |
| q4 对角输出 | 1.892511654260487e-14 | PASS，配对分支作用范围 |
| q0→q4：泄漏 / 对角尺度 | 2.407288081764573e-16 | PASS |
| q0→q4：stream/native 差 / 对角尺度 | 3.313929355217115e-16 | PASS |
| q4→q0：泄漏 / 对角尺度 | 2.3258027571170525e-16 | PASS |
| q4→q0：stream/native 差 / 对角尺度 | 3.273401604609453e-16 | PASS |

恢复代码不是只信任旧 PASS。`_v26_native_case_recovery_readback` 核验旧 source、精确失败叶节点、input/model/mode/producer 身份和数组哈希，从三组保存的输入输出重新计算对角、分量、双向 leakage。独立 partial checker 再次从数组计算并对照恢复回执。依据 [R9] 的 3700–4034、4414–4581 行，以及 [R5] 的 1274–1308、3199–3240 行。

记录中约 1.25 的“相对于极小跨 q 输出”的未缩放误差不构成新的失败。正确门限已经按非零对角响应归一化，尺度严格检查有限且大于零。这项定义应保留，不为了无意义的小分母重新做一轮实验。

V26 第二次 attempt 实际执行并保存三组 native case，随后因 `minus_D` 与真实键 `-D` 不一致而失败。最终 attempt 只读恢复成功，没有重复 native。旧 native 实测调用数和耗时未及时持久化，继续保留 NOT_RECORDED / UNKNOWN；源码可推导的 6 次 volume apply、9 次 provider sweep 不能改称实测计数。**无需为补齐历史计时再重跑已有 native 资格。**[R2]、[R3]

### 2.2 完整行计数通过，完整数值矩阵仍未生成

| 对象 / 指标 | 值 | 数据身份与边界 |
|---|---:|---|
| q0 矩阵形状 | 777,644×777,644 | measured；其中 trace 773,568、端口 aliases 4,076 |
| 完整结构预分配位置 | 577,061,168 | measured structural positions；不是已填值的 numeric nnz |
| 行计数 / 宽 offset 数量 | 777,644 / 777,645 | int64；最后 offset=577,061,168；全行一致性通过 |
| 结构索引容量 | 低于 int32 上界 | 当前资格化 PETSc int32 可表示此 q0 结构 |
| 已保存行结构 NPZ | 12,442,866 B | measured 文件大小；仅 counts/offsets 和其 manifest |
| support descriptor / route 数量 | 94,416 / 3,428,612 | measured 路由盘点；descriptor 字节 2,393,989,904 B |
| 完整数值 CSR | 0/8 | q0 也尚未 materialize；data/完整 columns 未交付 |
| factor / KSP / target PDE / official R/T/A | NOT_RUN | partial checker 26/26 true 与 worker exit 0 不改变此边界 |

这一结果使容量不再需要用小面板猜测。在保留当前所有结构位置、complex128 值和 int32 列/offset 时，纯数组容量为：[R2]、[R6]

```math
\begin{aligned}
B_{\mathrm{CSR}}&=(16+4)N_s+4(n+1),\\
n&=777{,}644,\qquad N_s=577{,}061{,}168,\\
B_{\mathrm{CSR}}&=11{,}544{,}333{,}940\ \mathrm{B}.
\end{aligned}
```

这是根据已测结构推导的 11.54 GB 数组量，不是 11.54 GB 的实测运行峰值，也不是 MUMPS 因子大小。V26 新增准入上界为 11,570,765,788 B，其中比纯 CSR 多出的 26,431,848 B 是该阶段计入的工作区。最终填值后应分别报告 stored structural slots、实际非零复数项及保留的 exact-zero 项。[R2]、[R3]

### 2.3 资源停止是有效结论，不能原样重试

| V26 CSR admission 时刻 | 字节 | 说明 |
|---|---:|---|
| 本阶段新增需求 | 11,570,765,788 | 完整 CSR 与该阶段工作区 |
| host/tree 实际可新增量 | 4,833,513,472 | 已扣 134,217,728 B 证据余量 |
| host/tree 缺口 | 6,737,252,316 | 单独约束 |
| task cgroup 实际可新增量 | 4,996,231,168 | 专用上限 17,179,869,184 B，另扣证据余量 |
| task cgroup 缺口 | 6,574,534,620 | 单独约束；不能与上一缺口相加 |
| admission 时 tree RSS | 8,687,230,976 | 不是整个 worker 的峰值 |
| admission 时 cgroup current | 12,049,420,288 | 包含与 RSS 不同的记账范围 |
| 整个 final worker 的 tree / cgroup 峰值 | 11,631,017,984 / 12,059,959,296 | 两种口径分开，不相加 |
| task swap | 0 | 本任务未靠 swap 撑预算；disk gate 通过 |

host-wide swapin/swapout 增量为 164/3,489 pages，不能归因成 Task40 的 swap。checker 的独立阶段 tree 峰值 911,728,640 B 也不能与 worker 峰值相加。V26 在分配之前停止并清理后代，属于有效监督结果。[R3]

### 2.4 成本已经有记录，但还不是一次 factor 的成本

| 区间 | 耗时 | 正确用途 |
|---|---:|---|
| 最终 q0 stage 父区间 | 2,352.2791 s，约 39.20 min | 包含其内部阶段 |
| CSR structure/admission 父区间 | 1,556.4472 s，约 25.94 min | 嵌套于 q0 stage，不能再相加 |
| worker watchdog monotonic | 2,410.6999 s | worker 监督区间 |
| 外层连续工作链 monotonic / conservative | 2,419.7040 / 2,690.1395 s | 首个外层时钟至父流程结束，含 run_case 与 required checker |
| 独立 systemd 生命周期 monotonic / UTC | 2,497.6893 / 2,775.3308 s | 范围不同；不与外层链相加 |
| 数值 CSR fill / symbolic / numeric factor | NOT_RUN | 目前不能给其吞吐、fill 或 48 h 实测外推 |

外层链前的 75.9554 s 启动区间归属仍 UNKNOWN，已包含在 service/campaign 范围，不能再补加一次。V26 结项前账本快照耗用 17,830.5559 s，数值余量 2,569.4441 s；它截至 12:08:08.554017 UTC，不包含之后全部文档、推送与回读。保留后续 append-only ledger，不能把该快照冒称完整批次最终费用。[R3]、[R4]

## 3. 本轮最需要改变的实现路径

### 3.1 新窗口直接导入已通过的 V26 证据

当前 V26 专用恢复入口对 source/window 的处理不适合直接搬到新窗口：标准 native manifest 复用要求 current_identity 全等；恢复文件按 source 命名，已存在会拒绝；恢复两代数据的 shared keys 包含 campaign_window_sha256。直接把 V27 新 source/window 填进去，会在数学数据完全相同时再次碰到身份错误。[R8] 1526–1617；[R9] 3782–3792、3924–3926。

V27 应增加一个薄的只读 donor 导入步骤：先按原 donor 身份验证已通过的 V26 native recovery manifest、checker 和原输入/输出，再在新的消费记录中单独绑定 V27 source/window。数学与 payload 身份必须相容，包括实际 reference 几何/离散、材料、Bloch/sector/alias、mode 顺序、原 H、active lookup、q map、volume/surface 数值及相关 ABI。原 parent target hash 单独相等不够。

旧 producer source、native source、recovery source、旧窗口和原数组 hash 原样保留；新源代码只对本次消费负责。输入文件若仅因 route/阶段选项变化而不同，应显式比较决定算子的字段并保存差异，不能静默把不同 input SHA 当作同一份文件。也不能为了让 current_identity 相等而刷新旧窗口、重写旧数据或重复 native。

### 3.2 把 CSR 构建从 FE owner 中分离出来

当前 `perform_native_validation=False` 只跳过 native action 调用，不跳过 FE 构建。`run_task40_v25_selected_q0_consumer` 仍会创建 mesh、p6 space、Floquet/MPC、surface assembler、transform bank、volume form/JIT、局部凝聚和 fresh q0/q4 maps；再加载旧双 maps 比对，最后才统一释放。[R5] 2443–2630、2653–2683、2791–2869、4041–4064。

V27 的主改动是一个**仅依赖已保存贡献的适配器**，复用 V17 已有精确投影/累加器，提供原来的两个接口：

- `iter_reduced_contribution_layouts(...)`：给出每个贡献在局部约束后 reduced 空间（trace＋port）中的行列，不能混用原 FE storage 编号。
- `iter_reduced_contributions(...)`：给出同一贡献的真实复数值，逐个消费。

体积部分直接使用已保存的 cell active IDs、expansion 和 class Schur，沿原 `E_K^H S_class E_K` 约束公式产生局部贡献。C、−D 直接消费已处理 MPC 的 surface 数据与原 active lookup；−D 保持普通转置/普通 dot 和负号，不增加共轭，不再次施加 MPC。H 保持原对角/缩放定义；direct-only reference 的内部零支撑仍检查，遇到非零 unmapped 值不能静默丢弃。[R5] 937–1265；[R14]；[R15]

这些数值公式已经用于通过 native 对照的保存流 matvec。这里改变的是对象所有权与读入流程，无需另写求解器、换 PC、重新积分或复制另一套投影算法。新增可复用能力放在合适的 src 模块，stage/service 只负责路由、监督和回读；不开展全文件架构重写。

选定 q0 路径还应只装并索引 q0 所需 map。当前 V17 即便只请求 `(0,0)`，仍遍历两张 q map 生成左右 support。[R6] 2309–2352、2374–2405。可以限定实际请求的 branch；不能传伪造的第二张 map，也不能借此放宽全 8-q backend 的覆盖合同。q4 的已通过 witness 可以按需读取，不必随完整 CSR 构建长期共驻。

### 3.3 先判定轻量 worker 的真实余量，再花时间重建全结构

目前已经知道完整 q0 的结构规模，所以没有理由再先做约 26 分钟结构扫描，最后才检查同一笔完整 CSR 需求。V27 在只装必要保存数据后，先按现有完整 payload 规则采样并预检；实际 allocation 前继续执行原实时门。预检并不保证随后资源一定不变。

仅作对 V26 当时快照的派生解释：若其他 host 状态不变，dynamic tree cap=13,520,744,448 B，扣新增需求后，CSR 前 tree RSS 需不高于 **1,949,978,660 B**；对应 cgroup 基线上限为 **5,474,885,668 B**。它们不是新冻结的通用 cap。V27 应记录新鲜 host availability、tree RSS、cgroup current/anon/file/dirty、全部 live owner、投影 workspace、读写/hash 缓冲和监督余量，重新计算。[R3]

q0 map、整个 volume stream、lookup 和 H 四项文件合计 596,278,287 B，只说明保存格式有机会支持轻量路径；**它不是 RSS 预测或完整预算**。约 11.23 GB 的 surface stream 还需按块读取，不能一次装入内存；压缩载荷解码、Python 容器、文件页和工作数组均须实测或有明确上界。[R11]

**继续保留 mmap 页的资源计费。** 当前 V17 已把完整映射 payload 保守纳入 admission，因为写入、校验和 matvec 会触发文件页与 dirty pages。不得只因数据放在磁盘，就把 11.54 GB 需求改为零。若将来改变为更严格的有界读写生命周期，应另用实际所有权与 file/dirty 峰值证明它，不能先降低门再宣称通过。[R6] 2740–2779。

若轻量路径仍拒绝，保存新实测的精确缺口和可执行交接包，不再重复同一固定 cap 的启动。数值资源不足不应改写成接口 bug，也不应通过提高 cgroup cap、使用 swap 或借用其他任务环境强行通过。

### 3.4 完整计数是规模见证，V27 要保存真正能续作的结构

V26 的 `support_routes.sqlite3` 位于 TemporaryDirectory 中，正常或异常退出都会清理；保存的 NPZ 只有 counts/offsets。源码明确写着 route 需要通过 layouts replay 重建。[R6] 2164–2175、2688–2713、2913–2939；[R5] 3519–3564。

因此，V27 允许一次必要的 support/column 重建；旧 counts/offsets 用于提前容量判断和逐行校验。这一次应持久保存已有格式中的 support/routes、完整 indptr/indices 与关联 manifest，明确阶段为 `STRUCTURE_COMPLETE_VALUES_PENDING`。若只保留 q0 支撑导致 descriptor 数量或 route hash 改变，应保存新旧表示各自的身份，不能要求与旧双-map route hash 字节相同；完整 q0 行计数和数值作用仍须一致。

填值未完成时标 `NUMERIC_FILL_INCOMPLETE`，完成全域并验收后才标 `COMPLETE_CSR`。不要求在本轮开发通用事务平台：完整 pattern 可以复用；若数值累加没有可靠游标与一致性设计，中断后从明确清零的数值阶段重启，不能在旧半成品上直接重新累加造成双计数。每个已完成的大阶段及时原子保存，不能等 factor 完成后才写 CSR 成果。

### 3.5 完整数值 CSR 的验收就是下一次实质进展

完成全部行列和 complex128 值后，必须交付完整三数组、shape/dtype、排序唯一列、范围检查、stored slots、numeric nonzero、exact-zero slots、字节及 hash。从文件独立回读，并用已有两组非零 q0 输入与保存 native 输出比较；volume/C/−D/Hhat 分量继续使用各自 1e-11 门限。保留 donor q0/q4 双向 leakage 与原 H 资格。[R5] 3680–3797。

不要只用新 CSR 与同一适配器自相比较代替 native 见证。也不要为获得 CSR 通过要求先完成 factor。当前 stage 已在 factor 资源不足时保留 `RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR`，这是正确层级，应沿用。[R8] 1868–1919。

填值后可以报告精确零带来的潜在压缩量，但不把压缩作为前置研究。只能删除严格等于零的值并重新绑定数组身份，不能按阈值丢弃小复数项冒称无损。单是 q0 H 的所有非对角位置即使都无损删除，派生节省也仅 332,194,000 B，不能解决本次约 6.7 GB 的缺口；其他部分未知，不预先记入容量收益。[R6]

## 4. 单 q 分解：入口已有，资源与成本尚未实测

### 4.1 接受现有受限入口，不重复造一个预条件器

`run_task40_v26_selected_q0_factor_lifecycle` 明确只接受一个完整 q0 CSR，执行输入检查、PETSc 转换、symbolic、numeric、fresh probe、另一组非零 RHS solve 和 factor/Mat/Vec 销毁。它不再假造 `q_count=1` 规避完整 profile 的合同；两次 solve 都以原 CSR 的完整 true residual≤1e-10 验收。[R7] 80–97、168–205、254–443、452–519。

symbolic 是先分析稀疏消元结构并给出后续内存估计；numeric 才真正计算因子。单 q 的这段完整生命周期能回答“一个块究竟多大、多贵”，但不能证明完整 reference inverse、target KSP 或原尺寸场已通过。

V27 应让该入口直接接收已完成的 CSR manifest，在独立资源阶段加载，不为到达 factor 再重跑 producer、native 或结构。当前 stage 传入 `resident_csr_admission=None`，因此 selected_q0 中那段可选 resident upgrade 未执行，不能把它当作 V26 的实际 bug；真正的全量 RAM 加载在 stage 的 factor 入口。[R8] 1641、1758–1801。

### 4.2 为什么现行完整结构下，16 GiB 无法直接推进 factor

以下是源码派生的现行准入预算，假设保留全部 577,061,168 个结构位置。它不是实测因子峰值。[R7] 212–247。

| 分项 | 字节 | 生命周期含义 |
|---|---:|---|
| 已驻留源 CSR，B | 11,544,333,940 | stage 先把完整三数组读入 RAM |
| PETSc input 上界 | 11,544,333,940 | 新建输入矩阵 |
| 显式转换数组 | 11,544,333,940 | indptr/indices/data 各 copy；构建后释放 |
| symbolic guard | 46,177,335,760 | 现行 max(128 MiB,4B) 规则 |
| 六个 complex128 向量 | 74,653,824 | probe/solve/checker 工作空间 |
| 转换前所需新增余量 | 69,340,657,464 | 源 CSR 已计入当前资源采样 |
| 加源 CSR 的准入账 | 80,884,991,404 | 约 80.885 GB / 75.330 GiB；还需其他 owner 与系统余量 |

```math
\begin{aligned}
V&=6n\times16=74{,}653{,}824\ \mathrm{B},\\
\Delta M_{\mathrm{admit}}&=B+B+4B+V=69{,}340{,}657{,}464\ \mathrm{B},\\
M_{\mathrm{envelope}}&=B+\Delta M_{\mathrm{admit}}
=80{,}884{,}991{,}404\ \mathrm{B}.
\end{aligned}
```

即使暂不考虑保守 symbolic guard，显式源 CSR 加转换数组也已有 **23,088,667,880 B，约 21.503 GiB**，超过本机 16 GiB 硬上限。减少 FE 常驻并不能改变这两份明确副本的重叠。

这项判断只针对当前表示和代码。未来完整 numeric CSR 若经有证据的精确零压缩或所有权优化改变了实际 B，应按新的真实对象账重算；不能把未做的优化先算成收益。也不能把 80.885 GB 写成“单 q 已测出要这么多内存”或“给 96/128 GB 就保证 numeric 成功”：symbolic 的真实估计、numeric fill、临时工作区和峰值仍待实际测量。

### 4.3 资源交接包要能直接执行

V27 本轮就准备受限单 q 的独立 continuation 入口和可审阅材料，不把后续资源安排留成一句“换机器再看看”。交接包至少包含：

1. 精确源码、branch、producer/native/recovery/current 身份关系，实际 regular reference 几何/模式/alias/数组合同；已存在的数据路径、文件大小、SHA-256 和完整性状态。
2. CSR 三数组及 manifest；若本机真实 gate 阻止填值，明确其为 `CSR_PENDING`，提供仅依赖保存数据的 build 入口与实际已保存的结构见证。若预检即停止、只有 V26 counts/offsets，应如实标注；仅在完整 pattern 已生成时附 indptr/indices，不能为了交接去执行被拒绝的构建，也不伪造完成的文件。
3. 复用现有通用 service/run_case/stage 的参数化调用或最小必要 continuation 模式，含 ABI preflight、单 heavy、host/tree/cgroup/task-swap、阶段截止、checkpoint、checker 和清理规则。未指定的执行目录/环境使用显式待填写字段，不能臆造已验证主机。
4. 分开列出 build、CSR retention、转换、symbolic、numeric、probe/RHS、释放与 checker 的资源合同；symbolic 完成即保存原 INFOG，再判 numeric，不能以预算门未通过抹去前一阶段成果。
5. 只需一次完整 fresh factor＋另一 RHS 的生命周期成本样本，分开记录 parent 时间、原 INFOG/factor entries、对象共驻数、tree/cgroup 峰值和 task swap。默认不反复 benchmark。

当前 Task40 `AGENTS.md` 明确限制本机 canonical worktree，禁止 SSH、切换工作站或其他项目/主机。本报告因此**只准备完整交接，不自动执行跨主机迁移或抬高本机 cap**。这项边界来自现有任务执行规则，不影响本轮继续完成 saved-only CSR、测试与交接准备。主控安排后续分解时，需明确 Task40 的目标环境身份和相应资源合同；不能借用其他任务已有权限。[R16]

## 5. 怎样把当前成果转化为 2 TB / 48 h 的路线

### 5.1 不再要求小模型无限变好

缩小模型的目的，是低成本验证数学接线、参考解、恢复、物理输出和误差比较，并观察真正的内存/时间构成。这些证据不能代替原尺寸精度，但已经足以支持当前转向原尺寸组成部分和完整矩阵。现在的优先级是**把完整 q0 变成实际可分解对象**，不是继续优化一个已经通过的小模型迭代数。[R11]、[R12]

本轮没有新的完整 KSP 结果，所以没有证据说 V26 的预条件器更快或更省内存。现有单槽 factor 的收益，是降低同时保留的因子数；代价是切换 q 之后可能反复分解。全 q CSR 本身仍常驻。两项开销必须分别记录。[R7]

### 5.2 2 TB 应约束完整同时共存账

2 TB 固定为十进制 **2,000,000,000,000 B 整机物理内存**，包括 OS/其他占用及必要余量；不是给单进程的全部可分配 RSS。生产验收仍要求 task swap=0。

```math
\begin{aligned}
M_{\mathrm{budget}}(t)={}&M_{\mathrm{OS,other,reserve}}+M_{\mathrm{FE,MPC}}\\
&+M_{\mathrm{local,maps,ports}}+M_{\mathrm{q\ CSR}}\\
&+M_{\mathrm{factors,work}}+M_{\mathrm{Krylov}}
+M_{\mathrm{recovery,output,check}},\\
\max_t M_{\mathrm{budget}}(t)&\le 2{,}000{,}000{,}000{,}000\ \mathrm{B}.
\end{aligned}
```

单 q0 的全部结构 CSR 约 11.54 GB。若仅作“八块都与 q0 相同”的情景，则是 92,354,671,520 B，约 92.35 GB；**它不是已测全 8-q 总量**。其他 q 的 aliases、相位、结构和因子 fill 可能不同。这个数量至少说明，当前 16 GiB 拒绝不能推出 2 TB 拒绝；真正还需要测的是全 q 结构、因子及共驻生命周期。[R2]、[R7]

原尺寸 pilot 的 6,188,544 active trace rows，complex128 主 FGMRES 方向组按 2m+1 个向量估计：m=30 为 6,040,018,944 B，m=60 为 11,981,021,184 B。这也是 derived 的部分库存，尚不含端口、额外 scratch、实现附加向量及最终精度网格增长。不得把这部分单独作为总峰值。[R11]

### 5.3 48 h 必须计入每一次 factor 重建

`ONE_Q_REFACTOR_V19` 保留所有 q CSR，初始化逐 q symbolic 后销毁临时对象；完整 reference action 遍历 8 个 q，单槽每次切换就驱逐。通常下一次完整 PC 调用又要逐 q 转换、symbolic、numeric 和 fresh probe。q0 一次 factor 通过不能乘一次 8 就当作整场 setup 已付完。[R7] 1647–1694、1885–2016、2204–2232；[R6] 850–905、949–964。

```math
\begin{aligned}
T_{\mathrm{field}}={}&T_{\mathrm{prepare,JIT,build}}+T_{\mathrm{initial\ symbolic}}\\
&+\sum_{q=0}^{7}F_q\,T_{\mathrm{rebuild},q}
+\sum_{q=0}^{7}S_q\,T_{\mathrm{business\ RHS},q}\\
&+T_{\mathrm{PC,other}}+T_{\mathrm{target\ actions,Krylov,checks}}
+T_{\mathrm{recover,output,final\ checker}}\\
&\le172{,}800\ \mathrm{s}.
\end{aligned}
```

F_q 是真实重建次数；rebuild 含转换、symbolic、numeric、fresh probe、evict，以及相应身份/准入外围成本。S_q 是另计的业务 RHS solve，不能再次包含已经计入 rebuild 的 probe。PC,other 单列参考预条件器内部的 q 投影、坐标传递、局部凝聚/恢复、端口处理和 augmentation 外围费用，排除已经单计的 factor 重建与 q solve。主 operator、PC 调用次数、原 A6 定期检查、恢复与输出均需实测归账。V25 完整体积诊断的父耗时包含构建、见证与恢复，不能除以见证数当作单次 matvec 成本。

以下只是情景算术，假定一个 q 的完整重建周期如下，且暂时忽略其余所有费用；不表示当前实测速度：

| 每 q 重建周期 | 每次完整 PC 的 8-q 成本 | 48 h 理论最多次数 |
|---|---:|---:|
| 1 min | 8 min | 360 |
| 5 min | 40 min | 72 |
| 20 min | 160 min | 18 |

实际次数上限更低。这解释了为什么迭代次数下降不自动等于端到端更快。如果实测 factor 成本使单槽路线超出预算，下一决策应优先用 2 TB 的真实余量确定能保留多少个**相同精确因子**及其生命周期，或能否复用同一 q 的结构；这是执行资源安排，可以先于更换数学预条件器。不能预先宣称全 8 因子能常驻，也不能在没有一次真实分解成本时把单槽认定为最终最优。

### 5.4 从现在到首次原尺寸完整场的退出条件

| 推进节点 | 通过条件 | 随后的直接行动 |
|---|---|---|
| V26 保存流/native 消费者 | 已通过；保留原身份与误差 | 进入本轮完整 q0 数值 CSR |
| 完整 q0 CSR | 全部行列与复数值持久化、两输入/分量 native 对照通过、真实资源账 | 独立单 q symbolic/numeric/probe/RHS/释放 |
| 完整单 q 生命周期 | 原矩阵 true residual、原 INFOG、实际 fill/峰值/端到端时间 | 评估其他 q 与完整 reference inverse 的资源和生命周期 |
| 完整 8-q 与 target 接线 | 实际 q 覆盖、真实 target 算子/RHS/恢复接线正确，首次全场容量和时间准入 | 运行原尺寸 Nx272/Ny8/Nz14/p6 pilot 第一场完整求解 |
| 原尺寸 pilot 全场 | 全原 A6 true residual≤1e-6、释放后检查和正式物理输出，完整单场成本 | 根据实际误差与资源推进 h/p、y/z 与通道精度 |
| 最终工程解 | 任务规定场量/模式/功率精度，原尺寸真实几何，整机 2 TB 与单场 48 h 全账 | 才能授予最终目标通过 |

首次原尺寸求解之前，要求的是算子/数据正确和资源准入；**不能要求先有一次成功的原尺寸原 A6 结果才准许第一次求解**。原 A6 与正式 R/T/A 是该场算完后的验收门。[R11]、[R12]

未来第一次全 8-q 构建需要自然覆盖一般复 twist。当前 q0/q4 只覆盖一个 sector，q1/q5 等分支的复相位、投影和双向 leakage 应随全 q 工作逐项验收，不能把 q0 或 q0×8 的推导写成全 q PASS。这不阻塞本次 q0 CSR，也不要求再开独立小模型回圈。[R6] 1107–1184。

## 6. V27 连续执行合同与本轮交付

### 6.1 固定新窗口，保留旧费用

V26 的旧 T0=2026-10-11T07:10:58Z，数值截止 12:50:58Z，总截止 13:10:58Z。旧窗口和费用永久保留；required-checker 中 600 s 的旧 profile 标签不改写，实际 V26 执行的是 1,200 s 收口 reserve / 20,400 s 数值 cutoff。[R3]、[R4]

V27 从本包在 Codex 端第一项实际准备、实现或测试开始，一次冻结新的 T0；总窗口 **21,600 s**，预留 **1,200 s** 收口，数值 cutoff=T0+20,400 s，总 deadline=T0+21,600 s。修复、重试、文档、提交/推送/回读计入当前窗口；不刷新 T0，不清零历史 UNKNOWN。主控在同一执行分支集中提交/推送，执行者继续遵守其不 commit/push 的边界。

| 顺序 | 本轮应连续完成的工作 | 允许停止的真实条件 |
|---|---|---|
| A | 跨窗口只读导入 V26 已通过证据，完成必要薄适配与定向测试 | donor/payload/数学身份实际不一致 |
| B | saved-only contribution adapter，真实 q0-only 支撑，轻量 worker 资源采样与全量 CSR 预检 | 新鲜 host/tree/cgroup/task-swap/disk 门拒绝 |
| C | 准入后一次必要的全结构重建并持久保存，完整数值填值和 native 对照 | 实际数值、资源或固定窗口门失败 |
| D | 独立 CSR continuation / 单 q factor 入口与完整资源交接包 | 交接材料仍应完成；不借不存在资源伪造 factor |
| E | 仅当当前已授权环境和新对象账确实通过全部门时，继续一个 q0 factor 生命周期 | 现行完整结构在 16 GiB 下默认无准入；不能原样重试 |
| F | response_v27、compact、索引、summary/test_summary、模型/进度总账和发布核验 | 不以小 bug 或成功软件测试代替实质交付 |

实现与轻量测试应优先服务于尽早启动完整保存数据构造，目标是在前约一小时内进入主线；这只是预算安排，不是尚未实测阶段的耗时保证。不要先扩展监督平台、增加无关 wrapper 或重跑历史全部测试。

普通键名、路径、schema、receipt、启动参数错误在本窗口内定位、最小修复、定向重测后继续；只冻结新的 source/attempt，旧负结果保留。真实身份、NaN/Inf、native 误差或资源不足必须停止受影响计算。修复后的重试应有改变失败条件的证据；不能把同一内存拒绝无限重试。

### 6.2 验证规模与架构边界

V26 记录的最终 source focused suite 为 80 passed / 1 skipped，另有资源停止 fixture 1 passed；closeout focused rerun 22 passed，文档合同 29 passed。三组 native 保存后仍出现的 KeyError 保留为独立历史失败。全仓 pytest、MPI2/4、Ruff、CI 和 full-q PDE 本轮均未运行，不能写成通过。[R10]

V27 只为实际改动运行有意义的定向验证：跨窗口 donor 导入且不重署名；保存贡献与既有作用一致；q0-only 支撑完整；结构复用/数值重启不重复累加；真实 CSR 对 native 的全域检查；factor 入口保留 CSR 成果和现有资源门。能够用保存数组或轻量 fixture 验证的，不新建一套 FE/PDE 测试。数值核心变化才使对应旧证据失效，无关文档/source 变动不自动要求重跑所有昂贵资格。

继续使用既有 Task40 canonical worktree `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`，资格化 activation、complex128/int32、MPI1、单 heavy、独立 watchdog、动态 host reserve、16 GiB hard cap 与 task swap=0。不得自动 SSH、改变工作站、创建执行聊天/项目/worktree、改变 ordinary default 或合并 master。[R16]

### 6.3 Response V27 必须先回答的六个问题

1. **完整数值 CSR 是否真的生成？** 先给形状、全行覆盖、stored slots、numeric nonzero、数据字节与 native 对照；未完成时明确停在结构、填值还是验收。
2. **是否摆脱 FE 重建？** 给该阶段实际 FE/native 调用计数、必要 owner、新鲜采样与资源需求；不能仅以 `perform_native_validation=False` 宣称整个入口 FE-free。
3. **哪些工作现在能够恢复？** 给保存 pattern/CSR 的真实文件和身份；counts 见证、完整 columns、完整 values 三者分开。
4. **CSR 与 factor 分别要什么资源？** 实测与推导分列；当前失败门、需求/余量/缺口明确；不得把当前 80.885 GB 预算冒充 factor 实测。
5. **单 q 分解下一次怎样直接运行？** 给可复用入口、manifest、资源合同和目标环境待指定项；已通过 CSR 不受后续 factor 停止影响。
6. **48 h 最关键的新信息是什么？** 已测则给完整重建成本及其调用账；未测保留 UNKNOWN，并明确下一次分解是关键测量，不能再由迭代数或小面板推导终极能力。

重型 arrays、CSR、factor、完整日志留在 ignored artifacts，只提交轻量记录、manifest、可复现入口和文档。本轮结束前完成 GitHub 公式/表格渲染检查。当前 review 只改变审阅文档；没有授予最终 PDE、2 TB / 48 h 或 master merge 资格。

## 附录 A：本次远端内容 SHA-256 复核

以下七项从冻结结果 HEAD 读取，按 UTF-8 原内容独立计算，并核对 Git blob 与 run index；全部一致。文件路径相对 `docs/task40extra_0p7nm_engineering/`。

| 文件 | 内容 SHA-256 |
|---|---|
| outcomes/records/target_operator_probe_v26.json | b87a152efaec3ab6045b4628e2b499d82afdcebdd86175f98b8f7aa4bc3e3e89 |
| outcomes/records/time_resource_accounting_v26.json | 28649fcaad302655359c1065afd7f44e2c26e8634f3ece9962b8fa0b8f988e96 |
| outcomes/records/review_v26_incremental_workflow_ledger.json | 5094dc647c02c7b180d56d9d164a3688f7cc7871e863db51df3610c36040e9fd |
| response_v26.md | a7096039a92d91f62b956fc61aba5d1b1709bf18b0c0bf1dd4e6026807cf6aeb |
| outcomes/summary.md | b8ced522ba1054a5d8beaf358b8d73278def403afc9cff0f75720dbaa057c5ea |
| outcomes/test_summary.md | d685b569981045ada44897dbd3f0c2cd8801a4dfadea292726bfc3d8ca5f13c7 |
| README.md | acf4ca60598f5d039060a79a722a4248ae09b13bd807d7cb9fc37ced994767fd |

复用入口中的关键原始证据由 [R13] 逐路径绑定：native recovery manifest SHA-256=`6a558896fc0e83826081d9b418a89d4cd76d45207bf7dd4cd086c68df7c12265`，checker=`e6b88c9eeb5e2314cdf427f4db76f67ca73aac162307d005d2ac22f455ce4ce2`；完整 counts/offset NPZ=`b8241f8bf6e6d40c4238a0a01da90cc6e58e06a92b179d524a243fbe65deab69`。这些是 donor 资格，不是新 V27 source 的生成结果。

## 附录 B：可直接交给 Codex 的执行文本

以下是交给既有 Task40 主控/执行者的完整文本；本报告没有代发消息。

```text
继续 Task40extra。先拉取同一分支 task40extra_0p7nm_engineering 的最新 review_report_v27.md，完整阅读后按它连续执行。本轮审阅结果基线是 399787abc991e0e30975bc694bd18a9a30c5470e，V26 最终科学源码是 f9093c87f81d52b75fbc156e562b3745df45ccf4。

目标保持原尺寸 50×25×140 nm、0.7 nm、真实非分离 Si/air、complex128、整机十进制 2 TB、task swap=0、单场全部必要费用≤48 h。Nx272/Ny8/Nz14/p6 是原尺寸工程 pilot，最终精度未自动通过。

本轮主交付是：复用已通过的 V26 完整消费者 → 脱离 FE 重建的完整 q0 数值 CSR → 独立 continuation 和可执行单 q 分解交接。普通 bug 在同一窗口修复后继续；不要以修键名、测试通过、又一个小面板或同一资源 gate 再拒绝作为整轮终点。

一、先复用 V26 已通过的资格，不重跑 producer/native。
完整 q0 两组非零输入误差约1.9e-14，q0/q4 双向 scaled leakage约1e-16，可以继续 CSR。显式只读导入原 producer、三组 native 数据、V26 recovery manifest及其checker；donor source/window与本次V27 source/window分列。先按原身份验证donor，再核验同一数学算子和payload。不要刷新旧window、把旧结果重新署名或要求new current_identity与旧window全等。旧native计数/用时缺失继续UNKNOWN/NOT_RECORDED，不为补历史统计重跑FE。

二、实现真正的saved-only CSR路径。
当前perform_native_validation=False仍会重建并保留mesh/p6/MPC、surface assembler、volume form/JIT、凝聚及fresh双q maps，不能继续原样调用。建立轻量保存贡献适配器，复用现有V17的layout/contribution两个iterator及精确投影累加核心。volume用保存的cell expansion和Schur class；C、-D、H用原surface流、lookup和H。保持-D普通转置/负号，不加共轭，不重复MPC；非零unmapped/interior值仍拒绝。只加载并索引实际q0支撑，不能伪造q4=q0。不要新造PC、重积分或复制一套solver。

三、先按已知完整规模做实时准入，再重建结构和填值。
q0形状777644×777644，结构位置577061168。保留全部结构位置时纯CSR为11544333940 B；V26含工作区的额外量为11570765788 B。当时host/tree可新增4833513472 B，缺6737252316 B；cgroup缺6574534620 B，两个缺口不相加。轻量worker装好必要保存数据后，先采样owner、RSS、cgroup anon/file/dirty和host余量做全量预检，真正分配前再过实时门。mmap和文件脏页照样计内存；不得把完整payload计为零、抬高16GiB cap或用swap强行通过。预检通过才投入完整结构主工作。

四、把这次结构变成能恢复的成果，完成全部数值。
V26只有完整counts/offset见证；旧support SQLite已被TemporaryDirectory清理，未保存完整columns/data。允许一次必要的route/column重建，这次持久保存既有格式的support/routes、完整indptr/indices和manifest。只q0的route hash可与旧双map表示不同，分别绑定；完整q0行计数和作用必须一致。随后完整填值，区分STRUCTURE_COMPLETE_VALUES_PENDING、NUMERIC_FILL_INCOMPLETE、COMPLETE_CSR。无可靠游标时从清零的数值阶段重启，禁止重复累加半成品。不要开发通用存储平台。
完整CSR完成后，报告stored slots、numeric nonzero、exact-zero slots、全行全列、shape/dtype、排序唯一性、字节及hash。从文件回读，用已有两组非零输入与保存native结果比较，并复用volume/C/-D/Hhat各自1e-11门限。不能只比较新CSR与同一适配器。精确零压缩不是前置门，不能阈值丢弃小项。

五、CSR与factor分开成功；准备直接可运行的分解入口。
现有run_task40_v26_selected_q0_factor_lifecycle已经实现，复用它，不再伪造q_count=1或新增PC。提供直接读完成CSR manifest的continuation，不重做producer、native或structure。当前完整结构下源CSR加转换副本已23088667880 B；现行含PETSc、4B symbolic guard和六向量的保守准入账约80884991404 B，还需其他owner/系统余量。它不是factor实测，不能承诺当前16GiB完成分解，也不说明2TB失败。
若当前已授权环境和新真实对象账确实满足所有门，在同窗口连续完成一个q0 symbolic→numeric→fresh probe→另一非零RHS solve→evict，true residual≤1e-10，每阶段立即保存INFOG、时间、峰值和清理证据。否则保留已完成成果，交精确manifest、实际需求/缺口、ABI/资源合同及独立build/factor命令入口；若CSR尚未完成，标CSR_PENDING，仅附实际已有的counts/offsets或完整pattern，不伪造文件，不为补交接执行被资源门拒绝的构建。
Task40 AGENTS仍限制本机canonical worktree，禁止SSH/切工作站或其他任务主机；本轮完成交接准备，不自动迁移、不借其他任务权限、不改cap。目标环境尚未指定的字段明确留待主控安排。这不阻止本机CSR和交接工作。

六、48h评估按真实重建次数，不只看迭代步数。
ONE_Q_REFACTOR_V19在完整8q遍历中通常每次PC都重新分解每个q。记录F_q及完整rebuild父成本；业务RHS与fresh probe分账，另计PC中的q投影、传递、局部凝聚/恢复、端口及augmentation外围费用，不能把一次q0成本乘8就当整场总成本。取得真实factor成本后，再用2TB共驻余量决定能保留多少相同精确因子，随后推进其余q和原尺寸pilot。q0×8的92.35GB CSR仅为情景，其他q未实测；一般复twist随首次全q构建自然验收，不额外开小面板回圈。

七、执行窗口与交付。
仅使用既有 /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering；资格化activation、complex128/int32、MPI1、单heavy、独立watchdog、16GiB hard cap、动态host reserve、task swap=0。沿用主控集中提交/推送、执行者不commit/push，不创建聊天/项目/worktree，不改master或ordinary default。
从本包第一项实际准备/实现/测试起冻结V27新T0，总窗口21600s，收口预留1200s；数值cutoff=T0+20400s，总deadline=T0+21600s。旧V26窗口、失败和所有unknown费用保留，修复不刷新T0。尽早完成必要薄适配并进入完整数据构造；只跑相关定向测试。普通bug最小修复后继续，真实身份/数值/资源门失败保留原始事实，不重复同一失败条件。
提交response_v27、operator/resource compact、run index、summary/test_summary和模型/进度总账。先回答：完整数值CSR完成多少、是否真正没有FE重建、保存了什么可恢复成果、新峰值/耗时和精确资源缺口、下一次单q分解怎样直接执行。后续factor拒绝不能抹去CSR成功。不要声称未运行的全q、target PDE、精度、2TB/48h或master merge已通过。
```

## 附录 C：冻结来源

所有链接均固定到本次结果 HEAD 或已明确引用的旧 review，不使用移动分支充当不可变证据。

- [R1] V26 执行回应。
- [R2] V26 完整 q 消费者、行结构与资源停点记录。
- [R3] V26 时间/资源账。
- [R4] V26 增量工作流与窗口账。
- [R5] selected q 保存数据消费、FE owner、CSR 构建与回读源码。
- [R6] 周期分支、V17 行结构/数值投影与完整 PC 调用源码。
- [R7] 单 q exact MUMPS 生命周期与 ONE_Q_REFACTOR_V19 源码。
- [R8] V26 stage 路由、恢复和单 q factor 入口。
- [R9] service 监督、native recovery 与独立 checker。
- [R10] V26 测试摘要。
- [R11] 已提交 Review V26：继承的原尺寸 volume、保存 producer 与目标推进合同。
- [R12] 原始任务书：物理模型、误差与最终目标边界。
- [R13] V26 run index：tracked 内容 hash 与原始 artifact 路径/hash。
- [R14] 原单元约束 Schur contribution 接口。
- [R15] 原 p6 体积/端口 contribution 接口。
- [R16] 当前 Task40 本机执行边界。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/response_v26.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v26.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v26.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/outcomes/records/review_v26_incremental_workflow_ledger.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/solvers/task40_v25_selected_q0.py
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/solvers/task40_v10_p6_yorbit.py
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/solvers/task40_v10_p6_mumps.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/runners/task40_v20_stage_runner.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/scripts/task40_v20_service_workflow.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/83c4fed6e29ea19f0a70a92a403b867851f3ef35/docs/task40extra_0p7nm_engineering/review_report_v26.md
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/task.md
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/solvers/static_local_schur_action.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/src/solvers/p6_cell_condensed_action.py
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/399787abc991e0e30975bc694bd18a9a30c5470e/docs/task40extra_0p7nm_engineering/AGENTS.md
