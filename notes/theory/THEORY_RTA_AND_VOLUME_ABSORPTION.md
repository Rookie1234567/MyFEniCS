# R/T/A 与体吸收说明

## 四类功率口径

本项目 Stage 4 同时保留四类功率或吸收指标。它们服务的目的不同，不能混成一个没有来源说明的 `R_total/T_total/A_balance`。

| method | 角色 | 含义 |
|---|---|---|
| `port` | 主结果 | DtN port 辅助模态振幅直接给出的反射率 `R_port`、透射率 `T_port` 和能量余额 `A_port_balance = 1 - R_port - T_port`。 |
| `probe_eh_fourier` | 交叉检查 | 在上下 probe plane 上采样总场，用切向 E/H Fourier directional fitting 分离上下行波，得到 `R_probe`、`T_probe` 和 `A_probe_balance`。 |
| `net_flux` | 诊断 | 在 probe plane 上采样 Poynting 通量，得到边界净能流对应的 `R_flux/T_flux/A_flux`。它不分解衍射级次。 |
| `volume_absorption` | 吸收校验 | 在材料区域内积分 `Im(epsilon_r)|E_total|^2`，直接估计材料体吸收 `A_volume`，可分为 grating、substrate 和 total。 |

## A_balance 的含义

`A_balance = 1 - R - T` 是某个功率口径下的能量余额。它不是直接的材料体吸收积分。

在无损结构中，理想情况下 `A_balance` 应接近 0。在有损材料中，`A_balance` 可以解释为入射端口到出射端口之间没有以传播模态离开的功率余额，但它仍然依赖所用的 R/T 口径和边界后处理方式。

因此，本轮输出把 `port`、`probe_eh_fourier`、`net_flux` 和 `volume_absorption` 分开保存，并在 `power_summary.csv` 中显式标出 `method`、`role` 和 `source`。

## 体吸收积分

体吸收使用总电场：

```text
E_total = E_background + E_scattered
```

若求解器已经直接求总场，则直接使用该总场。不能只用 scattered field 计算材料吸收。

当前 3D Stage 4 采用的 code-unit 表达式为：

```text
P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV
A_volume = P_abs / P_inc
```

其中：

```text
epsilon_r = n^2
```

吸收项使用 `Im(epsilon_r)`，不是直接使用 `Im(n)`。

体积分只覆盖真实物理材料 tag：

```text
substrate
grating
```

PML cell 和空气 cell 不计入 material volume absorption。若某个区域不存在，例如 flat-layer 没有 grating cell，则该区域在 JSON 中输出 `null` 或 0，并写明 `status/reason`。

## 理想一致性关系

在网格、端口、probe plane 和归一化都足够一致时，期望看到：

```text
R_port ~= R_probe ~= R_flux
T_port ~= T_probe ~= T_flux
A_port_balance ~= A_probe_balance ~= A_flux ~= A_volume_total
R + T + A_volume_total ~= 1
```

这里的近似关系不是严格物理证明。它是数值后处理的一致性检查，尤其用于发现端口归一化、probe 采样、材料 tag 或体积分口径是否出现明显错误。

## 有吸收材料时的判断

对 lossy Si 等有吸收材料，不能要求：

```text
R + T ~= 1
```

更合理的检查是：

```text
R + T + A_volume_total ~= 1
```

同时仍需比较 `A_port_balance` 与 `A_volume_total`。如果两者不一致，应优先把它视为归一化、有限网格、probe 后处理或端口边界口径问题，而不是直接声称物理吸收结果错误。

## zero-contrast 的作用

zero-contrast case 保留 rectangular block 几何和 cell tag，但设置：

```text
n_grating = n_air = 1 + 0j
```

这样可以检查几何、tag、mesh 和后处理路径本身是否引入虚假散射。它不是最终物理 benchmark，而是数值路径 sanity check。

## 本轮输出文件

每个 Stage 4 result folder 中正式使用以下五个功率/吸收文件：

```text
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

旧的 `power_metrics_3d.json`、`diffraction_orders_3d.json`、`dtn_port_*` 文件只作为 legacy/debug 信息保留，不作为本轮 outcomes 的正式依据。
