# Task042 V5 最新状态：固定对象失效定位完成，严格粗逆仍未资格化

同一个残差分别测局部B、粗空间C与原两层B2，再做有限方向的最小二乘，区分空间覆盖与组合失效；这不是新的求解器或训练。所有数值比例dimensionless，绝对port为原数组欧氏范数，无新物理R/T/A。

| 最新范围 / 身份 | measured结论 / 边界 | evidence |
|---|---|---|
| 完成阶段 | Review V2 D0–D4，12/12共同state、3已消费teacher离线审核、24同r作用和192原方程审核 | [response_v5](../response_v5.md) |
| 固定模型 | 原Si13.5nm/p6h10对应p4、MPI1/80DtN，53084FE/21824reduced/8184464NNZ；S/B/双rank128 Z/U/R不改 | [预登记](records/localization_design_v5.json) |
| 覆盖 | 物理初态OLDPOD eta_r/e .9990665/.2216303、ERROR .9997845/.7134416；e与r覆盖区别明确 | [24覆盖](records/coverage_v5.csv) |
| 同向量组合 | port-only Bopt .9845925；OLDPOD B2opt .9926201/ZB .6171864，ERROR .9872461/.7423358；部分组合利用不佳，原A4/port仍失败 | [192审核](records/same_residual_actions_v5.csv) |
| 补空间 | 有效rank16/16，完整TV最小奇异值4.771224799/3.034800156；无已证near-null，不能据小投影谱断言真实奇异 | [探针](records/complement_probes_v5.json) |
| 资格 / 未运行 | strict0/192诊断修正，无新solver pass；fresh seed420620、F5、短波、NN/GPU/official均not_run | [D4及唯一建议](records/localization_decisions_v5.json) |
| 内存 / 时间 | 四阶段wall1144.401529s，整树同时RSS峰1135407104B，own swap0；shared-workstation/performance inconclusive | [完整费用](records/run_index_v5.json) |
| 源码 / Git / 环境 | 四阶段clean source`5d82651af0f723c73487783deb43969f05d46ed3`，canonical NN-Lab / origin同任务branch；只读native prefix/独立cache，实际现场CPU0/0/0/13数学1，自有树16GiB监督 | [前检](records/pre_run_checks_v5.json) |

D4三假设分别评价、多因素或INCONCLUSIVE允许；[中心说明](failure_localization_v5.md)列实际连续指标、范数分母、完整像与限制。未修改A4/A6/80通道/原1e-10，未构造global p4 factor或隐藏fallback。未发现持续压力，但邻阶段没有可比时长，不宣称绝对零影响/提速。唯一下一试验仅建议、未实施；等待review，不merge。以下V1–V4正文逐字保留。

---

# Task042 V4 最新状态：两个全局空间仍未通过严格粗逆

| 最新范围 / 身份 | 实际结果 | 证据 |
|---|---|---|
| 合同 / 完成阶段 | 正式Review V1，V4_GLOBAL_ERROR_TWO_LEVEL；P0/P1/两P2/两P3完成，不沿用V3局部停滞禁令 | [response_v4](../response_v4.md) |
| 两空间 | 旧256训练对Q vs新16轨迹的128解误差；都重建Schur编码，rank均128，四恒等式和真实接口合格 | [空间](records/coarse_space_algebra_v4.json) |
| 收敛 / 负结果 | 6非零诊断strict0/6，全部256步；physical/mixed未满足预登记native和固定Schur各0.1 | [Gate](records/gate_decisions_v4.json)、[原始字段CSV](records/two_level_comparison_v4.csv) |
| P4 / F5 | 未解锁16项终测，仍未生成/读取/消费；F5/p6/official RTA/A_volume/field/channels/短波not_run | [fresh](records/fresh_qualification_v4.json) |
| 无全局因子 | 固定原GEO局部PC＋两层，无global p4 LU/私有CSR/fallback；局部＋R302309536B、Z＋U89391104B | [预算/作用](records/coarse_space_algebra_v4.json) |
| 全过程资源 | 六阶段整树wall1534.00828393s、同时RSS最大1128828928B、own swap0；MPI1/math1、现场核/own lock/16GiB监督 | [run/cost](records/run_index_v4.json) |
| 归因 / 边界 | 未训练NN，G-neural not_run；固定局部步骤上的全局空间未获得严格收敛，不否定全部空间/神经路线 | performance inconclusive，全部shared-workstation |

