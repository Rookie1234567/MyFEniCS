# Task033 高阶 3D Floquet 结果

## 1. 正式矩阵

Case090 在源码 `6613f94b91ebc77eb50e74086475c67df46236f6` 上完成：

| 夹具 | 每个 MPI 的组成 | MPI | 合计 |
|---|---:|---|---:|
| A：10 nm air box | `4 degree × 2 mesh × 2 polarization = 16` | 1, 2, 4 | 48 |
| B：10° air–Si 主矩阵 | `4 × 2 × 2 = 16` | 1, 2, 4 | 48 |
| B：1°/5° smoke，仅 h5 | `2 angle × 4 degree × 2 polarization = 16` | 1, 2, 4 | 48 |
| 总计 | 每个 MPI 48 | 1, 2, 4 | **144 PDE** |

p3 与 p4 各占 36 项。`p3/p4 × MPI1/2/4` 六个 coverage 组合全部
`core_algebra_gates_passed=true`。

## 2. 核心 Gate

| Metric | 最大观测值 | Gate | 结果 |
|---|---:|---:|---|
| constraint round-trip relative error | `2.9461100e-14` | `<=1e-12` | pass |
| Bloch trace mismatch | `3.1890378e-15` | `<=1e-11` | pass |
| reduced/full action relative error | `3.1269071e-16` | `<=1e-11` | pass |
| full true residual | `6.5984836e-12` | `<=1e-10` | pass |
| MPI result difference | `1.0668903e-11` | `<=1e-10` | pass |
| global boundary allgather | false | false | pass |
| dense boundary square | false | false | pass |

外部 watchdog 的整批同时内存峰值为 MPI1 `0.930 GiB`、MPI2 `4.412 GiB`、
MPI4 `5.420 GiB`，三组均零 swap 并通过资源 Gate。

## 3. p3/p4 精度与代价

Case090 的 36 个可比 p-refinement 条目中：

- p3 相对 p2 的误差改善为 76.42%–90.88%；
- p4 相对 p3 的误差改善为 83.33%–91.97%；
- 36/36 均归类为 `positive_p4_benefit`。

代表性算例为 air box、10°、S、h=2.5 nm：

| degree | DoF | NNZ | MPI1 time/s | MPI4 time/s | 物理误差 |
|---:|---:|---:|---:|---:|---:|
| p3 | 6,084 | 1,459,422 | 14.2548 | 5.1567 | `1.20864e-2` |
| p4 | 13,872 | 6,284,640 | 114.1689 | 34.7252 | `9.93658e-4` |

p4 在该点把误差降低约 91.8%，同时 DoF 增至 2.28 倍、NNZ 增至 4.31 倍，
墙钟时间也显著上升。因此结论是“高阶能力与精度收益成立”，不是“p4 总是更划算”。

## 4. 适用边界

Case090 是小型解析 3D fixture 的直接 FEM 资格化。它证明高阶双 Floquet、orientation、
稀疏约束与 MPI 路径正确，但不能替代目标光栅上的 p3/p4 Hybrid/full3D 同阶对照。
