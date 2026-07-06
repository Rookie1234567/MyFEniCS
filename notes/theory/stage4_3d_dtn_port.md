# Stage 4 3D DtN 总场端口

## 2026-07-06 更新：official R/T/A 来自 DtN port modal amplitudes

当前 Stage 4 `dtn_port + auxiliary` 主线的官方功率口径已经统一为：

```text
power_source = dtn_port_modal_amplitudes
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
```

辅助未知量仍按总场投影理解：

```text
top outgoing amplitude    = auxiliary_total_projection - incident_projection
bottom outgoing amplitude = auxiliary_total_projection
```

体吸收闭合为：

```text
energy_closure_error_dtn_port_modal_volume
  = R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total - 1
```

E/H Fourier probe、E-only Fourier probe 和 sampled net flux 现在只保留为 diagnostic：

```text
diagnostic_eh_fourier_probe
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

注意：`T_total_dtn_port_modal` 的参考面是 bottom physical port plane。对有损 substrate，不同计算域高度会改变 bottom port plane，因此 70 / 110 / 130 / 150 nm height scan 中 `T_total` 随高度变化是当前参考面定义下的预期结果。若要比较同一物理界面的透射，应新增统一 reference plane 或界面处外推后处理。

详细记录见：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md
```

## 2026-06-25 更新：当前 DtN 端口实现口径

当前 Stage 4 正式主线仍是总场 DtN 端口：

```text
unknown = E_total
top port = incident Floquet fundamental + outgoing reflected orders
bottom port = outgoing transmitted orders
x/y side = Floquet MPC
z top/bottom = Fourier-DtN auxiliary modal unknowns
PML = 不用于 dtn_port 主线
```

实现上，辅助变量保存端口总场投影；功率输出时：

```text
top outgoing amplitude    = total_projection - incident_projection
bottom outgoing amplitude = total_projection
R/T                       = outgoing modal power / incident modal power
```

MPI 后处理注意：

```text
并行运行不再写 3D VTX .bp，因为当前容器下 ADIOS2/VTXWriter 可能触发 BUS error。
并行 ParaView 请打开 fields_3d_for_paraview_parallel.pvd。
```

网格注意：

```text
lambda0 = 13.5 nm 时，h=10 nm 太粗，不作为物理验收。
当前更可信的 flat sanity 是 h=2.5 nm：R/T/R+T = 6.04e-4 / 0.9993956 / 1.0。
```

## 2026-06-25 更新：DtN 弱式符号与端口装配性能修正

本轮重新检查了 3D curl-curl 弱式的边界项号。对内部体积分部后，`a(E,v)` 本身等于边界上的 `n x curl(E)` 贡献，因此把出射 DtN 牵引项移到左端时应写成：

```text
FEM equation:
  A_fem E - q_j ell_j a_j = b

Modal equation:
  a_j - (1/A_cell) ell_j^H E = 0

Top incident source:
  b_top = +2i beta_0 E_inc 的等价边界向量
```

反射/透射幅值仍按总场投影读取：

```text
top outgoing amplitude    = top total projection - incident projection
bottom outgoing amplitude = bottom total projection
```

同时优化了辅助模态装配：

```text
1. 每个 (side,m,n) 只装配一次 x/y 表面分量；
2. 同一 (side,m,n) 的两个偏振用线性组合得到 trace 和 traction；
3. 表面 form 使用 fem.Constant 更新 alpha/gamma/kz，相同 form 不再反复重建。
```

本轮实测：

```text
block grating, h=5, np=4, auto_propagating:
  DtN modes = 1068
  stage4_dtn_port_assembly_and_solve = 12.210 s
  stage4_dtn_modal_loop_seconds      = 2.431 s
  R/T/R+T = 0.366105 / 0.633895 / 1.000000

flat, n_sub=1.0, h=2.5, np=8:
  R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000
```

注意：`stage4_dtn_port_assembly_and_solve` 包含基础矩阵装配、端口装配、矩阵 finalize、直接求解和回代。若它仍然很长，应优先看 `dtn_port_power_metrics_3d.json` 里的细分字段；例如 h=2.5 flat case 中主要耗时是 `stage4_dtn_linear_solve_seconds`，不是端口模态装配。

## 2026-06-25 更新：最终采用的 auxiliary 符号口径

本轮实跑后确认，3D DtN 第一版必须和 2D 端口保持同构的 auxiliary 结构：

```text
auxiliary unknown a_j = 端口总场在第 j 个模态上的投影

FEM equation:
  A_fem E - q_j ell_j a_j = b

Modal equation:
  a_j - (1/A_cell) ell_j^H E = 0

Top incident source:
  b_top = +2i beta_0 E_inc 的等价边界向量
```

