# Task028 outcomes

本目录保存 Task028 的轻量、可审查结论和复现信息。逐项审查回应位于：

- `../response_v1.md`：第一轮 benchmark 与环境修正；
- `../response_v2.md`：文档体系、PyCharm、feature benchmarks、RTA 和 metadata 修正。

## 文件职责

| 文件 | 内容 |
|---|---|
| `summary.md` | 当前完整结论、数值表、限制和审查问题 |
| `metrics.csv` | direct/iterative 与 Response V2 smoke 指标 |
| `parameters.json` | 冻结模型、求解器、文档规模和验证计数 |
| `run_log.txt` | 关键命令、诊断过程和未执行项目 |
| `changed_files.md` | 按源码、测试、benchmark、文档分类的改动 |
| `documentation_audit.md` | 五层文档、13 cases 和交叉链接审计 |
| `benchmark_gate.csv` | 面向人的细粒度 Gate 表 |
| `gate_decision.csv` | 最终分组决策 |
| `test_summary.md` | 105 项测试、MPI4、87/87 Gate 与 smoke |
| `merge_recommendation.md` | 合并范围和风险 |
| `next_decision.md` | 最终审查与用户决策顺序 |

完整 benchmark 运行文件位于 gitignored `benchmarks/artifacts/`；普通用户运行仍写 gitignored `results/`。本目录不保存 mesh、VTU/XDMF/HDF5、矩阵、cache 或 raw run。
