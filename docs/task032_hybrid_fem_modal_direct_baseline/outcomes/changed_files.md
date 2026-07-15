# Task032 Phase 6f--10 变更清单

## 物理与求解

- `src/postprocessing/hybrid_field_reconstruction.py`：选面 E/H、界面连续性、体吸收；
- `src/solvers/hybrid_fem_modal_schur_direct.py`：fast 与 memory-minimal Modal-Schur；
- `src/modes/mode_classification.py`：被动方向 candidate 过滤；
- `src/geometry/hybrid_local_mesh.py`：h3 精确 10/110 nm 接口插入；
- `src/solvers/hybrid_fem_modal_augmented_direct.py`：逐衍射级复振幅/功率输出；
- `src/coupling/hybrid_internal_modes.py`：大 M 有界日志。

## Benchmark

- `benchmarks/run_task032_phase6_augmented.py`：物理场、三种 direct lifecycle、ledger/stage；
- `benchmarks/run_task032_phase8_funnel.py`：total/order/interface 收敛；
- `benchmarks/run_task032_phase9_smoke.py`：固定角度/S-P smoke；
- `benchmarks/run_task032_memory_forensics.py`：外部同时内存权威；
- `benchmarks/run_task032_h2_prediction.py`：两方法 h2 解锁判断；
- `benchmarks/run_direct_memory_forensics.py`：识别 Task32 MPI worker rank。

## 测试与文档

- `src/test/test_33_task032_mode_classification.py`；
- `src/test/test_36_task032_hybrid_local_mesh.py`；
- `src/test/test_39_task032_hybrid_augmented_direct.py`；
- `src/test/test_40_task032_hybrid_field_reconstruction.py`；
- `notes/reference/code_walkthrough/51_task032_fields_schur_and_memory.md`；
- `notes/reference/code_walkthrough.md`；
- `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/` 本轮证据；
- `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/test_summary.md`。
- Case080 records/gates/checker/README 在正式 clean record 阶段同步。
