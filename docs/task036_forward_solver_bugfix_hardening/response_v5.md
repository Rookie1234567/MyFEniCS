# Task036 Review V5 执行响应

> **当前结论 / H5-M1 最终更新**：direct Hybrid 已在同一 dirty source manifest 下修复并通过
> A007-P 以及五点 grazing/P direct 扫描的数值 Gate；当前 Hybrid 与同 manifest Full3D 的
> A007-P 对照同时满足完整 observable、external wall 和 simultaneous process-tree peak
> 更低。下列第 1--17 节保留为历史阶段记录，不再代表当前状态；当前状态以第 18 节为准。

## 1. 结论先行

本轮严格按 `review_report_v5.md` 执行了接口内移诊断：

```text
I0 30/90 assemble-only = pass
I0 40/80 assemble-only = pass
I1 30/90 actual        = physics_fail / resource_pass
I2 40/80 actual        = physics_fail / resource_fail
R0 mode-capacity audit = not_run_by_physics_gate
R1 localized buffer    = not_run_by_R0_gate
```

最重要的物理结论是：把上下局部三维有限元端部加厚、把中间模态传播段从
`100 nm`缩短到`60 nm`和`40 nm`，确实改善了总能量闭合和中间场，但没有把固定衍射
通道从`79/96`推进到`96/96`。因此接口位置是误差来源之一，却不是当前通道误差的充分
解释。继续用同一种接口内移，或直接据此开发局部 evanescent buffer，都没有通过本 Review
要求的因果 Gate。

最终分类为：

```text
ASYMPTOTIC_INTERFACE_HYPOTHESIS_NOT_SUFFICIENT
production qualification = fail
ordinary default = unchanged
```

其中“not sufficient”不等于完全没有接口效应：energy 和总量给出了部分正信号，但正式
96-channel Gate 没有闭合。

本轮没有开发或运行 RCWA，也没有进入迭代法、波长 continuation、P 偏振、p6/59-goal、
h/p 或参数扫描。

## 2. 权威身份与范围

| 角色 | 完整 SHA / SHA-256 | 说明 |
|---|---|---|
| Review V5 起点 | `76e92feb95b27b1b840b4e5b96f4c87de14ba4ef` | 含唯一有效的 Review V5 |
| I0 数值源码 | `0870e10c9b41aa5859c76ea1b5e5596c73e83a73` | 有界接口 Gate 和 assemble-only preflight |
| I1/I2 数值源码 | `3259bcb6ed2b6d71a9c51a701c4cf51410d7b353` | 只比 I0 多一个跨 clean-worktree 的 evidence 路径修复 |
| reused Full3D source | `6d5e9781bcb1458ecac7a77af22fa2d420f0cd55` | same-input p5/h10/Ny4/MPI8 authority |
| Full3D watchdog SHA-256 | `f91d30d7237c1f39aae7633309dc076e5acf04532f92214024fb48e691a9cfb8` | 未重跑 Full3D |
| historical 10/110 strong source | `5b04a4398fe752083024487ca95eb00a09e646cc` | Review V3 controlled negative |

正式环境均为 WSL Ubuntu 24.04、MPI8、PETSc `complex128/int32`、p5/h10、Ny4、
S 偏振、0.5° grazing、45° azimuth、M120/方向和
`assembly_time_static_condensed`。I1/I2 在独立 detached clean worktree 中执行；主工作树中
用户已有的 `hybrid_production_readiness_assessment.md` 尾随空格修改没有被覆盖、暂存或提交。

## 3. 本轮最小实现

本轮没有修改 strong-trace 数值内核。实现只包含：

1. 只对 A004-S、M120、strong-trace 开放 `30/90`和`40/80`两个 Review V5 接口点；
2. 增加 assemble-only 的材料 z 不变性、真实网格面、局部/中间 cell 数、传播长度、
   traction beta、`D R-I`、无自由 trace complement、无稠密接口平方算子的绑定检查；
3. 允许 Full3D 选定平面比较使用 archive 中与当前 modal 区间严格匹配的平面子集；
4. 允许已经通过 SHA Gate 的 Full3D ignored artifact 由独立 clean worktree 读取绝对目录。

没有增加 package、campaign、状态机、receipt/hash 框架、watchdog 框架、罚项、接口扫描器或
RCWA 代码。ordinary default 未改变。

## 4. I0：装配预检

I0 只构造完整方形 strong-trace Petrov--Galerkin 矩阵，在 MUMPS 前停止；因此 factor NNZ
和求解结果在这一阶段均为 `not_run`。

| 指标 | 30/90 | 40/80 | Full3D 对照 |
|---|---:|---:|---:|
| modal middle 长度 | 60 nm | 40 nm | 不适用 |
| bottom/top local z cells | 4 / 4 | 5 / 5 | 14 total |
| rows | 26,256 | 32,736 | 46,656 |
| rows / Full3D | 56.276% | 70.165% | 100% |
| matrix NNZ | 16,512,096 | 20,317,296 | 26,952,096 |
| NNZ / Full3D | 61.265% | 75.383% | 100% |
| bottom/top interface trace rows | 1,200 / 1,200 | 1,200 / 1,200 | 不适用 |
| bottom/top `D R-I` | `1.95e-12 / 2.33e-12` | `2.54e-12 / 2.63e-12` | limit `1e-10` |
| preflight 总时长 | 133.789 s | 141.668 s | 不适用 |
| 判定 | pass | pass | — |

两个点的六项 middle material layer hash 完全一致；接口均为实际 p5/h10 网格面。没有形成
`R D`、`I-RD`、全维乘子或稠密 interface square。

## 5. actual PDE 资源与结构结果

这里的“authority GiB”是 watchdog 冻结的同时存活 MPI worker/process-tree 资源口径；
RSS/PSS/USS 是完整 8-rank `smaps` 同时和。两种口径均列出，避免把历史逐 rank 峰值相加。

