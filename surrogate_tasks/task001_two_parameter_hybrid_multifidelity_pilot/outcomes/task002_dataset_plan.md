# Task002 多保真数据计划（冻结，未执行）

## 数据接口

```text
configuration:
  wavelength_nm = 13.5
  illumination = {grazing_deg, azimuth_deg, polarization}

geometry:
  height_nm in [115,125]
  width_x_nm in [16,18]
```

Task002 首版 configuration bundle 固定为 Task001 经 HF 确认的：

```text
(10° grazing, 0° azimuth, S)
(10° grazing, 90° azimuth, S)
```

这使数据表明确区分“同一个几何样品在不同实验配置下的响应”，方便未来 DOE 比较哪些角度、
偏振最有利于区分 height/width。当前 P 和近 0.5° 的失败必须先由单独前向资格化任务解决，
不能直接加入训练集。

## 设计与物理 solve 数

| 阶段 | geometry | 每 geometry 配置 | physical solves |
|---|---:|---:|---:|
| LF 7x7 Chebyshev-Lobatto tensor | 49 | 2 | 98 |
| initial HF center + 4 edges + 4 corners | 9 | 2 | 18 |
| adaptive HF | 6--10 | 2 | 12--20 |
| frozen-before-fit validation | 6--8 | 2 | 12--16 |

HF 总预算为 42--54 solves；跨 LF/HF 总预算为 140--152 physical solves。即使未来验证
multi-RHS 共享 factor，也只能另报 factorization count，不能把它写成较少的 physical solve。

## 模型比较

至少比较：

1. low-order Chebyshev/PCE baseline；
2. Gaussian Process baseline；
3. `y_H = rho*y_L + delta(h,w)` multi-fidelity correction。

角点非线性最高 0.1617，因此不采用提高全局多项式阶次作为默认补救。adaptive HF 依据
discrepancy uncertainty、PCE/GP disagreement、posterior region、Fisher 信息和 corner evidence。

## 数据身份

- LF=`LF4 global p4/h10/M120`，HF=`HF10 global p6/h10/M120`；
- 每个正式 dataset version 只能绑定一个完整 forward solver SHA 与一个 observable schema；
- Task001 PDE baseline `68f4f9b...` 是 pilot 证据，不自动成为 Task002 dataset source；Task002
  开始时必须在最终实现 HEAD 上重新冻结 clean dataset baseline；
- 固定保存 9 个 n=0 x-orders、S/P 独立功率、R/T/A、数值 Gate、资源和 raw hash；
- 任何 Gate failure 不进入训练集；失败记录另存；
- 材料目前固定。未来增加材料信息必须升级参数/schema 与 dataset version，并重新训练；禁止
  用当前两几何参数模型对未见材料做隐式外推。

## 明确未执行

Task001 没有运行 49 点 LF design、HF anchor budget、surrogate fit、GPU training、Bayesian
inversion 或生产反演。
