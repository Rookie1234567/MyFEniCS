# Task041 Review V9：H0旧场成本、H1回归与短波长缺口

## 当前阶段结论

H0把两场已完成的 W、5 nm、p6/h4、M480、MPI8×1 cell-condensed consumer 放到相同的 `consumer/markers.jsonl` 阶段边界下比较，并流式汇总其 side RHS 审计。它回答已有工作花在哪里，不重跑求解，也不把不同源码、并行负载下的耗时差解释成某个优化的因果收益。

| 项目 | H0事实 | 当前判定 |
|---|---|---|
| 5 nm数值锚点 | 9月28日和10月3日均完成1920/1920 formal side responses；两场五项真实残差、R/T/A/A_volume、衍射和恢复物理门通过 | 接受两场各自固定离散的数值结果；保留9月28日public/finalizer exit3历史，不用10月3日覆盖 |
| 总体时间 | 9月28日public-to-finalizer为189323.841971047 s；10月3日为202124.563261555 s，后者多12800.721290508 s（约6.76%） | 两场source不同且 `performance_not_isolated`；差值仅描述，不归因为A6、P4、邻任务或单一阶段 |
| 工作量 | 两场内部KSP迭代合计都为30296；10月3日P4 backsolve与refinement各比9月28日多8686次 | 同迭代数不等于每步工作相同；不能从调用数直接换算秒数 |
| 2 nm | 2 nm producer已使用SLEPc PEP/TOAR；旧consumer未完成4800项formal响应 | TOAR不是新候选；旧consumer负结果保留，真实2 nm新路线尚未完成 |
| 0.7 nm W | 只有air-side组件模式枚举和外部材料来源线索；正式W材料封套、完整外部keys、合格h/M及目标容量证据未齐 | 不满足0.7 nm正式计算/2 TB/48 h资格 |
| H0本轮执行 | 文档和只读源码审查；没有运行测试、MPI、QEP或FE | 这是H0时点记录；其后H1组件、13.5 nm Si和W5 fixed-H6 public/service回归分别在后续章节记录 |

机器可读H0证据见[H0 record](records/task041_v9_h0_readonly.json)。该record是H0时点快照；随后H1新增的一场13.5 nm public/service结果在下文单列。本文不把“完整5 nm或13.5 nm解已通过”误写成“0.7 nm容量目标已达标”：10月3日5 nm全流程约56.146 h，超过48 h目标；2 TB目标也没有0.7 nm实测峰值支持。

## H1后续状态：13.5 nm Si public/service完整回归

在完成单`.dat`接线后，Review V9授权的一场13.5 nm Si fixed-H6研究回归已沿service parent→`scripts/run_case.py`→launcher/supervisor→consumer→ExecStopPost finalizer完整运行。它验证了公共身份链和一次完整求解生命周期；H6只提供模态预条件反馈，原全局方程、RHS、RIGHT FGMRES、P4与物理验收不变。

| 项目 | 实测 | 说明 |
|---|---:|---|
| 运行身份 | source `836b7dfb377f11d8d9fd591eacb7a982f7cbbbac`；Invocation `443995ec69bd45d0a36a1be48ced33a3`；Si 13.5 nm、p6/h10、M120、MPI8 | 唯一新public回归；不是W 5 nm或0.7 nm资格 |
| 原方程求解 | 37 outer步；原五项真残差为`1.8215487484151747e-9 / 1.821548606659606e-9 / 2.284003276919731e-9 / 5.083945967955327e-10 / 9.156507528011665e-10`（global/reported/bottom/top/modal） | 全部≤`5e-9`；recovery、physics、80个external Q通道和closure通过 |
| fixed-H6内层 | 264 solver `S_H`作用；最后一次inner reason 2、7次solver作用+1次独立raw末检；raw相对残差`3.4826090281102427e-4 <= 1e-3` | 只持久化最后一次inner独立末检；不宣称此前36次逐一核验 |
| setup固定反馈门 | 8次`S_H`、C matvec 8次；每侧H6 apply 8次、degree-3实际matrix mult 16次；原legacy side预付调用0，Schur columns 0 | setup门成本另列但计入整场；这些rank-local记录不乘8 |
| side与P4工作 | bottom/top side apply 74/74；内层KSP 2410/2608步；P4 backsolve 4820/5216；P4 refinement 0/0 | 每侧本地或复制计数；没有新leading-PH/route-plan复用 |
| 累计operator动作 | fixed-H6每侧共272次apply、544次degree-3矩阵乘；全场C matvec共272次；side内Q 4820/5216、H6 2410/2608、A6 4820/5216、P/PH audit 4820/5216、PH total 9640/10432 | setup门8次已加在fixed-H6总数中；不得把C matvec当作C-LU solve数 |
| C-LU | owner rank 7建立一次；inventory累计attempt/success字段`0/0`，但owner inventory和最后solve显示`8/8` | 全run累计solve数不一致，记unknown；不以C matvec补算 |
| 非重叠时间 | setup到outer开始343.619396 s；outer 2821.718933 s；outer结束到recovery开始0.943681 s；recovery 9.978173 s；recovery结束到final cleanup 0.517839 s；consumer总段3176.842516 s | 来自相邻consumer marker；parent与嵌套阶段不能相加 |
| 外层workflow与资源 | public-to-finalizer 3180.339667 s；service parent 3180.537532 s；finalizer计账wall 3181.091282263 s。tree RSS 8,936,820,736 B，PSS 6,437,861,376 B，USS 6,069,190,656 B，dedicated job cgroup peak 6,214,434,816 B | 同一Invocation只由finalizer计一次；`performance_not_isolated`，tree与专属cgroup峰分列；job swap 0 |
| service终态 | exit0，finalizer 10/10 checks true | integrated secondary checker `not_available`，没有另跑checker |

