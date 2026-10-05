# 当前 V30：神经求解研究进行中

| 当前授权 | 实际阶段 | 数值结论 |
| --- | --- | --- |
| [Review V29](../review_report_v29.md)：局部波动神经子空间及同能力固定控制 | S0全矩/梯度和S1解析校准实测完成，S2学习路线运行中；控制及独立审核依赖串行推进 | M5联合Gate/神经资源收益尚未判定，原尺寸0.7nm仍未资格化 |
| 部分256列里程碑 / measured，不是终态 | native0.5535684；256次连续q更新；秩256/256，正交缺陷1.84e-14；实际source fa84926b… | 小空间投影残差3.15e-15不能代替完整原方程；[原值、prefix/state/hash](records/learning_milestone_256_v30.json) |

| 后续512列 / measured，dc89b320源码 | native0.4904158713；秩512/512，正交缺陷2.86e-14；完整保存后暂停资格化投影缓存，随后续同一空间 | 完整原方程未过；[原监督及保存边界](records/engineering_pause_2_v30.json)，不重置原48h预算 |

[新机制与设计](neural_wave_galerkin_v30.md)。本支只做神经，不再续做W0/W1/全口面/存储或传统完成器。以下所有历史结果、负态、费用和UNKNOWN完整保留。

# 当前：Review V28 → Response V29，原尺寸完整口面实算与本机 API 接入完成

把区域内有限元场与外部模式交换的边界计算扩展到上下所有面，而非代表面乘数量。p4/p6各一次健康producer，独立保存checker采用原分母；固定见证的原门通过，但极小原生列的额外逐列负结果及体内未资格化边界保持。不是完整散射解或NN收益。

| measured / 同实例 W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28 | 当前结果、原门与证据 |
| --- | --- |
| 物理/输入 | 原50×25×140nm、Si17/120nm、λ0.7、双Floquet；复用36,263,033B/SHA7dd07d71…输入，旧字节/ledger未恢复、等价UNKNOWN；[设计](records/design_v29.json) |
| 原尺寸口面/空间 | 上下2,176面，x90/46/46/90、y4、z=-10/130nm；p4/p6边界trace行69,632/156,672，全部32,060所选传播模式；不是体积DoF |
| 原门/独立数组 | p4/p6各513,630项失败0，最大相对8.784101295566122e-11/7.435717804637401e-11≤1e-10；[checker](records/independent_checker_v29.json)、[最大值/分子/分母](records/full_surface_metrics_v29.csv) |
| 新宽度矩 | 3,503精确binary64频率/ell0..6，复用357、新3,146；最大绝对9.082805012334877e-14≤1e-12；p6完全复用p4参考 |
| 额外负结果 | 61,200/179,928逐列诊断，1,360/4,947项失败；积分相对最大23.8779043/16.8054835，B/D约0.736/0.743；旧c129 FAIL保留，微小内部迹/体内恢复不授资格；[修复](records/repair_log_v29.json) |
| 真正API/包 | 原FacetPolynomial/BoundaryLayout/DirectionalBoundaryAction(face_inventory=None)实际全口面调用；37相对路径文件/251,699,594B默认ready重开；MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED；[调用/消费](records/main_api_handoff_v29.json) |
| source / 秒 / 采样同时树峰B | p4 ef9f9f39…/153.006203/814727168；p6 91023bdc…/91.694705/910086144；checker c94fe051…/162.992869/545341440；[完整SHA](records/run_index_v29.json) |
| 所有费用/资源 | 正式阶段976.193991953s，开发/失败/等待/发布同一28800s连续窗另记；24/24样本、等待813.597248s≤900；实际worker CPU新鲜度最大2.959228s≤15，60s PSI、原系统及384GiB邻余量；采样ownswap0，未测峰UNKNOWN；[完整账](records/resource_costs_v29.json) |
| 定向测试/呈现 | 最终17项/Ruff/compile通过，旧失败和健康资格不重跑；新页视觉未确认、旧渲染失败保留；[测试](records/targeted_tests_v29.json)、[呈现](records/render_check_v29.json) |
| 全目标/神经/未运行 | 全域原残差、total/scattered E/H/curl、六样点、散射复通道、R/T/A/A_volume均NOT_RUN；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED |
| 收口 | 关闭本轮确定性全口面辅助循环；主线须按自己的合同绑定同instance体积/内部/完整物理门，不混旧B/D/H；无master/production批准；[依赖分组](records/selective_merge_manifest_v29.json) |

[回执](../response_v29.md)、[完整专题](full_surface_action_v29.md)。原尺寸0.7nm完整3D、decimal2e12B整机、ownswap/OOC0、172800s完整冷流程及原精度门尚未达成。M3600较好/Mfinal退化、D0成本否决/D1未运行、旧single-array/严格场/hash/资源失败、UNKNOWN和所有成本完整保留。下方全部历史原文不构成新的自动启动授权。

# 当前：Review V27 → Response V28，新输入/全模式代表面/新目录消费者均已实际通过

本批把可获得的V27清单定义为明确的新实例，再独立核对全部模式物理；随后完成真实原生方向控制、原q60全32060模式边界数组与独立新目录重开。接收状态READY_FOR_MAIN_OPT_IN_NOT_INGESTED。它让主线得到可实际消费的确定性边界包，尚未完成全域接入或原尺寸PDE；不是NN收益。旧原件缺失/旧bitwise失败保留。

| 当前实测对象 / 物理与身份 | 结果、原门与证据 |
| --- | --- |
| schema2新输入 | W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28；36263033B/SHA7dd07d71…；32060key/四组各8015；416780字段检查失败0，最大普通相对1.0747787677074433e-15≤1e-10；[输入/身份](records/input_identity_v28.json)、[科学检查](records/mode_validation_v28.json) |
| 实际native控制 | p4/p6全300/882列、非单位双Floquet和角点；方向/MPC/伴随通过；[run/source](records/run_index_v28.json) |
| 两代表面q60全模式 | 原top/bottom(100,1)、原面宽和分段；p4/p6各32060，1004完整chunk；357频率/ell0..6；一维矩绝对9.082805012334877e-14≤1e-12；[设计/分母](records/design_v28.json) |
| 保存数组独立checker | 1218328项、失败0；最坏原相对9.595725209727146e-11≤1e-10，p6 top(-64,-35,p)回散布，门裕量约4.04%；[全部原数组hash](records/independent_checker_v28.json)、[最大值/分子/分母](records/boundary_metrics_v28.csv) |
| 实际新目录消费者 | 重开1043文件/1625383207B，再核物理和全部数值门；两包manifest SHA664e4ad4…相同；[实际收据](records/consumer_receipt_v28.json)、[主线接入](main_handoff_v28.md) |
| 资源和失败 | 新连续28800s窗；24采样/873.628663s等待；同时树采样峰810545152B、ownswap0；保留所有启动/namespace/socket/quota/import失败，健康producer不重跑；[费用](records/resource_costs_v28.json)、[修复](records/repair_log_v28.json) |
| 未运行及边界 | 条件分面profile未触发；无新Maxwell/Gram因子或solve/NN；原尺寸全场残差、E/H/curl、样点、散射复通道、R/T/A/A_volume/R00 NOT_RUN；[Gate](records/gate_decisions_v28.json) |
| 原目标/主求解器 | 原50×25×140nm、Si17/120nm、λ0.7、decimal2e12B/ownswapOOC0/172800s原门仍未达成；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED |

[Response V28](../response_v28.md)、[专题](versioned_manifest_and_boundary_v28.md)、[定向测试/复用](records/targeted_tests_v28.json)、[分组合并边界](records/selective_merge_manifest_v28.json)、[呈现阻塞范围](records/render_check_v28.json)。M3600较好、Mfinal退化、D0成本否决/D1未运行及所有旧FAIL/UNKNOWN/费用不改。新清单与旧数值原件等价UNKNOWN；本次经验组件PASS不覆盖全域误差、全场或NN。交付清场后停止等待审阅；下方全部历史原文保留，旧“当前”不授新运行预算。

# 当前：Review V26 → Response V27，唯一R真实生成但原字节重现失败

修复pin前允许范围与内层新样本选择、Git/blob封存和marker-last事务，39项定向逻辑资格通过。已实际完成一次原生模式生成；文件比原要求多18,110B且完整hash不同，所以B0/B1停止。32060名称及物理身份一致不能替代数值原件，未用剩余时间重试候选。

| 固定对象 / measured、failed、not_run | 实际值、门与原因 | 证据 |
| --- | --- | --- |
| 实现/实际R source | 904131e19396c4b6896d42056df2e27387908c1f；数学c354afa、43文件/1,054,179B，启动29依赖 | [run/source](records/run_index_v27.json) |
| P0逻辑资格 | 23新增＋16旧增量＝39pass；旧92A复用；P0完整边界1144.441616s | [测试/全部初始失败](records/targeted_tests_v27.json) |
| R原件重现 / failed | 实际36,263,033B/SHA7dd07d71…；原36,244,923B/SHA52d7ec80…；只生成1次 | [输入原值/hash](records/input_reproduction_v27.json) |
| 部分身份及安全拒绝 | 32060唯一有序key/物理hash一致；inventory hash不符；原数值逐字段差NOT_RETAINED；最终ledger/输入标记未发布 | [独立重算](records/independent_checker_v27.json) |
| 真实R成本 / s、B | 全链81.936506s；同时终端树采样峰437,981,184B，hard2GiB/ownswap0；监督前峰未保留 | [完整账/不双加](records/resource_costs_v27.json) |
| B0/B1/B1checker / not_run | 原重现门失败；q60准确性UNKNOWN；FE action/factor/solve/Gram/NN0 | [Gate](records/gate_decisions_v27.json)、[接入包](records/integration_packet_v27.json) |
| 原完整目标与神经 | 原50×25×140nm、Si17/120nm、λ0.7、decimal2e12B/172800s和原精度门未达成 | FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED |

[Response V27](../response_v27.md)、[专题](w1_input_reproduction_v27.md)、[有限修复](records/repair_log_v27.json)、[分组合并边界](records/selective_merge_manifest_v27.json)、[呈现范围](records/render_check_v27.json)。保留M3600较好、Mfinal退化、D0否决/D1未运行、所有旧FAIL/UNKNOWN和费用；不把COMPLETED运行状态写成科学PASS。交付后清场停止等待审阅，下方全部历史原文逐字保留，其旧“当前”不授新预算。

# 当前：Review V25 §8 → Response V26，R输入接线完成、资源阻塞

新增一次确定性输入恢复入口，要求原文件逐字节相同后才进入q60组件；16项增量fixture、Ruff、compileall通过，已接受92项A按hash复用。实际两次launcher在固定核内层审计拒绝，**原生worker和生成次数0，R/B0/B1及数值checker未运行**。这是部分实现交付，不能称找回原件、q60全模式资格或完整解。

| 固定对象 / 数据身份 | 实际结果、单位与门 | 证据 |
| --- | --- | --- |
| clean实现 / implemented | 9ec41386a0ab8c17ae2447507648ab2b039feeae；原数学c354afa、43文件/1,054,179B | [run/source](records/run_index_v26.json)、[包](records/integration_packet_v26.json) |
| 增量逻辑 / measured fixture | 16/16；最后2.656706s、同时树峰90,886,144B、hard2GiB/ownswap0；不重跑A | [测试](records/targeted_tests_v26.json) |
| 期待原输入 / UNKNOWN | 36,244,923B/SHA52d7ec80…、32060/SHA03c1965c…尚未生成和核验 | [Gate](records/gate_decisions_v26.json) |
| R资源 / controlled refusal | 两次外层有候选、固定核内层拒绝；一次实测重新准入已用尽；失效原分数未保存、归因UNKNOWN | [费用/缺失口径](records/resource_costs_v26.json)、[修复限定](records/repair_log_v26.json) |
| B0/B1/B2 / not_run | native/32060 q60/checker0；B2本包不授权，主线承担；factor/solve/NN0 | [保存收据核对](records/independent_checker_v26.json) |
| 原完整目标与神经 / not_qualified | 原50×25×140nm、Si17/120nm、λ0.7、decimal2e12B整机/172800s未达成；全部原精度门保持 | FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED |

[Response V26](../response_v26.md)、[专题](w1_input_recovery_v26.md)、[分组边界](records/selective_merge_manifest_v26.json)。旧中期较好/Mfinal退化、D0否决/D1未运行、q30/q60负结果、FAIL/UNKNOWN与全部成本均保留；两新页发布6a698306…的标题/全部4表、6图实际目视通过，21.901543s/树峰1,775,185,920B/ownswap0；seal呈现尾段及其他导航页未视觉复验，旧有限范围不扩大。[呈现](records/render_check_v26.json)。本窗数值已关闭，一次交棒后停止；下方全部历史原文保留，旧“当前/下一步”不是新运行授权。

# 当前：Review V24 → Response V25，W1接收包与真实缺项

新入口统一实际输入和固定q60，避免worker/checker读取不同目录或暗用旧积分阶次。实现及49项纯数据/安全测试完成，真实native控制在启动前被CPU资源门拒绝，原manifest/ledger和checkpoint仍缺。**P0整体PARTIAL，P1/P2未运行；没有新q60物理资格、场、全局求解或NN收益。**

| measured / implemented / not_run；固定W1范围 | 本轮结果与口径 | 证据 |
| --- | --- | --- |
| 输入及两类source | 11显式dat，同binding供worker/checker；主线数学19文件/365726B、SHA c354afa449fb80cfb5012e7d2ff66a3e3e64e088 | [包](records/integration_packet_v25.json)、[回执](../response_v25.md) |
| 接入定向资格 | 49/49，含29新增W1＋20既有安全fixture；Ruff/compileall通过；非FE/物理测量 | [测试](records/targeted_tests_v25.json) |
| 最后合格轻树 / s、B | 2.832654745s / 同时树采样峰111972352B，显式2GiB、自身swap0，后代清场 | [完整费用](records/resource_costs_v25.json)；初始默认12GB缺口保留 |
| 原生方向/MPC控制 | NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE；tmux/worker/原生raw未创建 | [Gate](records/gate_decisions_v25.json)、[有限修复](records/repair_log_v25.json) |
| 全32060-key及p4/p6上下恢复 | NOT_RUN_INPUT_UNAVAILABLE / NOT_RUN_P0_P1_PRECONDITIONS；实际原件0、local/global factor和solve0，q60准确性UNKNOWN | [输入](records/input_receipt_v25.json)、[运行](records/run_index_v25.json) |
| 旧主线负结果（发布字段，未重算） | q30/q60最坏5.70590933>1e-10，原H组件4.14930383、作用0.008663089；旧p4恢复通过，旧p6计时异常未运行 | [冻结对照与全部边界](w1_receiver_v25.md)，没有新q60结论 |
| 原完整物理/神经终点 | E/H/curl/六点/复模式/R/T/A/A_volume本轮NOT_RUN；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED | 原50×25×140nm、Si17/120nm、λ0.7/decimal2e12B/172800s和原门未达成 |

本轮数值链关闭，不轮询抢跑或代造原件；P3交付可消费但仍待实际native资格的包。M3600较好、Mfinal退化、D0成本否决/D1未运行及全部旧负结果/UNKNOWN/费用保留，无production/master合并批准。新页仅本地结构检查，实际GitHub视觉NOT_RUN；未改Review V24的原视觉收据复用。[依赖分组](records/selective_merge_manifest_v25.json)、[呈现边界](records/render_check_v25.json)。下方从V24起全部历史原文逐字保留，旧“当前/下一步”不是新预算。

