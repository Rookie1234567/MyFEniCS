# Task40extra Review V32：严格接续 q4 pending，打通局部原生验证与连续全 q 路线

## 0. 仓库快照、结论与本轮要消除的 blocker

| 项目 | 本次审阅身份 / 决定 |
|---|---|
| 审阅日期 | 2026-10-14，Asia/Singapore；下文原始运行时间均标 UTC |
| 仓库 / 执行分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| V31 结果基线 | `0a082891f450bef5903df5c5cb40236ac35d3081`，已实际回读远端分支 |
| 最后结果提交 | Task40 V31: retain readonly NO_PARTIAL_FOOTER recheck limitation，2026-10-13T21:28:48Z |
| 数值运行 source | `54cf6d367b07355c0ab08c8c10655ecac73cfc6a` |
| 收口 checker 修复 source | `c9c7f4af19917cbd2c0e4ecd5c0b167cab6752f5`；不冒充数值运行源码 |
| 已回应的上一 review | Review V31，`d7ffbfea952bc160742b18739369f2e3f656ee8e` |
| 正式 attempt | `20261013T114619.891762Z` |
| 结果验收 | 接受 q4 完整数值数组及其可接续里程碑；不授予 q4 native / factor、全参考或 target PASS |
| 新运行权限 | 本文只提出新固定窗；`PENDING_USER_APPROVAL`，不刷新 V31 窗口 |
| 本次仓库写入 | 仅新增本 review；不改数值源码、历史证据或 master |

**本轮要消除的是“完整数值 CSR 已经存在，却仍可能因跨 source 路径未接通、重复端口准备和缺少内部阶段证据而无法进入独立 native”的 blocker。** 这是求解器准备、内存/时间工程及项目治理问题，不是物理模型或精度门限问题。第一项新科学交付应是 q4 独立 native 通过，而不是又一份 q4 fill 或更多接口 PASS。

最终目标保持：50×25×140 nm、真空波长 0.7 nm、真实非可分三维、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN，整机十进制 2 TB、有系统余量、任务零 swap，必要完整冷流程不超过 172,800 s。当前参考分块的工程试验不等于任意三维目标已解出；最终网格/mode 精度另行资格化。

本次联合核对了正式回应、controller audit、operator/reference/time-resource/pilot 四份 compact、只读补检、handoff、run index 的 V31 项、当前 summary、目录规则、任务书、上一 review 和相关源码。科学 source 到结果 HEAD 的三笔提交只改收口 service/checker 及测试、文档与证据，没有改 q4 数值构建/局部 owner 的科学实现。[R1]–[R9]、[D1]

审阅边界：本 Chat 没有登录工作站、重算 PDE/native/factor、运行项目 pytest，亦没有重新读取工作站的 11.62 GB 数组。数组全文件 SHA 一致是已回读的主控审计事实，不是本 Chat 又做了一次数组审计。正文的计数/字节恒等式与 UTC 区间换算另作算术核对。旧 P0 的 PENDING/0 个成果文字是历史快照，不覆盖本轮最新结果。[R1]、[R2]、[R7]、[R8]

## 1. V31 成果与资格边界

### 1.1 q4 确实完成了什么

| 指标 | 实际值 / 状态 | 含义 |
|---|---|---|
| q4 数值矩阵 | 777,424 × 777,424 | q4 自己的矩阵，不是复制 q0 |
| 结构位置 | 581,086,528 | 包括保留的精确零槽 |
| 数值非零 / 精确零槽 | 566,185,131 / 14,901,397 | 两者之和等于结构位置；未压缩删零 |
| 纯 CSR 载荷 | 11,624,840,260 B | complex128 值、int32 列号与行指针 |
| 三份 NPY 总大小 | 11,624,840,644 B | 比纯载荷多 384 B；两种口径不混用 |
| pending | NUMERIC_COMPLETE_NATIVE_PENDING | 完整数值数组可恢复；独立 native 尚缺 |
| 三数组完整读回 | 主控逐文件 SHA256 全匹配 | 文件完整性，不是算子正确性证明 |
| q4 factor / 独立 native | 未运行 / 未完成 | 不允许据 pending 进入 numeric factor |
| 历史 q0 | CSR/native、V29 分解生命周期资格继续有效 | 旧 factor 已销毁；不是当前 live owner |
| 其余六 q / 八因子 / 六组参考检查 / target | 未完成或 NOT_RUN | 未记录的运行计数保留 null，不虚填 0 |

字节恒等式为 `20 × 581086528 + 4 × (777424 + 1) = 11624840260`。原生 factor 的未记录计数与源码路径未进入 factor 阶段是两种证据，继续分别表述。[R2]–[R5]

q4 的实际形状、槽数和载荷与 q0 不同。这次已新增一个真实数值构建成果；“无新 native 合格 q”不应写成“无任何新数值成果”。不过，hash 一致不能代替四次完整 CSR/native 对照，所以 factor、reference、原尺寸场和最终 2 TB/48 h 仍不通过。[R3]–[R6]