consumer summary为[`consumer_summary.json`](../../../results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8_cell_condensed/task041_13p5nm_p6h10_m120_mpi8_cell_condensed__hybrid_iterative__mpi8__M120/20261006T052732.307687Z/consumer/consumer_summary.json)，SHA `21ac7e56c45d90cbe540587bda831540d42077a32477cfae8a1daa2ba11f54d9`；finalizer summary位于[run finalizer目录](../../../results/task041_v9_13p5_fixed_h6_public_service_run_20261006T044333Z/finalizer/finalizer_summary.json)，SHA `04d0b4d8c2ade9f85340a363bb38b2abd9f64be4c4a0891bf9608e8fde0682f7`。只读工作量摘录见[cost compact](../../../results/task041_v9_13p5_public_fixed_h6_service_preparation_20261006T044333Z/readonly_h1_13p5_cost_compact.json)。该Invocation已在V5 ledger唯一记账`3181.091282263 s`，ledger SHA `15d4b5dcb1ed0a867e584dc89d33a52da453575697a16a45d2aed101b5964836`。这些数值不能估算W 5 nm成本或0.7 nm容量。side audit的`side_A`计数与最终side诊断范围不同（audit delta和最终累计不一致），因此不将它们混为同一总数。

## 5 nm运行身份与数值边界

| 运行 | 数学源码 / run | 正式响应与数值结果 | 时间与历史状态 |
|---|---|---|---|
| 较早场 | source `d86ee4afb352304c9ff0d5042256ad9a7d0c9a4f`；run `20260928T085850.487306Z` | 1920/1920；`R/T/A/A_volume=0.7331842733877258 / 0.00022009869572797534 / 0.2665956279165458 / 0.2665962726230213`；最大真残差 `6.221702926229589e-11`，门 `5e-9` | public-to-finalizer `189323.841971047 s`；worker exit0但 public/finalizer因运行末端Git identity合同 exit3，保留原分类 |
| 最新场 | source `5bfb813870182fda172f658c8f276f58318844a5`；run `20261001T055115.915457Z` | 1920/1920；`R/T/A/A_volume=0.7331842733875563 / 0.00022009869572797534 / 0.2665956279167157 / 0.2665962726229846`；最大真残差 `6.21753923942821e-11`，门 `5e-9` | public-to-finalizer `202124.563261555 s`（56.146 h）；finalizer exit0，24 h旧目标未达，当前48 h目标也未达 |

两场均为 W 5 nm、p6/h4、M480、MPI8×1、cell-condensed。最新场的R/T/A和能量闭合通过，不构成更细网格的连续性或0.7 nm资格。运行源、consumer摘要与markers/audit的大小和SHA绑定在record中。

## 逐段wall：使用共同marker边界，不叠加嵌套计时

阶段边界直接来自各run的 `consumer/markers.jsonl` 中 `stage` 和 `wall_seconds`。每行是前一边界到后一边界的相邻差值，因而这张表不重叠。`monitor` 独占wall没有marker，记为 `unknown`。`outer_solve_begin → outer_solve_ready` 已包含PC和求解工作；summary里的KSP `timing.total_seconds` 以及PC内部计时是嵌套记录，不再加到阶段wall。

| 相邻边界 | 9月28日 (s) | 10月3日 (s) | 10月3日−9月28日 (s) |
|---|---:|---:|---:|
| `preflight_begin → system_ready` | 1244.023 | 1826.926 | +582.903 |
| `system_ready → both_side_actions_ready` | 939.160 | 1381.736 | +442.576 |
| `both_side_actions_ready → modal_schur_build_begin` | 0.038 | 0.044 | +0.006 |
| `modal_schur_build_begin → modal_schur_ready`（样本/重复＋构建） | 179949.948 | 192042.848 | +12092.900 |
| `modal_schur_ready → outer_solve_begin`（outer setup） | 0.093 | 0.097 | +0.004 |
| `outer_solve_begin → outer_solve_ready` | 7085.226 | 6797.107 | −288.119 |
| `outer_solve_ready → recovery_physics_begin` | 1.189 | 1.144 | −0.045 |
| `recovery_physics_begin → recovery_physics_end` | 88.129 | 57.710 | −30.419 |
| `recovery_physics_end → final_cleanup_complete` | 0.917 | 0.764 | −0.153 |
| marker `preflight_begin → final_cleanup_complete` | 189308.722 | 202108.376 | +12799.654 |
| monitor独占wall | unknown | unknown | unknown |

最后一行marker总长与public-to-finalizer wall的口径不同：marker由consumer自己的 `preflight_begin` 起，并在 `final_cleanup_complete` 截止；public-to-finalizer由外层supervisor/finalizer定义。不得把两者互相替换。10月3日modal/Schur阶段增加约12092.900 s，是相邻marker实测差；它与P4调用数同向变化，但两场source和调度不同，不能据此断定P4或某一内核是原因。outer阶段反而短约288.119 s，仍不足以抵消全流程差值。

## Side RHS与P4实际工作量

下表的`modal_schur=976/侧`不是976个正式解：每侧包含16个样本/重复响应，之后才有960个formal列响应；bottom/top合计1920项formal。`outer` audit每侧10条也不是全局KSP只跑10步；summary记录outer right FGMRES为5步。

| Audit阶段 | Side audit数 bottom/top | 内部KSP迭代数 bottom/top（两场相同） |
|---|---:|---:|
| `cost_probe` | 4 / 4 | 42 / 65 |
| `modal_schur`（16样本＋960列/侧） | 976 / 976 | 14688 / 14620 |
| `outer` audit | 10 / 10 | 385 / 496 |
| 合计 | 990 / 990 | 15115 / 15181；两侧合计30296 |

