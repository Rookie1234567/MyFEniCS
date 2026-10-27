# Task43 Response V16：用户授权的末节点补验通过，P8 科学阶段未运行

## 当前补验收口（2026-10-27）

T 是工程验证：检查研究入口、身份绑定和留证流程能否正确工作。此前失败来自测试夹具对 phase 文件生命周期的错误假设，不是残差、精度或物理量不达标。用户随后明确回复“授权一次单节点补验”，范围为一个非 PDE 节点，CPU1、8 GiB、270秒工作／300秒含清理；不重跑其他17项，不启动正式求解。

本次把末 fixture 改成可以独立运行：若 phase 不存在，先通过真实首次启动门，再用真实 WorkflowLedger 创建；若已存在，则核当前 worker 身份并保留原文件。后续调用真实 identity reader，固定 PID/start_ticks、tracer 和绝对路径；生产 unused-phase 默认不变。实际本次走“不存在→真实 ledger→同 worker 续接”路径，所有断言完成，phase 前后 SHA256 均为 `7c1fc04475c1f7b7bd4d942668511d8adf55fc0a426213a6e929df9511a1a602`。已存在分支本次未单独重跑。

| 补验项目 | 实际证据／边界 |
|---|---|
| 运行 HEAD | `087ef600a4531c9e65643df787eb71e965f41b65`；base交付 `1fb881f4d6fb836d96c650329529d0d1e18c03c5` |
| 测试字节 | SHA256 `c7ae026e40ac782652b17e87e7399eef541c139ff62900b20caf7ea59e34a236` |
| 唯一节点 | `test_v16_p8_resume_phase_is_exclusive_and_same_worker_bound`，**1 passed**，pytest stdout 5.59 s |
| 费用 | whole **12.767253825906664 s**，包括测试及清理；原两次82.05409320862964 s不退款，三次合计94.8213470345363 s；本次静态／人工操作not_measured |
| 资源 | 树RSS采样同时峰256032768 B，限8589934592 B；task VmSwap0，MPI1，六线程变量1，CPU1 |
| trace／清理 | 6文件1918行、35次getter均[1]、0 setter、0信号；21资源行；launcher/watchdog/worker=0/0/0；全部后代清除 |
| 当前次数 | 原review T2/2保留；用户新增单节点1/1已用。原review支持2/5与用户新增1次分列；不挪用S/C/E |
| 科学阶段 | S/F/C均NOT_RUN；新增正式PDE0、P8槽0/1、正式包络7/9；历史末槽封存 |

主控亲读全部最终 raw trace（重复栈帧仅显示去重，原件未改）、实际 fixture/runtime、XML、资源流、退出与清理。第17资源行出现worker和orted两个已知Z态空cmdline，之后后代为空，按终态退出记录分类，不解释为活进程身份缺失。运行前后源码快照和输入hash无漂移；共享JIT/global cache没有专门监控，仍为NOT_MEASURED。只读收口中误读不存在的 `watchdog/log.txt`，改读已存在的 `watchdog/worker.log`；未重复运行。

其余17个历史通过节点及共同helper相对 `3b9d5e0adb43f69a1fdf339691b26d7eec506686` 逐定义文本相同，只有末fixture改变。资格表述是“17项同字节历史复用＋1项本次实测”，不是一次最终18项批次全通过。该节点验证恢复绑定 helper，**不代表完整E CLI或同worker测试后恢复链已实现／资格化**。

本次按用户限定只完成单节点补验，没有写自动READY或调用S/F/C；原条件科学槽未消耗。五项能力及无merge approval不变。原两次失败与原V16结果v1完整保留，下面为补验授权前的历史交付，不能当作当前补验失败。

证据：[本次机器收口](outcomes/records/v16_single_node_completion_v1.json)、[主控终态](outcomes/records/v16_r9_p8_sources/T_user_completion/terminal_review.json)、[测试字节复用核对](outcomes/records/v16_r9_p8_sources/T_user_completion/test_byte_scope.json)、[用户授权](outcomes/records/v16_r9_p8_sources/user_single_node_authorization.json)。

