# Task001 照明 DOE 与局部可辨识性

## 参数角色

`configuration` 是实验人员可选择的波长/角度/偏振；`geometry` 是反演算法要估计的
height/width。DOE 的作用是从可实现的实验配置中挑选能让“高度变化”和“宽度变化”产生
不同功率响应的组合，而不是把角度也当成未知几何量。

Task001 只在端点代表条件做有限 pilot。当前通过 HF 确认的最小 bundle 是：

```text
C1: grazing 10°, azimuth 0°,  S
C2: grazing 10°, azimuth 90°, S
```

这同时包含 planar 与 conical 条件。P 未通过当前 physical Gate；0.5°/90°/S 虽能求解，
单独使用时 `rho=-0.9839`，几乎沿同一方向混合 height/width，因此不选。

## 功率特征与噪声

候选特征只使用实验可能测得的固定 order S/P 分量功率；不把 S、P 和 S+P 三者同时作为
独立观测。每配置按 Fisher 增益最多选 8 个，active floor `1e-8`。噪声模型为
`sqrt((r*y)^2 + 1e-8^2)`，同时测试 r=0.5%、1%、2%；它只是 DOE 假设。

R+T 的 LF channel bundle 为 planar 8 个 order 分量加 conical top/bottom m0 S；HF 复用
这些由 LF 选出的物理 identity，不在 HF 结果上重新挑通道以获得乐观结论。

## Fisher 结果

| 层级/观测 | rank | singular values | cond | rho | sigma h/w (nm, 1%) |
|---|---:|---|---:|---:|---:|
| LF reflection | 2 | 28.284 / 21.346 | 1.3250 | `-5.79e-5` | 0.03536 / 0.04685 |
| LF R+T | 2 | 63.555 / 34.567 | 1.8386 | -0.26586 | 0.02844 / 0.01660 |
| HF reflection | 2 | 31.741 / 24.016 | 1.3217 | `1.82e-4` | 0.03150 / 0.04164 |
| HF R+T | 2 | 44.832 / 36.723 | 1.2208 | -0.14793 | 0.02648 / 0.02320 |

HF rank=2、`|rho|<0.90`、cond<100。最大单通道同时控制 h/w 信息的份额为 0.0808
（reflection 为 0.0964），没有单通道同时垄断两个参数。

LF bundle 的噪声稳定性：

| relative noise | R+T cond | R+T rho | sigma h/w nm |
|---:|---:|---:|---:|
| 0.5% | 1.6602 | -0.1926 | 0.01541 / 0.00968 |
| 1% | 1.8386 | -0.2659 | 0.02844 / 0.01660 |
| 2% | 1.9215 | -0.3751 | 0.05166 / 0.03108 |

## Synthetic local recovery

HF 中心点自回代得到 `(0,0)`。两个小扰动在无噪声时逐数值精度恢复；2,000 次固定 seed
的 1% 抽样为：

| true delta h/w nm | mean h/w | bias h/w | std h/w | empirical corr |
|---|---|---|---|---:|
| +0.5 / +0.1 | 0.49927 / 0.10082 | -0.00073 / +0.00082 | 0.02670 / 0.02373 | -0.1635 |
| -0.5 / -0.1 | -0.50062 / -0.10015 | -0.00062 / -0.00015 | 0.02643 / 0.02355 | -0.1342 |

这只说明中心附近的功率梯度包含两维信息；它没有覆盖整个 prior，也不是 surrogate training。

## 非线性与适用边界

角点相对局部线性误差在 selected conical 条件达到 0.1617，说明全域不能只靠中心 Jacobian。
Task002 应保留 9 个初始 HF anchors，再用 GP/multi-fidelity discrepancy uncertainty 自适应增加
HF 点。

接口域与资格化域必须区分：未来 DOE 可以在 `configuration` 的 0.5--10°、0--90°、S/P
中提议新实验，但在用于训练或反演前必须先通过同样的 trace、residual、interface、energy 和
order Gate。当前可以正式进入 Task002 首版的只有上述两个 10°/S 配置。
