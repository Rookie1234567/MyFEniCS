# Task001 保真度资格化

## 选择

```text
selected_high_fidelity = HF10 global p6/h10/M120 MPI2
selected_low_fidelity  = LF4 global p4/h10/M120 MPI2
HF7P5                  = controlled_stop_resource_projection; PDE launched=false
M160                   = not_run
```

这里的 global p6 指整个正式有限元域统一使用任务书定义的 p5 trace / p6 interior
exact-sequence contract，不启用自适应 p 或局部加密功能。

## HF10 nominal

| 字段 | 实测 |
|---|---:|
| source SHA | `68f4f9bc92de6cd7ec2896755ef210fb182280a1` |
| geometry/configuration | 120 nm / 17 nm；10° grazing / 0° azimuth / S |
| axis cells | `(6,3,14)` |
| local algebra rows / side | 8,464 |
| local matrix NNZ / side | 6,156,616 |
| factor NNZ bottom / top | 23,023,456 / 23,139,232 |
| modal Schur | 240 x 240 |
| full true residual | `2.4838e-12` |
| max interface E/H relative L2 | `1.6395e-7 / 3.8958e-5` |
| energy closure | `1.5568e-10` |
| R / T / A / Avolume | 0.0007628815 / 0.6027016340 / 0.3965354845 / 0.3965354847 |
| watchdog wall | 253.971 s |
| process-tree peak RSS / swap | 3,287,891,968 B / 0 B |

Case095/096 的 12 个冻结显著通道全部存在。相对 p6/h10 reference 的最大功率和边界复振幅
绝对差为 `2.052e-12 / 2.183e-12`。reference 只代表同代码 best-available 离散 band。

## HF7P5 启动 Gate

HF10 measured peak 为 3,287,891,968 B，固定 cell plan 从 `(6,3,14)` 增至
`(9,4,20)`，cell ratio 为 2.85714。三档预测：

| 预测 | bytes | GiB | Gate |
|---|---:|---:|---|
| optimistic linear payload | 9,393,977,051 | 8.748 | 仅参考 |
| central sparse-fill | 11,588,731,106 | 10.793 | 超过 9.45 GiB launch ceiling |
| conservative factor-fill | 15,878,719,347 | 14.788 | 超过 10.5 GiB hard ceiling |

因此按任务书在启动前受控停止；没有创建 HF7P5 PDE 进程，也没有用 swap 或 OOM
冒险获取结果。该结论只适用于当前 16 GB laptop 与当前 direct 生命周期，不代表其他机器
无法计算。

## LF4 五点资格化

在 10°/0°/S 的 G00/Gh-/Gh+/Gw-/Gw+ 上，HF 与 LF 使用相同 source、M120、MPI2、
order identity 和参考面：

| 指标 | 结果 | Gate |
|---|---:|---|
| active HF channels | 14 | floor `1e-8` |
| cosine(dy/dh) | 0.999689 | >=0.85，期望 >=0.90 |
| cosine(dy/dw) | 0.999998 | >=0.85，期望 >=0.90 |
| top-80% Fisher sign | h/w 均一致 | 必须无反转 |
| mean wall LF/HF | 0.19155 | <=0.5 |
| mean RSS LF/HF | 0.31765 | <=0.5 |

LF4 因此通过。LF5 不运行。LF-HF 的平滑 R/T/A bias 留给 Task002 的
`y_H = rho*y_L + delta(h,w)` correction 学习，不把 LF 冒充 HF。

## 正式 M6 HF 五点

新增的 10°/90°/S 五点 wall 为 228.60--272.01 s，peak RSS 为
3,310,305,280--4,181,561,344 B，全部零 swap、全部 residual/interface/energy/order Gate
通过。10°/0°/S 的五点复用 M3/M4；没有重复计算。

M120 是 Task001 固定 modal identity。M160 属可选诊断，未运行不能写成通过。
