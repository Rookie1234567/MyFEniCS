# Response V8：停机语义修复，列尺度负结果，批量计算工程正信号

**V8_SCALING_AND_EXECUTION_CALIBRATION 已执行C0–C4适用部分。C1事务和C3等价通过；C2严格及研究正信号均未通过。batch8的共享微基准成本下降48.55%，不代表数值收敛。最终0.7nm／48h仍NOT_QUALIFIED。**

整理本响应时HEAD为 `5067a5ea390d7f4064f70cd3cb5774a2549a0e43`；最终文档HEAD由Git交付回报报告，不填写自指SHA。branch逐字符 `task42_neural_coarse_inverse`，upstream `origin/task42_neural_coarse_inverse`，worktree `/home/fenics/Projects/NN-Lab`、common `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。开始clean `c4fadde46978f2ba0ca3e25734311b6d3c8599c5`，确认无本任务活跃run后，只获取并ff到实际远端Review V5 `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`、初始文档 `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`仍为祖先。未reset/改旧worktree/merge，提交仅Task042。

完整合同及Review V1–V5、最新response/outcomes已读。Review V5实际GitHub richText **4表／2math-renderer**、列一致，通过；未擅改review。V7三候选及更早负结果按字节保留，旧p4路线继续关闭。[完整结果](outcomes/scaling_and_execution_v8.md)、[真实source/index](outcomes/records/run_index_v8.json)。

固定对象为原384 hex／p3／h0.175 nm三维缺口，wavelength0.7 nm、grazing1°／azimuth0／s、双Floquet／layered DtN。FE34050、独立trace18144、内部13824、slave2082、reduced18184，完整top20＋bottom20=40复port。材料仍为唯一canonical表`input/materials/si_optical_constants_v1.json`，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`、SHA `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`；Si n=0.999885140474+4.32477054e-6i、epsilon=n*n，精确0.699999988→nominal0.7 alias不变。physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`，mode SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`。原材料、入射、RHS、master/MPC、方程及验算均未改。

| 独立问题 | 实际结论／限值 | 证据 |
|---|---|---|
| C1停机 | 实际strong-Wolfe异常复现并恢复参数＋optimizer；7测试通过；消耗不回滚，LAST_COMPLETED_OUTER_STEP不是内部Wolfe点 | [停机记录](outcomes/records/optimizer_stop_semantics_v8.json) |
| D设置 | 原CSR正确合并列贡献，8列＋3复向量误差≤4.48e-16，c比762.67；setup整树6.818829s/641200128B，释放CSR后零初值求解 | [列来源/成本](outcomes/records/column_scaling_v8.json) |
| C2原方程 | 1915步/S1999/Sᴴ1919，Schur0.068283273738、native0.026675035784；未达1e-6或十倍研究阈值 | [完整工作点](outcomes/records/convergence_checkpoints_v8.csv) |
| C2真实场 | scattered L2差0.998598490718，严格≤1e-4／研究≤0.5均失败；全场E/H、curl、40复port及功率也未合格 | [独立物理审核](outcomes/records/scaled_blind_validation_v8.json) |
| C3表示／执行 | 保持同3×64/8载波/FP64/q15/MPC/owner，全trace/loss/gradient/clone Adam通过；最大梯度差5.338e-13，FD最大1.794e-9 | [等价与缓存](outcomes/records/batch_equivalence_v8.json) |
| C3成本 | 三pair/36完整评估，paired中位降幅48.55%，新增缓存35107584B；固定参数，不训练 | [全部样本](outcomes/records/batch_costs_v8.csv) |

列均衡只有小幅残差改善，未恢复可信散射；不据此宣布唯一根因或所有神经方法无效。V7接受状态不可还原，记录V7_ACCEPTANCE_STATE_UNKNOWN，但原向量数值负结果仍有效。C3只是数学相同计算更便宜，神经数值增量NOT_DEMONSTRATED。候选R/T/A仅unqualified diagnostic，完整原残差、恢复、E/H、全通道和功率见上述审核。

本轮源：C0/C2 `1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05`，C3 `52d47d35656c5a763bed07e07f827fb6fb285bb7`。一个额外所有权细节如实收口：初次C2 wrapper加载了未用于LSQR的3369888B moment包，费用/RSS包含；结束后 `9915f6168ec4035470870a5d8c3c3bbfe0e6277a` 修复并做2边界回归，没有重跑已冻结负结果，也不宣称修复后的最小部署已完成整场实测。候选从未读CSR、准确解或global因子；只有operator-only setup小CSR，**SCALING_SETUP_USES_SMALL_ASSEMBLED_S**，无新symbolic/numeric/solve、无p4/ILU/Riesz/隐藏fallback。

11正式阶段supervised wall 791.658916180s，含准入launcher wall 809.987740805s；采样同时树峰816152576B、own swap0、GPU未使用。worker/子项嵌套不重复相加，全部aux/失败/后续费用继续计入8751.379832064034s carry，最终4h新增／10h累计逐秒账见[完整费用](outcomes/records/resource_costs_v8.json)。整交互会话资源未连续采样。原受控共享授权、自有锁/MPI1/math与Torch1/DataLoader0/nice10/idleIO/16GiB hard与12GiB warn、系统与邻增长余量、独立缓存均保持；无cgroup委派，不称连续内核保证。未观察持续压力，无可比邻吞吐、影响INCONCLUSIVE；微基准仅共享观测，无争用加速未证明。

最终16相关pytest、2 checker损坏反例、7事务测试、tiny batch等价与2000 closure小数组预算回归通过；无full pytest/CI/MPI2/4重跑。[测试](outcomes/test_summary.md)、[依赖变化](outcomes/changed_files.md)。新长训练、监督拟合、p4 enrichment、GPU、最大模型／短波、F5/p6、旧teacher／seed420620、official候选物理结果均not_run。目标规模单步／步数／通道存储／离散误差和48h资格unknown，材料已ready。

唯一下一最小建议：固定pilot上仅对已经冻结的误差方向做原S/恢复/端口分量审核，复用已有p3参考作离线核对，定位残差下降为何没有恢复散射；不训练、不建新PC、不扫描。 本批不实施。同步summary及项目／模型总账后，只推送本执行分支，停止等待ChatGPT review，不merge。
