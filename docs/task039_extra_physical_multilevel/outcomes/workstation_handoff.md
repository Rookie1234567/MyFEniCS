# Task39extra 工作站移交边界：V10 macro inverse M1 资源阻断

V10 没有形成可移交的 workstation solver 资格。局部块的部分回代证据保留为研究材料；保守 allocated resident policy 在 block 7 超过 2 GiB 后停止，未进入外层、restart 或 official output。

| 项目 | 当前结论 | 口径/边界 |
|---|---|---|
| 身份 | source `b0df7457c0c4b33c66abda16862926da3426bb7d`；13.5 nm、p6/h10、Full3D、MPI1、80 modes（冻结输入合同，不是完整新 macro identity 证明）；input/physical hash 见 [V10 compact](records/physical_macro_inverse_v10.json) | final local source state；远端 push 认证仍待用户配置 |
| M1 local quality | block 0–6 persisted 14 backsolves，最大相对残差 `2.0002787934351233e-15`；6 native witnesses 最大 `8.243915633632588e-16` | `PARTIAL_PASS`；block 7 backsolve residuals 未持久化；不等于 cached/native A4 或 p4 true error |
| partial stage observables | blocks 0–7 symbolic=`0.13301346899970667 s`、numeric=`0.8125463649976155 s`、matrix NNZ=`5,379,856`、factor entries=`5,796,240` | raw stages sum；回代/缓存加载时钟=`UNKNOWN`，global coarse/Krylov/postprocess=`not_run` |
| M1 resource | policy value `2,243,365,908 B` > cap `2,147,483,648 B` by `95,882,260 B` | derived conservative allocated envelope；不是实测常驻或系统 OOM |
| 实测资源 | process-tree RSS peak `1,107,648,512 B`；job swap peak `0 B`；descendants cleared | measured；系统资源 Gate 未触发 |
| M2/M3 | BAL_H/ONE_C、restart32/64、original、notch、recovery 均 `not_run` | M1 前置 Gate 未通过 |
| official fields | E/H、near-field、R/T/A、`A_volume`、重要衍射级均 `not_run` | 无 workstation capability claim |
| 总成本 | preparation=`1281.5 s`（截止 `2026-09-10T12:14:07.163Z`）+ 两次 M1 终态=`380.27739690501534 s`，已记录 charged=`1661.7773969050152 s`；nominal remaining=`3738.222603094985 s` | 12:14 之后 repair/测试/M4 文档未完整计入；complete total cost=`UNKNOWN` |
| 下一步 | 停止 V10 candidate；任何新局部逆或 workstation heavy case 需新 review、预算和 identity | 不调参、不扩 rank、不复用旧 g1 作本轮证据；唯一主要缺口是完整新局部逆未跨过 allocation 预审 |

证据入口：[V10 中心结果](physical_macro_inverse_v10.md)、[V10 compact](records/physical_macro_inverse_v10.json)、[selective merge manifest](selective_merge_manifest_v10.md)、[M1 ledger](../../../benchmarks/artifacts/task39extra/v10_m1/v10_m1_budget.json)。

---

# 历史：Task39extra 工作站移交边界：V9关闭等新工作量复用候选

本节是当前工作站边界。V9 L2 的较低 RSS 只属于第 38 个 PC 后 time-progress screen stop 的未完成 outer；它不是成功 PDE 的容量或 solver 资格证据。L1 只是一组有限控制，不能作为完整 outer 资格。

| 项目 | 当前结论 |
|---|---|
| V9 L2 | `TIME_PROGRESS_SCREEN_STOP` / `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`；PC38、full explicit residual `0.1292009191903606`，process-tree RSS 峰 `1426276352 B`，job swap peak=`0 B`、global pswpin/pswpout delta=`0/0`，后代清场 |
| V9 L1 | 12 个 sequence I4 + 4 个 control I4；全六行累计 RESET/CARRY=`96.98303711495828 / 112.19278895820025 s`；5 个有效 pair admission open，不是 outer solver pass |
| 内层证据 | 76 次 I4 全部完成 16 新 B4、B4=`1216`、`A4_matvec=1292`、`explicit_A4=168`；逐 I4 compact rows 仅含标量审阅字段 |
| V5 baseline | 原始 564 步成功 baseline 保留，可用于复现比较；不外推为 2 GB/0.7 nm 能力 |
| 未运行 | official E/H、R/T/A、`A_volume`、notch、recovery、5 nm、0.7 nm 和 workstation heavy case |
| 当前动作 | 无新的 workstation qualification；不重跑、不扩 rank、不换候选；等待集中 review |

