# Response V45：完整矩分层神经候选已完成

收到`review-execution-handoff-20261004-v42`，已按完整Review V42连续完成机制／真实校准、3×128训练、五路线40终测、独立CHECK和保存误差／成本分析。神经研究实际执行，未转回旧p4或纯FE求解开发。资格结论为CLOSE_FIXED_A_FULL_MOMENT_HIERARCHY_QUALIFICATION，NN20与原尺寸目标仍未达成。

| 路线 | ρ门 | η门 | 完整资格 | ρ范围，门1e-6 | η范围，门1e-4 | 总Arnoldi | 含共同前段的8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 258.393582 |
| CL44 | 8/8 | 0/8 | 0/8 | 2.581975482e-08..3.78853399e-08 | 0.0003508615011..0.0005405081646 | 128..128 | 263.432889 |
| LIN-H | 8/8 | 0/8 | 0/8 | 2.61547387e-08..3.861573114e-08 | 0.0003484809644..0.0005296573543 | 128..128 | 260.056874 |
| NN-L | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 250.222528 |
| NN-H | 8/8 | 0/8 | 0/8 | 2.505960139e-08..3.847077003e-08 | 0.0003661522394..0.0005538544985 | 128..128 | 260.343939 |

| 项目 | 实际交付 |
|---|---|
| canonical／branch／upstream | /home/fenics/Projects/NN-Lab；task42_neural_coarse_inverse；origin/task42_neural_coarse_inverse；交接前核实clean/0:0与实时远端 |
| base／review | ccd357885f7f9be84efe3be07868cc94f13d93fc／2e5bfc593716d82ccbca4cc2061b50fe491186cd |
| 实际run source | 53b7a109160e52caf6a712b1d4059b6adbb049ce；最终文档提交不是数值source |
| 架构 | 1817040实参数，全6/60/450复矩，H分层／L最细桶；同信息identity LIN-H；CPU FP64/math/Torch1、Loader0、GPU0 |
| 梯度 | 9FD max3.01079069292e-09；原loss VJP、远参数／完整输出矩、batch1/2通过 |
| 训练／选择 | 三模型各128更新；LIN-H选择128，NN-L/H选择零head step0；不是未训练，也不是成功修正 |
| heldout | 新封存8个，5×8独立路线；全部冻结退出后CHECK才读取制造e；原总128 Arnoldi不加步 |
| 因子／对象 | 原有限CSR与显式AH存在；新LU/global p4/QR/JIT/mesh/目标作用0；完整内部输出绕开旧未合格trace-only恢复，旧FAIL不改 |
| 峰／费用 | 树采样峰2882494464B、ownswap0；有载2222.726593072s下界／2222.726593072s扣费，完整清场／Git费用另留unknown/观测；shared-workstation |
| 原尺寸／物理 | 无完整DtN/E/H/curl/32060端口/功率，0.7nm/2TB48h与同正确性NN20未资格 |
| V44新纠正 | 最终全26监督最大elapsed间隔1.9185047228820622s，aux_post_collect03；旧记录保持 |
| 测试／文档 | 62 focused及最终Ruff/compile/ML资格；15文档检查；GitHub视觉NOT_VERIFIED |
| 额外旧总账checker | 两项入场历史错误原字节复算相同，FAILED_INHERITED_EXACT；Task042最新总账已同步，不把该额外检查写成PASS |

完整矩没有强制32维瓶颈，分层内容见证与真实训练通过；但validation拒绝了两份非零神经head，终测仍没有同正确性合格配对。线性、远程信息、神经非线性、训练费用分别记账；小loss变化、相同残差或共享墙钟变化都不授神经收益。

唯一下一建议：把本轮冻结输入／完整系数／原残差／伴随／全部费用接口交给同物理合格传统引擎做一次匹配，先判断难误差与冷N=1是否存在20%空间；不再在同一A上换seed、加层、调tau或延长128步。本批不重建传统引擎、不复制dot求解器。

[完整结果](outcomes/full_moment_hierarchy_v45.md) · [run/source](outcomes/records/run_index_v45.json) · [独立checker](outcomes/records/neural_heldout_checker_v45.json) · [保存向量](outcomes/records/saved_heldout_vector_audit_v45.json) · [成本](outcomes/records/resource_costs_v45.json) · [资源](outcomes/records/resource_samples_audit_v45.json) · [原始证据](outcomes/records/raw_evidence_index_v45.json) · [容量](outcomes/records/neural_capacity_contract_v45.json) · [closed](outcomes/records/closed_window_v45.json)

只提交推送本执行分支，closed、清场、锁释放、remote/clean/upstream核验后，经原队列`execution-review-handoff-20261004-v45`一次交回；不需要用户转发，不用subagents／重置卡，不改dot／其他分支／master，不merge。

最终全部 29 份监督的elapsed相邻采样间隔最大 1.90659618401s；配置0.5s不冒充实际全集上界。

冻结CL44只承担继承的V44训练／准备及本轮加载／前段／审核；未消费的V45新训练与梯度准备不重复分摊给它。研究批次总费用不变。共享SETUP含本轮神经校准，成本情景不冒充另一传统引擎的不可省费用。最终少量未监督关账／Git／通知的RSS及精确费用保持unknown，29份有载监督峰不称全天连续峰。

截至本次费用修正的已测有载下界／已扣预算为 2222.726593072s；历史加本轮下界 88389.247599376s。后续极少量文件／Git／通知unknown；当前全日历 4722.717218s 亦低于7200s，未靠刷新窗口或漏记等待过预算。
