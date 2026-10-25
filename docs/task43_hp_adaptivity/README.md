# Task43：面向三维 Maxwell 的自适应 h/p 网格

| 项目 | 本轮权威 |
|---|---|
| 执行分支 | `task43_hp_adaptivity` |
| 建立日期 | 2026-10-22 |
| 源码基线 | `task40para_phi90_mesh_modes_direct@405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 当前状态 | `PARTIAL / CONTROLLED_NEGATIVE`；accepted9/R9冻结，最终空间精度未达；V2三次和V3两次正式dispatch共5/6，A1组2/2、A2组3/3，剩余1次封存。V4的N1–N6和本轮Review V4的F1–F4均为非PDE整改，正式dispatch新增0；25个F1–F3定向案例通过，具体失败重跑和费用见V5 compact。A1_q2因实际入口未接`WorkflowLedger`而在已构网/进入装配后受控停止；A2_q3已进入native workflow并保存primary partial数据，但在7200秒墙钟门后INCOMPLETE，且extra full-active residual未严格下降。没有完整q/R结论或production merge approval |
| 第一目标 | 在新 phi90、50×50 nm 周期、17×20 nm 光栅模型上，建立实际求解验真的局部 h/p 闭环 |
| 第一验证波长 | 13.5 nm；小规模 direct 作数值核验 |
| 后续方向 | 自适应空间的迭代接线；通过前置条件后做一个 0.7 nm 缩比 pilot |

**本任务研究怎样用合适的局部单元尺寸 h 和局部多项式阶次 p 达到所需精度，并核算完整代价。** h 加密把单元变小，适合难以用一个光滑多项式表示的局部结构；p 加密提高单元内部的表达能力，可能更适合光滑区域。两者都会改变全局方程和求解器的成本，必须实际求解才能确认收益。

## 阅读入口

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

V1数值/比较代码及原focused/full pytest使用源码HEAD为 `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`；之后V2/V3入口和报告工具分别按各次source snapshot、测试及compact绑定。V2三次正式尝试在完整端点证据前遇到工程/输入绑定错误；V3的A1_q2实际路线漏接WorkflowLedger、A2_q3进入求解后被性能门停止。两项都没有完成完整新端点资格，且V1旧结果保留各自source/ABI/input身份。当前执行分支 `task43_hp_adaptivity` 等待外部审阅，未获merge approval，未合入master。

V3单次A1_q attempt2已构网并进入装配路径，但在因子分解/求解完成及primary端点留证之前，由于真实A1入口没有创建要求的workflow phase ledger，按主控指令受控停止。原READY文件保留为历史授权记录，不能据此继续派发。V4增加了真实A1入口的mesh-boundary组件测试，但不追溯改变该历史dispatch或READY效力。原始summary分类、资源样本、PID/信号、60源码和47输入哈希及独立终态审核见[A1_q2停止记录](outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json)与[root终态审计](outcomes/records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json)。A2_q3真实建立native ledger并运行到受控停止，最终状态和primary原件审计见[post-PDE记录索引](outcomes/records/v3_root_post_pde_audit/index.json)。V4本轮新增正式dispatch为0，剩余1/6封存；具体工程整改、测试和N5费用边界见[Response V4](response_v4.md)及[V4验证compact](outcomes/records/v4_focused_validation_v1.json)。

## Review V4 的最新执行状态（V5，2026-10-25）

F1–F3有限修复和定向组件验证已完成：A1只有成功取得空输出根后才有权限写失败终态；A2降权 comparison 的原件路径现在指向 sidecar；测试内的联合读取约定覆盖 terminal、进程退出、权限、文件绑定和hash。25个最小案例通过；31项focused首轮30 passed/1 failed，失败来自支持驱动的父子进程拓扑，两个窄恢复节点通过，但没有一次干净的31项全通过运行。六个受监控driver的严格全程CPU1门未通过；wall/RSS/swap和清理通过，具体异常与两次未监控metadata检查失败见[Response V5](response_v5.md)、[V5 validation compact](outcomes/records/v5_focused_validation_v1.json)及[资源复核](outcomes/records/v5_root_resource_recheck.json)。这些fixture不含网格构建、装配或求解，不改变历史A1/A2终态。

原始授权不变：正式dispatch 5/6已耗用，A1 2/2、A2 3/3，最后1槽封存；A1_R/A2_R/B/C、成本campaign、迭代和0.7 nm仍锁定。R9最终精度未达，生产合并未批准。旧A2 resources中实际有三段空cmdline尾段：两个 other_or_unknown各9条观察，另一个 MPI_runtime有8条；仅按同PID/start_ticks前序身份关联，不能补造缺失命令。历史response_v4原字节保留，三段修正见当前Response V5。
