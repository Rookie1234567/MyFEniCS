# response_v43：真实神经训练与未见右端对照完成，完整资格仍为负

这次网络实际学习了“从相邻边／面／单元的残差产生有限元修正”，输出完整trace和内部系数，再用同一传统GMRES清理；不是纯FE演示。NN和同邻域复线性控制各完成128次Adam更新、全部层组改变，完整原残差／伴随梯度门通过。最终8未见RHS的三路线均未通过完整系数资格，因此NN20%和原尺寸0.7nm／2TB48h仍未资格化。

| 对象／门 | 实际结论 |
|---|---|
| 合同／base | Review V40 `84c38b882795c56fead54d75cd56389262c86e31`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| canonical／branch／upstream | /home/fenics/Projects/NN-Lab；task42_neural_coarse_inverse；origin/task42_neural_coarse_inverse |
| 有限问题 | 64hex/p6/q15/3tag/0.7nm，45000native、42624独立、2376slave；A不含完整DtN；B12port只验梯度 |
| NN／LIN | 70144／74240实参数，CPU FP64、2轮消息宽32、batch2、128更新；val选128，封存e只在求解冻结后由CHECK读取 |
| 原梯度 | 9/9全向量FD≤2.077e-10<1e-5；3个VJP运算尺度最大1.442e-20<1e-10；非互伴非零port门通过 |
| R0 | ρ8/8通过，但η0.0062675..0.0167821>1e-4；完整0/8；87–91步 |
| R-LIN | ρ4/8，η0.0340369..0.458594>1e-4；完整0/8；127–128步 |
| R-NN | ρ8/8，η0.0571237..0.227036>1e-4；完整0/8；114–120步，慢于R0清理 |
| 当前费用／资源 | 已测有载下界1305.826678908s；原A/Aᴴ4090，B21；峰2696056832B、ownswap0、GPU0；本行是生成时下界；含收尾的最终金额见closed费用包 |
| 真实source | SETUP/RECOVERY 5cc546a920f7557520395e505bb314cdb2c90a71；DATA 582146016392567aecca89ab2142bbdf9ec5227a；训练 0ed2850df39a53a4c4a6f49ab308c6619de696d4；终测 9c223d99038605f606e8912ba23b1453896d2b9d；CHECK 765f9899f2914931b4cf945c99f34eb516ff268c |
| 旧恢复／大对象 | A旧native7.59147e-10、B旧CSR1.01045e-10>1e-10保持FAIL；本轮新mesh/JIT/LU/QR/目标动作0，无global p4逆或fallback；显式有限CSR/AH仍计内存 |
| 原尺寸／场功率／NN20% | NOT_RUN / NOT_QUALIFIED / NOT_DEMONSTRATED；无合格同正确性非神经基线，无official R/T/A |

NN自身val中位数4.3599→1.02735，比LIN本轮val低，但零修正ρ=1，且残差下降没有降低完整清理成本。局部NN优于LIN、缓变LIN优于NN，二者皆不如R0系数误差，不能宣称普遍神经增益。低原残差而系数误差仍较大是实际证据，不推断唯一根因或条件数。全部失败、零作用入口错误及已消费梯度费用保留，没有增加迭代、训练预算或换参数救场。

唯一下一建议：只比较同一架构的零输出层初始化与本轮初始化，其他数据生成族、seed、128更新及清理规则不变；检验训练是否主要花在撤销有害初值。当前heldout已消费，只能再作诊断；后续资格需另预登记独立集合。该对照需未来review授权，本轮不实施；即使改善，残差与完整系数误差仍须同时过门，不能因此授NN20%。

[完整结果](outcomes/neighborhood_residual_correction_v43.md) · [24项对照](outcomes/records/neural_candidate_comparison_v43.json) · [独立checker](outcomes/records/neural_heldout_checker_v43.json) · [训练NN/LIN](outcomes/records/neural_training_nn_v43.json) · [梯度](outcomes/records/neural_gradient_v43.json) · [run/source](outcomes/records/run_index_v43.json) · [raw](outcomes/records/raw_evidence_index_v43.json) · [数组](outcomes/records/array_inventory_v43.json) · [全费用](outcomes/records/resource_costs_v43.json) · [资源CPU](outcomes/records/resource_samples_audit_v43.json) · [就绪](outcomes/records/integration_readiness_v43.json) · [测试](outcomes/records/tests_v43.json)。历史费用下界和unknown保留，shared-workstation性能／邻影响INCONCLUSIVE；GitHub视觉NOT_VERIFIED，不宣称CI。

按合同完成队列后收口，ledger closed、清场、只提交推送本分支，核实clean/upstream0/0后以execution-review-handoff-20261004-v43原队列交回审阅。最终精确文档HEAD和实际交付UTC在最终消息／交接给出，不冒充运行source。不使用subagents／重置卡，不改dot／其他分支或merge。
