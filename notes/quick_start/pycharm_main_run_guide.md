# PyCharm 直接运行 main.py 指南

## 2026-06-18 更新：3D 求解器选择变量

如果 `SIMULATION_DIMENSION = "3d"`，可以在 `src/main.py` 的 3D 区块直接选择求解器：

```python
SOLVER_PROFILE_3D = "default"
SOLVER_RTOL_3D = 1.0e-8
SOLVER_ATOL_3D = 1.0e-12
SOLVER_MAX_IT_3D = 1000
SOLVER_MONITOR_3D = False
```

`default` 保持原来的直接法；压力测试时可以改成 `iterative_asm_ilu` 或 `iterative_bjacobi_ilu` 先试低内存迭代路径。运行结果会在 `solver_log.txt` 和 `run_summary.json` 里记录实际 PETSc options、迭代步数、残差、耗时和最大内存占用。

本文只回答一个问题：在 PyCharm 里到底运行哪个文件。

结论很简单：请直接运行

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/src/main.py
```

不要再手动运行 `run_cases.py`、`solve_vector_maxwell.py`、`solve_port_maxwell.py` 或其他子模块。它们都是被 `main.py` 调用的内部模块。

## 1. main.py 现在做什么

`src/main.py` 现在不是一个空转发文件，而是 PyCharm 友好的控制入口。文件开头有一组大写变量：

```python
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "mpc_official"
SCATTERING_BACKGROUND = "layered"
PORT_BOUNDARY_MODEL = "robin"
NEDELEC_DEGREE = None
MESH_TARGET_SIZE = None
INCIDENT_ANGLE_DEG = None
COMPUTE_POWER_METRICS = True
```

你在 PyCharm 里反复点 Run 时，主要改这些变量即可。`None` 表示继续使用 `src/common/config.py` 里的默认值。

当前推荐默认值是：

```text
scattered + layered + mpc_official
```

也就是先跑散射场法、分层背景、官方 `dolfinx_mpc` 约束后端。这个组合最稳，也最适合作为日常查看电场和 R/T 的入口。

## 2. 常见选择怎么改

只跑当前推荐的散射场法：

```python
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "mpc_official"
SCATTERING_BACKGROUND = "layered"
```

跑端口总场法：

```python
CALCULATION_METHOD = "port"
CONSTRAINT_BACKEND = "mpc_official"
PORT_BOUNDARY_MODEL = "robin"
```

串行对比官方 MPC 和手写矩阵消元：

```python
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "both"
```

修改网格、边元阶次、入射角：

```python
MESH_TARGET_SIZE = 25.0
NEDELEC_DEGREE = 2
INCIDENT_ANGLE_DEG = 15.0
```

如果这些变量保持 `None`，就读取 `src/common/config.py` 中的值。

## 3. 各 py 文件之间的调用关系

从 PyCharm 点 Run 后，代码调用关系是：

```text
src/main.py
  -> src/runners/run_cases.py
      -> src/solvers/solve_vector_maxwell.py      散射场法
      -> src/solvers/solve_port_maxwell.py        端口总场法
      -> src/geometry/mesh_builder.py             建网格
      -> src/constraints/floquet_constraint.py    Floquet 周期约束
      -> src/common/materials.py                  材料参数
      -> src/common/pml.py                        PML 张量
      -> src/postprocessing/postprocess.py        电场、VTU、图片输出
      -> src/postprocessing/power_metrics.py      R/T 和衍射级次
```

因此你平时只需要运行 `main.py`。其他文件用于阅读、调试或扩展，不作为日常入口。

## 4. 结果文件看哪里

每次运行会在 v2 目录下新建短名字结果目录，例如：

```text
results/2D_grating_sc_lay_p2_h25p0_t85p0_mpc_YYYYMMDD_HHMMSS/
```

如果只运行一个 case，`fields_for_paraview.vtu`、`power_metrics.json` 等文件会直接放在这个目录里。如果一次运行 `all` 或 `both` 产生多个 case，才会额外建立短子目录，例如 `sc_lay_mpc/`、`sc_lay_man/`、`port_robin_mpc/`。

MPI 并行运行时，目录名会额外带上进程数，例如：

```text
results/2D_grating_sc_lay_p2_h10p0_t15p0_mpc_np8_YYYYMMDD_HHMMSS/
```

这里的 `np8` 表示 `mpirun -n 8`。当前版本会由 rank0 统一决定这个目录，再广播给所有 rank，所以同一次 MPI 运行的 `.pvd`、各 rank 的 `.vtu`、`mesh.h5` 和 R/T 文件都会在同一个目录里。

串行运行时，重点看：

```text
fields_for_paraview.vtu
power_metrics.json
diffraction_orders.csv
run_summary.json
E_total_norm.png
material_domains.png
```

其中 `fields_for_paraview.vtu` 是 ParaView 直接打开的电场和材料数据文件，`power_metrics.json` 里有 `R_total`、`T_total`、`R_plus_T`。

MPI 并行运行时，重点看：

```text
fields_for_paraview_parallel.pvd
fields_for_paraview_rank0000.vtu
fields_for_paraview_rank0001.vtu
power_metrics.json
diffraction_orders.csv
run_summary.json
```

在 ParaView 里优先打开：

```text
fields_for_paraview_parallel.pvd
```

它会自动引用各个 rank 写出的 `.vtu` 分片。

## 5. 关于并行和 PyCharm

直接在 PyCharm 里点 `main.py`，通常是单进程运行。这已经会输出单文件 `.vtu` 和 R/T。

如果要真正使用多进程 MPI，需要通过 `mpirun` 启动 Python。v2 代码本身已经支持 MPI 路径，并且并行后处理会输出 `.pvd + rank*.vtu` 和 R/T；但 PyCharm 普通 Run 按钮默认不会自动变成 MPI 多进程。

也就是说：

```text
PyCharm 直接 Run main.py       -> 单进程，最方便，适合日常看结果
mpirun -n 2/4 ... src.main     -> 多进程，适合大网格和并行性能测试
```

## 6. 已验证的输出

我已在 Docker complex DOLFINx 环境中验证：

```text
python3 /work/fenics_vector_maxwell_floquet_demo_v2_parallel/src/main.py
```

可以直接运行，并输出：

```text
fields_for_paraview.vtu
power_metrics.json
diffraction_orders.csv
run_summary.json
```

同一轮默认算例中：

```text
Nedelec dofs = 17714
R_total      = 0.4911757993
T_total      = 0.5099242493
R_plus_T     = 1.0011000486
```

并行小网格冒烟测试也已验证，会输出：

```text
fields_for_paraview_parallel.pvd
fields_for_paraview_rank0000.vtu
fields_for_paraview_rank0001.vtu
power_metrics.json
```
