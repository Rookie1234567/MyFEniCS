# FEniCSx 周期 Maxwell / Floquet Demo

本项目用于验证二维、三维频域 Maxwell 有限元、Floquet 周期约束、DtN 模态端口、official R/T/A 与材料体吸收。当前阶段已经具备目标三维 EUV 光栅的 direct reference，以及显式 opt-in 的 MPI4 workstation 迭代候选。

## 当前能力

| 能力 | 状态 |
|---|---|
| 2D Floquet + DtN | 稳定；具体组合和 backend 限制见能力矩阵 |
| 3D Stage1-Stage4 staged workflow | 稳定 |
| p=2 topological-trace Floquet MPC | 稳定 |
| complex refractive index 与 A_volume | 稳定 |
| DtN modal official R/T/A | 稳定 |
| p=2 h=2 direct reference | 已验证 |
| exact auxiliary condensation | 稳定模块 |
| p=2 h=5/3/2 MPI4 physical-slab iterative | 显式 opt-in 候选 |
| h=1.5 production solve | 未完成 |
| spectral/GenEO/HPDDM research routes | 不进入普通 API |

## 快速入口

普通入口保持既有 direct 默认：

```bash
python -m src.runners.run_cases
python -m src.runners.run_3d_cases --stage-case stage1_airbox
python -m src.runners.run_3d_cases --stage-case stage4_block_grating
```

经过验证的 workstation profile 必须显式调用：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --h-nm 2 \
  --record benchmarks/records/workstation_p2_h2_mpi4.json
```

普通运行的完整网格、场和日志写入 `results/`，不提交 Git。轻量 benchmark 摘要放在 `benchmarks/records/`。Task028 V1 审查要求进一步修正 canonical benchmark 的重型输出目录、脚本自动化和环境复现说明，当前分支尚未建议合并 master。

## 文档导航

| 文档 | 内容 |
|---|---|
| [开发进度](docs/development_progress.md) | Task000-Task028 分阶段开发内容、关键结果、失败路线与当前进展 |
| [快速开始](docs/quick_start.md) | 环境、普通入口、workstation 入口；Task028 V1 要求继续扩充 |
| [架构概览](docs/architecture_overview.md) | 模块边界与数据流 |
| [求解器指南](docs/solver_guide.md) | direct/iterative 选择与限制 |
| [能力矩阵](docs/capability_matrix.md) | 已支持与未支持能力；Task028 V1 要求继续补全 |
| [结果 schema](docs/result_schema.md) | JSON、RSS、R/T/A 字段 |
| [Benchmark](docs/benchmark.md) | 分层验证与当前记录 |
| [任务索引](docs/README.md) | Task000-Task028 闭环与 Task028 V1 审查入口 |
| [理论笔记](notes/README.md) | 物理和数值解释 |

## 重要边界

当前 workstation profile 针对固定目标几何、p=2、MPI4 和已审查参数。h=5/3/2 均通过显式真残差 `1e-6` gate，但迭代数不单调，因此称为 mesh-robust production candidate，而不是数学意义上的 mesh-independent solver。新角度、波长、材料或几何必须重新与 direct reference 交叉验证。