# 当前：用户接续 W0 → Response V24

已完成实际worker、原科学数组、955项独立数值门、4错误负控及1619原件持久读回；数学组件PASS，接收批次PASS_WITH_QUALIFICATIONS。初始nice/IO/终端绑定缺口、两次EMFILE、一次数值前CPU拒绝及全部成本保留。不是完整原尺寸前向解；没有NN净收益。

| measured / derived / not_run，固定W0组件 | 当前值/状态 | 证据 |
| --- | --- | --- |
| 固定模型 | 80hex/p6、λ.7、φ5°、缩比规则80；独立FE52992/内部36000/端口532 | [回执](../response_v24.md)、[专题](w0_receiver_v24.md) |
| 原native/增广制造态 | 1.00025e-15 / FE5.00108e-16、port1.11980e-16，门1e-10 | [955项原门](records/w0_metrics_v24.csv)、[原checker](records/independent_checker_v24.json) |
| 完整作用/恢复、纯代数最大相对差 | 1.50063e-12 / 2.50759e-14，门1e-11/1e-12；错误H/共轭/符号/漏项检出 | [Gate](records/gate_decisions_v24.json) |
| 本机保存/完整读回 | 1619原件/3287字段、625253744B文件、数值625046512B；非跨机/断电资格 | [readback](records/durable_readback_v24.json) |
| 真正数值source | 主线数学d4b6ed6b；初始接收1527e115；最终checker/readback6eb24884，完整SHA/hash独立绑定 | [run index](records/run_index_v24.json) |
| 成本/同时树峰 | worker3363.419s；原父3478.277s/2383208448B；最后checker父203.854s/972025856B；nested不相加，own swap0 | [完整账及流程限定](records/resource_costs_v24.json)、[修复](records/repair_log_v24.json) |
| W1/W2 / 原终点 | 冻结32060原件本机缺失 / dot C1c待闭合；原50×25×140nm/λ.7完整3D、decimal2e12B/172800s仍NOT_QUALIFIED，E/H/R/T/A NOT_RUN | [接入条件](records/next_input_and_handoff_v24.json) |
| 神经/旧证据 | FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT；M3600较好/Mfinal退化、D0否决/D1未运行、全部失败/UNKNOWN及费用保持 | 下方V23及全部历史原文完整保留，无production/master合并批准 |

下方是历史原文；其中“当前/下一步”不是新预算或自动启动许可。

## 当前：Review V22 → Response V23（入口拒绝、可消费局部积分及q60出口）

宽面片的波动积分需要足够精度，本轮已将现有解析矩接为接收方[0,1]接口，并实际运行固定p4/p6局部消费及独立原分母核验。两方案都够准，但解析未带来20%完整成本优势，**推荐已有可靠q60，结束额外解析优化**。没有新场或NN收益；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED不变。

| 本轮局部实物 / measured | 解析 | q60 / 当前判断 |
| --- | --- | --- |
| 单位区间矩最大绝对差 | 3.554448e-16 | 9.082805e-14，均≤1e-12 |
| 逐case/方向最大原分母相对差 | 1.657198e-13 | 1.976754e-11，均≤1e-10 |
| 完整冷进程s / 同时树峰B | 64.46515 / 175190016 | 64.61506 / 114491392；仅0.232%时间改善，解析RSS增加53.016% |
| P0实际入口 | 旧E3/E4负场可读，严格角色false | oracle/实际投影FAIL及仿射标量UNKNOWN都拒绝，所有新Maxwell因子/solve/Gram/NN=0 |
| 原尺寸与历史 | 1213一维频率、两p各24局部case | 不是32060全模式/目标网格；旧物理投影/有限p/REFERENCE_LIMITED、M3600较好/Mfinal退化、D0成本否决/D1未运行保留 |
| 预算/资源/测试 | 全批14400s，末段1800s；已测树峰179499008B、swap/OOC0 | 原ABI/MPI1/单核线程1及系统/384GiB邻预留；47最终fixture/独立数组通过，早期失败/NOT_RETAINED不改 |

入口：[Response V23](../response_v23.md)、[单个专题](portable_facet_component_v23.md)、[可消费包](../../../benchmarks/cases/portable_interval_facet/README.md)、[完整source/运行](records/run_index_v23.json)、[原数组checker](records/independent_checker_v23.json)、[完整成本](records/resource_costs_v23.json)、[逐case864行](records/local_case_errors_v23.csv)、[六类依赖](records/selective_merge_manifest_v23.json)。完整原50×25×140nm/Si17/120nm、λ0.7三维FE、十进制2e12B整机、172800s和原门仍未达成，无production/merge批准。一次交棒后停止，不重复数值/归档批次。

下方V22及全部历史原文保留；历史“当前/下一步”不是新的授权。

## 当前：Review V21 → Response V22（可靠输出、解析面矩与条件修正）

已实现双分量总场输出和解析面端口，给定存储D/H下的准确算术、面块/作用及空气资格通过；实际原点投影对独立物理积分仍失败，严格角色资格未闭合。两份保存相位场在新算子中超残差门，启动链各执行一次同G0/p/κ修正，保留为研究数据。独立比较结论为 **STRICT_FINITE_P_FIELD_MODE_FAIL / REFERENCE_LIMITED**。没有NN训练或有效NN净增益，也没有合格O6参考或原尺寸解。

| 当前范围 | 实际完成 | 限定/准确缺项 |
| --- | --- | --- |
| P0/P1总场hi/lo | 三旧c不改；给定存储D/H下恢复约1e-16，消费者读取两部分 | 独立物理原点投影仍FAIL；旧single-array三FAIL/终端舍入保留 |
| P2解析面矩 | p3/p4/p6、ky/方向/双边/截止/真实空气36模式与独立oracle通过 | p6仅小组件，不恢复O6；旧q15失败保留 |
| P3固定原场 | E3/E4新native .004417604/.000275503均超1e-6；先保存全模式/一致RHS/交叉项 | O3控制新native .012671仍不重求；旧体积分按hash复用 |
| 两次条件触发修正+独立比较 | 同G0/原p/κ研究状态，独立q15/30公共全场、6点、340×4模式/功率/区域 | 实际物理投影前置缺口保留；STRICT_FINITE_P_FIELD_MODE_FAIL，无严格O6仍REFERENCE_LIMITED |
| P4原尺寸接口 | 交可复用函数/布局/source/ABI及已有真实小组件证据 | 冻结32060-key本体缺失，完整key oracle/20%局部成本收益NOT_RUN/UNKNOWN |
| 目标/神经/生产 | FULL_TARGET_NOT_QUALIFIED / NO_VERIFIED_NN_INCREMENT；NN/ML/Gram=0 | FEINN与固定单载波缩减仍暂停；D0成本否决/D1未运行 |

| 新状态 / MPC后全独立复FE | native | 增广 | total增广 | 独立total弱式 | 给定D/H下total恢复 | MPC最大 |
| --- | --- | --- | --- | --- | --- | --- |
| E3 / 27648 | 6.291569235e-11 | 6.291464121e-11 | 4.383374959e-12 | 5.458992036e-12 | 9.677671955e-17 | 0 |
| E4 / 65280 | 2.961389644e-10 | 2.961391913e-10 | 2.158049324e-11 | 2.654925696e-11 | 3.885370552e-17 | 0 |


| 独立比较 | total E / scaled-curl相对差 | scattered E / scaled-curl相对差 | 最大功率 / 逐级绝对差 | 用途 |
| --- | --- | --- | --- | --- |
| old_E3_vs_new_E3 | 6.383912525e-07 / 7.470548197e-07 | 4.445757218e-06 / 5.202561137e-06 | 5.402123193e-10 / 1.100722402e-09 | 同角色旧→新控制，无精度权威 |
| old_E4_vs_new_E4 | 1.03254663e-08 / 2.80014132e-08 | 7.190845069e-08 / 1.950096489e-07 | 5.290851091e-12 / 6.434049798e-12 | 同角色旧→新控制，无精度权威 |
| new_E3_vs_new_E4 | 0.000448141158 / 0.0004497335664 | 0.003120937634 / 0.003132069951 | 7.337027094e-07 / 7.337027094e-07 | 修正算子有限p |


全尺寸目标与精度门不变，原single-array FAIL、普通p6 q15/q30=4.275671921747731e-7 >1e-8、旧M3600中期较好/Mfinal退化、全部失败/UNKNOWN及失联3284s保留。D0成本否决，D1未运行。 新[回执](../response_v22.md)、[专题](reliable_affine_ports_v22.md)、[Gate](records/gate_decisions_v22.json)、[运行](records/run_index_v22.json)、[checker](records/independent_checker_v22.json)、[全部资源](records/resource_costs_v22.json)、[原尺寸最小包](records/minimal_integration_v22.json)。下面历史正文完整保留，不把历史“下一步”当新增授权。

## 当前：Review V20 → Response V21（相位FE端口恢复与有限p收口）

| 当前范围 | 已完成 | 明确边界/未运行 |
| --- | --- | --- |
| 准确原点端口与拓扑迹 | 保存p3系数不变、O3R/E3R新α、三α保留；真实空气双向通量/36模式与18组面迹先验完成 | total rounded再回代仍未闭合；普通p6 q15/30=4.27567e-7 >1e-8，完整联合FAIL |
| 唯一相位p4 | G0/336hex、65280独立复FE/340端口；native7.79224e-10、能量1.53932e-12 | 候选方程及scattered约束合格；全部total恢复/严格参考证书不成立 |
| 独立物理比较 | E3R↔E4与O3R↔E3R，q15/30公共2112子单元、E/H/curl、6点、全部340×4通道和6区域 | 散射E/curl差0.00312405/0.00313518、最坏复模式约167，有限p FAIL；O6未准入，无同精度20%收益 |
| 原尺寸及NN | REFERENCE_LIMITED / FULL_TARGET_NOT_QUALIFIED；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT | 不选原尺寸胜者，不训练、不新增p/κ/h/端口；D0成本否决/D1未运行 |

三份新保存状态均为缩小7/135几何、λ0.7nm、G0/336hex、340端口，非原尺寸；p3保留旧完整系数字节。下表功率只是离散诊断：总场原点恢复尚未闭合，不能授予严格解资格。P2的211.602641s/690110464B为两个p3角色共享进程总费用，未人为均分；E4为独立完整求解进程。

| 新状态 | p / 全独立复FE | native原残差 | R / T | A_volume | 完整父阶段s / 同时树RSS峰B | 严格结论 |
| --- | --- | ---: | --- | ---: | --- | --- |
| O3R普通p3 | 3 / 27648 | 9.92770427e-12 | 0.999974256 / 1.66195796e-5 | 9.12422670e-6 | 共享P2 211.602641 / 690110464 | total原点恢复3.14135e-7 >1e-10，不合格 |
| E3R相位p3 | 3 / 27648 | 9.97105087e-11 | 0.0761265836 / 0.905766809 | 0.0181066076 | 共享P2 211.602641 / 690110464 | total原点恢复1.58808e-5 >1e-10，不合格 |
| E4相位p4 | 4 / 65280 | 7.79223689e-10 | 0.0761271395 / 0.905766879 | 0.0181059814 | 363.543991 / 2179440640 | total原点恢复4.28610e-4 >1e-10；有限p散射场/复模式FAIL |
| O6普通GX560 p6 | 6 / 365760（V20保存包已测） | NOT_RUN | NOT_RUN | NOT_RUN | 本批solve/factor=0；小资格成本已计P1 | 小fixture q15/30端口作用4.27567e-7 >1e-8，未准入 |

新[Response V21](../response_v21.md)、[专题](phase_port_recovery_v21.md)、[Gate](records/gate_decisions_v21.json)、[运行](records/run_index_v21.json)、[checker](records/independent_checker_v21.json)、[完整费用](records/resource_costs_v21.json)、[原尺寸差距](records/target_cost_gap_v21.json)。下方所有历史完整保留，V20原恢复FAIL不追改。

# 当前：Review V19 → V20 相位适配FE整批结果

本轮是实际FE新空间研究，旧NN训练仍暂停。已完成A资格、普通/相位p3实际求解、唯一p6参考尝试、保存物理全场及独立C/D。**原恢复超门、合格参考缺失，表示收益UNKNOWN；没有有效解或NN净收益。** 下方V1–V19历史完整保留，其旧“下一步”不构成新授权。

