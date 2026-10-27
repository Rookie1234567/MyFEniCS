# Review V16 窄实现准备记录

- 分支：task41extra_phi90_p50x50_g17x20
- Review HEAD：3205450c390d86e574187b833593de2bffe1ff76
- 结果 base：3b2b8f683eebfa8ec86503378913c67a29dae086
- 当前代码工作树在 Review HEAD，初始干净；二者是不同身份，后续分别记录。
- 唯一执行范围：V9→V15 保存向量分解、V14 已存 star 终态与本次输出交叉绑定、新最大 active row 的现有元数据/数值证据缺项清单。
- 用户已在主控对话明确批准 V16 六小时分析窗口：准备通过、源码冻结后直接连续执行。冻结前不创建正式 T0/window、不读取大型 NPY 或运行正式分析；冻结后按 21600/20400/1200 秒建立一次新实例，保留旧账。始终禁止全域数值 owner、GETRS/factor/native 作用、200q/FGMRES；执行者不 commit/push。

## 实现边界

沿用现有 checker、saved-output service、V14 candidate manifest 和 V11 metadata reader。新增 manifest/layout 明确区分旧双列矩阵与四个独立列文件；分块读、只保留受界标量/行元数据，不落盘全长差向量。统计保留动态与冻结分母、trace/port、带符号能量项、top-k/覆盖数、互斥 MPC incident signature 分组。旧 star 绑定必须分别核对 y 与 g、最终 z/correction、j0/j3 和生产顺序；不以 d-only 匹配代替。新最大行仅盘点原始行和完整 incident/现有块，不触发重建。

## 准备状态

Review V16 的本地实现包括 V9/V15 分列输入 reader、流式互斥 row-incidence 累加器及其 same-mesh callback event adapter、分块向量统计，以及旧 attempt01/04 y/g 终态逐列比较器。最大行元数据 reader 要求哈希绑定的 trace-only group codes、原始行映射和完整 incident-cell 列表；原始 permutation（例如 4680）先经过实际值 codebook 映射，不用作 bit 位。attempt01 保留无 state 字段的原身份；attempt04 分开保留 j0/j3。

V14 closeout evidence index 已固定到 SHA-256 `4dbafa42a2387d11a78cf8757a3ce0692f26c0a0d5f38c377937ef49dc0d6e95` 和原窗口 `4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c`。本地 helper 会逐项校验候选/独立 checker/Decimal 补充/receipt 路径与哈希，并只读取 V14 已存小数组；本机未挂载这些历史结果时会 fail closed。V14 的本地 Decimal 通过仍标为局部候选，不会提升全局资格。

尚未完成：把 same-mesh/MPC metadata-only 全域扫描接到 V16 saved-output service，使它逐 cell 喂给流式累加器并只保存紧凑 group/probe 文件。service 输入收集器已改为校验紧凑 group codes、probe、provenance 与哈希绑定的 active-original-row map，不再要求旧式完整 incidence-array 清单；但当前没有 V16 metadata producer route 调用 `incidence_callback` 生成这些文件，因此缺字段时仍会 fail closed，不能执行完整 saved-vector package。实际 V15 active-original-row map、V14 历史数组和 V15 大向量均不在本地挂载；不得用合成数据或占位 PASS 代替。

最后一次资格化检查：项目 WSL activation 下 PETSc 3.19.6 complex128/int32、Open MPI 4.1.6、DOLFINx 0.10.0.post2、SLEPc 3.19.2；`src/test/test_task41_p0_v16_saved_vectors.py` 为 10 passed，相关 Python 文件 `py_compile` 与 `git diff --check` 通过。该测试只验证合成的小型保存包及分组/身份逻辑。

没有真实 V16 window、authorization、accounting 或 T0；没有执行 V16 checker、service、metadata-only mesh scan 或任何数值/owner/FE/native 动作。正式命令仍待准备通过与主控冻结；窗口已获用户明确批准，冻结后直接启动，不重复请示。未 commit/push。

## 最新授权（主控核验）

2026-10-27 用户在主控对话 `01a08a95-afb8-7432-aa08-cefd32b0f4ae` 明确要求：“批准 V16 六小时分析窗口，准备通过、源码冻结后直接连续执行，保留旧账，不重建全域、不启动200q或FGMRES。”执行者已通过 `read_thread` 回读核实。此授权属于 V16，不是旧 V15 的36小时许可。实际 T0 从冻结后首项正式准入/读取开始，不能预填或刷新；当前仍处准备阶段。

## 2026-10-27 V14 saved-array replay 补充

V14 reader 现在可在收到按 attempt 绑定的 replay inputs 时调用 `_task41_p0_v16_replay_v14_star_saved_arrays`，并把回放结果放回对应的 star 记录。直接 fixture 用 `I=3,T=2` 的 attempt01 和 `I=4,T=3` 的 attempt04 覆盖非方形分块；attempt01 仅通过已身份绑定的 V13 cell360 lambda 包计算伴随项，attempt04 明确报告无可复用 lambda。污染 `returned_correction` 会被拒绝。Equation-2 回放单独读取 `b_volume_rhs`，报告 `epsilon = b_full - b_volume - B_alpha`；缺输入时列为缺项，不从 `b_full` 推算并把 epsilon 置零。attempt01 的 j0/j3 分解仍不赋给没有 state 字段的 V14 terminal。

