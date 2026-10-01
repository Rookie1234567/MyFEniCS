# Response V9：p5精度续审与全参数阻尼GN已完成

本轮完整A–E授权矩阵已执行。p5参考合格；p4/p5的场变化显著缩小，但curl/H尚未过门限。两条无标签GN均未解出原p3，条件监督诊断自动完成且均未达到部分表示门限。没有严格求解、GN研究正信号或神经增量；本轮停止等待review。

| 身份 | 准确值 |
|---|---|
| 分支 / 显式tracking | task42extra_feinn_5nm / refs/remotes/origin/task42extra_feinn_5nm |
| Review V8发布 / 审阅基线 | 678a1ef5ed5aba9334f05569a6dec04c80e21be4 / 52e65aa24de3c22ae9af1ae42d25706cf51b395c |
| 冻结base | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff |
| canonical common Git | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git |
| linked worktree / 环境 | /home/fenics/Projects/NN-Lab-V2；工作站原生Linux；独立FE/ML activation |
| 运行/检查源码与文档HEAD | 以如下source表和run_index绑定；最终发布及tracking见records/git_delivery_v9.json，最终HEAD另在交付回复报告 |
| 默认/生产/合并 | ordinary default保持；production initialization false；NOT_APPROVED |

## 实际执行与方法

GN用网络参数的小改动预测残差的变化，再用真实目标验证方向。它更新全部8966实参数，保持全部31968复FE系数和40端口；不是冻结195维末层，也不是一般loss的完整Hessian。一次outer含多次参数方向作用和试探，不是epoch，不能与旧L-BFGS closure当同一种工作量。小模型C每路线仍新建准确稀疏G因子，是RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；没有global Maxwell训练因子。

| 包 | 实际完成 / measured结果 | 边界 / 证据 |
|---|---|---|
| A | p5参考合格；唯一新增numeric；p4/p5仍有curl/H敏感性 | p_ladder_v9.md；p5_authority_v9.json |
| B | GN/JVP/实伴随/K/真实C500/batch/事务资格通过 | gn_checks_v9.json；targeted_tests_v9.json |
| C | plain与phase均正常预算冻结；原p3未解合格；GN信号false | pde_comparison_v9.json；inner_solver_history_v9.json |
| D | 条件自动触发；两条独立监督FIT-GN均正常预算冻结；三项1%门限未过 | fit_comparison_v9.json；D权重不反馈C |
| E | 独立q15/q30重建、FE compare-only、原字段checker通过；渲染另列 | gate_decisions_v9.json；run_index_v9.json |

## 同p3的冻结验收

| 路线，原V1同p3评分 | native / augmented | 散射E L2 | 散射curl/H | E_G | 独立能量闭合 | 结论 |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 1.0285051156 / 1.0285051156 | 0.9989232163 | 0.9989423061 | 0.99894183584 | 0.4157492147 | 无标签未合格 |
| V9-PHASE-DAMPED-GN | 1.0187461988 / 1.0187461988 | 0.43715907484 | 0.43778332738 | 0.43776795997 | 0.12094192809 | 无标签未合格 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 11.001030573 / 11.001030573 | 0.068217087643 | 0.1000521103 | 0.09939045116 | 0.014917309507 | 监督表示门限未过 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.8082166866 / 0.8082166866 | 0.014403534682 | 0.013024032447 | 0.013059766413 | 0.0028868109962 | 监督表示门限未过 |

严格 native/augmented/原total≤1e-6，场/复通道≤1e-4，功率/独立能量≤1e-5、逐级功率≤1e-6，均未放宽。D的G/L2/curl三项均≤1e-3/1e-2才是表示正/部分见证；本轮未过。完整total/scattered E/H/curl、六点复E/H、四类各40级复通道、逐级功率、区域和实际分母见[GN完整结果](outcomes/damped_gn_v9.md)、[PDE原字段](outcomes/records/pde_comparison_v9.json)、[FIT原字段](outcomes/records/fit_comparison_v9.json)及对应CSV；不拟合整体相位。

| V9路线，仅diagnostic | R | T | A_balance | A_volume | R00_s | R00_p | R00_total |
|---|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 0.83742149248 | 0.11324361848 | 0.049334889034 | 0.46508410374 | 0.83732200974 | 4.9136786443e-10 | 0.83732201023 |
| V9-PHASE-DAMPED-GN | 0.79552935118 | 0.056384531239 | 0.14808611758 | 0.26902804567 | 0.7955167162 | 3.6564527673e-07 | 0.79551708185 |
| V9-PLAIN-FIT-GN-DIAGNOSTIC | 0.82174534833 | 0.036121409888 | 0.14213324178 | 0.15705055129 | 0.8122280192 | 0.0016546189228 | 0.81388263812 |
| V9-PHASE-FIT-GN-DIAGNOSTIC | 0.81034611294 | 0.032231395236 | 0.15742249183 | 0.15453568083 | 0.81031486242 | 2.1748139964e-05 | 0.81033661056 |

