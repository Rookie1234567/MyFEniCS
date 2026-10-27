# Task43 V15 response（P5诊断完成；原P4失败保留）

V15 修复普通研究入口接线问题，并继续原授权的 P2→P5 工作链。P2 的实际闭包与自由度审计完成；原 A1 primary 的窄后处理续接通过 root-joined q8/q10 和能量闭合门，但原正式 A1 terminal 仍为 FAILED。P4 h 求解的 raw 数值门通过，最终共享 summary writer 因 NumPy 数组不可序列化而退出，P4 terminal 同样保留 FAILED。P5 原槽已完成共同积分诊断，状态为 COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE：q8/q10 均未越过冻结的清晰输出收益阈值，整体精度仍未通过；P5 没有将原 P4 FAILED terminal 改写为成功。

本轮把少量大网格单元切成小单元（局部 h 加密），只测试预先固定的 seed8，并保留相邻面需要的闭包。FE 是约束后独立未知量数；J 把各输出与固定 Y6_1 场的差除以各自容差，取其中最大值，因此 J>1 表示至少一项尚超容差。G（文中 η）衡量全域电场及其旋度的加权相对差，越小越接近这个离散参考，不代表已知连续真误差。ΔJ、ΔG均为R9减h；每新增FE收益再除以6,268。primary 指正常修正之后、额外诊断修正之前的固定场，本轮normal一次、extra零。A_volume表示体内吸收占入射功率的比例。

## 授权、普通错误修复与保留边界

用户明确授权修复普通实现/接线错误并在受影响路径验证后继续；数值 Gate 失败才暂停等待审阅，资源安全门继续有效。V15 给旧 V12 resolver 加入固定 P2_BUGFIX 来源的显式恢复绑定，绑定用户授权、先前 P2R 失败 closeout 和新 joined 产品；旧 V12 manifest、旧 P2R terminal 和失败槽原件未改，解析不扫描目录或挑选“最新”文件。round1 中读取 constraint audit 的键已按 producer 改为 hanging_or_floquet_slave_rows_globally_numbered；真实 P2 路径完成并由 root joined。

P3 原正式 A1_q_attempt3 因 raw scope 表示问题而失败：只读视图把运行中的范围转换为 tuple，而 JSON 序列化保存为标准 list [0, 38412]，raw gate 未接受该表示。主控从原 primary 数组独立复算的 A6、full-active Gram 与 condensed 残差均在固定阈值内，但不改变该正式入口失败状态。依据用户“修复普通bug后继续”的授权，采用只针对这份固定 primary 的非 official 后处理续接：原 partial terminal、源码/合同身份、primary 与 checkpoint 哈希均固定核验，恢复时逐数组核对 P6 系数及 mesh/DOF 索引，通过 raw gate 后才计算 q8/q10 样本和 Av。续接没有重建 PDE 矩阵、调用求解器或额外 correction；原失败记录保持不可变。

P4 主流程已实际得到 h 网格解和已保存 primary；故障发生在收尾 writer 将共享 summary 中的 raw NumPy 数组送入 JSON 编码器。V15 研究入口窄补丁只把这些已持久化数组映射成 NPZ 中的 key、dtype/shape/hash 记录，不展开巨型向量，也不改共享数值核心。P5 使用新 opt-in saved-primary adapter 读取原 FAILED P4 terminal，在固定子目录完成 q8/q10 公共积分诊断；不会制造成功 P4 endpoint，也不放宽普通 pending-candidate reader。P4 失败原件与 P5 的派生诊断并列保留。

V15 没有改变 Maxwell 方程、离散/约束、数值核心、模型、阶次、quadrature、容差、watchdog 或 formal 求解次数规则。旧 V14 的 P2R audit key mismatch、A1 首次 scope-validation fixture 失败、原 P3 FAILED、原 P4 FAILED 及 h恢复接线fixture首轮验证失败均保留原件。首轮h恢复接线fixture验证结束后、root读取器完成终态核对前，compare接线完成了最小快照修复；该首轮source复核只见 compare 文件相对初始快照不同，其他源项相同且输入未变，因此不是运行时输入漂移。

## 定向验证与局部问题记录

