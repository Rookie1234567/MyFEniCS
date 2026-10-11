# Review V42：保留真实场改善，从同一完整状态续算，不让研究早停代替数值结论

## 0. 裁决、目标与身份

**接受 V42 的完整实施、独立验收和联合 FAIL；同时接受已经实际观察到的隐藏学习场改善。批准一次同算法、有上限的延续试验：从 V42 学习路线第4轮最终完整状态继续，并从完全相同的状态分叉一个停止隐藏学习的控制。不得再次从零训练、换网络、增加秩或重做容量证明。正式精度门不变。**

本轮消除的 blocker 是：有显著下降趋势的候选被预先设置的第4轮绝对/减半筛选截断，尚不知道该趋势能否在有限追加成本内转化为合格场。它属于**神经优化进展判别及执行连续性**，不是解决了原尺寸容量，也不是已经证明神经网络优于传统有限元。

```text
repository               = Rookie1234567/MyFEniCS
branch                   = task42extra_feinn_5nm
canonical_worktree       = /home/fenics/Projects/NN-Lab-V2
original_base_SHA        = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD     = 9ec83316492b25391fec50591b2721d4ac19b67a
result_commit_time       = 2026-10-10T19:13:33Z / 2026-10-11 03:13:33 +08:00
review_date              = 2026-10-11 Asia/Singapore
previous_review          = review_report_v41.md
reviewed_response        = response_v42.md
campaign                 = V43_BLOCH_FTT_TREND_CONTINUATION
required_response        = response_v43.md
new_total_window_s       = 28800
production_merge         = NOT_APPROVED
```

最终目标仍是原尺寸0.7 nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、复 E/H、完整衍射及独立体吸收；十进制2e12 B是整机内存，须留系统余量，ownswap/OOC=0，单场必要准备到验收不超过172800 s。当前本支没有承担该交付的合格方案。本批8 h是新增研究上限，不是目标48 h成绩。

本报告明确覆盖上一合同的第4轮停止、原6轮/18核访问/5400迭代上限和Response V42的自动关闭状态，**仅按本报告的新增额度及分流规则继续**。旧结果不改为PASS，不把研究续算许可当作原Gate通过。没有重新开启旧V42窗口；新旧费用分开且全部保留。重复收到本指令不重开V43。

本支仍只做神经研究；不恢复旧稠密波库、W0/W1、全口面、模式恢复、传统Maxwell PC、存储系统或主线接入，不修改或向Task42、主线、dot、master及其他工作树派活。

## 1. 仓库快照、证据与审阅范围

已回读分支、Response V42全文、summary当前段、核心/隐藏/轮次记录、内层CSV、完整Gate关键字段、停止策略与训练循环源码、根规则和仓库原则，并比较Review V41之后3次提交。原task、docs/目录AGENTS和历史执行补充的未变内容沿本会话既有原文衔接；目录已知正式补充不增加本轮预算。Review V41全文从本会话挂载原件读取，Git blob与远端4b892bcfa963203e4d4220f9ce81b083927f438f一致。未SSH、未检查工作站实时PID、未在本端重新运行M5或逐数组复算大型artifact。

主要依据：[Response V42](response_v42.md)、[summary](outcomes/summary.md)、[轮次与隐藏更新](outcomes/records/hidden_updates_and_rounds_v42.json)、[路线及最终状态](outcomes/records/conditional_core_routes_v42.json)、[逐核心内层](outcomes/records/conditional_inner_solver_v42.csv)、[独立全场Gate](outcomes/records/full_numerical_gates_v42.json)、[成本](outcomes/records/resource_costs_v42.json)、[研究分流源码](../../src/solvers/ftt_bloch_field.py)、[训练与恢复](../../src/solvers/ftt_core_training.py)。实际V42数值source为c1c82474d9a26675f1829db5a219efdc04a60f59；文档HEAD不是数值source。

