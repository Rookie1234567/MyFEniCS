# Task033 阶段交付文件

## 2026-07-17 Review V6 F0 与选择性合并收口

| 文件 | 作用 |
|---|---|
| `benchmarks/task033_source_compatibility.py` / runner | 新增 p3/h10、p3/h7.5 两段 descriptor-only D1 source split 审计 |
| `records/stage5_equal_accuracy/d1_source_compatibility_audit.json` | tracked D1 kernel-blob/source compatibility 证据 |
| `benchmarks/task033_reduced_equal_accuracy.py` / runner | 冻结镜像/digest/MPI4/zero-swap/solver/memory authority/clean SHA 与指示性时间语义 |
| `benchmarks/task033_resource_gates.py` | 冻结 1.947→1.980 GiB、2.463→3.667 GiB 高阶预测低估 |
| `benchmarks/task033_reduced_scope_completion.py` / runner | fail-closed reduced-scope completion record/checker |
| `records/task033_reduced_scope_completion.json` | 绑定 Stage1、QEP、Phase B/C、D1/D2、测试与 merge manifest |
| `outcomes/selective_merge_manifest.csv` | 文件级精确 allowlist/exclude list；不再使用 glob |
| `src/test/test_71_task033_reduced_scope_completion.py` | completion record 防陈旧合同 |
| `src/test/test_72_task033_variable_p_capability.py` | 可独立合入 master 的 D2 fail-closed 合同 |
| `src/test/test_53_task033_high_order_hybrid_components.py` | 同步已接受的 p3/h5 reference wiring；继续拒绝 p3/h3 与 p1 |
| `response_v7.md` | 对 Review V6 与实际选择性合并的回复 |

F0 未修改 Maxwell、Floquet、QEP、Hybrid coupling、solver 或 physical
postprocess numerical kernel，也未运行新的 PDE。adaptive/graded-h、1 TiB runner、
full-scope campaign 与对应 prototype tests 不进入本次 master 能力合并。

## 2026-07-17 Review V5 D0/D1/D2 增量

| 文件 | 作用 |
|---|---|
| `benchmarks/task033_source_compatibility.py` / runner | pure-3D 与 Hybrid numerical source fail-closed 兼容性审计 |
| `benchmarks/task033_reduced_equal_accuracy.py` / runner | 聚合 p2/h3、p3/h10、p3/h7.5 的物理误差、M 收敛与资源 |
| `src/test/test_70_task033_reduced_equal_accuracy.py` | D1 聚合正/负合同与 payload hash 测试 |
| `records/stage5_equal_accuracy/full3d_reference_p3_h10.json` | p3/h10 direct descriptor |
| `records/stage5_equal_accuracy/full3d_reference_p3_h7p5.json` | p3/h7.5 direct descriptor |
| `records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json` | Review V5 D1 hash-bound aggregate |
| `records/variable_p_capability_audit.json` | D2 当前运行时 API 与 semantic requirement audit |
| `outcomes/reduced_equal_accuracy_phaseD.md` | D1 物理、闭合和资源结论 |
| `outcomes/variable_p_hp_capability.md` | D2 fail-closed 结论和 fixed-p zoning 设计 |
| `outcomes/task33_completion_matrix.md` | 原 task Phase 0–8、14 问与全文档审计 |
| `response_v6.md` | 对 Review V5 的正式回复 |

D1 的重型 raw field/NPZ/matrix/factor/timeline/log 继续保存在 gitignored
`benchmarks/artifacts/`。tracked descriptors 和 aggregate 保存路径、SHA256 与关键数值。

## 2026-07-17 Phase C1 / p4 后续增量

| 文件 | 作用 |
|---|---|
| `benchmarks/run_task032_phase6_augmented.py` | 接入 p3/h5 同阶 full3D reference |
| `benchmarks/run_task033_full3d_watchdog.py` | p3/p4 assembly/full-solve 监控；p4 强制 p3 与四模态双前置 |
| `benchmarks/run_task033_matched_trace.py` | p4 `[4,5,6,7]` 四模态近简并块实测 |
| `benchmarks/task033_matched_trace_qualification.py` | 四模态 fail-closed 聚合与基底无关 MPI block invariant |
| `benchmarks/run_task033_memory_watchdog.py` | 审计 Case090-core-compatible descendant 路径 |
| `records/stage2_matched_trace/p4_four_mode_summary.json` | p4 四模态 MPI1/MPI4 轻量证据 |
| `records/stage3_p3_h5/full3d_reference.json` | p3 direct NPZ 固定描述符 |
| `records/stage3_p3_h5/full3d_closure_summary.json` | p3 同阶 Hybrid/full3D 闭合 |
| `records/stage4_p4_h5/calibration_summary.json` | p4 受控内存负校准与停止理由 |
| `response_v5.md` | 对 review v4 后续执行的正式回复 |