局部修正可能遗留跨模型误差。本批用有限全局解方向在局部步骤前后消除其可表示残差，代价是额外基存储与S作用。两空间的数学作用通过自检，但在规定的已消费问题上没有达到有效研究分流或1e-10严格精度；训练空间内自检不等于泛化成功。

| 路线 / 已消费RHS | 原A4相对残差 | 固定Schur/RHS | port绝对范数 | port operation-relative | 严格返回 |
| --- | --- | --- | --- | --- | --- |
| TWOLEVEL-OLDPOD-V4 / 0 | 0.99858818727 | 0.999092817197 | 0.0333030546374 | 0.0654894807753 | False |
| TWOLEVEL-OLDPOD-V4 / 10 | 0.949242609663 | 0.971634245187 | 0.000954707150083 | 0.480383202996 | False |
| TWOLEVEL-OLDPOD-V4 / 11 | 0.905073739084 | 0.97721673465 | 0.000949297617596 | 0.235770374702 | False |
| TWOLEVEL-ERROR-V4 / 0 | 0.999863649936 | 0.99961809965 | 0.0256415022841 | 0.0849928945237 | False |
| TWOLEVEL-ERROR-V4 / 10 | 0.937175812499 | 0.957474274981 | 0.000927512266936 | 0.334601298612 | False |
| TWOLEVEL-ERROR-V4 / 11 | 0.901084822725 | 0.963534624076 | 0.000946698188098 | 0.203706802155 | False |

原13.5nm Si、p6/h10对应p4、252cells、80完整通道、A4/A6/MPC和最终验算保持。数据来源/单位/normalization/rank、native与Schur/port分母、实际CPU和邻影响边界、离线/在线/审核/IO/释放费用以及selective merge分组见[中心结果](two_level_global_error_v4.md)。新teacher/NN/GPU未运行；资源未触线，缺邻可比实时阶段指标，不能证明零干扰。原task/review/response_v1–v3和全部历史证据保留；下面V3/V2“当前”均指当时，最新状态以本节为准。

---

# Task042 V3：几何重叠的局部作用，严格全局粗逆仍未合格

| 项目 | 最新实际状态 / 身份 | 证据 |
|---|---|---|
| 状态 | `BOUNDED_STRUCTURAL_GLOBAL_STAGNATION`，有限批次完成，待review，F5 not_run | [原字段重算Gate](records/gate_decisions_v3.json) |
| 授权 | 用户仅授权一个新B0/表示诊断批次，保留旧合同与负结果；继续仅Task042受控共享CPU，不代表F0正式review | [预登记与准确授权](bounded_diagnostic_design_v3.md) |
| Git | NN-Lab canonical linked worktree，`task42_neural_coarse_inverse`；起点d42a7de47bcd966472d58367bab93872d31584e7；base ccd357885f7f9be84efe3be07868cc94f13d93fc | [运行source](records/run_index_v3.json)；最终HEAD另由实际push回报 |
| 旧结果 | 三路线各15个非零失败、仅零通过；16个heldout已消费，全部原始结果保留 | [response_v2](../response_v2.md)、[旧CSV](records/strict_rhs_metrics_v2.csv) |
| 新结果角色 | 重算9个旧失败状态，不重跑旧KSP；一个几何PC仅3个已消费RHS，非fresh资格 | [复用](records/reused_diagnostics_v3.json)、[结构](records/structure_complete_v3.json) |

单元边/面上相邻场分量需要一起修正，旧按连续编号切512行块可能切断这种耦合。本轮把每个单元的全部trace支撑和80端口放进一个小问题，分别解后按共享次数平均；代价是252个局部因子和更多局部回代。它处理完整空间并借用原方程，最终是否可用仍由原A4/port/recovery全部1e-10决定。

## 实际实施矩阵

| 阶段 / 身份 | 完成项 | 未完成边界 |
|---|---|---|
| inherited implementation | 复用原A4/A6接口、p4-only、严格协议、固定Q的精确native最小残差LIN、冻结FP64 NN | 旧F1/teacher/训练不重跑，不把历史证据冒充新数值 |
| consumed artifact diagnosis | physical0/port-only10/mixed11 ×B0/LIN/NN，原Schur/native/port/恢复及PC4快照重新核查 | 旧未保存的restart显式状态不猜补 |
| new structural measurement | R-GEO-CELL80-v3，252个几何支持重叠子域，各192trace+80port；3 RHS各固定256步，逐步独立审核 | no global p4 LU / fallback / private audit CSR；非新大型NN |
| conditional finite-space comparison | not_run | 原physical/mixed仍量级1且末周期停滞，触预登记停止；不扩展teacher/训练 |
| new unconsumed pool | 候选freeze后另选seed420620/整族16项，未生成数组、未求解 | [计划](records/unconsumed_test_plan_v3.json)，不能称fresh终测 |
| F5 / p6 / shortwave / GPU | not_run | 本轮F5未授权；严格逆未资格化；无official物理结果 |

