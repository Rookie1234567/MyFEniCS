# Task033：高阶 Floquet 与 Hybrid 阶段性收口

## 当前状态

```text
stage status = p3/p4 high-order stage completed
original Task033 scope = partial; adaptivity deferred by user on 2026-07-17
formal source SHA = 6613f94b91ebc77eb50e74086475c67df46236f6
Phase A source SHA = bb830ba5dd74ced30475402bd6bc6d3c1856c630
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
| Hybrid vs full3D | p2/h5、p2/h3 同阶同网格一致性通过 | 复用 Task032 clean Case080 records |
| p3 Hybrid vs p3 full3D | 没有正式同阶 reference | 仅有非正式 p3 Hybrid 诊断，不作等价性结论 |
| p4 Hybrid | 未运行 | 延期 |
| 自适应与 interface 优化 | 未运行 | 用户缩小范围后延期 |

## 结果入口

- [阶段总结](outcomes/summary.md)
- [高阶 3D Floquet 结果](outcomes/high_order_floquet_results.md)
- [QEP 阶次研究](outcomes/qep_order_study.md)
- [QEP tracking 诊断](outcomes/qep_tracking_diagnostic.md)
- [Hybrid 与直接 3D FEM 对比](outcomes/hybrid_vs_full3d_summary.md)
- [负结果与延期边界](outcomes/negative_results.md)
- [原阶段回复](response_v1.md)
- [对审阅报告的回复](response_v2.md)
- [轻量阶段证据记录](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage1_high_order/stage_summary.json)

完整 21-role formal manifest 尚未生成；
`records/formal_evidence_manifest_NOT_RUN.json` 继续代表原 Task33 完整范围未闭合。
