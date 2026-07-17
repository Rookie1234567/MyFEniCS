# Task033：高阶 Floquet、Hybrid 与等精度阶段性收口

## 当前状态

```text
stage status = review-v5 D0/D1/D2 completed; p3/h7.5 is a qualified equal-accuracy engineering candidate
original Task33 scope = partial; h-adaptivity, buffer, 1 TiB update and full formal closure remain
Stage1 formal source SHA = 6613f94b91ebc77eb50e74086475c67df46236f6
Phase A source SHA = bb830ba5dd74ced30475402bd6bc6d3c1856c630
Phase B measurement SHA = bd7a6023bde7a7c06d456e702af4b7f9f047b3fc
Phase B aggregate SHA = 9ac29db45b387d4590de084710abe2cc38b25ffe
Phase C numerical SHA = b636444b693a932988b6d5d69f7e44e6a8cddb38
Phase C1 implementation and p3 Hybrid closure SHA = 95921ab76e39eb1a7c5b3321b93d36939afb4075
Phase D1 p3/h10 full3D SHA = bb03ad4557e4cf8ada2a7448e9a4e8386ec196b6
Phase D1/D2 audit and p3/h7.5 full3D SHA = 6cb63a5b49ef2db0491ef21a5536eef5f54e1feb
Phase D1 p3/h7.5 Hybrid SHA = 7a7db5874b1eca5e60e5367e0e8bfb3fe0fd0d73
Phase D1 aggregate implementation SHA = df35889
ordinary default = unchanged
```

原任务书 [`task.md`](task.md) 保持不改。Review V5 把剩余当前阶段减缩为 D0
证据收口、D1 fixed-p 等精度、D2 variable-p capability audit；三项现已完成并停止。
原 uniform p/h 20 项矩阵不再机械执行，取而代之的是有决策价值的
`p2/h3 → p3/h10 → conditional p3/h7.5`。p2 graded/adaptive h、interface buffer、
1 TiB 推演和原 21-role formal closure 仍未完成。

## 阶段结论

| 对象 | 结论 | 证据身份 |
|---|---|---|
| 直接 3D FEM p3/p4 Floquet | 通过 | Case090，MPI1/2/4 共 144 次 clean-source PDE |
| p3/p4 QEP component | p3、p4 均资格化 | MPI1 36-shard replay + p3/p4 h3 MPI2/4 positive identity |
| QEP legacy 全阶 aggregate | 未资格化 | p1 与 p2 真实低阶负结果保留；不再由 p4 基旋转阻止 |
| p3/p4 matched trace | p3 基础迹通过；p4 新增四模态近简并块 MPI1/MPI4 正式通过 | 两模态 Phase B + `95921ab...` 四模态补测 |
| Hybrid vs full3D | p2/h5、p2/h3 同阶同网格一致性通过 | 复用 Task032 clean Case080 records |
| p3/h5 Hybrid M funnel | M80/M120/M160 与 augmented/minimal M160 通过 | Phase C 同一 clean SHA、MPI4、零 swap |
| p3 Hybrid vs p3 full3D | 同阶 h5 数值闭合通过 | direct 7.781 GiB、Hybrid 2.618 GiB；最大 R/T/A 差 `1.214e-7` |
| p4 target | 四模态组件通过；full3D/Hybrid 目标求解未启动 | full3D 装配在 12.616 GiB 受控终止；Hybrid 资源上界 42.594 GiB |
| p3/h10 fixed-p equal accuracy | 不通过 | direct 安全完成，但全部规定物理误差劣于 p2/h3 |
| p3/h7.5 fixed-p equal accuracy | 带资格的工程正结果 | 所有物理误差不劣；FE DoF/local-system rows/total rows/factor-NNZ/memory/time 改善 2.571x/2.567x/2.548x/3.557x/1.606x/1.331x |
| variable-p / hp | 当前原生能力未资格化 | fail closed；不做 bespoke constraint，不触发 microfixture；提交 fixed-p zoning 设计 |
| p2 h-adaptive | 未运行 | 等待 D1/D2 新审阅 |
| interface 优化 | 未运行 | 等待 defect/nonuniform-end geometry；暂保留 10/110 nm |
| 1 TiB / 0.7 nm | 未更新 / 未证明 | 等待 measured adaptive compression 和 scalable modal/QEP 证据 |

## 结果入口

- [阶段总结](outcomes/summary.md)
- [高阶 3D Floquet 结果](outcomes/high_order_floquet_results.md)
- [QEP 阶次研究](outcomes/qep_order_study.md)
- [QEP tracking 诊断](outcomes/qep_tracking_diagnostic.md)
- [Phase B matching-interface 迹组件](outcomes/matched_trace_phaseB.md)
- [Phase C p3/h5 候选级 Gate 与 Hybrid 结果](outcomes/p3_h5_phaseC.md)
- [Hybrid 与直接 3D FEM 对比](outcomes/hybrid_vs_full3d_summary.md)
- [Phase D1 精简等精度结果](outcomes/reduced_equal_accuracy_phaseD.md)
- [Phase D2 variable-p/hp capability 与 zoning 设计](outcomes/variable_p_hp_capability.md)
- [Task33 全任务与全文档完成矩阵](outcomes/task33_completion_matrix.md)
- [负结果与延期边界](outcomes/negative_results.md)
- [原阶段回复](response_v1.md)
- [对审阅报告的回复](response_v2.md)
- [对 Phase A 复审及 Phase B 执行要求的回复](response_v3.md)
- [对 Phase B 复审及 Phase C 执行要求的回复](response_v4.md)
- [对 review v4 后续执行与 p3/p4 结果的回复](response_v5.md)
- [对 review v5 D0/D1/D2 的回复](response_v6.md)
- [轻量阶段证据记录](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage1_high_order/stage_summary.json)
- [Phase B 独立轻量聚合](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/phaseB_summary.json)
- [Phase C p3/h5 轻量摘要](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC_summary.json)
- [p3/h5 同阶 full3D 闭合摘要](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/full3d_closure_summary.json)
- [p4 四模态迹摘要](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/p4_four_mode_summary.json)
- [p4/h5 目标装配负校准](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage4_p4_h5/calibration_summary.json)
- [Review V5 减缩等精度聚合](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json)
- [variable-p capability 正式审计](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/variable_p_capability_audit.json)

完整 21-role formal manifest 尚未生成；
`records/formal_evidence_manifest_NOT_RUN.json` 继续代表原 Task33 完整范围未闭合。
该文件不被本轮 reduced summary 覆盖。whole-branch merge 仍待新的独立审阅批准。
