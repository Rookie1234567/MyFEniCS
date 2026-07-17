# Changed files

## Tracked implementation

| 文件 | 作用 |
|---|---|
| `benchmarks/neural_pc/audit_task005_captures.py` | fingerprint、count、split overlap、duplicate/near-duplicate audit |
| `benchmarks/neural_pc/build_lu_teacher_dataset.py` | T1/T2/V/H raw-RHS LU teacher dataset |
| `benchmarks/neural_pc/build_all_slab_lu_teacher.py` | 16 slab 顺序 one-factor/many-RHS 编排 |
| `benchmarks/neural_pc/build_task005_ilu_holdout.py` | complex PETSc ILU(0)+RCM R4 holdout |
| `benchmarks/neural_pc/screen_task005_linear.py` | Lane A、D0/D1、exact H quality |
| `benchmarks/neural_pc/screen_task005_nonlinear.py` | Lane B GPU training与三 backend screen |
| `benchmarks/neural_pc/benchmark_task005_owner_batch.py` | four-slab grouped runtime |
| `src/solvers/lu_teacher_local_solver.py` | bounded multi-RHS SuperLU teacher |
| `src/solvers/physical_slab_two_level.py` | research-only deterministic capture partition/capture hooks |
| `benchmarks/cases/094_comprehensive_all_slab_learned_pc/p2_candidate_pool.json` | 12 组预冻结候选 |
| `src/test/test_35_lu_teacher_contract.py` | teacher/raw capture contracts |
| `src/test/test_45_para_task005_contract.py` | Task005/P2/export contracts |

## Heavy ignored artifacts

全部位于 `benchmarks/artifacts/cases/094/`，包括 captures、leakage audit、teacher
datasets、P2 checkpoints、raw JSON/logs 和 rejected diagnostics。未加入 Git。
