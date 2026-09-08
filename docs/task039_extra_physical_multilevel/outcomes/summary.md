# Task39extra：Review v1 / R6 收口

| 项目 | 当前结果 |
|---|---|
| 模型 | 原始13.5 nm、掠入射1°、Full3D p6/h10、MPI1、80 modes；零初值完整R3 |
| R0 / R1 | 原PC同机非warm中位22.021386729524238 s；等价实现74.87089344408014 s，3.3999172878472805倍，未满足≤0.75倍；等价误差通过，速度失败 |
| R3 LIGHT | H6–p4–H6，582完整PC中位10.293892393587157 s；7200.255611149943 s求解后 `PERFORMANCE_CONTROLLED_STOP` |
| 完整wall / RSS峰值 | 7966.278611822054 s / 3352014848 B（同期parent+后代RSS采样）；swap=0，cap=8588566528 B，系统余量≥4294967296 B，30230样本无违规 |
| 最后安全结果 | 第576步原A6真残差0.0791360407785889 >1e-6；第582步reported=0.07877047901292458，不是终止瞬间真残差 |
| p4参考逆 | 583次原A4残差最大7.058163970105702e-11≤1e-10；仍未带来合格p6场 |
| 退出缺口 | parent记录预算停止并清场；worker terminal summary、final arrays与normal checker未生成；第583个PC的post未证明完成 |
| official物理输出 | R/T/A、A_volume、R00_s/R00_p/R00_total、衍射级、复E/H和近场均not_run |
| 条件未触发 | R2因速度Gate失败跳过；R4非可分、R5参考/direct与h5 heavy未运行；无第三PC、5nm或0.7nm资格 |
| 事后修复 | `597546311feea60d61acb2a9999b706dd895dcf0`只修未来LIGHT安全停止路由；没有R3重跑，不提升正式负结果 |

轻量组合用p6上的局部平滑H6代替S6内的p3/p1多层步骤，减少每次辅助修正的工作，但方向对原方程误差的削弱仍不足。准确的p4直接逆是诊断依赖，不能替代外层真残差和物理输出Gate。两条路线按本轮合同结束，不能说两种算法已彻底研究完：完整S6配合后续contiguous packing的重新资格化为not_run。

在共同32步观测下，接近0.1826残差的累计周期时间由旧A2R的3528.55 s降至R3的2861.69 s，约19%；这不等于相同残差的精确穿越时间，也不是趋近1e-6的外推。方法、计时嵌套范围、贡献统计、完整曲线、source及hash见 [成本与贡献](cost_and_contribution_v1.md)、[紧凑JSON](records/cost_and_contribution_v1.json)、[response_v2](../response_v2.md)。p/h、Full3D/Hybrid、M和MPI扫描无新增对照，0.7nm物理收敛和global p4 factor扩展能力未资格化。当前进入集中审阅，不继续formal。

## 历史 A5 证据（原结论保留，当前阶段以上表为准）

| 项目 | 结论 |
|---|---|
| 研究对象 | 13.5 nm、掠入射 1°、Full3D p6/h10、MPI1、80 DtN 模式；不是 0.7 nm 已通过模型 |
| 最终状态 | A2R 在原 3600 s solve Gate 触发 `PERFORMANCE_CONTROLLED_STOP`；外层未达到 1e-6 |
| 已证明的边界 | p4 参考矩阵容量可容纳；163 次中间逆均通过原 A4 真残差 1e-10 Gate；最后有效第 160 步外层残差为 0.18250767622880507 |
| 移交资格 | 可移交机制与负结果证据，未满足 `LOCAL_13P5NM_3D_READY_FOR_WORKSTATION` 或 `REFERENCE_ONLY_HANDOFF` |
| 未运行 | A3 非可分、A4 h5/独立 direct、official recovery/输出、5 nm、0.7 nm；不补跑 |

主候选用较低阶 p4 的迭代解辅助 p6 外层修正。A2R 把中间迭代逆换成原 p4 物理矩阵的一次直接分解，取得准确且可复用的中间修正，代价是装配时间和分解内存。A6、传递、80 modes、S6 pre/post、MR、FGMRES32/max512 和零初值不变，生产默认不变；中间逆通过不能替代外层通过。

时间为 s，内存为 B；RSS 为 watchdog 同期进程树采样峰值，含 parent、MPI worker、编译后代。

| 运行 / source SHA | 分类与阶段 | workflow / RSS peak / swap | 数值边界 |
|---|---|---|---|
| A2 旧 setup；`39448e6a0e5705ad2c40b4bf7733ce2249e35a84` | 用户 setup 受控停止 | 5946.465141321009 / 1582481408 / 0 | outer 未开始 |
| A2 优化后；`2bed3d4248a465a9cf2224c575fc8b64357fd020` | `USER_AUTHORIZED_COST_CONTROLLED_STOP` | 3015.3758775380556 / 1849683968 / 0 | 7 完整 PC，第 8 partial；outer final 不可用 |
| A2R 入口；`f93edc8ae9e90c4ed07e375d964312eb68999ee9` | `adapter_unavailable`，测量前登记遗漏 | 0.014696567959617823 / 未采样 / 未采样 | watchdog/MPI/symbolic/PDE 均未开始，不计 reference 正式次数 |
| A2R 唯一正式；`54ab46cf4c8378a9b27650ca6963cadb34013a2f` | `PERFORMANCE_CONTROLLED_STOP`，solve 3600 s Gate | 4451.728501909005 / 3588677632 / 0 | 163 完整 PC，第 164 仅 pre 开始；最后 checkpoint=160 |

