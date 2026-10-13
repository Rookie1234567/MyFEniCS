# Task40extra Review V31：先产出 q4 保存矩阵，再连续推进全 q、参考逆与原尺寸 pilot

**审阅结论：V30 交付可作为一次保留了原失败证据、任务零 swap 的受控停止接受；新增科学资格仍未闭合。下一轮继续现有精确参考预条件器路线，首先纠正 q4 保存数据入口的执行顺序，使已经拥有的贡献数据尽早变成可复用矩阵，再完成独立 native、其余 q、全因子驻留和原尺寸 target。**

V30 的软件工作有可用价值：八 q 数据接入、旧 q0 CSR 注入、ALL_Q_RESIDENT 两 RHS 和计时、六类完整参考检查以及 reference-first→target owner 交接已经进入源码。但“接口实现”与“真实矩阵、因子和场通过”须分别验收。此次关键问题是必要数值成果出现得太晚，而且前置阶段缺少足以定位费用的持久记录。继续增加同样的运行时长不能替代修正执行顺序。

## 0. 审阅身份与执行边界

| 项目 | 本次核对或决定 |
|---|---|
| 审阅日期 | 2026-10-13，UTC |
| 仓库 / 唯一分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 已回读确认的 V30 远端 HEAD | `05d66907b56c24d3fb916122eb0509c07a0aa343` |
| V30 最终科学源码 | `1e9109cb62343b13c850da03432def2109fee481` |
| V29 结果基准 | `5823faf26e5425974645c2b1fc2b4004552b4324` |
| 上一份 Review V30 | `8c05f1bf2aecd318ca3270ddfb0b787dcc3465e8` |
| V30 交付审阅状态 | `pass_with_qualifications`：接受受控停止和软件增量的证据；不授予新增 q、全参考或 target 科学 PASS |
| 继续沿用 | 现有工作站、原 ABI / exact MUMPS、1.5 TiB task cap、64 GiB host reserve、任务 swap0 |
| 新重型执行窗 | **PENDING_USER_APPROVAL**；先完成 P0 可审查实现包，再一次批准新的 12 h 固定执行窗 |
| 分支与发布 | review 直接提交同一执行分支；不合并 master，不改变普通默认 |

科学源码到结果 HEAD 的实际远端差异只有一笔、14 个文档/证据文件；没有在收口提交中再改科学源码。[D1] 本次读取了完整 response、controller audit、逐 q/operator、reference、time/resource、pilot、artifact inventory、handoff，以及 run index 的 V30 项和相关冻结源码。[R1]–[R9]

本 Chat 进行了远端源码审查与轻量原文 hash 校验，没有登录工作站、执行 FE/PDE、重分解、运行项目测试或回读本机大数组。工作树干净是交付方声明；本 Chat 独立核对的是远端提交与文件内容。工作站大数组、向量和完整 timeline 的资格依赖已保存的精确路径/hash 与 controller 审计，不能把本次文本审阅说成另一次数值重算。

## 1. V30 的真实进展与尚缺的科学结果

### 1.1 接受范围

| 对象 | 已确认事实 | 状态 / 边界 |
|---|---|---|
| 历史 q0 算子 | V28 的 777,644²、577,061,168 结构槽、11,544,333,940 B complex128/int32 CSR/native 资格继续有效 | ACCEPTED_LEGACY |
| 历史 q0 分解 | V29 两 RHS 真残差 1.977628323114713e−14、1.6069609784650353e−14，均≤1e−10；一次 numeric、两次 MatSolve | V29 生命周期 PASS；factor 已销毁 |
| V30 新 q 资格 | 无新的 COMPLETE CSR/native 收据 | 新增 0/8；不能写成历史总资格 0/8 |
| ALL_Q 软件实现 | 全 q symbolic 后统一准入、逐 q numeric、同因子第二 RHS、ready 状态分离和计时接口已接入 | 源码/fixture 能力，未得到真实八 q 实测 |
| 完整参考逆接口 | 原四类 startup 加两类 mixed FE/port RHS，同一 reference owner 交给 target | 源码接线完成；真实完整检查 NOT_RUN |
| 最终正式服务 | 确实进入 FE/编译相关流程；最后持久阶段 preflight | PERFORMANCE_CONTROLLED_STOP |
| 八 q 因子组、完整参考资格、目标场 | 没有相应完成收据 | NOT_QUALIFIED；factor/MatSolve 实际计数 UNKNOWN |
| 原尺寸与最终精度 | 50×25×140 nm、0.7 nm 非可分三维目标、网格/mode 精度、完整冷流程 2 TB/48 h | 均未闭合 |

依据为正式回应及四份 compact；ALL_Q 与参考接口的实现范围另由冻结源码确认。[R1]、[R3]–[R6]、[C1]、[C6]

旧 q0 的 COMPLETE manifest 为 `ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290`，匹配 native PASS 为 `63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81`。下一轮不重跑其 producer、pattern、fill 和已接受 native。新进程建立 live bank 时仍需对 q0 重新 numeric 一次并做本次因子资格；这笔必要成本正常计入。[R4]、[R8]、[R10]

### 1.2 时间、内存和停止原因

| 口径 | 原始值 | 正确使用方式 |
|---|---:|---|
| 最终正式服务父钟 | 13,918.291982708964 s，约 3.8662 h | 一次正式运行的父区间 |
| 更外层 run_case 父段 | 13,918.492594092 s | 包围同次运行；不能与上一项相加 |
| service 十个相邻外层区间之和 | 13,919.84385643185 s，derived | 由 controller 原始 budget 字段求和；包含入口、ABI、准入和 checker supervisor |
| launcher 停止时工作包保守累计 | 42,033.09600802868 s | 已包含准备、修复、失败、等待和最后服务；不是纯算法成本，也不是最终文档/推送收口完成时点 |
| 最后 worker 入口数值余量 | 13,885.1193 s | 原固定窗中剩余的数值预算 |
| 后续只读 checker | 0.20212502288632095 s，return 2 | NO_PARTIAL_FOOTER；checker_passed=false |
| 同时进程树 RSS 峰值 | 18,555,887,616 B，约 17.2815 GiB | 身份覆盖 complete |
| 专用任务 cgroup 峰值 | 26,902,548,480 B，约 25.0550 GiB | 与 RSS 不同口径；不能用差额断言某个缓存大小 |
| task tree / cgroup swap | 0 / 0 B | 任务零 swap 通过 |
| PSS | null / DISABLED_BY_PROFILE | 未采样，不填 0 |
| host-global 诊断 | pswpin +1 页，pswpout +0 页 | 保留宿主既有 swap；不能归属本任务 |
| 清场 | SIGTERM 后 30 s 宽限，随后完整后代清理；remaining_child_pids=[] | 受控截止，不是 OOM |

