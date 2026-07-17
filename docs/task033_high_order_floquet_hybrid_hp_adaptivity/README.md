# Task033：高阶 Floquet 与 Hybrid 阶段性收口

## 当前状态

```text
stage status = p3/h5 Hybrid component closed; full3D not run by memory gate
original Task033 scope = partial; adaptivity deferred by user on 2026-07-17
Stage1 formal source SHA = 6613f94b91ebc77eb50e74086475c67df46236f6
Phase A source SHA = bb830ba5dd74ced30475402bd6bc6d3c1856c630
Phase B measurement SHA = bd7a6023bde7a7c06d456e702af4b7f9f047b3fc
Phase B aggregate SHA = 9ac29db45b387d4590de084710abe2cc38b25ffe
Phase C numerical SHA = b636444b693a932988b6d5d69f7e44e6a8cddb38
ordinary default = unchanged
```

本轮按用户缩小后的范围收口，只回答两件事：

1. 直接 3D FEM/Floquet 与 QEP 是否已经扩展到 `p=3,4`；
2. 已有 Hybrid FEM–modal 复合方法相对直接 3D FEM 的规模与精度表现如何。

原任务书 [`task.md`](task.md) 保持不改。其 uniform p/h 全矩阵、graded/adaptive h、
equal-accuracy、interface buffer、variable-p/hp zoning 与 1 TiB 推演均延期，不计为失败，
也不计为已完成。

## 阶段结论

| 对象 | 结论 | 证据身份 |
|---|---|---|
| 直接 3D FEM p3/p4 Floquet | 通过 | Case090，MPI1/2/4 共 144 次 clean-source PDE |
| p3/p4 QEP component | p3、p4 均资格化 | MPI1 36-shard replay + p3/p4 h3 MPI2/4 positive identity |
| QEP legacy 全阶 aggregate | 未资格化 | p1 与 p2 真实低阶负结果保留；不再由 p4 基旋转阻止 |
| p3/p4 matched trace | p3、p4 均通过；p4 独立判定 | p2 MPI1 + p3/p4 MPI1/MPI4 五条 clean-source Phase B shard |
| Hybrid vs full3D | p2/h5、p2/h3 同阶同网格一致性通过 | 复用 Task032 clean Case080 records |
| p3/h5 Hybrid M funnel | M80/M120/M160 与 augmented/minimal M160 通过 | Phase C 同一 clean SHA、MPI4、零 swap |
| p3 Hybrid vs p3 full3D | 没有正式同阶 reference | full3D 第二内存中心/上界失败，`not_run_by_memory_gate` |
| p4 Hybrid | 未运行 | 延期 |
| 自适应与 interface 优化 | 未运行 | 用户缩小范围后延期 |

## 结果入口

- [阶段总结](outcomes/summary.md)
- [高阶 3D Floquet 结果](outcomes/high_order_floquet_results.md)
- [QEP 阶次研究](outcomes/qep_order_study.md)
- [QEP tracking 诊断](outcomes/qep_tracking_diagnostic.md)
- [Phase B matching-interface 迹组件](outcomes/matched_trace_phaseB.md)
- [Phase C p3/h5 候选级 Gate 与 Hybrid 结果](outcomes/p3_h5_phaseC.md)
- [Hybrid 与直接 3D FEM 对比](outcomes/hybrid_vs_full3d_summary.md)
- [负结果与延期边界](outcomes/negative_results.md)
- [原阶段回复](response_v1.md)
- [对审阅报告的回复](response_v2.md)
- [对 Phase A 复审及 Phase B 执行要求的回复](response_v3.md)
- [对 Phase B 复审及 Phase C 执行要求的回复](response_v4.md)
- [轻量阶段证据记录](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage1_high_order/stage_summary.json)
- [Phase B 独立轻量聚合](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/phaseB_summary.json)
- [Phase C p3/h5 轻量摘要](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC_summary.json)

完整 21-role formal manifest 尚未生成；
`records/formal_evidence_manifest_NOT_RUN.json` 继续代表原 Task33 完整范围未闭合。