## 原V16交付历史（两次T停止，保留原失败）

本轮实际完成 P8 研究入口、固定合同和定向测试，并执行两次获授权的 T driver。恢复批次 **17 passed、1 failed**；失败仍在测试 fixture，尚未进入真实 P8 空间或求解。最终 fixture 已静态修正，但没有第三次 T 权限，不能写成通过。按正式 [V15 review §9.3](review_report_v15.md)，S/F/C 未启动，P8 正式槽未消耗。这是工程前门未完成，不是 p 加密的科学负结果。

## 1. 身份与实现范围

| 身份 | 完整值 |
|---|---|
| 仓库／唯一分支 | `Rookie1234567/MyFEniCS` / `task43_hp_adaptivity` |
| canonical worktree | `/home/fenics/Projects/NN-Lab-V2` |
| 正式 V15 review／本轮 base | `f72e1c8d031de7acc374f0806ddac06099c461c4` |
| V15 固定被审交付 | `1290b4f283c01d81f23ba9e1a187458d24bde2af` |
| P8 实现、测试与合同冻结 | `c620c96ef98adac4e1caf05e28dae7744e73a328` |
| T 局部恢复实际 HEAD | `3b9d5e0adb43f69a1fdf339691b26d7eec506686` |

开始时安全 fetch / fast-forward 接收 review，分支、upstream 与 canonical 登记一致；未 reset、clean、强推或覆盖其他工作。仅使用一个 Luna 执行代理；主控审核源码、launch 和最终原件。最终交付 SHA 在提交后单独报告，不把最终文档 SHA 当作测试运行 HEAD。

p 加密在原单元内提高多项式阶次，让同一块空间有更强表达能力，代价是增加未知量。本轮只请求 accepted9/R9 的 global cell 8 / forest root 4，盒子 `[16.5,5,-10]→[33.5,10,0] nm` 从 p5 提至 p6；不切单元，必要实体／周期闭包照实记录。请求不是第十次接受更新。

| 文件／产物 | 本轮实现与资格边界 |
|---|---|
| `round1_candidates.py` | 显式 P8 合同、真实 p 计划 builder／闭包、实际空间后置门、固定 P5 样本点权与 owner-box 核对；T 计划测试通过，真实 S 未运行 |
| `h100_anchor.py` | 明确 `R9_P8` phase、S 来源绑定、primary-only 原向量留证、受限共享 JSON writer 适配及非 official 终态；T 穿过实际 main→observer→共享 writer，昂贵 mesh/solver 用 fixture 替代 |
| `compare_round1_candidate.py` | 固定旧 P5 三场样本读取，只采新 P8 的四场比较模式；T 验证磁盘绑定、混包拒绝、一次采样和 q10 故障保留 q8。fixture 的指标使用合成边界值，不是新科学指标验证 |
| [固定合同](outcomes/records/v16_r9_p8_contract.json) | 绑定 V15 review、固定动作／输入／阈值／路径／预算与 18 节点；合同不自行授予权限 |
| E 恢复 | 只建立互斥用途和同 worker 绑定 helper；未选择恢复阶段，完整 E CLI／同 worker 测试后续接链尚未实现或资格化，不能称 E 已可用 |

未修改共享数学核心、`candidate_checkpoints.py`、`reference_restore.py`、writer 默认、activation、ABI 或 watchdog 默认策略。新增逻辑集中于三个研究入口，但增量仍需外审其复用程度；不能因 fixture 局部通过提升为生产默认。

## 2. 两次 T 的实际结果与修复

