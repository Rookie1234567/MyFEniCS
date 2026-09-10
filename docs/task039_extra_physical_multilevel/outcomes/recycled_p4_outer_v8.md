# Task39extra V8 K4：recycled p4 outer 受控负结果

## 结论

本轮唯一正式原始模型在 `59` 个外层 PC 后按 screen 规则受控停止。worker 的状态是 `NORMAL_SCREEN_STOP`，wrapper/parent 的工程分类是 `WORKER_FAILED`；这表示物理进展 Gate 未通过后的正常受控退出，不是 MPI、内存或清场故障。独立 checker 的完整显式真相对残差为 `0.09114277170870674`，终端解向量重算值为 `0.09114277170870651`，均远高于 `1e-6`。

因此 V8 的整体状态是 `RECYCLE_BOUNDED_NEGATIVE`：有限 CARRY 序列确实减少了重复 B4 工作，但当前有限容量的近似粗逆没有支撑冻结的完整外层进展。notch、recovery、official E/H、near-field、R/T/A、`A_volume` 和衍射级均保持 `not_run_locked`，不能从失败外层产生正式物理输出。

这里的“recycled”是一个很小的 Krylov 方向池：同一物理 `A4` 处理不同右端项时，保留本次求解产生的至多 8 对方向及其算子像，以减少重复搜索。它不是准确 p4 逆，也不是参考答案缓存；因此 B4 成本下降与完整 Maxwell 外层收敛是两个不同问题。

## 身份、方法和终态

| 项目 | 记录 |
|---|---|
| 模型 | 13.5 nm、grazing 1°、p6/h10、MPI1、80 modes、complex128；物理模型 SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| 输入 | `input/task39extra/original_13p5nm_p6h10_balanced_h6_entity_gcrot8_v8.dat`；SHA `0cf709b02e21ca94788196024b2c25014162567e18ab2f2d9b5aeade3adf994d` |
| source | K2 `49ddad7f4b196e45e449c1044d90b17d6ee6300c`；K1 运行 `09c1b3a6f3c21d4d0e99feb36a97972819971fb3`；K1 checker 修复 `49ddad7f4b196e45e449c1044d90b17d6ee6300c` |
| profile | `balanced_h6_entity_gcrot8_v8` / `ENTITY_GCROT8`；本地 SciPy `1.11.4` `gcrotmk(m=8,k=8,maxiter=1,truncate='smallest',atol=0)` |
| 外层 | 一个 right FGMRES32、`max_iterations=2048`、零初值、一个 KSP create/solve；没有恢复 V7 的解或 K1 的池 |
| K2 终态 | 59 PC、60 matvec、KSP create/solve/destroy=`1/1/1`；官方结果 `null`；官方输出 `not_run` |
| residual Gate | full explicit true relative `0.09114277170870674 > 1e-6`；checker 独立失败项为 fine residual 和 official outputs |
| screen Gate | 40/48/56 节点为 `0.13301163584099004 / 0.1075737569345282 / 0.09320528571929491`，末三节点几何缩比约 `0.837 > 0.80`，故在第 59 步停止 |
| 内部工作 | 118 次 I4，118 次均为 `APPROXIMATE`，`0` 次达到 `1e-4` inner target；K2 B4 累计 `980`；最大池 `8` 对 |

K2 的真实节点为：

| 外层迭代 | 0 | 8 | 16 | 24 | 32 | 40 | 48 | 56 | 59 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| explicit true residual | 1.0 | 0.8736493980326089 | 0.48427086094403843 | 0.23070247906752248 | 0.1511040946440908 | 0.13301163584099004 | 0.1075737569345282 | 0.09320528571929491 | 0.09114277170870651 |

## 同节点、同时间和不同停止点

为避免把“更早停止”误写成求解提速，下面分别给出同一外层迭代的实际监测节点、接近同一求解时间的实际监测节点，以及三条路线的最终停止点。没有对缺失节点做插值。

### 同一外层迭代：第 56 个 PC

| 路线 | 实际节点 | solve clock (s) | full explicit true residual | 说明 |
|---|---:|---:|---:|---|
| V8 K2 recycled outer | 56 | 1731.0239353248717 | 0.09320528571929491 | 继续条件未满足，随后在 59 停止 |
| V7 A entity16 | 56 | 2490.940211896077 | 0.075149822567280145 | 继续到中点 121，仍未达 `1e-3` |
| V5 exact p4 original | 56 | 604.39200434937197 | 0.030977506489411246 | 准确 p4 基线，最终继续到 564 步通过 |