| measured；M5/5nm/384hex/p3/N31968/40端口 | 学习隐藏NN | 初始隐藏冻结NN | Cheb控制 |
|---|---:|---:|---:|
| 完整轮次/核心访问 | 4/12 | 4/12 | 4/12 |
| LSMR迭代/隐藏调用 | 3358/53 | 3050/0 | 3600/0 |
| native及augmented相对残差 | 0.444550296118 | 0.743141789453 | 0.234159905921 |
| 散射E相对误差 | 0.132626683892 | 0.475004668693 | 0.990553945539 |
| 散射H/scaled-curl相对误差 | 0.132884263175 | 0.475418400627 | 0.990493647966 |
| 独立能量闭合误差 | 0.0338269975021 | 0.150558570472 | 0.410955650733 |
| 实际模型重建相对差 | 2.03083041062e-14 | 4.51077485441e-15 | 1.01413918605e-14 |
| 正式attempt秒 | 2920.6633467 | 2156.6865337 | 2893.55737274 |
| 同时自身树RSS采样峰/B | 910639104 | 832794624 | 825778176 |
| actual/producer联合Gate | FAIL/FAIL | FAIL/FAIL | FAIL/FAIL |

参数/相位、完整矩、MPC、端口恢复和求积均有合格配对；约13%的场误差不是writer未完成。相位NN相对同相位初始隐藏冻结控制的场改善应保留，但两者执行成本不同、且均未到同等合格精度，不能授20%资源收益。Cheb残差较小而场几乎全错，再次说明不能只看loss。

| 学习路线measured；轮数为一基 | 原残差 | 散射E | 散射H/curl |
|---|---:|---:|---:|
| 第1轮 | 0.745820871053 | NOT_RETAINED于轮次标量表 | NOT_RETAINED于轮次标量表 |
| 第2轮 | 0.741414507640 | 0.471857766118 | 0.472274564567 |
| 第3轮 | 0.673809674886 | NOT_RETAINED于轮次标量表 | NOT_RETAINED于轮次标量表 |
| 第4轮 | 0.444550296117 | 0.132626683892 | 0.132884263175 |

由上述原字段计算，2→4轮原残差下降40.04025%，E/H误差分别下降71.89266%/71.86292%；最后一轮原残差下降34.02435%。它不是平台期证据。旧规则要求第4轮三项均≤0.1，或残差相对第2轮至少减半且E/H≤0.2；第二项需要残差≤0.370707253820，实际0.444550296117，所以合法触发停止。

**Codex执行旧规则没有错；此前审阅设计把筛选做得过早。本次纠正的是未来的研究分流，而不是降低物理精度。** 同时不能把下降率外推成保证：当前E误差仍约为1e-4门的1326倍，原残差约为1e-6门的444550倍，距离联合PASS仍远。

9/12个学习核心求解达到300迭代上限，最大真伴随残差比约0.233；它们是验证过实际下降的有限增量，不是精确条件最优。这个未决项保留，但本轮不同时改变LSMR精度、做白化/预条件或扫更多迭代，以免失去可解释的延续对照。

## 2. 唯一起点与同状态消融

本次不是新表示，不是从零冷启动；两条路线都从V42 **LEARNED最终完整第4轮状态**开始。只取末态，不按准确场误差选择best或其他中期点。

```text
parent_record   = outcomes/records/conditional_core_routes_v42.json
parent_route    = BLOCH_FTTNN_CORE_LEARNED
checkpoint_name = committed_000023.pt
checkpoint_sha256 = 820482a3ff75c87203f301e628b5874be2e387b0627b8765a96e1a8ae6076c2f
checkpoint_bytes  = 1887719
parent_phase_sha256 = 32824e3063679681f77f6bb103fbb1ec9264f09f3441201407f6d0144cdc2ecc
parent_source_sha = c1c82474d9a26675f1829db5a219efdc04a60f59
```

真实路径从原run/index读取，不凭文件名猜路径。完整状态应含第4轮结束、下一轮第一个核心、全部权重/输出系数/phase buffers、c/r、RNG及累计记录。原始counts为12核心访问、3358迭代、53隐藏调用、4完整轮次；未保存内层工作为0。恢复后以原mapping和A重算c/r并与原保存数组≤1e-10配对；必要时有限查找本任务声明的hash副本，不全盘扫描，不重新训练四轮来补文件。