| 指标 | 9月28日 bottom/top分组 | 10月3日 bottom/top分组 | 总数变化 |
|---|---:|---:|---:|
| P4 backsolve：cost / modal / outer | 104/249；32961/43985；1268/1984 | 110/252；38153/47261；1477/1984 | 80551 → 89237（+8686） |
| P4 refinement：cost / modal / outer | 20/119；3585/14745；498/992 | 26/122；8777/18021；707/992 | 19959 → 28645（+8686） |

两场内部KSP迭代总数相同，但10月3日的P4回代与精化分别多8686次。这说明每步工作量并非仅由KSP步数决定；它没有单独证明增加由A6造成。P4表的三组分项来自side audits，调用数表述为实际审计计数，不将每次rank-max耗时求和冒充并行总wall。

从每条audit的`counts.delta`逐相位汇总，两个运行记录到的Q/P/PH/A6/H6调用数相同；每对数字按bottom/top排列，带分号时依次对应列名中的两个指标。计数来自每条side审计记录，不跨MPI rank相加。它说明这些动作的重复次数没有减少，不能把A6的局部时间变化推广为全流程提速。

| Audit阶段 | Q / P调用数 | PH_total / PH_audit | A6 / H6调用数 | 记录范围 |
|---|---:|---:|---:|---|
| `cost_probe` | 84 / 130；84 / 130 | 168 / 260；84 / 130 | 84 / 130；42 / 65 | 每侧4条审计记录 |
| `modal_schur` | 29376 / 29240；29376 / 29240 | 58752 / 58480；29376 / 29240 | 29376 / 29240；14688 / 14620 | 每侧976条，含16条样本/重复与960条正式响应 |
| `outer` | 770 / 992；770 / 992 | 1540 / 1984；770 / 992 | 770 / 992；385 / 496 | 每侧10条审计记录；不等于全局KSP步数 |

对`modal_schur`逐条读取的`operation_seconds.detailed.max_rank_seconds`也可以按字段求和。每个单元格是“9月28日 → 10月3日”的bottom/top对应计时字段之和，单位秒；它是976条记录的逐RHS rank-max汇总，**不是阶段wall、不是跨rank累加，也不能把表中不同列相加**。

| Side | `q_factor_solve_seconds` | `q_p_seconds` | `q_ph_seconds` | `q_a4_residual_refinement_seconds` | `balance_a6_seconds` | `balance_h6_seconds` | `balance_ph_seconds` |
|---|---:|---:|---:|---:|---:|---:|---:|
| bottom | 10481.850 → 13571.669 | 5643.298 → 9499.964 | 4129.361 → 7363.806 | 8727.528 → 10237.218 | 29615.965 → 21634.400 | 9730.139 → 16465.521 | 4180.795 → 7465.633 |
| top | 12850.832 → 15581.574 | 8954.501 → 9416.777 | 6992.190 → 7403.842 | 11765.831 → 12819.805 | 30212.171 → 20471.510 | 16157.685 → 16766.899 | 6994.281 → 7403.670 |

这些字段分别来自既有`operation_seconds`：Q/P/PH传递、P4解与残差动作、BAL_H动作。raw定义说明`q_p_seconds`与其route/通信子项、`q_ph_seconds`与其子项、`q_physical_action_matrix_mult_seconds`与包含它的`q_a4_residual_refinement_seconds`，以及`balance_ph_seconds`与其PH子项存在嵌套关系；即使各值已单独报告，也不能相加为总成本。不同阶段、RHS和源码下的每条MPI.MAX之和同样不能换算成端到端收益。两场没有能从这些字段独立分离monitor-only wall的记录。

`modal_schur`成功路径每RHS记录的rank-max elapsed求和：bottom为`77694.603 → 93397.837 s`，top为`102190.236 → 98574.353 s`。这两对数是不同RHS的MPI.MAX耗时相加，不是该阶段的整体墙钟；modal阶段真正可比的非重叠wall是上表的markers边界。

### A6局部收益为何不能直接代表整场加速

A6把体作用和DtN邻项融合，减少一段局部动作；已有microbenchmark约降低36–58%，两条冻结5 nm RHS的整次side响应max-rank均值约降低9.6–9.8%，但该局部测量 `not_isolated`。完整consumer还要逐项执行Q/P/PH、精确cell-condensed P4回代、A4检查及必要的同因子精化。两个完整场的计数正显示KSP步数相同而P4工作量不同。outer `pc_apply_seconds`（9月约7079.002 s、10月约6790.484 s）是包含first/delta side response、模态反馈、投影和通信的整体PC累计，不能全归给A6、Schur、某一侧，也不能从modal阶段wall中作严格相减。

两场完整public-to-finalizer差为`+12800.721 s`、约`+6.76%`；运行source分别是`d86ee4...`与`5bfb81...`且均标记为并行非隔离测量。最稳妥结论是：局部A6确有作用级/两RHS信号，但尚未证明完整工作流收益；更大的modal/Schur相邻阶段差、更多P4工作和更短outer wall共同构成观察结果，因果尚未分离。

## 最新13.5 nm Fixed-H6研究锚点

运行目录为[`run_20261005T151618Z_fixed_h6_leading_ph_route_plan_cpu10_17_rankmap`](../../../results/task041_review_v8_on_demand_modal_schur/run_20261005T151618Z_fixed_h6_leading_ph_route_plan_cpu10_17_rankmap)。运行source `df9c3b368516eb0a14574b2d9f9ea1d90ce32bf0`，Invocation `c0ef9dd4e7b2410182543d6c18a5e178`。它是13.5 nm Si、p6/h10、M120、MPI8的研究候选，使用fixed-H6 modal GMRES、route-plan及leading-PH-dual复用；不能当作W 5 nm或0.7 nm验证。