### 1.2 时间、内存与截止

| 区间 / 资源 | 已记录数值 | 计量边界 |
|---|---:|---|
| q4 保存构建父段 | 17,281.822695894 s，约 4.80 h | UTC 阶段 start/end；包含 pattern、fill 及其他保存工作 |
| pattern 子段 | 6,066.371507694945 s | 包含于上述父段 |
| numeric fill 子段 | 7,262.07835266809 s | 同样包含于上述父段 |
| fill 内贡献生成 / 局部投影 / 全局累加 | 2,631.449041903019 / 2,111.333873125026 / 141.27612544083968 s | 已记录子段，不与 numeric 父段相加 |
| watchdog 运行父段 | 33,786.45508461888 s，约 9.39 h | 同次运行监督区间 |
| run_case 父段 / service 相邻父段合计 | 33,786.969049097 / 33,788.25402626567 s | 相互包围，不再相加 |
| 数值结束保守累计费用 | 42,032.2399471737 s | 包含准备、失败、等待与实际清场；不是最终全部收口成本 |
| 主控读回 | 26.34986114501953 s | 单列收口工作；与数值父钟分开 |
| 同时进程树 RSS 峰值 | 16,563,810,304 B | 不与 cgroup 峰相加 |
| watchdog 专用 cgroup 峰值 | 24,329,441,280 B | 包含任务 cgroup 记账；不是单纯 factor 库存 |
| systemd MemoryPeak | 24,325,746,688 B | 单列采样口径，不强行改成一致 |
| task tree / cgroup swap | 0 / 0 B | 任务范围通过；PSS 未采样为 null |

全局累加只有约 141.28 s，不能把 q4 保存总父段，更不能把随后 owner 阶段，笼统归因于 CSR 累加。未覆盖的父段内部时间保持未归因，不以减法猜成 JIT、I/O 或某个 owner 热点。全机 swap 既有状态与 task swap 分开；本轮 host-global 页计数增量为 0，仍不等于整机从未使用 swap。[R2]、[R3]、[R4]

V31 固定窗口：T0 为 2026-10-13T09:28:54.340648489Z；数值截止 21:08:54.340648489Z；总截止 21:28:54.340648489Z。window SHA 为 `57133ebfe54c109ca77af4e529df94708c29c2b4c79d301b862b01ee70cf8f56`，未刷新。数值截止 SIGTERM，30 s 宽限后 SIGKILL，后代清空；分类保留 PERFORMANCE_CONTROLLED_STOP。没有内存门、OOM、因子失败或目标迭代不收敛证据。[R2]、[R4]

## 2. 本次源码审阅的确定发现

### 2.1 跨窗口 helper 已有，但正式入口仍缺“从哪里导入”

`_load_v30_numeric_pending` 已能严格读回三数组并验证跨窗 consumer authorization；这是 V31 的有效增量，不重写其数值内核。但正式 worker 调用 `prepare_saved_selected_q_numeric_pending` 时，搜索位置固定为当前 `factor_config.output_directory/selected_q/q4_twist0`。该函数只在这个目录找到 pending 才读回；找不到就进入 pattern/fill。[C1]、[C2]

与此同时，`require_v31_input_identity` 和批准包生成器把 factor 输出目录锁定为当前 source 的新目录。授权字典本身不提供旧 pending 路径。因此“给新窗口填一个 import authorization”还不能保证实际消费旧 source 的成果。手工把 factor 输出目录改回旧目录又违反当前输入合同，并混淆旧证据与新写入。[C3]

**V32 必须完成一条闭合的 continuation：批准包 → staged DAT/执行绑定 → worker → 精确旧 pending 路径 → read-only CSR → 新 native 输出。** 新增字段/接口是本轮实施任务，不能声称现有 V31 CLI 已支持。

### 2.2 owner 阶段名还不足以定位真正瓶颈

公开到仓库的原始 phase 摘录只有 q4 start、q4 complete、twist0 owner-prebuild start。q4 完成于 2026-10-13T16:34:30.097190265Z；owner wrapper 开始于 16:34:30.098068598Z；SIGTERM 为 21:08:54.506887258Z。两者相减为 **16,464.40881866 s，约 4.5734 h，DERIVED UTC 未完成阶段占用区间**，不是已经量完的 owner 构建耗时。[R2]

尤其需要注意：`prepare_twist0_owner_with_phase` 包住的 `prepare_twist0_owner_before_global` 不仅创建局部 owner，还包含 H/map/lookup 核对、旧 q0 CSR 读取和后续 q4 native 子阶段。不能把 wrapper 的整个未完成区间直接归给局部构造函数。[C1]

本次证据不足以判定它具体停在 mesh/MPC、surface JIT、端口积分、volume JIT、凝聚、映射还是后续读取。下一轮先只读核对主控已保存的完整 `controller_readback.json`、worker events/log、watchdog 日志与可用 compiler 记录；从原始行及明确调用边界提取证据。若没有，就明确记录“历史无法进一步拆分”，不要为了追补旧计时重做旧矩阵。

