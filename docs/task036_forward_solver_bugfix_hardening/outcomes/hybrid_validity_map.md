# Task036 V2 Hybrid validity map

## 1. 当前结论

本轮在源码 `6d5e9781bcb1458ecac7a77af22fa2d420f0cd55` 上完成五个 same-input
Full3D/Hybrid M120 配置对。五个 Full3D 全部通过；五个 Hybrid 均完整结束、zero swap，
但固定衍射通道全部未闭合，因此当前生产有效域为空：

```text
production-qualified S region = none established
production-qualified P region = none established
minimum passing M = none
formal M cap for next architecture = 120
Full3D fallback counted as Hybrid success = false
```

这里只能报告已运行的五个配置，不能把它们外推成 226 点全域通过率。
更新后的离线 analyzer 把 sampled recovered-field 值明确标为 diagnostic-only，不用
任意 `5e-3` 筛选值替代 Review V2 的正式 algebraic `1e-8` Gate；但 diagnostic 超限会
设置 production hold，防止投影残差掩盖真实 trace 补空间。五点分类计数为：

```text
trace_complement_diagnostic_hold = 4
basis_or_physical_gate_failed = 1
```

## 2. 同源有效性表

| point | polarization | p | Hybrid M | residual / algebraic E / traction / biorth row | recovered physical E jump | energy | totals | fixed-channel pass | classification |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| A001-P | P | 5 | 120 | pass / pass / pass / pass | `1.709e-1` | fail | fail | 66/80 | trace-complement / channel failure |
| A004-P | P | 5 | 120 | pass / pass / pass / pass | `4.375e-2` | fail | pass | 48/96 | trace-complement / channel failure |
| A004-S | S | 5 | 120 | pass / pass / pass / pass | `9.272e-5` | fail | pass | 77/96 | channel/energy failure |
| A049-P | P | 5 | 120 | pass / pass / pass / pass | `8.284e-3` | pass | pass | 32/80 | trace-complement / weak-channel failure |
| D001-P | P | 6 | 120 | pass / pass / pass / pass | `1.822e-1` | fail | pass | 66/80 | trace-complement / channel failure |

“algebraic E pass”只说明 M 个投影坐标满足耦合方程；“recovered physical E jump”是把
Hybrid 解恢复到实际有限元界面后观察到的切向场差。二者相差多个数量级，正是当前
M120 不能 production qualification 的核心证据。

## 3. 资源图

| point | Full3D peak GiB | Hybrid M120 peak GiB | reduction | 资源判定 |
|---|---:|---:|---:|---|
| A001-P | 10.092 | 7.212 | 28.5% | 有内存优势，但数值不合格 |
| A004-P | 10.516 | 7.450 | 29.2% | 有内存优势，但数值不合格 |
| A004-S | 10.549 | 7.464 | 29.2% | 有内存优势，但数值不合格 |
| A049-P | 10.228 | 7.131 | 30.3% | 有内存优势，但数值不合格 |
| D001-P | 18.572 | 11.222 | 39.6% | 有内存优势，但数值不合格 |

这些是 simultaneous process-tree peak；inventory sum 没有冒充峰值。首批并行调度发现
OpenMPI rank binding 重叠，因此捕获的 wall time 不作为正式速度优势。该调度 bug 已
修复，但数值 kernel 未变，所以没有为了更新时间重跑 PDE。

## 4. M 扩张路线关闭

历史 A049-P 同点漏斗的物理界面跳跃在 M120、M240、M480、M492 间形成平台，而内存约为：

| solver | peak GiB | 相对 Full3D |
|---|---:|---|
| Full3D | 10.161 | authority |
| Hybrid M120 | 7.263 | 较低 |
| Hybrid M240 | 9.146 | 接近 |
| Hybrid M480 | 18.829 | 更高 |
| Hybrid M492 | 19.405 | 约 1.91× |

所以 M492 没有工程意义，本区域正式归为
`HYBRID_FUNCTIONAL_NO_REDUCTION_ADVANTAGE`。Task036 不再运行 M240/M480/M492，
也不会用 full-rank 结果替代真正的降维成功。

## 5. 保持 M120 的后续实现

通俗地说，当前实现只检查界面场在 120 个“测量方向”上的系数相等，却允许它在其余
有限元方向上残留不连续分量。下一步应把界面场本身直接限制为这 120 个物理模式的线性
组合，而不是增加模式数。

令 `g_s` 为某一侧的界面 trace，`D_s` 为左投影，`R_s` 为右侧物理模式 prolongation，
`L_s a` 为传播到该面的 M120 系数。新的强约束应是：

```text
g_s = R_s L_s a
```

而不只是：

```text
D_s g_s = L_s a
```

实现时直接从局部系统消去界面 trace，并保留内部有限元行与 M 个 Petrov flux 行；不形成
稠密 `R_s D_s`。理想行数为：

```text
N_new = (n_bottom - g_bottom)
      + (n_top    - g_top)
      + 2 M
```

因此 M 固定为 120 时，新系统行数不会高于当前增广系统，通常还会下降。它能从结构上
保持降维和内存目标，但实际 residual、59/通道、energy、wall 和 peak 是否通过仍必须由
新 PDE 验证，不能提前保证。

这项改动会改变 Hybrid 的试探/检验空间、Floquet/orientation closure、field recovery
以及 true-residual 语义，超出 Task036 的最小 bug port 范围，正式状态为：

```text
DEFERRED_ARCHITECTURE_REQUIRED
ordinary default = unchanged
Task036 implementation = not_run
production claim = none
```

最小涉及模块预计为：

- `src/coupling/hybrid_internal_modes.py`
- `src/solvers/hybrid_local_dtn.py`
- `src/solvers/hybrid_fem_modal_augmented_direct.py`
- `src/solvers/hybrid_static_field_recovery.py`

验收时必须先用小型 exact-trace fixture 证明消元、Floquet 和 H(curl) orientation 正确，
再只运行 M120 的 S/P anchors；若 M120 不通过，fail closed，不自动扩大 M。
