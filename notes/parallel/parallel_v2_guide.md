# v2 并行版本说明

这个文件夹是第二版代码：`fenics_vector_maxwell_floquet_demo_v2_parallel`。旧版 `fenics_vector_maxwell_floquet_demo` 没有被修改，可以继续作为串行参考版使用。

## 1. 这版主要解决什么

旧版代码的核心目标是把二维矢量 Maxwell、Floquet 周期边界、PML、端口法和反射透射率后处理跑通。它更适合学习、验证和小规模扫描。

v2 的目标是为后续大规模并行和未来 3D 扩展铺路。当前已经完成的重点是：

- 重新整理源码目录，不再把所有 Python 文件堆在同一个 `src` 下；
- 修复 MPI 下 `mesh.xdmf` 写入的集合通信问题；
- 重写 Floquet 约束构造，使 `dolfinx_mpc.MultiPointConstraint.add_constraint` 可以在 MPI 下使用；
- 让散射场法 `scattered + layered + mpc_official` 可以用 `mpirun -n 2` 跑通；
- 让端口总场法中的 Robin 端口 `port + robin + mpc_official` 可以用 `mpirun -n 2` 跑通；
- 保留旧的串行 manual 和 DtN 功能，但 MPI 下不再误跑这些串行路径。

## 2. 新的源码分类

v2 的源码按功能分成几类：

```text
src/common/
  config.py              参数、几何尺寸、材料、波长、入射角
  materials.py           分区介电常数
  pml.py                 PML 复坐标变换和 Maxwell 张量
  output_paths.py        结果文件夹命名

src/geometry/
  mesh_builder.py        Gmsh 网格生成和 DOLFINx mesh 导入

src/constraints/
  floquet_constraint.py  Floquet 周期边界约束，含 MPI 版本

src/solvers/
  solve_vector_maxwell.py  散射场 Maxwell 求解器
  solve_port_maxwell.py    端口总场 Maxwell 求解器

src/postprocessing/
  postprocess.py         场输出、ParaView/VTX/图片
  power_metrics.py       反射率、透射率和衍射级次后处理

src/runners/
  run_cases.py           真正的批量运行器

src/tools/
  inspect_environment.py 环境检查
  inspect_mpc_api.py     dolfinx_mpc API 检查
  diagnose_pml_fields.py PML 场诊断
```

顶层 `src` 现在只保留一个主入口 `src/main.py`，它会调用 `src/runners/run_cases.py`。其他 Python 文件都按功能放入上面的子目录，避免以后继续扩展时所有代码都堆在一个文件夹里。

## 3. 并行 Floquet 约束怎么做

旧版手写 Floquet 约束的思路是：

```text
右边界自由度 = exp(i kx period_x) * 左边界自由度
```

串行时，程序能一次看到左边界和右边界的所有 facet，所以可以直接按 y 坐标配对。

MPI 并行时，每个进程只拥有一部分网格。某个进程看到的左边界 facet 数量和右边界 facet 数量可能不同。因此 v2 改成：

1. 每个 rank 先只收集自己本地左、右 Floquet facet 的 y 坐标；
2. 所有 rank 用 `allgather` 交换这些 y 坐标，得到全局统一的配对顺序；
3. 所有 rank 按同样的 y-key 顺序调用 `locate_dofs_topological`，避免集合调用次数不一致导致 MPI 卡住；
4. 所有 rank 按同样顺序构造探针函数，得到 H(curl) 边元自由度之间的变换矩阵；
5. 每个 rank 只把自己拥有的右边界自由度作为 slave；
6. 左边界 master 使用全局自由度编号和 owner rank；
7. 把 `slaves, masters, coefficients, owners, offsets` 传给 `dolfinx_mpc.MultiPointConstraint.add_constraint`。

数学上仍然是 Floquet 条件：

```text
E(x + L, y) = exp(i kx L) E(x, y)
```

其中 `L = period_x`。不同的是，v2 把这个关系写成适合 MPI 分布式自由度的形式。

## 4. 已通过的测试

以下测试已经在 Docker 里的复杂 PETSc/DOLFINx 环境中实际运行通过。

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --help
```

串行散射场 MPC：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend mpc_official \
  --mesh-target-size 0.05 \
  --nedelec-degree 1 \
  --scattering-background layered
```

串行 manual 验证版：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend manual \
  --mesh-target-size 0.05 \
  --nedelec-degree 1 \
  --scattering-background layered
```

MPI 散射场，一阶边元：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend mpc_official \
  --mesh-target-size 0.05 \
  --nedelec-degree 1 \
  --scattering-background layered
```

MPI 散射场，二阶边元：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend mpc_official \
  --mesh-target-size 0.05 \
  --nedelec-degree 2 \
  --scattering-background layered
```

MPI 端口 Robin：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation port \
  --constraint-backend mpc_official \
  --port-boundary-model robin \
  --mesh-target-size 0.05 \
  --nedelec-degree 1
```