### 2.3 静态可确认：局部 owner 仍走完整端口重建前缀

`build_task40_v10_p6_local_sector_owner` 先做 local FE/MPC，再调用 `build_same_mesh_physical_action`。后者先创建上下两侧、两个分量的 surface assemblers，再构造完整所选 mode 的 DtN carrier，然后才创建 split-volume action。局部 owner 最后从 carrier 创建 cached port action、凝聚恢复对象和坐标映射。此入口没有接收已经保存的 twist0 原始 B/D 流。[C4]、[C5]

这是**可确认的重复准备风险和下一步优化位置**，不是已经由日志证明的性能热点。不能从低 RSS 或 compiler 存活推导“全部 4.57 h 都是 JIT”。也不能只删除端口工作而丢失恢复与完整参考所需接口。

### 2.4 已修复的内容不要再当新任务重复开发

V31 已将 `sector_builder_inputs` 放到非 q4 callback 使用之前；all-q callback 也已有 V31 reference-only 分支，不再强迫尚未构建的 target 提供 actual-match=True。pending 的三数组读回、consumer 身份核验和同 owner 交接已有基础实现。[C1]–[C4]

下一轮只补真正未闭合的正式接线、必要原生 owner 与监督验证。旧 helper fixture 的通过不能替代新的端到端 continuation 测试；也不因这些增量尚未实测就推倒已有 ALL_Q、六 case 或分阶段资源门。

## 3. 必须冻结的 q4 continuation 身份

### 3.1 旧数据只读，新证据另存

精确旧根目录：

```text
/home/fenics/Projects/laptop_share/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_54cf6d367b07355c0ab08c8c10655ecac73cfc6a/factor_bank/selected_q/q4_twist0
```

| 文件 / 身份 | SHA256 / 值 |
|---|---|
| task40_v30_q4_twist0_numeric_pending.json | `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad` |
| task40_v30_q4_twist0_00_data.npy | `e0e209b7804956a8c998eac05422f6f6ff255ed857182e066eedfd509b005ad2` |
| task40_v30_q4_twist0_00_indices.npy | `3af86cbe15de1615304659e112deccb0d00c86c7cfe5d588cde846d84c3a7c97` |
| task40_v30_q4_twist0_00_indptr.npy | `0049c1ab9662e30b7cfe460f622557571172f8b5196174e64d4b4529ba2f334b` |
| 旧 contribution source / window | `9d0f4dbfc730dd620b709d048e33e9da6c77520c` / `a8ee7ab9970ece892d85f9313180438e88561f0bfc63b68acdb11f536400def7` |
| 数值构建 source / window | `54cf6d367b07355c0ab08c8c10655ecac73cfc6a` / `57133ebfe54c109ca77af4e529df94708c29c2b4c79d301b862b01ee70cf8f56` |
| scientific_input_sha256 | `f6726d005713b586f1bccfbf6904dd64f3f1f31dd3b069607b55e9b430d294c7` |
| q_map_sha256 | `318853f330128711b413b6d7eacd6b917a2e72ab95ce206b7bd31944ec3b4a69` |
| original_h_sha256 | `50271e2f584cd5e1da0abcb0c64a3e936fea57dd76df2b60c8edaf87e8d813d8` |
| profile_identity_sha256 | `5bf9bf0b68ca9d885373642333ef77b778b8f60f288a77cba0b6c3d434752e56` |
| ordered_mode_sha256 | `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` |

以上字段来源为主控/operator compact，正式导入必须回读实际 pending 原文、sidecar 和数组验证，不用本表重新拼一个“旧收据”。`ordered_mode_sha256` 不与其他编码口径的 manifest/key hash 混用；完整 physical_model_sha256、ABI、材料和 mode 身份还须从原 run_manifest/冻结输入逐项继承。[R2]、[R3]

### 3.2 正式导入合同

在新 source 输出根之外，显式登记一个只读 import root 和精确 pending path/hash；同时绑定新 consumer source/window。q4 策略必须为 **REQUIRE_EXISTING_NUMERIC_PENDING，禁止 fallback producer/routes/pattern/fill**。任一必需旧文件不存在、hash 不符或算子身份不一致，就报明确 import BLOCKED，不能悄悄在新目录重做矩阵。

执行顺序为：小收据/审批/路径核对 → 实时资源准入 → 三数组长度、hash、int32 结构与 canonical/finite 检查 → read-only mmap → 新 consumer receipt → 必要原生 owner。大文件扫描应在获准运行窗及监督下进行，真实记录费用；P0 可以检查小型索引和路径绑定，但不能把完整数组扫描作为“免费前置”。

继续复用 `_load_v30_numeric_pending` 的严格检查；增加明确的源路径参数及消费输出根，不用修改旧 pending 来迁就函数。目前 `_persist_v31_pending_consumer_receipt` 把新 receipt 写在旧 pending 旁边，V32 应允许新 receipt/native/COMPLETE manifest 写到新执行根，并以批准的原始路径/hash 引用只读数组。finalizer/provider 的路径校验也要贯通，只允许显式 import 根，不能全局放开任意路径。[C2]、[C3]

