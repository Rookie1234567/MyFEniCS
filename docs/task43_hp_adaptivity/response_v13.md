# Response V13：S1 支持验证完成；D1 性能受控停止；P2R 未运行

本轮按 [V12 review §9](review_report_v12.md) 的有限范围完成代码与定向 fixture 修正，并在冻结源码上完成一次支持验证 S1。S1 的 12/12 节点通过，只说明指定研究入口和合成 fixture 的有限工程检查通过。随后唯一 D1 在空间约束构造路径上到达 540 秒工作停止门，分类为 `PERFORMANCE_CONTROLLED_STOP`；未完成实际独立自由度（FE）审计；本支持阶段不装配 PDE 矩阵，也没有新模型求解或正式 PDE 结果。P2R 因缺少 1740 秒内完成剩余工作的保守预算依据而未获放行。

空间构造要把细分单元之间的电磁场连续条件落实为约束，再计算真正独立的未知量数（FE），因此194个网格叶单元不能替代自由度审计。本轮保存数组诊断检查提高积分阶次 q 后已有场的变化；它不重新求解。分阶段 checkpoint 则让已经算出的结果在后续失败时仍可查读。

## 范围、身份与 V12 §9 修复

仓库 `Rookie1234567/MyFEniCS`，唯一分支 `task43_hp_adaptivity`。执行 review 为 `37f3376be410657fbaec86b0412086745419c506`，其固定被审交付为 `30333c5705d6a9ef64ba22d0d7030dd63a9c763d`；原代码基线为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。

修改限于 review §9.1 指定的 `round1_candidates.py`、`h100_anchor.py` 和既有 V11 scientific restart 测试；未改共享数值核心、激活脚本、ABI、watchdog/profile/cache 策略或历史合同。实现提交为 `7546c7bdb91b2c07c0344c41d418e8a0808ea6a6`，S1 在该 HEAD 执行；随后没有代码变化，D1 的源码 HEAD 为 `d8cba4f1377b526101c37213d5bc8e88db23effc`。测试文件最终 SHA256 为 `8516a90dd558e6c2ec4d9329da26fa2aba5bdb0b253e5ac3c6838dbbda5f38ba`。V11 科学合同与 V12 recovery manifest 均保持原字节。

| Review §9 项 | 本轮结果 | 证据范围 |
|---|---|---|
| V12-01 / §9.1 observer 返回类型与委托 | 区分 degree-map entity cells 与无 `degree_map` 的 cell-trace map；原函数只委托一次、保留返回对象/错误和别名缓存属性 | S1 中真实数据类 fixture 通过；D1 实际 entity-map 返回并留有阶段记录，但 cell-trace map 未完成返回 |
| V12-03 / §9.1 A2 子阶段持久化 | raw、modal、q8、q10 完成后可分别原子保存；后续故障记录已完成子项与原异常 | S1 覆盖 helper 和真实 main sink 的成功、q10 故障路径；D1 确实在 space authority 前保存并由 root 检查四个旧 A2 数组阶段 checkpoint |
| V12-02 / §9.1 raw packet 约束 | 拒绝非零齐次 modal RHS；同场 RHS、solution、residual 与恢复 storage 绑定检查保持原公式与容差 | S1 的合法包与六类语义反例穿过 checker/reader；不代表旧 A2 端点重新资格化 |
| V12-04 / §9.1–9.3 实际读取及门 | 比较路径的成功尾段、P2 joined-source 拒绝和 main sentinel 按最终源码验证 | S1 全部 12 个展开节点通过；不代表 P2 空间门或后续科学门通过 |

S1包含并通过V12当时尚未运行的两个受影响节点：`test_compare_v11_union_reads_bound_p2_p4_inputs_and_preserves_q8[None]`和`test_v12_p2_joined_source_binding_rejects_root_terminal_failure`。这关闭了“最终两断言未验证”这一V12时点状态，但不改变P2R预算前置或后续阶段资格。

## S1：有限支持工程验证

| 项目 | 实测值 | 分类与边界 |
|---|---:|---|
| 测试节点 | 12 passed / 12；六个 selector 范围，展开节点上限 16，`--maxfail=1` | `PASS_LIMITED_SUPPORT_ENGINEERING`；focused selector 验证，不是全文件、全仓或 CI 结论 |
| watchdog whole wall | 27.02263388223946 s | 单次 S1 支持调用 |
| 进程树 RSS 采样峰 | 313,585,664 B | 同时进程树采样值，不是连续峰；swap 0 B，清理完成 |
| worker/watchdog/launcher exit | 0 / 0 / 0 | 终态由主控审阅；没有 formal dispatch |
| source/test | HEAD `7546c7bdb91b2c07c0344c41d418e8a0808ea6a6`；test SHA 如上 | 原始 JUnit 和 closeout 链接见机器记录 |

## D1：真实空间 authority 路径的性能受控停止