| 模型 | middle | rows | matrix NNZ | factor NNZ | fill | authority GiB | smaps RSS/PSS/USS GiB | swap | wall s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full3D authority | — | 46,656 | 26,952,096 | 164,378,718 | 6.099 | 10.549 | 10.441 / 8.951 / 8.541 | 0 | 869.607 |
| old strong 10/110 | 100 nm | 13,296 | 8,901,696 | 29,290,898 | 3.290 | 7.893 | 7.802 / 4.531 / 4.105 | 0 | 484.913 |
| I1 strong 30/90 | 60 nm | 26,256 | 16,512,096 | 70,778,288 | 4.286 | 8.291 | 8.730 / 6.522 / 6.079 | 0 | 179.024 |
| I2 strong 40/80 | 40 nm | 32,736 | 20,317,296 | 100,178,268 | 4.931 | 9.999 | 9.931 / 7.851 / 7.424 | 0 | 195.277 |

相对 Full3D 的 whole-job authority 比值为：old `74.82%`、I1 `78.59%`、I2 `94.79%`。
Review V5 的 85% engineering Gate 因此在 I1 通过、在 I2 失败。按完整 smaps RSS 比较，
I1 为 Full3D 的`83.61%`，I2 为`95.12%`，判定相同。

相对 old 10/110，I1 的 rows/NNZ/factor 分别增加`97.47% / 85.49% / 141.64%`，
authority 增加`5.04%`；I2 分别增加`146.21% / 128.24% / 242.01%`，authority 增加
`26.68%`。I1 到 I2 的单一同-SHA比较显示 factor 又增加`41.54%`、authority 增加
`20.61%`。这说明缩短 middle 的代价主要落在更大的端部矩阵和更高 factor fill 上。

old 10/110 与本轮使用不同 numerical SHA，wall time 的大幅下降还包含此后 field recovery
和生命周期改进，不能全部归因于接口位置；I1 到 I2 的`+9.08%`才是本轮最干净的同-SHA
时间比较。

## 6. I1/I2 正式物理 Gate

| Gate | I1 30/90 | I2 40/80 | 限值 | 判定 |
|---|---:|---:|---:|---|
| fixed channels | **79/96** | **79/96** | 96/96 | 两者 fail |
| `abs(R+T+A_volume-1)` | `7.5390e-6` | `4.8453e-6` | `1e-5` | pass / pass |
| max `abs(Delta R/T/A_volume)` vs Full3D | `4.8617e-6` | `2.7680e-6` | `1e-4` | pass / pass |
| reduced true residual | `5.9442e-11` | `6.6078e-11` | `1e-9` | pass / pass |
| strong trace identity, bottom/top | `0 / 0` | `0 / 0` | `1e-10` | pass / pass |
| Petrov traction max | `3.3042e-10` | `3.0451e-10` | `1e-8` | pass / pass |
| noninterface FE max | `5.8586e-11` | `1.4796e-10` | `1e-9` | pass / pass |
| external DtN max | `9.5931e-13` | `1.9116e-12` | `1e-9` | pass / pass |
| bottom/top `D R-I` max | `3.8396e-12` | `2.5682e-12` | `1e-10` | pass / pass |
| zero swap | true | true | true | pass / pass |
| resource / Full3D authority | 78.59% | **94.79%** | <=85% | pass / fail |

所以 I1 不能写成 overall engineering pass：它是“资源通过但 fixed-channel 物理失败”。I2
同时是物理失败和资源失败。

## 7. R/T/A 与中间场

| quantity | Full3D | old 10/110 | I1 30/90 | I2 40/80 |
|---|---:|---:|---:|---:|
| `R_total` | 0.621460748388 | 0.621472858503 | 0.621465610123 | 0.621463516401 |
| `T_total` | 0.006248078496 | 0.006248145689 | 0.006248107241 | 0.006248121620 |
| `A_balance` | 0.372291173116 | 0.372278995808 | 0.372286282637 | 0.372288361979 |
| `A_volume` | 0.372291173114 | 0.372294312469 | 0.372293821652 | 0.372293207311 |
| energy closure | `-1.632e-12` | `+1.531666e-5` | `+7.539015e-6` | `+4.845332e-6` |
| z=60 E relative L2 vs Full3D | — | — | `1.5953e-5` | `1.2021e-5` |
| z=60 H relative L2 vs Full3D | — | — | `1.9548e-5` | `1.7027e-5` |

能量和中心平面场随接口内移单调改善。这是 boundary-layer/interface-placement 确实有影响的
实测证据，但 fixed-channel 数没有从 I1 到 I2 继续改善，因此不能把它写成完整根因。

## 8. 96 通道 delta 与失败集合

合同保持原值：significant power floor `1e-8`；significant power/complex amplitude 相对误差
`<=1e-3`；weak power/complex amplitude 绝对误差`<=1e-8`。

| 模型 | pass | significant fail | weak fail | power fail | amplitude fail |
|---|---:|---:|---:|---:|---:|
| old 10/110 | 77/96 | 6 | 13 | 5 | 18 |
| I1 30/90 | 79/96 | 5 | 12 | 4 | 17 |
| I2 40/80 | 79/96 | 6 | 11 | 4 | 16 |

old 到 I1 只净修复两个 identity：`bottom (0,0,p)`和`top (-1,0,p)`。I1 到 I2 又修复
`top (0,-2,p)`，但新增`bottom (-1,0,p)`，所以总通过数不变。

以下 16 个失败 identity 在 old、I1、I2 三者中全部持续存在：

```text
bottom: (-6,-2,s), (-6,-1,s), (-5,0,s), (-4,0,s), (-3,0,s),
        ( 0,-2,p), ( 0,-2,s), ( 0,-1,s)
top:    (-6,-2,s), (-6,-1,s), (-5,0,s), (-4,0,s), (-3,0,s),
        ( 0,-2,s), ( 0,-1,s), ( 0, 0,p)
```

完整 96 项 amplitude/power 原值位于各自 `solver_record.json` 的
`validation.external_diffraction_orders`；本报告没有删除或放宽任何失败项。

## 9. 根因 delta 与 R0/R1 决策

Review V5 冻结的 Full3D trace 投影 residual 为：

