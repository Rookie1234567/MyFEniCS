# Task042 Response V2：完成首轮真实试验，严格粗逆负结果

| 身份 / 交付 | 实际值 |
|---|---|
| branch / upstream | `task42_neural_coarse_inverse` / `origin/task42_neural_coarse_inverse` |
| pwd / toplevel / worktree | `/home/fenics/Projects/NN-Lab`，本身为canonical登记linked worktree，无嵌套clone |
| common Git / origin | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / `git@github-myfenics:Rookie1234567/MyFEniCS.git` |
| base / 初始任务锚点 | `ccd357885f7f9be84efe3be07868cc94f13d93fc` / `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`，均祖先 |
| 本轮起点HEAD | `a76e0435a40139dd6d2a31f0726fb229c7adaff8`，开始时local/remote相同、clean |
| 最后clean实际数值HEAD | `7216efa605bae155ee383fd716c0fae422448b52`，三条F4同source；更早真实source见后表 |
| 最终交付HEAD / 状态 | 后续报告提交不作为数值source；精确push后HEAD、clean/ahead0/behind0由最终Git回报及[发布核验](outcomes/records/publication_checks_v2.json)记录 |
| 终态 | `COARSE_INVERSE_NOT_QUALIFIED`；F1/F2/F3/F4完成，F5 `not_run`；停止等待ChatGPT review |

## 用户共享授权及资源路线

用户2026-09-28明确授权Task042在其他heavy仍运行时受控并行，覆盖仅本任务task.md §2.3“已有heavy禁止FE/JIT/teacher/训练/PDE”及必须独占全机heavy lock的要求；允许Task042共享profile及自有非阻塞锁。它不取消精度、资源、provenance、停止条件，不宣称F0正式review通过。原task/review、response_v1和F0数值records保持原内容；[授权完整记录](outcomes/shared_authorization_v2.md)。本轮不再以heavy_present本身作为等待条件，实际启动并完成下面数值阶段。

每个负载前现场只读检查CPU拓扑/worker-supervisor-loader线程亲和性/两次CPU样本、MemAvailable、cgroup祖先余量、磁盘和GPU。本轮实际选CPU0，48独立物理核、无SMT；不是使用历史CPU14或永久保留CPU0。MPI1、数学/编译/后处理线程1；torch.set_num_threads(1)、torch.set_num_interop_threads(1)、Loader workers0，float64实虚通道、2hidden64/300epochs预算保留。两卡持续训练，CPU-only `.venv-ml` Torch2.7.1+cpu，未等待GPU、安装CUDA或改卡。FE保持complex128/int64同ABI，只读复用原生prefix，所有src/可写缓存/输出为NN-Lab，ML和FE分进程。

Task042自身nice10/idle I/O；自有flock防重复，内部只一个阶段，teacher/训练/candidate先释放并退出才下一阶段。整树RSS hard16GiB/warning12GiB包含launcher/worker/JIT/编译及全部后代，own swap0。无可写独立cgroup委派，实际用0.5s采样整树阈值/专用subreaper清理，不冒充内核cgroup连续限制；已以setsid grandchild触线实验验证清理且sibling存活。原system reserve216310038528B另加邻增长规划128GiB和自身16GiB；disk>=50GiB/artifact<=20GiB，PSI持续触线或监督失效仅撤本任务，未修改邻锁/亲和性/优先级/watchdog/运行文件。

全过程自己的健康记录未显示持续资源压力，swap0，各run后代清场；固定邻PID/start_ticks保留、CPU时间推进。现有短phase记录缺少可比实时阶段耗时，不能证明绝对零干扰，也无足够证据判断邻计算性能退化；未读邻巨大日志或smaps。所有成本标shared-workstation；缓存、负载、生命周期不一致，性能结论inconclusive。[环境/影响](outcomes/environment_and_isolation.md)、[现场snapshot](outcomes/records/shared_workstation_snapshot_v2.json)。

## 完成的真实数值工作

粗层LU相当于预存精确求解辅助表；候选用反复作用原方程来求解，少存全局因子，代价是更多迭代和审核。B0固定有限局部块处理全空间，R-LIN增加线性低维补偿，R-NN用同basis尝试额外非线性补偿。NN只是内层辅助PC，真正返回依旧需完整原A4/port/recovery<=1e-10，合格后才能交给原p6/BAL_H。

| 阶段 | 实际结果 | true clean source SHA |
|---|---|---|
| F1原接口 | original13.5nm、p6/h10、252cells、173802/53084 FE storage、80通道；A4=PH A6P差3.366065072840215e-15；p4独立Schur差2.3566154699905024e-16；非零内部/port制造解A4/A6差1.2255722548154e-14/2.0935547822786585e-14 | `cca180f875bd22146f2d30fa4d004e372135dfbb` |
| F2 teacher/reference | 8准确参考和384对全部原A4/port/internal/恒等式<=1e-10；256/64/64，batch<=32；最坏native3.959901353972973e-12 | `b72448bb2117a0221f041f1b47ac41049750a3c7` |
| F2 oracle | ranks16/32/64/128诊断通过；rank128 validation误差表示比.5138245737888352、最佳native残差比.3338841772011458；不是严格资格 | `d9de8ad69bfeeac4860e5187e1738c902a3d808e` |
| F3训练/冻结 | CPU FP64、rank128/2hidden64/103040参数；300epochs完成，validation选51，有载19.036173629s；真实Torch/NumPy probe差5.71091073830398e-17 | `a221d881bae9405c98e351df2b0b9533582e6d50` |
| F4三路线 | 同16heldout各一次、RIGHT32/max256/零初值，非零均到256仍失败；全过程无global p4 LU | `7216efa605bae155ee383fd716c0fae422448b52` |