PC 是一次辅助修正。优化后 A2 的 7 个 PC 各运行 36 个中间步，A4 残差依次为 0.846787、0.815692、0.720637、0.794347、0.817342、0.635752、0.803464，均未达到中间目标 1e-2。这些 RHS 不同，不能串成收敛曲线；其 checkpoint 0=1 只代表初始零解。

| A2R 周期末迭代 | 原 A6 显式相对真残差 | 成功门槛 |
|---:|---:|---|
| 32 | 0.46338436888430473 | 1e-6，未通过 |
| 64 | 0.41005441732961595 | 1e-6，未通过 |
| 96 | 0.3139861672303239 | 1e-6，未通过 |
| 128 | 0.2753887167051727 | 1e-6，未通过 |
| 160 | 0.18250767622880507 | 1e-6，未通过；最后有效 checkpoint |

每周期 reported 与显式残差差值通过既定核验，精确对照见索引。163/164 步最终残差不可用，不把第 160 步结果当作停止瞬间最终场。残差降低但预算内未达标，不证明整个 p4 空间或 Full3D 迭代数学不可能。

| 对象 / 阶段 | 实际或推导值 | 口径 |
|---|---:|---|
| p6 / p4 rows（独立 rows） | 173802（164592）/ 53084（48960） | 原模型 |
| p4 slaves / modes | 4124 / 80 | actual MPC/carrier |
| volume / augmented NNZ | 24666128 / 24730144 | 实际；augmented rows=53164 |
| S6 / 至 solve 开始 | 117.70526724500814 / 847.9243652080186 | 本次 marker 跨度；后者包含全部 worker setup |
| reference volume compile / values | 13.712174824962858 / 588.368423515989 | marker 跨度 |
| augmentation / symbolic / numeric | 0.5967822759994306 / 0.3211546370293945 / 18.394115508999676 | 各一次；numeric 含 preflight 设置 |
| post-symbolic RSS / 预测峰值 / cap | 2292035584 / 6988289408 / 8736759808 | 预测为 2×带 padding 的 MUMPS 估计加 workspace 和 1 GiB，非严格上界 |
| reference solve / 原 A4 action | 163 / 163 | 最大相对残差 5.7889315844880267e-11 |
| 完整 PC 最小 / 中位 / 最大耗时 | 20.112385745043866 / 20.611484433989972 / 21.111527371045668 | 原 A2 约 290–446 s；成本下降不等于 outer PASS |
| RSS / 可读 PSS 采样峰值 | 3588677632 / 3554077696 | RSS 的 16993 样本均可读；1 个 PSS 不可读样本，PSS 非完整 Gate 权威 |

S6 精确对角优化省掉取得对角项时不需要的单元耦合，保持原积分和约束；旧 S6 5916.818793114 s（约 98.6 min）降至优化后 A2 的 143.69 s。本次 S6 为 117.71 s。S6 单段不等于完整 setup 或 workflow。

| 计数 / 尾段证据 | 审计结果 |
|---|---|
| S6/S3 次数更正 | 原 cycles 将生命周期序号相加，五周期误报 2080/6176/10272/14368/18464；逐次重算每周期均为 64。163 完整 PC 合计 S6 326 次、S3 326 次；最后完整周期后的 3 个完整 PC 合计增加 S6 6 次、S3 6 次；partial 第 164 不推算 |
| 修复边界 | cycles 原文不改；checker 只读重算；未来 ledger 只修序号误加，不改数值路径 |
| 终止时间 | solve Gate 的 monotonic 阈值为 503631.500417347；最后 marker 为 solve 3596.8651744240196 s；单独发信号时间戳未记录，不伪造精确触发时刻 |
| 清场 | parent 及 61 后代共 62 PID 均消失；cache metadata 稳定；swap 与全局换页增量均 0 |
| worker 尾段缺口 | physical_intermediate_summary.json 未生成；正常 release/recovery/checker completion 未完成，不补造原 worker 终态 |

official R/T/A、A_volume、R00_s/R00_p/R00_total、重要衍射级、E/H 与参考平面均 `not_run`。p/h、Hybrid、M、MPI 扫描没有新增正式对照，不宣称连续极限收敛。

证据：[运行索引](records/run_index.json)、[测试摘要](test_summary.md)、[移交包](workstation_handoff.md)、[response_v1](../response_v1.md)。索引绑定本次 28 份 raw（含每周期 manifest/solution）及早先停止、入口失败、实现/修复记录；大型 raw/cache 保持 ignored。

下一步只提交集中审阅，决定如何解释中间逆已准确但外层仍昂贵的机制，以及是否开展新的算法比较。不自行延长预算、重跑 A2R、换 PC 或进入 A3/A4；当前未获最终 merge approval。