证据入口：[V9 中心结果](equal_work_recycled_p4_v9.md)、[V9 compact](records/equal_work_recycled_p4_v9.json)、[V9 L2 stop record](../../../benchmarks/artifacts/task39extra/v9_l2_original_p6/55b7325cae8477ded7b04cfab42181f18e035a0f/v9_l2_screen_stop_record.json)。本节不构成 `master` merge approval；普通默认保持不变。

---

# Task39extra 工作站移交边界：V7 J5关闭两条 bounded 候选

本节是当前工作站边界；以下 V2 及更早内容是历史移交记录。V7 没有新的 workstation heavy 授权，也没有把未完成 PDE 的低 RSS 观测写成能力通过。

| 项目 | 当前结论 |
|---|---|
| V5 可复现基线 | 原始 564 步和唯一 notch 576 步保留为完整双模型成功 baseline；参考 workflow 的 448 页 global `pswpout` 归因仍为 `UNRESOLVED` |
| V6 | 递归 coarse route、G1/G2 保留未资格化负结果；真实难误差定位属于 `response_v6` 历史补充授权，不是本轮 V7 新结果；不重跑、不升 production default |
| V7 A | entity16 在 121 步、true residual `0.04256451212826674` 处中点失败；RSS `1449623552 B`，fields/RTA 未运行 |
| V7 B | projected seq2 在 88 步、true residual `0.06385558342151046` 处中点失败；RSS `1517813760 B`，fields/RTA 未运行 |
| 资源含义 | 两次 tree swap/global swap delta 均为零；低于 2 GB 仅是未完成 outer 的受控观测，不是成功 PDE |
| 资格边界 | A/B 两条冻结 bounded candidate 关闭；不作所有无 global p4 LU 方法的普遍不可能性结论 |
| 下一步 | 无新 heavy case；如需重开，必须重新冻结 source/input/ABI、资源口径和独立 physical output Gate |

方法解释、逐 8 步曲线、成本和 compact hash 见 [V7 中心结果](bounded_inexact_outer_v7.md)、[A compact](records/bounded_inexact_outer_a_original_v7.json)、[B finite compact](records/bounded_inexact_outer_b_controls_v7.json) 和 [B original compact](records/bounded_inexact_outer_b_original_v7.json)。

| 当前 selective merge 依赖组 | 边界 |
|---|---|
| production numerical/core | V7 不改变 ordinary default；bounded profiles 不能因 finite/control pass 升级为默认 |
| reusable runner/watchdog | 只审已有单 KSP、midpoint stop、资源采样和清场；本轮无新 runner code |
| checker/benchmark | finite `checker_recheck.json` 作为独立审计入口；保留 outer checker 原规则，不因 audit 计数差异改 production |
| compact evidence/docs | V7 center、response V8、summary/index/handoff 与两份 B compact 最后审阅 |
| research-only | entity16、projected seq2、252 patch construction 及 V6 recursive/C；保留 controlled negatives |
| do-not-merge | raw fields、matrix/factor、cache、timeline、checkpoint 大文件及 ignored scratch |

本表不是 merge approval；没有执行 `master` 合并。工作站 0.7 nm、2 TB、非可分结构和新的 heavy PDE 均为 `not_run`。

## 5 nm 短波预审清单（未授权）

如未来重新提出 5 nm heavy case，必须先完成以下轻量资格化；本轮没有获得短波 heavy 授权，也不能直接复用旧 mode/hash 放行。

| 预审项 | 必须重新确认的内容 |
|---|---|
| 材料 | 5 nm 对应频率下的材料色散、损耗和单位体系；不能把 13.5 nm 材料参数直接外推 |
| mode/hash | 重新生成并核验 mode manifest、physical-model hash、input hash 与 source identity；旧 hash 只能作历史参考 |
| 底层规模 | 重新估计/测量 S/p2、local inverse、DtN、矩阵/因子和同时存活对象的规模，不能只按当前 13.5 nm rows 外推 |
| 完整资源 | 先做完整 process-tree RSS、swap、MPI/线程和 cleanup 预审，并记录所有 inner/outer 成本；单组件低 RSS 不等于 full PDE 通过 |

在上述 material/mode/hash、底层规模、完整 RSS 和全部内层成本检查完成并获得新的明确授权前，5 nm 与 0.7 nm 仍保持 `not_run`。

---

# 历史：Task39extra 工作站移交边界：V2关闭

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |

