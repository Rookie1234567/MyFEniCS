## 2026-06-15 更新：TE 和吸收率

本文原来主要解释 TM，也就是：

```text
E = (Ex, Ey, 0)
H = (0, 0, Hz)
```

现在 `power_metrics.py` 会根据：

```python
cfg.polarization_type
```

自动选择 TM 或 TE 后处理。

TE 中：

```text
E = (0, 0, Ez)
H = (Hx, Hy, 0)
```

代码先恢复缩放磁场：

```text
Hx_scaled = dEz/dy / i
```

第 `m` 个 Floquet 级次满足：

```text
alpha_m = kx + 2*pi*m/period
beta_m = sqrt((k0*n)^2 - alpha_m^2)
```

向下波和向上波的关系是：

```text
Hx_scaled_down = - beta_m Ez_down
Hx_scaled_up   = + beta_m Ez_up
```

所以 TE 的上下行分解为：

```text
Ez_down = 1/2 (Ez_m - Hx_scaled_m / beta_m)
Ez_up   = 1/2 (Ez_m + Hx_scaled_m / beta_m)
```

TE 的模态功率因子为：

```text
P_m_scaled = period * 0.5 * Re(beta_m) * |Ez_m|^2
```

TM 的原公式仍然保持：

```text
Y_m = (k0*n)^2 / beta_m
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
P_m_scaled = period * 0.5 * Re(Y_m) * |Ex_m|^2
```

新增吸收字段：

```text
A_balance = 1 - R_total - T_total
A_volume = 0.5*k0^2*int Im(epsilon_r)*|E|^2 dOmega / P_inc
```

其中体积分只统计真实材料区：

```text
air/substrate/grating
```

不统计 PML。无损材料时 `A_volume` 应接近 0；如果 `A_balance` 和 `A_volume` 差很多，通常说明 R/T 后处理仍受探测线位置、网格、级次数或边界模型影响。

对于 DtN 端口法，除了水平探测线：

```text
power_metrics.json
```

还会输出端口面模态投影：

```text
dtn_port_power_metrics.json
```

后者复用了装配 DtN 端口矩阵时的压缩 Fourier 投影向量，通常更适合与 COMSOL 周期端口功率对比。

# 反射率、透射率和衍射级次后处理说明

本文说明当前项目如何从二维矢量 Maxwell 解 `E=(Ex,Ey)` 计算反射率、透射率和各个 Floquet 衍射级次功率。新版后处理不再只依赖 `Ex`，而是先由电场旋度恢复磁场的 `Hz` 分量，再用 Poynting 通量和上下行模态分解计算功率，因此比旧版更接近 COMSOL 周期端口的功率定义。

## 1. 为什么不能只看 Ex

最早的后处理做法是：在上、下两条水平探测线上采样 `Ex`，把 `Ex` 做 Fourier 投影，然后用平面波公式估计功率。这个方法能做快速诊断，但它有一个明显问题：功率流不是只由 `Ex` 决定，而是由电场和磁场共同决定。

时间平均 Poynting 矢量为：

```text
S = 1/2 Re(E x H*)
```

这里的 `*` 表示复共轭。二维 in-plane 模型里：

```text
E = (Ex, Ey, 0)
H = (0, 0, Hz)
```

所以 y 方向能流为：

```text
S_y = -1/2 Re(Ex Hz*)
```

如果只看 `Ex`，但没有同时看 `Hz`，就无法严格知道这部分场到底是向上传播还是向下传播，也无法做严格的能量守恒检查。

## 2. 如何从 E 得到 Hz

当前频域相位约定使用 `exp(-i omega t)`。Maxwell 方程给出：

```text
curl(E) = i omega mu H
```

二维时只有 z 向旋度：

```text
curl_z(E) = dEy/dx - dEx/dy
```

因此：

```text
Hz = curl_z(E) / (i omega mu)
```

在反射率和透射率中，分子和分母都会同时除以入射功率，所以公共常数 `1/(omega mu0)` 会抵消。代码里实际保存的是缩放后的：

```text
Hz_scaled = curl_z(E) / i
```

这不会影响无量纲的 `R` 和 `T`。

## 3. 在哪里做功率统计

代码自动选择两条水平探测线：

```text
top_probe_y     位于光栅上方的均匀空气区域
bottom_probe_y  位于下方均匀基座内部
```

不要在光栅旁边直接统计远场功率，因为那里有强近场和倏逝场。功率统计线必须放在横向均匀介质里，这样 Floquet 模态分解才有明确含义。