原 T0 为 2026-10-12 12:23:42Z，数值截止 2026-10-13 00:03:42Z，总截止 00:23:42Z，没有刷新。累计比 42,000 s 多出的约 33.096 s 是已发生费用，不增加数值授权。第一次只读包装的 KeyError 没有单列父计时，仍为 UNKNOWN；最终全部收口成本也不能用 42,033.096 s 代替。[R2]、[R5]、[R9]

本轮有五次早期入口失败，源码、原失败和测试记录应保留。最后一次服务缺少 FE/MPC、JIT、local owner、q 投影等内部阶段的完整时间边界，因此不能把 3.87 h 全归给其中一项。没有 OOM、因子资源门失败或目标迭代不收敛的证据。[R1]、[R2]、[R9]

## 2. 为什么 q4 保存数据没有先形成成果

这里的 q 是周期参考问题按相位拆开的分块；完整预条件器需要八块。q4 与 q0 共用 twist0 的局部贡献数据，但 q4 有自己的相位映射、端口和矩阵，不能复制 q0 的 CSR。

冻结源码中，q4 donor 的打开点位于完整 reference builder 的 missing-q callback 内。实际先后关系如下。

| 冻结源码位置 | 在打开 q4 保存贡献之前已经安排的工作 |
|---|---|
| worker.py 6936–6965 | 进入 `build_task40_v10_p6_reference_inverse` |
| yorbit.py 4676–4687 | 全局 regular-reference FE/MPC 与完整 physical action |
| yorbit.py 4767–4784 | 全局 orbit entities 与完整 FE layout |
| yorbit.py 4898–4904、4921–4930 | twist0 局部 FE/MPC 与 physical action |
| yorbit.py 4932–5016 | global/local transport、form 编译、局部凝聚/恢复 owner、trace 与两 q map |
| yorbit.py 5018–5064 | 加载现成 q0，再调用 missing-q preparer |
| worker.py 6812–6824 | 此时才调用 `_task40_v30_open_saved_q4_source` |

因此，V30 实现了 reference 先于 target，却没有实现上一轮要求的 q4 保存成果先于完整 reference 准备。[C1]、[C2] 这是一项可静态确认的顺序问题；本轮实际停在哪个内部调用仍未知。

### 2.1 下一轮首先产出 q4 数值矩阵

将保存数据阶段移到上述完整 reference builder 之前。复用现成 `build_saved_selected_q_pattern`、`fill_saved_selected_q_values`、`_persist_v30_numeric_pending`；不另写第二套数值内核。[C3]

第一段只依赖已绑定身份的保存数据：

1. 核验 continuation manifest、producer、mode/profile、V26 支持收据及相关 payload 的长度/hash。
2. 直接打开保存 q0/q4 maps、原始 H、active lookup、volume stream、surface B/D stream。
3. 用 q4 自己的 map 建 pattern、prefix/indices/indptr 和 complex128 data，保留每 q int32 可表示性检查。
4. 完成 fill、flush、三数组 hash 和结构/finite 核验，原子保存 `NUMERIC_COMPLETE_NATIVE_PENDING`。

这一段不应构建 global FE、target、完整 reference owner、任何 factor，也不需要先加载 11.54 GB 的旧 q0 数值 CSR。q0 的旧资格头与必要 map 可以读取。q4 的 777,424² 是 profile 预期；先核验实际保存 q4 map 的列数和 trace/port 分割再记录实测形状，其 NNZ 和 payload 由真实 pattern 得出，不能填入 q0 数字。[R3]、[C1]、[C3]

当前 saved opener 还要求 live q0/q4 map 和 live H，worker.py 202–224 因而把保存读取与 live owner 绑定在一起。将它拆为“保存身份打开”和“后续 live 身份核对”，两项检查都保留，只改变执行时机。不得先用 profile 预期值冒充 live 验证完成。[C1]

**numeric-pending 是完整数值数组的可恢复里程碑，仍不是可分解的合格 CSR/native。** 本轮计划继续补 native，不把 pending 当作主动停审的终点。

### 2.2 再补 q4 独立 native，复用必要局部 owner

独立 native 检查是让另一条原始 FE 作用路径计算同一输入，与新 CSR 的输出比较，防止组装错误在“自己检查自己”时被掩盖。保存 Schur replay 来自 CSR 的同一数据源，不能替代它。

保留旧 q4 完整第一输入见证和已经接受的双向 leakage；仅补 q4 缺失的 trace/port 分量及第二个不同非零 full 输入，完成四次完整 CSR 作用、分量重组与配对泄漏检查，最大相对误差继续≤1e−11。旧 q0 native 不重跑。P2 若需 peer diagonal 对照，可以读取一次旧 q0 CSR 并消费保存见证；这笔读取正常计费，且不成为 P1 的前置。[C3]

这些缺项确实需要 action.recover_storage、原生 volume action、原 B/D/H 和 dual reduction。V25 保存包没有完整 interior LU/recovery owner，不能承诺纯保存数据就能完成全部 native。[C9] 先从既有 sector 实现抽取只依赖冻结 modes/context 的 twist0 局部 builder，避免先建立全局 reference FE；与保存 map/H/lookup 核对后补齐原生见证。必要的局部 FE、JIT、凝聚及恢复工作属于获准窗口内的新工作，全部计时计内存。

V25 generated action 与 V30 local_bundle/carrier 的接口并不完全相同，应做局部适配，使满足 native/recovery 接口的同一 twist0 owner 可交给后续 reference；不能为了满足旧 builder 的形式参数又偷偷重建整个前缀。owner 标识、创建、借用和释放要可追踪。完整 reference 的 global layout/transport 可以后建。同一进程中复用可用 owner；跨进程只能复用已资格的数据，必须重建的原生对象如实计费。

### 2.3 direct-H 的数学前提保留

q4 的 direct-H 简化只在已 hash 绑定的 V26 twist0 支持收据证明内部 B、D 非零数都为 0 时成立。当前 worker.py 264–312 与 selected_q_csr.py 193–207 已有该门，应保留。[C1]、[C3]