保持四层来源：旧 contribution → V31 numeric producer → V32 native qualification → 本次 live factor。旧 matrix_source/execution/window 和 hash 不改成当前 source。新检查器的源码身份单列。不要复制 11.62 GB 数组来伪装新生产，不对旧 hardlink/backing 进行清零、删零或写入。

成功导入的运行收据至少包含：`reopened_existing_pending=true`、旧 pending/hash、三数组/hash、原/新 source/window、数值构建调用数为真实 0、只读标志、实际导入时间与峰值，以及 `native_status=PENDING`。其中 0 要由本次计数/禁止调用断言获得，不能由日志缺失推断。

## 4. 局部原生 owner：明确主方案与独立性

### 4.1 主方案是复用已资格原始端口数据，重建必要 FE 恢复对象

这里的 owner 是持有局部 FE、约束、单元内部消元/恢复、原始端口作用和映射的运行对象。它不是 q4 矩阵文件，也不能从一个已销毁的 Python/PETSc 对象恢复 live 状态。

**优先采用既有 V25/V26 保存流原生验证组件来构建可复用的局部 owner，而不是无条件重新运行完整 surface assembler/carrier 前缀。** 保留 fresh local mesh/FE/MPC、原始 split-volume FE action、必要 local LU/recovery；读取已经绑定且资格有效的原始 B/D/H 流，核对 fresh lookup、q0/q4 maps、H、端口支持与完整 mode inventory，接入 native action/recovery 所需接口。[C4]–[C6]

这项优化改变的是“原始端口数据怎样交给恢复和作用对象”，不改变 Maxwell 方程、材料、模式或 CSR 数值。收益是避免重复准备同一端口数据；代价是实现 saved-provider 与现有 local bundle/carrier 的受控适配、保持清理和共享所有权。实际时间/内存收益尚未实测，不能保证所有 JIT 或局部消元都可省去。

独立 native 的含义必须清楚：以原始未凝聚 FE 体算子、真实内部恢复和原始 B/D/H、primal/dual 映射计算作用，再与 q4 CSR 比较。不能用 q4 CSR 自身、其子矩阵或同一份保存 Schur replay 作为“独立 native oracle”。已资格原始端口数据的复用，应写为“旧端口资格继承 + fresh FE/recovery 验证”，而不是“本轮重新独立积分全部端口”。若旧端口资格/身份不足，只补确实缺失的验证并说明，不默认重跑 q0 producer/native。[C6]

q4 direct-H 仍须消费既有 twist0 内部 B/D 非零数均为 0 的支持证据，不删除该前提。新 twists 不继承这个结论；任何非零内部耦合都保留准确的一般 Hhat/凝聚修正，不能为了进入快速路径将其置零。[R3]、[C1]、[C2]

### 4.2 必须在真实调用内部落盘阶段，而不只包一层函数

在以下实际调用之前保存 STARTED，成功完成之后保存 COMPLETE，异常/截止保留最后可证状态：

| 子阶段 | 需要的定位证据 |
|---|---|
| frozen context / H / donor metadata | mode/q/twist、H 和来源身份；未创建的对象不记 READY |
| local mesh / FE / MPC | 实际 cells/rows、约束数量、map 身份 |
| 原始 B/D provider / carrier | 读取、核验、积分是否重跑；每个实际 mode/side 的工作量和保存结果 |
| volume form / JIT | form/cache key、hit/miss、compiler PID/起止/退出；调用未结束不记完成 |
| local condensation / recovery | 已完成 class/cell、LU/Schur/recovery 唯一 backing 和缓存命中；共享按真实身份 |
| entity / trace / q maps | 成功映射数量、fresh-vs-saved 身份门 |
| q0 CSR 读取与 q4 native | 读取起止；每个 full/masked case 各自结果与向量收据 |

使用 monotonic/perf_counter 父子区间，并同时保存 UTC、boottime/boot_id、attempt、q/twist、owner_id。V31 helper 的 `time.time_ns()` 历史计时保留为 UTC，不倒改成 monotonic。长阶段按 mode/cell/class/tile 的实际进度低频 heartbeat；必要时启用定点栈快照和 compiler/IO 状态采样，禁止以“无输出”直接重复启动。[C1]、[C4]、[C5]

先查旧日志，再在本轮必要构建中加入这些观测；不单独重跑一个旧完整前缀只为了做 profiler。检测到实现死循环、缓存键错误或非必要重复遍历时，在不改算子的前提下定向修复。同窗重试继续计费；不同 source 不能接着声称旧 live 因子仍在。

### 4.3 q4 首个新科学 Gate

复用已接受且身份一致的旧 q4 第一完整输入见证及双向 leakage，只补缺失的第二个不同非零完整输入及 trace-only/port-only 原生分量；所有输入与输出必须真正覆盖该 q 的完整行域。四次完整 CSR 作用、分量重组、H/支持与同 sector 双向泄漏继续执行原相对误差门 **≤1e−11**，原来更严格的映射/H 门也不放宽。

