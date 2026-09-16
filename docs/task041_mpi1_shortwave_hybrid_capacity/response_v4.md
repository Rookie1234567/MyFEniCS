# Task041 Response V4：V3 执行结果与收口

## 0. 身份、范围与结论

| 项目 | 本轮事实 |
|---|---|
| 分支 | `codex/20260902-task41-mpi1-shortwave-hybrid-capacity` |
| 文档编辑前 HEAD / upstream | `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab` / 同一远端分支同 SHA |
| 工作树口径 | 编辑前 clean；当前仅七个 R4 文档/compact 文件待提交；最终文档 commit SHA 尚未产生 |
| Task base | `50897c0c62d1f35abed5b196ae17997b2e7521cc` |
| Review V3 reviewed HEAD | `74ea02308070ed047989d8997e2627cee79e35db` |
| Review V3 同步提交 | `90fab889d9d7fd8a2551b3cf6e6df7ea8bec5372` |
| R1 实现与原算法分侧 baseline source | `3ee452ac0adc0c3c88b9610b6446e93a3c02444a` |
| R2 optimized source / run HEAD | `376a6c2e6ff1d13b8c4f182dd97e5ee2629f85ab` |
| 本次正式文件 | 本文、[setup/recovery](outcomes/setup_recovery_v3.md)、[compact](outcomes/records/task041_setup_recovery_v3.json)、`outcomes/summary.md`、`outcomes/test_summary.md`、development progress、model registry |

V3 不是只读阶段：R1 实现了 sequential component 入口、生命周期证据和受监督边界；R2c 实现并验证了显式 profile 下的 A1 owner-row 批量路径与 A2 复数共轭临时量路径；R2 baseline 与 optimized 各完成一次分侧固定八项运行。R4a/R4b 只整理这些已关闭结果，没有新增计算。

最终状态是 `PAIRING_IDENTITY_UNPROVEN`。原算法分侧与优化分侧各自四项 bottom、四项 top 均有 `reason=2` 和显式 inner residual `<=0.01`；R2e 的独立 P/PH action/transfer relative 均为 `0`。但是两个 fresh run 的 `132300` 个凝聚行没有持久化、可跨运行验证的几何/拓扑/方向/MPC active-row key，因此不能把按数值位置计算出的差异称为数值 Gate failure，也不能称为等价通过。旧双侧构造的资源负证据仍然有效，所以本轮不宣称完整 consumer、双侧容量或 production approval。

## 1. 通俗说明与四个结果维度

这里的 sequential component 是先把 bottom 侧的一套 p4/迭代 KSP 组件建好，完成四个代表性响应后释放，再建 top 侧的一套组件完成另外四个响应。它测的是“同一时刻只驻留一套侧区求解器”的可能收益；它没有删掉全局物理 action、改变 RHS 或传播因子，也没有把完整双侧 consumer 变成分侧 consumer。A1 减少 P 阶段逐行 Python 分组的重复工作，A2 避免为 PH 每个单元形成整张共轭矩阵；两者都保持原检查与精度门。代价是本次 R2 只测了八项和分侧 setup，不能替代完整 1920 formal response、outer、recovery 或双侧内存包络。

| 维度 | baseline | optimized | 结论 |
|---|---:|---:|---|
| 数值/局部响应 | bottom 4 + top 4；baseline 最大 residual `0.00920818603450433 / 0.009453705395988539`（bottom/top） | `0.009208186034505206 / 0.009453705395970853` | 各自满足原 `<=0.01` 与 reason=2；跨 run 行身份未证实 |
| 时间/固定八项 | `1680.27495998214 s` | `1258.8479048048612 s` | ratio `0.7491916113647505`，减少 `25.0808388635%`；仅组件 apply |
| 时间/full service | `4015.539370124 s` | `3630.563676387 s` | 减少 `9.587147784%`；与组件 apply 不相加，也不把差额全归因 A1/A2 |
| 资源/full service RSS | `51975606272 B` | `51796770816 B` | 观测差 `178835456 B = 170.55078125 MiB`；不是双侧 capacity 资格 |
| 覆盖 | 两次各 8 manifests/64 shards | 同左 | response、lifecycle、finalizer 均有关闭证据；完整双侧和 formal output 未运行 |

`R2e` 的 `P=0`、`PH=0`（均为全局 relative）是独立 linear action/transfer 基本门，阈值为 `1e-11`；它不是跨 fresh run response 的行配对门。原 response inner residual 门是 `1e-2`，不是把近似 KSP response 差异另立为 `1e-11` 硬门。

## 2. 固定八项与逐项证据