新 twist 必须以各自真实数据核查，不能继承 twist0 的空内部支持结论。优先保留现有准确一般 Hhat 路径；若实际内部 B/D 非零，必须保留完整内部凝聚修正。扩展 direct-H 不是本轮前置要求。若扩展，除了支持证明，还要修通 live contribution 的 `include_hhat` 参数接口，不能只切一个布尔值。

## 3. 重型运行前必须修好的几处实际接线问题

以下都是源码中可定位的有限修复。它们不构成重跑已接受 q0 的理由，也不能追认成 V30 已发生的耗时原因。

### 3.1 q1/q5 callback 的局部变量先用后赋值

worker.py 6853 在生成新 sector producer 身份时读取 `sector_builder_inputs["mode_manifest_sha256"]`，同一 callback 到 6862 才赋值。q4 被前面的 continue 跳过，第一批新 q1/q5 则会进入该读取，导致 UnboundLocalError。[C1]

将 `_task40_v30_sector_builder_inputs` 移到 q_maps 和冻结 mode inventory 就绪之后、首次读取之前。最小 fixture 必须调用真实非 q4 callback 的 identity 路径；只测试 helper 返回值或检查源码字符串不覆盖此问题。

### 3.2 reference-first 与 all-q 资源门不相容

正式 stage runner 明确传 `share_transform_bank=True`。reference-first 阶段 target 尚未构建，worker 正确传 actual target rows=None，并另外传 planned rows。AllQ 也正确将 actual match 留为 False。[C1]、[C6]、[C8]

但是 worker.py 6037–6046 的真实 `all_q_symbolic_before_any_numeric` callback 仍要求 `actual_target_and_reference_full_rows_match_required is True`。当前路径即使获得八 q CSR，也会在所有 symbolic 后、任何 numeric 前被此门拒绝。

窄修为三个明确边界：

| 边界 | 允许依据 | 尚不授予的资格 |
|---|---|---|
| REFERENCE_ONLY | 完整 reference 当前/未来对象、八 q CSR/PETSc、实际逐 q symbolic、reference 恢复与检查工作集闭合 | actual target 仍 null；target 尚未准入 |
| TARGET_BUILD | 保留 live bank 时，target mesh/MPC、local LU/action/cache、映射、构建及未来工作集的新增量已闭合并实时准入 | planned rows 只作派生预算，不写 actual=True |
| TARGET_READY / 首次 PC 前 | target 建成后核验 actual 行数、mode/map/布局与 reference 的真实一致性，并回读完整共驻量 | 任一不符就拒绝 target 作用 |

参考自身账闭合时允许完成 reference 资格。未知的 target 对象只阻止 target 开始，不应反过来强迫先建 target 或阻止已准入 reference。不能通过删除 gate、关闭共享标志或把计划值伪装成 actual 绕过。[C1]、[C6]

### 3.3 落盘成果需要真正的重开入口

selected_q_csr.py 1846–1885 目前每次无条件 pattern→fill→pending；已存在的 SQLite、数组或 pending 又会被安全拒绝覆盖。已有持久化函数尚不足以构成可续作流程。[C2]、[C3]

本轮做一个受身份约束的分阶段 dispatcher，优先覆盖完整状态，不发展复杂的逐 contribution 崩溃恢复：

| 已保存状态 | 接续动作 |
|---|---|
| COMPLETE_CSR + 匹配 native PASS | 严格导入并消费；不重复 pattern/fill/native |
| NUMERIC_COMPLETE_NATIVE_PENDING | 核验三数组与身份后直接补缺 native |
| 完整且已认证的 pattern，数值未完成 | 复用 indices/indptr；新数值 attempt 从精确零开始 fill |
| 只有部分 route/pattern | 保留旧 attempt；缺少结构完成证据时不冒称 pattern PASS |

partial data 不能继续无条件累加。当前 fill 已有“restart from exact zero”的约束，应保留。每个阶段开始前先查旧成果，避免以“文件已存在”为理由换目录重做整条前缀。

### 3.4 非 q0 成果跨窗口需要明确消费身份

QualifiedQCSRProvider.load 在 290–295 要求 selector.execution_identity 等于当前 execution，在 367 又要求非 q0 native qualification 的 execution_identity 相同。因此，未来某个 q 完成后换窗，单改 selector 仍会被旧 native 的窗口绑定拒绝。[C4]

引入明确的导入 receipt/sidecar：旧 producer、matrix source、native source/window 与原始 PASS 不可变；本次 consumer source/window 单列，并绑定被批准的旧 manifest/native hash、相同 scientific input/profile/ordered modes/q map/H/三数组。相关数值实现变化时说明旧证据仍适用的依据；真正改变算子时重新资格化受影响部分。不能全局取消身份校验，也不能改写旧 PASS 伪装为本窗新做。

### 3.5 收口 checker 必须使用总截止，修完整调用链

已发生错误有三处：

- service workflow.py 3268–3272 给 required checker 使用数值截止；
- watchdog.py 463–476 在启动时扣去 closeout reserve；
- watchdog.py 721–731 在运行中采样仍按数值截止终止。[C5]、[C7]

仅把第一处 wall_seconds 改为 43,200 s 不够。给经用途、命令和身份校验的 required/read-only checker 明确 `phase=closeout`；继续绑定同一固定 window/hash、连续计费账、保守时钟、专用 cgroup、task swap0 和后代清场。数值阶段的截止保持不变。

收口可用时间取以下三者的最小值：总预算减已计费、总 deadline 减当前时间、该 checker 的剩余子预算。启动门和采样门都使用同一 phase 语义；相关 campaign observe 接口也要一致。30 s 终止宽限与证据 flush 包含于总窗，不能在总截止后追加。

不得移除 campaign 参数，不把数值命令标成 closeout，不刷新 T0。旧 checker 错误和已得到的 NO_PARTIAL_FOOTER 保留；缺 footer 的复核仍返回 false，不补造 footer，也不重解 PDE。

### 3.6 记录勘误与状态命名

本 Chat 对 controller audit 的 17,753 B UTF-8 原文重算 SHA-256，结果为：

```text
588f5476552fa3dfdaf2e517e6ab8bcc0400b580ac97c98fbb1bac2cd2cc074f
```

