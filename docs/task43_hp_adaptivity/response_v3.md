# Task43 Response V3：有限诊断收口

本轮只尝试提高 q 并检查一次额外同因子回代；R 固定为 R13，没有运行 R 诊断。提高 q 会增加体积、入射和端口积分所用的采样点，用来观察积分近似对当前离散结果的影响。额外回代复用已经分解的矩阵，检查代数误差对输出的影响，但会让大因子更久地留在内存中，并增加回代与输出时间。这些检查都不改变网格，因此不能证明空间精度通过。

结论为 `PARTIAL / CONTROLLED_NEGATIVE`。V1 的 accepted9/R9 选择不变，最终空间精度和相近精度下更少独立未知量仍未证明。V2 的三次正式尝试均未得到完整 q/R 结论。V3 按授权又 dispatch 两次：A1_q2 因实际入口没有建立要求的 workflow phase ledger 而由主控受控停止；A2_q3 确实建立了 ledger、构建 Y6_1 网格并进入求解/extra 校正，但 7200 秒墙钟门到期后不完整停止。它留下了可读的 primary 与 partial 数据，也留下 extra 校正全显式残差未严格下降的负项；没有完整 native summary 和端点比较。两次都不能解读为 h/p 方法的数值失败或完整通过。

本轮审查依据为 Task43 V2 review `fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12`，在其之前的 V2 回应/阶段收口提交为 `fd4a63098893a82374f43f8c3066b74285e9c020`，冻结base为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。A1_q2实际源码HEAD为`28dd150ac2917d6df272324e0b00b960064dad00`，A2_q3为`d92c210a6704de99362f5e696d157d6c356d9efd`；两次attempt的源码、输入、launch和watchdog身份见closeout compact。

## 对 V2 review 的逐项回应

| 审查项 | 本轮处理和结果 | 结论边界 |
|---|---|---|
| V2-01：最终科学验收未完成 | 保留 R9 为最后接受状态、R10 为未接受诊断；A1_q2 与 A2_q3 都没有完成可资格化的完整端点比较 | `NOT_PASSED`。A2 的 primary 残差通过只说明已保存状态满足列出的方程残差门，不是空间精度或端点通过 |
| V2-02：全仓测试没有有效测试体证据 | 保留原全仓 pytest 的 collection 结果：1 skip、8 errors、测试体0执行。V3 focused 为57 passed/1 skipped（source `81c97e7c`），最终仅变化的生命周期节点另1 passed（source `fc260b1e`）；实际native WorkflowLedger no-mesh fixture另1 passed/2.51s（source `28dd150a`，测试文件当时为untracked，按精确test SHA绑定）。本轮文档收口后，现有registry Markdown合同测试再执行1次，5 passed/0.06s | 全仓/生产测试门仍未通过；这些定向回归不等于现场A1接线通过，也不替代全仓测试。Ruff全文件77项与review base 77项逐类别相同，新改动行诊断0；本轮新增Markdown链接45项无缺失，JSON parse与diff-check通过。没有CI声明 |
| V2-03：primary 结果未及时持久化 | 加入 before-extra 原子包、逐阶样本保存、真实 MPI1 bcast/JSON/NPZ 运输回归和 extra、transport、sampler、后处理异常注入；A2_q3 实际保存了 primary 包及 q8/q10 primary 样本 | A2 现场保留满足要求的 primary 核心资料，但 A1_q2 的真实入口未创建 WorkflowLedger，暴露出组件测试没有覆盖真实 A1 workflow 接线；主控在装配中止。旧 READY 作为历史记录保留，但已被该事实反证，不能再授权派发 |
| V2-04：A2 的 q19 算子不等于 `A_volume` 显式 q19 | 同一旧 Y6_1 保存场的 automatic、q15、q19 体吸收积分均复核；automatic/q15 为 `0.6915175267821607`，q19 为 `0.6915175267821573`，差 `3.4416913763379853e−15`。A2 native 新算子实际使用 q19，吸收积分仍是 automatic 配置 | 这是旧场纯后处理支持证据，不能回写旧配置，也不是新端点 `A_volume` 的 q 收敛资格；A2_q3 的 native summary 未生成 |
| V2-05：历史尝试/终态计数未独立完整核验 | root 扫描全 Task43 artifact 中 launch 与 attempt 入口，识别并去重两个 prelaunch alias；独立重算 V2 三次及 V3 两次真实 watchdog 资源、source/input hashes 和进程终态 | 总计 5 次 formal dispatch / 6 个原额度；各次结果和缺口见[closeout compact](outcomes/records/v3_formal_diagnostic_closeout_v1.json)、[G0–G3证据索引](outcomes/records/v3_root_pre_pde_audit/index.json)及 A2 root terminal audit |
| V2-06：阶段标题/汇总时序 | 将 V2 阶段一无新 PDE 的语句限定为当时快照，并在最新段说明 V3 后续两次 dispatch；原 V1 inventory 未重写 | summary 中“16次求解/5份导入场”现明确属于 V1 inventory 历史范围；V2/V3 另列，不用旧计数暗示全任务至今只有 16 次 |