当前水平探测线默认放在 95% 位置，也就是尽量靠近“物理区域与 PML/端口的交界面”，同时仍然留在真实介质区域内：

```text
top_probe_y = grating_y_max + 0.95 * (physical_y_max - grating_y_max)
bottom_probe_y = substrate_y_max - 0.95 * (substrate_y_max - substrate_y_min)
```

这样做的目的很直接：让探测线尽可能远离光栅近场，同时不要进入 PML。PML 内场经过复坐标拉伸，不能再直接当作普通传播波做 Floquet 功率分解。

对应输出字段在：

```text
power_metrics.json
```

中可以看到：

```text
top_probe_y
bottom_probe_y
probe_position_fraction_from_structure_to_outer_interface
```

新版代码不再用点值有限差分计算 `dEx/dy`，而是用 UFL 直接构造：

```text
(dEy/dx - dEx/dy) / i
```

并把它插值到 DG 空间中。对应字段为：

```text
hz_reconstruction
hz_dg_degree
```

## 4. Floquet 衍射级次

左右边界满足 Floquet 准周期条件：

```text
E(x + period, y) = exp(i kx period) E(x, y)
```

因此端口截面上的场可以展开为：

```text
Ex(x, y_probe) = sum_m Ex_m(y_probe) exp(i alpha_m x)
Hz(x, y_probe) = sum_m Hz_m(y_probe) exp(i alpha_m x)
```

其中：

```text
alpha_m = kx + 2*pi*m/period
```

`m=0` 是基模，`m=-1`、`m=+1` 等是衍射级次。配置项：

```python
diffraction_order_count = N
```

表示后处理统计：

```text
m = -N, ..., -1, 0, 1, ..., N
```

如果 COMSOL 周期端口里启用了相同的衍射级次，建议让这里的 `diffraction_order_count` 与 COMSOL 保持一致。

## 5. 如何区分向下波和向上波

在某个均匀介质中，第 `m` 个 Floquet 级次的竖向波数为：

```text
beta_m = sqrt((k0 n)^2 - alpha_m^2)
```

对于传播级次，`beta_m` 为正实数；对于倏逝级次，`beta_m` 主要是虚数，远场不携带净功率。

定义缩放后的模态导纳：

```text
Y_m = (k0 n)^2 / beta_m
```

对向下传播波，有：

```text
Hz_m =  Y_m Ex_m
```

对向上传播波，有：

```text
Hz_m = -Y_m Ex_m
```

所以只要同时知道 `Ex_m` 和 `Hz_m`，就能把同一条线上的总场拆成向下和向上两部分：

```text
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
```

这一步就是新版后处理相对旧版最重要的改动。它不再靠“总 Ex 减去入射 Ex”来猜反射波，而是用 `Ex` 和 `Hz` 的相位关系直接判断能量传播方向。

## 6. 反射率和透射率

上方空气探测线：

```text
反射级次 = 向上传播的 Ex_up
```

下方基座探测线：

```text
透射级次 = 向下传播的 Ex_down
```

每个传播级次的功率权重为：

```text
P_m = period * 1/2 * Re(Y_m) * |Ex_m|^2
```

入射功率为：

```text
P_inc = period * 1/2 * Re(Y_inc) * |Ex_inc|^2
```

归一化后：

```text
R_m = P_reflected_m / P_inc
T_m = P_transmitted_m / P_inc
```

总量为：

```text
R_total = sum_m R_m
T_total = sum_m T_m
R_plus_T = R_total + T_total
energy_residual = 1 - R_total - T_total
```

对于无吸收材料、足够细的网格、足够多的传播级次、足够好的端口或 PML，理论上应该有：

```text
R_total + T_total = 1
```

如果小于 1，常见原因包括：

```text
1. 网格不够细，curl(E) 的数值导数误差较大
2. 探测线离结构太近，仍含有近场和倏逝场影响
3. 衍射级次数设置太少，漏统计了传播级次
4. PML 或 Robin 端口吸收/截断造成数值损失
5. 当前 2D 模型、边界模型和 COMSOL 周期端口并非完全同一个离散问题
```

## 7. 直接 Poynting 通量诊断

除了模态分解得到的 `R_total/T_total`，新版还输出直接通量诊断：

```text
top_flux_y_weighted
bottom_flux_y_weighted
top_outward_power_weighted
bottom_outward_power_weighted
net_outward_power_weighted
poynting_R_plus_T_from_net_flux
poynting_energy_residual
```