| 新路线 | 起点 | 第5轮以后 | 范围 |
|---|---|---|---|
| BLOCH_FTTNN_R4_LEARNED_CONTINUE | 同一parent | 核心更新+原隐藏学习 | 默认到总第8轮；趋势准入后至多总第12轮 |
| BLOCH_FTTNN_R4_FREEZE_ABLATION | 同一parent | 只更新核心输出；隐藏冻结在parent | 至多总第8轮 |

这个控制回答“已经学习四轮之后，再学习隐藏层是否仍有边际贡献”。它**不是从零从未学习的非神经基线**：两条均继承学习前缀，不能用新控制的名字抹去前缀。原V42冻结/Cheb结果保留作历史对照，本批不重跑它们，不因某条新路线失败再生成第三条候选。

## 3. 算法、物理和低存储边界均不改变

保持原M5、5nm、384hex/h1.25nm、p3/N31968/完整40端口、正式Si/air材料、背景、原A/f、体与DtN q15、网络完整矩q30及独立q60。保持TT秩(1,8,8,1)、9072实参数、两层sin核；隐藏可训练参数仍912。已知未折叠横向相位、物理nm坐标和原点不训练、不改：

```math
E_{\theta,s}^{\mathrm{scat}}(x,y,z)
=\exp\{i[k_x(x-x_c)+k_y(y-y_c)]\}F_{x,s}(x)F_{y,s}(y)F_{z,s}(z),\qquad
r=A I_h^{\mathrm{curl}}E_\theta-f.
```

H/curl从最终实际FE场恢复；保留所有边/面/内部矩、真实Piola/orientation、唯一owner及MPC一次展开。已合格FactoredMomentMap、相位增量和独立旧逐点路径复用，不再优化已足够快的内核。

每个活动核心仍按原实现求：

```math
B=A K/\|f\|_2,\qquad b=(f-Ac)/\|f\|_2,\qquad
\min_{\delta w}\|B\delta w-b\|_2.
```

LSMR仍damp=0、atol=btol=1e-8、conlim=1e12、每核maxiter=300、增量零初值。实际参数写回、完整c/r复算、线性配对≤1e-10和原loss不增才提交。原隐藏fresh L-BFGS的lr1/history10/strong-Wolfe/max_iter10/实际调用≤20均保留；只在LEARNED运行，仍是固定输出的普通隐藏梯度，不宣称精确VarPro。

从总第5轮z→x→y继续，第6轮反向，之后交替。不得把轮数归零而改变顺序；不得在旧末态上重复运行第4轮隐藏步骤。冻结控制的隐藏权重/偏置及全部phase buffers全程逐位不变。

禁止新rank/width/载波/衰减/seed/loss、监督fit/oracle、容量证明、新的核心预条件器或LSMR扫描；不允许全FE逆/Krylov完成器、global Maxwell/Gram factor/Gsolve、N×d列库、大J或A*A。小端口准确消元仍属于原A，成本照计。

## 4. 先处理真正的恢复和政策适配，不复制新训练器

复用当前runner与`run_core_training`，增加显式的parent-fork/continuation与execution_policy参数；原V41/V42默认行为不变。不要复制一份500行训练循环，也不重做调度或封存系统。

目前代码对input/design/route身份严格相等、空目录初值必须为零，并硬编码6轮/18访问/5400迭代和只在第2/4轮评分。因此不能把旧PT直接当作“同一次run恢复”，也不能改旧PT元数据或只加载权重归零计数。新分叉应：

1. 原件只读核验后，创建新的run manifest，显式保存`parent_checkpoint`和全部parent binding；新input/design/source/route独立绑定。继承权重、buffers、RNG、完整位置、round_start_native和历史计数，新增计数从0开始；来源转换记录允许差异白名单。
2. 将历史`ROUND4_FIELD_PROGRESS_NOT_QUALIFIED`保留于parent_result，只用新review授权新的停止政策，不删除旧validation=false，也不再次执行旧第4轮关卡。新状态从下一完整核心开始。
3. 两条新路线首次正式核心更新前，核对完整state/c/r逐位或规定数值配对；不得用参考或旧控制终态补齐。后续同V43恢复仍严格校验新binding，不借parent导入放宽一般恢复。
4. 原隐藏优化器每轮fresh；parent内已完成隐藏历史仅作为证据，不错误接成跨轮L-BFGS。LSMR内部态未保存，不能恢复半次bidiagonalization；中断费用和预留迭代仍按原保守规则入账。