| interface z | exact M120 trace residual |
|---:|---:|
| 10 nm | `3.514657e-6` |
| 30 nm | `2.881134e-9` |
| 40 nm | `8.852074e-11` |
| 80 nm | `3.717959e-10` |
| 90 nm | `8.687626e-9` |
| 110 nm | `5.224931e-6` |

从 30/90 到 40/80，端点可表示性又改善约 23--33 倍，但 16 个通道失败完全持续，且
通过总数仍为 79/96。这使以下排除判断成立：

- 不是 strong-trace 代数错误：`D R-I`、trace identity、Petrov、noninterface FE 和 external
  DtN residual 全部远低于 Gate；
- 不是模态身份漂移：两个接口点使用相同 QEP family、120/240 candidate window，Gram 和
  biorthogonality 均稳定；
- 不是单纯 external DtN 后处理错误：direct tangential projection 和 port totals Gate 通过；
- 不是只存在于弱通道的显示噪声：I1/I2 仍有 5--6 个 significant channel 失败；
- same-input Full3D 与 Hybrid 的 geometry、mesh、p、Ny、偏振、入射角和端口定义均通过 hash
  绑定，但二者的离散算子并不等价：Hybrid 中间仍是有限 M120 的模态/轴向传播算子。

因此当前最窄结论是：接口边界层误差解释了 energy 和一部分 channel 改善，剩余误差更像
M120 core propagation/coupling 对小衍射幅值的累积误差，而不是仅靠端点 extra QEP modes
即可修复的局部缺失空间。

Review V5 明确要求“接口内移物理成功”才解锁 R0。本轮两个 actual 均未达到 96/96，故：

```text
R0 = not_run_by_physics_gate
R1 = not_run_by_R0_gate
```

没有用已有 M240 candidate 冒充 R0 结论，也没有实现 localized buffer。下一轮若继续，应先
由 Review 判断是否转向 transfer/optimal-port 局部算子；本轮不自动实施 R2，也不转入迭代法。

## 10. 路径失败与证据保留

I1 在正式成功运行前有两次 post-solve evidence 路径失败。两次 MUMPS 已结束，但在 Full3D
场比较前因 clean worktree 与主 checkout 的 ignored artifact 绝对路径不能
`relative_to(ROOT)`而退出，均没有 `solver_record`，不具有物理 credit：

```text
benchmarks/artifacts/task036/0870e10c9b41aa5859c76ea1b5e5596c73e83a73/
  review_v5_interface/I1_30_90/

benchmarks/artifacts/task036/3259bcb6ed2b6d71a9c51a701c4cf51410d7b353/
  review_v5_interface/I1_30_90_retry_pathfix/
```

两份失败 stdout/timeline 均保留，没有覆盖或改写为成功。最终成功 I1 使用同一物理输入，
只修正 evidence 路径入口。

## 11. Evidence index

| evidence | 相对路径 | SHA-256 |
|---|---|---|
| I0 30/90 preflight | `benchmarks/artifacts/task036/0870e10c9b41aa5859c76ea1b5e5596c73e83a73/review_v5_interface/I0_30_90/preflight.json` | `fef7818b20da48c34cd16c45a2fc3dfa5c19764383d8309ded8d833652549569` |
| I0 40/80 preflight | `benchmarks/artifacts/task036/0870e10c9b41aa5859c76ea1b5e5596c73e83a73/review_v5_interface/I0_40_80/preflight.json` | `ab1bb2bd1680591df65d2be292d5c3b2ccaf42810e48c81a9856b2115e74b2e4` |
| I1 solver | `benchmarks/artifacts/task036_v5_local/3259bcb6ed2b6d71a9c51a701c4cf51410d7b353/review_v5_interface/I1_30_90_retry2_lexical_paths/solver_record.json` | `e2893447997f0b2286e2ad8ae93132a1cbe6165530db61c3b059aaaadad6d7e5` |
| I1 memory | `benchmarks/artifacts/task036_v5_local/3259bcb6ed2b6d71a9c51a701c4cf51410d7b353/review_v5_interface/I1_30_90_retry2_lexical_paths/memory_sampler_summary.json` | `c8e5797377e14a5e0a08d1f177aa7fd4f3c8f14f6070fb9c57ae696bcba00be5` |
| I2 solver | `benchmarks/artifacts/task036_v5_local/3259bcb6ed2b6d71a9c51a701c4cf51410d7b353/review_v5_interface/I2_40_80/solver_record.json` | `80f70ea16a1f2832ea486a9e0804f0deba532acf14c368a1a22c973e4d2a2e24` |
| I2 memory | `benchmarks/artifacts/task036_v5_local/3259bcb6ed2b6d71a9c51a701c4cf51410d7b353/review_v5_interface/I2_40_80/memory_sampler_summary.json` | `1d7494511a7505451419ee38e075ef8fa997d9e58a7f865ac4ca53ff4c07a9b7` |

这些是 ignored heavy/raw artifacts，不进入 Git；报告只记录可复核路径和哈希。

## 12. 测试与交付边界

最终源码验证：

- Task032/033/034/035c/036 相关 runner、gate、strong-trace、postprocess 和 one-cell
  targeted tests：`127 passed in 15.00 s`；
- Ruff：pass；
- changed-file `git diff --check`：pass。

额外运行 `src/test/test_26_documentation_contract.py` 得到`13 passed, 1 failed`。失败项是静态
case 集合没有枚举仓库中既有的 Case098 和 Case099 目录；本轮没有修改该测试、Case098 或
Case099 目录，且这与 Review V5 的接口数值结果无关。它被保留为 pre-existing repository
documentation-contract failure，没有借本轮扩修或隐藏。

由于 actual 已形成正式负结果，并且用户明确允许负结果后直接收尾，本轮没有运行全仓库
pytest。

本轮明确未运行或未实现：

```text
R0 mode-capacity audit
R1 localized-evanescent buffer
R2 transfer/optimal-port implementation
M240/M480/M492 actual PDE
P polarization anchors
226-point scan
iterative or matrix-free solver
wavelength continuation
p6/59-goal or h/p
RCWA development or RCWA run
```

