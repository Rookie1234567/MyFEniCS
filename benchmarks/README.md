# Benchmark 运行说明

Benchmark 与普通 `results/` 分离。轻量 JSON/CSV 记录提交 Git，完整网格和场写入被忽略的 `benchmarks/artifacts/`。

| 脚本/文件 | 实际内容 |
|---|---|
| `scripts/run_level1.sh` | compileall、全量单元测试、显式2D manual DtN、3D Stage1 MPI2 |
| `scripts/run_level2_mpi.sh` | MPI1/MPI4 condensation+physical-slab tests、automatic checker |
| `scripts/run_level3_direct.sh` | 默认h5/h3 direct；h2仅显式resource-heavy opt-in |
| `scripts/run_level3_iterative.sh` | p2 h5/h3/h2 workstation完整求解并运行checker |
| `configs/workstation_p2.json` | canonical profile唯一默认来源；CLI只做override |
| `expected/gates.json` | 残差、迭代比、RTA、RSS阈值 |
| `check_benchmarks.py` | 从manifest/records重算Gate，失败返回非零 |
| `records/` | canonical轻量记录与machine-readable Gate report |
| `artifacts/` | ignored重型输出 |

## 推荐顺序

```bash
sh benchmarks/scripts/run_level1.sh
sh benchmarks/scripts/run_level2_mpi.sh
sh benchmarks/scripts/run_level3_direct.sh
sh benchmarks/scripts/run_level3_iterative.sh
```

不要在14 GB环境默认执行direct h2。确需运行时必须显式传：

```bash
sh benchmarks/scripts/run_level3_direct.sh --include-resource-heavy-h2
```

## Record身份

clean rerun必须记录commit、branch、dirty、command、time、container digest、host ID和provenance。h5 iterative在Response V1从`3b3abf0` clean source重新运行；h3/h2 iterative和h5/h3 direct是`440885b` clean source的ancestor records；h2 direct明确为Task008 reviewed reference。checker分别验证这些身份，不能把reviewed reference写成clean rerun。

当前环境状态为 `qualified_local_image`，详见 `docker/STAGE4_ENVIRONMENT.md`。
