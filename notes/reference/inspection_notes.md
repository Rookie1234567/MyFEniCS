# 检查记录

## 已检查的项目文件

- `codex_fenics_vector_maxwell_floquet_scattering_task.md`：本次任务说明，要求二维截面、复数矢量电场、`H(curl)` 空间、Nedelec 边单元、左右 Floquet 准周期边界、上下 PML，并在 Docker 中实际运行。
- `Dockerfile`、`docker-compose.yml`、`docker-entrypoint.sh`：已有 Docker 服务名为 `dolfinx`，镜像为 `code-dolfinx:latest`，挂载当前目录到 `/work`，并把环境变量指向 complex PETSc/DOLFINx 路径。
- `requirements-dolfinx.txt`：已有 `gmsh`、`pyvista`、`scipy`、`matplotlib`、`meshio` 等后处理和网格依赖。
- `demo_pml.py`：可复用的复数 Maxwell、Nedelec `N1curl`、PML 张量和 VTX 可视化思路。
- `demo_scattering_boundary_conditions.py`：可复用的散射场形式、入射场插值、Nedelec 场插值到 DG 空间后输出的做法。
- `demo_helmholtz.py`：这是标量 Helmholtz 示例，仅用于确认复数弱式中 `ufl.inner` 的共轭约定；本次主算例没有采用它。
- `DOLFINX_DOCKER_GUIDE.md`、`PYCHARM_DOCKER_SETUP.md`：已有 Docker/PyCharm 使用说明，本次不改动。

## Docker 与运行环境

- Docker Desktop 的 `docker.exe` 不在当前 PowerShell 的 `PATH` 中，需要使用完整路径 `$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe`。
- `code-dolfinx:latest` 镜像已经存在。
- 已在 Docker 中确认：
  - `PETSc.ScalarType = numpy.complex128`，可以求解复数频域 Maxwell 方程。
  - `dolfinx = 0.10.0.post2`。
  - `gmsh` 和 `pyvista` 可以导入。
  - `dolfinx_mpc` 未安装。
- 为了不破坏原镜像，另外拉取官方 `ghcr.io/jorgensd/dolfinx_mpc:v0.10.5`，并构建派生镜像 `code-dolfinx-mpc:latest`。派生镜像中确认：
  - `PETSc.ScalarType = numpy.complex128`；
  - `dolfinx = 0.10.0.post2`；
  - `dolfinx_mpc` 可以导入；
  - `gmsh`、`pyvista`、`scipy`、`matplotlib` 可用。

## 可复用与不复用的内容

- 复用 `demo_pml.py` 中的 Maxwell curl-curl 弱式方向、Nedelec 元素、PML 复坐标变换思想和 DG 可视化输出方法。
- 复用 `demo_scattering_boundary_conditions.py` 中的散射场分解和入射平面波插值思路。
- 不复用 `demo_helmholtz.py` 作为主模型，因为它是标量 Helmholtz 方程，不满足本次矢量 Maxwell 要求。
- 没有发现已有的空气-基座-光栅周期微纳结构、Floquet 边界或 Nedelec 周期约束示例，因此新算例独立实现。
- 原 `code-dolfinx:latest` 未被覆盖；新增的 MPC 环境使用单独镜像名 `code-dolfinx-mpc:latest`。

## 2026-06-09 复查补充

这次是在现有空气-基座-光栅算例上追加功能，不删除原来的散射场法。新增内容集中在：

```text
src/solvers/solve_port_maxwell.py
src/common/output_paths.py
src/main.py
```

`solve_port_maxwell.py` 实现端口总场法：上边界为入射端口，下边界为出射端口，左右仍使用已有 Floquet 约束。`output_paths.py` 解决每次运行覆盖旧结果的问题。`run_cases.py` 负责在命令行中选择：

```text
--formulation scattered
--formulation port_total
--formulation both
```

两个老入口脚本也已改为唯一结果目录输出，但仍只分别运行原来的官方 MPC 版本和手写矩阵版本。

端口法还增加了：

```text
--port-order-count N
```

用于手写矩阵后端的 Fourier 多衍射级次端口。它会在上、下端口包含 `m=-N...N` 的 Floquet 模态，更接近 COMSOL 周期端口的模式展开。

现在这些选择也都集中到了 `src/common/config.py`，包括：

```python
calculation_method
constraint_backend
port_boundary_model
port_dtn_order_count
unique_output
```

因此 PyCharm 中直接运行 `src/main.py`（它会调用 `src/runners/run_cases.py`）时，会按 `main.py` 文件开头的大写变量和 `config.py` 默认值生成对应结果目录，不需要每次手写命令行。