master 未修改、未合并；ordinary default 未改变。最终 execution-branch HEAD、远程同步和工作
树状态在提交并推送本 response 后由最终聊天报告给出。

## 13. 后续补充：exact Cauchy / port-operator / 16-channel audit

本节结论是截至 exact-Cauchy audit checkpoint 的历史结论；后续 C2、D0、D1a 和 D1b
状态以第17节为准，不把本节旧的 candidate 文本当作当前实现状态。

在没有新增 review 文件的情况下，本节按用户要求继续追加到原 `response_v5.md`。完整表格、
方法和 evidence index 见：

[`outcomes/exact_cauchy_port_operator_audit.md`](outcomes/exact_cauchy_port_operator_audit.md)

本补充使用 numerical source
`c8725e9eedc8a558719008f8762bc79eca48fbb7`，在 MPI8/complex128/int32 环境中复用 frozen
Full3D traces、one-cell Schur blocks 和 old/I1/I2 records。总审计时间为 `134.992 s`；没有
运行新的 Full3D 或 Hybrid forward PDE，也没有运行 actual enrichment candidate。

### 13.1 对第 9 节根因推断的实证修正

第 9 节在当时证据下把剩余误差暂时指向“M120 core propagation/coupling 累积误差”。新的
exact port-operator audit 已把这个推断进一步收窄并**实证修正**：

| middle length | exact FE selected port operator vs current scalar-CG modal operator |
|---:|---:|
| 40 nm | `1.593747e-11` |
| 60 nm | `1.749079e-11` |
| 100 nm | `1.951491e-11` |

因此在当前 selected M120 R/W space 内，中间 scalar-CG propagation/operator 是正确的；
不应继续修改 core propagation。真正仍未闭合的是端部 selected space 对完整 Maxwell Cauchy
数据的表示：

| best approximation | aggregate relative | max cell relative |
|---|---:|---:|
| electric trace | `1.099844e-6` | `2.072564e-6` |
| magnetic/traction | `2.364065e-5` | `4.609620e-5` |
| joint Cauchy | `1.677328e-5` | `3.214277e-5` |

这里的 traction 是 Maxwell 弱式中与 `n x H` 成比例的离散 conormal，不是 sampled H。
只看 electric trace 会把 aggregate 缺口低估约 21.5 倍。中心 selected-Petrov 通量连续性可到
`5.72e-9`，但靠近 20/100 nm 两端分别回升到 `5.73e-5`和`2.00e-4`，支持“健康的
M120 core + 不完整的端部 joint-Cauchy port space”。

### 13.2 Port pair 与 16 个失败通道

right/left raw Gram conditions 分别为 `3.12e4 / 4.23e4`，但白化后的 pair condition 为
`1.00001975`、inf-sup 最小奇异值为 `0.99998025`。所以这不是物理 port pairing 退化，raw
condition 主要是坐标尺度。

16/16 个持续失败通道的代数 adjoint residual 均不高于 `1.776730e-12`。归一化接口灵敏度
的第一方向只占 `6.3915%`，前两方向只占 `12.7827%`；达到 90%/95%/99% 分别需要
15/16/16 个方向。因此失败通道不是由少量共同 output-adjoint directions 主导，不能靠两三
个通道专用模式解决。局部 fixed-trace predictor 的向量相对误差仍为 `0.999467`，不授予
逐通道定量预测 credit。

### 13.3 Raw diagnostic 纠正

正式 raw `audit.json` 中原字段
`exact_cauchy.all_internal_conormal_cancellation_relative` 将左右端面不同编号/orientation 的
1,200 维 active-row 向量直接相加，其约 `1.37` 的值没有物理意义，现标记为 withdrawn。

替代结果由原 coordinate-matched `projected_one_cell_blocks.npz` 和
`exact_petrov_plane_coefficients.npz` 在共同 Petrov 坐标离线重放得到；没有重跑 PDE。runner
也已修正为只计算 side-specific Petrov 映射后的连续性。tracked compact 为：

[`../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_exact_cauchy_port_audit_v1.json`](../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_exact_cauchy_port_audit_v1.json)

### 13.4 唯一冻结的下一路线与 PDE 决策

只冻结一个 enrichment family：

```text
transfer_optimal_port_modes
```

它应从两端短 buffer 的 exact discrete transfer/port operator 中提取 joint trace/traction 最
重要的共同方向，corrector 只在端部局部存在并随后 Schur 凝聚；目标仍是恢复 10/110 nm
接口，让原 M120 core 跨完整 100 nm。`Cauchy-complete discrete Bloch correctors` 和
`failing-channel adjoint modes` 本轮均不同时实施。

本补充只修正 diagnostic 并完成根因审计，**没有形成会改变 forward solution 的数值修复**。
因此即使用户允许“修正成功后最终跑一次 PDE”，当前也不满足该条件；现在重跑只会复现旧
Hybrid negative。只有后续 transfer-optimal 实现先通过 exact fixture、joint-Cauchy
projection、orientation/row-map 和资源 preflight，才有理由只运行一次 A004-S actual PDE。

```text
exact_Cauchy_audit = complete
selected_M120_core_operator = qualified_inside_selected_space
endpoint_joint_Cauchy = incomplete
few_common_failing_channel_directions = false
frozen_next_family = transfer_optimal_port_modes
actual_candidate_at_exact_cauchy_checkpoint = not_implemented / not_run
Hybrid production = fail
ordinary default = unchanged
```

## 14. Direct-D0 trace-only AIJ first static slice

本轮只交付 Direct-D0 的静态切片，没有启动 live、PDE、MUMPS numeric factor 或 runner。
目标是把已经存在的 11-plane/10-cell trace action 显式表示为 13,200 行的三对角带状
AIJ；它只包含端面 trace 与 one-cell Schur，不把 cell interior 或端帽 complement 组回
46,656-row augmented 系统。

### 14.1 改动文件与目的

