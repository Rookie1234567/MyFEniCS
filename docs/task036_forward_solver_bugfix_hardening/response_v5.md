# Task036 Review V5 执行响应

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
actual_candidate = not_implemented / not_run
Hybrid production = fail
ordinary default = unchanged
```
