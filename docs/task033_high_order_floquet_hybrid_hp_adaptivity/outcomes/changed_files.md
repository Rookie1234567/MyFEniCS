# Task033 阶段交付文件

## 源码与测试

高阶实现、schemas、runners 与测试已冻结在正式计算源码
`6613f94b91ebc77eb50e74086475c67df46236f6`。本次范围调整后没有再改求解源码。

## 本轮新增或更新

| 类别 | 文件 |
|---|---|
| 阶段摘要 | `outcomes/summary.md` |
| 高阶结果 | `outcomes/high_order_floquet_results.md`、`outcomes/qep_order_study.md` |
| 方法对比 | `outcomes/hybrid_vs_full3d_summary.md` |
| 边界与暂停点 | `outcomes/negative_results.md`、`response_v1.md` |
| 环境/审计/测试 | `outcomes/environment_and_base.md`、`high_order_assumption_audit.md`、`memory_prediction_and_launch_decisions.md`、`test_summary.md` |
| 轻量证据 | `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage1_high_order/stage_summary.json` |
| Case/项目索引 | Case090/091 README、项目 README、docs/notes 索引与 roadmap |

## 明确保留不改

- `docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md`；
- `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/formal_evidence_manifest_NOT_RUN.json`；
- Task032 六份 tracked Hybrid/full3D comparison records；
- ignored campaign 原始 field、mesh、matrix、factor、timeline 与 logs。

stage summary 不是 formal manifest。文档交付 commit 与正式计算 source SHA 可以不同，
两者会在最终回复中分别报告。
