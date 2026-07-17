# Task033 阶段负结果与延期边界

## 2026-07-17 更新

- 旧的“p3/h5 full3D 未运行”已经被新实测取代，不再是当前负结果。p3 direct
  以 7.781 GiB、零 cgroup swap 完成，并与 Hybrid 同阶闭合。
- p4 四模态 matched-trace 不是负结果；MPI1/MPI4 正式通过。
- 当前新的可复现负结果是 p4/h5 target 资源门禁：assembly-only 在 base
  155,205,040 NNZ、DtN 插入后达到 12.616 GiB 并受控终止，未进入 factor/solve。
- p4 Hybrid M160 仍被其独立 37.038/42.594 GiB 中心/上界拒绝。没有用 p3 的低峰值
  反向覆盖 p4 自己的候选 Gate。
- Review V5 的 `p3/h10` 是新的 accuracy negative：direct solve 安全完成，但相对
  provisional p3/h5 reference 的全部规定物理误差都劣于 p2/h3。低资源不能替代精度。
- `p3/h7.5` 不是负结果；它在同一口径下通过，并降低六项报告资源。
- variable-p capability audit 为 fail-closed negative：当前运行时观察到 mixed/submesh
  API，但没有 native cellwise variable-p H(curl) 的共形、周期和 MPI 证据。

| 项目 | 观测 | 解释 | 处理 |
|---|---|---|---|
| QEP legacy 全阶 aggregate | 未资格化 | p1 解析趋势/分支闭合失败，p2 h5→h3 beta drift `0.26087 > 0.25` | 保留真实低阶负结果；p3/p4 独立资格不受阻塞 |
| patterned p4 h5→h3 单模 | overlap `0.48444 < 0.5` | 四维块 principal cosine `0.999999999999851`，属于近简并块内基旋转 | p4 block tracking pass；不放宽阈值 |
| QEP MPI2/4 timeout negatives | 1 秒 clean timeout | 有意的合同负向测试 | 已由 p3/p4 h3 四个正向 MPI2/4 pass 补足身份 |
| p1/h5 Hybrid funnel | M160 仅有每方向 120 个有限有效模态 | singular-K2 数值无穷根导致 modal capacity 不足 | 作为已测负结果保留，不继续完整 p/h 矩阵 |
| p3/p4 matched trace | Phase B 五条最小 shard 已通过并获 review v3 接受 | 只验证 matching-interface 迹、投影、积分和 MPI，不是目标求解 | Phase C Hybrid 在新 clean SHA 独立实测 |
| p3/h5 full3D 旧 C0 | centers `6.445 / 15.031 GiB`，upper `18.038 GiB` | 历史预测曾超过现场缩放 Gate | 已由用户授权实测取代；不得继续写成当前 `not_run` |
| p3/h5 Hybrid same-degree reference | direct 7.781 GiB；16 项闭合 Gate 全过 | 真实同阶 reference 已建立 | whole Phase C 数值闭合通过；Review V6 已接受 |
| p4 四模态 matched trace | MPI1/MPI4、4×4 Gram 与块不变量全过 | 近简并子空间需块跟踪而非逐向量比较 | 正结果；不再阻塞 p4 候选校准 |
| p4/h5 full3D target | 12.616 GiB 受控终止；`pswpout` +4 pages | 自身 assembly-only 资源 Gate 失败 | 未进入 factorization/solve；不重复装配 |
| p4/h5 Hybrid M160 | center/upper `37.038 / 42.594 GiB` | 自身预测远超当前主机预算 | `not_run_by_memory_gate` |
| p3/h10 fixed-p equal accuracy | scalar/field/interface/order 12 类比较均劣于 p2/h3 | coarse h=10 物理离散不足；不是残差或内存问题 | `negative_not_equal_accuracy`；合法触发 h7.5 |
| p3/h10 Hybrid H-interface | M120/M160 同一 sampled H Gate 未过，增加 M 不改善 | 不是 modal truncation 收敛问题 | 不跑 M240；direct 等精度已失败 |
| variable-p H(curl) | 无 native operational/conformity/periodic/MPI evidence | API 存在不等于 unequal-p 语义资格 | `not_qualified_fail_closed`；不做 bespoke prototype |
| adaptive/graded | 未运行 | 用户与 Review V6 已移交下一独立任务 | `transferred_to_next_task` |
| buffer | 未运行 | 等待 defect/nonuniform-end geometry | 保留 10/110 nm，不选伪最优 |
| 1 TiB | 未更新 | 缺 measured adaptive compression，且旧高阶模型低估 p3/h7.5 full-solve memory | 移交 adaptive/scalability task；不宣称 0.7 nm 可行 |

## 不能升级的结论

- Case090 p3/p4 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- p3/p4 QEP component 通过，不等于 p1–p4 legacy 全阶 aggregate 通过；
- p3/p4 matched-trace Phase B 通过，不等于目标光栅 p3/p4 Hybrid/full3D 等价；
- p3/h5 的旧 M 漏斗和 augmented/minimal 记录单独看不等于 Hybrid/full3D
  等价；本轮新增的同阶 direct/Hybrid、R/T/A 与五平面对照已另行完成数值闭合，
  但仍不等于 h 收敛或连续解误差证明；
- Task032 p2 同网格一致性，不等于连续解已网格收敛；
- 当前阶段没有 0.7 nm PDE、材料转移验证或 1 TiB 可行性证明；
- 已终止的完整 campaign 没有生成 final outcome、21-role manifest 或 publication descriptor。
- p3/h7.5 的等精度正结果使用 provisional p3/h5 离散参考；不能改写成连续解误差、
  网格收敛或“任意问题 p3 都优于 p2”。

这些限制是当前证据的组成部分，不是待隐藏的问题。

Phase B 修改了 `modal_trace_projection.py`。Phase C 将 Case090 复用范围严格收窄为
`case090_pure3d_floquet_core`，并把该文件明确记为 component-disjoint numerical
change；目标 Hybrid 在新 clean SHA 独立实测。旧 Case090 本身仍不是 p3/h5
full3D reference，但该缺口已经由本轮真实同阶 direct 运行补齐。