## 源码与测试

高阶 PDE/QEP measurement 实现冻结在正式计算源码
`6613f94b91ebc77eb50e74086475c67df46236f6`。Phase A 在
`bb830ba5dd74ced30475402bd6bc6d3c1856c630` 增加 aggregate block tracking 与严格的
Case090 非数值后继提交复用门禁，没有改动数值装配或求解器。

Phase B 的 matching-trace 实测冻结在
`bd7a6023bde7a7c06d456e702af4b7f9f047b3fc`；它为
`ModalTraceProjection` 增加可选显式积分阶次和切向值通信字节遥测，普通默认调用不变。
远程可审计聚合器冻结在 `9ac29db45b387d4590de084710abe2cc38b25ffe`。

Phase C 候选级 Gate 与数值运行冻结在
`b636444b693a932988b6d5d69f7e44e6a8cddb38`。该提交新增 C0/aggregate，
并把 Case090 复用语义收窄为 pure-3D core compatible descendant；Phase B 的
Hybrid trace 数值改动显式记录为 component-disjoint。四条 Hybrid 正式记录使用
同一 clean source；在该历史阶段 full3D 没有因文档交付而补跑。

Phase C1 实现与 p3 Hybrid 闭合冻结在
`95921ab76e39eb1a7c5b3321b93d36939afb4075`。用户授权的 p3 full3D reference
来自 `bd828f24dc1546263210d73d08bf7bc16ba8a129`，随后由 `95921ab...` 上的
Hybrid M160 绑定 NPZ SHA 并完成 16 项同阶闭合 Gate。p4 四模态正式记录和
p4 assembly-only 负校准也绑定 `95921ab...`。

## 本轮新增或更新

| 类别 | 文件 |
|---|---|
| 阶段摘要 | `outcomes/summary.md` |
| 高阶结果 | `outcomes/high_order_floquet_results.md`、`outcomes/qep_order_study.md` |
| Phase A 诊断 | `outcomes/qep_tracking_diagnostic.md`、`response_v2.md` |
| Phase B 实现 | `src/coupling/modal_trace_projection.py`、`benchmarks/run_task033_matched_trace.py` |
| Phase B 资格判定 | `benchmarks/task033_matched_trace_qualification.py`、`src/test/test_66_task033_matched_trace_qualification.py` |
| Phase B 结果与回复 | `outcomes/matched_trace_phaseB.md`、`response_v3.md` |
| Phase C 实现 | `benchmarks/task033_phaseC.py`、`benchmarks/run_task033_phaseC.py` |
| Phase C watchdog hardening | `benchmarks/run_task033_memory_watchdog.py`、`benchmarks/task033_watchdog_launch.py` |
| Phase C tests | `src/test/test_67_task033_phaseC.py`、`src/test/test_59_task033_memory_watchdog_contract.py` |
| Phase C 结果与回复 | `outcomes/p3_h5_phaseC.md`、`response_v4.md` |
| 方法对比 | `outcomes/hybrid_vs_full3d_summary.md` |
| 边界与暂停点 | `outcomes/negative_results.md`、`response_v1.md` |
| 环境/审计/测试 | `outcomes/environment_and_base.md`、`high_order_assumption_audit.md`、`memory_prediction_and_launch_decisions.md`、`test_summary.md` |
| 轻量证据 | `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage1_high_order/stage_summary.json` |
| Phase B 轻量证据 | `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/phaseB_summary.json` |
| Phase C 轻量证据 | `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC_summary.json` |
| Case/项目索引 | Case090/091 README、项目 README、docs/notes 索引与 roadmap |
| Review V6 当前态同步 | root/docs README、capability matrix、development progress、roadmap、quick start、code walkthrough、theory note |

## 明确保留不改

- `docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md`；
- `benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/formal_evidence_manifest_NOT_RUN.json`；
- Task032 六份 tracked Hybrid/full3D comparison records；
- ignored campaign 原始 field、mesh、matrix、factor、timeline 与 logs。

stage summary 不是 formal manifest。文档交付 commit 与正式计算 source SHA 可以不同，
两者会在最终回复中分别报告。