同一迭代的比较显示：K2 比 V7 A 更早达到该节点，但其残差较大；V5 准确 p4 的残差更低，但它使用的是不同质量的准确 p4 粗逆。该表不能被解释为完整求解速度排名。

### 接近同一求解时间：实际节点而非对齐后的曲线

| 路线 | 实际节点 | solve clock (s) | residual | 当时状态 |
|---|---:|---:|---:|---|
| V8 K2 recycled outer | 59 | 1831.843792324894 | 0.09114277170870651 | screen stop |
| V7 A entity16 | 41 | 1818.5808033521107 | 0.11311148655819143 | 仍在继续 |
| V5 exact p4 original | 160 | 1730.2127802911145 | 0.0010143070512597125 | 仍在继续；下一实际节点 172 为 `0.0009115148645006361` |

K2 的总 charge 较短主要因为它在第 59 步停止，而 V7 A 运行到 121 步、V5 成功基线运行到 564 步。不能用这三个终止总时间宣称 V8 求解器比 V7 或 V5 更快。

### 最终停止点

| 路线 | 步数 | solve/中点秒数 | 显式真残差 | 状态 |
|---|---:|---:|---:|---|
| V8 K2 recycled outer | 59 | 1831.843792324894 | 0.09114277170870674 | `RECYCLE_BOUNDED_NEGATIVE` |
| V7 A entity16 | 121 | 5423.950016599915 | 0.04256451212826674 | `PROGRESS_INSUFFICIENT_AT_MID_BUDGET` |
| V5 exact p4 original | 564 | 6102.614282540989 | `9.932289219916376e-7` | 双模型成功基线中的原始模型 |

## 成本证据：复用确实省了内部工作

在前 59 个外层 PC 的同前缀比较中，V8 K2 的 B4 累计为 `980`，V7 A entity16 的 B4 累计为 `1888`，少 `908` 次，即 `48.09322033898305%`。这是从两个 `pc_applies.jsonl` 的实际累计节点读取的内部工作量减少；它不是完整外层的 speedup，也不改变 residual Gate。

K2 内层账本还记录了 `A4_matvec=1098`、`explicit_A4=260`，118 次 I4 中最大实际 elapsed 为 `16.918557867058553 s`。逐 I4 的 118 行 compact 表见 [per-I4 compact rows](records/recycled_p4_i4_rows_v8.json)：每行保留 RHS 的 g1/g2、pool rank 起止、new/completed B4、A4 的 total/attempted/explicit/cached/native/pool 分类、native relative residual、pool projection、`eps_norm`、truncation、elapsed 和 bytes，以及每 32 次调用的 spot/eps 摘要；没有写入向量或整份 `pc_applies` raw。由于原始运行没有分别测量每个 I4 的所有 timing 子组件，compact 表明确保留总 elapsed，并将这些子组件标记为未单独测量。

内层质量审计也保留在 compact record 中：native spot 审计覆盖调用 `[1, 32, 64, 96]`，共检查 `25` 对，最大绝对误差 `3.048957055467129e-12`，限值 `1e-10`；终端退出审计另有 `8` 次、最大误差 `9.657062051613457e-13`、耗时 `3.6081345150014386 s`。逐 I4 的 pool closure 和 orthogonality 最大误差分别为 `1.3729122738464301e-12` 与 `8.420384855112346e-14`，对应 pool 限值均为 `1e-10`；这两个量不冒称为终端 `eps` closure。真实 BAL_H 终端 `eps` audit 的 closure relative 为 `8.534472501127559e-13`，限值为 `1e-8`，共 `3` 次 audit、总耗时 `4.5635235459776595 s`，其中 A6 和 PH 额外耗时分别为 `4.207173248985782 s` 与 `0.3528787540271878 s`。

K1 的六项有限控制给出同方向的成本证据。RESET 每个 RHS 前清空池，CARRY 只在序列开头清空池：

| RHS | RESET s | CARRY s | RESET B4 | CARRY B4 |
|---|---:|---:|---:|---:|
| A2R160 g1 | 18.655620419071056 | 16.588588000973687 | 16 | 16 |
| A2R160 g2 | 17.054215552983806 | 16.31573777506128 | 16 | 15 |
| LIGHT448 g1 | 17.65030103805475 | 14.155002929037437 | 16 | 14 |
| LIGHT448 g2 | 17.33492745796684 | 13.294386520981789 | 16 | 13 |
| JOINT448 g1 | 17.008818196947686 | 12.43555125896819 | 16 | 12 |
| JOINT448 g2 | 15.976367055089213 | 11.486373497988097 | 16 | 11 |
| **总计** | **103.68024972011335** | **84.27563998301048** | **96** | **81** |