新增最小测试覆盖：非零parent读入；错hash/错相位/监督parent拒绝；两分叉同c/r；从第5轮正确轴序；不重复第4轮；新旧/继承工作上限；冻结隐藏逐位保持；pending scalar恢复；旧政策默认不变；超时/保存失败/partial不当committed；用途字段贯穿writer→seal→reopen。真实parent仅做一次原c/r核验和必要非零作用短检查，不重跑旧相位全资格、准确参考或全部benchmark。

普通API/schema/缓存/目录/用途/角色错误在同批最小修复、受影响定向测试后继续，不按bug次数结束；健康产物只复用。不因为新版本编号误走已耗尽的旧观察池，数值续算、隔离FE评分、pure工具角色正确分派。

## 5. 新增轮数、趋势分流及正式数值门

### 5.1 有限延续，不再在仍有明显场改善时机械关停

两条都先执行总第5—8轮四个新增完整轮次；第6轮只记录规定标量，不因尚未到绝对精度或未减半而停止。原残差每轮仍审计。除真实安全/数据/非有限数/正确性失败或自身时间上限外，不用旧两轮慢降卡提前结束这一有限区间。

第8轮控制停止并完整验收。学习路线在第8轮决定是否准入第9—10轮，在第10轮决定是否准入第11—12轮。**总第12轮是本批绝对上限，不自动延长。** 每两个完整轮次由隔离checker返回R、散射E/H/curl相对误差及身份，不返回向量、分布图或方向。R取native/augmented较大者；各比率使用原完整范数分母。

记第j轮的散射误差为eE_j/eH_j，且q_j=max(eE_j,eH_j,eCurl_j)。准入下两个轮次只需以下之一，但要求全部数值有限非负、身份与正确性合格：

- 最近两轮R、eE、eH都至少下降10%，即相应当前/前次比值均≤0.9；不另外要求先降到0.1或残差必须减半。
- 已进入数值精修区：R≤1e-5且q≤1e-3，三个指标相对上次均不恶化超过5%，并且R至少下降1%，或E/H都至少下降1%。这是有限精修准入，不是正式PASS。

其余情况以`NO_CONTINUED_JOINT_PROGRESS`结束该候选并验收，不自动换方法或扩大参数。R/e分母为0时不做除法：立即触发完整Gate或按另一非零指标判定，不能产生NaN或人为floor扭曲结论。

第一次native/augmented均≤1e-8的完整参数边界立即做联合验收；如场门未到但正确性成立，只允许同算法在原剩余额度内以原残差目标1e-10继续一次，不根据参考误差向量改方向，不循环重复同一验收。保存实际终态及规定第6/8/10/12轮，不按参考误差挑best替换最终成绩。

本政策在新计算前冻结，以后不得根据看到的曲线改10%/1%数字。它是资源分配策略，不是数学收敛定理。V42已有轨迹作为回归fixture，应保留旧政策false，并证明新趋势规则会允许这类共同下降；也覆盖只降loss但场变差、仅场改善而R平台、数字非有限等负控。

### 5.2 真正的联合Gate不降低

| 完整实际网络和producer分别验收 | 阈值 |
|---|---:|
| native、augmented、独立total原方程相对残差 | 各≤1e-6 |
| total/scattered E/H/curl、六点复场、四类完整40复通道向量误差 | 各≤1e-4 |
| R/T/A/A_volume差、独立体吸收一致性、独立能量闭合 | ≤1e-5 |
| 逐衍射级功率绝对差 | ≤1e-6 |
| 实际网络完整矩重建、MPC、端口恢复 | ≤1e-10 |
| 网络q30/q60系数及原作用、FE独立求积配对 | ≤1e-8 |