它们的作用是帮助判断误差来源。简单理解：

```text
top_flux_y_weighted       顶部探测线的 y 向 Poynting 通量
bottom_flux_y_weighted    底部探测线的 y 向 Poynting 通量
net_outward_power         上下两条线合计流出计算区域的净功率
```

如果场里只有一个从上方入射的波，那么：

```text
net_outward_power / incident_power = R + T - 1
```

所以：

```text
poynting_R_plus_T_from_net_flux = 1 + net_outward_power / incident_power
```

这个量是对 `R_total + T_total` 的独立检查。若二者差很多，说明模态投影、探测线或 `Hz` 数值导数还需要加密验证。

## 8. 输出文件

每个算例子目录都会输出：

```text
power_metrics.json
diffraction_orders.json
diffraction_orders.csv
```

这三个文件是“水平探测线法”的结果。它们适用于散射场法、Robin 端口法和 DtN 端口法，做法是在上方均匀空气区和下方均匀基座区各取一条水平线，再用 `Ex` 和由 `curl(E)` 恢复出的 `Hz` 拆分上下行波。

如果当前算例使用：

```python
calculation_method = "port"
port_boundary_model = "dtn"
```

还会额外输出一组“DtN 端口面法”的结果：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.json
dtn_port_diffraction_orders.csv
```

这组文件不再另找内部水平探测线，而是复用 DtN 端口矩阵装配时的边界积分投影向量，直接得到端口模态幅值，更接近 COMSOL Periodic Port 给出的 S 参数或 diffraction order power。

`power_metrics.json` 包含总量：

```text
R_total
T_total
R_plus_T
energy_residual_1_minus_R_minus_T
poynting_R_plus_T_from_net_flux
poynting_energy_residual
incident_power_weighted
reflected_power_weighted
transmitted_power_weighted
```

`diffraction_orders.csv` 包含每个级次：

```text
order
alpha
beta_top_real / beta_top_imag
beta_bottom_real / beta_bottom_imag
top_modal_admittance_real / top_modal_admittance_imag
bottom_modal_admittance_real / bottom_modal_admittance_imag
top_propagating
bottom_propagating
top_down_Ex_abs
top_up_Ex_abs
bottom_down_Ex_abs
bottom_up_Ex_abs
R_order
T_order
reflected_Ex_real / reflected_Ex_imag / reflected_Ex_abs / reflected_Ex_phase
transmitted_Ex_real / transmitted_Ex_imag / transmitted_Ex_abs / transmitted_Ex_phase
```

`dtn_port_diffraction_orders.csv` 的列名略有不同，因为它直接记录端口面上的总场 Fourier 系数：

```text
top_total_Ex_port_real / top_total_Ex_port_imag / top_total_Ex_port_abs
bottom_total_Ex_port_real / bottom_total_Ex_port_imag / bottom_total_Ex_port_abs
reflected_Ex_abs
transmitted_Ex_abs
R_order
T_order
```

其中：

```text
top_down_Ex_abs
```

应主要对应入射基模。如果 `m=0` 的 `top_down_minus_incident_abs` 很大，说明顶部探测线、边界条件或入射场归一化需要检查。

## 9. 与 COMSOL 对比时看什么

建议按这个顺序对比：

```text
1. E_total_abs，也就是 COMSOL 里的 normE 或 emw.normE
2. R_total 和 T_total
3. R_plus_T 是否接近 1
4. 每个衍射级次的 R_order/T_order
5. reflected_Ex_phase 和 transmitted_Ex_phase
```

如果 COMSOL 使用 Periodic Port，并启用了 diffraction orders，应让本项目的：

```python
port_dtn_order_count
diffraction_order_count
```

都和 COMSOL 保持一致。

更接近 COMSOL 周期端口的组合是：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = 1
diffraction_order_count = 1
```

如果只是想同时运行全部方法做互相印证，可以用：

```python
calculation_method = "all"
constraint_backend = "both"
port_boundary_model = "all"
```

## 10. 准确性应该如何验证

建议做三组检查。

第一组，后端一致性：

```text
scattered + mpc_official  与  scattered + manual
port robin + mpc_official 与  port robin + manual
```

同一物理模型下，二者的 `R_total/T_total/E_total_abs` 应该非常接近。如果差到 `1e-6` 甚至更大，就要先检查 Floquet 约束或矩阵消元。

第二组，能量守恒：

