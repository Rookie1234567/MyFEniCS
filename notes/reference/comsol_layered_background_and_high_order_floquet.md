# COMSOL 对齐修改与高阶 Floquet 边界说明

本次修改保留了原来的算例版本，同时新增了一个更接近 COMSOL 周期端口设置的背景场版本，并修复了 Nedelec 边元阶次不能调高的问题。

## 1. 保留的旧版本

旧版本仍然可以使用：

```text
scattering_background = "air"
```

它的散射场方程是：

```text
curl curl(E_scat) - k0^2 epsilon_actual E_scat
  = k0^2 (epsilon_actual - epsilon_air) E_air
```

其中 `E_air` 是空气中的解析平面波。

这个版本的左端确实考虑了真实材料，包括空气、基座和光栅。但它的背景场是全空气平面波，所以右端项会把整块基座也看成相对于空气背景的扰动。

## 2. 新增的分层背景版本

新增版本使用：

```text
scattering_background = "layered"
```

它把“平坦空气/基座结构”作为背景。背景场写成：

```text
E_bg = E_inc + E_ref        在空气侧
E_bg = E_trn                在基座侧
```

这里 `E_ref` 和 `E_trn` 使用平坦空气/基座界面的 Fresnel 反射和透射关系计算。然后求解：

```text
curl curl(E_scat) - k0^2 epsilon_actual E_scat
  = k0^2 (epsilon_actual - epsilon_background) E_bg
```

其中：

```text
epsilon_background = epsilon_air        空气区和光栅凸起所在高度
epsilon_background = epsilon_substrate  基座区
```

这样平坦基座本身不再作为散射源，主要散射源来自光栅凸起：

```text
epsilon_grating - epsilon_air
```

这比旧版本更接近 COMSOL 中“上方周期端口入射、下方周期端口出射、左右 Floquet”的物理定义。

## 3. 仍然和 COMSOL 不完全相同的地方

这个新增版本不是完整的 COMSOL 周期端口复刻。COMSOL 的周期端口会做模式分解，自动处理反射、透射和可能存在的衍射级次。

当前新增版本做的是“平坦分层背景 + 光栅扰动散射”。它通常会比全空气背景更合理，但如果要和 COMSOL 严格逐点一致，下一步应继续实现真正的 Floquet 模态端口边界，或者至少输出反射/透射级次功率来对比。

## 4. 高阶 Nedelec 边元为什么之前不能调

之前的 Floquet 约束代码里有一个一阶假设：

```text
每条边界 facet 只有 1 个 H(curl) 自由度
```

这对一阶 Nedelec 成立，但对二阶或更高阶不成立。高阶 Nedelec 在同一条边上会有多个切向矩自由度。

现在的约束代码不再假设一条边只有一个自由度，而是对每一对左右 Floquet 边构造局部多项式探针场，反推出：

```text
右边界自由度 = Floquet 相位 * 左边界自由度的线性组合
```

这个线性组合通过 `coefficients` 和 `offsets` 存储，因此官方 `dolfinx_mpc` 低层接口和手写矩阵消元版本都可以共用。

## 5. 运行方式

旧的全空气背景版本：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background air"
```

新的分层背景版本：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered"
```

使用二阶 Nedelec 边元：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered --nedelec-degree 2"
```

如果二阶算例太慢，可以先用较粗网格检查流程：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered --nedelec-degree 2 --mesh-target-size 60.0 --visualization-degree 2"
```

## 6. 本次验证结果

一阶分层背景版本已验证：

```text
constraint_backend = both
scattering_background = layered
mesh_target_size = 40.0
visualization_degree = 2

官方 MPC 和手写矩阵版本均运行成功。
Floquet 探针重构误差约为 5.9e-16。
Floquet mismatch 约为 1e-15。
```

二阶 Nedelec 分层背景版本已验证：

```text
constraint_backend = both
scattering_background = layered
nedelec_degree = 2
mesh_target_size = 60.0
visualization_degree = 2

官方 MPC 和手写矩阵版本均运行成功。
Floquet 探针重构误差约为 1.6e-15。
官方 MPC 与手写矩阵版本的 max(|E_total|) 差异约为 4.8e-14。
```

结果目录：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_layered_mpc_official
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_layered_manual
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_layered_p2_mpc_official
fenics_vector_maxwell_floquet_demo_v2_parallel/results/air_substrate_grating_layered_p2_manual
```

## 7. 2026-06-09 补充：真正的端口总场法入口

本文前面说“下一步应继续实现真正的 Floquet 模态端口边界”。现在已经先补上一个端口总场法框架：

```text
--formulation port_total
```

它和 `scattering_background = "layered"` 不是同一个东西。

`layered` 仍是散射场法：先构造平坦空气/基座背景场，再求光栅扰动引起的 `E_scat`。

`port_total` 则是端口法：直接求 `E_total`，上端口输入入射 Floquet 基模，下端口作为出射端口，左右边界仍是 Floquet 周期条件。

运行命令：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend both"
```

如果想一组里同时跑旧散射场法和新端口法：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation both --constraint-backend manual --scattering-background layered"
```

端口法默认不使用上下 PML；若希望端口放在 PML 外边界，可以加：

```text
--port-use-pml
```

重要提醒：不加额外参数时，`port_total` 是单 Floquet 基模 Robin 端口。它比散射场背景法更接近 COMSOL 周期端口的“入射端口/出射端口”结构，但如果 COMSOL 端口启用了多个衍射级次，应使用多级次 Fourier 端口。

现在已补充一个可选的多级次 Fourier 端口：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend manual --port-order-count 1"
```

`--port-order-count 1` 表示端口里包含：

```text
m = -1, 0, +1
```

如果 COMSOL 周期端口里启用了更多 diffraction orders，就把这里的 `1` 增大。这个功能当前只支持 `manual` 后端，因为 Fourier 端口是非局部矩阵项，不能直接写成普通局部 UFL 边界积分后交给官方 `dolfinx_mpc.LinearProblem`。

不想写命令行时，直接在 `src/common/config.py` 里设置：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = 1
```

这样就是专门对照 COMSOL 周期端口的 DtN 总场版本。若想同时比较旧散射场法、Robin 端口和 DtN 端口，设为：

```python
calculation_method = "all"
constraint_backend = "both"
port_boundary_model = "all"
```

## 8. 和 COMSOL 对比时建议看的指标

现在每个算例会输出：

```text
power_metrics.json
diffraction_orders.csv
```

建议先比较：

```text
E_total_abs
R_total
T_total
R_plus_T
```

如果 COMSOL 周期端口启用了衍射级次，再逐项比较：

```text
R_order
T_order
reflected_Ex_phase
transmitted_Ex_phase
```

当前更接近 COMSOL Periodic Port 的版本是：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = 1
diffraction_order_count = 1
```

其中 `diffraction_orders.csv` 可以逐项对照 COMSOL 的 diffraction order 表。若 COMSOL 的入射功率归一化方式不同，先比较无量纲的 `R_order/T_order`，再确认入射场幅值或端口功率归一化。