每个 case 完成即原子保存输入、CSR 输出、native 输出和结果/hash，以便 native 后半段失败时仅补缺项，不重新做已经合格的 case。只有全部原门通过后才追加独立 native PASS 和 COMPLETE_CSR manifest。pending 原文不覆盖，q0 旧 producer/native 不重跑。必要的 q0 CSR 读回是消费，不是重新资格化。

同一可用 local owner 留给后续 reference。其 action、原始 volume/port、recovery、entities、maps 和 transform bank 需要相容接口及唯一销毁责任；fixture 要验证后续 reference 实际借用了这些对象，没有为接口适配悄悄重建同一个 owner。若必须跨进程重建，明确计入真实冷/暖账，不称 live 复用。

## 5. 后续连续执行、资源与数学 Gate

### 5.1 q4 通过后不逐阶段等待审阅

| 阶段 | 连续动作 | 交付 / 停止边界 |
|---|---|---|
| P0，运行窗前 | 补正式 import 路径、最小原生 owner 适配、内部事件、监督 checker；真实入口 fixture；冻结源码 | 不启动目标 FE/JIT、大数组扫描、pattern/fill/native/factor；不重复上一轮已闭合 P0 |
| P1，导入 | 精确消费 V31 q4 pending | 新 consumer receipt；routes/pattern/fill 均不调用 |
| P2，首要科学成果 | 必要 twist0 owner + 缺失 q4 native | 四作用与原门通过，q4 COMPLETE/native |
| P3，三个真实 sector | (q1,q5) → (q2,q6) → (q3,q7) | 每个 sector 共同准备一次；每 q 自己 CSR/native，逐项保存 |
| P4，全 q 分解 | 八 q 齐全；逐 q symbolic 后全对象统一准入，再 numeric/两 RHS并保留 | 八个合格 numeric 因子同时 live，不把 symbolic 对象当因子 PASS |
| P5，全参考 | 同一 bank/owner 做六类全空间原生检查 | strict 与 V15 PC 分开；记录所有作用和校正费用 |
| P6，条件 target | 目标完整共驻账、实际布局和时间准入后进入原尺寸 pilot | 原 A6、场、R/T/A/体吸收及资源证据 |
| P7，固定收口 | 受监督的只读检查、未完成状态、释放与完整清场 | 旧失败不改，新独立 q 成果不因缺总 footer 被抹去 |

新 sector 的真实 phase/MPC、所选 modes、B/D/H、支持与来源必须独立绑定。可共享本 sector 的生产数据给两个 q，不能共用 q0 的矩阵数值或以相同行数推断相同算子。必要贡献/owner 生产要有可复用记录；若采用 live source，明确哪些数据可落盘再用、哪些原生对象只能在本进程复用。

原 full reference builder 目前只允许 prebuilt twist0 owner，不能仅传入 {0,1,2,3} 就声称全部可预构建。先保证 q4 真正资格化，其他 sector 沿已审查的真实顺序生产；若完整 global carrier 前置再次成为阻塞，可定向扩展已存在的 prebuilt owner 接口及 allowlist，保持一个共享 transform bank、逐 sector 身份及唯一清理责任。不得把这一扩展夸称现成能力，亦不以全面重构作为 q4 native 的前置。[C4]

### 5.2 ALL_Q_RESIDENT 与参考资格

保持 exact MUMPS、complex128/int32、MPI1/数学线程1、原排序/主元及控制设置，禁止自动 OOC、BLR、近似因子或线程扫描。对每 q 保存实际 CSR/PETSc 身份、symbolic INFOG16/17 和资源准入，然后 numeric；fresh 与同因子第二个不同非零 RHS 都以该 q 原完整 CSR 算 true residual **≤1e−10**。不得用更容易的 RHS、合成 A×x 测试替换已冻结 RHS 合同。

新 live bank 的 q0 需要重新 numeric 一次并取得本次 factor 两 RHS 收据，因为 V29 factor 已销毁。不要先逐 q factor→evict，之后为 bank 再全部分解。各 q 通过后保留，证明最终八个 numeric PASS 同时存活；失败的后代或销毁失败的 owner 不记已释放。

完整参考仍有六类检查：full independent FE、interior-only、all-mode port、physical incident、mixed FE+port、mixed interior+port。strict full/augmented/local-combined/q 门≤1e−10、alpha≤1e−11；既有 V15 业务 PC 的原生 eliminated/augmented/noncancelling/q 门≤1e−8、alpha≤1e−9、decomposition closure≤1e−10，并保留 frozen-scale/结构门。两种状态从同一个 selected state 聚合，不能混 initial 与 corrected。factor 两 RHS 的 1e−10 前置不借 V15 放宽。通过已注册 V15 准入但 strict 未过时，可以依原合同进入获准 pilot，但报告真实 strict 失败指标。[R9]

