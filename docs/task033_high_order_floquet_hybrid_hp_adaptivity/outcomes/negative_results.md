# Task033 阶段负结果与延期边界

| 项目 | 观测 | 解释 | 处理 |
|---|---|---|---|
| QEP legacy 全阶 aggregate | 未资格化 | p1 解析趋势/分支闭合失败，p2 h5→h3 beta drift `0.26087 > 0.25` | 保留真实低阶负结果；p3/p4 独立资格不受阻塞 |
| patterned p4 h5→h3 单模 | overlap `0.48444 < 0.5` | 四维块 principal cosine `0.999999999999851`，属于近简并块内基旋转 | p4 block tracking pass；不放宽阈值 |
| QEP MPI2/4 timeout negatives | 1 秒 clean timeout | 有意的合同负向测试 | 已由 p3/p4 h3 四个正向 MPI2/4 pass 补足身份 |
| p1/h5 Hybrid funnel | M160 仅有每方向 120 个有限有效模态 | singular-K2 数值无穷根导致 modal capacity 不足 | 作为已测负结果保留，不继续完整 p/h 矩阵 |
| p3/p4 matched trace | Phase B 五条最小 shard 已通过并获 review v3 接受 | 只验证 matching-interface 迹、投影、积分和 MPI，不是目标求解 | Phase C Hybrid 在新 clean SHA 独立实测 |
| p3/h5 full3D direct | centers `6.445 / 15.031 GiB`，upper `18.038 GiB` | 第二中心与上界超过现场缩放 Gate | `not_run_by_memory_gate`；未强跑 |
| p3/h5 Hybrid same-degree reference | 不存在 | Case080 full3D 只有 p2；本轮 p3 full3D 被 C0 阻止 | Hybrid component 可通过，但 whole Phase C 不通过 |
| p4 Hybrid | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |
| adaptive/graded/buffer/1 TiB | 未运行 | 用户缩小范围 | `deferred_by_user_scope` |

## 不能升级的结论

- Case090 p3/p4 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- p3/p4 QEP component 通过，不等于 p1–p4 legacy 全阶 aggregate 通过；
- p3/p4 matched-trace Phase B 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- p3/h5 Hybrid M 漏斗和 augmented/minimal 等价通过，不等于 Hybrid/full3D 等价；
- Task032 p2 同网格一致性，不等于连续解已网格收敛；
- 当前阶段没有 0.7 nm PDE、材料转移验证或 1 TiB 可行性证明；
- 已终止的完整 campaign 没有生成 final outcome、21-role manifest 或 publication descriptor。

这些限制是当前证据的组成部分，不是待隐藏的问题。

Phase B 修改了 `modal_trace_projection.py`。Phase C 将 Case090 复用范围严格收窄为
`case090_pure3d_floquet_core`，并把该文件明确记为 component-disjoint numerical
change；目标 Hybrid 在新 clean SHA 独立实测。旧 Case090 仍不是当前 p3/h5 full3D
reference，full3D 缺口只能由未来通过新 C0 的真实同阶运行补齐。