独立路径仍为未改FTT点值再显式乘chi，经旧完整矩q30/q60；FE compare-only只读原V1同p3参考，SHA256为0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7。无需重新求MUMPS。完整分子/分母和材料/界面区域保留；不调相位、不用total掩盖散射误差。R/T/A在原残差不过时只标diagnostic。

训练未读取参考场，仍保留reference_used_for_training=false；但标量参与停止、设计受历史参考诊断影响，应明确validation_used_for_stopping=true、benchmark_previously_seen=true、design_informed_by_reference_diagnostics=true。新冻结控制也继承此前真实学习，不能叫“没有训练过的控制”。production_initialization_allowed=false贯穿raw/manifest/checkpoint/compare/reopen；合格求解资格可在最终独立记录中判定，不能由预置true字段宣布。条件缩小pilot只读明确通过Gate的模型，是本review限定授权，不意味着通用production初始化获批。

## 6. 预算、低内存与可恢复执行

新增唯一总窗28800 s，自首次准备起包括实现、失败、等待、训练、验证、发布；实际起点马上持久保存，不能再用发布时刻倒推。旧V42账不重开、不清零。建议A与适配软3600 s；LEARNED新增硬10800 s；FREEZE新增硬5400 s；最后至少1800 s完整验收/发布；条件D最多7200 s。软项可以登记转移，不单边扩大候选硬上限，不挪用最后1800 s。

| 路线新增上限；任一先到 | LEARNED | FREEZE |
|---|---:|---:|
| 新增完整轮数 | 默认4，趋势准入后最多8 | 4 |
| 新增核心访问 | 24 | 12 |
| 新增计费LSMR迭代，含丢失工作上界 | 7200 | 3600 |
| 新增隐藏实际调用 | 160 | 0 |
| 新增路线wall秒，含setup/审核/保存/恢复 | 10800 | 5400 |

继承3358次LSMR/53次隐藏调用在各逻辑路径中保留，不在全项目已付账重复收费；原12次核心和4轮也不计成新增成绩。V42学习attempt约2920.6633467 s是本续算实际依赖的一部分，两分叉都需归属共同前缀；旧冻结/Cheb及早年波库不是每条新单场的必要前缀。参考验证及实际必需的网格/native/moments准备另计，冷N=1缺项仍UNKNOWN。

同状态消融先比较相同总第6/8轮及共同可用新增wall边界；最后LEARNED可能跑到12而控制只到8，不能把不等工作量终态差直接称同成本优势。不以0.618 s历史梯度内核时间代替本次核心LSMR耗时。只有同严格精度且完整账本可比，才可能授≥20%时间或同时峰收益；控制分叉本身也不等于最佳传统FE基线。

CPU-only/MPI1/math/Torch1、单个现场合格物理核，numeric warn12/hard16GiB、含临时规划12GiB、新cache/AD≤1GiB、轻2GiB、自身swap/OOC0。原PSI/CPU/SMT、系统max(128GiB,10%有效内存)和384GiB邻增长余量不变，整机2TB不作为本任务可占满的RSS。成功60s准入计总wall，不扣旧失败观察池；真实拒绝后的额外前台等待≤900 s，不无限等资源或后台抢跑。

延用durable launcher/watchdog；在已有外层deadline-150 s进入收口，预留至少120 s完整安全保存，不由新增循环覆盖监督门。每个完整核心/隐藏/轮次后先原子保存一致模型、c/r、RNG、位置、计数和source，再发布committed；纯writer/checker修复不重算健康producer。中断发生在LSMR内且无内部检查点时，只能恢复上个完整边界，丢失作用与预留迭代照计，不宣称零成本恢复。

## 7. 与0.7nm目标的联系与条件pilot

当前证据支持的是有限续研，不是生产路线：13%的场误差仍严重不合格。2TB能放宽容量，不能替代误差收敛；rank8小权重不代表原全算子、CL展开、DtN、全场/残差和微批AD在目标规模可用。没有真实大尺寸数据，就不对单场48h作线性外推。

