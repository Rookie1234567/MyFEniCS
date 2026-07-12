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
| `src/test/test_25_benchmark_contract.py` | 自动Gate、配置、脚本与ordinary output contract |
| `src/runners/run_cases.py` | 增加显式output root覆盖，ordinary默认不变 |
| `src/runners/run_3d_cases.py` | 增加显式output root覆盖，ordinary默认不变 |

## Benchmark

新增/更新 `benchmarks/check_benchmarks.py`、单一JSON配置、expected gates、L1/L2/L3 scripts、manifest、完整metadata、自动summary与轻量 records。正式 benchmark 的完整网格与场写入被忽略的 `benchmarks/artifacts/`；普通 CLI 仍写 `results/`。

新增 `docker/Dockerfile.stage4` 与 `docker/STAGE4_ENVIRONMENT.md`，固定本地base digest并统一complex PETSc、dolfinx_mpc和gmsh；环境诚实限定为 `qualified_local_image`。

## 用户文档

重建根 README、docs索引、notes索引、code walkthrough和current boundaries；新增 quick start、architecture、solver guide、result schema、capability matrix与benchmark说明。

## 历史文档

选择性加入 Task021-Task027 的核心闭环文档，并新增 Task28 审计、manifest、gate和总结材料。未加入 raw_runs。