固定 P2_BUGFIX resolver/joined-binding focused 集合为 10/10 passed，whole-watchdog 29.47382813040167 秒。A1 scope validation 首次运行 17.657307378947735 秒，2 passed、1 failed、12 not run；失败在 observer fixture 对同一 worker 已创建的 phase file 再要求“必须不存在”。生产 runtime 门未放宽。新 root 上的定向恢复验证为 14/14 passed，whole 22.31426020199433 秒；旧 raw 节点仅在测试字节完全相同的条件下复用。

P4 saved-primary validation 首轮选择了 13 个节点：10 passed、1 failed、2 not run，whole-watchdog 22.533459630794823 秒，采样进程树 RSS 峰 276,164,608 B。唯一已到达失败是 opt-in P5 success 路径的快照集合不一致：前置快照漏了binding文件自身，后置快照包含它，因此比较结束时报 source/input identity changed。主控承认预审漏掉了这一集合不对称。worker退出后、root读取器完成失败终态核对前，compare接线完成最小修复；该失败轮源代码仅 compare 与当时快照不同，其他已绑定源项相同，输入没有改变，不是运行时漂移。修复把binding hash放入共享快照构造，前后集合一致。随后局部验证为4 passed：真实main、opt-in的两个参数和joined-source拒绝节点；pytest 6.59 秒，whole-watchdog 9.225778500083834 秒，RSS采样峰 260,907,008 B，worker/watchdog/launcher退出 0/0/0。另9个未变函数/相同测试字节按先前成功结果复用，合计13个unique节点；对应root gate见 v15_bugfix_sources/h_validation_recovered/h_saved_primary_validation_root_gate.json。该组验证工程接线，不构成PDE科学资格。P5比较记录与watchdog证据分别位于 `benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/comparison/v11_r9_h8_union_comparison.json` 和 `benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/watchdog/summary.json`。P5记录为 COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE，candidate terminal仍FAILED，`official_result=false`、`passed=false`、没有写入selection transition；比较前后source/input身份不变。

| P5 原授权 union comparison | 实测与冻结门 | 结论 |
|---|---|---|
| q8 / q10分类 | 两者均 `NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE`；ΔJ=0.09051462124265441 < εJ=0.12716416232413652 | 清晰输出收益条件未达到；不选择新状态 |
| q8 / q10 G场误差 | q8 η: 3.995683423458671e-5→4.547357272406127e-5；q10 η: 3.9956834234581814e-5→4.5473572724057846e-5 | 两档误差增幅分别为5.516738489474555e-6和5.516738489476032e-6，均小于εG=9.088158796603444e-6；记录ΔG按R9−h定义为相应负值 |
| 主精度阻塞 | h对Y6_1的R00_s绝对差=3.9745473239816143e-6 > 1e-6；J_h=3.9745473239816143 > 1 | accuracy仍 `NOT_PASSED`；此诊断不构成精度资格 |
| FE及参考网格 | R9=110,472；R9_H8=116,740（+6,268）。Y6_1参考为576格、FE=380,160；6×10×6控制为FE=237,600 | 参考与控制是不同对象；h比控制少50.867% FE不能单独证明同精度成本降低 |
| 积分范围 | 公共域350,000 nm³、612模态；q8=565,248点、q10=1,104,000点 | q8/q10各自分类相同；不宣称连续误差或accepted state |
| P5执行 | watchdog whole=1,134.8697960400023 s；采样进程树同时RSS峰=1,621,196,800 B；task-tree swap=0；worker/watchdog/launcher退出=0/0/0，后代清理完成 | RSS为采样同时峰，不是连续高水位；未触及8 GiB硬限值 |

q8样本 `v11_r9_h8_union_q8.npz` 为565,248点、SHA256 `7286c09d6b3f3bb3a7ece1cd46284a9a5faafd6ebbcb213e2568b6a32ed1119e`；q10样本 `v11_r9_h8_union_q10.npz` 为1,104,000点、SHA256 `82d7bc676e23bea0794caf5e16b3d6c28ee02cb18c57cb59e4bfc08a55759f99`。root标准库只读复核耗时49.98319954331964秒，通过2,654项检查，复算保存数组上的E/curl/H/G范数、J和ΔFE收益；源码51项、输入76项前后未变。其限定是owner map只核slot/global-ID内部一致性与hash，没有独立重新搜索几何；散射参考范数及modal参考norm沿用worker保存标量，没有重新生成背景sampler。trace留有7个文件、1,506条原始行（含栈帧）和62个syscall事件（59个getter、3个成功的CPU1 SCOTCH setter），无signal；104个独特栈帧与此前已读帧一致。watchdog记录1,741行资源样本；样本行1737中的3个Z进程cmdline为空且RSS/swap为0，终态核对时host PID/start ticks均已消失。closeout `docs/task43_hp_adaptivity/outcomes/records/v15_bugfix_sources/P5/P5_joined_root_closeout.json` 的SHA256为 `5f2312d3bdf52a410a777e8e119ec8dbf6af992adb8bd575e12e0579e381165d`。