```text
R_total + T_total -> 1
poynting_R_plus_T_from_net_flux -> R_total + T_total
```

无吸收材料下，网格越细、端口越准确、级次数越足，这两个量越应该接近 1。

第三组，收敛性：

```text
mesh_target_size = 120.0
mesh_target_size = 80.0
mesh_target_size = 50.0
```

观察 `R_total/T_total/R_plus_T` 是否逐步稳定。只有网格收敛后，才适合与 COMSOL 做定量误差比较。

## 11. 本次实际验证结果

我在 Docker complex DOLFINx 环境中重新运行了新版后处理。

粗网格全组合：

```text
mesh_target_size = 120.0
visualization_degree = 1
```

结果目录：

```text
results/run_air_substrate_grating_all_bg_layered_port_all_dtn1_20260609_063301/
```

汇总结果：

```text
scattered layered official: R=0.022484523, T=0.920728371, R+T=0.943212894, Poynting=0.968234229
scattered layered manual:   R=0.022484523, T=0.920728371, R+T=0.943212894, Poynting=0.968234229
port robin official:        R=0.024468797, T=0.908128159, R+T=0.932596956, Poynting=0.957633032
port robin manual:          R=0.024468797, T=0.908128159, R+T=0.932596956, Poynting=0.957633032
port dtn manual:            R=0.024118213, T=0.899487852, R+T=0.923606065, Poynting=0.957428047
```

这个粗网格太粗，不能用来做最终能量守恒结论。它的主要价值是验证 official/manual 后端仍然一致。

随后我只对更接近 COMSOL 周期端口的 `port dtn manual` 做网格加密：

```text
mesh_target_size = 60.0:
R=0.021751048, T=1.014932528, R+T=1.036683576, Poynting=1.018692855

mesh_target_size = 40.0:
R=0.022157946, T=0.969313345, R+T=0.991471291, Poynting=0.992615839
```

`40.0 nm` 网格已经把 `R+T` 拉回到距离 1 约 `0.85%` 的范围，直接 Poynting 检查也在约 `0.74%` 范围内。说明新版功率统计是朝能量守恒方向收敛的；后续若要和 COMSOL 做定量比较，建议继续使用 `port dtn manual` 并把 `mesh_target_size` 进一步降到 `30.0` 或 `25.0`。

## 12. PML 复坐标更新后的默认精细运行

PML 公式改为官方 DOLFINx demo 复坐标形式后，我重新运行了当前默认配置：

```text
mesh_target_size = 15.0
nedelec_degree = 2
calculation_method = all
constraint_backend = both
port_boundary_model = all
```

结果目录：

```text
results/run_air_substrate_grating_all_bg_layered_port_all_dtn1_20260609_095504/
```

结果为：

```text
scattered layered official: R=0.022112910, T=0.979624581, R+T=1.001737492, Poynting=1.001842494
scattered layered manual:   R=0.022112910, T=0.979624581, R+T=1.001737492, Poynting=1.001842494
port robin official:        R=0.021927723, T=0.989427546, R+T=1.011355268, Poynting=1.002585068
port robin manual:          R=0.021927723, T=0.989427546, R+T=1.011355268, Poynting=1.002585068
port dtn manual:            R=0.022117491, T=0.980299708, R+T=1.002417199, Poynting=1.002577824
```

这组结果比粗网格更适合作为当前默认算例的参考。散射场法和 DtN 端口法均给出接近 1 的能量守恒检查；official/manual 后端在同一物理问题下仍一致。

## 13. DtN 端口面法如何计算 R/T

2026-06-15 后，DtN 端口法会同时给出两套 R/T；2026-06-16 辅助变量法加入后，auxiliary 路径还会多给出第三套直接模态幅值 R/T：

```text
power_metrics.json              水平探测线法
dtn_port_power_metrics.json     DtN 端口面法
dtn_auxiliary_power_metrics.json 辅助变量直接幅值法
```

水平探测线法仍然保留，因为它是所有求解方法共用的后处理，可以检查端口外的场分解是否和内部均匀区域一致。

DtN 端口面法只在 `port_boundary_model="dtn"` 时启用。它使用和 DtN 端口边界条件相同的 Floquet 展开：

```text
Ex(x, y_port) = sum_m Ex_m(y_port) exp(i alpha_m x)
alpha_m = kx + 2*pi*m/period
```

代码实现时没有再画一条采样线，而是复用装配 DtN 端口矩阵时已经算过的边界积分向量：

