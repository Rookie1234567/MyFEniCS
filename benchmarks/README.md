# Benchmark 运行说明

Benchmark 与普通 `results/` 分离。轻量 JSON/CSV 记录提交 Git，完整网格和场写入被忽略的 `benchmarks/artifacts/`。

| 脚本 | 内容 |
|---|---|
| `scripts/run_level1.sh` | 语法、导入和串行单元测试 |
| `scripts/run_level2_mpi.sh` | MPI4 凝聚与 physical-slab 测试 |
| `scripts/run_level3_iterative.sh` | p2 h5/h2 workstation 完整求解 |
| `configs/workstation_p2.json` | 固定 profile 参数 |
| `expected/gates.json` | 自动审查阈值 |
| `records/` | 当前 clean-branch 轻量结果 |

所有 Level3 结果必须来自当前 checkout，不能复制旧 Task027 record。