P5完成后，本轮8次support whole累计2,240.4899401497096 s；两次formal累计5,210.411748223938 s。P5没有新增formal PDE dispatch。下一步动作和配额应由最新review明确指定；此处不选seed、不安排新计算。

## P2：真实空间计划与实际自由度

计划程序依据 seed 8、请求根 4 和强制材料根 34，实际把 180 个根单元闭包扩展为 194 个叶单元。闭包是为维持相邻面与周期边界一致而随指定根单元一并细分的集合；这是网格计划，并未装配 Maxwell 矩阵或重新求解场。叶单元次数为 p5:35、p6:159，180 根单元继承关系逐项重算。

| P2 实测或记账项 | 数值 | 身份/限制 |
|---|---:|---|
| 实际自由度 | 116,740 = 36,790 trace + 79,950 interior | measured；P2 空间审计 |
| 对 R9 自由度增量 | +6,268（R9=110,472） | measured；低于固定 exclusive upper 237,600 |
| 约束前 raw / 消除 | 124,012 / hanging 1,820 / periodic 5,452 | measured |
| 预计凝聚系统rows（trace + 612模态） | 37,402 | predicted；非实际 PDE 装配 rows |
| PDE rows、NNZ | not measured | P2 不装配 PDE |
| whole / 进程树 RSS sample peak / task swap | 959.6084092017263 s / 2,211,012,608 B / 0 B | measured；RSS 为采样进程树峰，非连续高水位 |

P2 源码 51 项、输入 41 项按实际 launch 绑定。joined terminal 为 P2_BUGFIX 的 root-verified 产品；字段、资源和产品 hash 见 outcomes/records/v15_bugfix_sources/P2/。

主控的A6/full-active/condensed复算是从原运行保存的RHS、solution及residual数组重算范数和同状态关系；独立A6算子作用由原正式worker完成，本轮恢复没有再施加算子或生成新A6。

## P3 原正式 A1：FAILED 保留，固定 primary 后处理另记

原正式 A1_q_attempt3 用时 3036.0769646498375 秒，terminal 为 FAILED_RESEARCH_SCOPE_CONTAINER_MISMATCH。原运行在 scope 检查失败，q8/q10 和 Av endpoint 没有由原入口完成。主控从同一保存 primary 独立读取并复算：A6 相对残差 8.162860542115928e-9（限值 1e-8），full-active Gram 5.177423112815622e-13（限值 1e-8），returned condensed 5.275175272012167e-13（限值 1e-9）；normal correction 一次后从 5.5046830229695776e-11 降至 5.275175272012167e-13，extra correction 为零。raw 通过不能把原端点标为 q/Av qualified。

授权的 saved-primary continuation 在 44.807101065758616 秒内完成，进程树 RSS sample peak 739,282,944 B、task swap 0 B，原 primary 哈希前后不变。q8/q10 最大场分量相对差约 6.920096e-12（限 1e-5），最大 612 通道功率比差 8.184619648687885e-12（限 1e-7）；采样点 92,160 / 180,000，正权积分体积约 350,000 nm³。实际 Av=0.6915150591709378，能量闭合绝对值 4.103828388224429e-12（限 1e-5）。root 对保存字段做了 1,246 项算术检查。这些是固定旧场的后处理比较，不是新 PDE 解或 continuum convergence。A1 joined gate 为非 official，production_qualified=false；原 FAILED terminal 仍保留。

## P4 原正式 R9_H8：raw 数值门过，末尾 JSON writer 失败

