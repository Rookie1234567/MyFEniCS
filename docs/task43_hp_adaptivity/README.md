# Task43：面向三维 Maxwell 的自适应 h/p 网格

| 项目 | 本轮权威 |
|---|---|
| 执行分支 | `task43_hp_adaptivity` |
| 建立日期 | 2026-10-22 |
| 源码基线 | `task40para_phi90_mesh_modes_direct@405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 当前状态 | `PARTIAL / CONTROLLED_NEGATIVE`；V13 S1 有限支持验证 12/12 通过，D1 在 540 s 工作门受控停止，实际 space authority/FE audit 未返回；P2R 因 1740 s 工作预算缺少保守上界而 `NOT_RUN`，P3/P4/P5 也未运行。旧正式5/6及封存末槽、扩展正式5/8、五项科学状态不变，新正式dispatch为0；无READY、生产资格或合并许可。详见[Response V13](response_v13.md)与[V13机器收口](outcomes/records/v13_minimal_completion_and_scientific_results_v1.json) |
| 第一目标 | 在新 phi90、50×50 nm 周期、17×20 nm 光栅模型上，建立实际求解验真的局部 h/p 闭环 |
| 第一验证波长 | 13.5 nm；小规模 direct 作数值核验 |
| 后续方向 | 自适应空间的迭代接线；通过前置条件后做一个 0.7 nm 缩比 pilot |

**本任务研究怎样用合适的局部单元尺寸 h 和局部多项式阶次 p 达到所需精度，并核算完整代价。** h 加密把单元变小，适合难以用一个光滑多项式表示的局部结构；p 加密提高单元内部的表达能力，可能更适合光滑区域。两者都会改变全局方程和求解器的成本，必须实际求解才能确认收益。

## 阅读入口

**当前研究范围沿用[V11正式补充任务书](supplement_v11_scientific_restart.md)，本轮执行权威为[V12正式review第9节](review_report_v12.md)，V13完成状态按[Response V13](response_v13.md)记录。**S1 的12个定向节点通过有限工程验证；D1 在真实 space-authority 路径上受控停止，P2R 未获放行，因为剩余冷构造及 authority 尾段没有1740秒内可审的保守费用界。后续阶段和正式计算均未运行。历史合同、初始 manifest、V12 失败和全部旧科学状态均保留；本状态不授予后续运行或合并许可。

上一轮[V10正式review](review_report_v10.md)已验收有限静态整改；原执行依据为[正式V9 review第9节](review_report_v9.md)，V10当轮未新增运行。其交付见[Response V10](response_v10.md)、[静态纠正记录](outcomes/records/v10_static_evidence_correction_v1.json)及[纠正版依赖表](outcomes/records/v10_static_evidence_sources/corrected/direct_needed_edge_map_corrected.json)。原V9派生表保留原字节；三个边界的12个字段更正在新文件中。V11/V12/V13有限工程证据与受控停止见[Response V11](response_v11.md)、[Response V12](response_v12.md)和[Response V13](response_v13.md)；没有新增正式 PDE 结果或合并许可。

1. [task.md](task.md)：科学问题、模型、阶段、接受规则和验收合同。
2. [AGENTS.md](AGENTS.md)：本目录执行规则；任务书与工作站实施之间的边界。
3. [baseline_audit.md](baseline_audit.md)：主线判定、两条 NN 路线、旧 hp 与 dot 的固定 SHA 证据。
4. [codex_handoff.md](codex_handoff.md)：工作站接入与可直接交给 Codex 的指令。
5. [branch_provenance.json](branch_provenance.json)：建分支来源与立项时尚未运行状态。

## 与其他研究线的关系

- `task40para` 是本次新几何、直接解和方向网格对照的基线。
- `task41extra_phi90_p50x50_g17x20` 继续代表 0.7 nm 迭代求解研究；不与 Task43 整分支合并。
- `task42_neural_coarse_inverse` 与 `task42extra_feinn_5nm` 的当前研究可暂停投入；本次建立 Task43 不删除或改写它们的远端历史。
- 旧 Task35d/e 数值核心按函数与依赖选择性复用；dot 的新 hp 报告是设计证据，其中未同步的外部源码不冒充可直接继承的实现。

## 最终结果入口

九次按冻结规则接受的 p-up 将最后接受场推进到 R9（110,472 FE），但 top/bottom `(0,0,s)` 两个功率通道仍超过 `1e-6` 精度限值；R10自然到180格全p6、118,800 FE，G改善小于冻结参考噪声，拒绝且没有transition10。真实600叶局部h1已完成数值求解和全场比较，但同样未达到最终空间精度。用户要求的相近精度下更少独立未知量尚未证明；任务书还要求比较同精度全过程成本，但不要求成本必须获胜。

停止选择后，三个恢复参考与R9/R10共同用q8/q10进行九组方向明确的全场比较；结果已由root从原始数组独立审计，未反馈选择或增加PDE。全仓 `pytest -q` 已真实尝试，但在collection阶段发生1次skip和8个collection errors，测试体执行0项；负结果与其SLEPc/忽略artifact来源保留。没有CI通过声明。

- [结果与统一模型表](outcomes/summary.md)
- [V13执行回应](response_v13.md)；[V13机器结果与预算裁决](outcomes/records/v13_minimal_completion_and_scientific_results_v1.json)
- [V13 S1 closeout](outcomes/records/v13_completion_sources/support/s1_completion_attempt1/root_closeout.json)；[D1 closeout](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/root_closeout.json)；[P2R预算裁决](outcomes/records/v13_completion_sources/support/authority_profile_attempt1/p2r_budget_decision.json)
- [V12执行回应](response_v12.md)；[V12 recovery/science机器记录](outcomes/records/v12_recovery_and_scientific_results_v1.json)
- [V12 S1 closeout](outcomes/records/v12_recovery_sources/support/focused_attempt1/root_closeout.json)；[V12窄恢复 closeout](outcomes/records/v12_recovery_sources/support/focused_recovery1/root_closeout.json)
- [V11收口回应](response_v11.md)；[V11科学结果机器记录](outcomes/records/v11_scientific_results_v1.json)
- [执行回应](response_v1.md)
- [V2最终执行回应](response_v2.md)
- [依赖组选择性合并清单](outcomes/selective_merge_manifest.md)
- [后验六场比较compact](outcomes/records/post_selection_existing_fields_validation_v1.json)
- [最终定向/全仓测试compact](outcomes/records/final_test_attempts_v1.json)
- [V2正式尝试与元数据修复compact](outcomes/records/v2_formal_attempts_and_profile_fix_v1.json)
- [V2最终文档与原件合同验证compact](outcomes/records/v2_closeout_validation_v1.json)
- [V3诊断计划与冻结合同](diagnostic_plan_v3.md)；[当前有限验证索引](outcomes/records/diagnostic_plan_v3_final_validation.json)
- [V3执行回应](response_v3.md)；[V3两次formal dispatch/终态与资源compact](outcomes/records/v3_formal_diagnostic_closeout_v1.json)
- [A2_q3实际watchdog/worker命令摘录](outcomes/records/A2_q3_actual_launch_process_excerpt_v1.json)；[primary原向量/场样本独立复核](outcomes/records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json)
- [A1_q2受控停止原件](outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json)；[A2_q3历史READY](outcomes/records/v3_root_ready_A2_q_attempt3.json)；[A2_q3实际终态审计](outcomes/records/v3_root_post_pde_audit/A2_q3_terminal_audit.json)
- [V3 G0–G3审计副本与支持费用索引](outcomes/records/v3_root_pre_pde_audit/index.json)
- [V4执行回应：N1–N6有限整改](response_v4.md)；[V4最终focused验证索引](outcomes/records/v4_focused_validation_v1.json)
- [V4旧A2 affinity区间与生命周期费用审计](outcomes/records/v4_root_audit/index.json)
- [V5执行回应：Review V4 的 F1–F4有限整改](response_v5.md)；[V5验证与支持费用compact](outcomes/records/v5_focused_validation_v1.json)
- [V6执行回应：affinity导入诊断与S2 helper静态修正](response_v6.md)；[V6支持compact](outcomes/records/v6_affinity_support_closeout_v1.json)
- [V7执行回应：完整setter trace、静态装载身份与未执行的OB1假设](response_v7.md)；[204条trace事件索引](outcomes/records/v7_affinity_trace_event_inventory_v1.json)、[source/ELF审计](outcomes/records/v7_affinity_source_loader_audit_v1.json)
- [V8执行回应：D3准备未通过顺序门，未派发](response_v8.md)；[V7 D3准备原件与收口记录](outcomes/records/v8_d3_preparation_closeout_v1.json)
- [V9执行回应：D3有限工程复核](response_v9.md)；[D3 resume closeout](outcomes/records/v9_d3_resume_closeout_v1.json)；[实际脚本和root审计字节归档](outcomes/records/v9_d3_sources/README.md)

## V9 历史工程状态：有限工程终态复核完成；无科学或生产资格

V8 review的前瞻许可用于恢复原来未消耗的唯一D3支持运行。V9完成S1静态准备、S2固定字节采用、19项stdlib/AST synthetic sanity；之后对8项源码做hash核对并保存不可后验替换的`prelaunch_snapshot`，再启动唯一D3。root终态审计为`PASS_LIMITED_ENGINEERING`，只覆盖固定启动/import/ABI/affinity链与20个S2 fixture字节：20 passed/0.91s，watchdog whole wall 8.763570327777416s，13个采样的同时进程树RSS峰180887552B、task VmSwap峰0、全局swap增量0/0页，清理完成。没有构网、装配、求解或PDE；审计不授予科学、生产、CI或merge资格。D3额度已耗、无重试；正式额度仍5/6，最后1槽封存，五项科学能力和所有下游锁定不变。V8准备顺序失败与复制失败仍保留，不回写为未发生。见[Response V9](response_v9.md)、[D3 closeout](outcomes/records/v9_d3_resume_closeout_v1.json)与[脚本及轻量证据归档](outcomes/records/v9_d3_sources/README.md)。

V1数值/比较代码及原focused/full pytest使用源码HEAD为 `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`；之后V2/V3入口和报告工具分别按各次source snapshot、测试及compact绑定。V2三次正式尝试在完整端点证据前遇到工程/输入绑定错误；V3的A1_q2实际路线漏接WorkflowLedger、A2_q3进入求解后被性能门停止。两项都没有完成完整新端点资格，且V1旧结果保留各自source/ABI/input身份。上述为历史状态；当前有限执行范围见V11补充任务书，未获merge approval，未合入master。

V3单次A1_q attempt2已构网并进入装配路径，但在因子分解/求解完成及primary端点留证之前，由于真实A1入口没有创建要求的workflow phase ledger，按主控指令受控停止。原READY文件保留为历史授权记录，不能据此继续派发。V4增加了真实A1入口的mesh-boundary组件测试，但不追溯改变该历史dispatch或READY效力。原始summary分类、资源样本、PID/信号、60源码和47输入哈希及独立终态审核见[A1_q2停止记录](outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json)与[root终态审计](outcomes/records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json)。A2_q3真实建立native ledger并运行到受控停止，最终状态和primary原件审计见[post-PDE记录索引](outcomes/records/v3_root_post_pde_audit/index.json)。V4本轮新增正式dispatch为0，剩余1/6封存；具体工程整改、测试和N5费用边界见[Response V4](response_v4.md)及[V4验证compact](outcomes/records/v4_focused_validation_v1.json)。

## Review V4 的历史执行状态（V5阶段快照，2026-10-25）

F1–F3有限修复和定向组件验证已完成：A1只有成功取得空输出根后才有权限写失败终态；A2降权 comparison 的原件路径现在指向 sidecar；测试内的联合读取约定覆盖 terminal、进程退出、权限、文件绑定和hash。25个最小案例通过；31项focused首轮30 passed/1 failed，失败来自支持驱动的父子进程拓扑，两个窄恢复节点通过，但没有一次干净的31项全通过运行。六个受监控driver的严格全程CPU1门未通过；wall/RSS/swap和清理通过，具体异常与两次未监控metadata检查失败见[Response V5](response_v5.md)、[V5 validation compact](outcomes/records/v5_focused_validation_v1.json)及[资源复核](outcomes/records/v5_root_resource_recheck.json)。这些fixture不含网格构建、装配或求解，不改变历史A1/A2终态。

原始授权不变：正式dispatch 5/6已耗用，A1 2/2、A2 3/3，最后1槽封存；A1_R/A2_R/B/C、成本campaign、迭代和0.7 nm仍锁定。R9最终精度未达，生产合并未批准。旧A2 resources中实际有三段空cmdline尾段：两个 other_or_unknown各9条观察，另一个 MPI_runtime有8条；仅按同PID/start_ticks前序身份关联，不能补造缺失命令。历史response_v4原字节保留，三段修正见当前Response V5。

## Review V7 §9历史收口（V8准备阶段停止）

V7原审阅给出的唯一D3支持许可以先完成§9.2静态核查为条件。本轮候选在输入/ELF核查完成前已被生成，随后首次机械patch/copy以exit 1结束。主控裁决准备不合格并停止；不把候选期望hash相同追认为顺序门通过。候选留在`/tmp/task43_v7_d3_proposal/`仅供审阅；sanity、native import、ABI、固定20项测试、D3 driver和正式PDE均未运行。V7要求的静态项也未全部完成：15个ELF对象有读取记录，但插件直接依赖闭包及完整输入集未完成。费用与原命令/输出见[Response V8](response_v8.md)和[准备收口记录](outcomes/records/v8_d3_preparation_closeout_v1.json)。本次没有merge approval。

## Review V6 §9历史收口（V7，只读证据与候选文档）

V7完整索引了D1/D2的204条成功affinity setter并只读核对八个V5/V6 support根、保存的启动器与当前安装ELF身份。D1为hwloc196、libinfinipath2、libpsm2 2；D2禁用hwloc x86组件后仍有两类网络库setter各2次。V6主控在D2前漏分类D1已有网络库调用，监督遗漏已明示。旧V6中的 `source_snapshot_all_match_manifest=false` 在本轮规范化路径键后8/8匹配；原比较生成器未留存，未推断原标志的确切成因。候选只是在D2 worker shell中追加 `OMPI_MCA_pml=ob1` 的静态diff；它没有创建或运行，也不证明CM组件或PSM setter会消失。

本轮没有运行driver、导入、pytest、网格或PDE；正式预算和V6 support负结果不变。R9仍为最后接受状态，最后1个formal槽封存，未获READY或production merge approval。详情见[Response V7](response_v7.md)与[204条trace/ELF记录](outcomes/records/v7_affinity_trace_event_inventory_v1.json)、[装载与diff记录](outcomes/records/v7_affinity_source_loader_audit_v1.json)。

## Review V5 §9历史收口（V6）

V6阶段只修正测试内联合读取helper的身份存在性约束并核对旧support affinity上下文；S2计划的20个案例未运行。两个受限driver在首个显式`dolfinx`导入返回后的`native_import_complete`检查点停止；导入过程已触发成功setter偏离CPU1，完整MPI/PETSc ABI preflight为`NOT_REACHED`，pytest为`NOT_RUN`。D1/D2 whole-watchdog合计`20.736750496551394s`，task VmSwap采样峰为0 B，global `pswpin/pswpout`增量均为0页；RSS/时限/清理满足支持门，但严格CPU1不通过。主控D2前漏分类了D1中已存在的两类网络库setter（合计4次）；该审查遗漏及两次driver的原栈证据已保留。无新正式dispatch/PDE/READY，额度仍5/6，最后一槽封存；科学结论与production资格不变。

详见[Response V6](response_v6.md)、[V6 S1只读索引](outcomes/records/v6_s1_v5_support_affinity_context_v1.json)和[V6 affinity support compact](outcomes/records/v6_affinity_support_closeout_v1.json)。该段为V6阶段历史记录；V9历史工程状态见上文，当前执行范围以顶部V11入口为准。