一次受限非递归修正、各 q MatSolve、fold/transform/recovery 和 native 检查均计费。保留 T_bank 总父段、排他的各 q 构建活动时间、第二 RHS、shared/unattributed，以及按 reference startup/correction/target PC 分开的业务计数。不同 q 开始至 READY 的跨度相互重叠，不能相加；S_q 原生 solve 是完整 PC 父钟的子项。

### 5.3 内存是全过程对象账，不只是八份 factor

继续采用 task cap **1,649,267,441,664 B**、host reserve **68,719,476,736 B**、task swap cap 0；工作站根不变。实时 host MemAvailable、有限 ancestor cgroup、任务 cgroup 与整机十进制 2 TB 边界分别满足，不把更大宿主物理内存当目标预算。

增长前列清：八 q CSR 的唯一 backing/驻留页、PETSc 复制和转换、symbolic/numeric 工作集及已留因子、reference/target 的 mesh/FE/MPC、local LU/Schur/recovery、H/modes/映射/transform bank/carrier/cache、JIT/compiler、Krylov V/Z及工作向量、完整 PC/A6/校正、恢复 E/H/旋度/alpha、输出/读回、checker/watchdog及系统余量。

已在当前 RSS/cgroup 的同一 backing 不再作为新增量重复计入；不同同时存活对象必须累计。只有确实不同时活跃的工作集才能取 max。mmap/file cache 不能视为免费；磁盘空间单独准入。未知项保持 UNKNOWN，不以 planned rows 覆盖全部 target 对象。

沿用三个门：REFERENCE_ONLY 依据完整参考账；TARGET_BUILD 依据 live bank 仍在时的目标新增账；TARGET_READY 在目标建成后核验 actual rows/modes/maps/primal-dual 与真实共驻量。未知 target 预算只阻止 target，不能强迫先建 target 来通过 reference；也不能反向删掉资源门。[C1]

全 bank 不准入时保留逐 q symbolic 与具体独立约束缺口，安全释放，不能以 OOM 试探。单 q 后备分解只限本轮实施前已冻结且实际准入的成本采样；不能临时改成 ONE_Q 循环并冒充 ALL_Q_PASS，也不重复已有 q0 容量样本。

### 5.4 原尺寸 pilot 与最终精度保持分离

target 冻结为当前 p6、272×8×14、30,464 cells 的工程 profile；32,060 ordered modes 必须由实际完整 inventory 核对。reference 允许结构利用，target 仍必须是原非可分三维模型，不能用填平、二维或局部周期结果替代。

原 A6 与释放后真残差≤1e−6、能量/体吸收绝对闭合≤1e−5，保留原每8步 A6、每32步 checkpoint、终态检查与已冻结求解设置；有效合同更严格时执行更严格者。合格场才授予 official 输出，停止场仅作有明确身份的诊断。原始复 E/H、衍射级、R/T/A/A_volume 及 provenance 不省略。[R10]

即使工程 pilot 通过，也不自动通过最终 h/p 或 mode 截断精度。本轮不新开网格/mode/PC 参数扫描。长期任意三维路线仍需分布式、matrix-free 和可扩展 Full3D iterative；当前准确参考分块只是固定工程路线资格，不应升级成通用生产能力。

## 6. 新固定窗口与受监督收口

### 6.1 本次建议一个新的 24 h 固定执行窗，尚未授权

| 项目 | V32 提案 |
|---|---|
| 总预算 | **86,400 s（24 h）** |
| 数值截止 | **T0 + 85,200 s** |
| 收口保留 | **1,200 s**，包括 checker、flush、销毁与后代清理 |
| T0 / deadline / 新 window hash | PENDING；实际用户批准后、第一项必要运行准备前一次锚定 |
| 作用范围 | 严格导入旧 q4 → owner/native → 三个新 sector → 全驻留 → 参考 → 条件原尺寸 pilot |
| cap / host / ABI / 数值门 | 全部不变；不是提高内存，也不是放宽最终 48 h |
| 同窗失败与重试 | 修复、等待、重新启动及必须重建的对象全部继续收费；不刷新 T0 |

选择 24 h 是为了减少必要 owner/后续因子在过短交接窗之间反复销毁的机会，而不是对完成时间的预测。V31 一个保存父段已占约 4.80 h，之后还有长未完成准备；未知的三 sector、完整参考和 target 成本不能用 q4×6 或 q0×8声称已经估准。24 h 也不保证全部阶段完成。若用户另给更短窗口，严格执行实际批准值，不静默采用提案值。

P0 先完成小型实际入口 fixture 和源码冻结，不为新版本复制整套庞大 runner。新 review、source、imports、window 数值与批准 evidence 需要最小显式注册；旧 V31 常量和历史合同仍可审查，不能把旧批准 JSON 编辑后继续用。新窗起算覆盖 activation/ABI、资源核对、必要数组读回、FE/JIT、native、factor、target 和收口；不是从数据准备完后才计时。

获准后在同窗内连续推进，不在每个 q 或 reference 完成后再等网页审阅。阶段允许开工应考虑剩余时间和有依据的完成/封存费用；不能临近截止才启动显然无法保全的昂贵 bank。真正缺少估计时如实记录并采用已批准的有界尝试，不凭空填 ETA。

