# Task006 changed files

基准为 Task006 入口前 clean `7f9c577`。

| 文件 | 作用 |
|---|---|
| `benchmarks/cases/095_zero_copy_learned_pc_audit/README.md` | 22 项 Case095 冻结合同与结果边界 |
| `benchmarks/cases/095_zero_copy_learned_pc_audit/config.json` | h5/MPI4/R4/audit budgets |
| `benchmarks/cases/095_zero_copy_learned_pc_audit/expected.json` | hard Gate 与禁止声明 |
| `benchmarks/cases/095_zero_copy_learned_pc_audit/run.sh` | gated entry |
| `benchmarks/neural_pc/qualify_task006_borrowed_action.py` | 16-slab ephemeral-reference equivalence |
| `benchmarks/neural_pc/build_task006_ilu_reference.py` | Q0/V PETSc ILU per-sample ground truth |
| `benchmarks/neural_pc/calibrate_task006_proxy.py` | Q0-only reduced/CountSketch family calibration |
| `benchmarks/run_task031_memory_forensics.py` | borrowed qualification 参数透传 |
| `benchmarks/run_workstation_iterative.py` | opt-in P1 qualification hook |
| `src/solvers/borrowed_local_audit.py` | zero-private-CSR collective exact auditor |
| `src/solvers/low_storage_audit_proxy.py` | guards、reduced certificate、procedural sketch primitives |
| `src/solvers/physical_slab_two_level.py` | borrowed auditor explicit factory/lifecycle |
| `src/test/test_26_documentation_contract.py` | 注册 Case095 |
| `src/test/test_46_para_task006_contract.py` | Case095/P0 provenance contract |
| `src/test/test_47_borrowed_local_audit.py` | MPI、overlap、rho、ephemeral reference、destroy |
| `src/test/test_48_low_storage_audit_proxy.py` | sketch deterministic/batch、guards、no-CSR |
| `docs/para_task005_comprehensive_all_slab_learned_pc/response_v1.md` | Task005 review identity修正 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/validation.md` | Task005 集中验证 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/changed_files.md` | Task005 42-file diff |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/data_and_teacher_report.md` | split/distribution identity修正 |
| `docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md` | H/V/D1 结论边界修正 |
| `docs/para_task006_zero_copy_audit_architecture/outcomes/*` | P0-P2 evidence、P3-P8 Gate处置与集中验证 |
| `docs/development_progress.md` | Task006 retrospective |

Task005 review contract修复还更新了 Case094 README/expected、
`test_26_documentation_contract.py` 和 `test_45_para_task005_contract.py`；详见
Task005 `outcomes/changed_files.md`。heavy artifacts 全部位于
`benchmarks/artifacts/cases/095/` 并由 `.gitignore:58` 命中。