| 量 | 已存结果 |
|---|---:|
| workflow wall / consumer worker wall | 3140.3142969929613 / 3138.23346615606 s |
| outer步数 / `S_H`作用次数 | 37 / 264 |
| 最终outer五项真残差 global/bottom/top/modal/reported | 1.82160410400884e-9 / 2.284102068287176e-9 / 5.084205552897934e-10 / 9.15675086602306e-10 / 1.821604281085912e-9（各≤5e-9） |
| 最后一次inner | raw相对残差 0.0003482367629781309；7步；reason 2；独立inner门通过 |
| side调用 | fixed-H6每侧264次apply、528次矩阵乘；原first/delta每侧37；BAL_H callback bottom2614、top2847 |
| route-plan payload | 8 rank、16 side记录；索引载荷合计6479456 B；最大rank/side 483128 B |
| 资源观察 | process-tree峰约8945627136 B；专属job cgroup峰约6258421760 B；`performance_not_isolated` |
| inventory | 按需modal作用；没有materialized全Schur列，columns=0；modal condition未测 |

五个outer残差通过并恢复/物理门通过，只证明最后inner有存储的独立raw门结果；没有36个更早inner终检值可逐项复核时，不补写为36次均通过。route-plan索引payload是对象字节，不是进程RSS。该anchor用于复用同一数学不变部分与接线规划，非性能对照或0.7资格。

### 较早13.5 nm Fixed-H6 baseline的历史outer侧计时

`1177.4862258147914 s`（bottom）和`1288.735517281806 s`（top）来自baseline run `run_20261005T022505Z_fixed_h6`，source `455540e5350c1743598ea65d828c7940f4473d5f`，consumer summary SHA `3c0297553e8ab91592868d29794c46351091f031854841003bcc4b78b02942a4`。这不是上表current route-plan run，也不是`df9c3b...` leading-PH anchor。证据来自[pair closeout JSON](../../../results/task041_review_v8_on_demand_modal_schur/13p5_fixed_h6_route_plan_reuse_research_preparation_20261005T075635Z/readonly_fixed_h6_route_plan_pair_closeout_20261005.json)，SHA `1db620668805bb41a1d4d3822a4c23f76237333052ae7357dc03d4dcbf823cb8`：baseline bottom/top分别位于`/side_rhs_audits/baseline_phase_side_aggregates/4/sum_of_per_rhs_MPI_MAX_elapsed_seconds`与`/side_rhs_audits/baseline_phase_side_aggregates/5/sum_of_per_rhs_MPI_MAX_elapsed_seconds`；每侧74条。合计`2466.2217430965974 s`是由两项相加得到的derived值。它只是逐RHS的MPI.MAX耗时和，不是phase wall，且baseline同样`performance_not_isolated`，不能用于严格成本归因。

## 2 nm与0.7 nm的容量/材料现状

| 目标 | 现有可用证据 | 尚缺内容与边界 |
|---|---|---|
| W 2 nm，p6/h1.5，M1200，MPI8 | 2026-09-18 producer summary显示正/负侧均为SLEPc `PEP/TOAR`、general quadratic polynomial、shift-invert MUMPS LU；requested 2400，converged 2422/2423，各26次迭代。rank-max分项：positive-right 6009.042 s、positive-adjoint 8324.175 s、negative-right 6206.448 s、negative-adjoint 8658.907 s、reciprocal 285.402 s、总29500.000 s；另存producer phase 29504.116 s，两者嵌套，不能相加 | 旧consumer重复门失败，formal `0/4800`，不是新的完整2 nm收敛/容量资格。`ncv/mpd`没有记录，源码默认值不代替实测配置。已用TOAR，容量审查应优先量大nev下左右基、shift因子及workspace |
| W 0.7 nm材料候选 | 来源字节已封存；E=`1771.202834760004 eV`，Henke线性插值得`f1=29.482678085431722`、`f2=9.276118377813308`；NIST/CIAAW给出N=`6.322199557658834e28 m⁻³`，项目正耗散约定下`n=0.9995903781323069+i0.00012887909720587614`、`εr=0.9991809074448665+i0.00025765261101874415` | 来源和派生值已可追溯，但未形成正式`.dat`/resolved材料身份；未传播Henke插值、CIAAW原子量或CODATA常数不确定度。1809.1/1809.3 eV吸收边两点不跨边插值 |
| W 0.7 nm全目标几何外部keys候选 | 现有几何与`outgoing_port_modes_3d`派生32056有序key：top16030、bottom16026；S/P各16028；32054 propagating、2 nonpropagating、0 Rayleigh；canonical UTF-8 key SHA `9f43482413e86c5d2db2e7ba8e5fed0b684d89566f070a88946f4c6bbbc7d4b5` | 这是完整W候选材料/目标几何的轻量枚举，不是旧16030 top-air-only列表。仍未绑定正式input/resolved/packet identity；正式channel material/geometry qualification未完成，亦未运行QEP |
| W 0.7 nm结构规模 | H0派生p6/h0.525投影DoF约173,802,000、active trace约51,192,000、NNZ约43,283,050,000；旧因子存储估算3234–32342 GiB | 结构派生旧估算不是fixed-H6对象清单或RSS上界；cell factors、TOAR bases/shift factor、DtN、恢复和MPI驻留缺实际bytes/并存证据。2 TB/48 h未证 |

### H2 W2 fixed-H6容量决定（2026-10-07，只读）

