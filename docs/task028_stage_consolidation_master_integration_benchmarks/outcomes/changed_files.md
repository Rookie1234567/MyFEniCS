# 本轮改动文件

## 稳定源码

| 文件 | 作用 |
|---|---|
| `src/solvers/condensed_dtn.py` | exact static condensation、matrix-free action与回代 |
| `src/solvers/physical_slab_two_level.py` | fixed coarse与MPI owner-computes slab smoother |
| `src/solvers/stage4_runtime.py` | 目标Stage4只装配runtime |
| `src/solvers/common_3d_utils.py` | 增加MPI总峰值RSS遥测 |
| `src/solvers/common_3d_case_flow.py` | 将总RSS写入普通3D summary |
| `src/test/test_22_condensed_dtn.py` | 凝聚代数/MPI回归 |
| `src/test/test_23_physical_slab_two_level.py` | owner、empty-owner与cache认证 |

## Benchmark

新增 `benchmarks/` 下 runner、configs、expected gates、scripts、manifest、environment、说明和轻量 records。正式 benchmark 的完整网格与场写入被忽略的 `benchmarks/artifacts/`；普通 CLI 仍写 `results/`。

## 用户文档

重建根 README、docs索引、notes索引、code walkthrough和current boundaries；新增 quick start、architecture、solver guide、result schema、capability matrix与benchmark说明。

## 历史文档

选择性加入 Task021-Task027 的核心闭环文档，并新增 Task28 审计、manifest、gate和总结材料。未加入 raw_runs。