| 文件 | 改动目的 |
|---|---|
| `src/solvers/hybrid_trace_chain.py` | 新增 `build_explicit_trace_matrix`；按 plane 内小 column block 物化唯一 cell/endpoint Schur 与 transfer，插入 trace-only AIJ；记录 rows、stored/allocated NNZ、matrix type、局部 dense block 体积及 `global_dense_formed=false`。 |
| `src/test/test_214_task036_one_cell_discrete_bloch.py` | 在已有复数非 Hermitian tiny chain 中验证显式 K 的 Mat.mult、线性/确定性、serial PREONLY+LU direct solve、端点 primal/dual 符号及 destroy。 |

生产 builder 不逐列调用完整 chain；它先分块物化一个 2,400×2,400 one-cell Schur 和两个
1,200×1,200 endpoint Schur，再按
`S_LL + J^H S_RR J`、`S_LR J`、`J^H S_RL` 及端点 `J^H S J` 插入 11 个 plane 的
三对角块。MPI communicator 使用每个 owned row 的实际三平面 column 支撑计算
`d_nnz/o_nnz` 数组；serial tiny 使用 `COMM_SELF` 和等价三带预分配。

### 14.2 已证结果

资格化环境下：

```text
targeted test214: 12 passed
Ruff: pass
compileall: pass
git diff --check: pass
```

tiny AIJ 记录为 22 rows、124 stored NNZ、matrix type `seqaij`，没有形成 global dense
matrix。`K_explicit @ probe` 与原 matrix-free chain action 的误差限为 `1e-11`；随后用
serial PETSc PREONLY+LU 解 `Kx=rhs` 并与 tiny probe 对照。端点块沿用现有 primal/dual
transfer，tiny action identity 同时覆盖 bottom/top raw-outward 符号。

### 14.3 A004 预估与未证边界

对正式 p5 trace（`p=1200`），11 个对角块、10 个上带块和 10 个下带块给出最多
`31×1200² = 44,640,000` stored complex entries；这是三带 block pattern 的上界，
实际 stored NNZ 需在 assemble-only preflight 后读取。按 complex128 16 bytes、PETSc
int32 column index 4 bytes 和 row pointer 4 bytes 粗估，数值与索引合计约
`892.9 MB`（约 `852 MiB`），还未计 AIJ allocator、MPI off-process buffers 和运行时
其他对象；因此这只是内存风险上界，不是实测峰值。builder 的
`local_dense_block_volume_complex_entries` 明确表示每个 rank 单个 replicated dense
block 的 complex-entry 数，不是 bytes、owned-local 总峰值或进程树峰值。没有形成
13,200² dense array。

当前 assemble-time 实现按 `2400 + 1200 + 1200 = 4800` 个局部 Schur scalar columns
分块物化；这意味着约 4800 次潜在 factor solve，暂记为 assemble-time 性能/生命周期
风险。后续 direct runner 必须在 local Schur 物化后按顺序释放对应 factor，并避免与旧
coarse/overlap factors 同时驻留；本轮没有伪造计时或声称该风险已解决。

尚未证实：MPI8 实际 ownership 下的 assembled NNZ/峰值内存、AIJ assembly wall time、
MUMPS symbolic/numeric factor、direct solve residual，以及与 Full3D direct observable
的同输入比较。后续必须先做 assemble-only preflight，再决定是否进行 numeric factor；
本轮不改 runner，也不启动小掠射角/P 偏振扫描。

## 15. Direct-D1a local materialization timing probe

本轮只在现有 runner 中加入 `--live-d1a-materialization-timing` 入口，目的是在决定
Direct-D0 是否适合进入 MPI8 direct 之前，测量三个已经完成局部因子化的 action。它只对
one-cell 2400 行、bottom 1200 行和 top 1200 行各执行一次真实的 16 列 identity slice，
记录 MPI 最大段耗时及 `segment_wall/16` 平均列耗时，然后按列数作线性外推到
2400+1200+1200=4800 个 scalar columns。
不会构造 13200 行 AIJ，不运行 internal discrete-Bloch QEP/modes、coarse/overlap/FGMRES/
Q5/C2；端部 external Fourier-DtN modes 仍按定义组装，也不做 global MUMPS factor；函数
返回后按 action、condensed objects、systems 的顺序清理。

D1a 的 RSS 字段明确采用 Linux `resource.getrusage(RUSAGE_SELF).ru_maxrss`，收集
`per_rank_process_lifetime_peak_rss_kib`；`not_simultaneous=true`，不求和、不做 start/end
差分。当前 runner 没有可直接复用的 process-tree 瞬时 watchdog，因此 process-tree RSS 标为
`unavailable`，不把累计对象体积当作峰值。局部 factor identity 必须是
`KSP=preonly`、`PC=lu`、`factor_solver_type=mumps`。endpoint assembly 需要外部 Fourier-DtN
modes，故记录 `internal_discrete_bloch_qep=not_run`、`external_dtn_modes=assembled_required`；
`full_forward_rhs_solve=not_run`。线性外推值不代表实测总耗时：若估计值不超过20分钟，才保留
scalar materialization 路线；若超过20分钟，下一步改用现有 `KSP.matSolve` 多右端接口，禁止先
做完整 assemble-only。该入口已完成静态实现；D1a MPI8 timing 已实际运行一次，结果见下文，D1b assemble-only 仍未资格化。

MPI8 D1a timing 已于唯一一次运行中完成：one-cell/bottom/top 的 MPI.MAX 段耗时分别为
`0.1016565150 s`、`0.2313270250 s`、`0.2299898160 s`，4800 列线性外推为
`49.8472403247 s`，低于 `1200 s`（20 分钟）阈值。三段 factor identity 均为
`KSP=preonly`、`PC=lu`、`factor_solver_type=mumps`。每 rank 的
`RUSAGE_SELF.ru_maxrss` lifetime peak（非同时值、不求和）已记录；起始约
`203508--205780 KiB`，结束约 `642104--676872 KiB`。process-tree RSS unavailable，临时目录
和8-rank进程均已清理。原始日志为
`/tmp/task036_direct_d1a_materialization_timing_v1.log`，SHA256 为
`b9b1ac57fe2bfddb6cd5ebe659c7fe6bc143ef8108b964fdf6d8edf2cd43e2d2`。