R9_H8_attempt1 使用 194 个叶单元、116,740 个 FE，37,402 行系统，NNZ used/allocated 为 30,072,292 / 36,616,200。一次 normal correction、零次 extra correction；独立 A6 action 用时 521.821879287716 秒。root 从已保存原向量独立复算：

| P4 保存原量 | 实测值 | 固定限值/判定 |
|---|---:|---:|
| 独立 A6 相对残差 | 7.77267194814766e-9 | ≤ 1e-8 |
| full-active Gram 相对残差 | 5.203523992032973e-13 | ≤ 1e-8 |
| returned condensed 相对残差 | 5.323075566556481e-13 | ≤ 1e-9 |
| normal correction 前 / 后 | 7.133919099294296e-11 / 5.323075566556481e-13 | 严格下降 |
| R_total / T_total | 0.2513585633216903 / 0.057125759200644305 | 保存实值 |
| R00_s / R00_p | 0.2513262857473211 / 1.5574751172765498e-23 | 保存实值 |
| A_volume | 0.691515677476035 | 保存积分值 |
| R+T+Av−1 | −1.6303625116620424e-12 | 绝对值 ≤ 1e-5 |

这些保存字段的数值门通过；但末尾 shared summary writer 尝试 JSON 编码 raw ndarray 后 TypeError。whole-watchdog 2174.3347835741006 秒、采样进程树 RSS 峰 7,309,836,288 B、task swap 0 B；worker/watchdog/launcher 退出 1/2/2，后代清理完成。原运行 source 51、input 60 项收口一致。最终 FAILED 优先于日志中较早的临时 official-result 字样；没有 candidate record、storage 或成功终态，不能把数值门通过写成 P4 整体成功。原件、异常和 root recheck 位于 outcomes/records/v15_bugfix_sources/P4_failed/。

修复只作用于 V11 研究入口保存 summary 的薄包装：数组以已有 NPZ key、dtype/shape/hash 引用，避免把巨型数据转成 JSON 列表；共享数学与 writer 默认行为不变。P5 saved-primary adapter 读取并重建所需场和索引，结果是绑定原 FAILED terminal 的非 official P5 诊断，不是伪造 P4 成功记录。

## 状态、费用与科研边界

P5完成后 formal dispatch 仍为 7/8（V15 新增 A1 与 R9_H8 各一次），最后历史槽仍封存；V15 两次 formal whole-watchdog 小计5,210.411748223938秒，8次support whole累计2,240.4899401497096秒。V12/V14 recovery历史2,215.2188096446916秒另列，早期V11 support 853.8004706790671秒另列；不同类别不混加为单次执行时间。P5未新增formal PDE dispatch。

五项能力保持：空间 PARTIAL；selection PARTIAL；accuracy NOT_PASSED；equal-accuracy total cost NOT_ESTABLISHED；iteration NOT_RUN / NOT_QUALIFIED。accepted9/R9 仍是最后接受态，R10 仍为噪声改善门拒绝。P4 的 saved primary 不自动恢复候选资格，P5 比较也不等于接受新状态。A1_R、A2_R、B/C、fresh baseline、成本 campaign、迭代、0.7 nm、NN/FTT 和 merge/master 仍锁定；生产资格 false，无 READY 或 merge approval。P5只给出固定参考输出响应诊断，不形成连续误差或接受态结论。下一步须由最新review明确后续动作及配额；本文不选新seed、不安排计算，也不授权重试或合并。

## 固定q诊断与来源

A1固定原R10空间118,800 FE、q19/q32/R13，恢复后q8/q10的G分别为6.9191197754623055e-12 / 6.919119701391214e-12；R/T/Av为0.2513573038030871 / 0.057127637030078865 / 0.6915150591709378，Av实际吸收form为q19。最大通道差8.184619648687885e-12低于1e-7。旧A2仅复算原数组，无新求解/采样/积分：A6=3.078522812304335e-10，full carrier+modal Euclidean=1.1972486317982494e-11，condensed=3.0440529386035694e-12；q8/q10 G为6.043732933300416e-11 / 6.04373290835214e-11，最大通道差4.5076775645469525e-11。旧A2 Av=0.6915175267406917，规则仍automatic，不能回写成q19。旧A2端点仍INCOMPLETE_NOT_QUALIFIED。二者都不等于整体独立精度通过。