MPI all/both 小测试：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation all \
  --constraint-backend both \
  --port-boundary-model all \
  --mesh-target-size 0.05 \
  --nedelec-degree 1 \
  --scattering-background layered
```

MPI 下程序会自动只运行可并行的 `mpc_official` 和 Robin 端口，不会误跑串行 manual 和 DtN。

## 5. 并行计算最重要的部分

对这个 Maxwell 算例来说，并行计算最核心的不是画图，而是前面的有限元求解链条：

1. **分布式网格和自由度**：每个 MPI rank 只保存一部分单元、facet 和 Nedelec 自由度。
2. **并行装配矩阵和右端项**：每个 rank 装配自己负责的单元积分，再由 PETSc 合成分布式线性系统。
3. **并行 Floquet 约束**：右边界 slave 自由度可能分布在不同 rank 上，左边界 master 也可能属于别的 rank，所以必须记录 master 的全局编号和 owner rank。
4. **并行线性求解**：真正耗时、真正吃内存的通常是 PETSc KSP/PC 对复数 Maxwell 矩阵的求解。自由度越大，这一步越关键。
5. **内存容量**：并行不仅为了更快，也为了把矩阵和因子分解/预条件器分摊到多个进程，避免单进程内存不够。

所以你的理解大体是对的：对于现在的二维中等规模算例，最值得并行的是求解 `E_scat` 或 `E_total` 的过程。求完以后，如果场数据不大，完全可以单进程写 `.vtu`、画图、计算 R/T。

但有一个需要提前纠正的地方：当以后进入更细网格或 3D 时，后处理也不能永远假设“全部收集到一个进程”。大规模情况下，单进程收集完整电场会带来内存和 I/O 瓶颈。更稳妥的做法是：

- 场数据用并行格式写出，例如当前 MPI 路径里的 `.bp`；
- R/T 这类标量指标用“各 rank 局部积分或局部采样，再 MPI reduce 汇总”的方式计算；
- 只有在数据量确实很小时，才把结果收集到单进程生成单文件 `.vtu` 或 PNG。

## 6. 串行和并行耗时对比

为了看并行本身的收益，我用同一个较大自由度案例做了计时。这里关闭了绘图和 R/T 后处理，只比较网格生成、Floquet 约束、矩阵装配和 PETSc 求解主路径。

测试设置为：

```text
formulation          = scattered
scattering_background = layered
constraint_backend   = mpc_official
mesh_target_size     = 0.015
nedelec_degree       = 2
incident_angle_deg   = 15
cells                = 9680
N1curl dofs          = 48722
```

实际计时结果：

| 运行方式 | 总自由度 | wall time | 相对串行加速 |
|---|---:|---:|---:|
| 串行 `-n 1` | 48722 | 26.01 s | 1.00x |
| MPI `-n 2` | 48722 | 10.39 s | 2.50x |
| MPI `-n 4` | 48722 | 7.92 s | 3.28x |

这个结果说明 `mpc_official` 路径已经能从 MPI 中获得实际收益。它不是完美线性加速，因为网格生成、MPC 约束交换、直接求解器/预条件器、以及 MPI 通信都有固定开销；但对接近 5 万自由度的二维案例，2 进程和 4 进程已经明显快于单进程。

## 7. 当前仍然串行的部分

### 7.1 manual 后端

manual 后端使用：

```text
A_reduced = C^H A C
```

然后用 SciPy SuperLU 解线性方程。这是串行验证版，不适合 MPI。

### 7.2 DtN Fourier 端口

DtN 端口不是多点约束，而是非局部边界算子。它需要把端口边界上的场展开为 Floquet 级次：

```text
E(x) = sum_m E_m exp(i alpha_m x)
```

然后每个级次乘以自己的传播常数或导纳，再组装回边界矩阵。旧版实现是 PETSc 转 SciPy CSR 后加 Fourier 外积矩阵，所以仍然是串行路径。

真正并行 DtN 的合理路线是：

1. 先用 `dolfinx_mpc.assemble_matrix` 得到已经考虑 MPC 的 PETSc 矩阵；
2. 在 PETSc 分布式矩阵上加入 DtN 的低秩非局部边界块；
3. 用 PETSc KSP 并行求解；
4. 再做 `mpc.backsubstitution` 恢复完整场。

这一步目前还没有作为稳定功能加入。

### 7.3 反射率和透射率后处理

MPI 下已经补充了 `power_metrics.py` 的分布式点采样。做法不是把完整电场全部收集到一个进程，而是让每个 rank 对同一组探针点查找自己拥有的单元；能找到单元的 rank 负责局部求值，然后用 `allgather` 汇总成完整探针线，再做 Floquet 投影。因此并行运行现在也会输出：

```text
power_metrics.json
diffraction_orders.json
diffraction_orders.csv
```

这条路径适合当前二维后处理。未来 3D 大规模模型如果要进一步优化，可以把 `allgather` 改成更精细的 owner-only gather 或局部积分再 reduce。

## 8. 输出文件说明

串行运行时，仍会输出旧版的 PNG、单文件 VTU、JSON、CSV 等文件：

```text
fields_for_paraview.vtu
power_metrics.json
diffraction_orders.csv
run_summary.json
```

MPI 运行时，v2 优先输出并行友好的：

```text
E_inc.bp
E_scat.bp
E_total.bp
fields_for_paraview_parallel.pvd
fields_for_paraview_rank0000.vtu
fields_for_paraview_rank0001.vtu
power_metrics.json
diffraction_orders.csv
```

`.bp` 是 ADIOS2/VTX 格式，可以在 ParaView 中打开。为了照顾你更习惯的 `.vtu` 工作流，MPI 下还会让每个 rank 写一个局部 `.vtu`，并由 rank0 写一个集合文件：

```text
fields_for_paraview_parallel.pvd
```

在 ParaView 中优先打开这个 `.pvd` 文件，它会自动加载各个 rank 的 `.vtu` 分片。MPI 下暂时不生成 PyVista 的 PNG 图片，因为并行图片需要额外 gather 或离屏渲染策略；场数据和 R/T 指标已经可以直接输出。

### 8.1 8 进程输出目录修正

曾经在 8 进程运行时出现过 HDF5 报错，典型信息是：

```text
MPI_File_open failed
mesh.h5 does not exist
```

根因不是 Maxwell 求解器，也不是 Floquet 约束，而是结果目录选择逻辑：早期版本让每个 MPI rank 自己调用 `unique_run_dir()`。8 个 rank 同时抢唯一目录名时，可能分别得到：

```text
2D_grating_..._20260612_010509/
2D_grating_..._20260612_010509_02/
2D_grating_..._20260612_010509_03/
...
```

这样并行写 `mesh.h5` 时，每个 rank 认为文件在不同目录，HDF5 集合 I/O 就会报错，后续 `.vtu` 也会分散到多个文件夹。

当前已经修正为：rank0 先决定唯一结果目录，然后通过 MPI broadcast 发给所有 rank。并行目录名还会带进程数，例如：

```text
2D_grating_sc_lay_p2_h0p01_t15p0_mpc_np8_YYYYMMDD_HHMMSS/
```

因此同一次 8 进程运行中，所有输出都会集中在同一层：

```text
fields_for_paraview_parallel.pvd
fields_for_paraview_rank0000.vtu
...
fields_for_paraview_rank0007.vtu
mesh.h5
mesh.xdmf
power_metrics.json
run_summary.json
```

我已实际验证 `mpirun -n 8`、`nedelec_degree=2`、`mesh_target_size=0.01` 可以正常运行，无 HDF5 报错，输出目录为：

```text
results/2D_grating_sc_lay_p2_h0p01_t15p0_mpc_np8_20260612_010910/
```

### 8.2 内存优化记录

当前版本还做了两类和内存有关的优化。

第一类是 DtN 端口投影向量。早期代码会把每个端口、每个衍射级次的 `ell` 保存成完整 dense 向量，长度等于全局自由度数。现在改成压缩格式：

```text
indices + values
```

只保存端口边界相关的非零自由度。端口矩阵外积、入射源项和 DtN 端口 R/T 后处理都复用这份压缩数据。

第二类是 DtN 端口矩阵装配。早期代码每个级次生成一个稀疏矩阵后反复相加；现在先收集所有级次的 COO 三元组：

```text
rows / cols / data
```

最后一次性构造 `A_port`，减少中间稀疏矩阵副本。

另外，ParaView 后处理现在只对 DG 可视化空间调用一次 `plot.vtk_mesh(V_dg)`，然后分别读取 `E_inc`、`E_scat`、`E_total` 的系数数组。这样输出内容不变，但避免为三个场重复构造同一份 VTK 网格拓扑和坐标。

需要注意：`manual` 后端仍然是串行验证路线，它要构造约束降阶系统 `C^H A C` 并用 SuperLU 解线性方程。这个后端适合验证 official MPC、检查 DtN 公式和小中型算例，不适合作为真正的大规模并行求解器。

## 9. 后续并行化路线

下一步如果继续推进，我建议按这个顺序：

1. 把 DtN 端口重写成 PETSc 分布式低秩边界算子；
2. 如果以后需要单文件 VTU，可以增加 rank0 gather 写出版本，但大模型更推荐 `.pvd + rank*.vtu` 或 `.bp`；
3. 给 PyVista PNG 增加可选 gather 渲染，主要用于小模型快速预览；
4. 把 2D 的并行约束经验迁移到未来 3D：两个周期方向、完整三维 H(curl)、二维 Floquet 级次 `(m,n)`。

## 10. 快捷脚本

v2 还提供了一个 MPI 示例脚本：

```bash
fenics_vector_maxwell_floquet_demo_v2_parallel/run_demo_mpi.sh
```

默认使用 `MPI_PROCS=2`，运行 v2 中已经验证过的并行安全组合。需要改进程数时可以设置环境变量：

```bash
MPI_PROCS=4 fenics_vector_maxwell_floquet_demo_v2_parallel/run_demo_mpi.sh
```