```text
ell_m,j = ∫_port exp(i alpha_m x) conj(phi_j,x) ds
```

有限元解写成：

```text
Ex = sum_j u_j phi_j,x
```

由于 Nedelec 基函数本身是实基函数，端口 Fourier 系数可以直接由：

```text
Ex_m = (1/period) sum_j u_j conj(ell_m,j)
```

得到。这个 `ell_m` 正是 DtN 端口矩阵里用于构造非局部端口算子的投影向量，因此后处理和端口边界条件使用的是同一套边界积分口径。

早期实现为了方便，曾经把每个 `ell_m` 都保存成完整 dense 向量。也就是说，即使只有端口边界上的少数自由度非零，也会保存长度等于全局自由度数的数组：

```text
ell_m_dense 长度 = N_dof
```

这在小网格里没什么问题，但大网格、多端口、多衍射级次时会浪费内存。假设有两个端口、`2N+1` 个级次、总自由度为 `N_dof`，dense 存储大约需要：

```text
2 * (2N+1) * N_dof * 16 bytes
```

现在代码改成只保存压缩向量：

```text
indices = ell_m 非零项所在的自由度编号
values  = ell_m 在这些自由度上的复数值
size    = 原始 dense ell_m 的长度，仅作诊断
cutoff  = 判断非零项时使用的阈值
```

端口矩阵外积、入射源项和 DtN 端口 R/T 后处理都复用同一份压缩数据：

```text
Ex_m = (1/period) sum_{j in indices} u_j conj(values_j)
```

因此结果的数学定义没有改变，但内存占用从“跟全局自由度数成正比”变成“跟端口边界相关自由度数成正比”。

如果使用：

```python
port_dtn_assembly = "auxiliary"
```

求解器会把每个选中端口级次的 `Ex_m` 直接作为辅助未知量：

```text
a_m = Ex_m = (1/period) ell_m^H u
```

后处理会同时保存：

```text
dtn_auxiliary_amplitudes.json
dtn_auxiliary_power_metrics.json
dtn_auxiliary_diffraction_orders.csv
```

`dtn_port_power_metrics.json` 是“求解完以后用 trace 向量重新投影”；`dtn_auxiliary_power_metrics.json` 是“直接读取线性系统里的辅助未知量”。它们使用同一个功率公式，所以小模型中应当一致。

上端口位于空气中，已知入射基模为：

```text
Ex_inc,0(x, y_top) = A cos(theta) exp(i kx x - i beta_top,0 y_top)
```

因此上端口第 `m` 级反射幅值为：

```text
R_amp,m = [Ex_top,m - delta_m0 A cos(theta) exp(-i beta_top,m y_top)]
          * exp(-i beta_top,m y_top)
```

这里的 `delta_m0` 表示只有 `m=0` 有外加入射波。`exp(-i beta_top,m y_top)` 是把端口面上的系数换算成统一参考相位的因子。

下端口没有外加向上入射波，因此第 `m` 级透射幅值为：

```text
T_amp,m = Ex_bottom,m * exp(i beta_bottom,m y_bottom)
```

然后每个传播级次的功率仍然用模态导纳归一化：

```text
Y_m = (k0 n)^2 / beta_m
P_m = period * 1/2 * Re(Y_m) * |amplitude_m|^2
```

所以：

```text
R_order,m = P_reflected,m / P_incident
T_order,m = P_transmitted,m / P_incident
R_total = sum_m R_order,m
T_total = sum_m T_order,m
```

注意：倏逝级次的复幅值仍会写入表格，但因为 `Re(Y_m)=0`，它们不计入总功率。

本次小网格验证使用：

```text
mesh_target_size = 80.0
nedelec_degree = 1
port_dtn_order_count = 1
diffraction_order_count = 1
```

结果目录：

```text
results/2D_grating_port_ptdtn_dtn1_p1_h80p0_t15p0_man_20260615_070608/
```

两种后处理结果为：

```text
水平探测线法，95% 位置：R=0.017253623, T=0.938810344, R+T=0.956063967
DtN 边界积分端口法：   R=0.016661748, T=0.983338252, R+T=1.000000000
```

这个对比说明：把水平探测线移动到远离光栅的 95% 位置后，通用探测线法有所改善；但在 DtN 端口法中，复用端口边界积分向量得到的模态幅值更接近端口功率定义。水平探测线法仍可作为独立诊断，但它更受 `Hz=curl(E)/i` 数值导数、采样线位置和网格粗细影响。