本轮没有合格原始场，不具备工作站solver资格；global p4诊断factor和难误差消除效率仍是限制。0.7nm、2TB容量和任意非可分结构均未通过。停止的是这两个限定候选，不是数学不可能性结论；无后续已授权PDE。

| V2 selective merge依赖组 | 数值行为 / 依赖 / 测试与fresh evidence / 建议顺序 |
|---|---|
| production numerical/core | 不提升本轮profile或joint算法；原A6/A4保持，既有组件候选仍需独立review；ordinary默认不变 |
| reusable runner/watchdog | 新profile接线和应用PID停止复用597；依赖原launcher/worker；test365/366/368，fresh F3用户停止safe476与清场；双时钟及user-wrapper分类限制须保留，core后审 |
| checker/benchmark | 已有计数checker与只读raw审计，依赖逐PC/周期/资源/哈希；不重新实现solver；接线后审 |
| compact evidence/docs | F1速度不足、F3未收敛/用户停止、时钟差异、完整索引与Response V3；最后合入 |
| research-only | packed S6及joint MR3、dat/profile、p4全局诊断factor；joint改变PC数值组合，依赖H6/原MR/A6/P64/A4/MUMPS；F1/实现tiny通过但fresh F3残差未过；禁止生产默认 |
| do-not-merge | raw向量、checkpoint、matrix/factor、cache、timeline、私有audit与测试scratch，保持ignored |

仅为依赖组建议，未获master merge approval。证据见[中心报告](packed_and_joint_mr_v2.md)与[response_v3](../response_v3.md)。

## 历史V1/A5移交快照（不作为新增运行授权）


| Review v1 / R6 更新 | 当前边界 |
|---|---|
| R1 | 等价通过、性能不通过；74.87089344408014 s对22.021386729524238 s；不是S6数学或收敛失败 |
| R3 formal source | `cbf56e87e515ab0c3fc5756cb6cf52feb047f610`；原始p6/h10 MPI1 H6–p4–H6零初值 |
| 数值 / 资源 | solve7200.255611149943 s，last_safe576真残差0.0791360407785889；workflow7966.278611822054 s，RSS3352014848 B，swap0；动态cap与4GiB余量无违规 |
| 停止修复 | `597546311feea60d61acb2a9999b706dd895dcf0`未来LIGHT opt-in；23局部测试通过；没有R3重跑，没有补齐原worker终态 |
| 资格 | `LIGHT_PC_FASTER_BUT_NUMERICAL_UNQUALIFIED`作为解释，parent正式分类仍为`PERFORMANCE_CONTROLLED_STOP`；不满足reference-assisted PASS或生产资格 |
| 下一步 | 集中review；不运行R4/R5/第三PC，不延长预算；完整S6+contiguous packing重新资格化为not_run |

本轮减少了单次修正成本，但准确p4逆辅助下的外层收敛效率仍是主要blocker。p4全局诊断factor依赖未解除；非可分、独立同离散authority和0.7nm物理收敛未取得。下面历史A5表保留，其旧“下一review”由当前R6证据补充，不作为新运行授权。见 [成本与贡献](cost_and_contribution_v1.md) 和 [response_v2](../response_v2.md)。

| 项目 | 当前可交付内容 |
|---|---|
| 状态 | 本机真实性能 Gate 已发生，可以移交可复现代码和机制证据；不是可用 solver 资格移交 |
| 正式 source / 输入 | `54ab46cf4c8378a9b27650ca6963cadb34013a2f`；[原 A2R dat](../../../input/task39extra/original_13p5nm_p6h10_p4_reference.dat) |
| 事后计数修复 source | `adc448814c3022fdf6d1a688da69a28238e7db9c`；只修账本，不使旧数值 evidence 失效 |
| 本机限制 | 13.5 nm/1° 原 p6/h10 到 3600 s 仍未达 1e-6；非可分、h5、独立 direct、official 输出均未运行 |
| 结果入口 | [总结](summary.md)、[运行/源码/原始 hash 索引](records/run_index.json)、[测试](test_summary.md) |

准确的 p4 中间逆已经把单 PC 中位耗时降至约 20.61 s，但未使外层在冻结预算内成功；最后 160 步真残差为 0.18250767622880507。尚不能仅凭这一诊断区分中间空间表示、S6、MR 或外层重启对最终效率的贡献。下一 review 需选择具体比较，不能自动增加预算或换算法。