| measured / derived / not_run | 当前值与判断 | 证据 |
| --- | --- | --- |
| 新空间gVh，λ0.7 / G0 | 全3D curl修正、340端口和完整内部；A20原门及独立空气物理通量通过 | [回执](../response_v20.md)、[资格](records/qualification_v20.json) |
| O3 / E3全场 | native9.93e-12 / 8.54e-11；原恢复2.42e-4 / 1.56e-3 >1e-10，FAIL | [原字段](records/physical_comparison_v20.json) |
| O6 / 条件E4 | p6 packet365760 FE保存，内部B/D各2264非零项，因子前拒绝；p4未准入 | [独立checker](records/independent_checker_v20.json)、[Gate](records/gate_decisions_v20.json) |
| C物理差 / 分母E3非参考 | total E差1.00526、scat E差6.85671；q15/30漂移3.39e-12；能量闭合好不等于精度 | [专题](phase_adapted_fe_v20.md)、[全通道](records/channels_v20.csv)、[区域](records/regions_v20.csv) |
| 费用 / 资源 | B4生命周期/两正式修复；O6 1752.71s/C1380.81s；数值同时树采样峰4929130496B，swap0 | [成本](records/resource_costs_v20.json)、[测试](records/targeted_tests_v20.json)、[运行](records/run_index_v20.json) |
| 原尺寸 / 神经线 | 50×25×140nm、λ0.7、2e12B整机、172800s完整3D NOT_RUN/NOT_QUALIFIED；NN NOT_TESTED，旧主解/生产初值暂停 | [一页后续准入](phase_adapted_fe_v20.md#5-原尺寸后续准入判断)；无production/merge授权 |

主线冻结最新b5f85c59已完成Gx784，其自身1%场配对6.42e-4不是本支1e-4证书；dot5be1210a小合成包不是FE/C1/完整存储资格。本支几何仍绑定2374d0d，不复制两线工作。旧M3600较好中期、Mfinal退化、D0成本否决/D1未运行、所有失败/UNKNOWN和旧费用不改。

# Task42extra Review V18 后续：V19 当前停止导航

**当前M5局部优化循环结束**：FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED。本轮只落实审阅结论和证据引用，没有新场、数值作用或训练；历史章节中的下一步建议不是当前授权。[Review V18](../review_report_v18.md)、[一次交接回执](../response_v19.md)、[P0收据](records/closeout_receipt_v19.json)。

| 当前对象 / 数据身份与分母 | 已接受结论及停止边界 | 证据 |
| --- | --- | --- |
| A，derived固定PDE8/原半径 | 两态线性N/F改善、R约1；最优界宽3.891e-6/1.608e-7超过1e-7，UNKNOWN，不收窄或重跑 | [原A](records/native_constraint_results_v18.json)、[审阅](records/review_v18_evidence_audit.json) |
| B，measured原q15保存积分 | 旧退化E/curl正交叉项占增量76.91%/76.81%；宽重叠邻层平均集中度约1，不排除薄层/个别模式 | [原积分](records/saved_integral_results_v18.json)、[固定区域](records/fixed_regions_v18.csv) |
| C，measured实际原网络 | native约0.883116/0.838398，仍远高于1e-6；R−1为1.007948258e-7/1.790179320e-7，超过1e-8，均FAIL | [原C](records/network_witness_results_v18.json)、[原Gate](records/gate_decisions_v18.json) |
| 审阅差量，derived保存向量 | 实际网络相对线性场的额外G改善仅占实际总改善0.07695%/0.42375%；主要改善来自线性选向，不是完整成本NN净收益 | [审阅收据](records/review_v18_evidence_audit.json)，原数值source不变 |
| 流程与历史 | 科研证据ACCEPTED_WITH_PROCESS_QUALIFICATIONS；旧修复次数/再准入对应限定、未测尾段、失联3284s及所有失败保留 | [原修复](records/repair_log_v18.json)、[原成本](records/resource_costs_v18.json)、[原Response](../response_v18.md) |
| D0 / D1及checker限制 | COST_VETO / NOT_RUN_COST_VETO；原四半径已独立核实；checker自身半径/来源绑定尚有限制，无复用需求不修改 | [D0成本](records/auxiliary_cost_v12.json)、[审阅限定](../review_report_v18.md) |
| P0，文档交接 / 条件P1 | ≤3600s pure2GiB/单核线程1/自身swap0、最后预留600s；只同步状态和总账；P1无真实接收包：NOT_REQUESTED_NO_RUN | [新检查/费用](records/closeout_receipt_v19.json)，不重复V17静态清单 |
| 新检查的实测边界 | pure身份/hash通过，3.00520s、57,675,776B树峰、swap0；改变页parser及视觉为NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE，worker前两次CPU拒绝/一次有新窗口的再准入，之后停止 | [本批收据](records/closeout_receipt_v19.json)；不标文档Gate全PASS |
| 原尺寸目标 / P2 | 原50×25×140nm、λ0.7nm完整三维FE、十进制2e12B整机、172800s及原精度门未资格化。P2是新机制/严格无标签同成本/≥20%净收益的重启条件，非数值许可 | [Review V18 §6](../review_report_v18.md)；无production或master合并授权 |

旧M3600散射E/curl约0.0933003/0.0935415，Mfinal约0.122945/0.123039，中期较好态与最终退化均保留。Review V18最终公式实际渲染及两张原区域表右侧补检按hash-bound审阅收据复用，原失败/部分视图记录不改。完整旧summary正文在下方原样保留；本次不是新的科学试验或通用表达能力上界。

并行状态仅引用审阅冻结信息：主线2374d0d556aed7a415202757daa2b94b76ad399b控制链补检通过，Gx784正式执行未开始；dot3c7458fad7c002babac4e634be4788b664be9ee5合成分块投影已测，真实FE/存储/后端待其资格。FEINN不复制或修改两线工作；释放计算配额，整批一次通知后停止，不再半步、留余量、调权或长训练。

# Task42extra Review V17 后续：V18 当前诊断导航

A/B/C及独立检查完成，无训练或新参考。实际网络原残差和G场误差略改善，但原对偶能量不增门两态均失败；主求解器及生产初值继续暂停：FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT。N/R/F为相对各态旧场的能量比，不能等同完整解精度。

| 工作包 / M5-p3身份及单位 | 实际完成、结果和边界 | 证据 |
| --- | --- | --- |
| A，derived固定PDE8/原半径 | 四配置、先无标签冻结再评分；rank8/两rcond步差0；N≈0.993834/0.980847，F≈0.996040/0.998407，R≈1；两态C准入，最优性界宽均UNKNOWN | [原数组/证书](records/native_constraint_results_v18.json)、[14行对照](records/native_constraint_comparison_v18.csv) |
| B，measured保存场积分 | E能量0.211141→0.366628；正交叉项0.119581占增量约76.91%；curl同向退化。周期/界面邻层浓集约1，缺口约1.3 | [完整归因](native_constraint_and_field_attribution_v18.md)、[8行区域原量](records/fixed_regions_v18.csv) |
| C，measured实际网络 | native 0.885852→0.883116、0.846542→0.838398；F≈0.996037/0.998401；R增量1.01e-7/1.79e-7超过1e-8门，两态FAIL；theta/buffers已恢复 | [C原记录](records/network_witness_results_v18.json)、[Gate](records/gate_decisions_v18.json) |
| 独立检查 / 真实用途 | B区域/分母/G配对、C向量、独立FE编号/MPC均完成；MPC≤1.54e-18，Gsolve真残差≤1.03e-13；真实性通过不等于解通过 | [checker](records/independent_checker_v18.json)、[回执](../response_v18.md) |
| 故障 / 全费用保留 | 首C写出协议失败，唯一修复重放完成；含失败前向≤8/A≤14/Gsolve≤8/Gmat≤20/Gram≤2，AH/JVP/VJP0 | [修复账](records/repair_log_v18.json)、[完整父墙钟及嵌套费用](records/resource_costs_v18.json) |
| Source / 同时资源 | A33fe1bc0、Bb42f0420、C及检查/恢复ca7ad5d5，完整SHA见索引；数值树sampled峰1,260,847,104B、自身swap0；Gram全部计费 | [身份](records/run_index_v18.json)、[六依赖组](records/selective_merge_manifest_v18.json) |
| 未验证 / 下一步 / merge | 原有效解仍失败，D0成本否决/D1未运行；新C无完整E/H/通道/功率资格。原尺寸0.7nm、十进制2TB/172800s未资格化；不自动缩步/训练/累积迭代，无production或master合并授权 | 暂停等待新review；局部改善不算≥20%同精度完整成本NN净增益 |

下方所有V1–V17历史、M3600较好中期和Mfinal退化、旧V15/V16失败/UNKNOWN、旧积分NOT_RUN、失联/PSI/重放及未测尾段原样保留。主线d24c97ae的Review V6已条件授权Gx784，但没有本次新结果；dot eb5b0ecc的新C1仍待真实FE/持久资格。本支不复制两线工作。原1e-6残差、1e-4场/通道、1e-5功率/能量、1e-6逐级功率及求积门不变。

# Task42extra Review V16 后续：V17 暂停交接导航

数值探索暂停：FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT，无主求解器或生产初值资格，D0成本否决/D1未运行。本轮只完成轻量交接与静态依赖闭环，没有新场或优化。下方所有V1–V16历史正文、M3600较好中期/Mfinal最终退化、UNKNOWN、失败与全部费用原样保留；历史“下一步建议”不是当前运行授权。

| 本轮对象 / 数据身份 | 实际完成及边界 | 证据 |
| --- | --- | --- |
| P0-A，文档交接 | 当前README/summary指向Review V16与Response V17，完成即暂停 | [回执](../response_v17.md)、[交接/完整费用](records/handoff_receipt_v17.json) |
| P0-B，静态源码文本 | 28模块import/包初始化/关键check调用依赖；六类组完整；研究工具尚未选定迁移 | [准确依赖manifest](records/diagnostic_dependencies_v17.json)，原数值/代码未改 |
| 条件P1，not_run | 无接收方及输入合同：NOT_REQUESTED_NO_RUN；不创造消费者 | 只允许后续review授权，不启动辅助初始化 |
| 已验收数值，复用 | 原8配置/32点/4候选；M3600四项界宽UNKNOWN、两态无标签NOT_ADMITTED；方向native冲突 | [Review V16](../review_report_v16.md)、[原checker](records/independent_checker_v16.json) |
| 主线/dot，冻结审阅信息 | Gx784 FE前工程失败、AUTO32060库存不是成功解；dot新C1待实际资格 | 主线再次运行须其独立review；本支不迁移代码/重复存储验证 |

原尺寸λ0.7nm完整三维FE、十进制2TB整机和172800s完整流程及全部原精度门未资格化；未来重启需新具体无标签机制、区分解释的保存数据、同成本非NN对照及完整资源/失败出口。旧Review V14暂停及V15–V16受控诊断重开记录都保留。无merge approval，不自动追加实验。

# Task42extra Review V15 后续：V16 当前验收导航

原V15保存数组完整验收闭环，暂停FEINN数值探索。只有新checker/保存方向归因，没有新网络场、训练、FE或投影优化；下方所有中期改善、最终退化、失败、未知和未运行历史保留。

| 本轮量 / derived、同M5-p3 | 实际值与独立状态 | 证据 |
| --- | --- | --- |
| 完整批次 / 用途 | 8唯一配置、32点、4候选及实际冻结账本闭环；记录COMPLETE，不是PDE成功 | [Response V16](../response_v16.md)、[checker/五层Gate](records/independent_checker_v16.json) |
| 共同下降 / 界宽 | 有限阈值6排除/2参考oracle可行；M3600四配置界宽UNKNOWN，Mfinal四配置PASS | [专题](checker_integrity_v16.md)，保留原1e-8门与margin |
| 两态无标签候选 | 双能量0.1%与native不增仍未通过：NOT_ADMITTED | [原四候选hash](records/run_index_v16.json)，无下一步非线性见证 |
| native方向归因 | b_N=0.00519171722/0.00198117265，c_N≥0，DIRECTION_NATIVE_CONFLICT | [两行三范数系数](records/native_direction_attribution_v16.csv)，仅既有线性方向；不缩步重试 |
| 测试/源码/资源 | 最终75 affected / 143相关pure、Ruff/compileall通过；checker源码a14dd6187336c866f0a327760f10c4ece0140a8d，旧数值99f2968不变 | [测试](records/targeted_tests_v16.json)、[完整成本](records/resource_costs_v16.json) |

FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT；D0成本否决/D1未运行不变。原0.7nm完整三维FE、十进制2TB/172800s目标与精度门未资格化；不承接主线Gx784/AUTO或dot C1/storage，不混入coarse_inverse/NN-V3。V15历史两次修复为数值1次+浏览器1次，旧失败不追改。本轮只推本支后等review，不合并master。

# Task42extra Review V14 后续：V15 当前数组诊断导航

本轮A–D保存数组诊断已完成，训练和PDE求解仍暂停：`FEINN_MAIN_SOLVER_ON_HOLD` / `NO_VERIFIED_NN_INCREMENT`。只用已保存方向问两项能量能否在固定小步内一起降低0.1%；新值均为DERIVED_LOCAL_LINEAR_MODEL，不是真实网络场。

| 当前结果 / 同M5-p3 | 实际值与边界 | 入口 |
| --- | --- | --- |
| PDE8无标签候选，M3600/Mfinal | F约0.996151/0.997526；R约0.999783/0.999588，未达两项≥0.1%，native预测均增加 | [专题](common_descent_v15.md)、[权限/hash](records/candidate_permissions_v15.json) |
| ALL16参考oracle | Mfinal共同F/R约0.996437可行；M3600 U约0.999312未达0.999；不算NN收益 | [四行主表/32点对照](records/common_descent_comparison_v15.csv)、[原小矩阵](records/common_descent_results_v15.json) |
| 数值界资格 | M3600含保守余量界宽约1.5e-7未达1e-8：UNKNOWN；Mfinal达到目标；不凑PASS | [原数组checker](records/independent_checker_v15.json)、[Gate](records/gate_decisions_v15.json) |
| 身份、测试与费用 | 新source99f2968be8d715a6f2e6985f5b032c53ca505950；87 targeted/Ruff/compileall通过，1局部修复；新FE/前向/训练/factor均0 | [Response V15](../response_v15.md)、[run index](records/run_index_v15.json)、[资源全账](records/resource_costs_v15.json) |

两档rcond结论一致；两态无标签稳定正信号条件不成立，不提出新的非线性见证。D0成本否决/D1未运行、M3600中期改善与最终退化、所有历史失败/未知/未运行、原严格精度和0.7nm/十进制2TB/172800s目标保留。主线Gx/Gz四角已完成；dot实际FE资格仍未完成，本支不重复两线工作。无生产或master合并授权，完成后等待review。

# Task42extra Review V13 后续：V14 归档停止导航

仅完成P0文档交接，维持 `FEINN_MAIN_SOLVER_ON_HOLD` / `NO_VERIFIED_NN_INCREMENT`，没有新数值任务或模型结果。下方V1–V13全部原值、M3600中间改善和最终退化、失败、未知与未运行项保留。

| 本轮范围 / 数据身份 | 实际处理与边界 | 入口 |
| --- | --- | --- |
| 文档入口，非新PDE实测 | README当前状态改为暂停，首次空目录/E0–E5标为已完成历史；原精度门与最终0.7nm/十进制2TB/172800s目标不变 | [README](../README.md)、[Response V14](../response_v14.md) |
| 既有数值与成本，复用 | 无合格无标签解/NN增量；D0已否决、D1未运行；不重跑背景、保存场、73项数值测试或完成器 | [Review V13](../review_report_v13.md)、[run index](records/run_index_v13.json)、[manifest](records/selective_merge_manifest_v13.json) |
| 最终公式资格，复用而不追改历史 | 审阅已通过未变专题最终字节的parser和实际GitHub目视；旧失败/资源未复验记录保留 | [审阅收据](records/review_v13_evidence_audit.json)、[旧失败](records/render_check_v13.json) |
| 本次文档检查与可访问性 | 只查改变页面与最小证据入口，结果、预算和未验证项分列；本地可读不等于跨机恢复资格 | [归档收据](records/archive_receipt_v14.json) |

暂停后只在Review V13 P2的新假设、无标签干预、保存数据预检、同成本非NN对照、完整成本和原精度/停止计划全部具备时提出重启，不自动执行。task40extra/dot继续各自精度与fresh C1/持久证据工作，本支不复制。无production或master合并授权。

# Task42extra Review V12 后续：V13 当前收口导航

A原向量分类、八个见证范数复用、D0/D1状态纠正及唯一B背景转换已完成；停止FEINN数值探索。没有训练、网络前向、新G/factor/reference或传统求解器复制。同 p3 NN 求解失败、有限已测局部方向的目标分歧成立、网络全局表达极限未知，三者分开。原 native/增广门1e-6、场/复通道1e-4、功率/能量1e-5、逐级功率1e-6均不改变。较好中间态M3600、最终退化Mfinal、全部失败/失联/PSI/重放费用与未验证项保留。

| 保存态（沿用 V12/V11，非新求解） | native 原残差 | 散射 E L2 相对误差 | curl/H 相对误差 | E_G | 原 Riesz loss |
| --- | --- | --- | --- | --- | --- |
| M3600 | 0.885852183253 | 0.0933002764708 | 0.0935415151962 | 0.0935355798945 | 0.094314671576 |
| Mfinal | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0872060784095 |

上表为同M5/p3、5nm/384hex/31968独立复FE/40端口的旧measured证据，均无量纲、越低越好；仍未过原1e-6残差与1e-4场门。下方所有历史原样保留，包含较好中间态与最终退化。

| V13项目 | measured / derived结果 | 边界 / 证据 |
| --- | --- | --- |
| 保存向量C1分类 | 两态LOCAL_OBJECTIVE_DIRECTION_MISMATCH；所有交叉字段重算 | [checker](records/independent_checker_v13.json)，不是全参数/全局表达上界 |
| 八个既有试探 | 三种范数分开；对偶最大5.003%，原前向不重复 | [全8行](evidence_closure_v13.md)、[hash核验复用](records/witness_norm_reuse_v13.json) |
| 背景同总场修正 | p3参考3.55236349556→5.20557219228；M3600 3.91639216676→5.03123428018；Mfinal 4.04010800106→4.89083794134 | 原f4分母不改，不支持消除大基线；[原向量/交叉项](records/background_conversion_v13.json) |
| 共享背景差的误差像 | 两候选.325782556578/.330392025659不变，defect≤1.82e-17 | 与同p3失败分开，不称G4/连续收敛 |
| D0 / D1 | COST_VETO_CONFIRMED / NOT_RUN_COST_VETO | 旧JSON不追改；[新映射](records/status_mapping_v13.json) |
| 正式B资源/操作 | 77.4764841361s，304291840B树峰，swap0；2 A4，其余禁止作用0 | [完整新增及历史账](records/resource_costs_v13.json)，自身已清场 |
| 测试 / 渲染 / 合并 | 73定向通过；首次8页26表parser通过，回执目视通过、专题公式失败；宏修正后复查资源未运行；无production晋级 | [测试](records/targeted_tests_v13.json)、[渲染](records/render_check_v13.json)、[六组清单](records/selective_merge_manifest_v13.json) |

[Response V13](../response_v13.md)、[专题与完整8见证表](evidence_closure_v13.md)、[source/index](records/run_index_v13.json)、[Gate](records/gate_decisions_v13.json)。新邻层/交叉FE积分仍NOT_RUN，历史optimizer/RNG仍NOT_RETAINED。原尺寸0.7nm/十进制2TB/48h完整流程未资格化，原精度门不放宽。无NN净增益，暂停并等review；不合并master。

# Task42extra Review V11 后续：V12 当前结果导航

本轮停止神经主求解器晋级：`FEINN_MAIN_SOLVER_ON_HOLD`、`NO_VERIFIED_NN_INCREMENT`。没有新训练、监督拟合、权重/尺度扫描、传统求解器复制或参考重求。已冻结18个指定保存场，重算退化段，完成两态局部参数诊断；所有前向见证立即恢复原参数。中间改善、最终退化与未运行项均保留。参考场只在标记为 `REFERENCE_EXPOSED_DIAGNOSTIC_ONLY` 的分析中使用，未形成新PDE-only候选。

| 保存态 | native原残差 | 散射E L2 | 散射curl/H | E_G | 原Riesz对偶loss |
| --- | --- | --- | --- | --- | --- |
| phase75 | 0.978821198632 | 0.362017880269 | 0.362633734179 | 0.36261857554 | 0.23467076194 |
| M3600 | 0.885852183253 | 0.0933002764708 | 0.0935415151962 | 0.0935355798945 | 0.094314671576 |
| Mfinal | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0872060784095 |
| Ifinal | 0.984363547288 | 0.15960198092 | 0.160305545482 | 0.160288250677 | 0.153600031731 |
| V10phasefit | 0.53147218171 | 0.00955792520676 | 0.0100342087994 | 0.0100227477417 | 0.275158308964 |

M5模型、单位、原Gate和分母沿用下方V11定义；上表均为无量纲误差，数值越小越好。当前原残差仍远高于1e-6、散射场仍远高于1e-4。M3600的改善和Mfinal的退化同时保留，功率只作diagnostic，不构成有效解。

[Response V12](../response_v12.md)、[退化与局部方向](diagnostic_attribution_v12.md)、[辅助成本否决](auxiliary_role_decision_v12.md)、[Gate](records/gate_decisions_v12.json)、[完整费用](records/resource_costs_v12.json)、[source/hash](records/run_index_v12.json)。新E/curl交叉/固定邻层积分为资源未运行；p4见证状态`EXISTING_P4_TEST_SPACE_WITNESS_COMPLETE`。V1–V11历史及失联/PSI/重放全部保留。

# Task42extra Review V10 后续：V11 当前结果导航

A/B及唯一一对C已执行，实际终态已冻结并独立复验。分组度量接口通过，研究分类为`NO_USEFUL_METRIC_GAIN`；严格求解资格按原方程、场及功率分别判定。缓存加速资格保留，不能当作求解收敛。本批无监督D、无新增参考求解。

本轮比较网络权重/偏置的步长尺度。原阻尼对各参数施加同一种步长限制；固定八组度量按方向曲率改变限制，但仍求同一Maxwell方程、使用同一Riesz对偶目标。额外代价是26次公共曲率诊断、资格检查，以及每条独立Gram准备。原残差1表示误差仍相当于原载荷；散射场相对误差0.36表示误差约为参考散射场范数的36%。curl描述场的空间旋转并对应磁场H，E_G综合电场与curl；各指标越低越好，但必须同时通过门限。

| 路线，相对原V1同p3参考 | native | augmented | 散射E L2 | 散射curl/H | E_G | 能量闭合 |
| --- | --- | --- | --- | --- | --- | --- |
| V10-PHASE-CACHED-GN-CONTINUE | 0.978821198632 | 0.978821198632 | 0.362017880269 | 0.362633734179 | 0.36261857554 | 0.0927477482932 |
| V11-PHASE-IDENTITY-METRIC-CONTROL | 0.984363547288 | 0.984363547288 | 0.15960198092 | 0.160305545482 | 0.160288250677 | 0.0293262887055 |
| V11-PHASE-BLOCK-METRIC | 0.846541904928 | 0.846541904928 | 0.122944519716 | 0.123039105854 | 0.123036776653 | 0.0492282322929 |

| 路线 | 新增接受 | K | JVP | VJP | 真实试探 | 拒绝 | 完整新增s | 树峰GiB | 停止原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V11-PHASE-IDENTITY-METRIC-CONTROL | 24 | 930 | 930 | 954 | 34 | 10 | 5225.489258 | 2.83142471313 | GRADIENT_START_SAVE_RESERVE |
| V11-PHASE-BLOCK-METRIC | 20 | 991 | 991 | 1012 | 31 | 11 | 5219.37018731 | 2.39972305298 | BUDGET_FRONTIER_CG_RESERVE |

[Response V11](../response_v11.md)、[完整度量诊断](parameter_metric_v11.md)、[原字段Gate](records/gate_decisions_v11.json)、[完整资源账](records/resource_costs_v11.json)、[source/模型/hash](records/run_index_v11.json)、[实际渲染](records/render_check_v11.json)。

本批最终保守新增16916.218990236s（上限21600s），项目累计154319.25454593s。GitHub视觉为实际Unicorn服务错误，BLOCKED；本地新页合同通过。自身数值树与锁已清场。

旧V1–V10结果、负结果、两次PSI停止及失联3284s费用全部保留；下方历史正文原样保留。

# Task42extra Review V9 后续：V10 当前结果导航

本轮A–E授权矩阵已执行。完整导数复用与包含建立/释放的加速通过；两条C仍未求准原p3。plain正常预算冻结，phase因两次系统压力停止后保全最后完整状态，停止原因与保存状态的精度分开报告。条件D已独立完成；全部候选功率仅为diagnostic。

原残差接近1表示场还不能满足原方程；相对场误差0.36表示约36%的参考散射范数。散射是相对于已知背景的变化，curl同时衡量磁场误差，E_G综合幅值与curl；越低越好，仍须各项门限同时通过。G/场拟合使用参考标签，其进步不能当无标签求解或官方功率结果。

| 路线，相对原p3参考 | native | augmented | 散射E L2 | 散射curl/H | E_G | 独立能量闭合 | 分类 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V10-PLAIN-CACHED-GN-CONTINUE | 1.0154347975 | 1.0154347975 | 0.99888849996 | 0.99890594486 | 0.99890551512 | 0.41593547468 | PDE_OPTIMIZATION_NEGATIVE |
| V10-PHASE-CACHED-GN-CONTINUE | 0.97882119863 | 0.97882119863 | 0.36201788027 | 0.36263373418 | 0.36261857554 | 0.092747748293 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PLAIN-DAMPED-GN | 1.0285051156 | 1.0285051156 | 0.9989232163 | 0.9989423061 | 0.99894183584 | 0.4157492147 | PDE_OPTIMIZATION_NEGATIVE |
| V9-PHASE-DAMPED-GN | 1.0187461988 | 1.0187461988 | 0.43715907484 | 0.43778332738 | 0.43776795997 | 0.12094192809 | PDE_OPTIMIZATION_NEGATIVE |
| V10-PLAIN-CACHED-FIT-GN-CONTINUE | 6.9238228453 | 6.9238228453 | 0.035964629101 | 0.048041839362 | 0.047781012309 | 0.0074739007987 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V10-PHASE-CACHED-FIT-GN-CONTINUE | 0.53147218171 | 0.53147218171 | 0.0095579252068 | 0.010034208799 | 0.010022747742 | 9.4658158489e-05 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 11.001030573 | 11.001030573 | 0.068217087643 | 0.1000521103 | 0.09939045116 | 0.014917309507 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.8082166866 | 0.8082166866 | 0.014403534682 | 0.013024032447 | 0.013059766413 | 0.0028868109962 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

| 子包 | 实际完成与边界 | 证据 |
|---|---|---|
| A | 四个V9 final身份、原历史/PC/未提交工作聚合；缺项NOT_RETAINED | records/state_identity_v10.json；records/inner_summary_v10.json |
| B | 四态等价、两条完整C proposal逐位一致；含建立/释放加速1.46–1.57倍 | derivative_reuse_v10.md；records/cache_checks_v10.json |
| C | plain新增14接受；phase新增21接受并保全第75完整边界；均无严格/10倍研究资格 | cached_gn_v10.md；records/gate_decisions_v10.json |
| D | 两条各自V9-D final隔离监督续算与完整独立审核 | records/comparison_v10.json；FIT CSV |
| E | q15/q30、原场/通道/功率/区域和独立checker；实际渲染另列 | records/run_index_v10.json；records/render_check_v10.json |

严格原方程1e-6、场/复通道1e-4、功率/独立能量1e-5、逐级功率1e-6未放宽。D的三项表示门限1e-3/1e-2不等于无标签求解或官方功率资格。p5已有准确参考只读复用，p4/p5仍有curl/H敏感性，不称连续/h/端口收敛。

[Response V10](../response_v10.md)、[导数复用](derivative_reuse_v10.md)、[GN续算](cached_gn_v10.md)、[最终资源账](records/resource_costs_v10.json)、[run/source/hash](records/run_index_v10.json)、[原字段Gate](records/gate_decisions_v10.json)。文档HEAD不冒充043资格、902性能、acdd/5cda训练或ca0c导出/独立验算源码。

本轮结束“只靠等价加速再加时间继续原GN”的尝试。唯一下一轮建议是一次有界、无标签的参数尺度与阻尼诊断：在冻结phase C状态记录同一K的方向曲率、mu所占比例及逐层更新尺度，并配对预测/真实下降。依据是C plain内层CG中位68步、真线性残差中位0.00955，phase中位28步/0.00834，但最终原方程仍近1，接受步也可能增加native；内层解得较准不能保证真正的场改善。建议未来授权上限20分钟、32次K和4次真实目标试探，保留120秒保存窗口；本批只写设计、不执行，不新增loss/PC/训练或改参数尺度，不声称已证明条件数是唯一根因。完整矩、原A/f/G和严格物理验收仍是基准。目标尺寸5nm/0.7nm、p6、h和端口扩展不启动。

以下V1–V9历史全部原样保留。

# Task42extra Review V8 后续：V9 当前结果导航

本页首先给出最新状态；下方全部V1–V8历史原样保留，历史V7 p4 blocked不代表现状。V8已完成等价装配、合格p4参考、plain/phase无标签与条件监督对照及实际渲染。V9完整A–E也已执行，停止等待review。

| 包 | 实际完成 / measured结果 | 边界 / 证据 |
|---|---|---|
| A | p5参考合格；唯一新增numeric；p4/p5仍有curl/H敏感性 | p_ladder_v9.md；p5_authority_v9.json |
| B | GN/JVP/实伴随/K/真实C500/batch/事务资格通过 | gn_checks_v9.json；targeted_tests_v9.json |
| C | plain与phase均正常预算冻结；原p3未解合格；GN信号false | pde_comparison_v9.json；inner_solver_history_v9.json |
| D | 条件自动触发；两条独立监督FIT-GN均正常预算冻结；三项1%门限未过 | fit_comparison_v9.json；D权重不反馈C |
| E | 独立q15/q30重建、FE compare-only、原字段checker通过；渲染另列 | gate_decisions_v9.json；run_index_v9.json |

| 路线，原V1同p3评分 | native / augmented | 散射E L2 | 散射curl/H | E_G | 独立能量闭合 | 结论 |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 1.0285051156 / 1.0285051156 | 0.9989232163 | 0.9989423061 | 0.99894183584 | 0.4157492147 | 无标签未合格 |
| V9-PHASE-DAMPED-GN | 1.0187461988 / 1.0187461988 | 0.43715907484 | 0.43778332738 | 0.43776795997 | 0.12094192809 | 无标签未合格 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 11.001030573 / 11.001030573 | 0.068217087643 | 0.1000521103 | 0.09939045116 | 0.014917309507 | 监督表示门限未过 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.8082166866 / 0.8082166866 | 0.014403534682 | 0.013024032447 | 0.013059766413 | 0.0028868109962 | 监督表示门限未过 |

严格 native/augmented/原total≤1e-6，场/复通道≤1e-4，功率/独立能量≤1e-5、逐级功率≤1e-6，均未放宽。D的G/L2/curl三项均≤1e-3/1e-2才是表示正/部分见证；本轮未过。

| 当前导航 | 内容 |
|---|---|
| [Response V9](../response_v9.md) | 身份/实际source/结论/资源/下一步 |
| [p5与p序列](p_ladder_v9.md) | 准确参考、p4/p5具体未过量和释放生命周期 |
| [完整GN结果](damped_gn_v9.md) | 原残差、全场/六点/40复通道/功率/区域、共同时间、Gram与PC |
| [Gate](records/gate_decisions_v9.json) | 从原字段独立重算，严格/研究/表示分别判定 |
| [资源](records/resource_costs_v9.json) | 历史74341.02060587064s+本批真实新增；含全部失败和未提交试探 |
| [run index](records/run_index_v9.json) | 所有14正式attempt与12个完成stage的source/输入/packet/状态hash |
| [渲染](records/render_check_v9.json) | 新Review及关键页实际浏览器状态；不等同结构检查 |
| [目标5nm计划](target_5nm_scale_plan.md) | 历史容量设计保留；目标尺寸/0.7nm仍未运行 |

候选功率均diagnostic，未取得神经增量或production资格。p5只是REFERENCE_ONLY，C/D仍按原p3评分。

下一轮仅建议先资格化等价的分块切线/激活复用：在这四个已冻结状态上做有界 JVP/VJP 配对与计时，保持原矩、参数导数和目标完全不变，再决定是否值得开展同预算 GN 对照。本轮实测 JVP＋VJP 占 C 新段约90%、D约97%–98%，是可定位的主要费用；该建议不授权继续训练、换 loss/PC、扩大模型或放宽门限。

# Task42extra Review V6 后续：V7 p4装配受控停止

本轮完成了同网格 p3→p4 的完整场/旋度嵌入、原算子配对与数组容量资格，但唯一 p4 参考在装配阶段耗尽数值工作窗口，状态 **P4_REFERENCE_TIME_BLOCKED**。没有获得 p4 参考场，因此未启动 p3/p4 比较，不能判断阶次变化大小。已按预算主动请求自有 watchdog 停止，原因明确；这不是 OOM 或 p4 精度失败证据。

提高阶次让同一个单元内的电场能表达更多细节，几何和网格都不变。准确 p3/p4 场的差可检查离散敏感性，不能直接当连续误差上界；代价是更大的有限元系统及一次独立准确参考。原 NN 对同一 p3 方程的失败与这个精度审计是不同问题，旧结论不改。

| 原方程/功率 / measured、原rhs或入射功率归一 | p3原参考 | p4本轮 | 验收 |
| --- | --- | --- | --- |
| native_relative | 6.78883619212e-12 | NOT_RUN | 参考各≤1e-10 |
| augmented_relative | 6.78883897883e-12 | NOT_RUN | 参考各≤1e-10 |
| original_total_augmented_relative | 3.514516446e-12 | NOT_RUN | 参考各≤1e-10 |
| independent_DOLFINx_total_native_relative | 3.26041877377e-12 | NOT_RUN | 参考各≤1e-10 |
| R_total | 0.812426499057 | NOT_RUN | 不能比较 |
| T_total | 0.0324623960953 | NOT_RUN | 不能比较 |
| A_balance | 0.155111104848 | NOT_RUN | 不能比较 |
| R00_s | 0.812256818464 | NOT_RUN | 不能比较 |
| R00_p | 1.25634444139e-26 | NOT_RUN | 不能比较 |
| R00_total | 0.812256818464 | NOT_RUN | 不能比较 |
| A_volume | 0.155111104847 | NOT_RUN | 不能比较 |

| 阶段 / measured | 完整launcher wall / s | 同时树RSS峰 / B | CPU | 自身swap峰 / B | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| v7_p_transfer_checks | 158.807494071 | 1586601984 | 12 | 0 | U0资格通过 |
| v7_p4_reference | 3452.53531242 | 1289834496 | 11 | 0 | 预算受控停止 |
| v7_p3_p4_compare | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | p4参考未资格化 |

U0现场核实p4含slave78936、slave3672、独立复FE75264（边4992/面28800/内部41472）、40端口，完整矩/非零公共点E/curl/MPC及原action≤1e-10；M5/5nm/384hex/h1.25/体与DtN q15相同，仅p3→p4。数组/转换12GiB规划通过，symbolic/factor容量未完成，不作PASS。

没有p4恢复packet、没有U2或q30差值复核，全部p场/功率/通道/原区域差NOT_RUN，不宣称连续/h/端口收敛。旧e4_p4 not_run、V1–V6所有NN失败和标签血缘保持。新p4仅REFERENCE_ONLY，训练/生产/神经资格仍false。

launcher在 3450.00074385s 到达原3600s的150s收口边界时，由Codex按用户预算请求停止。先核对自有PID/start_ticks和one-run命令，再只向launcher发SIGTERM，由既有watchdog终止/回收自身后代。原分类USER_CONTROLLED_STOP、worker exit−15，descendants_cleared=true；完整退出wall 3452.53531242s，剩余 147.464685061s≥120。本批全部数值阶段树峰 1586601984B（1.47763824463GiB），自身swap0，没有内存硬线、监督失效或OOM证据。

本页冻结前新增全账 3762.8175588s，含正式阶段、全部已完成辅助失败与直接/最终120s保守额度；旧45161.81665198447s及失联3284s/旧Gram/重放费用全部保留。原累计 48924.6342108s，剩 8675.36578922s。浏览器与发布后检查继续补入[最终资源账](records/resource_costs_v7.json)。U0含轻检查181.809311786s≤1200，唯一p4≤3600，新批≤7200/原≤57600均未越线。未取得装配完成timer，写NOT_RETAINED，不重放补计；父wall已包含这段CPU费用，不能重复相加或删除。

C1中断manifest保留p3依赖的provisional operator hash，不能冒充p4；实际输入由U0 hash/冻结依赖与degree4事件核清，原字节不改。C2修正启动前p4身份与长原生调用150s watchdog截止，10项targeted tests通过，未正式重放。[详细审计](p3_p4_authority_v7.md)列明保全与未知因素。

唯一下一步建议：review先决定如何在既定小型authority约束内解除p4装配预算阻塞并冻结比较基准，再决定是否授权[同规模单载波复包络方案](phase_representation_plan_v7.md)的最小完整矩/VJP资格与同预算对照。本批只交计划，不实现训练器、不训练、不自动第二次factor。目标尺寸5nm和0.7nm、p5、h细化、更多端口均未启动；小型p4未完成不能推广为模型不可计算。

[Response V7](../response_v7.md)、[run/source/hash](records/run_index_v7.json)、[U0](records/p_transfer_checks_v7.json)、[p4停止](records/p4_reference_v7.json)、[Gate](records/gate_decisions_v7.json)、[新渲染](records/render_check_v7.json)。实算source 76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2，后来文档HEAD不替代它。以下V1–V6历史原文原样保留。

# Task42extra Review V5 后续：V6 固定特征原方程残差下限

本轮已测得此固定195维特征空间的原方程最小残差，但没有获得物理解资格。V6实际网络 native/augmented 均为 **0.570577990454**，高于严格1e-6；G场误差 **0.569932119000**，散射E L2 **0.569893933222**，scaled-curl/H **0.569933083410**。相比V5，残差降低而场、功率显著变差。分类 `FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED` 只说明线性最小二乘子问题已测完，不表示solver通过或整个网络类不可能。

这一步把已经学到的隐藏特征固定，只重新组合最后一层，使原方程左右两边尽量接近。它回答同一组特征最有利的末层能把原方程残差降到哪里；收益是消除“末层优化还没求好”的不确定性，代价是195次原算子作用、约100MB受限矩阵及稳定分解。隐藏特征曾读过参考场，当前读出只用原载荷f，整条路线仍不是无标签求解。

保持原M5、5nm Si/air、384hex、p3/q15、31968独立复FE（边3744、面14400、内部13824）、2082slave、40端口、材料/背景/MPC/DtN。冻结8576实隐藏参数和坐标buffers，仅改变390实末层参数。复用V5已资格化Phi/Q_eff，不新增列，不重新G-QR；全部内部矩经原网络forward、Piola/orientation/MPC完整生成。

| 同p3参考、无量纲 / measured | V4 final | V5 G最优 | V6残差最优实际网络 | 门限 |
| --- | --- | --- | --- | --- |
| G场误差 | 0.0138716912975 | 0.0115909576376 | 0.569932119 | 三项表示0.001/0.01；物理场各1e-4 |
| 散射E L2 | 0.0132512476647 | 0.0139354062682 | 0.569893933222 | ≤1e-4，V6未过 |
| 散射curl / 完整H_code L2 | 0.0138870027008 | 0.0115255720568 | 0.56993308341 | ≤1e-4，V6未过 |
| total E L2 | 0.00908709789134 | 0.00955626248333 | 0.390807121709 | ≤1e-4，V6未过 |
| total curl / 完整H_code L2 | 0.00949580596642 | 0.00788108119955 | 0.389715051586 | ≤1e-4，V6未过 |
| 六点total复E | 0.00975197801709 | 0.00979563175999 | 0.386657557378 | ≤1e-4，V6未过 |
| 六点total复H | 0.00716738817286 | 0.00774628935817 | 0.383341995305 | ≤1e-4，V6未过 |
| 六点scattered复E | 0.0144133908755 | 0.0144779109614 | 0.571478575904 | ≤1e-4，V6未过 |
| 六点scattered复H | 0.0106715966193 | 0.0115335284392 | 0.570761767393 | ≤1e-4，V6未过 |
| native | 1.60884472011 | 1.97790914967 | 0.570577990454 | ≤1e-6，V6未过 |
| augmented | 1.60884472011 | 1.97790914967 | 0.570577990454 | ≤1e-6，V6未过 |
| 原total augmented | 0.762112577426 | 0.936939047704 | 0.270283798984 | ≤1e-6，V6未过 |
| 独立DOLFINx total | 0.762112577426 | 0.936939047704 | 0.270283798984 | ≤1e-6，V6未过 |

| 入射功率归一 / measured | V4 | V5 | V6 diagnostic |
| --- | --- | --- | --- |
| R | 0.813057790084 | 0.813166677492 | 0.831595684579 |
| T | 0.0327381741782 | 0.0327293240969 | 0.070897304214 |
| A_balance | 0.154204035738 | 0.154103998411 | 0.0975070112071 |
| A_volume | 0.155388025694 | 0.155420108597 | 0.308717201091 |
| R00_s | 0.812608163311 | 0.812222944068 | 0.83153891879 |
| R00_p | 5.02695584979e-05 | 0.000626436218627 | 1.2298159737e-07 |
| R00_total | 0.81265843287 | 0.812849380286 | 0.831539041772 |
| 独立能量闭合绝对差 | 0.00118398995593 | 0.0013161101857 | 0.211210189884 |
| 最大逐级功率差 | 0.000351344847336 | 0.000626436218627 | 0.0385569062796 |

195/195数值秩、经济QR/小R SVD/原网络回写全部合格，但rho0.570578远高于1e-6。G与物理L2/curl加权恒等式差约1.44e-15；相对V5 G最优的勾股缺陷8.44e-15；当前场没有低于V5最佳误差的异常。表示三项均约0.57，高于0.01；严格原方程、场、功率均失败。全40复通道/分母、逐级功率、六点复E/H、材料/界面区域均在[Gate](records/gate_decisions_v6.json)。

| 阶段 / measured | 完整launcher单调wall / s | 监督wall / s | 同时树RSS峰 / B | own swap / B |
| --- | --- | --- | --- | --- |
| v6_operator_readout_checks | 19.5020307989 | 15.379218037 | 967532544 | 0 |
| FEINN-FROZEN-FEATURE-RESIDUAL-READOUT | 48.924852098 | 46.314578537 | 1290457088 | 0 |
| v6_residual_readout_reconstruct | 22.060632084 | 19.683359519 | 536113152 | 0 |
| v6_residual_readout_compare_only | 23.720625111 | 20.4761449989 | 473350144 | 0 |

```text
reference_used_for_training=true
features_reference_exposed=true
readout_rhs_uses_reference=false
pde_only_solve=false
production_initialization_allowed=false
pde_only_solver_qualified=false
official_candidate_results=false
```

这些字段贯穿所有新输入、manifest、PT/NPZ和结果；新状态是parameter-only，没有Adam/L-BFGS历史。权重不得接回旧路线、Task042或0.7nm。准确参考只在冻结后的T2加载；不重新MUMPS求解，没有Gsolve/Gram/Maxwell因子、Krylov或optimizer step。

实际A/A*按列合计206/3，完整native审核4次另列（其中FE含2次独立DOLFINx作用），G合计16列；限值256/8/12/512均未超。新增Gsolve/Gram factor/Maxwell factor/optimizer step均0。原G稀疏payload146851456B、Phi/B各99740160B（数组体积，不是RSS）；旧Gram装配648.765s、历次factor、准确参考和监督特征学习费用保持原账，从零成本不能用本次约49s主阶段代替。

数值树峰1290457088B（约1.20GiB），自身swap采样全0、各阶段完整清场。主阶段完整launcher48.924852s含导入、加载、哈希、A/QR/SVD、存盘和审核；退出剩1751.075s，150s收口和至少120s保存留白通过。组件细分计时未保存，标NOT_RETAINED，不重放补计；父wall完整计费，嵌套/数组payload不重复相加。

本页冻结前V6账约257.8s（含全部已完成辅助及直接/最终120s保守额度）；发布与浏览器费用继续追加[最终资源账](records/resource_costs_v6.json)。旧累计44815.22461795143s和失联/重放成本不删除；本批≤3600s、主阶段≤1800s、T0≤600s及原57600s分别审核。CPU-only、MPI1、数学/Torch1，现场空闲物理核，本批正式CPU12；系统余量216310038528B＋384GiB邻增长＋自身cap，警戒12/硬16GiB，轻测试/浏览器≤2GiB。tmux管理服务器约4.7MB稀疏样本单列，不称连续峰；无cgroup委派，约0.5s树采样监督，不宣称连续内核限额或零干扰。

本轮已排除所测末层布局、两套置换混用、G/物理范数不一致、回写不稳、参考泄漏进读出右端项、q15漂移和最终状态丢失等因素。新残差下限高出1e-6约570578倍，回写原方程分辨差仅2.31e-11；它支持此冻结空间达不到原残差门限的数值结论，不是带区间误差界的数学证书，也不排除改变隐藏参数后的网络。V5 G最优已经不足以让L2/curl同时≤1%，当前读出的约57%场误差不能当有效求解进展。无标签神经增量仍未证明。

**唯一后续设计建议：在原M5上设计包含物理传播相位的隐藏表示，并先冻结其完整矩/原方程验证方案。** 不在本轮实施，不再扫描同一冻结特征的loss或末层超参，不继续hidden训练/VarPro/PDE微调。目标尺寸5nm需另行冻结几何、网格及可扩展求解设计后才可晋级；本轮p4、目标尺寸5nm与0.7nm均not_run。旧V1/V2负结果、V3中断及失联3284s费用不改。

[Response V6](../response_v6.md)、[详细诊断](frozen_feature_residual_v6.md)、[投影](records/residual_readout_projection_v6.json)、[三场CSV](records/residual_readout_comparison_v6.csv)、[run/source/hash](records/run_index_v6.json)、[资源](records/resource_costs_v6.json)、[新渲染](records/render_check_v6.json)。以下V1–V5历史原文保留。

# Task42extra Review V4 后续：V5 固定隐藏层输出诊断

本轮取得了**稳定、实际可回写网络的固定隐藏层投影**，去掉了V4剩余G误差能量的30.180006%，但未获得表示门限或严格物理资格。G场误差 `0.0138716912975` → `0.0115909576376`，散射curl误差下降；散射E L2 `0.0132512476647` → `0.0139354062682`、native `1.60884472011` → `1.97790914967`、复通道和能量闭合反而变差。分类为 `REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED`。固定特征的线性子问题已通过最优性审核；这个分类保留的是整个可变隐藏层网络及PDE求解的未决范围，不表示本轮线性优化又未完成。

本节追加V5，以下V1–V4原文保留。冻结V4 final的8576实隐藏参数与坐标buffers，仅改390实输出层参数；完整边/面/内部矩产生31968复FE，原M5/5nm/384hex/p3/q15/40端口不变。固定特征的线性组合经G-QR＋小R SVD重求一次，没有新增参考生成特征列、Adam/L-BFGS、Gsolve或Gram/Maxwell因子；参考已暴露，只是监督诊断。

| 阶段 / measured | 结果 | 资格边界 |
| --- | --- | --- |
| S0 | 原a0配对3.08e-15；复数/纯虚/bias/三类矩/batch通过；Phi一次14.806s | 不是PDE solver PASS |
| S1唯一投影 | rank195/195，G正交2.32e-13，实际网络最优性1.39e-13，gamma0.301800 | 此固定数值可辨子空间；不推广整个网络类 |
| S2独立ML/FE | 参数→c差0；q30差7.89e-13；新MUMPS0 | 仅复用V1同p3参考 |
| 表示/物理 | 三项未均≤0.01，严格方程/场/功率均失败 | G和curl改善，散射L2/native/通道/能量变差 |
| p4/目标尺寸5nm/0.7nm | not_run | 没有放大或合并授权 |

| 同p3参考 / measured、无量纲 | V4 final | V5实际网络c1 | 门限 |
| --- | ---: | ---: | --- |
| G场误差 | 0.0138716912975 | 0.0115909576376 | 表示正/部分要求三项均≤0.001/0.01，未通过 |
| 散射E L2 | 0.0132512476647 | 0.0139354062682 | 严格≤1e-4，未通过 |
| 散射scaled-curl / 完整H_code L2 | 0.0138870027008 | 0.0115255720568 | 严格≤1e-4，未通过 |
| total E L2 | 0.00908709789134 | 0.00955626248333 | 严格≤1e-4，未通过 |
| total scaled-curl / 完整H_code L2 | 0.00949580596642 | 0.00788108119955 | 严格≤1e-4，未通过 |
| 六点total复E | 0.00975197801709 | 0.00979563175999 | 严格≤1e-4，未通过 |
| 六点total复H_code | 0.00716738817286 | 0.00774628935817 | 严格≤1e-4，未通过 |
| 六点scattered复E | 0.0144133908755 | 0.0144779109614 | 严格≤1e-4，未通过 |
| 六点scattered复H_code | 0.0106715966193 | 0.0115335284392 | 严格≤1e-4，未通过 |
| native / augmented | 1.60884472011 | 1.97790914967 | 各≤1e-6，未通过 |
| 原total augmented | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |
| 独立DOLFINx total原方程 | 0.762112577426 | 0.936939047704 | ≤1e-6，未通过 |

| 功率 / measured、入射功率归一 | 同p3参考 | V4 final | V5实际网络c1 |
| --- | ---: | ---: | ---: |
| R | 0.812426499057 | 0.813057790084 | 0.813166677492 |
| T | 0.0324623960953 | 0.0327381741782 | 0.0327293240969 |
| A_balance | 0.155111104848 | 0.154204035738 | 0.154103998411 |
| A_volume | 0.155111104847 | 0.155388025694 | 0.155420108597 |
| R00_s | 0.812256818464 | 0.812608163311 | 0.812222944068 |
| R00_p | 1.25634444139e-26 | 5.02695584979e-05 | 0.000626436218627 |
| R00_total | 0.812256818464 | 0.81265843287 | 0.812849380286 |
| abs(R+T+A_volume−1) | 2.97762e-13 | 0.00118398995593 | 0.0013161101857 |
| 最大逐级功率差 | 0 | 0.000351344847336 | 0.000626436218627 |

| 阶段 / measured | 监督wall / s | 完整launcher单调wall / s | 采样同时树峰 / B | own swap / B |
| --- | ---: | ---: | ---: | ---: |
| v5_readout_checks | 29.1011772191 | 30.969128705 | 711270400 | 0 |
| FEINN-FROZEN-HIDDEN-READOUT-G | 362.10759266 | 364.272690128 | 1673396224 | 0 |
| v5_readout_reconstruct | 17.1475315631 | 19.403170257 | 517783552 | 0 |
| v5_readout_compare_only | 18.6208139439 | 20.795906125 | 462159872 | 0 |

reference_used_for_training=true；pde_only_solve=false；production_initialization_allowed=false；pde_only_solver_qualified=false；official_candidate_results=false。主阶段完整launcher364.273s、树峰1673396224B、自身swap0，120s留白通过；真实M5总G列作用1773≤2500，因子成本新增0，稀疏G/QR/SVD/存盘均包含于实耗。旧累计44119.848638203344s保留，后续辅助与浏览器计费以[最终资源账](records/resource_costs_v5.json)为准，采样峰不相加，管理tmux服务器单列。

[Response V5](../response_v5.md)、[详细诊断](frozen_hidden_readout_v5.md)、[完整通道/区域Gate](records/gate_decisions_v5.json)、[run/source/hash](records/run_index_v5.json)、[投影](records/readout_projection_v5.json)、[新渲染](records/render_check_v5.json)。固定特征里确有更优G组合，但它不足以通过门限，仍不能否定改变hidden后的同架构。下一最小建议交由review决定是否授权区分隐藏特征与原方程约束的单项诊断，本轮不自动实施。

# Task42extra Review V3 后续：V4 持久 Adam500 边界重放

本节追加V4，下面V1–V3历史原文保留。网络读取已知V1参考场作监督标签；本轮修复的是完整step的运行和存盘保全，让固定模型取得可独立审核终态。它不是PDE-only求解，拟合权重不能接回旧路线、Task042或0.7nm。[Response V4](../response_v4.md)、[详细诊断](durable_replay_v4.md)、[run/source/hash](records/run_index_v4.json)、[检查点](records/checkpoint_index_v4.json)。

| V4阶段 / measured | 结果 | 解释 |
| --- | --- | --- |
| R0运行保全 | 9项小tests＋4类进程故障通过；真实M5仅2次loss/gradient | 模拟断开只证明所测路径，SIGKILL只保证先前成功落盘边界 |
| R0 Adam500切换资格 | c/目标/梯度差0；E_G0.2008211341、native14.2634632 | 旧Adam500参数＋确定性重建buffers，创建fresh L-BFGS；817历史未恢复 |
| R1唯一正式后段 | WALL_BUDGET；新2129完整闭包、logical2629、93完整外层step | 末次未完成step回滚，final对应2122闭包边界；7次试探费用照计 |
| R2独立重建与FE compare-only | 参数→q15差0；q30/q15差8.5141e-13；新MUMPS0 | 所有参数、buffer和optimizer保留；V1同p3参考不重求 |
| 表示分类 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED | G/scattered L2/curl三项均未达部分0.01，更未达正0.001；不是数学不可表示证明 |
| 保存留白规则 | C1遗漏导入，至少120s规则未满足；总wall未超3h | C2已改launcher时钟/150s留白且targeted测试通过；未第二次正式运行 |
| p4 / 目标尺寸5nm / 0.7nm | not_run | 原无标签三路线负结果与旧V3中断不改 |

| 同一5nm M5、384hex、p3/q15、31968独立复FE、40端口 / measured | Adam500留存 | V4 final | 标准或参考 |
| --- | ---: | ---: | --- |
| G场误差 | 0.2008211341 | 0.01387169130 | 三项均≤0.001正 / ≤0.01部分，未达部分 |
| 散射E L2 / scaled-curl | 0.1620127280 / 0.2017046510 | 0.01325124766 / 0.01388700270 | 严格各≤1e-4，失败 |
| total E L2 / scaled-curl | 0.111101 / 0.137924 | 0.009087097891 / 0.009495805966 | 严格各≤1e-4，失败；完整H相对差与curl相同 |
| 六点total E / H_code | 0.112268 / 0.132886 | 0.009751978017 / 0.007167388173 | 全复向量及逐点严格≤1e-4，失败 |
| native / augmented | 14.2634632 / 14.2634632 | 1.608844720 / 1.608844720 | 各≤1e-6，失败 |
| 原total / 真出射 / scattered复幅相对差 | 0.137244 / 0.0658706 / 0.243664 | 0.02134370402 / 0.01024394361 / 0.03789375775 | 各≤1e-4；四类40级复值及各自分母见Gate |
| R/T/A_balance/A_volume | 0.828087/0.0419968/0.129916/0.171617 | 0.8130577901/0.03273817418/0.1542040357/0.1553880257 | 参考0.8124264991/0.03246239610/0.1551111048/0.1551111048；仅diagnostic |
| R00_s / R00_p / R00_total | 0.806827 / 0.00138799 / 0.808215 | 0.8126081633 / 5.02696e-5 / 0.8126584329 | 分极化完整定义，不用含糊R00 |
| 能量闭合 / 最大逐通道功率差 | 0.0417012 / 0.0130081 | 0.001183989956 / 0.0003513448473 | ≤1e-5 / ≤1e-6，失败 |

[独立Gate](records/gate_decisions_v4.json)保存全部40通道、六点复E/H及原材料/界面集合、绝对误差和分母。μ_r=1时H_code=curl E/(i k0)，完整H相对L2差等于相应curl相对差。port恢复和slave存储通过不替代体方程失败。五个标签政策字段贯穿manifest/checkpoint/results：reference_used_for_training=true；pde_only_solve/production_initialization_allowed/pde_only_solver_qualified/official_candidate_results全部false。监督场误差下降不等于神经求解增量。

| V4资源 / measured或保守计费 | wall / s | 同时整树RSS峰 / B | 自身swap / B |
| --- | ---: | ---: | ---: |
| R0 M5边界 | 15.843932监督 / 22.015435整launcher | 533176320 | 0 |
| R1唯一后段 | 10688.701736监督 / 10690.413275整launcher | 764751872 | 0 |
| R2 ML q15/q30 | 17.516962监督 / 19.315401整launcher | 523923456 | 0 |
| R2 FE compare-only | 18.164625监督 / 20.000318整launcher | 584249344 | 0 |

本页数值冻结时V4全账快照10934.6917s，含120s直接/最终保守费用；后续aux/浏览器与最终费用在[资源账](records/resource_costs_v4.json)追加。旧累计33070.52670758043s和失联3284s保留。新Gram factor/Gsolve均0；G CSR payload146851456B，2154次matvec95.4165s、检查点3.8402s、保留payload88078236B计入R1父wall/RSS，不重复加计，不将payload当RSS。tmux管理服务器在树外一次样本4702208B，不称全过程峰值。系统余量＋至少384GiB邻增长＋自身预算现场准入，内部串行、CPU-only/MPI1/线程1、采样swap0；共享运行性能不作方法速度归因。

保存留白偏差明确留存：C1时钟起点在worker导入后，闭包收口侵占原120s；退出后整launcher余量109.587s（监督111.298s），总3h未超。C2计时接线已修正，仅针对性测试，未重启重放。新review和必要新证据的实际GitHub渲染状态见[记录](records/render_check_v4.json)，历史页面不批量重渲染。本轮不merge，不改变旧负结果，下一步仅提交完整终态和计时偏差供review，未获准再训练或扩展模型。

# Task42extra Review V2 后续：V3 参考暴露表示诊断

本节追加 V3，下面的 V2 与 V1 历史及其负结果原文保留。固定 M5 的同一 5 nm Si/air、384 hex、p3/q15、31968 独立复 FE 系数和 40 端口不变。P0 用已保存四态考察场误差与原方程残差的关系；P1 唯一新路线 `FEINN-REFERENCE-FIT-G` **读取 V1 准确散射系数训练**，P2 冻结后独立 FE 审核。因此这项试验只探查固定网络能否表示已知参考，`reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`；V1/V2 无标签路线仍为原来的负结果，不能把监督拟合提升为独立求解成功。[详细方法与结果](representation_diagnostic_v3.md)、[Response V3](../response_v3.md)、[run index](records/run_index_v3.json)。

| V3 阶段 / measured | 数值或状态 | 解释 |
| --- | --- | --- |
| P0 四态 `A(c−c_ref)=r−r_ref` | 最大 operation-scaled 差 `3.45e-13`，参考原残差 `6.79e-12` | 恒等式和保存的参考均实算；未把参考残差设零 |
| P0 V1 FREE / V2 scaled FREE | `E_G=0.991760/0.954121`、原 native `0.596914/0.607772`、负梯度方向余弦 `0.02306/0.00508` | 两次解析最优实步长只作离线见证，场误差几乎不变 |
| P0 Gram 成本 | setup `96.880 s`、11 Gsolve `3.466 s`；A/Aᴴ `11/4`；树峰 `1,038,958,592 B`、自身swap0 | 仅 P0 进程一个研究用稀疏因子，结束释放 |
| P1 梯度/事务资格 | 三条非零实方向、batch1/8、合成复数目标与回滚通过 | fit 闭包只用 G matvec和完整矩 VJP，无 Gsolve/A/Aᴴ |
| P1 唯一拟合 | `EXECUTION_SESSION_LOST_NO_FINAL_CHECKPOINT`；观察825 closure，仅Adam500参数保存 | 受监督会话意外消失；没有final/last_trial/optimizer状态，不重启训练；不是 PDE-only 解 |
| P2 独立场/原方程/功率审核 | 留存态compare-only完成；严格Gate均失败 | 只审核Adam500并复用V1 p3参考，新MUMPS计数0；不得当完整候选终态 |
| p4 / 目标尺寸5nm / 0.7nm | `not_run` | 本批无放大授权 |

中间 Adam 日志的 `parameter_update_norm` 在更新前采样，0 不是接受更新幅度；每25 closure 的真实更新范数标 `NOT_RETAINED`，不重放唯一训练补历史。第817次已提交参数审核只留有`E_G=0.0603363`和原残差`8.19881`，相应参数未保存，不能用于P2；唯一可重建的Adam500态为`E_G=0.200821`、native`14.26346`。失联训练采样时长至少3097.314s、保守按3284s计入本批账，树RSS峰697479168B、自身swap0。[中断身份和账](records/fit_interruption_v3.json)。

| 同一 M5、同p3参考 / measured | 准确参考 | Adam500留存网络态 | 严格资格 |
| --- | ---: | ---: | --- |
| G场误差 | 0 | 0.200821 | 完整拟合研究正阈值0.001；缺final不得作最终分类 |
| 原native / augmented残差 | 约6.79e-12 | 14.263463 / 14.263463 | 各≤1e-6，未通过 |
| 散射E L2 / scaled-curl相对差 | 0 | 0.162013 / 0.201705 | 各≤1e-4，未通过 |
| total E L2 / scaled-curl相对差 | 0 | 0.111101 / 0.137924 | 各≤1e-4，未通过 |
| 40级原total / 真出射 / scattered复幅相对差 | 0 | 0.137244 / 0.0658706 / 0.243664 | 各≤1e-4，未通过 |
| R/T/A_balance/A_volume | 0.812426/0.0324624/0.155111/0.155111 | 0.828087/0.0419968/0.129916/0.171617 | 功率差与体吸收、能量均未过；候选仅diagnostic |
| `R00_s/R00_p/R00_total` | 0.812257/约1.26e-26/0.812257 | 0.806827/0.00138799/0.808215 | 单列极化，避免“R00”歧义 |
| `abs(R+T+A_volume−1)` / 最大逐通道功率差 | 约2.98e-13 / reference | 0.0417012 / 0.0130081 | 限值1e-5 / 1e-6，未通过 |

完整网络参数确实产生保存的全部FE系数，q30/q15差`2.85841e-12`、无求积漂移。六点复E/H、全40有序复通道及其分母、air/substrate/grating/interface-near双侧单元的场积分与cell集合hash见[完整诊断](representation_diagnostic_v3.md)和[独立Gate](records/gate_decisions_v3.json)。审核source为`7c2bffe4dff7b2c9a918ade6ec02a45e168b4890`；它不生成新的准确参考或MUMPS求解，`pde_only_solver_qualified=false`、`official_candidate_results=false`。快照未达研究阈值，但完整拟合最终参数已丢失，最终表示能力保持`INTERRUPTED_FIT_NO_FINAL_STATE`。

| V3资源口径 / measured或保守计费 | wall / s | 同时树RSS峰 / B | 自身swap / B | 说明 |
| --- | ---: | ---: | ---: | --- |
| P0误差—残差及唯一Gram因子 | 104.833 | 1,038,958,592 | 0 | 因子setup96.880s、11solve3.466s，结束释放 |
| 唯一P1训练尝试 | 3284.000保守计费；实际监督采样至少3097.314 | 697,479,168 | 0 | 会话消失无`run_summary`；保守计到首次确认进程不存在 |
| Adam500留存态登记 / q30重建 / FE独立审核 | 6.043 / 14.101 / 24.169 | 492,134,400 / 520,720,384 / 647,409,664 | 全0 | 各为独立监督阶段，不加RSS峰 |
| GitHub首轮8页浏览器检查 | 77.844 | 2,042,216,448 | 0 | 轻量2GiB内；26截图hash，抽看关键公式/表格 |

首轮已发布文档在GitHub实渲染8页、11表、7公式通过；Review V2为4表/5公式，V3详细诊断为3表/2公式。[渲染证据](records/render_check_v3.json)绑定精确发布blob与截图。首次本地Markdown检查因尚未生成此渲染记录的链接失败，生成真实待验记录后8页/38表通过，失败费用仍计入资源账。到首轮浏览器及其验算后，本批正式阶段加中断保守计费`3462.842s`、辅助`116.443s`、终端/最终尾段保守预留`120s`，合计`3699.285s`；原16h仍余约`24672.776s`，本批4h仍余约`10700.715s`。最终二次发布渲染与尾段费用以[完整资源账](records/resource_costs_v3.json)为准。最大同时树RSS是浏览器的`2,042,216,448B`，不把阶段峰值相加；所有自有树采样swap为0。目标尺寸5nm与0.7nm均未运行。

# Task42extra Review V1 后续：V2 固定尺度诊断

本节追加 Review V1 的唯一后续试验，下面的 V1 16节原文完整保留。原模型 M5、全部 31968 复 FE 系数、40端口、材料与弱残差未改。V2 把原 Gram 对角用于优化变量 `c=Dy`，用于检查各类系数尺度是否让旧 FREE 优化困难；它没有训练新网络。D0既有状态诊断、D1梯度资格、D2唯一候选及D3独立复验均完成。[详细解释和完整表](scaling_diagnostic_v2.md)、[Response V2](../response_v2.md)、[独立Gate](records/gate_decisions_v2.json)。

| V2 阶段 / measured | 实际结果 | 身份与边界 |
| --- | --- | --- |
| D0旧状态 | 4个保存态的loss/gradient；Adam500参数与optimizer state=`NOT_RETAINED` | 原native/Gram/history/checkpoint；不补跑历史 |
| D1缩放资格 | `diag(D*GD)`最大偏差4.44e-16；3个非零复向量、3个非零实方向及事务恢复通过 | `D`仅从原MPC后全局G对角取值，hash见[设计](records/scaling_design_v2.json) |
| D2唯一新候选 | 4000 closure停止；native/augmented均0.607772 | `CLOSURE_BUDGET`；相对V1 FREE 0.596914未改善 |
| D3 compare-only | 散射E L2相对误差0.954209；MUMPS symbolic/numeric/solve=0 | V1同p3参考复用，非新准确解或连续极限 |
| 严格/研究判定 | 方程、场、功率均未通过；`SCALING_DIAGNOSTIC_NEGATIVE` | 研究正信号需残差≤0.05969144472114且散射E≤0.5，均未满足 |
| 条件p4/目标 | p4=`not_run`；目标尺寸5nm/0.7nm=`not_run` | V1的`DISCRETIZATION_NOT_QUALIFIED`表示p4未准入 |

| 同口径量 / measured | V1 FREE-FE-DUAL | V2 scaled FREE | 用途 |
| --- | ---: | ---: | --- |
| `L_D` / native残差 | 0.103899 / 0.596914 | 0.0990053 / 0.607772 | loss降低不能替代原方程 |
| 散射E L2 / scaled curl | 0.991925 / 0.991755 | 0.954209 / 0.954118 | 仍远高于严格1e-4和研究0.5 |
| ordered原total port / 真出射复幅 | 0.573349 / 0.275180 | 0.554439 / 0.266104 | 分母分别是参考原port范数/出射范数 |
| R/T/A_balance/A_volume | 0.845194/0.115246/0.0395601/0.459627 | 0.841893/0.109807/0.0483005/0.443408 | 均为未资格化diagnostic；准确参考0.812426/0.0324624/0.155111/0.155111 |
| closure / A / Aᴴ / Gsolve | 4000/4002/4000/4003 | 4000/4002/4000/4003 | 同计算工作数，未隐藏额外closure |
| 候选监督wall / 树RSS峰 / 自身swap | 2901.906s / 1366249472B / 0 | 2539.810s / 1365712896B / 0 | shared-workstation，时间不可归因于方法 |

首轮“出射复通道”约0.27518确实对应 `ordered_outgoing_channels`，CSV约0.573349对应 `ordered_total_channels`；两者分子相同但参考分母分别0.913080与0.438234，旧V1文件不改。[V2 checker](records/gate_decisions_v2.json)从原40级复数组逐项复算。本批数值阶段最高同时树RSS为1365712896B，V1数值阶段最高约1.313GiB，而V1含浏览器的完整账最高2095390720B；不要混同口径。本批最终辅助/渲染成本与首次compare-only接线失败、默认沙箱MPI socket失败均在[资源全账](records/resource_costs_v2.json)和[run index](records/run_index_v2.json)保留。

本轮从 V1 研究档案延伸，不改变两条FEINN网络的旧负结果，也没有新的神经增量证据。Gram三次fresh factor setup约97.20/96.93/101.07s及全部solve均计入；候选复用G装配实耗为0，从零归属另加648.765s，不把此归属再计进本批实际wall。缩放不足以取得本固定M5的合格解，不能推论所有神经方法无效。下一步只能作为新的review建议，不在本批自动开展p4、目标尺寸5nm、0.7nm或其他尺度扫描。

Review V1与task一行公式修正的GitHub实际预览完成：前者6表/3公式、后者6表/7公式，表格列一致且无公式错误；关键截图抽看，24张截图均核hash。[渲染记录](records/render_check_v2.json)保留第一次导航超时和第二次Firefox `eager` 成功的费用。V2完整监督账含浏览器的同时树RSS峰为1,741,213,696B，自身swap0；[资源账](records/resource_costs_v2.json)给出全部阶段和快照截止，不能把数值峰1,365,712,896B称为会话峰。

# Task42extra 首轮执行总结

本轮完整接口资格为 True，三路线同离散资格 0/3。结果以原方程、独立完整FE场和功率审核为准。本轮比较的是同一M5、同全部独立FE、同原方程/材料/模式/初值的三条路线。坐标网络通过积分产生边、面和内部矩；FREE直接优化完整复系数。DUAL用正定测试内积衡量弱残差，增加真实稀疏Gram因子成本。LE与LD不能直接按数字大小比较精度。

## 1. 最终状态

| 项目 | 实际状态 | 边界 |
| --- | --- | --- |
| E0 Git/环境/资源 | 完成 | 原生Linux；canonical linked worktree；受控共享 |
| E1 | INTERFACE_PASS_ONLY | 完整矩/A/Aᴴ/Gram/梯度通过；不是5nm solver PASS |
| E2 | 0/3同离散合格 | 具体停止/失败量见下表与raw records |
| E3 | True | 独立参考资格单列，不反馈训练 |
| E4 | DISCRETIZATION_NOT_QUALIFIED | 未准入时P4 PDE不运行 |
| E5 | 完成成本/增量/容量设计 | 目标尺寸5nm与0.7nm均not_run/not_qualified |

## 2. 任务目标与非目标

| 目标 | 比较方式 | 未获资格项 |
| --- | --- | --- |
| 正确完整插值能否求得真实5nm FE解 | EUC/DUAL/FREE同物理与全部FE | 不是旧Task042 trace/p4粗逆续跑 |
| 分开度量与网络贡献 | EUC→DUAL度量；DUAL→FREE表示 | 无teacher/目标准确解监督或warm start |
| 决定目标尺度下一步 | 容量和全过程账 | 不启动大5nm/0.7nm，不扫描p/h/M/MPI或网络 |

## 3. 基线、冻结配置和环境

| 量 / 单位 | 冻结或实测值 | 证据性质 |
| --- | --- | --- |
| 物理 / nm | lambda5；Si/air；grazing1°/phi0/s/amp1 | frozen |
| 盒 / nm | [-5,5]×[-3.75,3.75]×[-1.25,8.75] | frozen |
| 离散 | h1.25、384hex、N1curl p3、q15、MPI1 | measured |
| native / slave / independent FE | 34050 / 2082 / 31968 | measured；内部13824完整保留 |
| 边 / 面 / 内部矩 | 3744 / 14400 / 13824 | measured；无内部物理恢复 |
| 材料cell / notch | air200、substrate48、block136；notch8 | measured；y/z同时变化 |
| 完整DtN / NN实参数 | 40 / 8966 | measured；3×64 tanh，6输出、FP64 |
| FREE实参数 | 63936 | 全部31968复FE实虚分量 |
| dtype / env | PETSc complex128/int64；Torch2.7.1+cpu；数学/interop1 | 新env，合格原生库只读接线 |

材料唯一hash与实际mesh/tags/mode/Gram/source见[run index](records/run_index_v1.json)及[预登记](records/design_v1.json)。Si n=0.99396854453+0.00435380777i，epsilon=n*n；不重新猜材料。环境与三个既有项目见[隔离记录](environment_and_isolation.md)。

## 4. 实现与方法

| 方法 | 用途 | 代价/限制 |
| --- | --- | --- |
| 完整Nédélec矩插值 | 把连续坐标网络转成原FE解；边36/面72/内部36每cell | Piola、T^-T、唯一owner和原MPC相位一次 |
| 原局部未凝聚A/Aᴴ | 对全部独立FE训练与真残差审核 | local tensor+约束COO+全部端口；无global A CSR/AᴴA |
| 原端口消元 | alpha=solve(H,gp+Dc) | 原[V B;-D H]，正表面归一化H；只消端口 |
| 正定Riesz | LD=r*G^-1r/(2f*G^-1f) | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，非Maxwell逆 |
| 有界VJP | 最多8cell图，重算反向 | 8966参数之外还有坐标/矩/激活/算子缓存 |
| 有界事务优化 | Adam500、L-BFGS history20/strong-Wolfe | 每条3h/4000完整closure；outer返回才提交 |
| 盲参考 | 冻结后独立准确同p3审核 | 只作authority，全局Maxwell因子不进入训练 |

详细论文方法与改动见[映射](method_and_paper_mapping.md)。论文正定Dirichlet模型及refined test与本复数不定开放同p3问题不同；没有论文原样复刻、波长鲁棒或超收敛结论。

## 5. 实验/运行矩阵

| 阶段 / evidence身份 | 实际source | 监督 wall / s | 同时树RSS / GiB | 结果 |
| --- | --- | --- | --- | --- |
| e1_fe | a3dd65f594dd | 737.521 | 1.13985 | FE_INTERFACE_PASS |
| e1_grad | a3dd65f594dd | 201.116 | 1.19316 | INTERFACE_PASS_ONLY |
| e1_smoke | a3dd65f594dd | 44.1878 | 0.494907 | PASS |
| e3_reference | 7a79b3007d92 | 672.463 | 1.16026 | INDEPENDENT_REFERENCE_PASS |
| e4_p4 | 7a79b3007d92 | 1.96302 | 0.0635757 | DISCRETIZATION_NOT_QUALIFIED |
| FEINN-DUAL | 7ac01a62453e | 10688.1 | 1.31262 | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-EUC | 7ac01a62453e | 10690.7 | 0.65601 | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | 7ac01a62453e | 2901.91 | 1.27242 | FEINN_OPTIMIZATION_NEGATIVE |

制造解是8-cell单位正定curl-curl+mass诊断，wavelength=None，不能叫5nm结果。正式FE均通过one-run dat和`scripts/run_case.py`，实际数值source与之后文档HEAD分开。每阶段结束清场再启动下一阶段。

## 6. 关键结果表

| 路线 | native / augmented | 散射E L2 / scaled-curl | selected total E/H | 出射复通道 | R/T/A_balance/A_volume |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 0.928287/0.928287 | 0.999215/0.999234 | 0.678586/0.671902 | 0.270177 | 0.837415/0.113261/0.0493242/0.465089 |
| FEINN-DUAL | 1.10264/1.10264 | 0.998885/0.998906 | 0.678322/0.671303 | 0.270119 | 0.837391/0.113257/0.0493519/0.464992 |
| FREE-FE-DUAL | 0.596914/0.596914 | 0.991925/0.991755 | 0.672954/0.670815 | 0.27518 | 0.845194/0.115246/0.0395601/0.459627 |

| 场身份 | R00_s / R00_p / R00_total | 最大逐级功率绝对差 | abs(R+T+A_volume−1) |
| --- | --- | --- | --- |
| REFERENCE | 0.812257/1.25634e-26/0.812257 | reference | 2.97762e-13 |
| FEINN-EUC | 0.837279/6.91785e-10/0.837279 | 0.080903 | 0.415764 |
| FEINN-DUAL | 0.837271/7.0838e-11/0.837271 | 0.0808367 | 0.41564 |
| FREE-FE-DUAL | 0.844749/1.02397e-08/0.844749 | 0.0825716 | 0.420067 |

未资格化候选的R/T/A标diagnostic；只有全部Gate通过的候选成为official。total/scattered E L2与scaled-curl、六点total/scattered复E/H逐点和整体、完整ordered原port/出射/scattered复幅、40级功率均见[独立物理记录](records/blind_physics_v1.json)。相对误差保留absolute与denominator，无全局相位拟合。A_balance=1−R−T；非平凡闭合使用A_volume。

三候选checkpoint/hash冻结后，独立DOLFINx原体矩阵和完整未凝聚增广系统建立一次MUMPS准确参考；factor/matrix销毁且RSS下降后才后处理。参考从未反馈训练。它是同p3离散authority，不是连续解。

| 独立参考量 / 单位 | 实测值 | 资格边界 |
| --- | --- | --- |
| native / augmented | 6.78884e-12/6.78884e-12 | 目标各≤1e-10 |
| original total / 独立DOLFINx native | 3.51452e-12/3.26042e-12 | 原RHS，无训练反馈 |
| R / T / A_balance / A_volume | 0.812426/0.0324624/0.155111/0.155111 | 同mesh/p3 authority；不是连续解 |
| R+T+A_volume−1 / A_balance−A_volume | 2.97762e-13/2.97734e-13 | 独立吸收闭合≤1e-5 |
| Maxwell symbolic / numeric / solve / s | 0.43006/5.97992/0.361829 | reference ONLY，禁止训练fallback |
| 释放前 / 后 worker RSS / B | 1.08556e+09/2.31522e+08 | 释放factor和matrix并确认下降后才后处理 |
| reference qualified | True | 方程、能量、资源分别审核 |

## 7. 数值正确性与 Gate

| 接口Gate | 原始字段独立重算结果 | 范围 |
| --- | --- | --- |
| positive_manufactured | True | 接口资格；不能替代方程/场/功率 |
| complete_moments | True | 接口资格；不能替代方程/场/功率 |
| full_uncondensed_model | True | 接口资格；不能替代方程/场/功率 |
| native_ports | True | 接口资格；不能替代方程/场/功率 |
| Gram_variational | True | 接口资格；不能替代方程/场/功率 |
| Gram_solve | True | 接口资格；不能替代方程/场/功率 |
| quadrature | True | 接口资格；不能替代方程/场/功率 |
| EUC_batch | True | 接口资格；不能替代方程/场/功率 |
| EUC_gradient | True | 接口资格；不能替代方程/场/功率 |
| DUAL_batch | True | 接口资格；不能替代方程/场/功率 |
| DUAL_gradient | True | 接口资格；不能替代方程/场/功率 |
| e1_smoke_resource | True | 接口资格；不能替代方程/场/功率 |
| e1_fe_resource | True | 接口资格；不能替代方程/场/功率 |
| e1_grad_resource | True | 接口资格；不能替代方程/场/功率 |

| 路线 | 实际停止 | 方程 / 场 / 功率 | 状态 |
| --- | --- | --- | --- |
| FEINN-EUC | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-DUAL | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | CLOSURE_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |

方程≤1e-6；同离散场/通道≤1e-4；MPC/消元恢复≤1e-10；功率总量差与闭合≤1e-5、逐级功率差≤1e-6。完整阈值重新计算于[独立Gate](records/gate_decisions_v1.json)，不靠optimizer success、小梯度或status字符串通过。q15/q30非零见证相对差1.47451e-15，q15冻结，q60未运行。

## 8. 性能或资源结果

| 路线 | closure尝试 / 完成 / 完整外层 | 实际完整wall / s (derived) | 从零归属 / s | 运行树峰 / GiB | own swap / B |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 2219/2219/578 | 10692.4 | 10783.2 | 0.65601 | 0 |
| FEINN-DUAL | 2387/2387/586 | 10689.9 | 11429.5 | 1.31262 | 0 |
| FREE-FE-DUAL | 4000/4000/649 | 2903.75 | 3643.38 | 1.27242 | 0 |

| 辅助量 / 单位 | 实测值 | 含义 |
| --- | --- | --- |
| Gram rows / NNZ | 31968 / 7336179 | 全部独立p3；材料无关正定测试内积 |
| Gram CSR payload / B | 146851456 | 数组体积，不是RSS |
| 首次装配 / s | 648.765 | 完整计入DUAL/FREE从零成本，研究实账只计实际一次 |
| 资格factor setup / s | 110.571 | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；LLᴴ/AMD |
| symbolic L NNZ | 1.88397e+07 | symbolic后容量Gate，非dense inverse |
| CHOLMOD current / peak B | 5.44919e+08 / 6.33593e+08 | 辅助因子也计资源 |
| 资格Gsolve max true relative | 9.13339e-12 | 限值1e-11；训练各路线另逐次检查 |

| 路线 / research-only | fresh setup / s | 全部Gsolve / s / count | max true residual | factor current / peak B |
| --- | --- | --- | --- | --- |
| FEINN-EUC | 0 | 0 / 0 | not_run | not_run/not_run |
| FEINN-DUAL | 128.442 | 810.233 / 2390 | 6.10176e-13 | 5.44919e+08/6.33593e+08 |
| FREE-FE-DUAL | 113.025 | 1394.34 / 4003 | 7.53354e-13 | 5.44919e+08/6.33593e+08 |

发布前数值/测试快照的监督实账25985.9 s；含启动/发布的workflow快照约26016.6 s（UTC/mtime derived）。发布后实际render及复核费用追加到最终[resource账](records/resource_costs_v1.json)，本快照不代替最终全账。首轮停止预算57600 s，以最终完整账重算。独立参考、资格和失败轻测试另列并包含研究全账。从零归属按本轮E1准备减exclusive Gram assembly作为保守common，DUAL/FREE各加完整assembly；各自fresh factor已在其运行账，不重复加。该归属不是额外研究耗时，也不是空机器冷启动benchmark。

原C2首个H除法同时位于setup和aggregate port timer。compact互斥账保留首项在setup，将其后port归入other_control，raw port timer只作非累加diagnostic；network/moment/Gsolve/A/Aᴴ/VJP/optimizer/IO均保留，避免父子重复相加。所有bytes/payload与采样RSS区分，峰取同一树同时最大而非加阶段峰。完整资源账见[records](records/resource_costs_v1.json)。

## 9. 根因解释

| 问题 | 已排除/已确认 | 仍未确定 |
| --- | --- | --- |
| 接口实现 | 完整矩、多项式/方向/MPC、A/Aᴴ、非零port/内部载荷、FD通过 | 通过不是普适几何/所有网络参数的求积证明 |
| 保留未知量 | 31968全部独立FE及13824内部矩实测 | 不是仅trace/内部局部物理恢复 |
| Riesz成本 | 真实SPD稀疏factor与每次solve准确性 | 正定G不保证不定A训练/波长鲁棒 |
| 优化与表示 | 三路线同固定预算与zero start | 有限负结果不能唯一归因于网络表达或优化条件 |
| 离散 | 仅固定p3/h1.25/M/MPI1 | p4有条件；continuum和目标未资格化 |
| 共享资源 | 未触线，own swap0，保护邻任务配置 | 无零干扰反事实或20%可比性能结论 |

## 10. 成功路线

完整数学接口、原生环境和事务检查提供可复核的实现证据。准确参考若通过，仅提供同离散authority；不会提升未通过的候选或目标尺寸资格。

## 11. 失败、负结果与未运行项

| 路线 | 实际停止 | 方程 / 场 / 功率 | 状态 |
| --- | --- | --- | --- |
| FEINN-EUC | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FEINN-DUAL | WALL_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |
| FREE-FE-DUAL | CLOSURE_BUDGET | False/False/False | FEINN_OPTIMIZATION_NEGATIVE |

p4判定：DISCRETIZATION_NOT_QUALIFIED。目标大5nm、0.7nm/48h、更多几何/波长/seed/宽度/carrier、监督拟合和raw NN点云超收敛均not_run。每条停止原因、last committed/trial与费用保留，checkpoint为parameter-only，未存一致optimizer state，不支持一致续训。closure尝试在开始时计数；完整loss＋gradient按成功history另计，失败/不完整尝试也保守占用预算。raw内层计数是最后完整外层的Torch n_iter；最后异常外层的partial inner次数未另存，其全部已完成closure/A/Aᴴ/Gsolve及费用照计。

| 对照轴 | 本轮身份 | 可得结论 |
| --- | --- | --- |
| p | p3 measured；p4 not_run | p3候选未过资格，禁止p4条件求解；无连续极限结论 |
| h | 1.25 nm fixed | 没有h收敛实验 |
| Full3D/Hybrid | 本任务仅原生完整Nédélec FE | 未比较不同离散/算法 |
| Fourier模式M | 原规则自动得到40个完整端口 | 未扫描M；不能代替模式收敛 |
| MPI | 1 | 没有并行加速或跨MPI等价声明 |

## 12. 代码和文件变化

详见[changed files](changed_files.md)：数值核在src/solvers，runner只参数化编排。普通默认solver数学不变；旧Task042历史/环境/运行目录保持只读；新scope为Task42extra。

## 13. 最终合并建议

| 依赖组 | 实际改动 | 本轮合入建议 |
| --- | --- | --- |
| production numerical/core | 原默认solver数学不改；run_case增加明确opt-in dispatch | 需review；不把未资格路径设默认 |
| runner/watchdog | task-local activation、资源准入与子树监督；依赖既有通用watchdog | 可单独审阅，不影响邻任务 |
| checker/benchmark | stdlib compact checker、容量推导、render检查 | 只读复核，依赖本任务compact records |
| research-only | 完整矩、A/Aᴴ、稀疏Riesz、三路线优化、reference/p检查 | 研究路径，不能当可扩展PC或生产solver |
| evidence/docs | 本任务response/outcomes、进度与模型总账追加 | 保存正/负结果，不改Task042历史 |
| do-not-merge | venv/cache/raw矩阵/场/history/checkpoint/浏览器profile | ignored；无master/跨支线merge |

只推执行支线，等待review；没有master/其他支线merge、amend、强推或生产默认资格。

## 14. 局限

只测一个固定小模型、单seed、p3/h1.25/M40/MPI1及当前共享工作站；未扫描这些影响。native Linux证据见ABI，通用watchdog旧raw label `WSL-global diagnostic`仅为复用标签，不表示运行于WSL。没有cgroup委派，使用目标0.5 s同时子树RSS采样，不冒称连续内核限额；自身swap按样本VmSwap，全球swap仅诊断。性能/邻任务影响为inconclusive。近零规则E0冻结，没有事后调分母或相位。

GitHub rendered-view 检查实际发现[发布任务书](../task.md) §5.4 使用的 `\operatorname{Re}` 被拒绝；该文档 Gate 为 `RENDERED_VIEW_FAIL_TASK_MATH`，不记为通过。本支线可修改的方法映射中的同类 `\operatorname{solve}` 已修正，复核证据及截图 hash 见[render记录](records/render_check_v1.json)。这不改变冻结数值实验和其失败判断。

## 15. 下一步决定

建议后续review只授权固定M5的一条FREE-FE-DUAL变量尺度诊断：用正定Gram对角给全部FE系数统一单位尺度，原loss、零初值、closure/wall和全部验收不变。该诊断不使用目标准确解训练、不调用Maxwell逆、不扩大模型；用于先区分优化条件问题与神经表示问题。本轮未实施。

目标尺寸容量与需要先解决的临时张量/Gram阻塞见[5nm计划](target_5nm_scale_plan.md)。本轮交付后停止等待review，不借剩余预算启动目标PDE。

## 16. 证据索引

| 入口 | 用途 |
| --- | --- |
| [response_v1](../response_v1.md) | Git/source与执行边界 |
| [run index](records/run_index_v1.json) | 每stage source/input/env/resource/artifact hashes及失败费用 |
| [interface](records/interface_gates_v1.json) | 原始完整矩/算子/梯度/Riesz Gate字段 |
| [comparison CSV](records/route_comparison_v1.csv) | 三路线完整统一口径 |
| [physics](records/blind_physics_v1.json) | 复E/H/全40级复幅与功率/原残差 |
| [Gate](records/gate_decisions_v1.json) | stdlib checker独立重算 |
| [resource](records/resource_costs_v1.json) | 实际/归属/互斥成本及树RSS/释放 |
| [tests](test_summary.md) | 相关tests、static、Markdown与render记录入口 |

## Task42extra Review V7 后续：V8 相位完整对照与p4恢复

本轮恢复了独立p4准确参考，并完整执行同参数plain/phase从零PDE对照及失败后条件监督拟合。相位把已知传播振荡先乘入网络点值，再经完整FE矩，减少了网络必须学习的振荡；这不提供准确解。C phase场近似好于plain但原残差更大，均未解出p3；D phase为REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED。A与B–D分别验收，没有因一个负结果结束整批。

| 新路线 / measured、功率diagnostic | native | G误差 | 散射E L2 | 散射curl | R | T | A_balance | A_volume | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V8-PLAIN-DUAL | 1.055409537 | 0.9989650389 | 0.998945184 | 0.9989655403 | 0.837397101 | 0.1132687865 | 0.0493341125 | 0.4650227017 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PHASE-DUAL | 1.319288666 | 0.2145123712 | 0.2134667998 | 0.2145387128 | 0.7784899564 | 0.04143373838 | 0.1800763052 | 0.2070765764 | PDE_OPTIMIZATION_NEGATIVE |
| V8-PLAIN-REFERENCE-FIT | 3.524097926 | 0.02509159227 | 0.02572950659 | 0.02507527061 | 0.8154647648 | 0.03390513729 | 0.1506300979 | 0.1552334771 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |
| V8-PHASE-REFERENCE-FIT | 0.7662824909 | 0.01040885398 | 0.01005721383 | 0.01041758155 | 0.8125474719 | 0.03261911224 | 0.1548334159 | 0.155181753 | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED |

p4自身参考残差≤1e-10、能量≤1e-5，完整75264复FE/40port，75304 rows/32891168NNZ，峰3888418816B；p3/p4散射E L2/curl相对差0.0149860/0.0190206、R/T/A/A_volume差0.00372680/0.000773685/0.00295312/0.00295312，超过场1e-3和功率1e-4，P3_P4_SENSITIVITY_OBSERVED。一次p变化不能证明连续/h/端口收敛，也不解释NN未求准同p3。

所有C/D为原M5/5nm/384hex/p3/q15/31968独立复FE/40端口，同8966实参数seed。C与D数据角色分离、从零参数相同，C4000/D1500完整closure各自硬预算；监督权重不回流C。旧e4_p4、V7中断和V1–V7结果永久保留。功率未过方程均diagnostic，不是official。

| 程序成本 / measured | plain C | phase C | plain D | phase D |
| --- | --- | --- | --- | --- |
| 全launcher wall / s | 9294.1348 | 8747.323512 | 2850.139041 | 2956.519787 |
| charged / committed closure | 4000 / 3997 | 4000 / 3986 | 1500 / 1480 | 1500 / 1480 |
| Gsolve / freshGram | 4043 / 1 | 4043 / 1 | 0 / 0 | 0 / 0 |

C source bc052a3744528277f00a7a9a5566aa4a6d7393ed；p4 actualsource d0b82d7a165be89d9fa90b03be3151db9a9c3869。每阶段树RSS/CPU/zero swap、Gram cost、独立重建/参考身份与所有失败费用见[完整资源账](records/resource_costs_v8.json)和[run/source index](records/run_index_v8.json)。旧保守累计49007.27663535159s保留，V8新增≤43200s；不将nested Gram/IO timer加到父wall。目标尺寸5nm/0.7nm均NOT_RUN、master merge未批准。

监督 phase 的 G/L2/curl 三项分类为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**，plain 为 **REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED**。相位在相同参数规模和1500完整closure内的G误差改善约2.410600851倍，说明它在这个固定G目标和预算下更容易拟合；C的原方程优化仍未通过，不能把D监督结果等同于无标签求解。两条拟合均使用参考，因此结果只能限定本架构、目标、预算，不能独立证明网络表达能力的数学上限。

已经排除本轮相位符号/单位/完整矩、非单位Floquet、非零实方向VJP、batch一致性、冻结参数重建、求积漂移、标签混入C、资源超限和匹配状态丢失等已测问题。剩余因素包括有限网络对反射/衍射/界面细节的表达、非凸残差目标的优化、G度量与原方程误差的差别，以及p3连续精度；p4对照仅说明离散敏感性，不解释NN未解出同p3。

后续只建议一项设计：在原M5/p3和同8966参数的plain/单相位表示上，预登记受控的网络参数空间Gauss–Newton信赖域对照。它用局部线性近似决定一次参数更新，并限制更新范围，检验当前非凸残差优化是否为瓶颈；仍从零、无标签，保持原Riesz目标/严格验收，不用Maxwell逆或监督权重。先核定JVP/VJP、A/A*、Gsolve、工作内存和完整成本上限，再由新review授权；本批没有实现或启动新优化器、PDE微调、多载波、p5/h细化或更大模型。

证据：[Response V8](../response_v8.md)、[authority](authority_recovery_v8.md)、[phase完整对照](phase_feinn_v8.md)、[设计/白名单](records/campaign_design_v8.json)、[维修](records/repair_log_v8.json)、[Gate](records/gate_decisions_v8.json)、[PDE CSV](records/PDE_comparison_v8.csv)、[D CSV](records/representation_comparison_v8.csv)、[GitHub actual view](records/render_check_v8.json)。同物理量完整分母、原始复样本和40级复通道/功率不省略到单一R/T。

# V9 完整执行归档

| 包 | 实际完成 / measured结果 | 边界 / 证据 |
|---|---|---|
| A | p5参考合格；唯一新增numeric；p4/p5仍有curl/H敏感性 | p_ladder_v9.md；p5_authority_v9.json |
| B | GN/JVP/实伴随/K/真实C500/batch/事务资格通过 | gn_checks_v9.json；targeted_tests_v9.json |
| C | plain与phase均正常预算冻结；原p3未解合格；GN信号false | pde_comparison_v9.json；inner_solver_history_v9.json |
| D | 条件自动触发；两条独立监督FIT-GN均正常预算冻结；三项1%门限未过 | fit_comparison_v9.json；D权重不反馈C |
| E | 独立q15/q30重建、FE compare-only、原字段checker通过；渲染另列 | gate_decisions_v9.json；run_index_v9.json |

实际数值、source、资源和失败项分别由上述新页与compact记录承载；本轮不删旧负结果、不改任务或review、不merge。