它与 response、run index 和四个 compact 的引用一致；artifact inventory 的该字段少一个 c、只有 63 位。四份 compact 的实际长度/hash 均与 run index 匹配。[R2]–[R7]、[R9] 下一份派生索引记勘误并指向正确 hash，保留原冻结记录；不开展数值重跑。

共享旧 label “target_retained_and_fast_backend_complete” 不能用于宣布 target 已建成。下一版 label 应对应实际 stage/owner 完成事件。当前 V30 源码事实与旧 label 的不符已由 controller 明确指出，不追溯伪造完成收据。[R2]、[R6]

## 4. 下一轮要留下可用断点，而不只是更多日志

本轮 watchdog/resources.jsonl 已有 477,687,370 B，仍不足以说明内部阶段在哪里花费时间。[R7] 新增的重点是实际调用边界及完成工作量，不是进一步提高全树采样频率。

在耗时调用**之前**原子写 start，在数组 flush/hash 或检查实际完成后写 end；以 append-only 事件账和最新阶段小 JSON 同时保存：

| 阶段组 | 最少可定位边界 |
|---|---|
| q4 保存路线 | donor 身份/读取、support/route、row-count/prefix、结构数组、fill、三数组封存 |
| native/local owner | mesh/MPC、form/JIT、局部凝聚/recovery、live map/H/lookup 绑定、各缺失 native case、COMPLETE/PASS |
| 三个新 twist | 每实际 sector 共同生产；每 q 自己 pattern/fill/native 与持久资格 |
| 完整 reference / bank | global FE/layout/transport、每 q conversion/symbolic/numeric/两 RHS、统一准入、live numeric 集合 |
| target 与收口 | target build/ready、PC/A6/检查点、恢复输出、checker、evict/清场 |

事件记录 source/input/window、q/twist、owner、父阶段、monotonic/boottime/UTC、当前/峰值资源、已完成工作量、产物路径/hash。长阶段按实际 cell、mode、tile 或 contribution 完成数给低频 heartbeat；无法提供进度时如实写 running，不把心跳当完成。

SIGKILL 后由 controller 依据已保存 start 和 watchdog 停止点标记 STARTED_NOT_COMPLETED，保留未记录计数 UNKNOWN。q 的已完成矩阵资格不依赖整个 target worker 最后能否写出一个总 footer。

## 5. q4 之后连续完成其余 q、live bank 和完整参考资格

### 5.1 三个新 sector 的实际生产

q4 资格通过后，依次执行 (q1,q5)、(q2,q6)、(q3,q7)。每个真实 twist 的必要 FE/MPC、mode/map、surface/volume 共同生产准备一次，保存必要贡献、身份和支持审计，供该 sector 的两份 q CSR 消费及后续续作。可以分别投影和填两份 CSR，不把双 q 同时填值重构设成前置。现成 local/recovery owner 尽量直接保留给完整 reference。

以下仅为冻结 profile 的预期行数，不是 V30 已装配矩阵；各 q 实际 NNZ、CSR 字节数与成本必须分别测量。[R3]

| 真实 sector | q | 预期增广行数 | 本轮起点 |
|---|---|---|---|
| twist0 | q0 / q4 | 777,644 / 777,424 | q0 COMPLETE/native 已接受；q4 从保存贡献开始 |
| twist1 | q1 / q5 | 777,620 / 777,552 | 需要该 twist 新的真实生产及两份矩阵资格 |
| twist2 | q2 / q6 | 777,596 / 777,596 | 相同行数不证明矩阵相同 |
| twist3 | q3 / q7 | 777,552 / 777,620 | 独立绑定各自相位、mode/map/H |

每个新 q 沿用两组不同完整非零 complex 输入、第一组的 trace-only/port-only 原生分量、四次完整 CSR 作用及≤1e−11 门。同 sector 双向泄漏按原 native 对角作用尺度检查。保存 stream replay 不能改名为独立 native；也不要求先建完整非对角 CSR 才能继续。单 q int32 合格不意味着可把八份 CSR 拼成一个 int32 巨矩阵；全局统计用安全宽整数。

### 5.2 在一次 ALL_Q 构建中取得分解资格并保留因子

因子是矩阵经过昂贵分解后可反复用于求解的对象。保留全部因子会占用更多内存，但能避免每轮参考作用再次分解各 q。V29 已有 q0 的建立与回代成本差别；当前需要其余 q 和整次参考作用的实测来判断这项交换是否值得。[R10]

保留已实现的 AllQExactMumps 主结构：

1. 八 q COMPLETE/native 真实齐全后，严格注入 CSR；无效数据拒绝，不 fallback 重装 q0。
2. 逐 q conversion/symbolic，保存实际 INFOG16/17；全部完成后按完整 reference 共驻账统一准入。
3. 准入后逐 q numeric、fresh true-residual probe、同因子第二个不同非零 RHS，均用该 q 原完整 CSR 算真残差≤1e−10。
4. 前面已通过 numeric 的因子继续保留，直到八个真实 numeric PASS 同时存活，进入 reference。
5. 各次 reference/target 调用复用同一 owner；结束时统一释放并验证清场。

源码已确认 fresh 调 `self.factors[q].solve`，第二 RHS 调同一对象的 `solve_repeated`，没有为第二 RHS 再 numeric；symbolic-ready 与 numeric-ready 也已区分。[C6] 无须推倒这部分实现。下一轮需要真实收据，不能将 fixture 通过或八个 symbolic 对象说成全因子组成功。

保持 exact MUMPS、complex128/int32、MPI1/数学线程1，原排序/主元和 ICNTL 控制不变；沿用 ICNTL(35)=0、(10)=0、(2)=0、(3)=6、(4)=2，并读回实际参数。不自动改 OOC、BLR、后端或线程。task cap 不是 MUMPS 单个控制参数的替代。

每 q 保存两组原 RHS/solution/residual、三数组身份、INFOG 原字段及单位、conversion/symbolic/numeric/fresh/second 的父计时与原生子计时、资源、调用计数和当前 live numeric 集合。资格 RHS 使用已冻结的实际定义，不因失败换容易通过的 RHS。

### 5.3 完整参考逆的六组检查与分级状态

完整参考逆还要完成完整 FE/端口 RHS 的折叠、内部消元、q 变换与求解、内部场恢复、原 H 端口重建。八个 q 分解成功不能替代这些接线的全空间验证。