底层直接求解是把一个小问题整体分解后反复回代，当前便宜，但规模增长时会成为内存和串行瓶颈。当前 positive p1 为 1067 rows，p3 为 23073 rows；p1 的 4096 rows/512 MiB 合同仍有效。A2R p4 的 53164-row 增广分解是显式诊断，不能拿它绕过生产底层限制。h5 未运行，不宣称已知其可容纳。

| 工作站阶段（全部未授权启动） | 必须先解决的问题 |
|---|---|
| W0 | 用户实际迁移后确认可见 RAM、NUMA、MPI/线程和 complex ABI；最新 review 冻结输入/预算后核验 13.5 nm 原始与非可分问题，不能把当前未通过结果冒充通过 baseline |
| W1 | 5 nm 真实非可分材料和至少两个有意义离散；核验场、衍射级与体吸收，不混淆旧 10° 与本任务 1° |
| W2 | 用有界局部/分布式多层方法解除随 N 增长的 global direct 底层瓶颈；至少三个实测规模点校准容量与总工作 |
| W3 / W4 | 仅必要的 2 nm 或 1 nm 中间点，再到 0.7 nm 受控规模与目标尺寸；保留三维材料变化及矢量 Maxwell，不做准二维替代 |

2 TB 是规划机器级容量，实际预算需用真实 MemTotal 与有效余量重新冻结。任务建议线为 `min(0.80*effective_total, effective_available-reserve)`，并非实测承诺。以 10^9 个 complex128 未知量估算，FGMRES32 的约 65 个 V/Z 向量仅存储就约 1.04×10^12 B（1040 decimal GB），尚无 FE/PC/编译/后处理；这是 derived 模型，不是可运行证据。本机 restart32 不保证适用于工作站 0.7 nm。

容量链须分别校准材料、离散精度、外部通道、local inverse、global coarse、DtN、MPI 复制七类限制，统计同时存活的对象；不能把旧 256 GiB no-go 直接变成 2 TB no-go。

| selective merge 依赖组 | 内容 / 数值影响 / 证据 / 顺序 |
|---|---|
| production numerical/core 候选 | 已独立验证的可复用传递、S6 精确对角等组件；依赖既有 FE/MPC/setup，对角保持原积分及约束。三单元与 serial/MPI2 oracle 已绑定；仅组件候选，不含未资格化的主 profile，不提升生产默认 |
| reusable runner/watchdog | 既有 public launcher/worker 和同 parent 资源链；先依赖 core，再接显式 profile。正式证据为本次受控停止；保留 worker 正常完成缺口 |
| checker/benchmark | 原输出 checker + 最小计数重算；依赖逐次 raw；test356/359/360 19 passed。只影响未来计数，不改 solver |
| compact evidence/docs | 五中心文件、开发总账、hash-bound 索引；最后合入，保持旧负结果 |
| research-only | 未资格化的 A2 物理中间层/shifted-cycle，以及 A2R augmented p4 reference、各自显式 dat/profile 与 tests；依赖可复用传递、S6、original A4/carrier/MPC/MUMPS。A2R 163 RHS 通过但 outer 未过，两条候选均不得升级为 production default |
| do-not-merge | 大型 results、cache、矩阵/分解、checkpoint solution 和完整 timeline；保持 ignored，以 hash 定位 |

此表为审阅建议，未获 merge approval。下一动作是集中 review，非工作站 heavy 启动授权。

| R6 selective merge补充依赖组 | 行为 / 依赖 / 验证 / 顺序 |
|---|---|
| production numerical/core候选 | 可复用局部作用/packing与monitor组件；保持原A6，依赖FE/MPC；局部oracle与bitwise monitor测试支持；先审core，不把未资格化profile升为默认 |
| reusable runner/watchdog | LIGHT应用PID/start-ticks登记、一次安全停止请求、超时/资源整树硬停；依赖launcher/worker marker；真实MPI1五路径小fixture；在core之后审阅，fresh大PDE未运行 |
| checker/benchmark | PC成本与贡献审计、32步曲线、真实残差快照；依赖raw记录；不重算求解器，不伪造终态 |
| compact evidence/docs | 本轮hash-bound小JSON、成本文档、summary/response及总账；最后合入，保留A5与R1/R3负结果 |
| research-only | S6等价fast、H6–p4–H6及p4诊断factor；分别依赖原action、transfer、MR、MUMPS；fresh R1速度失败/R3性能停止，禁止生产默认 |
| do-not-merge | 私有完整audit、raw向量、factor、cache、timeline与测试scratch；保持ignored |
