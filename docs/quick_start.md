# 快速开始

## 运行环境

本项目使用 complex-mode DOLFINx/PETSc。Windows 上推荐通过现有 Docker 镜像运行，源码目录挂载为 `/work`。首先检查标量类型：

```bash
python -c "from petsc4py import PETSc; print(PETSc.ScalarType)"
```

输出应为复数类型。

## 普通入口

| 目标 | 命令 |
|---|---|
| 2D 默认案例 | `python -m src.runners.run_cases` |
| 3D Stage1 | `python -m src.runners.run_3d_cases --stage-case stage1_airbox` |
| 3D Floquet | `python -m src.runners.run_3d_cases --stage-case floquet_airbox` |
| 3D Stage4 block grating | `python -m src.runners.run_3d_cases --stage-case stage4_block_grating` |

普通入口继续使用既有 direct 默认，并将每次运行的完整结果写入 `results/`。Task28 没有静默改变默认求解器。

## Workstation 迭代入口

该入口只针对已经验证的 p=2 目标几何，必须显式调用：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --h-nm 2 \
  --record benchmarks/records/workstation_p2_h2_mpi4.json
```

固定 profile 为：exact condensed DtN、75D 零阶 Floquet hat coarse、16 个完整物理 z slabs、0.25 slab overlap、owner-computes ILU1、两步 shifted-F smoothing 和 FGMRES(100)。

## 验证

```bash
python -m py_compile src/solvers/*.py benchmarks/*.py
python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level
mpiexec -n 4 python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level
```

完整分层命令见 `benchmarks/README.md`。