### 6.2 checker 的剩余问题不能靠直接 CLI 补检宣称闭合

本轮原自动 checker 未通过路径绑定；修复后直接只读重检 return2、NO_PARTIAL_FOOTER，三个 PASS 字段均 false，`required_checker_supervision_recreated=false`。这份负结果保留，不能追认“required checker 已通过”。[R7]

c9 修复对本次强制截止的身份绑定有价值，但其缺输出判定同时写死了 exit=-9、43,200/42,000 s 等 V31 条件。下一轮不能照搬：合同允许的正常响应 SIGTERM 的受控退出也应进入受监督只读收口，而不是只有被 SIGKILL 的 attempt 才能检查。时间从本轮批准合同取值，停止原因、退出状态、source/input/window、watchdog 和清场仍须真实一致，不能允许任意失败绕过绑定。[C7]

先用无 PDE 的小型监督 fixture 验证完整 **service 授权 → required-checker supervisor → watchdog 启动和运行采样 → checker → 结果/清场落盘**，覆盖普通完成、合格 partial、缺 footer、数值 cutoff 后的 closeout、响应 TERM 和需 KILL 两类、坏路径/hash/source 的拒绝，以及到总 deadline 的停止。只验证 helper 或直接调用 check-partial 不足以覆盖本次缺口。

本轮实际运行还必须留下同样的真实监督证据。原 service/cgroup 已退出的 V31 不能伪装复活；历史补检需要的 checker-only 执行使用独立、明确批准的范围或新窗中的只读步骤，原 window 与数值 source 不变，checker source 和本次监督 source 单列。无必要不重复已有大数组补检。

新 worker 在真实数值目录建立早期阶段账，独立 q 产品与每个 native case 原子保存；controller 在 KILL 后可另存“从哪些既有收据重建了哪些事实”的索引，但不得伪造 worker footer。缺旧 footer 仍为 NO_PARTIAL_FOOTER；另列 q4 artifact/native 的实际资格，不用一个总布尔量抹去或提升它。

总收口可用时间同时受剩余批准总预算、真实总 deadline 和 checker 子预算限制；启动和运行采样采用同一 closeout 语义。30 s 清场宽限需计入总窗，不在总截止之后自动追加。task cgroup/进程树/swap/源身份门继续覆盖 checker。

## 7. 测试、职责、提交与下一份回应

P0 最小必须覆盖：新旧 source 根不同且旧目录只读时，真实 package/dispatcher/worker 仍消费指定 pending；missing/corrupt pending 时禁止调用 producer/routes/pattern/fill；consumer/native 新输出不修改旧文件；四次 native 少一项或失败不能发布 COMPLETE；原生 owner 没有用 CSR/保存 Schur 自验；同对象交给 reference 后无隐藏重建；上述真实监督链的正负路径。既有已通过 helper/ALL_Q/六 case 只跑受影响定向回归，不反复启动全仓或大 PDE。

有边界接口不相容、无歧义程序错误时定向修复后继续，不把普通 bug 当成本轮永久停止理由。身份/材料缺失、真残差失败、资源不准入、task swap 非零、失联或固定截止则停止受影响数值阶段；同一范围内安全的保存/只读收口继续。不绕过数学门或改变 RHS/模式/材料来凑 PASS。

职责沿目录 AGENTS：执行者在现有 `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` 实现和测试，主控集中审查/冻结/提交，并通过原获准通道部署和启动 `/home/fenics/Projects/laptop_share`。本报告不授予执行者自行 SSH、另建工作树、安装新栈或操作其他项目的权限。已明确的主机/cap不重复询问；新窗口仍需一次真实批准。

提交建议：一笔受影响源码/定向测试/新执行包冻结；运行后集中提交轻量结果、response 和索引；必要 checker-only 修复另笔保留源拆分。所有运行源码先 clean，失败日志用唯一 attempt 路径，不复用同名日志覆盖原失败，不 amend/force-push，不合并 master。ChatGPT 只写本 review，Codex 按职责更新自己的 outcomes/response。

`response_v32.md` 开头直接报告新增哪个 q 的 native/矩阵/因子/参考或目标场，以及哪个门仍未过。至少同步：

| 交付 | 必含内容 |
|---|---|
| continuation receipt | 旧 pending/三数组原路径与 hash、四层来源、新 consumer、实际未调用重建计数、导入资源/时间 |
| owner phase audit | 历史可知/未知、新内部阶段完整事件、最后活跃调用、对象/共享/释放、实际热点证据 |
| per-q/operator | 每 q 实际形状/NNZ/字节/支持/来源、四作用/native 向量、COMPLETE 或缺项 |
| bank/reference/target | 两 RHS、实际 INFOG、live numeric 集合、六 case、strict/V15、PC/A6/Krylov及场状态 |
| time/resource | 不重叠父段、原生子段、冷/暖标签、历史失败/UNKNOWN、全过程 tree/cgroup/swap、系统余量 |
| supervised closeout / handoff | 实际 supervisor/命令/source/contract/window/资源/退出/清场收据；精确下次断点和命令 |