D1 按 **540 s 工作停止门、600 s whole 限值**执行。watchdog 在工作停止门向 worker 整个子树发出 SIGTERM；受控停止后的 whole 时间为 `541.9988412610255 s`。终态为 `PERFORMANCE_CONTROLLED_STOP`，不是科学门失败或数学反例。实际独立 FE 未取得（null）；本支持阶段不装配 PDE 矩阵，实际 rows/NNZ 未测，正式装配阶段未运行；停止前尚未返回 cell-trace constraint map，也没有完成 reduction-authority、`_audit_plan` 闭包/FE 检查或正式候选输出。

| D1 观察 | 记录值 | 解释边界 |
|---|---:|---|
| RSS / swap | 1,302,609,920 B / 0 B | 769 个资源样本的同时进程树 RSS 峰；PSS 按 profile 禁用；swap 是进程树采样 |
| trace / affinity | 6 个文件、795 行；19 getter，全部 mask `[1]`；0 setter | trace 从受控观察范围开始；不把它外推为进程全生命周期以外的事实 |
| 输入与清理 | 51 source checks、38 input checks 均未变；descendants cleared，剩余 PID 0 | worker/watchdog/launcher exit `-15 / 2 / 2`，对应受控 SIGTERM 与 wrapper 终态；不是额外 PDE 失败 |
| 已到达的空间工作 | parent identity、plan、mesh/reduction入口；degree/entity map 摘要；实际 cell-map 内开始 reference-space 冷构造 | cell-map 调用处于 `IN_PROGRESS_AT_STOP`；实际最终 map、authority 和 FE 未返回 |

769条资源样本的相邻间隔约0.3796–1.0291 s；配置周期为0.25 s，额外时间来自采样和调度开销，故不是严格每0.25 s一次。末次采样CPU累计读数（终态总CPU的下界）worker/tracer/watchdog分别为363.23/1.06/175.85 s；sampler wall/CPU为129.741/64.847 s。它们是嵌套在D1 whole期间的过程计数/观测开销，不与541.9988 s相加，也不作为独立阶段wall。

### D1 对旧 A2 保存数组的有限诊断

这些数据来自旧 A2 已保存 primary/checkpoints。D1 没有重新求解、重采样、积分或应用算子；它们不改变旧端点 `INCOMPLETE_NOT_QUALIFIED`。

| 已保存量 | D1 检查值 | 冻结门 / 结果 |
|---|---:|---|
| 独立原方程 A6 / native effective RHS | `3.078522812304335e-10` | `≤1e-8`，通过 |
| full-active 零从属 carrier + modal Euclidean residual | `1.1972486317982494e-11` | `≤1e-8`，通过；不是变量 p Gram norm |
| returned condensed residual / returned RHS | `3.0440529386035694e-12` | `≤1e-9`，通过 |
| normal correction history | `2.2945939789534043e-9 → 3.0440529386035694e-12` | 降低；旧 packet 不含独立 normal RHS/solution，因此只核 returned 向量与两份 `b−Ax` 快照 |
| modal 与功率 | 612 通道；边界幅向量差 L2 `8.471718620104984e-11`；单通道最大功率差 `4.5076775645469525e-11` | 对 Y6_1 的已存数组比较；未重新解算 |
| q8 / q10 场 | 516,096 / 1,008,000 点；体积分别 `349999.9999999999` / `349999.9999999998 nm³`；最大带入射尺度地板相对量约 `6.0443e-11` | E/H/G 五项保存场 gate 均通过；旧保存数组复算 |
| `A_volume` | `0.6915175267406917` | 读取历史材料积分值，未重积分 |

旧 A2 检查细节、向量身份和四个 raw/modal/q8/q10 checkpoint hash 见 [root A2 检查记录](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/A2_key_values_and_root_checks.json) 及 [机器结果记录](outcomes/records/v13_minimal_completion_and_scientific_results_v1.json)。

主控在两次 workflow 完全退出后，亲读 S1 的10份 trace（2988行）及 D1 的6份 trace（795行），检查全部调用行、退出尾段与各唯一栈帧；并复核37/769条资源行、PID/PPID/start_ticks、worker/tracer/watchdog父链、实际CPU1及单线程环境、退出码与子进程清理。S1的4个SIGCHLD包含预期fixture子进程exit 7；D1的SIGTERM来自已绑定watchdog，不是未知外部终止。主控还读取原始A2四阶段实值及hash，核对51项source与38项input绑定；未将代理的PASS标签直接当作结论。PSS、连续内存峰值与完整共享JIT cache状态仍未测，详见closeout。

## 为什么没有运行 P2R

**D1 的 540 s 是 D1 工作停止门；P2R 要求 1740 s 工作预算、1800 s whole 限值。** 两者不能混用。D1 的阶段日志显示实际输入有 25 个 unique degree keys、194 个 cell multiplicity：7 个冷 key 完整返回、1 个处于进行中、17 个未开始，因此 18 个未完成。一个 cold mixed-degree reference-space 调用耗时约 59.1 s，其他已返回冷 key 也有明显差异；已见样本不是未见 key 的上界。