仅当LEARNED实际M5联合PASS、同状态控制已经冻结并验收、资源安全且总窗剩余≥9000 s（其中最后1800 s不可动），才允许复用既有条件设计，执行一次M5所有长度×0.14的0.7nm非可分三维pilot。D整体最多7200 s，数值训练最多原合同2轮/1800 s。统一正式0.7nm材料、实际网格/背景/全部模式/chi/参考重新绑定，不硬套40端口、不缩放旧FE系数；合格模型归一化核参数只作初值并计全部必要前缀。不满足前置就NOT_RUN，不提前注册空输入。

该缩放基本保持几何/波长比，只有材料和小型三维链的意义；不能证明原50×25×140nm电尺寸、任意结构低秩或连续p/h/端口精度。要成为原目标候选，之后仍须accuracy-qualified离散、多个电尺寸下rank及算子/端口时间内存增长、完整冷单场与全过程RSS；本支不顺势接管传统Full3D工程待办。

## 8. 实施顺序、commit与交付

先只读核对branch/HEAD/worktree/锁/PID及同批是否已有健康工作。合法作业运行时不改HEAD/源码、不kill、不启动副本；重复消息优先继续同一V43。无活跃run且可安全更新时精确fetch/ff-only。遇本地未推送实现与纯本任务review分歧，只沿既有执行补充限定的同分支普通merge保全双方历史，绝不reset/stash覆盖、rebase/amend或merge master。

允许提交顺序：最小执行政策/parent-fork实现及定向测试；正式续算及原始证据；独立核验/用途/汇总。每项正式运行前clean实现commit并绑定源码；后续文档提交不使已hash绑定的健康结果失效。不开新执行分支，不全仓重构、不重装、不开full pytest，不重渲染历史。

先实现/validate新stage与现代资源分派，再串行依赖运行：

```text
input/task042extra_feinn_5nm/v43_bloch_resume_checks.dat
input/task042extra_feinn_5nm/v43_bloch_learned_continue.dat
input/task042extra_feinn_5nm/v43_bloch_same_state_freeze.dat
input/task042extra_feinn_5nm/v43_bloch_independent_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

wrapper选正确FE/ML/pure activation并调用`scripts/run_case.py`。LEARNED可以在同一run内完成准入后的第9—12轮，不在第8/10轮另等review；控制随后从同一parent独立运行，不能吃LEARNED新结果。每项确认清场再下一项；条件0.7输入只在真实准入后建立。

正式证据绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境/MPI/线程/资源及artifact hash。新增：

- response_v43.md、outcomes/bloch_ftt_trend_continuation_v43.md；
- compact parent身份/两分叉配对、政策与恢复tests、每轮R/E/H、内层及隐藏作用、actual/producer全场Gate、复通道/六点/功率、来源/资源/修复/最终决策；
- summary当前入口、progress、模型总账、tests/changed_files仅更新本分支，历史原字段和所有失败保留。大数组和轨迹留ignored，独立checker从原数字重算。

状态至少分开报告：PARTIAL_LEARNED_FIELD_IMPROVEMENT_OBSERVED、CONTINUATION_POLICY_ELIGIBLE/STOPPED、M5_JOINT_GATE、SAME_STATE_HIDDEN_ABLATION、NN_RESOURCE_GAIN和FULL_TARGET。V42保留原FAIL及关闭状态，当前页说明新授权和追加结果，不改写其历史判定。

本端仅做原标量算术、停止规则回归及文档检查，不是M5再测或新性能证明。GitHub视觉若只返回源码/错误页则NOT_VERIFIED；有限检查后继续数值工作，不为页面问题重算健康数据。只推送本分支：

```bash
git push origin HEAD:refs/heads/task42extra_feinn_5nm
```

完成两分叉与完整验收、条件D，或触发真实科学/资源/数据/总成本出口后一次交付准确HEAD、显式tracking/ahead-behind、clean及自身清场。不得在接口、commit、第一次普通bug或旧第4轮false处交棒；也不得承诺必然PASS或在第12轮后无限续跑。