更新 summary、test_summary、run_index、development_progress 和 development_model_registry。run_index 顶层旧 `current_code_sha` 仍指向 V30；新索引应明确各 run 的 source 与最新结果入口，保留旧字段历史，避免新入口误读成当前科学源码。[R8]

完整冷账不是 V31 工作包总父钟，也不是 V32 warm continuation。必要首次生产/pattern/fill、参考与目标构建、JIT、分解、完整迭代、恢复输出/检查/清理按真实不重叠阶段计入；共享只计一次，失败开发费用保留在工程账但不冒充必要算法成本。历史缺项不填零。跳过本轮已完成矩阵会减少重复工作，但未来读取/native 的真实成本仍要测量；不能仅凭跳过 4.80 h 历史父段宣布一个实测加速比或 48 h 已通过。

## 8. 给现有 Codex 的接续文本

> 请在 task40extra_0p7nm_engineering 按 Review V32 接续；结果基线 0a082891f450bef5903df5c5cb40236ac35d3081，V31 数值 source 54cf6d367b07355c0ab08c8c10655ecac73cfc6a。保留 q4 pending `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad` 及全部旧证据。先做窄 P0：把精确旧 pending 路径/hash接到正式 package、DAT/worker 和导入函数，新 source 输出根与旧只读数据根分开；q4 必须 require-existing，缺项拒绝，绝不 fallback routes/pattern/fill。先只读提取旧 owner 阶段证据；不足就保留 UNKNOWN，并在必要的新构建内部记录真实阶段。优先用已资格原始 B/D/H 流加 fresh volume FE/local recovery 构建兼容且可复用的 native owner，不以 CSR 或保存 Schur 自验，不无条件重建完整 surface 前缀。补真实受监督 checker 全链，包括 TERM/KILL 和缺 footer 的负结果。
>
> 主控冻结后提交实际可用的 continuation/service/受监督 checker 命令、完整 source/contract/import 身份。本文建议新的 24 h 固定窗，总86400、数值85200、收口1200，尚待用户一次明确批准；旧 V31 T0不刷新，cap/ABI/MUMPS/线程和数值门不变。已经实际批准的新窗口不重复询问，未批准则只完成 P0。
>
> 获准后连续推进：只读导入 q4 → 缺失独立 native 四作用≤1e−11 → (q1,q5)、(q2,q6)、(q3,q7) 真实共同生产和逐 q 资格 → 完整对象账准入八 q symbolic/numeric/同因子两 RHS≤1e−10并保留 → 同一 owner 六类原生参考检查 → 条件原尺寸非可分 target pilot。q0 producer/native不重做，旧因子已毁，本次 live bank 才新建一次 q0 factor。普通程序 bug 定向修复继续，真实数值/身份/资源/固定截止门不绕过。逐 q 保存成果和成本，不以缺总 footer 抹去产品，也不据 pending 授予 native/factor PASS。提交 response_v32、owner/per-q/bank/reference/target/监督收口证据、时间/对象账与精确 handoff，不合并 master、不自动提高 cap、不宣称最终冷流程或精度已通过。

## 9. 冻结来源与发布核验

本 review 使用以下固定源码/证据，不用分支漂移后的行号替换旧运行事实。当前任务目录没有列出独立新补充任务书；V31 review 是本次已正式回应的前序范围。历史任务初始小模型/WSL边界与后续已获准工作站范围按时间和权限分别理解，不追溯改写。

本次发布需回读完整新文件、远端 HEAD 与单文件 diff；Markdown 表格、围栏、来源引用作静态校验。未运行项目测试、工作站大数组或 GitHub 可视渲染核验的项目据实列明，不以静态检查冒充 CI 或科学 PASS。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/response_v31.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/review_v31_controller_closeout_audit.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v31.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v31.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/reference_qualification_v31.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/target_pilot_v31.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/readonly_closeout_recheck_v31.json
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/d7ffbfea952bc160742b18739369f2e3f656ee8e/docs/task40extra_0p7nm_engineering/review_report_v31.md
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/0a082891f450bef5903df5c5cb40236ac35d3081/docs/task40extra_0p7nm_engineering/task.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/runners/task40_v10_worker.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/solvers/task40_v30_selected_q_csr.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/runners/task40_v31_contract.py
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/solvers/task40_v10_p6_yorbit.py
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py
[C6]: https://github.com/Rookie1234567/MyFEniCS/blob/54cf6d367b07355c0ab08c8c10655ecac73cfc6a/src/solvers/task40_v25_selected_q0.py
[C7]: https://github.com/Rookie1234567/MyFEniCS/blob/c9c7f4af19917cbd2c0e4ecd5c0b167cab6752f5/scripts/task40_v20_service_workflow.py
[D1]: https://github.com/Rookie1234567/MyFEniCS/compare/54cf6d367b07355c0ab08c8c10655ecac73cfc6a...0a082891f450bef5903df5c5cb40236ac35d3081