以下字段来自 R2h v1 的两个 raw `rhs_audits_and_costs`，不是从摘要的 completed count 推断。`old/new elapsed` 是各次记录的逐 RHS elapsed；残差是原始 `relative_residual`，每项 reason 均为 `2`。

| ordinal | side | audit index → formal column | baseline s / iter / residual | optimized s / iter / residual |
|---:|---|---:|---:|---:|
| 0 | bottom | 227 → 207 | `102.12699768389575 / 17 / 0.008369286568899938` | `76.81722939712927 / 17 / 0.008369286568903086` |
| 1 | bottom | 35 → 15 | `293.41944872797467 / 49 / 0.008589298457437621` | `219.32229429786094 / 49 / 0.00858929845757816` |
| 2 | bottom | 691 → 671 | `101.76308298599906 / 17 / 0.00920818603450433` | `76.42636410496198 / 17 / 0.009208186034505206` |
| 3 | bottom | 513 → 493 | `293.2048611470964 / 49 / 0.00884167581120191` | `219.90457329410128 / 49 / 0.008841675811089952` |
| 4 | top | 330 → 310 | `102.67069668509066 / 17 / 0.009202848153148894` | `77.0530902640894 / 17 / 0.009202848153033096` |
| 5 | top | 32 → 12 | `342.3201059210114 / 57 / 0.009387047162049134` | `256.2623172069434 / 57 / 0.009387047163980188` |
| 6 | top | 686 → 666 | `101.88474587490782 / 17 / 0.009453705395988539` | `76.68501366884448 / 17 / 0.009453705395970853` |
| 7 | top | 513 → 493 | `342.8850209561642 / 57 / 0.009387047156741695` | `256.3770225709304 / 57 / 0.009387047157158403` |

两次运行各保存 8 个 response manifest 和 64 个 owned rank shard；每次 shard 总计 `33901312 B`。ownership range 只绑定各运行自己的代数编号，不能承担跨运行 physical-row identity。

## 3. 成本分解（同一 logging-rank/local 累计口径）

R2h v1 的 `timing_comparison.total.per_rank_seconds_sum` 是写日志 rank 的本地累计字典，不是八 rank 数组。下表只列不相加的诊断区间；PH 合计是两种 PH cell-adjoint 区间的派生和，不是另一个临界路径。完整 key、count delta 和逐八表在 compact 中保留。

| 诊断区间 | baseline s | optimized s | new/old |
|---|---:|---:|---:|
| Q/P overall | `395.87819189811125` | `68.96878564264625` | `0.17421718865584043` |
| P duplicate-row check | `333.5196231044829` | `7.7310076341964304` | `0.02318006827374745` |
| P local candidate generation | `43.247770307352766` | `36.482684139860794` | `0.843573758383058` |
| P route/sort/index | `3.2738890196196735` | `2.97846771357581` | `0.9097644103775447` |
| P MPI exchange | `1.7577059995383024` | `8.31076301052235` | `4.728187201218716` |
| PH overall | `103.06138404877856` | `46.72804473526776` | `0.45340012815228203` |
| PH cell-adjoint（Q） | `94.92420637980103` | `36.81349472259171` | `0.3878198841641859` |
| PH cell-adjoint（balance） | `94.46257099602371` | `36.69263332942501` | `0.388435683493831` |
| PH 两种 cell-adjoint 派生合计 | `189.38677737582475` | `73.50612805201672` | 仅派生，不作 wall |
| p4 MatSolve | `240.4323979311157` | `258.04327448271215` | `1.0732466868156512` |
| inclusive A4 residual/refinement | `142.9326381694991` | `143.64915666473098` | `1.0050129802710432` |
| `physical_action.matrix.mult` 子区间 | `141.9157515047118` | `141.58146657887846` | `0.997644483277778` |
| balance A6 | `558.5788922715001` | `557.1997007760219` | `0.997530892207778` |
| balance H6 | `117.1000568207819` | `116.50803733826615` | `0.9949443279654269` |

`A4 residual/refinement` 是包含 extract、Vec 分配、physical action、norm 和 audit 的 inclusive 区间；不能与其中的 `matrix.mult` 再相加。P/PH 的通信、ghost/MPC 准备、排序和分配子项，以及 baseline/optimized counts 相等关系，见 compact 的 `costs.rank0_local_comparison`。`max_rank` 与 logging-rank/local 累计不混用；嵌套字段不相加冒充 critical path。

## 4. 构造、释放和同钟资源窗口

两次 worker marker 都使用 `CLOCK_MONOTONIC`，各自 worker origin 与 outer origin 记录在 compact；时间换算为 `worker_origin + worker_wall - outer_workflow_origin`。marker 前后 RSS 是 outer 全树采样的括号，不是与 marker 同一时刻的精确读数。