官方输入为W 2 nm、p6/h1.5、M1200、MPI8、cell-condensed；既有TOAR packet身份可复用，但历史consumer在sampled-repeat实现路径停止，formal响应`0/4800`。当前**不启动**新fixed-H6 W2场，结论为`capacity_blocked_unqualified`，不是测得OOM或新算法数值失败。固定H6新路线的完整峰值未知。

本次两点host/node0 raw见[样本1](../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/host_visible/host_sample_1.json)（SHA `c5b53667b63a5545a3f4954c05b323e845a1417fa284b5dcb894e18093522559`）及[样本2](../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/host_visible/host_sample_2.json)（SHA `2cca36005b6496f0ccc9ddace8e8f3f3d87fdc49e75fe8ade5698507893a7aa8`）。node0 MemFree=`854604922880/854608048128 B`；host MemAvailable=`2070749650944/2070796640256 B`。注册W2 hard/warn/planning ceiling=`1759218604442/1539316278886/1649267441664 B`，注册reserve/baseline=`412316860416 B`；consumer timeout字段345600 s但不执行elapsed stop。任务书§10.2要求host可用量至少`max(predicted_peak+256 GiB, 1.70 TiB)`；固定H6 `predicted_peak`未知，384 GiB baseline不能替代文档合同。

