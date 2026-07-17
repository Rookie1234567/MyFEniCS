# Task033 阶段负结果与延期边界

| 项目 | 观测 | 解释 | 处理 |
|---|---|---|---|
| QEP legacy 全阶 aggregate | 未资格化 | p1 解析趋势/分支闭合失败，p2 h5→h3 beta drift `0.26087 > 0.25` | 保留真实低阶负结果；p3/p4 独立资格不受阻塞 |
| patterned p4 h5→h3 单模 | overlap `0.48444 < 0.5` | 四维块 principal cosine `0.999999999999851`，属于近简并块内基旋转 | p4 block tracking pass；不放宽阈值 |
| QEP MPI2/4 timeout negatives | 1 秒 clean timeout | 有意的合同负向测试 | 已由 p3/p4 h3 四个正向 MPI2/4 pass 补足身份 |
| p1/h5 Hybrid funnel | M160 仅有每方向 120 个有限有效模态 | singular-K2 数值无穷根导致 modal capacity 不足 | 作为已测负结果保留，不继续完整 p/h 矩阵 |
| p3/p4 matched trace | Phase B 五条最小 shard 已通过 | 只验证 matching-interface 迹、投影、积分和 MPI，不是目标求解 | 提交独立复审；不在同一阶段进入 Phase C |
| p3 Hybrid 同阶 reference | 不存在 | Case080 full3D reference 只有 p2 | 禁止把 p2 reference 按相同 h 跨阶绑定 |
| p4 Hybrid | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |
| adaptive/graded/buffer/1 TiB | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |

## 不能升级的结论

- Case090 p3/p4 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- p3/p4 QEP component 通过，不等于 p1–p4 legacy 全阶 aggregate 通过；
- p3/p4 matched-trace Phase B 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- Task032 p2 同网格一致性，不等于连续解已网格收敛；
- 当前阶段没有 0.7 nm PDE、材料转移验证或 1 TiB 可行性证明；
- 已终止的完整 campaign 没有生成 final outcome、21-role manifest 或 publication descriptor。

这些限制是当前证据的组成部分，不是待隐藏的问题。

Phase B 修改了 `modal_trace_projection.py`。旧 Case090 的 Phase A descendant-reuse
结论不延伸到当前 SHA；本轮 Phase B 使用新 clean source 独立实测，也没有提出新的
Case090 结论。未来 Phase C 必须重新生成目标 full3D/Hybrid 记录。