| run / side | setup 到 admission | full action | p4 form / matrix / factor | transfer | H6 diagonal / window / runtime | adapter/KSP |
|---|---:|---:|---:|---:|---:|---:|
| baseline / bottom | `674.9525812410284 s` | `5.783504035091028` | `2.285461188061163 / 497.1479417809751 / 20.62342693703249` | `95.12804950098507` | `30.252654343144968 / 17.34580230806023 / 0.3657998079434037` | `0.03541205381043255` |
| baseline / top | `669.0089339439292 s` | `4.64580956613645` | `1.8881716069299728 / 496.03055016906 / 31.757921094074845` | `81.66835550614633` | `29.421431415947154 / 17.344329809071496 / 0.38362951995804906` | `0.036570446100085` |
| optimized / bottom | `660.0814286530949 s` | `5.616531522013247` | `2.2954767250921577 / 497.1506807389669 / 19.40718612796627` | `84.67073051794432` | `29.208217314910144 / 17.341203927993774 / 0.3821493780706078` | `0.03647093288600445` |
| optimized / top | `664.6973237530328 s` | `5.607726576039568` | `2.267146711004898 / 495.17534057307057 / 26.445405110018328` | `84.31237075896934` | `29.184690851019695 / 17.33350289496593 / 0.37744932994246483` | `0.03624332998879254` |

上述数值均来自 compact 的 side-specific marker interval；不是把 worker wall 写成 service full wall。marker 对应的 outer RSS 只作前后括号，不能当同刻峰值。全局 `system_ready` 的 worker wall 为 baseline `983.0788940798957 s`、optimized `1039.0930612850934 s`；它与侧区 `before_build→after_admission` 分开。两场的 `factor_setup_begin→factor_ready` 分别为 bottom baseline `983.5931301249657→1653.4143726038747`、optimized `1039.5970036741346→1696.573750832118`，top baseline `2450.2057411340065→3114.250514271902`、optimized `2293.303577498067→2954.8940188910346`。这些值直接由两份 consumer marker 按 `(side,event)` 配对，完整 raw line/hash 在 compact 的 `construction_timing`。

实际全 service outer RSS：baseline `13255` 行，峰 `51975606272 B`；optimized `11999` 行，峰 `51796770816 B`。对应硬 cap `53221163008 B`，baseline margin `1245556736 B`，optimized margin `1424392192 B`。两次峰都来自 full service process-tree RSS，峰值同一行 PID 求和闭合；PSS/USS 是 sparse diagnostics，不是 RSS 替代。baseline/optimized post-I/O 峰分别 `51879936/51171328 B`，不回填全程峰。两次 job swap、new global swap 和 pswp 增量为 `0`，global used 的既有 baseline 是 `8192 B`。未知 native workspace/allocator 保留 unknown；RSS 下降不能单独称为 leak 修复或完整内存节省。

## 5. S0 归因与预测边界

S0 统计入口是 `s0_rhs_statistics_v2.json`（18352 B，SHA `36781c22a3565d70ed37364c94a0c2ec104b12279bbad0a8f27c06f2ef8917cf`）。它包含两侧 formal 960、sample 32、cost 8、outer 20 的计数与按阶段的 wall、median/p90/max、Q/H6/A6 及 uncovered；这些是逐 RHS/分项的 logging-rank max 或 local 累计诊断，不能当父 wall 相加。S0 与 R2h v1/v2 的原路径/hash 均在 compact。

旧 v1 的 `302123.4971531667 s = fixed-eight mean × 1920` 只作为未加权示例，已废止。现在可以使用旧类别权重、新八项实测比例和明确的误差界限做条件预测，但当前 `180784.16322105168 s`（formal主体 no-change 情景）与 `135444.80448636482 s`（固定八项比例缩放情景）都不是新实测 consumer 总 wall 或容量依据。还缺更可靠的类别外推假设/界限、稳定 row identity、完整双侧 admission/capacity 和同合同的 full-consumer 边界；不需要为了“能作预测”循环重跑全部 1920 行，但旧双侧超 cap 仍是实际 blocker。

## 6. 配对身份、配置与原始证据

配对正式状态是 `PAIRING_IDENTITY_UNPROVEN`。baseline/optimized 的 response manifest 只有 ordinal、side、formal column、packet/probe/source identity 与 ownership；没有每个 condensed row 的稳定几何/拓扑实体、局部方向/FE basis、MPC active-row 展开键。按各自 PETSc global index 直接拼接的约 `sqrt(2)` 差异保留为 `diagnostic_only_unverified_numbering`，不是 numerical failure 或 pass。hash 差异本身也只是 provenance。