## 16. Direct-D1b assemble-only 实测

D1b 复用 D1a 局部 setup 和 MPI-safe catalog，构造 13,200-row trace-only AIJ，并用同一
distributed input ownership layout 分别写 chain/AIJ output Vec 做 Kx 检查。数值/矩阵子 Gate
通过：MPI8、rows=`13200`、stored/allocated/global-used/global-allocated NNZ 均为
`44,640,000`、matrix=`mpiaij`、GLOBAL_SUM `mallocs=0`、`global_dense_formed=false`，
`Kx` relative error=`1.3795077434522408e-14`。local setup、AIJ assembly、Kx wall 分别为
`73.36240866599837 s`、`108.13421355801984 s`、`0.02407568698981777 s`。

整体仍为 `unqualified_development_probe`：watchdog rc=`2`，唯一失败是自然收尾时一次
`process_tree_status` unreadable；`watchdog_checks_satisfied=false`。观察到的
process-tree peak 为 `8041168896` bytes（约 `7.489 GiB`），swap=`0`，低于 development
cap=`9631464161` bytes（8.97 GiB）。运行前 ABI 探针脚本自身 SyntaxError，且 shell 未因该
错误停止，故不能倒写成运行前 ABI 通过；运行后正确 MPI8 ABI postcheck 为 8/8 通过，日志
SHA256=`538aac6bdbc807f058c6f6b4ba57f6d9a26ae4bf3d3dbb91306ebaa86d5cb89d`。

三个 D1b artifact SHA256 为：

| artifact | SHA256 |
|---|---|
| `d1b_run.log` | `4c0106f97a088505e0443e6d8f8629b9b83c09584781e0e7d79702155f5c6e4a` |
| `watchdog_raw.jsonl` | `48fd9d02f937f3bfe81f8beff997ec72c9f26068b0ad8c6b15e0443a916edac3` |
| `watchdog_summary.json` | `4b39e1553ac0f08a231c0f53828acac1427975bf3f368cb959673d1eabd44c61` |

运行前后 HEAD、完整 porcelain、tracked diff SHA，以及三个 untracked source SHA 均一致；
tracked diff SHA=`7d01546bdd3f17eb3cb52b6dce3185125bf3ab5c13058d85ef03dbd29f64cac5`，
runner=`4d985ac67d7a3e4a97ac4e7935134e0ec63d56a754232a68ed06bbdade4a97a0`，
`hybrid_port_metric.py`=`eb5893da02fbe91efe1e8a257ba6f7ea48219f79a11c1df6225d47fab2b77ae7`，
`hybrid_trace_chain.py`=`941cfa71513ccab3582f6bf20b6a152bacf76a10d2f0dcaa47aef9be91ce9285`。
运行后无残留 MPI/Python/task036 进程和 `task036-d1b-*` 临时目录。global factor/solve
仍为 `not_run`。

## 17. Hybrid 修复累计状态

| 阶段 | 当前结论 | 证据与边界 |
|---|---|---|
| Exact-Cauchy | historical checkpoint | 选定 M120 空间内 operator 通过；端部 joint-Cauchy 不完整，旧 checkpoint 结论不代表当前 direct 状态。 |
| Q5 | negative / tail-not-reached | 冻结方法与 rank≤240 容量下 tail Gate 未达到，因此停止当前 transfer-optimal enrichment；不代表所有更高秩或 exact FE trace 不可行。 |
| C2 | exact physical decomposition proven | 11-plane exact FE trace 拆分/恢复对 frozen Full3D 的 96 channels、R/T/A_volume 已闭合；true residual=`9.94745e-11`，ΔR=`3.18e-13`、ΔT=`7.56e-14`、ΔA_volume=`2.40e-12`。全局 trace solve 是 FGMRES，transfer chain 为 serial 对 MPI8 oracle，不是最终 direct-vs-direct。 |
| D0 | trace-only explicit builder proven on tiny | 13200-row AIJ 结构与小型复数 oracle 通过；未做 global numeric factor/solve。 |
| D1a | measured timing pass | 4800 scalar materialization 线性外推约 49.8472 s，保留 batched/local materialization 路线。 |
| D1b | numerical pass, resource unqualified | MPI8 formal-size AIJ/Kx 子 Gate 通过；watchdog natural-exit race 导致 rc2，故整体仍 fail-closed/unqualified。 |
| D1c | not_run | 尚未进入下一 direct 生命周期阶段。 |
| Direct-vs-Full3D | not_proven | 尚无同输入 direct-vs-direct observable 对照。 |

通俗地说，当前路线没有修好旧的“用 M120 截断模态代表整个接口”的 Hybrid；那条路线在
Q5 已显示低秩不足。现在采用的是 Hybrid 域分解，但把有损的 M120 接口替换成完整的
1200 维 FE trace，并逐 cell 做精确 Schur 凝聚。这样更可能与 Full3D 的接口物理等价，代价
是需要处理一个 13,200 阶的 trace direct 系统；目前只完成 explicit assembly/Kx，尚未做该
系统的 global factor/solve。

### 17.1 当前变更规模快照

现场按 13 个相关文件重新统计，未包含其他历史工作树修改：

| 类别 | 文件数 | 精确变更 |
|---|---:|---:|
| 核心数值 | 5 | `+1684/-2`（含 `hybrid_port_metric.py` 300 行、`hybrid_trace_chain.py` 729 行） |
| runner/watchdog/helper | 3 | `+6497/-30`（watchdog 146/30、capacity 19/0、综合 runner 约 6332 行） |
| tests | 4 | `+936/-172` |
| docs | 1 | `+162/-1`，以本节更新后的 `response_v5.md` 为唯一文档 |
| 合计 | 13 | `+9279/-205`（含 3 个 untracked source 的完整新增内容） |

综合 runner 当前约 6332 行；立即冻结 Q5/容量、迭代法和新框架扩展，不在下一 anchor 前
重构 runner。当前总状态是：`exact physical decomposition=C2 proven`；`formal-size
explicit K assembly/Kx=D1b numerical pass`；`D1b resource qualification=fail-closed/
unqualified`；`Hybrid global direct factor/solve=not_run`；`Hybrid direct vs Full3D
direct=not_proven`。下一步唯一为 D1c，不预写其通过或性能结论。