V30 的六组检查已接入：完整 independent FE、interior-only、all-mode port、regular physical incident、mixed generic FE+port、mixed interior FE+port。保留同一 inverse 的真实作用和 global/sector 原生 oracle，不额外构造只为小 fixture 使用的全局巨大 CSR。[C1]、[C2]

必须显式并列两个状态，而不是只使用 `regular_checks["passed"]`：

| 资格 | 门限与含义 |
|---|---|
| STRICT_REFERENCE_PASS | full equation、complete augmented FE、local combined、q solve≤1e−10；alpha closure≤1e−11；全部结构、映射与恢复门仍通过 |
| V15_REFERENCE_PC_PASS | eliminated FE、complete augmented FE、noncancelling budget、业务 q solve≤1e−8；alpha≤1e−9；decomposition closure≤1e−10；frozen-scale/结构门仍通过 |
| 每 q 本轮 factor 两 RHS | 独立的≤1e−10 前置；不借 V15 业务阈值放宽 |

当前 worker 会将 row.passed 更新为 V15 准入，再用其汇总值触发 reference-qualified marker；它不等同于严格完整 inverse PASS。严格状态绑定同一 selected_state_sha256，使用该被选中状态的 reference_pc_metrics、frozen_scale_metrics 及原结构/恢复门，对照 STRICT_REFERENCE_LIMITS 和既有冻结尺度规则聚合；完整 augmented FE 也要纳入。不能拿 initial 指标配 corrected 状态，也不能只合并旧 gates 字段。[C1]、[C10]

如果 strict 未通过但已注册 V15 的完整原生 PC 准入通过，按既有合同仍可进入获准 target pilot，同时保留 strict 的实际失败指标。若 V15 结构/数值也失败，则停止受影响 target。一次有界、非递归增广修正和实际八 q 额外回代全部计数计费，不改数学门。

### 5.4 按调用类别记成本，才能判断 48 h

现有 ALL_Q 的 `S_q_business` 会聚合两次因子资格之后的 reference startup、修正和 target 调用；yorbit.py 867–872 只向 ONE_Q 传 rhs_category。不能直接用这个混合均值命名为 target RHS 成本。[C2]、[C6]

用轻量 category 传递或明确外层阶段差分区分 factor qualification、reference startup、reference correction、target PC 与其他业务。整次 PC 的父钟包含折叠、各 q solve、恢复和检查；原生 S_q 是其子计时，不再次加到总成本。

ALL_Q 先全部 symbolic 后 numeric，单 q 开始至 READY 的跨度包含别的 q 工作，不能跨 q 相加。保留 T_bank 总父段、各 q 的排他 F_q_active、第二 RHS 父段、shared 与 unattributed。CSR 若已在前面打开并借给 bank，其首次 loader 成本留在原阶段；确实重复执行的检查按实际再计一次。[R10]、[C6]

## 6. 全对象账与原尺寸 target 的准入

### 6.1 沿用已经批准的工作站和 cap

目标根仍为 `fenics-ws:/home/fenics/Projects/laptop_share`，沿用已资格 native Linux 私有栈。原 ABI 收据位置/hash见 V30 handoff；下一次仍按真实激活后的解释器、PETSc/MPI 路径和类型回读，不重装、不迁移、不另建 Task40 项目。[R8]

| 资源项 | 延续值 / 语义 |
|---|---|
| task MemoryMax | 1,649,267,441,664 B = 1.5 TiB；上限，不预分配 |
| host reserve | 68,719,476,736 B = 64 GiB；按 host 可用量保留一次 |
| task MemorySwapMax / 峰值要求 | 0 / 0 B |
| ABI / 并行 | 原 complex128/int32、MPI1、数学线程1、exact MUMPS |
| 更紧实际边界 | 实时 host MemAvailable、所有有限 ancestor cgroup 和任务 cgroup 余量 |
| 本 review 不授予 | 自动提 cap、改变主机/ABI、关闭其他项目作业、刷新旧窗口或合并 master |

cap+reserve=1,717,986,918,400 B，小于十进制 2,000,000,000,000 B；这是配置算术，不是内存目标已经通过。最终仍按同一时刻的任务、必要外围所有者、系统及其他占用评估，不能利用宿主超出十进制 2 TB 的物理内存后宣布达标。[R5]、[R10]

### 6.2 真实同时对象必须完整列出

| 对象组 | 必须入账的内容 |
|---|---|
| 八 q 源 CSR | 每份 data/indices/indptr、驻留文件页及真实共享 backing |
| PETSc 与 factor | 转换复制、排序/索引/Vec 临时量、保留输入、symbolic/numeric 与已留因子 |
| reference 全局/局部 | mesh、FE/MPC、local LU、condensation/recovery、H、mode/alias、transport、缓存 |
| target 与共享映射 | target mesh/MPC/local action/LU/cache/carrier、两方 layout、primal/dual、transform bank |
| 构建工作集 | producer、surface、pattern/row tile、fill/projection、native、JIT/compiler |
| 求解工作集 | Krylov V/Z、残差/解、一次完整 PC/A6、修正、检查点 |
| 恢复与输出 | full-storage E/H/旋度、alpha、原生检查、序列化/读回与释放前后检查 |
| 监督与系统 | checker/watchdog/完整后代、任务文件页、系统 reserve；磁盘容量单列 |

每项给 owner、unique backing bytes、alias 依据、活跃阶段、current/future、实测/派生/UNKNOWN。已在 current 的对象不再作为新增量重复收费；只有生命周期确实互斥的工作集才能取 max。同时保留的 factor、输入、local LU、reference、target 必须共同核算。

当前 AllQ 已覆盖实际 symbolic、transform inverse、72 个 retained complex128 向量及按行数推导的恢复/输出数组，但 planned target rows 不覆盖 target mesh/MPC、local LU/action、carrier/cache 等全部构建对象。[C1]、[C6] 所以 `PLANNED_ROWS_RESERVED_ACTUAL_NOT_BUILT` 不能当完整 target 预算已闭合。

每个增长阶段都检查当前量加新增量，并分别满足 task/ancestor cgroup 与 host 余量。两种缺口不能相加。未来 target 不确定时先形成参考资格；target 的未知项保留 UNKNOWN，不填 0。

### 6.3 全驻留不能准入时的受控后备

主方案是全八 q 保留，避免先逐 q factor→evict 后又全部重建。若实际全账不准入，保存各 q symbolic、对象/阶段/当前量/新增量、独立约束和真实缺口，释放已创建对象；不以 OOM 试探，也不宣称整个 2 TB 目标不可行。