| 调用 | 实际运行及结果 | 失败和修复 |
|---|---|---|
| `focused_attempt1`，1/1 | HEAD `c620c96e…`；1 failed、17 NOT_RUN；pytest 12.01 s；whole 20.264135509729385 s | main fixture 的 `active_degree_plan_sha256="degree-plan"` 不符合真实 reader 的 64 位小写 SHA256 格式，在 observer 保存 primary 前被拒绝。改成明确的合成摘要，并使上下文／authority／storage 一致；mesh/DOF 摘要按 fixture 数组计算 |
| `focused_recovery1`，1/1 | HEAD `3b9d5e0a…`；17 passed、1 failed；pytest 54.26 s；whole 61.78995769890025 s | 最后 `test_v16_p8_resume_phase_is_exclusive_and_same_worker_bound` 误用首次启动的 unused-phase 门；此前同 worker 已合法建立 phase，触发 `RuntimeError: V11 watchdog phase file already exists`。其后续断言 NOT_REACHED |
| 最终静态修正 | AST、Ruff F821/F822/F823、diff-check 通过；pytest **NOT_RERUN** | fixture 先调用真实 reader 核当前 PID/start_ticks/tracer/绝对 phase 路径，再显式 allow-existing 并绑定原 identity。没有删除 phase 或放宽生产默认 |

恢复批次只执行修复的首节点和首次 `--maxfail=1` 中断的 17 个未运行节点；没有重复清洗已通过节点。17 项通过涵盖 main/writer/异常 primary 保留、真实 p 计划与后置门、9 个 raw/磁盘/身份正反例、5 个四场比较节点及保存样本 owner/轴断点测试。owner fixture 的 565248 个重复合成点仅用于真实布局 checker，不能当作新 P5 或 P8 场。

**主控责任：** 冻结前预审漏掉了 main fixture 的非法摘要，以及末节点对共享 phase 生命周期的错误假设。两次失败均真实计入 T；不能归因于物理模型、ABI 或时间不足。首次恢复修复后已到真实共享 writer，测试验证异常对象保持、primary hash 不变与 writer finally 恢复。最后同 worker 续接路径仍缺动态通过证据。

测试字节严格区分：

- 首次：`6fa8f1c85d8352a789b1b9c3faea90388b6375ff0635994d212467181e9aad87`。
- 恢复实测：`29b3d134f77f76c952d497a268e89c8727c3173c017be809fea3c2a8b46181f7`。
- 最终静态文件：`80a80fc82f67bebb8b218f5f2f7489b1f37e640da52fb22643b93eb5384ebe6e`，未整文件实测。AST 源码片段核对只改变最后一个 fixture，其他通过节点与共同 helper 同字节；这是有限历史复用，不是最终 18/18。

证据：[首次终态](outcomes/records/v16_r9_p8_sources/T_main/terminal_review.json)、[恢复终态](outcomes/records/v16_r9_p8_sources/T_recovery/terminal_review.json)、[最终字节范围](outcomes/records/v16_r9_p8_sources/final_byte_scope.json)、[末节点静态验证](outcomes/records/v16_r9_p8_sources/focused_recovery1_resume_fixture_static_validation.json)。

## 3. 主控独立终态核验与费用

两次均使用指定 activation，worker-local `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`；实际 complex128/int64、MPI1、MUMPS available、六线程变量 1。该有限运行环境证据不等于生产 ABI 或完整求解资格。

| 项目 | 首次 T | T 恢复 |
|---|---:|---:|
| 进程树 RSS 采样同时峰／8 GiB 上限 | 304947200 B | 519254016 B |
| task VmSwap 采样峰 | 0 B | 0 B |
| 资源行数 | 32 | 94 |
| 最终 trace 文件／行数 | 7 / 2166 | 7 / 3916 |
| sched_setaffinity 调用 | 0 | 0 |
| affinity getter／活进程采样 | 均 `[1]` | 均 `[1]` |
| launcher / watchdog / worker 退出 | 2 / 2 / 1 | 2 / 2 / 1 |
| 相关后代／host PID-start_ticks 残留 | 无 | 无 |

主控读取全部最终 syscall／退出尾行和去除完全重复后的原栈行，逐行核资源流、原始日志/XML、输入／源码快照、实际父链与 TracerPid。两次各一个 `SIGCHLD CLD_EXITED status=0` 对应源码身份读取子进程；无停止信号。空 cmdline 分三类判断：活进程不可缺身份；本轮只出现最终 Z 状态的已知 worker/tracer/orted，随后已 reap；其余未知或不可读身份不得通过。本轮无活进程空 cmdline 或未知 setter。两次运行退出后、静态修复开始前的快照复核均无源码／输入漂移。