反射/透射功率不是直接拿 top auxiliary，而是：

```text
top outgoing amplitude    = top total projection - incident projection
bottom outgoing amplitude = bottom total projection
```

这个口径已通过第一轮验证：

```text
flat, n_sub=1.0, h=2.5:
  R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000

flat, n_sub=1.45, h=2.5:
  R/T/R+T = 2.061463e-02 / 9.793854e-01 / 1.000000

block grating, h=5, auto_propagating:
  DtN modes = 1068
  R/T/R+T = 3.661053e-01 / 6.338947e-01 / 1.000000
```

早期尝试中把 auxiliary 定义成“出射幅值”会导致 flat-layer 端口不透射，`R+T` 大幅错误；这一路径已放弃。

## 2026-06-25 初版：为什么新增 dtn_port 主线

Stage 4 真实 3D 周期光栅当前不再把上下 PML 分支作为可信 R/T 主线。原因是此前 EUV block grating 中，即使线性系统残差很小，内部 probe 面分解仍出现 `R+T` 明显大于 1 的结果；这说明问题不能只靠后处理 clip 或调 PML 参数掩盖。

新的主线是：

```text
stage4_boundary_model = "dtn_port"
stage4_dtn_order_policy = "auto_propagating"
stage4_dtn_assembly = "auxiliary"
```

它的物理口径是总场法：

```text
1. 未知量直接是 E_total。
2. 计算域只包含物理 air/substrate/grating，不加 top/bottom PML。
3. x/y 方向继续使用 Floquet 周期约束。
4. top port 注入向下传播的入射 Floquet 基模。
5. top/bottom port 对所有传播出射衍射级施加 Fourier-DtN 条件。
6. R/T 从端口模态幅值计算，不再从内部 probe 平面拟合。
```

## 模态目录

3D 周期端口的横向波矢为：

```text
alpha_m = kx + 2*pi*m/Lx
gamma_n = ky + 2*pi*n/Ly
```

在介质折射率 `n` 中：

```text
beta_mn = sqrt((n*k0)^2 - alpha_m^2 - gamma_n^2)
```

平方根分支选择非负传播/衰减方向。第一版 `auto_propagating` 至少包含 top/bottom 介质中全部传播级，避免 EUV 小波长、多传播级场景被 `diffraction_zero_order_only` 误截断。

偏振基：

```text
kt = (alpha_m, gamma_n)
kt = 0 时使用 x/y 两个线偏振
kt != 0 时使用 s/p 两个横向偏振
```

所有模态目录由 `src/common/modes_3d.py` 生成，DtN 装配和 diffraction 后处理复用同一套函数，避免两处公式漂移。

## Auxiliary DtN 装配口径

第一版不做 dense 外积端口矩阵，而是为每个出射端口模态增加一个 auxiliary unknown。概念上可以理解为：

```text
E_t on port = E_inc,t + sum_j a_j e_j,t
n x curl(E) on port = n x curl(E_inc) + sum_j a_j n x curl(e_j)
```

有限元块仍由原来的 curl-curl Maxwell 弱式给出；每个 auxiliary unknown 通过端口 trace 投影和牵引向量与 FEM unknown 耦合。这样矩阵保持稀疏块结构，后续也方便接真正的 modal port。

## 功率和验收

每个传播模态的单位振幅功率用：

```text
P_j = 0.5 * Re(E_j x conj(H_j)) · n_out * Lx * Ly
```

端口输出：

```text
dtn_port_power_metrics_3d.json
dtn_port_diffraction_orders_3d.json
dtn_port_diffraction_orders_3d.csv
dtn_auxiliary_amplitudes_3d.json
```

lossless 材料的硬判断：

```text
R_total + T_total <= 1 + tolerance
```

如果超过容差，summary 必须标记失败，不能把结果当作可信物理结果。

## 必须优先验证的案例

```text
1. stage4_flat_layer_sanity + dtn_port
   无 grating/source，应回到 Fresnel R/T，且 R+T≈1。

2. n_grating == background 的零扰动 grating
   应连续回到 flat-layer。

3. 默认 block grating
   先 h=5 nm，再 h=2.5 nm；记录 R/T、A_balance、场分布和 MPI 一致性。

4. MPI np=1/2/4/8/16
   比较 R/T、主要辅助模态幅值、max|E|。
```

截至本记录，代码已通过本机语法检查，但尚未完成 Docker/DOLFINx 运行时验证。下一轮必须先验 flat-layer，再进入真实 grating。
