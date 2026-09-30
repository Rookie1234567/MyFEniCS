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