功率均为diagnostic。C能量闭合误差0.415749/0.120942；D为0.0149173/0.00288681，均超过1e-5。MPC/端口恢复与原方程验算单列，不能拿端口消元准确替代体方程通过。

## 同成本与标签

| 同表示共同窗口 | 目标s | GN保存差距s | V8差距s | native下降倍数 | aug下降倍数 | 信号 |
|---|---|---|---|---|---|---|
| V9-PLAIN-DAMPED-GN | 9291.6953416 | 97.469593144 | 0.87033197901 | 1.0094418096 | 1.0094418096 | false |
| V9-PHASE-DAMPED-GN | 8745.0180056 | 1057.6807378 | 0.750603989 | 1.2649844162 | 1.2649844162 | false |

两种表示均未达native/augmented至少10倍下降和散射L2/curl≤0.1的联合要求。phase共同时间只保留到目标前约1057.68s的审核点，此差距明确保留，不能称精确同一时刻比较；没有插值、挑最佳场或重放历史。最终GN与旧V8-LBFGS的同口径结果也完整列在结果页。

| 数据边界 | C无标签GN | D监督FIT-GN |
|---|---|---|
| reference_used_for_training / features_reference_exposed | false / false | true / true |
| pde_only_solve / benchmark_previously_seen | true / true | false / true |
| production_initialization_allowed | false | false |
| pde_only_solver_qualified / official_candidate_results | false / false | false / false |
| 初值 | 各自V8-C Adam500 | 各自V8-D Adam500；未混用C/best/last_trial |
| 旧optimizer历史 / 新Adam更新 | 不继承 / 0 | 不继承 / 0 |
| p4/p5或D权重供C训练 | 禁止且白名单无此数据 | D权重不回流任何无标签路线或新问题 |

## p序列与资源

[p序列审计](outcomes/p_ladder_v9.md)：p5为146400独立复FE，准确凝聚后54280行、30734728NNZ；只新增一次参考symbolic/numeric/solve，不重求p3/p4或新建Gram。native/augmented1.22906e-11，独立total6.76137e-12，体吸收闭合7.03215e-13。p4/p5散射E L2差2.15910e-4、curl差1.17945e-3、六点total H差1.40896e-3；R/T/A/A_volume和逐级功率差过1e-4，但curl/H与区域未过1e-3，故P4_P5_SENSITIVITY_OBSERVED。一次p序列不证明连续/h/端口收敛。

| 新增包 | 本页冻结账 / s | 限额 / s |
|---|---|---|
| A | 954.36190151 | 7200 |
| B | 204.88059772 | 3600 |
| C | 19014.926468 | 21600 |
| D | 4846.8746953 | 7200 |
| E | 349.44980168 | 3600 |

本页冻结新增保守账25370.493464s（约7.0473592956h），旧账74341.02060587064s全部保留，累计99711.51407s。旧失联3284s和重放未删。后续浏览器、检查器及交付尾段补记[最终资源JSON](outcomes/records/resource_costs_v9.json)，不改本页数据冻结快照；旧Adam前缀计入各逻辑路径，不在全项目账重复收费。

数值全过程同时树RSS最大7190847488B（约6.70GiB），C两条约1.18GiB，D约0.52/0.58GiB；自身swap均0。CPU-only/MPI1/数学和Torch线程1，现场空闲物理核；数值warn12/hard16GiB、factor内部12GiB，轻检查/浏览器2GiB。各启动保留max(128GiB,10%有效总量)系统余量、384GiB邻增长和自身预算；未修改其他项目。约0.5s采样不是连续内核cgroup上限，tmux管理开销另列。p5释放factor/KSP/无用矩阵后RSS6624419840→381079552B，再完整后处理。

两条C fresh G setup约66.85/67.03s，2525/2067次准确solve约619.66/590.01s，最大真相对残差9.52e-13/1.43e-12；因子释放前后均记录。D无G因子/Gsolve，训练A/AH均0。来源、计数、mu/h0/d_G、PC及接受/拒绝历史见[内层记录](outcomes/records/inner_solver_history_v9.json)。18/30/55/103次未提交K作用仍收费；内部未完成CG/PC逐次分解没有保留，写NOT_RETAINED，不能由完整PC数0声称没有尝试或PC无效。

## 自主修复、源码和测试