主控预算裁决为 `NOT_AUTHORIZED_PRECONDITION_NOT_ESTABLISHED`：缺少 18 个未完成冷 key、cell-map 的实体变换/rank/expansion 和全局 audit 尾段、reduction authority 与 `_audit_plan` 闭包/FE gate，以及空间阶段后的检查和输出持久化费用证据。新 worker 还需重复冷启动前缀；不能假设 D1 的进程内 warm cache 可以复用。因而在 1740 s 内的保守总工作界为 null。不得用均值、单个 warm hit、较低 RSS 或把 D1 限时加倍来代替上界，也不据此宣称模型数学上无效或不可行。

| 后续阶段 | 状态 | 理由 |
|---|---|---|
| P2R | `NOT_RUN_CONSERVATIVE_BUDGET_UNPROVEN`；0/1 | 不能证明实际 worker work ≤1740 s，whole 上限 1800 s |
| P3 A1_q3 | `NOT_RUN_P2_GATE_NOT_PASSED` | 无真实 P2 space/FE gate |
| P4 R9_H8 | `NOT_RUN_P2_AND_P3_NOT_PASSED` | 前置未完成 |
| P5 union | `NOT_RUN_P4_NOT_REACHED` | 前置未完成 |

P2R 的机器裁决和工作量摘录见 [budget decision](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/p2r_budget_decision.json) 与 [authority work profile](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/authority_work_profile.json)。P2R/P3/P4/P5各自的唯一输出root均不存在，launch次数为0。

## 费用、错误账与科学状态

V13 的两次受控调用 S1+D1 whole-watchdog wall 合计 `569.021475143265 s`。加上 V12 保留的两次失败支持运行 `49.582441974431276 s`，累计 `618.6039171176963 s`；旧失败未改写，也未重复计入本轮。shell timestamp envelope 的范围为 S1 `33.475959 s`、D1 `550.658259 s`，合计 `584.134218 s`；它们与 watchdog 单调时钟记录有重叠，不能相加。各自比 watchdog whole 多出的约 `6.4533 s` / `8.6594 s` 包括 watchdog 外薄 shell 工作，来自不同计时边界，不是精确独立阶段计时。最终文档校验前的实测静态小计 `9.170545399932646 s`；一次标准库文档/证据校验另计 `0.31329149194061756 s`（30项检查、无错误），合计 `9.483836891873263 s`。后续仅补此费用登记及Git操作，未计时项单列，不补造总wall。

本轮也有有限静态/记账错误，均已由主控纠正并保留，不影响 dispatch：

- 执行 subagent 曾把 D1 的 540 s 表述成 P2R 预算，主控已拒绝该表述并订正；实际是 D1 540/600，P2R 为 1740/1800。
- 主控早期进度摘录把 unique key 写成 24；完整最终 work profile 为 25 keys、194 cells，状态为 7 完成、1 进行中、17 未开始。
- post-run broad fixture extraction 因一个旧 schema mock 缺少 `substage_checkpoint_refs` 而报 `KeyError`；随后收窄到本轮实际 main fixture，并从真实 checkpoint 文件检查内容，没有重跑测试。
- 启动前读取误写的 `src/adaptivity/hcurl_broken_trace.py` 路径以 exit 2 结束，随后只读正确文件；fixture 的参数/数组目标/断言及语法问题均在唯一 S1 前修正，详见 [主控静态预审](outcomes/records/v13_completion_sources/preparation/root_prelaunch_review.json)。
- 最后暂存后全差异格式检查 exit 2：D1 的原始 `launch_context.txt` 第9行 argv 有尾空格，已逐字节核对与 ignored 原件一致，保留原字节作为明确格式例外；其余暂存文件单独检查。不把原始记录修剪成不同hash，未重跑测试。见 [格式例外记录](outcomes/records/v13_completion_sources/preparation/staged_format_exception.json)。
- 对尚未创建的输出目录执行过一次 `ls`，exit 2；属于 preparation 记录/路径检查，不是 worker、测试或 D1 失败。

本轮是 2 个 driver（S1 与 D1）；与 V12 两次失败支持运行合计为扩展 recovery envelope 4/5，P2R 0/1。P3/P4/P5 均未运行。旧 formal 额度仍 5/6、末槽封存；扩展正式总量仍 5/8，新 formal 为 0。五项科学状态不变：空间/选择 `PARTIAL`，最终精度 `NOT_PASSED`，同精度全过程成本 `NOT_ESTABLISHED`，迭代 `NOT_RUN / NOT_QUALIFIED`，0.7 nm 未运行。accepted9/R9 是最后接受状态；R10 仍为未接受诊断。无 READY、生产资格、CI 声明或 merge approval。

机器收口汇总见 [V13 结果记录](outcomes/records/v13_minimal_completion_and_scientific_results_v1.json)、[S1 closeout](outcomes/records/v13_completion_sources/support/s1_completion_attempt1/root_closeout.json) 和 [D1 closeout](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/root_closeout.json)。最小下一步是取得 18 个未完成 cold keys 与 cell-map 尾段的可审保守费用依据，或另行授权一个严格保持数学行为的窄成本修复；本轮不含继续运行或合并授权。
