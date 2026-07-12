# 环境与 PyCharm

## 必要环境

本项目求解时谐 Maxwell 复数线性系统，必须满足 `PETSc.ScalarType` 为 `numpy.complex128`。Windows 主机上的普通 Anaconda 不含本项目需要的 DOLFINx/Basix/PETSc；正式验证使用 Docker/WSL2。环境身份和镜像摘要见 [`../../benchmarks/environment.json`](../../benchmarks/environment.json) 与 [`../../docker/STAGE4_ENVIRONMENT.md`](../../docker/STAGE4_ENVIRONMENT.md)。

快速检查：

```bash
python -c "from petsc4py import PETSc; print(PETSc.ScalarType)"
python -m src.tools.inspect_environment
```

第一行不是复数类型时不要继续物理解读。

## PyCharm 直接运行

1. 将项目根目录设为 Working directory。
2. 运行文件选 `src/main.py`，Program arguments 留空。
3. 在 `src/main.py` 顶部修改唯一选择器，例如：

```python
ACTIVE_PYCHARM_PRESET = "3d_stage1_airbox_smoke"
```

4. 初次运行不要改默认值。它是小型 Stage 1，避免误触发 Stage 4 大矩阵。

查看所有名称：

```bash
python src/main.py --list-presets
```

显式使用 preset：

```bash
python src/main.py --preset 2d_tm_dtn_auxiliary_smoke
```

也可把 runner 参数直接传给统一入口：

```bash
python src/main.py 3d --stage-case stage1_airbox --case normal --mesh-target-size 300
```

## Docker 注意事项

- 普通输出留在 `results/`，该目录不提交 Git。
- 基准重型输出只写 `benchmarks/artifacts/`，轻量 JSON/CSV 才提交。
- 生产迭代器必须从容器外显式 `mpiexec -n 4`，见 `40_3d_workstation_iterative.md`。
- 不要在 Python 内部 spawn MPI；PyCharm 的单进程 Run 也不代表 MPI4 资格。

## 常见启动错误

| 现象 | 原因 | 处理 |
|---|---|---|
| `No module named basix` | 使用了 Windows 主机 Python | 切到项目 Docker 解释器/容器命令 |
| PETSc 是实数 | 镜像不是 complex build | 换用登记的复杂数镜像 |
| `Unknown preset` | 名字与代码不一致 | 运行 `--list-presets` |
| MPI direct 拒绝本地 LU | 并行镜像没有 MUMPS | 使用限定镜像，不能把每 rank 局部分解当全局解 |
| 14 GB 环境内存不足 | direct 因子填充或 h 太小 | 先 h=5；生产 h=2 使用 MPI4 迭代基准档 |

官方参考：DOLFINx Maxwell 示例明确要求 complex PETSc，见 <https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_scattering-boundary-conditions.html>。