本轮自行解决了小p4资格的配置阶次不一致、八单元资格网格不解析M5缺口而误触几何Gate，以及检查器两个未使用名称。两次资格失败、lint失败和所有辅助费用保留。另修正索引/记录读取假设，并先验阻止FE分派导入Torch、非有限试探JSON和标签混入；这些预防改动没有冒充真实数值故障。四条GN无故障重启，未重复Adam或旧L-BFGS；完整failure→hypothesis→change→test→retry见[repair_log_v9.json](outcomes/records/repair_log_v9.json)。

定向测试、真实C500接口资格、事务/PC测试及最终原字段checker通过；未full pytest、重装ABI或让FE顶层import Torch。没有GitHub Actions，不宣称CI。所有正式入口先clean实现commit再run，下表实际source与最终文档HEAD分开。

| 正式阶段 | 实际 source SHA | 完整launcher秒 | 同时数值树RSS峰 bytes |
|---|---|---|---|
| v9_p5_checks | f5b3c7d93af2cb57e3e4e0de48c4d23997d7f4f7 | 489.90165027 | 1695006720 |
| v9_p5_reference | ee295a30c2631a8f019ba3e435b83d211ea051a7 | 147.77891903 | 7190847488 |
| v9_p_ladder_compare | 2f7d6c0f6d9102742c951907df25efa04aaf16cc | 260.03396415 | 486072320 |
| v9_gn_checks | 2f7d6c0f6d9102742c951907df25efa04aaf16cc | 178.73114433 | 1256349696 |
| v9_plain_gn | bc4ecb2192e687273926e1d1f0ce5e7df4b78542 | 9528.2566436 | 1264013312 |
| v9_phase_gn | ebff76949c78560187d836830483172faf0cfc9a | 9486.6698242 | 1264005120 |
| v9_gn_reconstruct | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 40.910086819 | 553992192 |
| v9_gn_compare | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 57.939700314 | 479256576 |
| v9_plain_fit_gn | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 2440.8059746 | 555671552 |
| v9_phase_fit_gn | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 2406.0687207 | 627761152 |
| v9_fit_gn_reconstruct | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 42.918935966 | 548253696 |
| v9_fit_gn_compare | 556cb3e608db21c5a2fd44cb97cc553ae5d70e5f | 59.305431874 | 477523968 |

## 已排除与仍不确定

| 因素 | 已有证据 / 结论边界 |
|---|---|
| 数据/ABI/插值/复布局/导数 | 固定hash、complex128/int64与FP64、完整边/面/内部矩、非单位MPC、JVP/VJP/K见证和独立参数重建通过；有限见证不排除所有软件错误 |
| 求积/度量身份 | 四条q30漂移≤1.85e-12；G与独立L2/curl能量恒等式差≤6.17e-14；未靠改积分改善结果 |
| 目标与非线性模型 | phase C有21次拒绝、25次inexact试探；有效loss下降未转成严格原方程和准确场，不是工程异常 |
| 内层及网络代价 | C plain完成两次rank32 PC；完整作用和未提交尾段全部计费；JVP/VJP是主要费用，不称matrix-free必然更快 |
| 表示还是优化 | phase监督场比plain好，但新GN两条监督结果仍未过1%；未获得严格可表示见证，也不能证明网络数学上不可表示或存在可信驻点 |
| 离散精度 | p5自身准确满足方程，p4/p5功率差过1e-4但curl/H仍未过1e-3；不能用p误差解释NN对同p3方程失败 |
| 资源或失联 | 四条COMPLETED/WALL_BUDGET_SAVE_RESERVE、failure null、自身swap0和清场；不是OOM、INTERRUPTED或监督失败 |


下一轮仅建议先资格化等价的分块切线/激活复用：在这四个已冻结状态上做有界 JVP/VJP 配对与计时，保持原矩、参数导数和目标完全不变，再决定是否值得开展同预算 GN 对照。本轮实测 JVP＋VJP 占 C 新段约90%、D约97%–98%，是可定位的主要费用；该建议不授权继续训练、换 loss/PC、扩大模型或放宽门限。

目标尺寸5nm与0.7nm仍not_run/not_qualified。未自动p6、h细化、多端口、多载波或扩大网络，未将p5或监督权重接回C/Task042。合并未获批准。

## GitHub渲染与交付

本地结构检查与GitHub浏览器检查分别登记。新Review V8及关键新增页的实际浏览器结果、发布SHA和截图hash见[render_check_v9.json](outcomes/records/render_check_v9.json)；以该记录的真实状态为准，结构检查不能替代视觉PASS。精确tracking/ahead-behind、clean和本任务清场快照见[git_delivery_v9.json](outcomes/records/git_delivery_v9.json)。只推送HEAD:refs/heads/task42extra_feinn_5nm，不amend/强推/merge。
