# Task37c R0：1° 掠射与 S 偏振合同

本文件只固定 Task37c 任务书要求的角度、方向、S 偏振和 Floquet phase 解析值。数值由
只读 inline calculation 产生；没有新增脚本或 solver 逻辑。角度的正式配置是
`incident_grazing_deg=1.0`、`incident_theta_deg=89.0`、`incident_phi_deg=-5.0/0.0/+5.0`。

## 1. 解析定义

项目约定的 theta 是相对向下 `-z` 法向的角度，传播来自上方并指向 `-z`。令
`gamma=1 deg`、`theta=90 deg-gamma=89 deg`，方位角为 `phi`：

```math
\widehat{\boldsymbol k}(\theta,\phi)
=
\left(\sin\theta\cos\phi,\;\sin\theta\sin\phi,\;-\cos\theta\right).
```

S 偏振取当前入射平面的单位法向：

```math
\widehat{\boldsymbol e}_s(\phi)
=
\left(-\sin\phi,\;\cos\phi,\;0\right).
```

当前项目的 Bloch phasor 是 `exp(i k dot r)`，因此 `k0=2*pi/13.5 nm`，
`k_parallel=(kx,ky)`，周期相位按正周期平移计算：

```math
\phi_x=\exp(i k_x L_x),
\qquad
\phi_y=\exp(i k_y L_y),
\qquad
\phi_{corner}=\phi_x\phi_y.
```

这里采用 Task37c 几何的 `Lx=50 nm`、`Ly=25 nm`；`kx`、`ky` 的单位是 `rad/nm`。
这与现有 Floquet 约束中 `phase_x=exp(i*kx*length_x)`、`phase_y=exp(i*ky*length_y)`
的实现一致。`phi` 是方位角，不应与 Floquet 相位字段混名。

## 2. 解析数值表

数值保留足够位数用于 `1e-13` 审计。`khat` 与 `s_hat` 是无量纲；`kx/ky` 是
波数分量；phase 是复数。

| phi (deg) | khat | s_hat | kx | ky | phase_x | phase_y |
|---:|---|---|---:|---:|---|---|
| -5 | `(0.99604297281404885, -0.087142468505889387, -0.017452406437283598)` | `(0.087155742747658166, 0.99619469809174555, 0)` | `0.46357944978553395` | `-0.040557946499819558` | `-0.37367920127169069 - 0.92755800602277771i` | `0.52851273055539882 - 0.84892537577862304i` |
| 0 | `(0.99984769515639127, 0, -0.017452406437283598)` | `(0, 1, 0)` | `0.46535024797214902` | `0` | `-0.29019682129303004 - 0.95696698214275977i` | `1 + 0i` |
| +5 | `(0.99604297281404885, 0.087142468505889387, -0.017452406437283598)` | `(-0.087155742747658166, 0.99619469809174555, 0)` | `0.46357944978553395` | `0.040557946499819558` | `-0.37367920127169069 - 0.92755800602277771i` | `0.52851273055539882 + 0.84892537577862304i` |

由同一计算得到 `phase_corner` 分别为：

| phi (deg) | phase_corner |
|---:|---|
| -5 | `-0.98492174383521858 - 0.17300045815139359i` |
| 0 | `-0.29019682129303004 - 0.95696698214275977i` |
| +5 | `0.58993331380349512 - 0.80745197087184506i` |

每一行的 `khat dot s_hat` 为 `0`（打印精度下），`norm(khat)=1`，`norm(s_hat)=1`；
项目代码的 signed z 分量均为负。R0 的解析审计容差为 `1e-13`，不把这些解析值冒充 PDE
结果或 Floquet numerical qualification。

## 3. 三路路径的参数传递边界

Task37c 的后续 Full3D direct、Hybrid direct 和 Hybrid iterative 必须把同一组
`theta/phi/khat/s_hat/phase_x/phase_y` 传入各自配置和 authority record：

| 路径 | 必须保持一致的量 | R0 状态 |
|---|---|---|
| Full3D direct | `incident_theta_deg`、`incident_phi_deg`、S basis、period phases | 仅审计，R2 才运行 |
| Hybrid direct | 同一 physical config 与 external mode keys | 仅审计，R3 才运行 |
| Hybrid iterative | 同一 config、Floquet phases、mode identity 与 S basis | 当前 Task37b runner 仍冻结 10°/40 modes，R1 才接入 1°动态参数 |

R0 不修改现有 `ordinary` direct 入口，不把全局 y 向量误用作所有 `phi` 的 S 偏振，也不
运行 `P` 偏振、额外角度、M200 或 MPI1/8 PDE。后续正式记录必须同时保存角度、方向、S
向量和 phase，而不能只写一个 `1°` 标签。