## 18. 当前最终结论：H5-M1 同源码 direct Hybrid 闭环

本节覆盖第 1--17 节之后的最终状态。旧节仍是不可删除的历史证据；它们中的
`production qualification=fail`、D1b controlled stop 和 `direct_vs_full3d=not_proven`
分别属于当时的阶段边界，不应覆盖本节已经完成的 direct 结果。

### 18.1 任务边界、根因和最小修复

用户要求的是：在同一离散下，让 direct Hybrid 完整还原 direct Full3D，重点覆盖小掠射角和
P 偏振，并且 Hybrid 的 external wall 与 simultaneous process-tree peak 都严格低于 Full3D。
未经用户许可，不开发或运行 iterative/Krylov/FGMRES/PC。

旧根因不是“少做了几层防御检查”，而是 M120/M240 截断接口空间本身不完整：它不能携带端面
完整的电场/磁场联合信息，所以即使内部 residual 很小，也不能恢复完整端面 observable。

最小修复是把有损的截断接口替换为完整 1200 维 FE trace，在 11 个 plane、10 个 cell 上做
精确 Schur chain；MPI8 固定分成 bottom/top 两个 MPI4 endpoint 组并行，每侧只做一次
1200-column materialization；RHS 和 recovery 先在本侧完成，再只分享 canonical vectors 和
小型 payload；world 端用 recursive block direct LU 完成 trace solve。Hybrid 的 global
13200-row MUMPS factor/solve、Krylov/FGMRES/PC 均 `not_run`，没有 fallback、retry 或新
framework。

### 18.2 历史同 source 对照：M120/M240 为什么不是修复

以下数据绑定旧 source `2b56c68cae38b92c803c08c2fd28379a8af7f166`、A007-P、p5/h10、
theta=89.5、phi=90、P、MPI8。旧 wall/peak 只作历史记录：CPU affinity 与 Full3D
watchdog/Hybrid sampler 口径不同，不与 H5-M1 的百分比混算。

| 路径 | channels | max amplitude / key | max power | R | T | A_volume | closure | residual | external | peak | swap |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full3D direct | 80/80 | reference | -- | .6258391432044085 | .006252192503172068 | .36790866429300856 | `+5.890843369e-13` | `4.249455581e-13` | 530.001293 s | 10.2302475 GiB | 0 |
| M120 direct | 51/80, 29 fail | `7.655261787e-6` @ top(0,0)p | `1.676354229e-6` | .6258408209376 | .00625173075651 | .3678936467230 | `-1.380158284e-5` | `2.229013066e-12` | 338.197927 s | 5.566818 GiB | 0 |
| M240 direct | 52/80, 28 fail | `7.641402106e-6` @ top(0,0)p | `1.667404507e-6` | .6258408119795 | .006251731296567 | .3678936714706 | `-1.378525335e-5` | `2.451693233e-12` | 683.927168 s | 7.496483 GiB | 0 |

### 18.3 当前同源码 A007-P final-source anchor

H5-K1/H5-M1 运行时 source identity 的 normalized canonical 是
`ce88c5ec4da54bb05a5cc5bfc8b16f02f13ac4807d6b2280f76e0c9155688ac7`。

| 指标 | Full3D H5-M1 direct preonly/LU/MUMPS | Corrected Hybrid H5-K1 paired MPI4 + recursive block LU |
|---|---:|---:|
| channels | 80/80 | 80/80 |
| full true residual | `4.816720870e-13` | `7.443523829e-14` |
| direct projection | 80/80, max `5.498892155e-12` | 80/80, max `4.353000492e-12` |
| R | `.62583914320438716` | `.62583914320430711` |
| T | `.006252192503172611` | `.006252192503165086` |
| A_volume | `.36790866429305147` | `.36790866429248181` |
| closure | `6.112887974e-13` | `-4.596323322e-14` |
| external wall | `134.523771716 s` | `125.002722556 s` |
| process-tree peak | `10091102208 B = 9.398071289 GiB` | `8272744448 B = 7.704593658 GiB` |
| swap | 0 | 0 |

按完整 key-set 对照，当前 Full3D 与 corrected Hybrid 的最大 official
`outgoing_amplitude_at_boundary` 差为 `4.0085009737419503e-13`，key 为 `top,(0,0),p`；
最大 per-key power delta（亦为零级反射的 `dR`）为 `8.004708008e-14`，`dT=`
`7.525230439e-15`，`dA_volume=` `5.696554339e-13`。另有 current Full3D 与旧 Full3D
重跑的最大差 `2.760668393e-14`；那是 Full3D 重复性，不是 Hybrid 误差。

Hybrid 比同 manifest Full3D 快 `9.521049160 s`（`7.077596%`），峰值少
`1818357760 B = 1.693477631 GiB`（`18.019417%`）。

### 18.4 五点 grazing/P direct 扫描

以下四案对各自冻结 Full3D reference；A007 使用 18.3 的同源码 Full3D。五案均为
comparator `failures=[]`。

| case | theta / phi | channels | residual | max amplitude | projection max | dR / dT / dA_volume | closure |
|---|---|---:|---:|---:|---:|---:|---:|
| A002-P | 89.5 / 15 | 92/92 | `3.974e-13` | `3.780e-12` | `5.293e-12` | `5.498e-12 / 3.773e-15 / 4.711e-13` | `5.479e-12` |
| A003-P | 89.5 / 30 | 80/80 | `3.625e-13` | `3.381e-12` | `1.896e-11` | `5.257e-12 / 1.009e-14 / 2.224e-13` | `-3.870e-12` |
| A007-P | 89.5 / 90 | 80/80 | `7.444e-14` | `4.008500974e-13` | `4.353e-12` | `8.004708008e-14 / 7.525230439e-15 / 5.696554339e-13` | `-4.596e-14` |
| A008-P | 89.0 / 0 | 80/80 | `5.087e-14` | `8.673e-13` | `6.923e-12` | `9.594e-13 / 3.957e-14 / 1.302e-12` | `1.025e-12` |
| A046-P | 80.0 / 45 | 88/88 | `6.832e-13` | `4.599e-13` | `6.776e-13` | `1.527e-14 / 3.929e-13 / 7.044e-14` | `-6.588e-13` |