本轮在资格化 activation 下通过 `src/test/test_task41_p0_v16_saved_vectors.py`：`11 passed in 0.68s`；ABI 为 PETSc 3.19.6 complex128/int32、SLEPc 3.19.2、DOLFINx 0.10.0.post2、Open MPI 4.1.6。主控另报告 V16 shell/service selector 定向测试 `3 passed` 和 `bash -n` 通过。此 fixture 不读取旧 NPY，不调用 solver，也不构成历史产物回放结果。

仍待下一阶段：把真实 V14 小型 arrays、star/projection metadata、各自 state inputs、真实 `b_volume_rhs` 的路径/hash 绑定成 replay context，再由 metadata-only service route 生成新 active-row map 与紧凑 group/probe 文件。当前 V16 manifest→V14 reader 的默认调用尚未装配这套真实 context，故仍 fail closed；不得将本轮合成 fixture 描述成真实 V14 数值回放。没有创建窗口、授权、accounting 或 T0；没有运行正式 checker、service、mesh scan、FE/native 运算；未 commit/push。

## 主控接线锚点（防止压缩后重读旧失败）

当前唯一下一步是落地真实默认 replay context、metadata-only service 和 A/B 分阶段保存；用户已批准，准备通过后主控冻结即执行。不要再扫描整个 outcomes 找同名文件。

- attempt01 的**成功 V12 重放报告本地副本**：`outcomes/v12_closeout/attempt03_candidate_replay_report.json`；完整JSON顶层 `v11_selected_trace_candidate_replay`。它不是 `v11_closeout/runs/.../attempt03`（后者是旧失败）。真实远端引用为 `results/.../task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json`，SHA `2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876`。
- 该报告 `cells[].candidate_artifacts` 有 R/S/T/LU/pivots；`columns[].incident_cell_terms[].artifacts.known_trace_local`、`S_action`；同层 `states` 是 list，各项 `state=j0/j3`、`inputs.u_i/n_i/t_c/b_i`。metadata路径/hash在replay顶层，metadata SHA `332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3`。
- attempt04 的V8 full报告由V14 `star_producer_report_path/hash`绑定；已核实 `selected_trace_star_result.local_numeric_cell_identity_and_artifacts` 中按 cell23352/23493和candidate role读取R/S/LU；`selected_trace_star_metadata.cell_artifacts`给真实E/I/T；`selected_trace_star_p3_replay.per_cell_signed_contributions[].roles_and_states`给真实t/u/n/S_action。禁止把列表前两项或reference role冒充目标candidate。
- **独立 b_volume 已存在**，不能写缺失：`outcomes/b0_v3_saved_vector_hash_index_20261019.json` 的141 donor根 `20261019T053402.514018Z`，`task41_b0_recovery_mode_16030_native_volume_rhs.npy` SHA `99aa5d43893764499f31b5168e7dca00f776fba6623d698f43d78e850a15b97e`；48090同名SHA `ec5d487283045efe91c2b3b669dc69ed2a29fb0084a0a7ef91656b1137d2356c`。T0后hash-bound mmap，取真实original行；不得用full-Balpha定义volume而把epsilon归零。
- shell两层V16 selector主控已完成，`src/test/test_task41_v16_service_selector.py` qualified ABI下3 passed，勿重复实现。
- 现有V16 replay定向11 passed；尚需真实默认context而非只可选参数。然后同一受监督入口先生成缺失group/probe metadata并保存，再A先落盘/B执行。禁止循环要求metadata产物在producer运行前存在。
- 主控冻结/提交/同步，执行者不commit/push。无新正式T0，旧V15进程已结束；准备成本另记，不能反复回旧V15监督。

## 主控 service 审查（2026-10-27 08:40 UTC）