只有已在 P0 冻结验证、且同窗资源/时间确实允许的单 q 后备，才可对尚缺分解实测的新 q 做 factor→两 RHS→evict，形成可用成本收据。V29 已测的 q0 不再为容量后备重复分解。部分驻留/循环策略的后续选择依赖真实每 q 重建成本和访问序列，不临时改变 target 默认。[R10]

### 6.4 参考资格后直接进入原尺寸 pilot

满足原生 PC 资格、target 完整对象账和剩余窗口时，在同一进程、同一 live bank 下准备并求解原尺寸 50×25×140 nm、0.7 nm 非可分三维 target。沿用 Nx272/Ny8/Nz14、p6 工程配置；30,464 cells、32,060 modes 是冻结配置预期，现场重新核对实际数量。[R3]、[R10]

首先核查 target/reference 实际行布局、mode/map、原始物理模型和 owner；完整记录 PC、A6、Krylov、修正、恢复和输出父成本。不能为进入下一阶段返回并销毁 bank，再在另一服务中声称复用。

最终原 A6 与释放后真残差沿原门≤1e−6，能量/体吸收绝对闭合≤1e−5；若有效冻结合同更严格，执行更严格值。只有通过这些门的场才生成 official R/T/A、A_volume、全部有序衍射级和复 E/H。[R11]

Ny8 工程 pilot 即使成功，也仍需后续独立网格及 mode 截断精度验证。本轮不添加网格扫描，不回到已完成的小模型重复调参。

## 7. 新固定执行窗口：先做好可执行包，再批准一次

V30 窗口已经结束。用户明确要求新窗口另行授权；本 review 的发布不等于新重型运行授权。已批准的主机、目录、cap/ABI 不重复询问。[R8]

### 7.1 P0 现在可以完成的工作

Codex 先在现有控制工作树完成：

- 第 2–3 节的 saved-first、真实 callback、恢复/导入、分阶段准入和 closeout 窄修。
- 严格/V15 状态分开、调用类别、真实阶段持久化。
- 最小接线 fixture、输入/selector/contract 草案、源码冻结和实际命令生成。
- 新 V31 registration/contract/账路径，保留 V30 旧 window、批准回执和全部失败。

P0 不启动 FE/JIT、完整大 payload 扫描、pattern/fill/native/factor。代码开发与小 fixture 成本仍进入连续工程工作包账。下一次冷流程评估也不会把必要运行准备变成免费成本。

V30 的注册/contract 绑定旧 review、source/window/批准身份，不能编辑旧文件后继承其 USER_APPROVED。复用既有通用 service/worker，增加最小新范围接线，不复制另一套科学 runner。[C11]

### 7.2 本次提出的具体新窗口

| 项目 | V31 待批准值 |
|---|---|
| 范围 | q4 保存矩阵/native → 三个新 sector → 八 q 因子驻留 → 完整 reference → 条件原尺寸 pilot |
| 总预算 | 43,200 s，12 h |
| 数值截止 | T0 + 42,000 s |
| 收口保留 | 1,200 s，含 checker、flush、销毁与清场 |
| T0 | PENDING；P0 就绪并获一次明确批准后，在本窗第一项必要运行准备前锚定 |
| 起算覆盖 | native activation/ABI/live 准入、必要大数组 hash/读取、FE/JIT、pattern/fill/native、factor、target |
| 重试规则 | 同一窗内普通 bug 定向修复、重试、等待都继续收费，T0/cutoff/deadline 不刷新 |
| 资源 | 延续第 6.1 节；不新增 cap 或主机请求 |

不从 worker 已启动或 FE 已做完后才计 T0。实施准备与新执行窗的分账目的是让固定执行窗从可运行状态开始，不删除工作包历史费用，也不隐去完整冷流程必须承担的准备。

三个新 twist、完整 reference owner 和 target 的成本尚未实测，不能承诺每阶段固定两小时即可完成。按持久里程碑、实际工作速率和剩余父成本决定下一个昂贵阶段的启动；不使用任意几秒 timeout，不以无输出直接重启。已知余量不足以完成 bank/reference 资格时，优先保全 CSR/native，避免临近截止才新建一组马上要销毁的因子。

获准后按下表连续推进，不在每个 q、sector、factor 或 reference 完成后重新停审。真实身份/残差/资源门失败或固定截止仍停止受影响阶段；其他可独立完成且仍在范围内的收口/保存工作继续。

## 8. 连续任务表与最小验证

| 顺序 | 必做动作 | 可审查成果 / 下一步 |
|---|---|---|
| P0，重型窗前 | 第 2–3 节窄修、阶段收据、真实 callback 小 fixture、新合同与命令、clean 科学源码 | 可审查执行包；仅新固定窗等待一次授权 |
| P1，q4 数值 | 先从保存 twist0 数据生成 q4 自己 pattern/CSR，完整封存 | NUMERIC_COMPLETE_NATIVE_PENDING；不先建 global FE/reference |
| P2，q4 native | 仅补必要 twist0 native/recovery owner，绑定 live map/H/lookup，补缺失见证 | q4 COMPLETE_CSR + native PASS；保留 owner，立即继续 |
| P3，其余 q | (q1,q5)→(q2,q6)→(q3,q7)，各实际 sector 一次共同准备，每 q 独立资格 | 连同旧 q0 共八 q COMPLETE/native；逐 q 落盘 |
| P4，reference 与 bank | 接收已有 local owners，补 global reference；全 q conversion/symbolic→统一准入→numeric/两 RHS并保留 | 八个 numeric PASS 同时 live，真实 INFOG/F_q/T_bank/内存账 |
| P5，完整参考 | 六类 full native RHS，独立恢复与原 H 检查；strict/V15 并列 | 原生 reference PC 资格，重复作用不增加 numeric |
| P6，条件 target | 共驻账与时间允许时，同 owner 构建并运行原尺寸 pilot | 真实 PC/A6/Krylov/场证据，按门报告 official 状态 |
| P7，固定收口 | partial/complete 证据收集、只读 checker、evict、完整清场 | 逐 q 成果、真实中断点、父账、负结果和下一缺项均保存 |

P1 pending 是新增可复用的数值成果，P2 是首个新的完整 q 资格；本轮主目标继续到 P3–P6 可达的最深阶段。软件接口增加或再次仅到 preflight 不构成数值主线的完成。

