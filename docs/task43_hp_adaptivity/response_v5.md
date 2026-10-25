# Task43 Review V4 执行回应：F1–F4 有限整改（V5）

本轮回应正式 review 提交 `d1a005385bcaa736a2e2b9d0d411dca35a93868a` 的第 10 节；该 review 审阅的源码提交是 `80f51ad2694acaa0a2494c01752e84023c03beca`，本轮起点 HEAD 为 review 提交 `d1a005385bcaa736a2e2b9d0d411dca35a93868a`。执行分支仍为 `task43_hp_adaptivity`，任务基线仍为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`；本轮四个 Python 文件以验证 compact 中的实际 SHA 绑定。历史 response_v4、review、冻结合同、READY、terminal 和数值原件均未覆盖。

有限代码与fixture整改已完成，但验证不是无条件全通过：25项最小节点通过，31项focused首次运行有1项支持驱动父子拓扑失败，两个窄恢复节点通过；六次支持driver的严格全程CPU1要求未满足。本回应保留失败与资源限制，等待审阅，不申请READY或生产合并。

WorkflowLedger 是运行日志，记录真实入口进入的阶段以及监督器的进程身份，便于判断网格或求解是否已经开始；代价是少量文件写入。原子写入先完整写临时文件再替换目标，避免异常留下半份 JSON，但会增加磁盘操作。`primary`是在正常校正结束、额外校正之前冻结的解；`extra`用同一个已分解矩阵再校正一次，以观察额外回代是否降低残差，代价是保留原向量并继续占用因子内存。这些留证改动防止后处理失败丢失已完成的证据，不会提高网格精度。

## 执行结果

| Review 项 | 实施与验证 | 结论边界 |
|---|---|---|
| F1：A1 非空输出根保护 | 只有本次 rank 0 成功创建空 run root、并完成必要同步后才设置写入资格；失败 wrapper 在未取得资格时不写旧 root。真实 `h100_anchor.main` fixture 分别带/不带旧 terminal 拒绝非空目录，比较整个目录文件集合与逐文件 SHA；两例都证明 mesh/solver sentinel 调用数为0。missing phase 与错误 watchdog parent 也在 mesh 前拒绝。 | 这是隔离的入口/文件 fixture；不回填 A1_q2 历史现场 G2，也没有运行网格、装配或求解。 |
| F2：comparison 原件路径/hash | 降权限 comparison 的 `original_record_path` 现在指向不可变 sidecar，原来的当前 comparison 路径另列；两条现有后处理故障测试直接读取 sidecar 并核实原字节和 SHA。 | 不改变测量值、primary 或历史 comparison；不授予物理端点资格。 |
| F3：二次写失败的联合读取边界 | 测试内的文件联合约定同时核对 summary、comparison、terminal、primary 引用、source 身份、hash、权限状态及进程退出。完整合成控制包仅表示“没有这些工程否决项”，不授予数值资格。独立负例覆盖失败 terminal、nonzero/unknown exit、summary/comparison/terminal 降权、文件或绑定缺失、错误 hash 和 source mismatch。实际 writer 故障覆盖 sidecar 保存、comparison 降权、summary 降权；原异常保持可追溯，primary bytes/hash 与已测 R 值保持。 | 当前 V3 没有自动消费端；没有新增生产 checker、A2_R 路径或 controller。所有联合文件均为合成 fixture，不代表 Maxwell endpoint。 |
| F4：当前文档与进程尾段 | 更新本回应、README、summary、manifest、模型总账和 progress。将旧 response_v4 中“两个空 cmdline 段”的历史文字留在不可变文件里，由本回应纠正为完整三段计数。 | 更正文案不回写旧 resources 或历史响应。 |

最小受监控 driver 的 25 个定向案例通过（`25 passed in 11.59s`）。随后预定的31项 focused driver 报告30 passed、1 failed：A1真实入口测试发现 pytest 是检查 helper 的子进程，和它要核验的 watchdog 直接父子身份不符；这是支持驱动的进程拓扑/审查遗漏，mesh、装配与求解均未运行。第一次窄恢复在 pytest 前被一条新增 Ruff RUF059 阻止；修正唯一未使用变量名后，第二次窄恢复执行静态检查和两个受影响节点，2 passed。因而记录中不存在一次干净的31项全通过运行；25项成功、30/1 focused失败及2项恢复结果按各自命令和测试文件字节区分，不能拼成单次全通过。完整ABI、逐节点pytest argv、源码/测试/driver哈希、stdout和资源样本见[本轮验证compact](outcomes/records/v5_focused_validation_v1.json)。

六个 `subreaper_watchdog` driver 的 whole-wall 上限均为300秒，RSS上限8GiB，task swap门为0；wall依次为8.914583516307175、4.417637757025659、19.871055574156344、15.243286705110222、8.28013485390693和28.119390034116805秒，合计84.84608844062313秒。六次同时采样的树RSS峰依次为164892672、163442688、259756032、263839744、158900224和255451136字节；最大值263839744字节。swap峰均为0，所有watchdog均完成后代清理。严格“全树每个样本都在CPU1”的约束没有通过：原resources观察到minimal attempt2的ABI preflight样本、minimal attempt3的pytest worker样本、recovery2的ABI preflight样本各有一次affinity为`[0]`，另recovery1有一条Z状态进程样本没有affinity字段；这些观察的原因未确定，不归因MPI或数值行为。故本轮资源结论是wall/RSS/swap/清理已满足支持driver门，但全程CPU1资格为`LIMITED / NOT_PASSED`。另有两次主控未监控的metadata检查脚本失败，因没有watchdog timer不报告实测wall；路径和失败情况在compact单列。以上支持成本不与历史正式模型wall混算，也不是完整campaign成本。

单份 JSON 的原子替换并不构成多文件事务。故障时可能留下仍带旧资格字段的文件，因此读取者必须联合检查所有文件、终态、退出码和绑定身份；当前 V3 没有自动读取者。

| 写入故障 | 故障后可能残留的旧状态 | 联合读取处理 |
|---|---|---|
| comparison 原字节 sidecar 写入失败 | comparison 可能仍有 `endpoint_qualified=true` | 任一失败 terminal、非零/未知退出码、权限降级、缺失或错配的文件/绑定均否决；单个 true 不构成资格 |
| comparison 权限降级写入失败 | 旧 comparison 可能仍有 `endpoint_qualified=true` | 同时核对 summary、comparison、terminal、退出状态及 primary/source/hash；任一失败 terminal、非零/未知退出码、权限降级、缺失或错配均否决 |
| summary 权限降级写入失败 | 旧 summary 可能仍有 `passed=true` | 同时核对 summary、comparison、terminal、退出状态及 primary/source/hash；任一失败 terminal、非零/未知退出码、权限降级、缺失或错配均否决 |

文件系统整体不可写时，也不能保证 terminal 能成功落盘；原始异常必须由外层日志保留。三种故障测试分别验证以上残留和联合否决，不承诺跨文件原子性。

Recovery2对当时冻结的4个变更Python文件相对V4 review基线执行Ruff比较，基线/当前/新增为0/0/0，compileall通过；当时的5个JSON、10个本地链接目标及7份文档表格/链接/whitespace检查通过，`git diff --check`通过。此后又把资源复核、CPU affinity偏离和driver分次结果写入当前response/compact；这些后加文案没有由该次pytest/静态driver测试。本轮最终文案只做轻量JSON解析与diff/whitespace核对，具体命令状态在compact列明。没有运行 full repository pytest、完整 p6 FFCx witness、旧场采样/积分或模型求解；本轮新增正式PDE、dispatch、attempt、READY均为0，也没有生产合并许可。

## Task43 当前科学与授权状态

| 事项 | 当前状态 | 边界 |
|---|---|---|
| 正式预算 | 5/6 已耗用；A1 2/2、A2 3/3；剩余1槽封存 | 本轮 V4 review 执行新增正式 dispatch 为0，不重试、不跨组重分配 |
| A1_q2 | 历史受控停止 | 实际入口当时未建立 WorkflowLedger；主控此前错误放行后主动停止。F1 fixture 不能改变旧现场，亦不归因数值方法或环境 |
| A2_q3 | `INCOMPLETE_NOT_OFFICIAL` | 实际 native ledger 成立；primary 部分原始量经独立复核，extra full-active residual 未严格下降，完整 endpoint/comparison 缺失 |
| G0–G4 | 按分支和证据范围分别记录 | F1–F3 组件与文件约定有定向测试；不合并为总体 PASS，不补发 READY |
| 五项能力 | 空间 `PARTIAL`；选择 `PARTIAL`；精度 `NOT_PASSED`；同精度全过程成本 `NOT_ESTABLISHED`；迭代 `NOT_RUN / NOT_QUALIFIED` | accepted9/R9 仍为最后接受状态，最终空间精度未通过；0.7 nm 未运行 |
| 生产合并 | 未批准 | 新 observer、adapter、failure-safe 路径保持 research-only；旧 overlay 证据不覆盖最终共享文件资格 |

旧 A2 affinity 审计有三个空 cmdline 尾段：两个 `other_or_unknown` 段各9条成员观察，另一个 `MPI_runtime` 段8条，共26条。它们只按同 PID/start_ticks 的前序样本关联，不能声称读取到缺失命令；5,959 条可读 native 数值 worker 样本的 CPU1 结论和旧 `LIMITED` 分类不变。详细区间和生命周期边界见[V4 root audit](outcomes/records/v4_root_audit/index.json)。

本轮没有重读旧 V4 support driver 的完整原始输出，也没有重读 A2_q3 原始场/向量 NPZ；这里只引用已有 tracked V4 audit/index 和 V3 post-PDE audit。上轮主控交付消息/工具输出曾提及“104项 hash 一致”，但没有持久逐项清单；本轮未重建或独立核实这104项，不能将其陈述写成新的外部核验。只读复用了工作站环境记录来核对 mpi4py 的已知路径和 OpenMPI/PETSc 身份；六组 V5 support 原始stdout/resources/summary均单独保留并hash绑定，独立资源复核副本见[compact resource recheck](outcomes/records/v5_root_resource_recheck.json)。

历史 response_v4 和原始 records 保持不变；V4 所称 N1–N6 改进、V3-01–08 裁决与本轮 F1–F4 对应关系按各自历史范围阅读。本回应及验证 compact只记录有限工程整改，不授权恢复模型计算或合并到 master。
