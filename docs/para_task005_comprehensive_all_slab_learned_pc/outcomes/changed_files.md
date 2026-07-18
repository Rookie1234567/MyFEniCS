# Changed files

本清单以冻结任务书提交
`f4c0600f352dd940b48e7bdd9b9494d5ebe9e4b0` 为基准，覆盖 Task005 执行至
`5ed1162` 的全部 42 个 tracked diff；审阅响应阶段的追加文件另列于末尾。

## Case、运行入口与 benchmark

| 文件 | 作用 |
|---|---|
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/README.md` | Case094 冻结合同、证据身份与限制 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/config.json` | 冻结 h5/MPI4/16-slab 配置 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/expected.json` | Gate 与禁止声明 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/p2_candidate_pool.json` | 12 组预冻结候选 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/run.sh` | Case094 入口 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/run_capture.sh` | T1/T2/V/H capture recipe |
| `benchmarks/neural_pc/audit_task005_captures.py` | fingerprint、count、split overlap、duplicate/near-duplicate audit |
| `benchmarks/neural_pc/benchmark_task005_owner_batch.py` | four-slab grouped model-only runtime screen |
| `benchmarks/neural_pc/build_all_slab_lu_teacher.py` | 16-slab 顺序 one-factor/many-RHS 编排 |
| `benchmarks/neural_pc/build_lu_teacher_dataset.py` | T1/T2/V/H raw-RHS LU teacher dataset |
| `benchmarks/neural_pc/build_task005_ilu_holdout.py` | complex PETSc ILU(0)+RCM R4 screening baseline |
| `benchmarks/neural_pc/petsc_capture.py` | batched raw capture 与 clean-source attestation |
| `benchmarks/neural_pc/screen_task005_linear.py` | Lane A、D0/D1、R4 screening quality |
| `benchmarks/neural_pc/screen_task005_nonlinear.py` | Lane B GPU training与三 backend screen |
| `benchmarks/run_task031_memory_forensics.py` | capture 参数透传与外部 memory sampling |
| `benchmarks/run_workstation_iterative.py` | research capture/partition 参数接入 |

## 实现与测试

| 文件 | 作用 |
|---|---|
| `src/geometry/mesh_builder_3d.py` | 显式 research-only cell partition policy；默认 create-box policy 不变 |
| `src/solvers/lu_teacher_local_solver.py` | bounded multi-RHS SuperLU teacher |
| `src/solvers/physical_slab_two_level.py` | deterministic raw capture hooks |
| `src/test/test_15_stage4_hexa_mesh_spacing.py` | explicit partition policy regression |
| `src/test/test_35_lu_teacher_contract.py` | teacher、raw capture、batching contracts |
| `src/test/test_45_para_task005_contract.py` | Task005/P2/export contracts |

## 文档与轻量结果

| 文件 | 作用 |
|---|---|
| `docs/development_progress.md` | Task005 进展与 Gate 记录 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/README.md` | 任务入口状态 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/amortization_report.md` | dataset/checkpoint 审计摊销 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/changed_files.md` | 本完整清单 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/data_and_teacher_report.md` | P1 capture/teacher 证据 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/decision.md` | 最终 Gate 分类 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/experiment_matrix.csv` | 阶段矩阵 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/global_ab.csv` | 未运行的 global 阶段身份 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/local_quality_by_slab.csv` | R4 局部质量 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/memory_report.md` | model + private audit CSR storage |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/model_ablation.csv` | Lane A/B 候选结果 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/model_and_dataset_provenance.md` | source/checkpoint provenance |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/owner_batch_report.md` | owner-like model-only microbenchmark |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/p0_environment_and_baseline.md` | clean h5/MPI4 baseline |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/p1_teacher_summary.csv` | 16-slab teacher summary |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/robustness_matrix.csv` | stopped-by-gate matrix |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/runtime_backend_report.md` | CPU/CUDA model-only runtime |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/shadow_safety_report.md` | shadow 未运行身份 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md` | Task005 总结 |

`docs/para_task004_full_16_slab_exact_oracle/response_v1.md` 也位于上述 commit range，
但属于前置 Task004 的审阅治理，不属于 Task005 实现或证据；这里显式列出，避免
把相邻任务变更藏出 tracked diff。

## 审阅响应追加

| 文件 | 作用 |
|---|---|
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/README.md` | 补齐 22 项 case-contained contract 与证据限制 |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/expected.json` | 补充 qualified negative status |
| `src/test/test_26_documentation_contract.py` | 注册 Case094 |
| `src/test/test_45_para_task005_contract.py` | FEniCS 无 torch 时 skip，ML 环境单独验证 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/response_v1.md` | Review V1 正式答复 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/validation.md` | 集中验证与 provenance |

## Heavy ignored artifacts

全部位于 `benchmarks/artifacts/cases/094/`，包括 captures、leakage audit、teacher
datasets、P2 checkpoints、raw JSON/logs 与 rejected diagnostics。目录由
`.gitignore:58` 命中，未加入 Git。
