# Task041 Review V9：H0旧场成本、短波长缺口与最小接线审查

## 当前阶段结论

H0把两场已完成的 W、5 nm、p6/h4、M480、MPI8×1 cell-condensed consumer 放到相同的 `consumer/markers.jsonl` 阶段边界下比较，并流式汇总其 side RHS 审计。它回答已有工作花在哪里，不重跑求解，也不把不同源码、并行负载下的耗时差解释成某个优化的因果收益。

| 项目 | H0事实 | 当前判定 |
|---|---|---|
| 5 nm数值锚点 | 9月28日和10月3日均完成1920/1920 formal side responses；两场五项真实残差、R/T/A/A_volume、衍射和恢复物理门通过 | 接受两场各自固定离散的数值结果；保留9月28日public/finalizer exit3历史，不用10月3日覆盖 |
| 总体时间 | 9月28日public-to-finalizer为189323.841971047 s；10月3日为202124.563261555 s，后者多12800.721290508 s（约6.76%） | 两场source不同且 `performance_not_isolated`；差值仅描述，不归因为A6、P4、邻任务或单一阶段 |
| 工作量 | 两场内部KSP迭代合计都为30296；10月3日P4 backsolve与refinement各比9月28日多8686次 | 同迭代数不等于每步工作相同；不能从调用数直接换算秒数 |
| 2 nm | 2 nm producer已使用SLEPc PEP/TOAR；旧consumer未完成4800项formal响应 | TOAR不是新候选；旧consumer负结果保留，真实2 nm新路线尚未完成 |
| 0.7 nm W | 只有air-side组件模式枚举和外部材料来源线索；正式W材料封套、完整外部keys、合格h/M及目标容量证据未齐 | 不满足0.7 nm正式计算/2 TB/48 h资格 |
| H0本轮执行 | 文档和只读源码审查；没有运行测试、MPI、QEP或FE | H0已完成；H1–H4完整阶段当时均未完成，Review V9仍进行中 |

机器可读证据见[H0 record](records/task041_v9_h0_readonly.json)。本报告没有把“完整5 nm解已通过”误写成“短波长容量目标已达标”：10月3日全流程仍约56.146 h，超过48 h目标；2 TB目标也没有0.7 nm实测峰值支持。

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

## 2 nm与0.7 nm的容量/材料缺口

| 目标 | 现有可用证据 | 尚缺内容与边界 |
|---|---|---|
| W 2 nm，p6/h1.5，M1200，MPI8 | 2026-09-18 producer summary显示正/负侧均为SLEPc `PEP/TOAR`、general quadratic polynomial、shift-invert MUMPS LU；requested 2400，converged 2422/2423，各26次迭代。rank-max分项：positive-right 6009.042 s、positive-adjoint 8324.175 s、negative-right 6206.448 s、negative-adjoint 8658.907 s、reciprocal 285.402 s、总29500.000 s；另存producer phase 29504.116 s，两者嵌套，不能相加 | 旧consumer重复门失败，formal `0/4800`，不是新的完整2 nm收敛/容量资格。`ncv/mpd`没有记录，源码默认值不代替实测配置。已用TOAR，容量审查应优先量大nev下左右基、shift因子及workspace |
| W 0.7 nm材料 | 主控浏览提供的CXRO/Henke候选数据点：1752.87 eV处f1=32.5247、f2=9.39200；1781.22 eV处f1=27.8205、f2=9.21280，括住约1771.2 eV。NIST给纯W密度19.3000 g/cm³，CIAAW给Ar(W)=183.84(1) | 这些是一手来源线索，源字节hash、常数版本、插值规则、密度/原子量使用记录与项目符号转换仍未封存；项目约定正耗散`n=1−δ+iβ`，必须从Henke公式约定显式转换，不能粘贴负虚部。1809.1/1809.3 eV邻近吸收边，不能跨边插值 |
| W 0.7 nm完整外部模式 | Task039只能生成air-side组件模式清单：16030个top air keys，已测inventory SHA `28cf61cebf8656b207a5128cc98dda4e0bfcaad4cdb1fe1b784b33bcacd14e4d` | 此值没有W grating/substrate、两侧介质与完整正式input身份，不能当0.7 W外部通道清单。`src/io/execution_plan.py` 与validation显式以`0P7NM_MATERIAL_INPUT_INCOMPLETE`拒绝Full3D launch |
| W 0.7 nm规模 | 派生候选h≈0.525 nm仅来自保持h/λ的尺度关系；p6/h0.525的投影DoF约173,802,000、active trace约51,192,000、NNZ约43,283,050,000，旧因子存储估算3234–32342 GiB | 这些是结构/容量派生，不是实际材料、网格、所选M、factor或RSS测量。缺正式材料和external keys、合格hp/M阶梯、各对象生命周期字节及目标运行的node分布。2 TB/48 h目前均未证 |