## V3 两次正式 dispatch

| Attempt | 实际执行与结果 | 全流程资源/终态 | 资格结论 |
|---|---|---|---|
| A1_q attempt2 | source HEAD `28dd150ac2917d6df272324e0b00b960064dad00`。构建 180 格网格并进入装配；尚无因子分解或求解完成证据。主控发现真实 A1 route 未建立 workflow phase ledger 后，向已核身份 watchdog 发 SIGTERM 受控停止。原 watchdog 分类仍为 `USER_CONTROLLED_STOP`，主控补充原因 `G2_A1_WORKFLOW_LEDGER_NOT_WIRED` | watchdog whole wall `159.36019697086886 s`；采样树 RSS 峰 `948682752 B`；task swap 观测峰 0；后代最终清除。见[A1 dispatch/停止原件](outcomes/records/a1_q_attempt2/dispatch_and_stop_record.json)及[A1 root终态审计](outcomes/records/v3_root_pre_pde_audit/A1_q2_terminal_audit.json) | 工程入口缺陷导致受控中止；不是离散数值失败。没有 primary endpoint、完整 residual 或完整 q 比较 |
| A2_q attempt3 | source HEAD `d92c210a6704de99362f5e696d157d6c356d9efd`。Y6_1 native p6、576 cells、FE=380160（由389832 carrier减9672受约束行推得，亦为120960 trace+259200 interior）；R13 612 modes；实测 q19 volume operator、q32 incident/port、unscaled mode policy。矩阵121572²、实测stored NNZ111681742、allocated NNZ128135952；此前Y6 stored-NNZ预测112458734另列，不推断差异原因。装配wall `4771.323931380641 s` | watchdog whole wall `7213.133929461241 s`，其中按资源时钟推导 stop event 在 `7200.713435649872 s`，余下 `12.420493811368942 s` 为停止后清理；配置门仍为 7200 s，没有延长计算。5971 samples，树 RSS 峰 `27098828800 B`，task swap 峰 0。watchdog 报 cache-stability cleanup exception，但最终 descendants-cleared=true、无剩余 PID；清理门仅为 limited，不称无条件通过。原始进程命令摘录见[实际launch excerpt](outcomes/records/A2_q3_actual_launch_process_excerpt_v1.json)；终态见[A2 terminal audit](outcomes/records/v3_root_post_pde_audit/A2_q3_terminal_audit.json) | WorkflowLedger真实接线成立；运行在完整端点前被墙钟门停止。`run/p6_condensed_direct_summary.json` 与 `run/comparison_record.json` 缺失，不补造 |

A2_q3 在正常 correction 后、extra前保存的primary状态为：凝聚`b−Ax`相对残差`3.0440529386e−12`（门限`1e−9`），full-active transformed residual`1.1972486318e−11`（`1e−8`），独立原方程A6`3.0785228123e−10`（`1e−8`）；normal correction raw audit通过。root从保存的primary原向量重算后得到condensed`3.0440529386035694e−12`、A6`3.078522812304335e−10`、full-active`1.1972486317982494e−11`，normal 1次修正由`2.2945939789534043e−9`降至`3.0440529386035694e−12`，MUMPS调用计数为symbolic/numeric/solve=`1/1/2`且INFOG(1)=0。独立raw audit的完整条目和数组身份见[tracked primary audit](outcomes/records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json)（SHA256 `95524c004138eecbf59ce6a61cc87426558ea10746caee1f06164d93273d49ba`）。

root还独立重算了old Y6_1→primary的612通道Poynting：最大逐通道功率绝对差`4.507666462316706e−11`（门限`1e−7`，0项失败），四组边界复幅最大入射地板归一差`6.139994079567577e−11`（`1e−5`），能量闭合`5.071976172388304e−11`（`1e−5`）。q8/q10样本各有516096/1008000个Gauss点，权重为正且重建规则有效，积分域体积约350000 nm³；E/H、散射E/H和G的最差归一差为`6.04423083302925e−11`（`1e−5`），不作相位拟合。`A_volume`来自已hash绑定的材料积分记录，本次没有重新积分。root已独立复核已保存的primary场与原向量，但native `comparison_record.json`仍未生成；因此这些只表示primary partial组件各自满足差异门，不是完整q/R资格或endpoint通过。五平面样本12800点也已保存。

