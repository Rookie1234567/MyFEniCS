# Task032 变更清单

## 2026-07-15 Review V1 跟进

| 类别 | 本轮同步内容 |
|---|---|
| 结论与回复 | 重写 `outcomes/summary.md`；新增 `response_v1_review_followup.md`，逐项回应 Review V1 与 addendum |
| 0.7 nm 可扩展性 | 新增确定性投影脚本、投影 JSON、可扩展性评估、轻量记录尺寸清单与选择性合并清单 |
| 契约与测试 | 新增 `test_41_task032_scalability_projection.py`；扩展仓库原则与文档契约测试，固定 table-first 和 evidence identity 规则 |
| 求解器边界 | 给 QEP、耦合、augmented-direct 与 Modal-Schur direct 接口补充“当前尺度基线、非 0.7 nm 生产路径”的边界说明 |
| 全局文档 | 同步根 README、benchmark 索引、能力矩阵、开发进展、迭代端口、项目路线图、Phase-1 scope、理论说明与代码导读 |
| 保留不动 | `task.md`、`review_report_v1.md`、`review_report_v1_addendum.md` 作为不可改写的任务与审阅输入；Case080 原始记录保留完整精确振幅 |

本轮新增轻量证据位于 `outcomes/`；没有把重型场数组或 solver 工作目录纳入 Git。

## Task032 Phase 6f--10 与最终闭合变更

## 物理、模式与求解

- `src/postprocessing/hybrid_field_reconstruction.py`：选面 E/H、界面连续性与体吸收；
- `src/solvers/hybrid_fem_modal_schur_direct.py`：fast 和 memory-minimal Modal-Schur；
- `src/modes/mode_classification.py`：被动方向 candidate 过滤；
- `src/geometry/hybrid_local_mesh.py`：h3 精确插入 10/110 nm 接口；
- `src/solvers/hybrid_fem_modal_augmented_direct.py`：逐衍射级复振幅与功率输出；
- `src/coupling/hybrid_internal_modes.py`：大 M 有界日志。

## Benchmark 与 evidence

- `benchmarks/run_task032_phase6_augmented.py`：物理场、三种 direct 生命周期、ledger/stage；
- `benchmarks/run_task032_phase8_funnel.py`：total/order/interface 截断收敛；
- `benchmarks/run_task032_phase9_smoke.py`：固定角度和 S/P smoke；
- `benchmarks/run_task032_memory_forensics.py`：外部同时 RSS/cgroup/swap/stage 采样；
- `benchmarks/run_task032_h2_prediction.py`：双方法 h2 解锁判断；
- `benchmarks/task032_final_gates.py`：最终场、Schur、漏斗、内存、h2 与参数 Gate；
- `benchmarks/check_benchmarks.py`：接入 Task32 最终 Gate；
- `benchmarks/cases/080_hybrid_fem_modal_direct_baseline/{config.json,expected.json,expected/gates.json,README.md}`；
- `benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/`：四条主记录、两条漏斗、
  六条内存、参数 smoke 和 h2 决策。

## 测试与文档

- `src/test/test_33_task032_mode_classification.py`；
- `src/test/test_36_task032_hybrid_local_mesh.py`；
- `src/test/test_39_task032_hybrid_augmented_direct.py`；
- `src/test/test_40_task032_hybrid_field_reconstruction.py`；
- `notes/reference/code_walkthrough/51_task032_fields_schur_and_memory.md` 与索引；
- `docs/task032_hybrid_fem_modal_direct_baseline/response_v1.md`；
- `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/` 最终证据；
- `docs/development_progress.md` 最新状态。

重型 timelines、field arrays 与 solver work directories 保持在
`benchmarks/artifacts/cases/080/`，继续由 Git 忽略；Git 只保存轻量、可审计摘要。
