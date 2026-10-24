# Task43：面向三维 Maxwell 的自适应 h/p 网格

| 项目 | 本轮权威 |
|---|---|
| 执行分支 | `task43_hp_adaptivity` |
| 建立日期 | 2026-10-22 |
| 源码基线 | `task40para_phi90_mesh_modes_direct@405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 当前状态 | `PARTIAL / CONTROLLED_NEGATIVE`；accepted9/R9冻结，最终空间精度未达；V2三次正式诊断尝试均因工程接线/元数据错误提前失败，未形成完整q/R数值结论；V3的A1_q2已dispatch后因A1入口未接入`WorkflowLedger`而受控停止，已发READY仅作为该次dispatch的历史记录，不能授权后续尝试；A2仍未READY、未dispatch |
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

V1数值/比较代码及原focused/full pytest使用源码HEAD为 `3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`；之后的报告工具和V2诊断入口分别由对应compact/source snapshot绑定。V2的A1/A2三次正式尝试在获取完整端点证据前因工程问题失败；随后仅完成profile组件及真实只读输入预检修复，没有新的PDE。旧PDE结果保留各次运行自己的source snapshot/ABI/input身份。执行分支 `task43_hp_adaptivity` 等待最终外部审阅，未获merge approval，未合入master。

V3单次A1_q attempt2已构网并进入装配路径，但在因子分解/求解完成及primary端点留证之前，由于真实A1入口没有创建要求的workflow phase ledger，按主控指令受控停止。原READY文件保留为历史授权记录，不能据此继续派发。原始summary分类、资源样本、PID/信号、60源码和47输入哈希及独立终态审核见[A1_q2停止记录](outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json)与[root终态审计](outcomes/records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json)。A2的native入口仅通过了一个在真实mesh-builder边界前触发sentinel的WorkflowLedger组件测试；它没有构网、求解或消耗正式预算，且不构成A2 READY，详见[组件记录](outcomes/records/a2_native_workflow_ledger_component.json)。