## 冻结模型和容量

| 对象 / 单位 | 实值或预算身份 | 保持的合同 |
|---|---|---|
| 模型 | original13.5nm、1°/phi0/s、同p6/h10对应p4；252cells | 原Si、双Floquet、无PML、quad15、完整80 DtN |
| A4 | trace+port21824、NNZ8184464；CSR SHA150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560 | 每次与qualified F1原方程身份完全一致；p4 FE53084，未改变原A4/A6 |
| 几何PC因子 | 302047392 B，measured NumPy payload（含cell/port） | 构造前预算，maxpatch272<6000、bottom80<2048，全因子<512MiB |
| PC索引/次数/权重/buffer | 3010048 B，derived budget | <512MiB；dense局部临时上界3586048B，无private audit CSR |
| 整树规划与限制 | engineering reserve8GiB；实限制RSS16GiB/warn12GiB，own swap0 | 无cgroup委派，0.5s整树采样停止，包含launcher/compiler/后代；不假称连续内核限额 |

## 原方程实测（dimensionless；绝对port为原数组范数）

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

新结构带来原native残差的部分下降；完整误差仍为量级1，末周期进展不足以取得严格收敛。端口相对closure的分母随状态参与项范数增长，不能把相对值下降等同于绝对端口错误下降。每步真实数据见[完整历史CSV](records/full_residual_history_v3.csv)，每restart PC作用见[PC probe](records/pc_probes_v3.csv)。

## 复用诊断的结论

| 检查 / 身份 | 结果 | 解释边界 |
|---|---|---|
| KSP vs显式Schur | 四个已存快照及最终状态一致 | reported是绝对范数；Schur/RHS与operation-scaled audit为不同分母 |
| native residual映射 | 复用9状态最大7.44e-15；新每步差见[结构记录](records/structure_complete_v3.json) | 原A4有效RHS含非零port贡献；局部恢复误差及端口映射独立核对 |
| 原port范数 | physical旧B0/LIN/NN绝对0.0353871/0.0420845/0.0399233 | LIN/NN相对closure变小不等于绝对误差变小；没有先改loss权重 |
| CPU记录 | oracle实际33、F4-B0实际45，其余已核FE0；V3见成本表 | v2“全部CPU0”不准确，本轮明确纠正；[manifest/source_state/affinity](records/cpu_provenance_v3.json)，未猜填 |
| 固定Q最优性 | R-LIN已是固定native范数中的精确最小残差修正 | 同Q MLP不能优于该最优解；局部/空间选择/接口响应等学习方向需后续review及空间证据 |

## shared-workstation 完整新数值成本

| 新阶段 | 真实clean source | 现场核 / threads | 整树wall s | 整树RSS峰 B | own swap B |
|---|---|---|---|---|---|
| V3-reuse | `b158c5301e7ff59000b15b335672afdb61c5e5e1` | 12 / 1 | 141.744161531 | 1074900992 | 0 |
| V3-overlap | `7fc3f1434cf4f38f43e5244ebfed3a19d0780a26` | 0 / 1 | 2494.75110155 | 945766400 | 0 |

两阶段监督wall合计2636.49526309s，阶段同时整树RSS最大1074900992B（峰取最大、不相加），swap0。新teacher/训练成本0（not_run），复用固定模型的诊断成本包含在reuse阶段；几何setup/数值PC/每步审核probe分别在[结构记录](records/structure_complete_v3.json)。所有成本shared-workstation；负载、缓存和审核频率不同，性能inconclusive，无无争用加速声明。编辑/Git/审阅时间及总会话RSS未持续计量，辅助测试/后处理另列。

## 停止、测试与下一步