NIST来源为[元素钨密度表](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=074)，CIAAW为[钨原子量页](https://ciaaw.org/tungsten.htm)，Henke为[W光学常数文件](https://henke.lbl.gov/optical_constants/sf/w.nff)及[公式说明](https://henke.lbl.gov/optical_constants/intro.html)。这里只登记主控浏览提供的来源线索与候选点值；尚未下载封存源字节或生成正式输入。后续材料封存应独立记录来源版本、文件SHA、密度/原子量、eV–nm转换、复折射率符号和插值区间。本次不变更5/2 nm冻结材料、不运行QEP或生成0.7数值输入。

## 最小V9接线审查（仅规划，不是实现）

fixed-H6的作用是给模态未知量提供廉价、固定的双侧反馈，避免预先为所有模态列重复求昂贵侧区响应；代价是它只是原外层系统的预条件近似，必须继续以原全局算子、RHS和五项真残差验收。当前`fixed_h6_modal_gmres_research`只在内部贯穿到factory，`scripts/run_case.py`没有这个公开开关，已有fixed-H6 scope也只允许13.5 nm Si、cell-condensed、M120、MPI8、V8、candidate、`target=None`。V9应使用一个默认关闭的CLI opt-in，不增加新的dat字段/模型类型，不改变ordinary default。

| 层 | 现有位置与最窄接线 | V9新增检查 |
|---|---|---|
| 单.dat公共入口 | `scripts/run_case.py::_parser/main`；它已有`--task041-p4-refinement-target-tolerance`，并把单个resolved `.dat`交给`launch_specification` | 新的`--task041-fixed-h6-modal-gmres-research`只作为Task041 candidate显式opt-in，缺省false；绑定入resolved/run manifest，不在`.dat`中改模型身份 |
| public launcher | `src/runners/task038_launcher.py::launch_specification`→`run_task041_public_supervisor` | strict-true仅允许注册的13.5 Si anchor与W 5 nm p6/h4/M480/MPI8 cell-condensed formal candidate；未知model/非candidate/额外诊断组合在数值启动前拒绝 |
| supervisor与命令生成 | `src/runners/task041_supervisor.py::run_task041_public_supervisor`→`_task041_builders`→`benchmarks/task041_balh_workflow.py::build_task041_balh_candidate_consumer_command` | 在同一worker命令中透传flag，并校验命令、config、manifest的一致性；不要只在Python wrapper里偷偷改内部参数 |
| consumer与candidate setup | `benchmarks/task041_exact_side_workflow.py::run_task041_consumer`→`_run_task041_balh_candidate_setup`→唯一`build_side_balanced_inverse`→`create_side_balh_block_ldu_preconditioner` | 继续保留producer identity、13.5/W5注册身份、MPI/M/后端与V8 swap-only规则；数值默认路径不变，复用已存在互斥诊断guard，独立标注first/delta侧响应与modal反馈 |
| 5 nm P4 target | `.dat`仍是同一W 5 nm注册input；CLI既有target经`task038_launcher`、`task041_supervisor`、candidate命令和`run_task041_consumer`送入`task041_p4_refinement_target_binding` | 5 nm必须继续要求`5e-13`和最多2次同factor修正；这是精确侧P4逆/回代精化，不是新fixed-H6模态repeat门，也不能被其替代。13.5 nm仍要求`target=None` |
| modal PC | `src/solvers/hybrid_fem_modal_block_ldu.py::create_side_balh_block_ldu_preconditioner` | 只在新opt-in分支用同一FixedH6双侧反馈做有界复数repeat/linearity检查，代替该fixed-H6候选在factory内对原自适应`SideBalancedInverse`预付16次/侧的旧sample repeat；其他默认与Anderson/complex-QR保持原样 |
| 最小测试位置 | 现有`src/test/test_350_task041_balh_block_ldu.py`与`src/test/test_351_task041_balh_public_workflow.py` | 覆盖默认false、单.dat public参数到worker/factory的透传、错scope/互斥拒绝、固定H6复数repeat/linearity、5 nm target保留、原算子/RHS/五残差和cleanup；先tiny/serial，再按实际新增collective另审MPI。当前无测试运行 |

`src/io/input_validation.py`不必因该CLI布尔开关新增`.dat`字段；5 nm与13.5 nm均是已登记的case。`src/runners/task041_service.py`若负责新的systemd config/public-command绑定，则必须新增窄的命令－config一致性检查；此文件当前含用户保护dirty Node0内存Gate补丁，未来实施需在该工作树原有hunk上增量应用并逐SHA保留，不能替换文件或把受保护patch混进审核提交。`src/io/input_validation.py`也有Node0/2 nm protected dirty；避免无必要触碰。当前这里只做调用链阅读，没有编辑这些源码。

新门要在factory/source确认样本所用的是固定H6反馈，且对复数零/近零与非零输入分别定义；通过它不等于真实原Schur已解，也不替代全局outer五项残差、恢复/能量/物理门。若模态H6替代导致outer步数或总成本劣化，Review V9只允许一次预先指定的固定BAL_H反馈备选；不扫描弱PC、预算、history、degree或容差，也不把自适应BAL_H注册成fixed矩阵。H1前仍需主控审核本接线和测试范围。

## 尚未执行与下一步

| 阶段 | 当前状态 | 退出前必须提供 |
|---|---|---|
| H0 | 文档、markers分段、全量side count、13.5/2 nm/0.7 nm read-only和最小接线审查完成 | 主控审阅本报告与record |
| H1 | 组件门tiny serial/MPI2测试已过；public single-dat路由及真实W5 FE仍 `not_run` | 接线后复用数值未变的13.5 anchor；再以V9路线做一次W5真实consumer，保留P4 target `5e-13`、原五门和完整physical output |
| H2 | `not_run` | 用已存在的合规2 nm producer packet进入同尺寸新consumer试算；Ncv/mpd与factor/workspace需实测，达到容量/残差门后才延续完整运行 |
| H3 | `not_run` | 封存W 0.7来源字节/正耗散符号与完整keys；建立小型真实3D和相邻hp/M资格；给逐对象容量模型 |
| H4 | `not_run` | 目标50×25 nm完整单胞，实测2 TB物理内存口径和从输入到恢复/核验/清理全过程≤48 h |

目前没有依据宣称0.7 nm材料、2 TB容量或48 h目标已解决。没有新运行结果时，不复用旧的D1e、小RHS均值或local A6微基准作为新路线实测。

## H1组件测试的后续状态（2026-10-06）

fixed-H6反馈repeat/linearity门已在test350的tiny代数fixture完成serial与MPI2验证：serial非有限参数1 passed；MPI2批准的五selector组两个rank各8 passed。core/test源SHA、ABI、父wall、V5唯一计账见[进行中回应V11](../response_v11.md)和[测试记录](test_summary.md)。这些测试核对门公式、每次作用计数及受控坏rank的拒绝/清理；没有启动public `.dat` consumer或真实W 5 nm场。下一步为public single-dat开关接线与service绑定，然后按H1条件运行一次真实5 nm；H2、H3、H4状态仍分别见上表。