- 自动审批曾拒绝 metadata producer 补丁，理由为冻结前不得读取真实数组/建立网格；主控明确将函数定义与正式调用分离，随后仅源码定义补丁已正常落库。此间未运行真实 metadata scan。
- 两层 shell selector 保持 V16 与 V15 等路线互斥；service 允许明确 `metadata_pending=true` 的小型输入清单，将缺失元数据的生成交给冻结后受监督的 worker。原 map 仍须带路径、字节、文件摘要、布局和数组摘要，不能伪称新 group/probe 已存在。
- V16 分析使用原固定窗口的 numeric cutoff；不误用仅 1200 秒的 closeout 额度执行 metadata+分析。旧 saved routes 的 closeout 合同不变。
- V15 accepted checker 的唯一原始路径位于本 Task 的 benchmarks/artifacts；按确切路径与 `927d05cf...36540` 摘要允许只读消费，其余 NPY 仍限本 Task results。没有迁移或重写旧收据。
- 主控 service 合成回归 `src/test/test_task41_v16_service_selector.py`：资格化 complex128/int32 下 **5 passed in 0.35s**；包含真实 collector 的 pending 路径、坏 hash/混合元数据拒绝，以及数值/收口截止选择。bash 语法与 diff 检查通过。
- 工作站 08:28:39 UTC：当前 Task41 分支和 Review HEAD 一致，tracked clean，没有 Task41 进程；当时 MemAvailable=2082135212032 B，磁盘可用=1980447109120 B。宿主既存 swap 使用955535360 B单列，不等于本包 task swap；正式启动仍须实时核验 task swap=0。
- 主控已从旧小 JSON 准备 input manifest 草稿，未打开科学 NPY。V9 run manifest=9395 B，SHA `d3261125ed7584d2b221fba4f5fc10e7aaee6f5b8ee1b1896bf6dd3de3b0491f`。草稿仅在本机/tmp，不是正式分析结果。
- 当前仍无 V16 正式 T0/window、没有新数值 owner或求解；准备成本与正式分析账分开。待默认两 star 上下文、metadata→A先保存→B及断点消费和最小测试闭合后，由主控冻结并直接使用已经批准的窗口。

## 主控最终准备审查（2026-10-27，正式窗口启动前）

已闭合两份 star 的默认保存数据上下文、metadata-only 准入及全域互斥分组、Stage A 先保存及 Stage B 失败后的只读接续。读取器仅共享同一 cell 的张量/LU 身份，不错误要求两列独立内部 RHS 相同；每列 j0/j3、candidate/reference 和原生 volume RHS 仍分别绑定。V15 checker 的原 benchmarks/artifacts 路径仅按确切路径/hash认可，普通文件继续受 results containment 约束。

最后改动后，主控在现有 qualified WSL activation、complex128/int32 下运行两份直接相关回归：`src/test/test_task41_p0_v16_saved_vectors.py`、`src/test/test_task41_v16_service_selector.py`，结果 **20 passed in 1.64s**。早期失败及修正属于准备工程成本，不是科学计算通过；未运行全仓测试。`bash -n scripts/run_case_in_user_service.sh`、`git diff --check` 通过。执行者不提交，由主控冻结。

本机沙箱曾阻止 MPI socket 初始化；使用同一 activation 在允许本机 socket 的执行边界完成检查，未重装/更换环境。定向回归还修复了缺失 `shutil` 导入、相对路径及 accepted checker 的断点接续路径处理；合成测试保留不同 RHS 和负向 hash/角色/状态约束，没有放宽生产检查。

准备阶段尚无正式 V16 T0；用户授权已核实，不再请求确认。准备开始可核实的执行对话 turn 时间为 2026-10-27 06:47:25 UTC；该跨度含编辑、等待、主控审查和测试，不作为 CPU 或正式分析实测时间。正式窗口将从冻结后首项正式准入/读取开始一次登记，保留旧 V15 窗口、账本与 unknown。

正式输入清单草稿 SHA256：`61dadbe8dd9ba3ec0e8fccf47a3e329548636d5a871cf13a6e43733466e0141c`。它只引用旧文件，不重署旧 source/window。实际 prepare 输出合同/命令、T0、账本和运行收据将在正式结果中记录；本准备记录不声明 A/B/C 或原 action 通过。

## 首次正式入口失败与同窗修复

窗口已于 `2026-10-27T09:26:25.501825940Z` 正式冻结；数值截止 `15:06:25.501825940Z`，总截止 `15:26:25.501825940Z`，window SHA256 `3d22e02f713c4a68c79759b2c5cb7cbcec693b7b3277ad98b529838008e38beb`，入口 source `5eed6872243035a6efa6aa0eb662375bd035af8d`。不得刷新。

`myfenics-case-20261027T092655-3402492.service` 在 saved-route guard 前置失败，exit1、MainPID0、ControlGroup为空；未启动分析子进程。主控生成命令误把DAT放在saved selector前，而该已有服务约定selector必须居首；另发现V16诊断scope误复用V15全域策略v2守卫，而实际prepare正确产生旧诊断策略v1。修复命令顺序，并令V16只匹配其准确诊断策略及原scope/window；未放宽科学门或允许full owner。

原日志：`benchmarks/artifacts/user_services/myfenics-case-20261027T092655-3402492.log`。systemd原字段：ExecMainStartTimestampMonotonic=3018212875316、Exit=3018219095710（微秒），相减得到该进程墙钟6.220394秒；CPUUsageNSec=8440974000。MemoryPeak已不可得，保留UNKNOWN；不以CPU时间冒充墙钟，也不把此短进程成本重复加到固定窗口跨度。旧失败日志保留。

本次只复验受影响服务路径：原两层selector/collector/截止测试加真实dispatcher和策略守卫回归，**6 passed in 3.61s**；不重跑无关科学测试。下一attempt仍复用同一授权/T0、旧manifest和全部科学数据。
