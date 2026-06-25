# Stage 4 3D DtN 总场端口

## 2026-06-25 更新：最终采用的 auxiliary 符号口径

本轮实跑后确认，3D DtN 第一版必须和 2D 端口保持同构的 auxiliary 结构：

```text
auxiliary unknown a_j = 端口总场在第 j 个模态上的投影

FEM equation:
  A_fem E + q_j ell_j a_j = b

Modal equation:
  a_j - (1/A_cell) ell_j^H E = 0

Top incident source:
  b_top = -2i beta_0 E_inc 的等价边界向量
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