额外一次 same-factor 回代有明确负项：full-active explicit relative residual 从 `1.1972486318e−11` 增至 `1.2068417985e−11`，虽两者低于 `1e−8`，但没有严格下降，因此 `FAIL_UNCONTROLLED_EXTRA_CORRECTION`。凝聚 residual 从 `3.0440529386e−12` 降至 `2.4209863927e−12`，A6 从 `3.0785228123e−10` 降至 `3.0781012464e−10`，仍均低于各自 hard limit。额外残差向量没有保存，故这些 extra 数字是原 stage ledger 标量，未能从 extra raw vectors 独立复算；不以另外两项下降掩盖 full-explicit 负门。extra q8/q10 样本和最终比较记录均未产出。完整逐项原件 hash、终态、缺失文件和 raw-vs-derived 边界在[closeout compact](outcomes/records/v3_formal_diagnostic_closeout_v1.json)。

## 总额度、能力与合并边界

工程门、模型数值资格和合并资格须分开判断。V3有限回归与root代码审查覆盖了留证helper、native adapter和故障分支，但A1真实route在dispatch中没有写WorkflowLedger，故该分支G2实际未满足，原A1 READY失效；A2真实native入口的phase/stage ledger成立，然而A2 endpoint仍`INCOMPLETE_NOT_QUALIFIED`。V1/Stage1旧66文件overlay和组件测试不授予新增native A2分支production资格。合并状态`NOT_APPROVED`。

| Gate | A1_q attempt2 | A2_q attempt3 |
|---|---|---|
| G0：清单、冻结输入与身份 | dispatch前门通过；终态source/input posthash和资源由独立审计复核 | 60源码/47输入及实际launch/ABI身份绑定，终态posthash和资源行通过独立复核 |
| G1：失败安全和结果留证 | helper及故障注入组件检查通过；实际dispatch未到primary留证，现场缺口属于G2的WorkflowLedger接线 | actual native ledger、primary-before-extra原子包及q8/q10样本已写出；primary原向量和样本由root独立算术复核 |
| G2：真实入口phase ledger | `NOT_MET`；实际路线没有建立WorkflowLedger，触发主控受控停止 | `MET`；native入口写出phase与stage记录并运行到recovery |
| G3：冻结参考/observable前置核验（旧场Av规则、612模式、q8/q10点权与H/背景/reference方向） | `PASS`；读取并核对冻结旧参考输入，未产生新的primary端点 | `PASS`；相同冻结输入门通过；这不等于运行后的完整endpoint比较 |
| G4：源码/输入、scoped tests、CPU1/ABI/资源计划及对应root READY | dispatch前`PASS`并获得仅授权A1_q2的一次READY；该额度已耗，之后现场G2失败使READY失效，不授权重试 | dispatch前`PASS`并获得仅授权A2_q3的一次READY；该额度已耗，A2组3/3封闭，不授权A2_R或重试 |

两份V3 READY都只对应已完成的单次dispatch，不再产生后续授权。运行后资格另行判断：A1因未到primary endpoint而无新数值结论；A2 primary部分观测由保存原件独立复核，但extra full-active residual严格下降门失败，且完整comparison record缺失，因此端点未资格化。总预算5/6，剩余一个槽封存。V2/V3的G0–G4紧凑状态也记录在[closeout compact](outcomes/records/v3_formal_diagnostic_closeout_v1.json)；其中G0历史dispatch枚举和V1/V2阶段证据不替代本表对两条V3真实入口的区分。

| 能力 | 当前结论 |
|---|---|
| 空间 | `PARTIAL`：R1–R9 的既有局部 p-up 闭环保留；level2 与跨 h 转移未资格化 |
| 选择 | `PARTIAL`：冻结选择停在 R9；R10仍因 G 改善未超过冻结噪声而拒绝；V3 partial 输出不反馈或改写选择 |
| 精度 | `NOT_PASSED`：R9的两个零级 s 功率差仍高于 `1e−6`；A1/A2新诊断没有完成完整端点门 |
| 同精度成本 | `NOT_ESTABLISHED`：没有通过相近精度/更少独立 FE 的候选对照，也没有同精度全过程成本结论 |
| 迭代 | `NOT_RUN / NOT_QUALIFIED`；0.7 nm pilot亦未运行 |

原总额度最多 6 次，当前正式 dispatch 为 5/6。A1 使用 2/2，A2 使用 3/3；A1_R、A2_R、B、C均不运行，剩余 1 个槽封存，不再跨组调配、重试或启动求解。V2三次 formal watchdog wall 小计 `4915.1723896381445 s`；V3两次为 `7372.49412643211 s`；五次合计 `12287.666516070254 s`。RSS 峰不可相加。支持性后处理、组件、预检与未监控检查另列于[closeout compact](outcomes/records/v3_formal_diagnostic_closeout_v1.json)和[V3 pre-PDE audit index](outcomes/records/v3_root_pre_pde_audit/index.json)；这不是全 campaign 成本。

V1不可变记录和既有 accepted reader 保持原样。新增 native A2 opt-in、adapter、observer 留证和比较器仍是 research-only；不能借 Q03 的旧 66 文件 overlay 或 V1 PDE 把新分支提升为 production。Task43 执行分支只等待外部 ChatGPT 审阅；没有 merge approval，也没有合入 master。没有 CI 通过声明。
