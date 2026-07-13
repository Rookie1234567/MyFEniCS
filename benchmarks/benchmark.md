# Benchmark 维护规范

编号功能级说明见 [`cases/README.md`](cases/README.md)。本文件保留 target 数值与维护规范，case 目录负责逐项复现契约。

## 目的

本目录验证 clean checkout 中的稳定入口、代数等价、MPI owner-computes 语义和目标工作站求解能力。它不承担普通用户的完整结果存储。

## 规范配置

目标 Level3 模型为 50 x 25 x 140 nm，光栅 17 x 25 x 120 nm，波长 13.5 nm，入射角 80 度，s 偏振，N1curl p=2。迭代 profile 见 `configs/workstation_p2.json`。

## Gate

| 项目 | 阈值 |
|---|---|
| condensed action error | <= 1e-11 |
| coarse cache true-action error | <= 1e-10 |
| synthetic reconstruction | <= 1e-12 |
| reported/condensed/full residual | 相对差 <= 1e-8 |
| production true residual | <= 1e-6 |
| energy closure | abs <= 1e-6 |
| h2 total RSS | <= 14 GB |
| h5/h3/h2 iteration ratio | <= 2.0 |
| h5/h3 direct-iterative R/T/A | case-specific <= 1e-8 |

## 输出策略

`records/` 保存 canonical JSON、CSV 和轻量日志；`artifacts/` 保存大场文件并默认忽略。普通 CLI 继续写 `results/`，benchmark runner 则显式使用 `benchmarks/artifacts/`。

## 可复现命令

```bash
sh benchmarks/scripts/run_level1.sh
sh benchmarks/scripts/run_level2_mpi.sh
sh benchmarks/scripts/run_level3_iterative.sh
python -m benchmarks.check_benchmarks
```

Direct默认脚本只运行h5/h3；h2约需20.53 GB，必须显式opt-in。环境限定见 `docker/STAGE4_ENVIRONMENT.md`。