RSS 是采样同时进程树峰；不是连续内存高水位。名义间隔 0.25 s 加采样与调度开销，实际间隔见终态 JSON。全局 swap-in/out 增量均 0，单独记录。未传专用 cache path，watchdog 的 cache 稳定标签不能证明共享 JIT/global cache 无变化，该范围 `not_measured`。

本轮两次支持 whole 合计 **82.05409320862964 s**，与 6000 s 支持总上限分开记录；pytest 时间已含其中，不重复相加。初始输入身份只读核对另有实测静态 1.8255486912094057 s。其他人工阅读、编辑、AST/Ruff/bash-n、终态整理与 Git 耗时 `not_measured`，不以工具响应延迟补造总 wall。旧 V15 费用不归零、不混入本轮。

准备期局部错误保留：四次路径／命令查找失败及修正见[原记录](outcomes/records/v16_r9_p8_sources/root_static_notes.jsonl)；一次 Ruff 发现误插入旧 V11 fixture 的 V16 合同片段，已在首次冻结前恢复旧 fixture；主控一次读取不存在的 `watchdog/command.log` 后改读实际 `worker.log`。均未启动额外 driver，不冒称测试通过。

## 4. 科学结果与配额裁决

| 阶段／模型 | 本轮实值 | 分类 |
|---|---|---|
| S P8 真实空间 | FE、trace/interior、carrier 尚未取得 | NOT_RUN；fixture FE=110682 不是 P8 实测 |
| F R9_P8 | primary、A6/full/condensed、612、R/T/Av 均未取得 | NOT_RUN；无正式调用 |
| C 四场共同点 | 新 P8 q8/q10 的 J/G、ΔFE、收益/FE 均未取得 | NOT_RUN；无旧三场重采样 |
| 旧 R9/H8 | FE 110472/116740；H8 ΔJ=0.09051462124265441 < εJ=0.12716416232413652 | 仅复用 V15 已有结果说明背景；不称本轮测量 |
| 本轮动作 | 工程前门未合格 | ACTION_ENDPOINT_NOT_QUALIFIED，不能说 P8 数值失败或没有收益 |

本轮支持调用 **2/5**，其中 T 主／恢复 **2/2 用尽**；S/C/E 各 0。剩余秒数和其他支持槽不能替代第三次 T。P8 正式调用 **0/1**，正式包络 **7/9**，历史封存槽不动。sanity/D3/旧失败槽不恢复。未新建 READY、accepted10 或 transition10。

五项能力仍为：空间 PARTIAL；选择 PARTIAL；精度 NOT_PASSED；同精度全过程成本 NOT_ESTABLISHED；迭代 NOT_RUN / NOT_QUALIFIED。没有 merge approval；无 master 修改或合并。

下一步最小技术任务是审查末节点的静态 fixture 修复及实际同 worker 续接覆盖缺口，明确授予有界补验的唯一命令／root／次数／预算；通过后才可恢复原 S→F→C 条件链。不能把本文件作为第三次 T 或 E 替代授权。P8 专用求解槽仍未使用，不需要也不允许靠重解解决测试问题。

## 5. V15 文案勘误与证据入口

V15-04 已在当前 summary 更正：候选减 Y6_1 的 top/bottom `(0,0,s)`，R9 为 `+4.065061945224269e-6 / −2.1482450713386503e-6`，H8 为 `+3.974547323981614e-6 / −2.1129819847975906e-6`，四个绝对值均超过 `1e-6`；其余610条功率通道在该门内。此前已存在的 `hanging_or_floquet_slave_rows_globally_numbered` 字段修正不归入 V15 八行来源绑定改动。旧 response/review 不回写。

- [机器结果／配额](outcomes/records/v16_r9_p8_results_v1.json)
- [轻量证据目录](outcomes/records/v16_r9_p8_sources/README.md)
- [当前结果](outcomes/summary.md)与[选择性合并边界](outcomes/selective_merge_manifest.md)
- 大原件：`benchmarks/artifacts/task43/v16_p8/`；两次失败 root、实际 launch/source 快照、全部 trace/resources/fixtures 原样保留。
