# Stage 1：3D 空气盒子快速运行指南

这个文件对应四步路线里的第一步：先建立一个最小 3D 全矢量 Maxwell 求解框架，并用均匀空气盒子里的解析平面波检查它。

## 运行哪个文件

原来的 2D 光栅入口仍然是：

```text
src/main.py
```

新的 3D 空气盒子入口是：

```text
src/main_3d_airbox.py
```

这样做的原因是：2D 程序不改名、不搬家、不打断；3D 学习路线从独立入口开始，后续再逐步加 Floquet、PML、benchmark 和衍射级后处理。

## PyCharm 里怎么改参数

打开 `src/main_3d_airbox.py`，主要改这几个大写变量：

```python
AIRBOX3D_CASE = "both"        # "normal", "oblique", or "both"
NEDELEC_DEGREE = 2
VISUALIZATION_DEGREE = 2
MESH_TARGET_SIZE = 0.14
UNIQUE_OUTPUT = True
```

建议刚开始保持默认值。默认会跑两个测试：

```text
normal  ：k = (0, 0, -k0)，p = (1, 0, 0)
oblique ：一个简单斜入射方向，偏振选成和 k 垂直
```

## 命令行怎么跑

在 Docker/DOLFINx 环境中可以运行：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case both
```

只跑正入射：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case normal
```

只跑斜入射：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case oblique
```

## 输出看哪里

结果会写到类似下面的目录：

```text
results/3D_airbox_stage1_normal_oblique_p2_h0p14_YYYYMMDD_HHMMSS/
```

如果跑 `both`，里面会有两个子目录：

```text
airbox3d_normal/
airbox3d_oblique/
```

每个子目录里重点看：

```text
run_summary.json
solver_log.txt
fields_3d_for_paraview.vtu
```

在 ParaView 里打开：

```text
fields_3d_for_paraview.vtu
```

里面包含：

```text
E_real, E_imag, E_abs
E_exact_real, E_exact_imag, E_exact_abs
E_error_real, E_error_imag, E_error_abs
eta0_H_real, eta0_H_imag, eta0_H_abs
H_SI_A_per_m_real, H_SI_A_per_m_imag, H_SI_A_per_m_abs
```

`eta0_H` 是归一化磁场，和电场同量级，适合做数值检查。`H_SI_A_per_m` 是按 SI 单位换算后的磁场。

## 验收看什么

先看 `solver_log.txt` 或 `run_summary.json`：

```text
PETSc ScalarType
mesh cells
3D N1curl dofs
solver residual norm
relative_max_abs_E_error
relative_max_abs_eta0_H_error
poynting_direction_cosine
paraview_file
```

`poynting_direction_cosine` 越接近 1，说明平均能流方向越接近设定的传播方向。

`relative_max_abs_E_error` 不是机器零，因为解析平面波不是有限元空间里的精确多项式；网格变细或 Nédélec 阶数提高后，它应该下降。