H5-L1 是一次监督命令错误：四个作业误带旧 flag，随后受控停止，保留为无数值结论的
invalid launch。H5-L2 只使用 paired flag，一次完成四案；A007 已由 H5-K1 独占完成。A007
行使用最终 current Full3D 与 corrected Hybrid 的 official boundary-plane 对照；旧冻结
reference 对照的 `3.7898e-13` 仅保留为历史边界，不作为同源码主行。

### 18.5 验证、证据和边界

- qualified PETSc `complex128/int32`；serial test214 `13 passed / 1 skipped`；MPI8 seam
  targeted test 各 rank 通过；compileall、Ruff、diff-check 通过。没有运行 full repository
  suite，也没有 CI 声明。
- paired 修复后没有继续修改生产源码；最后生产补丁约 `+350` 行，未增加 retry、fallback、
  scheduler 或 iterative 路径。综合 runner 约 6315 行是研究过程累积，不应伪装成精简
  production；后续 selective merge 仍需区分 production core 与 research runner，本轮不重构。
- HEAD=`e7208c6c28a42885f4a42ea1ca63cf3a7a3a8033`，两次数值运行时 tracked diff SHA=
  `06667cc915e3768647ff2d513db505fb88b2ce9796d00090a8f253ed6d9a50e6`；数值运行后仅
  `response_v5.md` 做了 doc-only closeout，因此当前 full-worktree diff 已有意不同；文档自身属于该哈希输入，故不在文档内嵌自引用 current SHA。
  数值源码/测试未改，无需重跑 PDE；工作树是 dirty development。因此结论是“同源码开发态数值/资源闭环 pass”，不是 clean-commit、CI 或已合并 production
  qualification。

整个 dirty research worktree 的最终 17 文件变更规模快照如下；第 17.1 节的数字是早期
历史快照，本表是当前最终口径。它不是最后 paired 根因修复的单独增量；该增量约为
`+350` production lines：

| 类别 | 文件数 | 精确变更 |
|---|---:|---:|
| core numerical | 7 | `+1821/-73` |
| runner/watchdog/helper | 4 | `+6542/-32` |
| tests | 5 | `+1275/-175` |
| docs | 1 | `+304/-1` |
| total | 17 | `+9942/-281` |

Evidence index：

| evidence | relative path | SHA256 |
|---|---|---|
| H5-K1 result | `benchmarks/artifacts/task036/direct_d2/a007-p/d2_result_full_v1.json` | `35127710d7216396f524c2e6c931e0110307d2f5f9517c4b66e55220059291d1` |
| H5-K1 trace | `benchmarks/artifacts/task036/direct_d2/a007-p/trace_solution_full_v1.npz` | `7c92e821c9748c82dbe81e333fc70a0c8a9a35c64ec9453d3447b605f28af57e` |
| H5-K1 recovery | `benchmarks/artifacts/task036/direct_d2/a007-p/recovery_observables_full_v1.npz` | `86ce27cd7a94d7841975616fcd38662e6149e01e611700d3c5149abe4cc49f1a` |
| H5-K1 log | `benchmarks/artifacts/task036/direct_d2/a007-p/d2_full_run_h5k1_paired_v1.log` | `653bb286548b9bfca8fb869451f8788c57f3b19e211ecce58834627fe0480227` |
| H5-M1 Full3D result | `benchmarks/artifacts/task036/full3d_same_source_a007_h5m1_v1/full3d_result.json` | `361a2ab2fe91eda8bdeebc2d8b0df00975ff5c9a15ba6ba626042bbb27e18eda` |
| H5-M1 Full3D log | `benchmarks/artifacts/task036/full3d_same_source_a007_h5m1_v1/full3d_run_h5m1_v1.log` | `96df8b5da175b290b36ddea7ff93674b1c3b5eb08812ea86f58c1cbdab458307` |
| H5-M1 watchdog raw | `benchmarks/artifacts/task036/direct_d1b/h5m1_full3d_a007_v1/a007-p/watchdog_raw.jsonl` | `1ce38caf2bbbacdb87ae6fd4032b1d330eac66bd8e4042c22b7b38ff7bfb8fb6` |
| H5-M1 watchdog summary | `benchmarks/artifacts/task036/direct_d1b/h5m1_full3d_a007_v1/a007-p/watchdog_summary.json` | `a74b27ee289f0687c5d2235b6f032a1de3f4ad5a3bc0046cf4c92dbebfe61644` |
| corrected manifest audit | `benchmarks/artifacts/task036/full3d_same_source_a007_h5m1_v1/source_manifest_canonical_audit.json` | `997cf85a3e56832b70bc55aa232d7e1b9f239c187c97687d6cd3565661eb98eb` |

Manifest carrier口径明确为：M1 JSON before/after raw file SHA=`5686de6931064647199f386baf60d65f76e8ba26e3db1ca3139fcd77bf9c4b3a`；
K1 TXT raw file SHA=`e4a2c87e4a53358e450a1b95ca817e432feb55e7baec09a95e0384d8cedc3fcc`；两种载体
解析后的 normalized semantic canonical=`ce88c5ec4da54bb05a5cc5bfc8b16f02f13ac4807d6b2280f76e0c9155688ac7`，且
parsed identities 相等。raw carrier SHA、normalized semantic SHA 和重建文本 SHA 不混称。

### 18.6 最终状态矩阵

| Gate | 当前状态 |
|---|---|
| direct Hybrid ↔ Full3D complete observable equivalence | pass |
| grazing/P five-point scan | 5/5 pass |
| Hybrid external wall lower | pass |
| Hybrid simultaneous process-tree peak lower | pass |
| swap | 0 |
| iterative/Krylov/FGMRES/PC | not developed / not run |
| ordinary default | unchanged |
| clean-source formal qualification | not_run |