**最小验证应覆盖真正变化的控制流：**

1. saved-q4 路径在 global FE/native/factor 被设置为“禁止调用”的小 fixture 下，确实走到数值 pending；后续 native 失败不能发布 COMPLETE/PASS。
2. 非 q4 的 (q1,q5) 实际 callback 正常生成身份，覆盖 sector_builder_inputs 的赋值顺序。
3. 真 worker 使用的 reference-only admission 函数接受 actual target=None 的合格 reference 账；target 阶段缺对象、缺实际匹配或数值不符必须拒绝。
4. 完整 pending 重开不再次 fill；COMPLETE 导入不重跑 native；跨窗导入必须带明确授权与匹配身份，坏 hash/输入拒绝；partial fill 仍从零。
5. 同窗 numeric cutoff 后数值入口拒绝、合格 closeout checker 可启动且可持续；到总 deadline 两者受限；错误 hash/用途拒绝；NO_PARTIAL_FOOTER 仍 false。
6. 沿用已有 AllQ 两 RHS/retention、六 case 与 owner 交接 fixture，只补本次真实联动、strict/V15 聚合和费用分类的缺口。

避免每个小 bug 都跑全仓、MPI2/4或重复昂贵 Gate。测试结果按实际 source/runtime/范围和日志保存；fixture、语法检查、文档检查与科学资格分别记录。所有科学源码在 heavy 前冻结；不在 live factor 等待期间热改运行中的代码。

## 9. 如何用下一轮实测推进十进制 2 TB / 48 h

当前最缺的不是又一个 q0 外推，而是三个层次的数据：

- **完整 bank 的实际同时内存与父成本**：决定能否持续保留准确因子。
- **完整参考 PC 的一次真实成本及目标迭代轨迹**：决定用因子复用换来的时间是否足以解决原尺寸问题。
- **同一目标实例必要冷流程与精度**：决定是否真的满足 2 TB/48 h，而非只证明 warm pilot 较快。

时间继续保留两套账：连续工程工作包包含开发、失败、修复、等待；算法冷流程包含实际必需的冷输入/JIT、首次 producer/pattern/fill、reference/target 构建、分解/必要重建、业务迭代、恢复输出、独立检查和清理。V28 已测 fill 等费用仍是已知；缺失历史项保持 UNKNOWN。V31 复用旧数据的本窗时间明确是 warm continuation。

将各项划成不重叠父段后才比较：

```math
T_{\mathrm{cold}}
=
T_{\mathrm{required\ setup}}
+
T_{\mathrm{bank}}
+
T_{\mathrm{reference\ checks}}
+
T_{\mathrm{target\ iterations}}
+
T_{\mathrm{recovery,\ output,\ checks,\ cleanup}}
\le 172800\ \mathrm{s}.
```

其中 bank 的 native 子时长、各 q S_q、PC 内部子段都不再次相加。实际 target 迭代成本使用完整 PC+A6+Krylov+规定检查的实测区间，并报告变化和停滞；不能用 q0×8 或第一步速度冒充整场实测。[R10]

只有真实原尺寸解、完整冷账、峰值/系统余量/任务零 swap 和最终网格/mode 精度各自通过，才授予最终目标资格。当前继续用工程 pilot 来取得这些决策所需的数据，不因最终精度尚未证明而禁止已经获准的工程探索。

## 10. 给 Codex 的直接接续指令

以下正文可以直接交给现有 Task40extra Codex，用于先完成本轮 P0 的既定工作安排；**新重型窗状态仍为 PENDING，不能把复制本文当作用户批准窗口。** 用户若在同一会话已经明确批准本报告第 7.2 节，则记录该真实批准并直接推进，无需重复询问。

> 请在现有 task40extra_0p7nm_engineering 分支按 review_report_v31.md 继续。V30 审阅基线是 05d66907b56c24d3fb916122eb0509c07a0aa343，最终科学源码 1e9109cb62343b13c850da03432def2109fee481。保留 V28/V29 q0 COMPLETE/native 和已通过的 q0 分解证据；V29 factor 已销毁。
>
> 现在先完成 P0，不启动新 heavy：把 q4 保存数据 pattern/fill/pending 提到完整 reference builder 之前；拆开 saved identity 与后续 live map/H/lookup 绑定。补齐 numeric-pending/COMPLETE 的严格重开及跨窗口 consumer receipt，不重写旧 PASS。修正非 q4 callback 中 sector_builder_inputs 先用后赋值。分开 reference-only、target-build、target-ready 资源门，target 未建时 actual 保持 null，不能让旧 actual-match 门阻断 reference，也不能把 planned 冒称 actual。
>
> 窄修 required checker 的 closeout 时间合同，覆盖 service、watchdog 启动和采样三处，保留同一 window/hash/连续账与资源约束。修正派生索引的 controller hash 抄录，保留原失败及 NO_PARTIAL_FOOTER，不为 footer 重解 PDE。补真实阶段 start/end、进度和产物收据，以及 strict/V15 分级与 RHS 成本分类。
>
> 使用真正 callback 的最小 fixture，冻结干净科学源码，给出实际 service 和只读 checker 命令、输入/selector/contract 路径和 hash。继续沿用 fenics-ws:/home/fenics/Projects/laptop_share、1,649,267,441,664 B task cap、68,719,476,736 B host reserve、task swap0、complex128/int32、MPI1/数学线程1、原 exact MUMPS。无需重新迁移或询问主机/cap。
>
> P0 就绪后，只需一次明确的新固定窗口授权：总 43,200 s，数值 42,000 s，收口 1,200 s；T0 从本窗第一项必要运行准备之前开始。旧 V30 窗口已结束，不能刷新或修改旧批准 JSON。P0 与历史工程成本保留，运行后 bug 修复/重试仍消耗同一窗口。
>
> 获准后连续执行：先 q4 自己的完整数值 CSR并封存 pending；再只补必要 twist0 native/recovery owner和缺失独立见证，完成四作用≤1e−11；不重跑已接受 q0 producer/native。随后 (q1,q5)、(q2,q6)、(q3,q7) 各做一次真实共同准备，逐 q 保存 COMPLETE/native。
>
> 八 q 齐全后，复用已有 local owners，补全 reference，全 q conversion/symbolic 后按完整共驻账准入，再逐 q numeric/fresh/第二非零 RHS，严格≤1e−10并保留全部可准入准确因子。q0 为本次 live bank 重新 numeric 一次正常计费。不要先七次 factor→evict 再全部重建。
>
> 同一 live owner 做六类完整原生参考检查，strict reference 与 V15 PC 状态并列。资格、完整 target 对象账和时间允许即进入原尺寸非可分 target pilot，不逐阶段停审，不借新服务假称原生因子复用。账包括所有 q CSR/PETSc/factor、两方 FE/映射/local LU/cache、构建、Krylov、恢复、输出、checker和系统余量；UNKNOWN 不填零，q0×8不作全 q 实测。
>
> 普通工程 bug 定向修复并继续，真实身份/残差/资源/截止门按报告停止受影响阶段。各 q 成果即时持久化；不得让一个总 footer 缺失抹掉已完成阶段。提交 response_v31、逐 q/operator/reference/resource/pilot、时间与完整对象账、run index、handoff、summary及模型总账到同一分支。大数组保留 ignored artifacts 精确路径/hash，不合并 master，不自动提高 cap，不宣称完整冷流程/最终精度已通过。