保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`的node0 gate未应用，仅按最小hunk核对：用node0 MemTotal/MemFree作启动与运行门；floor=`412316860416 B`；effective hard=`min(registered hard, node0 MemTotal−floor, node0 MemFree−floor)`；warning=`min(registered warning, 90% effective hard)`；采样到node0 MemFree跌破floor时以`node0_memfree_floor`受控停止。按当前两点假设性hard=`442288062464/442291187712 B`，warning=`398059256217/398062068940 B`；扣reserve后的空间比历史树峰`642449637376 B`少约`200.16 GB`，比authority峰`647904415744 B`少约`205.61 GB`。这不是当前活动合同或新场准入值。host/node0快照是容量判断，不是future admission；共享cgroup没有有限限制。

旧process-tree峰出现在top side-factor construction，bottom已ready；其workflow elapsed为`72296.84627462388 s`、consumer-local为`42792.07925245399 s`（该phase边界`32893.35281426599–43916.50308411103 s`）。authority峰出现在第四次top pre-formal repeat，workflow elapsed为`165204.9244649848 s`、consumer-local为`135700.1574428149 s`（该batch边界`116426.447–135702.941 s`），两个side factors/actions和modal sample同时存在。旧单cell exact-P4 factor在consumer-local `8176.224993840093 s`已destroy，但resident packet副本、allocator保留页、后续cell-condensed factors和新H6/C/Krylov/recovery对象的并存均unknown。新fixed-H6明确移除全Schur列物化及旧每侧16次自适应sample预付，改为8次setup反馈门；这不能推断早先top factor/repeat峰会消失，也不能给新路线下界/上界。2 nm producer使用TOAR已是现状（requested2400、converged2422/2423、26迭代）；ncv/mpd、bases、shift factor/workspace bytes未存。

| 新路线库存类别 | 对象及证据状态 |
|---|---|
| 明确保留 | 4.84 GB磁盘packet/identity、cell-condensed P4 side operators/factors、BAL_H side actions、C-LU、固定H6、trace maps、full external DtN、Krylov basis、恢复/输出/canonical arrays、MPI copies；其中多数驻留/并存bytes未知 |
| 明确移除 | materialized full modal Schur columns；旧每侧16次自适应`SideBalancedInverse` sample/repeat预付。替代门为8次固定H6反馈作用，不是零成本 |
| 新增/改变 | setup中8次`S_H` gate；每侧8次H6 apply/16次degree-3 MatMult，8次C作用；GMRES每solve仍最多9次solver作用+1次独立末检 |
| 未知 | TOAR稀疏矩阵、左右基、MUMPS shift factor/workspace；cell-condensed局部因子大小及重叠；packet驻留/复制；H6 scratch、C因子、S_H/Krylov向量；DtN/全场/recovery buffers；各对象MPI复制方式和新路线同步高水位 |

原始逐对象字段见[只读机器记录](../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/w2_capacity_h3_assessment_20261007.json)，SHA `10e67f3e8115874f26cfac71af16b0f096019e548d56ed2f0773914fdd001f81`；资源与并存解释的[派生更正](records/task041_v9_w2_h3_interpretation_correction_20261007.json)不修改原始记录。当前不以“启动后等硬门”代替证据；新fixed-H6对象并存峰未知，不能作保守容量上界，也不据旧peak认定新路线超限。

### H3 W 0.7 nm候选派生与轻量pilot边界

来源原始文件逐项SHA见同一[机器记录](../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/w2_capacity_h3_assessment_20261007.json)；文件位于`results/task041_v9_13p5_public_fixed_h6_service_preparation_20261006T044333Z/h3_sources/`。取Henke在1752.87 eV `(f1,f2)=(32.5247,9.39200)`与1781.22 eV `(27.8205,9.21280)`作线性插值；以精确SI的h、c、e求`.7 nm`能量1771.202834760004 eV，插值比例0.6466608380953782，得`f1=29.482678085431722`、`f2=9.276118377813308`。NIST钨密度19.3000 g/cm³、CIAAW相对原子质量183.84(1)、CODATA经典电子半径`2.8179403205e-15 m`和精确Avogadro常数给`N=6.322199557658834e28 m⁻³`与`N r_e λ²/(2π)=1.3893645160256921e-5`。按项目正吸收符号，`δ=4.0962186769307124e-4`、`β=1.2887909720587614e-4`，`n=1−δ+iβ=0.9995903781323069+i0.00012887909720587614`，`εr=n²=0.9991809074448665+i0.00025765261101874415`。Henke展示约定的虚部符号相反，必须按项目约定转换；不能直接搬负虚部。未做材料/source/interpolation不确定度传播，也未写正式输入。

现有代码可在不建QEP的轻量几何计算中列出完整候选keys：从既有`SimulationConfig3D`/target-stage几何构造配置，用`outgoing_port_modes_3d`生成模式，并按`(side,m,n,polarization)`规范顺序序列化。目标50×25 nm几何得32056 keys；文件`../../../results/task041_v9_w2_capacity_decision_20261007T020417Z/w0p7_external_keys_candidate_20261007.json`为1633069 B、SHA `bb50ccac921413aab2ab213becd3bdb6bbd1a321c129e29f7071c358850ef863`，其中canonical key JSON 1,631,161 B、SHA `9f43482413e86c5d2db2e7ba8e5fed0b684d89566f070a88946f4c6bbbc7d4b5`。这是候选材料/几何计算产物；正式`.dat`的介质、orientation、normalization与resolved identity仍需由注册输入链权威绑定。历史16030 top-air-only key表不能替代完整W通道。

当前侧逆接口只支持p6，因此撤回先前p4→p5阶次泛化方案。一个独立缩减pilot候选保持p6：周期10×5 nm、z范围−2到26 nm、材料表面`interface_z=0`、grating宽3.4 nm/高24 nm、air 26 nm、substrate 2 nm；Hybrid内部bottom/top界面由原目标10/110 nm按几何1/5映射为2/22 nm，不能与材料表面z=0混淆。候选阶梯是p6/h0.70/M400作未资格化起点；仅在其门通过后，固定p6/M400把h改到0.525；再固定该网格只改M到600。M400只是计算起点，不能由面积或`1/h²`公式称为已资格，也不作DOF/内存预测。保持10×5缩减几何与50×25目标身份分离；此候选不是完整目标。

此pilot当前还不是可执行`.dat`：`physical_balanced_side_inverse.py`只接受p6，满足阶次方向；但W 0.7新`model_id`未注册，当前Task041 input registry、BAL_H case、P4 target和fixed-H6 consumer scope均拒绝未知模型。缩减尺寸是否满足loader的层区与uniform propagation假设须在最小注册审查中逐项核；明确的几何候选为`0 < bottom=2 < top=22 < interface+grating_height=24`。如进入后续实现，需为新model_id注册专用10×5×0.7身份及p6、h/M ladder，审核Hybrid内部界面2/22映射、P4 target和CPU/资源/public service绑定；不得复用W5/13.5/2 nm身份或关闭身份校验。未经该审核，不称schema/loader通过。

pilot候选的光学材料和通道均属`derived`。target 50×25 nm key候选32056项与本pilot 1292项分别绑定各自的几何/输入身份；两组都保留各自2项nonpropagating key，原`auto_propagating`及zero-Rayleigh策略不变。`M`是内部模态数，不等同于外部传播通道总数；目标M32056与pilot M1292也不是此处的p6/h0.70/M400起点。来源和派生值尚未经过完整不确定度传播，也没有材料实验精度认证；这不是新增pilot门。正式输入封套需要绑定原始来源字节hash、使用常数和单位、Henke插值区间/方法、正吸收符号、n/epsilon、几何、每组有序external keys及resolved hash。

NIST来源为[元素钨密度表](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=074)，CIAAW为[钨原子量页](https://ciaaw.org/tungsten.htm)，Henke为[W光学常数文件](https://henke.lbl.gov/optical_constants/sf/w.nff)及[公式说明](https://henke.lbl.gov/optical_constants/intro.html)。来源原始字节保存在`results/task041_v9_13p5_public_fixed_h6_service_preparation_20261006T044333Z/h3_sources/`：`w.nff` 13,801 B/SHA `dd11d29386952edd3259f2d3c4ddc88589ff6f6fb1e3ba3db43a4c589ea3ad95`、Henke公式页SHA `5dea737ff27676a17c9a076c9f9b99e40a3dfec4767fbeb549862b21b5cdfdc6`、NIST页SHA `d99569a1c84837b1f5f29e9a3862ddcc8d4acac4a52fe064cb9fd503cacfcd91`、CIAAW页SHA `b997d72d2e2cff592ce9ed5e07a490dc6ba331ea6efc5506b345bffd0ddf5454`、BIPM常数页SHA `dddeb6c0c7171df77f20c48742cb4774a5b1062d58a35d5ea75477bab31331e7`、CODATA PDF SHA `4d7e7f34b98ab2fc4df68b38247f818f6fc8bdf7f25f91abcdfbc329e22d2f32`。NIST密度19.3000 g/cm³、CIAAW原子量183.84(1)对应候选原子数密度`6.322199557658834e28 m⁻³`；0.7 nm能量为`1771.2028347600037 eV`，插值比例`0.6466608380953702`。这些来源字节及派生值便于追溯，但正式材料输入、常数使用记录和完整W外部通道仍需独立资格化。本次不变更冻结5/2 nm材料、不运行QEP或生成正式0.7 nm输入。

## W5 legacy-native packet到fixed-H6的最薄兼容方案（H0时点规划快照）

截至H0审计时，10月3日完整W5已有数值身份，不是缺packet或缺布局；当时fixed-H6新profile入口与legacy-native descriptor目录形状不兼容。旧producer的公共资源证据另为`unqualified`，不能冒充资源PASS，也不应抹掉已有数值身份。以下保留当时的规划边界，当前实现状态见后续H1更新。

| 合同 | 最薄兼容边界 |
|---|---|
| 适用范围 | 只给注册W5、p6/h4、M480、MPI8、`cell_condensed`、P4 target `5e-13`的fixed-H6显式研究分支增加legacy descriptor入口；13.5/2 nm新profile及普通legacy默认不变 |
| 验证路径 | 原样复用`task041_legacy_native_profile`、`validate_task041_legacy_native_packet`和`bind_task041_legacy_native_consumer`，继续核验source/input/resolved/physical、M/MPI、600个external keys及packet manifest/shard hashes；不复制mode-prep封套、不放宽新profile validator |
| 路由位置 | H0规划范围为只在`run_case.py`、`task038_launcher.py`、`task041_supervisor.py`、`task041_service.py`和`task041_exact_side_workflow.py`的fixed-H6 guard加入W5边界例外；service argv/manifest/worker传递同一descriptor身份 |
| 负边界 | producer root与legacy descriptor必须恰有一个；两者皆无、同时提供、错target/scope/CPU map、额外诊断都拒绝；route-plan与leading-PH继续默认false |
| 资源解释 | `resource_qualified=false`保持历史事实；新W5 consumer必须依自己的public service门采资源，不能继承或伪造producer资源资格 |

10月3日`supervisor_summary.json`已经记录`validated_legacy_native_packet`和descriptor SHA `175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86`；packet manifest、identity、600-key绑定和consumer输入身份均已在“5 nm运行身份与数值边界”部分绑定。H0本身没有读取shards或重跑validator。其后提交`ce31f3738f469a04d23c50af0a7c7306afde3b38`已按该边界实现W5 fixed-H6 descriptor/binder兼容；路由测试证据见[Response V11](../response_v11.md)和[test summary](test_summary.md)。该段描述的是H0时点；W5实际public/service结果见下方H1终态。

## H1：W5 fixed-H6 public/service完整回归（2026-10-06）

固定反馈给模态方程的内层迭代提供一个按需近似作用，避免先为全部模态列逐一调用昂贵侧区逆；正式答案仍由原全局算子、右预条件FGMRES、P4修正、五项真实残差和物理门决定。本场复用已验证的legacy-native W5 packet，不重跑QEP；旧producer资源资格仍为`unqualified`，本场只用自己的准入和资源采样。

| 项目 | 实测 | 解释与范围 |
|---|---:|---|
| 身份与终态 | source `d6fe6b2b239896e66d8c5d1bf9b8a0e45931a561`；Invocation `2539de4d129f41e2ac49536bfd3b6fde`；W 5 nm、p6/h4、M480、MPI8、`cell_condensed`、P4 target `5e-13` | `TASK041_CONSUMER_PASS`；固定H6为显式研究方法，不是普通默认 |
| 原方程求解 | 49 outer；五项真残差 global/bottom/top/modal/reported=`8.573354680237858e-10 / 4.87285789944735e-9 / 4.3588733213657296e-10 / 3.0159774145340474e-9 / 8.573351523834966e-10` | 全部`<=5e-9`；KSP reason 2，recovery、physics、traction、interface及external-Q门通过 |
| 物理输出 | R/T/A/A_volume=`0.7331842734229947 / 0.00022009869546076797 / 0.2665956278815445 / 0.2665962726246991`；closure=`6.447431546430238e-7` | 此场官方输出通过原门；integrated full-3D secondary checker仍`not_available/not_run` |
| 固定反馈工作 | 旧legacy预付probe为0；setup gate 8次`S_H`、每侧8次H6 apply/16次MatMult、8次C matvec；49个inner共258次solver `S_H`和49次独立末检 | setup+solve为315次`S_H`、每侧315次H6 apply/630次MatMult、315次C matvec；C-LU只因子化1次，owner累计LU solve attempts/successes为307/307；不同rank的复制报告不相加 |
| 原侧区与P4工作 | bottom/top各98条apply记录，内部KSP 3839/3893步；P4 backsolve 11551/15546，refinement 3873/7760 | side Q/A6/P/PH与H6按各自审计字段保存，不乘8；原侧区不是固定H6算子 |
| 非重叠wall | consumer marker setup到outer `2110.216175755 s`；outer `57734.113258151 s`；outer ready到recovery begin `1.625604577 s`；recovery `59.012698122 s`；recovery end到cleanup `0.804580129 s` | 各段来自相邻marker；consumer wall `59905.832512734 s`；唯一public-to-finalizer账为`59914.951233018 s`，由service finalizer写一次 |
| 资源与清理 | process-tree峰`42,573,258,752 B`；专属job-cgroup峰`41,376,940,032 B`；job swap峰0；finalizer 10/10 checks true | warning/cap/reserve为`47,899,046,707 / 53,221,163,008 / 412,316,860,416 B`；保持`performance_not_isolated`；不同内存口径分列 |
| 限定 | H0 Oct 3 wall `202124.563261555 s`；本场wall较低`142209.612028537 s`（派生约70.36%） | source与方法变化、宿主未隔离，不能称因果加速；两场旧新峰值差也不是内存优化资格 |

同一Invocation的consumer、side audit、marker、run/resource、service及finalizer文件SHA见[W5 machine record](records/task041_v9_fixed_h6_public_5nm.json)，record SHA `498e898e2e789daa392281b13c70e0b582def3032b5776b2af296c735796fb47`。该record绑定finalizer唯一ledger增量`59914.951233018 s`；不再重计consumer/阶段/rank墙钟。完整secondary checker、W2、0.7 nm、2 TB容量和目标48 h资格仍未建立。

### W5 fixed-H6与explicit-Schur候选的离线产物对照（2026-10-08）

这次只读checker把W5 fixed-H6结果与既有explicit-Schur candidate artifact按原阈值比较；右侧“reference”仍是candidate角色，不是exact truth。此前一次调用因候选method不属于注册route而在artifact identity处被拒，numeric未评估，checker wall`122.18274498195387 s`；保留其attempt与raw，不计入FE账。旧reference summary SHA为`bd8cf3d9696c17a54c64239334acab90de3e9dc1cae383c4b9fe537991eb332d`，fixed-H6 candidate SHA为`4257b309c5381498c6a84110d5c49e86eb0e3ca78272b09b7bb6ee731dd18526`；两侧input/resolved身份相同，18项artifact identity和public input envelopes均通过。该派生比较不会撤销上节W5 public/service自身已通过的残差与物理门；它回答的是两组保存产物是否满足逐项等价阈值。

| 比较项 | 差值/误差 | 判定 |
|---|---:|---|
| R/T/A/A_volume（fixed-H6−explicit-Schur） | `+3.543842996833746e-11 / −2.6720737168056674e-13 / −3.5171199286310184e-11 / +1.7145174169286292e-12`，各限`1e-8` | 通过 |
| selected E/H相对L2 | `5.688326111234493e-10 / 5.742838138430747e-10`，各限`1e-6` | 两项通过 |
| 四canonical角色相对系数L2 | bottom active/full `1.7128976856531144e-8 / 1.6977718026171218e-8`；top active/full `1.1038152408073086e-10 / 1.102299390456392e-10`，限`1e-5` | 通过 |
| 外部通道 | 600个ordered keys完全一致，其中26个显著；唯一失败项`["bottom",-15,0,"s"]`幅度/功率相对差`1.0880143757234042e-6 / 2.074050200051092e-6`，限`1e-6` | 其余25个显著项通过；这一项超限，external gate与整体numeric comparison失败 |
| 法向通量 | relative L2 `1.7488283863630695e-11`，限`1e-4` | 通过 |

比较器status为`numeric_gate_fail`、full comparison false；raw-Q跨场逐向量比较`not_run_not_defined`，资源/workflow可比性`inconclusive`，integrated full-3D checker和solver/FE均`not_run`。失败项参考功率`2.2419065611486787e-8`高于显著性floor`1e-8`，因此其幅度绝对差`2.4738743521870602e-11`和功率绝对差`4.6498267516462735e-14`虽小，仍须遵守原`1e-6`相对门。candidate/reference复幅值、分母和所有差值见[失败行记录](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_significant_external_failure_record.json)，SHA `9fe88ab05dfb1b448935e127103a3d871b5d07f4626133ef23943f51ebf7cb3a`。实际读取了双方32个canonical shards，共`1,313,610,614 B`。唯一完整checker调用wall`533.9173726618756 s`，Python父wall`534.6402724480722 s`，单Python进程`ru_maxrss=5,691,043,840 B`（不是process-tree或cgroup峰），`performance_not_isolated`；该离线时间不进入FE ledger。原compact [`w5_offline_comparison_compact.json`](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact.json) SHA `c088bd14872e924d990cdb4e1eed94af96c3f9bbf477cbc376389815ae96a032`原样保留；带正确有符号R/T/A/A_volume差值的[更正compact](../../../results/task041_w5_candidate_artifact_comparison_retry_20261008T002033Z/w5_offline_comparison_compact_corrected.json) SHA `f9505f6b92cc14cec3da9b863f21cb6bbbaacf98393db9eed56ad56c94b70f63`，更正回执SHA `21320f82533a74bcfb066e9d207a24b2189759a289122dd9a176a505a03e724e`；原始derived JSON SHA `b65537515682987ea7e5eac15e655cf231af885eb66ea9170dbb4669231e9fcc`。两侧run与输入产物未修改。

## 尚未执行与下一步

| 阶段 | 当前状态 | 退出前必须提供 |
|---|---|---|
| H0 | 文档、markers分段、全量side count、13.5/2 nm/0.7 nm只读审查完成；H0 record保留其冻结时点 | 后续H1结果另列，不覆盖H0历史 |
| H1 | fixed-H6组件/路由和13.5 nm Si回归通过；唯一W5 fixed-H6 public/service场已完成且原五门、恢复/physics和finalizer均通过 | W5是研究候选；性能`not_isolated`，integrated checker未运行；不外推W2/0.7/2 TB资格。详见上方H1表与record |
| H2 | 未启动；W2 fixed-H6为`capacity_blocked_unqualified` | host样本已高于1.70 TiB，但预测峰项未知；node0扣384 GiB floor后约442.29 GB。旧峰仅为不同后端风险信号，新路线峰未知；不是政策冲突或已测超限 |
| H3 | 材料/key和p6缩减pilot为derived候选，资格`not_run` | 新model_id未注册，candidate `.dat`不可执行；formal source/constant/resolved绑定及p6 h/M真实门待审。材料不确定度模型未做，但不是pilot额外门 |
| H4 | `not_run` | 目标50×25 nm完整单胞，实测2 TB物理内存口径和从输入到恢复/核验/清理全过程≤48 h |

目前没有依据宣称0.7 nm材料、2 TB容量或48 h目标已解决。没有新运行结果时，不复用旧的D1e、小RHS均值或local A6微基准作为新路线实测。

## H1组件与接线测试状态（2026-10-06）

fixed-H6反馈repeat/linearity门已在test350 tiny代数fixture完成serial与MPI2验证；后续13.5 nm Si和W5 public/service整场均完成各自原数值门。W5沿原legacy-native validator/binder复用旧packet，并用新consumer自己的资源合同和ExecStopPost finalizer收尾；组件测试、单场与资源边界见[test summary](test_summary.md)。下一步是以既有W2 packet准备一次fixed-H6同生命周期场，不重跑W5或QEP；H3/H4仍按上表保留未完成项。
