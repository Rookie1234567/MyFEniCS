# Task40extra 精度与容量判断

## 数值精度状态

| Gate/指标 | 目标 | G0/G1 实际证据 | 状态 |
|---|---:|---|---|
| G0 p6 原 A6 full explicit true residual | `≤1e-6` | 两次 worker 都在外层 KSP 前失败；残差 `null` | `not_run` |
| G0 official R/T/A、`A_volume`、R00_s/p 与衍射级 | A6 通过后计算 | 无完整 p6 场和 official packet | `not_run` |
| energy closure | `≤1e-5` | G0 未产出正式功率与体吸收 | `not_run` |
| G0–G1 E/H/scaled-curl 变化 | `≤1%` 工程观察目标 | G1 未运行 | `not_run` |
| G0–G1 R/T/A/`A_volume` 变化 | `≤1e-3` 绝对变化目标 | G1 未运行 | `not_run` |
| G0–direct 同离散比较 | 场 `≤1e-4`，R/T/A `≤1e-5` | direct 预检和求解均未运行 | `not_run` |
| 外部通道截断 | 独立 cutoff convergence | 80 模式仅由当前规则枚举，未做收敛研究 | `CHANNEL_TRUNCATION_UNQUALIFIED` |

唯一 measured 数值求解是 60-cell p2 N2 diagnostic：残差 `1.772707454694957e-12`、Rtotal `0.999983627560756`、Ttotal `1.570950234381809e-05`、Avolume `8.856354534342745e-08`。它验证的是缩小诊断链路，不能代替 336-cell G0 p6 的精度证据。

## 已到达的 G0 规模与未到达对象

| 对象 | G0 实际/导出事实 | 后续未到达项 | 数据身份 |
|---|---|---|---|
| 网格 | 轴区间 `6×4×14`；336 owned cells | G1 的 880 cells 未构建 | G0 measured; G1 derived |
| p6 FE | 229,680 full rows；68,256 active trace；10,224 slave；151,200 interior；局部维度 `882/450/432` | global p6 matrix未组装；没有 solver rows/NNZ 完整报告 | setup measured |
| q4 FE | 69,856 rows；28,992 active trace；4,576 slave；36,288 interior | q4 global factorization未开始；没有 NNZ/factor memory | setup measured |
| modal manifest | 80 modes；SHA `c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a` | 没有正式通道功率或 official fields | setup measured |
| native AQ projection | DtN relative `9.584104029325266e-15`；volume relative `2.7510630979502593e-15`；限值 `1e-10` | 这不是 outer solve 的 residual | component/setup check pass |

## 资源观测口径

| 统计量 | G0 attempt 2 | 含义 |
|---|---:|---|
| watchdog simultaneous process-tree RSS peak | `1,538,707,456 B` | 在 322 个 watchdog 样本中采到的同时进程树 RSS 峰值 |
| live cgroup `memory.current` | `1,080,860,800 B` | 同一活动快照下的当前 cgroup 用量 |
| live cgroup `memory.peak` | `1,673,117,696 B` | cgroup high-water；不同于 process-tree RSS，不能相加 |
| process-tree swap / OOM kill | `0 B / 0` | 没有观测到 Task swap 或 OOM kill |
| PSS | disabled by profile | 不提供 PSS 峰值 |
| N2 RSS | `368.8008 MiB` | 各 rank 历史峰值求和的上界，不是 simultaneous tree RSS |

尝试 2 在 setup/cleanup 阶段失败。观察到的 RSS/cgroup 数值不能当成求解峰、容量 Gate 或成功内存成绩。Attempt 1 RSS 峰值为 `142,209,024 B`，同样只对应 3.896 s 的失败启动流程。

`shared_workflow_ledger.json` 最终 SHA256=`d70e23cd1cb7461408ff9872242ba646f0a9e517330108069bfe993532656e84`；累计账面 `91.793057 s`，bug replay 计数 `1`，时间策略是 `observe_only`。任务的 `43,200 s` 字段仅用于参考/记账，**不是硬性 12 小时 timeout**。

## 容量结论与下一步

本轮没有足够数据对 p4 factor、端口数组、局部消元缓存、Krylov basis 或全流程峰值作容量归因：p4 全局因子和 outer Krylov 从未建立，所有 official accuracy Gate 也没有运行。因此不估算 2 TB 目标可容纳规模，不选择 Phase II 算法，也不声称某一对象已被证实为主瓶颈。

唯一授权的实现错误重放已经用完。新增 G0/G1/direct 数值运行必须先由后续 review 明确新范围与授权；当前留下的最近修复只完成了 targeted G0 mesh/FE/MPC fixture。