| 项目 | 实际判断 / 身份 | 原因 / 证据 |
|---|---|---|
| 新严格p4返回 | 3项均未资格化，diagnostic only | 原A4/port均未达1e-10，[Gate](records/gate_decisions_v3.json)；不得进入p6 |
| 资源与邻影响 | own swap0，持续PSI未触线、邻身份/CPU推进只读记录 | 无可比实时阶段耗时，不能证明零影响或宣称邻性能不受争用；不改邻任务/锁/监督器 |
| 测试 | 48纯数组/协议，4 FE ABI/支撑/旧默认，4准入/监督通过；最终检查另见测试页 | Ruff/compile/diff、protected history/独立Gate与GitHub实际render在交付收口核验 |
| 未运行 | 新teacher、真实误差128维空间对照、训练、fresh qualification、F5、正式RTA/场/通道、短波、GPU | 同一有界结构未解决全局困难方向；停止扩大，保留旧神经负结果 |
| 后续 | 待review根据真实残差/范数/全局方向决定唯一下一设计 | 不扩大同Q网络、不参数扫描、不merge/master；源码保持显式research opt-in |

## 依赖与合入边界

| 分组 | 改动 / 证据 | 边界 |
|---|---|---|
| research core | bounded geometry overlap、可选逐步observer、原协议/新支撑测试 | 无严格资格，不提升默认；既有B0与普通运行不变 |
| Task042 runner/config | V3两dat/独立预登记、明确opt-in dispatcher及活动样本选核 | 旧V2准入默认不改，不操作共享父cgroup或邻任务 |
| compact evidence/docs | v3残差CSV/JSON、CPU纠正、response/两总账 | 原task/review、response_v1/v2、原raw/v2数字逐字保留 |
| do-not-merge | ignored full arrays、原state、JIT、env、权重与运行日志 | 全在NN-Lab；仅本执行分支push，之后review |

本页是V3最新状态，下面保留V2完整历史，其“当前”只指当时。CPU概括以本页逐run纠正为准。

---

# Task042 第二轮：真实首轮试验，严格粗逆未合格

| 项目 | 实际结果 / 单位与身份 | 证据 |
|---|---|---|
| 终态 | `COARSE_INVERSE_NOT_QUALIFIED`；F1、teacher、oracle、CPU训练和三条F4路线已运行；F5 `not_run` | [独立重算Gate](records/gate_decisions_v2.json) |
| 授权 | 用户允许Task042受控共享运行，覆盖本任务§2.3 heavy禁令和全机独占锁；原task/review保留；不代表F0正式review通过 | [授权原文与适用边界](shared_authorization_v2.md) |
| 工作树 / 分支 | `/home/fenics/Projects/NN-Lab` canonical linked worktree；`task42_neural_coarse_inverse` | [隔离](environment_and_isolation.md) |
| 冻结模型 | original Si矩形块13.5nm、1°/phi0/s、p6/h10、同网格p4、完整80个DtN通道；252cells | [真实F1](records/f1_real_components_v2.json) |
| 真实运行源码 | F1 `cca180f875bd22146f2d30fa4d004e372135dfbb`；teacher `b72448bb2117a0221f041f1b47ac41049750a3c7`；oracle `d9de8ad69bfeeac4860e5187e1738c902a3d808e`；训练 `a221d881bae9405c98e351df2b0b9533582e6d50`；F4 `7216efa605bae155ee383fd716c0fae422448b52` | [逐run索引](records/run_index_v2.json)；后续文档HEAD不替代source |
| 候选无全局p4 LU | B0及线性/NN构建全过程没有global p4 factor；只有有界cell/port、43个<=512行patch和128行bottom | [构造与全部F4](records/run_index_v2.json)、[架构](architecture_and_oracle.md) |
| 资源 | MPI1、现场选核CPU0（48独立物理核，无SMT）；数学/编译/训练线程1；nice10/idle I/O；整树RSS hard16GiB/warning12GiB、own swap0 | [资源与影响](environment_and_isolation.md) |
| GPU / 性能 | 两卡持续邻训练，CPU-only；所有成本标 `shared-workstation`，性能结论 `inconclusive` | [时间与内存](accuracy_performance_memory.md) |

粗层直接分解提前存储一套精确求解辅助表，迭代粗逆则反复纠正误差，节省因子存储但可能难以收敛。本轮用固定传统块方法B0处理全部未知量，再分别增加线性低维修正与小型神经修正，检验它们能否把原方程的误差降到严格门限。真正的p4返回需原A4、端口和恢复全部通过`1e-10`；局部误差或训练loss变小不等于返回合格。

## 完成的数值阶段

