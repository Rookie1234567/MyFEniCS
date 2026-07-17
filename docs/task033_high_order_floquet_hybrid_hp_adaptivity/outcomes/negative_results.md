# Task033 阶段负结果与延期边界

| 项目 | 观测 | 解释 | 处理 |
|---|---|---|---|
| QEP 全局 aggregate | 未资格化 | p1 解析趋势、p1/p2 patterned tracking 及 p4 一段 overlap Gate 未过 | 保留真实负结果；不影响 Case090 直接 3D p3/p4 资格 |
| patterned p4 h5→h3 | overlap `0.48444 < 0.5` | 两个近简并模态的公共 Fourier overlap 略低于冻结阈值 | 不放宽阈值，不宣称 p4 QEP aggregate pass |
| QEP MPI2/4 | 1 秒 clean timeout | 这是有意的合同负向测试 | 不写成 MPI2/4 正向资格 |
| p1/h5 Hybrid funnel | M160 仅有每方向 120 个有限有效模态 | singular-K2 数值无穷根导致 modal capacity 不足 | 作为已测负结果保留，不继续完整 p/h 矩阵 |
| p3 Hybrid 同阶 reference | 不存在 | Case080 full3D reference 只有 p2 | 禁止把 p2 reference 按相同 h 跨阶绑定 |
| p4 Hybrid | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |
| adaptive/graded/buffer/1 TiB | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |

## 不能升级的结论

- Case090 p3/p4 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- 36 个 QEP shard 通过，不等于全局 QEP aggregate 通过；
- Task032 p2 同网格一致性，不等于连续解已网格收敛；
- 当前阶段没有 0.7 nm PDE、材料转移验证或 1 TiB 可行性证明；
- 已终止的完整 campaign 没有生成 final outcome、21-role manifest 或 publication descriptor。

这些限制是当前证据的组成部分，不是待隐藏的问题。