CARRY 的总实测序列时间少 `19.40460973710287 s`，相对 RESET 减少 `18.7158207946894%`；六项都没有时间回退。另一方面，CARRY 是有状态的近似序列，六个返回的近似 residual 并不与 RESET 逐项相同，所以这只能证明有限控制中的重复搜索成本下降，不能证明完整模型的物理质量或外层收敛保证。

## 双时钟、资源和账本口径

K2 的时间分层如下，避免把 worker solve、watchdog process-tree 和 batch charge 混成一个数：

| 口径 | 秒数 | 含义 |
|---|---:|---|
| worker solve monotonic | `1686.910741629079` | worker 求解阶段的 monotonic 时间 |
| worker solve conservative | `1839.8522862158648` | worker 求解阶段的 conservative-realtime 时间 |
| watchdog process-tree monotonic | `1890.020882648998` | 父进程及全部后代的清场前 monotonic 口径 |
| watchdog conservative | `2060.6735806883685` | watchdog conservative workflow interval |
| runner outer actual charge | `2060.801451572` | batch ledger 中 K2 original 的实际 conservative charge |
| UTC positive excess | `170.64719553199575` | conservative 与 monotonic 的时钟差，单列不重复计费 |

同时记录：process-tree RSS 峰值 `1530359808 B`，process-tree swap 峰值 `0 B`，global swap delta `0/0`，`descendants_cleared=true`，剩余子进程为空。`55625984 B` 是新增 payload 的 derived upper bound，不是 RSS，也不是整个 PDE 的内存峰值。

共享账本的 `3600 s` 是 K0/K1 preparation 的保守 RESERVED 上界，不是实测 CPU 或墙钟。K2 的实际 outer charge 是 `2060.801451572 s`；ledger 的 `charged_seconds_after_k2=5660.801451572001 s` 表示“3600 s preparation reserve + K2 actual charge”的记账语义，不应当报告成累计实际求解时间。K1 parent outer 的实测 `512.710820815 s` 已在该 preparation envelope 中计入一次；K1 nested stage `505.9943155682661 s`、finite control `305.74144293995806 s` 不再重复加入。failed preflight 保留为 `charged=false` 的真实失败前证据，不能改写为零成本；旧 V7 账本没有并入。

## 观测事实与根因假设分开

已经由 raw/checker 直接支持的事实是：

- CARRY/GCROT 方向复用降低了有限控制和同前缀的 B4 工作；
- K2 的 118 次 I4 全是 approximate return，没有一次达到 `1e-4` 目标；
- K2 的 residual 从 1 降到约 0.091，但 40/48/56 节点的继续条件不满足；
- 资源和清场 Gate 通过，失败不是 swap、RSS 或后代残留导致；
- fine residual Gate 和 official-output Gate 未通过，notch/recovery 没有启动。

以下只是待后续设计验证的根因假设，本轮没有新诊断来确认它们：有限 rank 池可能不足以表达全局外层误差；较便宜的 approximate I4 返回可能留下过大的 coarse defect；或者效果主要依赖当前 RHS 顺序和池演化，不能推广成“所有 recycling 都无效”或“所有困难方向都低秩”。因此本轮只关闭这个固定 rank/profile 候选，不作数学不可能性结论。

## 未运行项、保留项和停止决定

`not_run_locked`：notch、recovery、official E/H、near-field、R/T/A、`A_volume`、能量闭合、显著衍射级、独立 A4 reference comparison、rank/策略扫描、第二种 recycling、增 rank、V7 候选重跑、5 nm/0.7 nm 和 workstation heavy case。V7 A/B 旧 compact、V5 双模型成功 baseline、K1 `checker_pre_fix` 和所有旧 raw 负结果均保留，不覆盖、不改判。

本轮不改变 ordinary default，也不提供 master merge approval。下一步若要继续，必须由新的 review 明确冻结新的方法、source、输入、资源和独立输出 Gate；本 K4 结束不自动启动更大子域或新的 PDE。

## 证据入口

- [K4 compact record](records/recycled_p4_outer_v8.json)：身份、节点、双时钟、账本、对照和 raw hash 的紧凑绑定。
- [K2 result binding](../../../benchmarks/artifacts/task39extra/v8_k2_original/49ddad7f4b196e45e449c1044d90b17d6ee6300c/k2_result_binding.json)：worker/checker/resource/artifact hash。
- [V7 A compact](records/bounded_inexact_outer_a_original_v7.json) 与 [V5 compact](records/balanced_coupling_v5.json)：旧候选和准确 p4 基线的权威摘要。
- 原始大矩阵、因子、fields、checkpoint 和长日志继续留在 ignored artifact 根目录；本次只提交文档和 compact evidence。
