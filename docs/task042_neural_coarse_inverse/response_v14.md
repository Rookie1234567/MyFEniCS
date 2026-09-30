# Response V14：正交trace decoder合格，有限重求头只有小幅原目标改善

已按[Review V11](review_report_v11.md)完成`V14_ORTHONORMAL_TRACE_REPROFILE`的O0–O4：**六固定点＋两个有界新点全部执行，独立FE审核10状态，严格通过0个**。最终分类`OBJECTIVE_ONLY_IMPROVEMENT`，没有神经求解增量、完整micro FE或0.7 nm／48小时资格。旧V11头1e-8、V12 FD与V13全部负结果原样保留。

神经隐藏特征先经原Nédélec边／面积分矩，得到合法的有限元trace方向P；这些方向很相关，直接用巨大原始输出系数相消容易损失数值稳定性。本批把它们换成长度归一且互相正交的方向Q，再由原方程决定组合系数c，主正向直接输出t=Qc。它解决输出路径的稳定性，代价是构造、分解和保存大型薄矩阵。相同hidden的P和Q在精确算术下覆盖同一空间，换坐标本身不扩大表示能力；不同hidden的完整头重求才检验空间变化。

新家族为`ORTHONORMAL_NEURAL_FE_BASIS`：网络计算空间特征，QR与原方程LS组成decoder；不是仅保存原MLP参数就能推理的场。本批不求全hidden梯度、不宣称精确VarPro或旧raw头回写通过。

| 身份／执行 | 实际情况 |
|---|---|
| Git与工作树 | 唯一`task42_neural_coarse_inverse`，NN-Lab canonical linked worktree；upstream origin/task42_neural_coarse_inverse；origin git@github-myfenics:Rookie1234567/MyFEniCS.git；common `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。V13干净HEAD安全快进52bfe9ca622481df8f686a92cbb632885610d0e8，无回退/其他worktree操作 |
| base／实际source | 冻结base `ccd357885f7f9be84efe3be07868cc94f13d93fc`及初始任务提交为祖先；全部正式运行source **`87940891c12ccdec35fca39cd453ab9a29eeeda5`**，最终文档HEAD另在推送报告给出 |
| 物理／材料 | 原0.7nm、384hex/p3/q15/batch8、完整40端口；canonical SI_OPTICAL_CONSTANTS_USER_20260929_V1，Si n=0.999885140474+4.32477054e-6i、epsilon=n*n，明确0.699999988→0.7 alias；物理/材料/mode/action/数组hash不变 |
| 新入口／Gate | 三个规定dat已实现且正式执行；ORTHO-M1/M2已知解误差2.31e-13／3.52e-13，齐次恢复约1e-16；所有点P/A rank1560，直接Qc与thin、驻点、端口solve合格；原点逆序QR Phi差8.99e-10作为观察余量，不替换主解 |

六固定点按原点→trial4→3→2→1→0完成，没有缺项。trial0完整头把旧一阶头Phi230.446144降至0.318108327；相对**新原点0.318179987**只降2.25e-4，满足有界继续条件，故实际再作s2与s4。每点重新构造当前P/Q/A、独立求c/port，无gamma继承、warm start或参考。最终s4原Phi0.3178970548，下降**0.088922%**；本批未训练新的hidden优化器。[八profile raw](outcomes/records/profile_points_v14.json)、[基底敏感性](outcomes/records/basis_sensitivity_v14.json)。

| O4冻结后实际结果；无量纲 | V14原点 | 最终s4 | 原限值 |
|---|---:|---:|---:|
| 原Schur／native | 0.797721740／0.309359507 | **0.797366986／0.309221932** | 各1e-6 |
| total E／scaled-curl（mu=1时亦为全域H相对误差） | 0.076836177／0.076848599 | 0.076763861／0.076776275 | 各1e-4 |
| scattered E／scaled-curl | 0.734256828／0.734361605 | **0.733565775／0.733670474** | 各1e-4 |
| selected复E／H | 0.085531024／0.066986743 | 0.085450000／0.066924970 | 各1e-4 |
| 40复通道／能量误差 | 0.049415153／0.112132957 | **0.049365073／0.112062042** | 1e-4／1e-5 |

最终端口、恢复、identity约2.35e-16／6.09e-13／6.62e-13且slave-zero，不能替代全方程失败。散射E/curl只改善约0.0941%，研究所需≤0.5、25%改善和rho减半均失败，原残差平台没有实质突破。R/T/A_balance/A_volume=0.0849762742／0.7981065222／0.1169172036／0.00485516192，全部**未资格化诊断，无official R/T/A**。全部复通道、selected E/H、原增广/独立native和功率绝对差见[完整研究](outcomes/orthonormal_trace_reprofile_v14.md)、[对照CSV](outcomes/records/candidate_comparison_v14.csv)、[原键通道](outcomes/records/channel_observables_v14.csv)。当前参考native标量未被复用验证器持久化，明确缺项、不猜填；沿用既有合格REF7身份，候选FAIL不依赖这一缺项。

正式O1/O2–O3/O4监督wall为507.130224／1965.470091／37.672464秒，合计**2510.272780秒**；同时采样树峰**3243409408B≈3.021GiB**、ownswap0、VRAM0，全部清场。9套P/Q/A、11LS/11RHS、12551次S/SH、20audit、2新点、10场状态均在上限内。全大薄矩阵/分解/父子进程纳入，保留原点和最终Q+c，新artifact约0.922GB；其余可再生workspace有lifecycle/hash，旧负artifact未删。全流程source不是网络参数内存口径。[完整资源与历史账](outcomes/records/resource_costs_v14.json)、[run index](outcomes/records/run_index_v14.json)。

受控共享CPU延续：每正式stage实时选CPU0、MPI1、数学/Torch1、Loader0，独立环境/cache/ownlock、nice10/I/O idle；16GiB hard／12warn、规划7.6e9B＜8GiB、ownswap0，系统/邻任务余量保持。无cgroup委派，实际是0.5s独立整树采样监督，不称连续内核cap或零干扰；未见持续压力stop，邻任务可比速度unknown，性能INCONCLUSIVE。没有修改邻任务/环境/锁/亲和性/watchdog/系统，候选没有global p4因子、全局S/CSR、正规方程、ILU/Riesz或隐藏fallback。V6起formal可核下界升至14670.412103秒，旧辅助unknown保留；四小时窗口未刷新，总elapsed含研发/交付。

writer最小修复与原子候选存储通过；最终22小回归及raw checker通过，保留Q重算trace差0。初期整数key边界失败、浮点断言失败和纯小测试误用旧CPU0均保留/修正，正式数值重放0次。Ruff不可用，无CI/full-repository/MPI2/4资格声明。[测试](outcomes/test_summary.md)、[变更分组](outcomes/changed_files.md)、[静态及GitHub服务端结构](outcomes/records/publication_checks_v14.json)；无浏览器glyph证据不称完整视觉PASS。

唯一下一建议，尚未实施：在新review中固定相同micro、1560维容量和40端口，做一次**几何局部、正交Nédélec trace表示**对照，替换当前高相关全局tanh特征，检验表示是否覆盖更有用的原方程方向。当前仅一条hidden射线的数据不支持继续相同大头／QR／切向／缩步循环，也不证明所有神经方法或Full3D迭代都不可行；旧p4逆继续关闭。

所有授权路径已完成；不新增参考/p4、最大模型、GPU、续训或同射线点，不消费seed420620。完成交付仅push本分支，清场后等待review，不merge。