后续F2/F4使用原p4-only构建，mesh/tags/MPC/mode/quadrature15及完整Schur CSR内容必须与完整F1一致，21824×21824/8184464 NNZ，未减少积分/模式。operator SHA `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`；physical SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`。原A4/A6/传递/DtN/材料和最终验算保留。

## 严格线性与NN对照

| 路线 | 严格通过 | 物理PH b6 原A4残差 | 同载荷端口closure | 全15非零A4残差范围 | 整树wall s | 整树RSS峰 B |
|---|---|---|---|---|---|---|
| R-B0 | 1/16，仅零 | 0.9986549671046351 | 0.4654717527063063 | 0.91058295–1.8905576 | 486.668 | 851476480 |
| R-LIN | 1/16，仅零 | 0.9982615362865193 | 0.2394959774159406 | 0.60250448–1.8626502 | 1239.273 | 1032511488 |
| R-NN | 1/16，仅零 | 0.9984559262641479 | 0.1799872838355197 | 0.63176606–1.8621898 | 1238.082 | 1006587904 |

残差门限为1e-10。每路线只有zero精确0/0步/无backend通过，其余15项都不合格；port闭合独立失败，内部恢复很小仍不能放行。原raw zero条目的附带native_audit沿用前项缓存，数值zero返回正确；旧raw未改，v2记录置null、使用本次zero三项0检查，最终仅修正报告条件。全部16项具体A4/port/内部/PC/作用耗时见[48项CSV](outcomes/records/strict_rhs_metrics_v2.csv)，判定由[独立checker](outcomes/records/static_checks_v2.json)从原字段重算，不信solver reason或PASS文本。

去掉全局因子已完成：B043个<=512行patch177886464B，cell/port3469728B，R-LIN表示+buffer159186688B，R-NN160011008B；128行bottom包含在同一因子预算，不把共享R重复当独立分配。构造没有global LU、ILU或private audit CSR，失败没有LU fallback。唯一global p4 LU只在离线teacher，factor.destroy/runtime.destroy/worker退出/descendants清场之后才oracle、训练和候选；没有因子共驻留。[构造证据](outcomes/records/run_index_v2.json)、[架构](outcomes/architecture_and_oracle.md)。

oracle证明固定basis可表示部分误差；B0、线性和NN在严格返回上均失败。训练loss下降和部分端口/native改善不构成G-neural正信号，没有任何路线获得资格、没有合格端到端三进程中位数。不能把去因子或线性降维收益归给NN，也不能以本小case否定所有尺寸/几何。失败属于固定表示/B0与迭代下的全局收敛负结果，不是内存触线或训练预算耗尽；没有restart/shift/ILU/rank/width/epoch无界调参重跑。

## 全过程成本、测试和未运行项

数值尝试包括4个实现/环境失败，共监督wall`8250.064113 s`，同时整树RSS阶段最大`2359627776 B`（峰取最大、不相加）、own swap0；teacher、oracle、训练和三路线分别列在[完整成本表](outcomes/accuracy_performance_memory.md)。ML训练监督wall22.267641s含导入/装载/保存，有载19.036174s；teacher numericsetup6.264s、分组生成/原方程审核另列。所有shared-workstation；Task042不分配GPU VRAM，PSS/cgroup峰未采样；编辑器/Git/审阅等待没有持续计量，不虚构总会话峰。[aux安装/预检/测试成本](outcomes/records/auxiliary_costs_v2.json)独立列出。

本轮targeted arrays、p4/default ownership、mode、noncommuting、watchdog与最终source/static/doc checks见[测试摘要](outcomes/test_summary.md)。两个继承schema2枚举文档失败在exact起点a76重现，保留而不改无关旧合同；不存在CI或full pytest声明。protected task/review/response_v1和F0数字记录逐字保留；提交只含Task042相关源码/配置/docs以及两总账Task042段，ignored大数据/权重/缓存不入Git。

无F4合格候选，按原Gate不执行三次合格路线计时及F5 p6物理解；原A6<=1e-6和场L2/scaled-curl/EH/80复模态/RTA/A_volume/所有通道功率/能量闭合最终比较全部not_run，没有official结果。独立F1-reference dat未运行，8参考已在F2完成；64heldout中16做candidate终测，剩余48未测；5/2/0.7nm、h/p/angle/几何泛化、GPU训练/推理、无限扫描均not_run。G-time/G-memory inconclusive，G-neural无正信号；没有合格单次节省，N=1/10/100与break-even未定义，不能用失败求解推摊销。

F0等待状态是历史，当前真实停止条件是严格粗逆未合格。下一步只等待review决定是否开展新的有限B0/表示设计；本轮不自行扩大。只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`，不合并master或其他分支。

验证集原方程残差loss的线性初始映射为1.6581681312213055，所选NN为1.837990301367067，记录`LINEAR_BASELINE_PREFERRED`，仅指该离线native方程目标。它不代表任一粗逆可部署，也不是三进程端到端性能胜出；combined teacher/native loss用于选择epoch，两类目标不可混称。

交付检查实值：44协议/表示/监督器 +18小型FE/默认回归 +27治理文档通过；Ruff20文件、compile41文件、bash/diff通过。额外旧总账checker仍1 failed，精确a76已有40节固定序列与旧Task038缺失链接；Task042统一表头已补齐，无新增错误。该失败及两个继承schema2失败均明确保留，不修改其他任务记录或宣称全仓全绿。