### 10.1 现成的只读拉取与核对

在**现有 Task40 控制工作树**执行以下只读核对，不另建项目，也不修改工作站运行数据：

```bash
git branch --show-current
git status --short
git fetch origin task40extra_0p7nm_engineering
git rev-parse origin/task40extra_0p7nm_engineering
git merge-base --is-ancestor 05d66907b56c24d3fb916122eb0509c07a0aa343 origin/task40extra_0p7nm_engineering
git show origin/task40extra_0p7nm_engineering:docs/task40extra_0p7nm_engineering/review_report_v31.md
```

确认分支和工作树、回读本 review 的实际提交后按既有 fast-forward 流程接续；有意外本地变更时先保留并审查，不 reset/强推。

P0 必须在 `outcomes/handoff_v31.md` 写出**真正已实现且做过轻量解析/接线验证**的服务命令与只读 checker 命令。当前 V30 full 命令尚不具备本报告的 saved-first 与新窗口接线，不能直接重放。命令应包含实际 activation/runtime、输入/selector/合同路径、hash、冻结科学 SHA，以及获准后的唯一 T0/cutoff/deadline。本 review 不虚构尚未实现的 V31 CLI 参数。

## 11. 交付要求和本次核验范围

下一份 response_v31 首先回答“新增哪个 q 的可用矩阵/因子/参考或目标场”，再报告代码变更。至少交付：

| 交付 | 必含内容 |
|---|---|
| 逐 q/operator | shape、真实 NNZ/字节、三数组/producer/native hash、四作用结果、复用/新建/缺项 |
| factor / live bank | 每 q INFOG、两 RHS、numeric/MatSolve 计数、同时 live numeric 集合、T_bank/F_q_active/分类 S_q |
| 完整 reference | 六 case、全 interior/mode/q 覆盖、保存 native 向量、strict/V15 两状态和校正费用 |
| 时间与对象账 | 连续父钟、排他阶段、历史失败/UNKNOWN、current/future/alias、RSS/cgroup/swap/清理 |
| pilot | 实际是否 build/solve、PC/A6/Krylov成本、真残差历史、场/输出资格，不用 marker 替代 |
| handoff / 索引 | 能直接消费的完成/待 native 状态与命令，最后真实阶段、剩余缺项，原窗口与新窗口分列 |

本 Chat 已核对远端 HEAD 与科学→文档差异，读取上述正式证据并完成 controller 原文及四个 compact 的长度/hash 交叉核验，审查相关冻结控制流。没有重跑项目 pytest、FE/native、factor、PDE 或工作站大数组审计，也不声称 CI 通过。Markdown 结构、链接与远端回读由本次发布过程核验；GitHub rendered view 的实际可用性在发布回报中如实列明，不把静态文本检查冒称可视渲染检查。

**本轮推进标准是新增 q4 合格矩阵、其余 q 真实资格、可用 live 因子组、完整原生参考 PC，以及条件原尺寸 target 的真实成本/场证据。** 最终 0.7 nm、原尺寸非可分三维、十进制 2 TB/48 h 与网格/mode 精度仍分别验收。

## 12. 冻结来源

所有源码行号与以下文件均固定在 V30 结果 HEAD，后续执行另记自己的 source、window 和产物身份。

| 引用 | 证据内容 |
|---|---|
| [R1] | V30 正式回应 |
| [R2] | controller audit 与完整停止/时间/清场/只读 checker 记录 |
| [R3] / [R4] | 逐 q/operator 与 reference compact |
| [R5] / [R6] | time/resource 与 pilot compact |
| [R7] / [R8] / [R9] | artifact inventory、handoff、run index |
| [R10] / [R11] | 上一份 Review V30 的已接受基线与原任务科学门 |
| [C1] / [C2] | worker 和完整参考 builder/作用源码 |
| [C3] / [C4] | selected-q 构建/资格与 qualified CSR provider |
| [C5] / [C7] | service workflow 与 watchdog 时间合同 |
| [C6] / [C8] | AllQ MUMPS 与正式 stage runner |
| [C9] / [C10] / [C11] | 原 native 依赖、严格/V15 门、新执行合同既有实现 |
| [D1] | 最终科学源码到正式结果 HEAD 的远端差异 |


[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/response_v30.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/review_v30_controller_audit.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v30.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/reference_qualification_v30.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v30.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/target_pilot_v30.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/v30_run_artifact_inventory.json
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/handoff_v30.md
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/review_report_v30.md
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/docs/task40extra_0p7nm_engineering/task.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/runners/task40_v10_worker.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/task40_v10_p6_yorbit.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/task40_v30_selected_q_csr.py
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/task40_v30_qualified_q_csr.py
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/scripts/task40_v20_service_workflow.py
[C6]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/task40_v10_p6_mumps.py
[C7]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/benchmarks/subreaper_watchdog.py
[C8]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/runners/task40_v20_stage_runner.py
[C9]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/task40_v25_selected_q0.py
[C10]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/solvers/augmented_reference_correction.py
[C11]: https://github.com/Rookie1234567/MyFEniCS/blob/05d66907b56c24d3fb916122eb0509c07a0aa343/src/runners/task40_v30_contract.py
[D1]: https://github.com/Rookie1234567/MyFEniCS/compare/1e9109cb62343b13c850da03432def2109fee481...05d66907b56c24d3fb916122eb0509c07a0aa343