两次 public root 都实际保存了 `resolved_config.json`。`consumer/consumer_summary.json` 的 `identity.physical_sha256` 均为 `65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4`；`identity.resolved_sha256` 均为 `95a155334dacf75d30c005338ff689fd676532b49ae392e6fad868d0eee23e51`。两份 `resolved_config.json` 均为 `116779 B`，各自文件 SHA 也实际为 `95a155334dacf75d30c005338ff689fd676532b49ae392e6fad868d0eee23e51`。compact 将逻辑 identity 字段与 resolved 配置文件 SHA 分开列出；这里恰好相等，不把两者混成同一语义。

compact 还绑定两个 service root、public root、launch/parent/service/finalizer/post 文件、RHS audit、8 manifests/64 shards 的计数和 hash、固定 input/packet/legacy descriptor、完整 public argv、MPI8×1/CPU0–7/数学线程1、profile、sequential schedule、配置/源 SHA、unit identity 与唯一 ledger。大 memory/marker/field/factor/shard 原始文件继续留在 ignored results，不复制进 Git；原 R2g index、R2h v1 和 R2h v2 均保留，两个摘要 SHA 的历史索引手误仍作为 correction 记录。

## 7. 旧负证据与未运行项

旧 S1f 已实测全树 RSS `53331742720 B > 53221163008 B`，fixed8=`0/8`，分类为 `process_tree_rss_limit` 的受控资源停止；它不能被本轮分侧峰值低于 cap 抵消。旧 H3 的 numerical PASS 与 `RESOURCE_COMPARISON_INCONCLUSIVE`、父/监控事故及其修复证据继续单列。本轮 R2 的正常 service/finalizer 关闭并不把分侧事实升级为双侧 full pass。

| 项目 | 本轮状态 |
|---|---|
| 13.5 nm 新运行 | `not_run` |
| 完整 5 nm 双侧 consumer | `not_run / not_qualified` |
| full Schur / outer / recovery / official RTA | `not_run` |
| producer | `not_run` |
| QEP | `qep_calls=0`，无新调用 |
| 分侧配对的第二场（唯一 optimized R2g） | 已完成并已纳入 R2 配对；额外/重复 optimized run 为 `not_run` |
| S2/S4 | 未启动，均为 `0` |

预算尚余不等于准入。未取得双侧构造峰、稳定 row identity 和完整合同边界前，不启动 13.5、完整 5 nm 或新的 optimized consumer。

## 8. 测试和选择性合入边界

R1/R2d/R2e 的实际命令、日志、SHA、测试计数和 source 绑定见 [test summary](outcomes/test_summary.md)；R1 的 137 passed 发生在后续机械 lint 修正之前，之后单独有最终受影响 9 passed，不能合并说成“最终 hash 上 137 passed”。R2d 的 pure 346、builder 349、profile 351 和 R2e 的 serial/MPI2 也分别计数；没有 CI/full-repository 声明。R4 文档阶段没有重跑这些已绑定测试或任何 heavy。

| 依赖组 | 本轮事实与边界 |
|---|---|
| production numerical/core | R2c A1/A2 是已审 research changes；ordinary/default 数值路径保持不变，未获 production promotion |
| reusable runner/watchdog | R1 service/supervisor 接口和生命周期证据保留；本轮没有新 watcher、接管器或调度框架 |
| checker/benchmark | fixed-eight checker、raw audit、manifest/shard/hash 和 R2h 离线配对证据保留；正式 row identity 仍未证实 |
| compact evidence/docs | 本文、setup/recovery、summary、test summary、progress、registry 与负结果证据应一并保留 |
| research-only | `task041_schur_speed_v2` sequential component 与 A1/A2 optimized profile 仍是显式 opt-in、未资格化研究路径 |
| do-not-merge | incident-specific orphan sampler、固定 PID 接管、大型 raw artifacts 和未资格化生产提升；负结果文档/compact 不是禁止提交项 |

最终结论：本轮保留了真实的分侧响应、局部成本和两次完整 service 观测，但跨运行 row identity 未证明、双侧构造仍受旧超 cap 证据约束。因此不宣称 `COMPONENT_EQUIVALENT_SPEEDUP_MEMORY_NONINCREASE`、precision failure、完整 consumer capacity 或 master approval。

<!-- r4b-final-metadata -->
最终 compact：[task041_setup_recovery_v3.json](outcomes/records/task041_setup_recovery_v3.json)，153382 B，SHA256 `7f5d84e6a2a9a6809d9438bbb6e9444a4ffead9d6272728b394d3346401852df`；唯一 V2 ledger 已记 shared=11145.609111173893325 s，remaining=10454.390888826106675 s，S2/S4=0。