P5每新增FE的ΔJ为1.4440750038713213e-5；q10 ΔG/ΔFE=−8.801433454811793e-10，q8为−8.801433454809436e-10。h改善量未越过εJ，G也没有改善；因此不写transition10。下一轮审阅应明确是否接受本次固定诊断、是否需要补充特定证据，以及下一科学动作/配额/停止门，不能仅以“继续优化”代替任务。

| 阶段 | 实际运行完整HEAD | whole-watchdog秒 | 退出worker/watchdog/launcher |
|---|---|---:|---|
| focused | `05ec419b757ff11daab6e3658dfdc3e333ae0947` | 29.47382813040167 | 0/0/0 |
| P2 | `ffe64470628b8c23e3419c9b6cc21146be927ea2` | 959.6084092017263 | 0/0/0 |
| A1_validation_failed | `bac6da786efd945f32725229e133ed0b66a9b7bf` | 17.657307378947735 | 1/2/2 |
| A1_validation_recovered | `96c57fbb481eef483c4e6dadc3358552d31c448b` | 22.31426020199433 | 0/0/0 |
| A1_saved_primary | `75da89ee77c5879cd23d387464e6d5589911f131` | 44.807101065758616 | 0/0/0 |
| h_validation_failed | `5fa2ff5e5fe130d4fc33d3dafb970546e4bf571e` | 22.533459630794823 | 1/2/2 |
| h_validation_recovered | `d48ee3c389b42387dcff522cba059c0ddb5beffc` | 9.225778500083834 | 0/0/0 |
| A1_q3 | `d4e2be77a90e39d49fc56b4214f3bcc24843ddf4` | 3036.0769646498375 | 1/2/2 |
| R9_H8 | `7beeb78b4d6110b6d0a46a64e1bd0bb91bd9877e` | 2174.3347835741006 | 1/2/2 |
| P5 | `e1ca85df5e181daec7f0e4715e6d43038a1683a2` | 1134.8697960400023 | 0/0/0 |

这些whole相互独立，嵌套阶段耗时不重复相加。标准库P5原件核算49.98319954331964秒单列为静态读取费用；手工审阅、编辑、复制、Git和未逐项计时检查均not_measured，不补造总wall。所有局部读取错误、两次fixture失败和正式两次失败保留，详见[最终机械记录](outcomes/records/v15_bugfix_sources/local_mechanical_notes_final.json)。

| 定向测试运行 | 当时整个测试文件SHA256 | 实测/历史边界 |
|---|---|---|
| focused | `69bbfcd4135bba7c7e2a1beee8a4de19a33be35787db346bb1b26b73ffdcb63d` | 10 passed |
| A1_validation_failed | `bcd9ca6405cb3075d228b6a0255eaedf7ea6f23b8023421af7a78f324b4baed1` | 2 passed / 1 failed / 12 NOT_RUN |
| A1_validation_recovered | `87e412818d5e2bb78d1e0f62501d016aea4baf265dd74c619ee1e1417d27e9ae` | 14 passed；另1未变raw节点历史复用 |
| h_validation_failed | `336d88e3005525780e83fe5ea940f4c5ecf1f6572cf281f55fa156d1a04ddf4c` | 10 passed / 1 failed / 2 NOT_RUN |
| h_validation_recovered | `336d88e3005525780e83fe5ea940f4c5ecf1f6572cf281f55fa156d1a04ddf4c` | 4 passed；9未变节点复用，合计13 unique |

最终P5执行源码HEAD为`e1ca85df5e181daec7f0e4715e6d43038a1683a2`；本次后续文档提交不是运行HEAD。当前变更base为`12c7d4b2d35d033defead807e3e4c5d3407dc85f`，数值基线为`405e3aff42ac421a4c99315df1ed9b96941ecbe4`。源哈希、逐次launch/输入、测试XML和费用见[V15机器结果](outcomes/records/v15_bugfix_and_scientific_results_v1.json)、[P5主控联合记录](outcomes/records/v15_bugfix_sources/P5/P5_joined_root_closeout.json)及[证据导航](outcomes/records/v15_bugfix_sources/README.md)。共享数值核心/activation/ABI未改；没有重跑全仓pytest、旧20项或完整p6 witness，旧全仓收集/ABI阻塞仍有效。本次只取得指定研究路径的有限证据；P4写出器修复经过fixture，未作新的正式PDE重跑验证。