| 阶段 | 实际结果 | Gate与限制 |
|---|---|---|
| F0历史 | 独立Git/FE/ML/缓存和33解析协议测试；先前因heavy等待 | [response_v1](../response_v1.md)及无后缀records是保留历史；不再把等待状态当本轮终态 |
| F1真实接口 | 原A4=PH A6P相对差`3.366065072840215e-15`；独立p4 Schur作用差`2.3566154699905024e-16`；非零内部/80端口制造解p4/p6原残差`1.2255722548154e-14 / 2.0935547822786585e-14` | 接口通过；F1 B0七个非零载荷在256步失败，全部保留 |
| F2 teacher | 256train/64validation/64heldout，每batch<=32；384对原方程/端口/内部/恒等式均<=1e-10；最坏native`3.959901353972973e-12` | global LU仅离线teacher；destroy且退出后才运行下一阶段 |
| F2可表达性oracle | ranks16/32/64/128全部通过预登记的诊断标准；rank128 validation误差比`.5138245737888352`、最佳native残差比`.3338841772011458` | 仅表示正信号，非严格逆资格；固定rank128继续，未扫描扩大 |
| F3 R-LIN / R-NN | 同basis/FP64/归一化/B0；NN两hidden64、103040参数、300epochs，validation选51；有载训练19.036s | 独立CPU-only Torch进程；heldout不参与训练或选型 |
| F4严格返回 | 三路线各同16 heldout；每路线只有精确零通过，其余15个均256步后未达1e-10 | 无fallback、无数值调参重跑；端口失败独立记录，内部恢复小不改变判定 |
| F5 / 三次合格计时 | `not_run` | 无F4合格路线，不能嵌入p6；不产生official R/T/A、场或通道数据 |

## 同组严格粗返回结果

| 路线/作用 | 严格通过 | 实际 PH b6 原A4残差 | 同 RHS port closure | 非零 RHS 内部恢复最大 | 整树 wall s | 整树 RSS 峰 |
|---|---|---|---|---|---|---|
| R-B0 | 1/16，仅零 RHS | 0.998655 | 0.465472 | 4.70942e-16 | 486.668 | 0.793 GiB |
| R-LIN | 1/16，仅零 RHS | 0.998262 | 0.239496 | 2.11953e-16 | 1239.273 | 0.962 GiB |
| R-NN | 1/16，仅零 RHS | 0.998456 | 0.179987 | 2.20347e-16 | 1238.082 | 0.937 GiB |

原A4残差是完整原方程的相对不平衡量，port closure是端口方程的独立相对不平衡量；门限均`1e-10`。内部恢复达到很小误差，只证明局部消元有效，全局及端口错误仍接近原载荷量级。全部16项与实值见[逐RHS CSV](records/strict_rhs_metrics_v2.csv)和[准确性分析](accuracy_performance_memory.md)。

去全局因子已由构造及容量记录证明；B0、线性降维和NN均未提供合格粗返回。oracle显示线性子空间能表示部分训练/验证误差，但未使严格迭代成功。神经额外贡献没有正信号，不能把表示改善或去因子的效果算给NN。共享负载、缓存及生命周期不同，不能据此宣布正式20%内存/时间改善或10%神经加速；N=1/10/100合格求解摊销与break-even未定义。

## 全过程数值成本及未运行项

全部正式组件尝试（包含4次实现/环境失败）监督wall合计`8250.064 s`；阶段同时整树RSS最大`2.198 GiB`（取最大，不相加），各树swap0。teacher、oracle、训练和各路线分别计费；安装/测试/预检另列，编辑器/Git/只读审阅的总会话内存与耗时未持续采样。所有数值成本均shared-workstation，未启动Task042 GPU，无本任务VRAM分配，PSS及cgroup峰未采样。

原p6物理载荷求解与全部R/T/A/A_volume、R00_s/p/total、复E/H、场/scaled-curl、80通道复振幅/功率均`not_run`，见[统一p6 CSV](records/full_p6_comparison_v2.csv)。p6仅F1矩阵作用/制造解接口验证，不冒充最终物理解。5/2/0.7nm、h/p/角度/几何泛化、GPU训练和无界参数扫描均未运行。

运行中未观测到触线的持续内存压力或Task042 swap，邻worker/监督器身份保留并有CPU时间推进；已有可读阶段记录缺少可比实时耗时，不能证明绝对零干扰，也不能判断邻任务自然阶段变化是否受影响。详见[环境与影响证据](environment_and_isolation.md)。

## 审阅与合入边界

研究接口、参数化监督器、严格checker、有限数值证据和模型总账可审阅；本轮研究粗逆未合格，不作为production默认。[实际变化与依赖分组](changed_files.md)、[测试](test_summary.md)、[数据与模型身份](dataset_and_model_provenance.md)、[response_v2](../response_v2.md)给出完整入口。保留所有失败与F0记录；只推送本执行分支，之后停止等待ChatGPT review，不合并master。
