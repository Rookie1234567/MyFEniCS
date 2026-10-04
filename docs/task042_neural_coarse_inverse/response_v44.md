# response_v44：后期误差学习及五路线冻结对照完成

本轮实际执行了四模型各128步训练，先共同GMRES64步，再按残差输出一次完整有限元修正，最后用剩余最多64步清理。NN-E使用本轮授权制造误差标签；NN-R只按残差，实/复线性模型提供控制。完整40项在求解退出后由独立checker打开封存误差审核，结果保持真实，不以loss下降授NN20%。

| 对象 | 实际结果与门 |
|---|---|
| canonical/branch/upstream | /home/fenics/Projects/NN-Lab；task42_neural_coarse_inverse；origin/task42_neural_coarse_inverse |
| Review/base | `5fa04c6c517e019107bd4a9ec7dacd8a1e0dd676` / `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| 有限问题 | 64hex/p6/q15/0.7nm，45000native/42624独立/2376slave，A无完整DtN；非原尺寸物理解 |
| 数据/梯度 | 新16/4/8 split，s=Ad操作尺度max5.623e-16；9FD max2.103e-10<1e-5、非零VJP和batch1/2通过；heldout未参与权重选择 |
| 实际训练 | NN-R/NN-E/RL-E各70144实参数，CL-E74240，各128Adam；零decoder初始化一致，全部参数组改变；NN-E从合法第7步恢复，未重跑完整训练 |
| 最终资格 | 各路线ρ≤1e-6且η≤1e-4、完整8项才合格，详见下表 |
| 全对象/资源 | 无新mesh/JIT/LU/global QR/目标动作；原CSR/AH副本仍持有；峰2493480960B，ownswap0/GPU0、CPU/math/Torch1/Loader0 |
| 时间费用 | 当前已测有载下界1937.458426175s、保守扣费2125.489426302s；A/AH7046/12000，最终closed补收尾；历史84193.14521706612s+unknown保留 |
| 原尺寸/2TB48h/NN20 | NOT_QUALIFIED / NOT_DEMONSTRATED；无新official E/H/RTA及完整32060端口解 |

| 路线 | ρ门 | η门 | 完整资格 | ρ范围 | η范围 | 总Arnoldi | 含共同前段的8项求解s |
|---|---|---|---|---|---|---|---|
| R0 | 8/8 | 0/8 | 0/8 | 2.512542745e-08..3.98664504e-08 | 0.0003359336327..0.0005311309217 | 128..128 | 244.588831 |
| NN-R | 8/8 | 0/8 | 0/8 | 2.490087855e-08..4.2150641e-08 | 0.0003674131818..0.0005308487408 | 128..128 | 247.686011 |
| NN-E | 8/8 | 0/8 | 0/8 | 2.651771046e-08..4.215432378e-08 | 0.0003643483429..0.0005497722015 | 128..128 | 245.305868 |
| RL-E | 8/8 | 0/8 | 0/8 | 2.651087888e-08..4.21524334e-08 | 0.0003643298497..0.0005496776936 | 128..128 | 246.041111 |
| CL-E | 8/8 | 0/8 | 0/8 | 2.610389954e-08..4.146630952e-08 | 0.0003642299582..0.000517074058 | 128..128 | 207.051734 |

NN-R/E初始参数hash相同；误差标签是否改善、非线性是否优于同实架构控制、完整清理是否受益分别在[完整结果](outcomes/late_error_learning_v44.md)和[40项对照](outcomes/records/neural_candidate_comparison_v44.json)报告。未合格时不安排额外计时或扩大训练；decoder投影仅为变换后表示诊断，不是原η下界。唯一下一建议：在新合同中只比较一种包含远距离残差信息、并扩大单元内部输出表达能力的可扩展神经表示及同信息线性控制；先以本轮封存误差诊断确定所需容量，不复用它们训练。本批不实现该网络，不再为同一两跳宽32表示追加初始化、训练步或GMRES步数。

NN-E两次软件失败保留：旧20GiB存储门误触后修为授权24GiB，从一致Adam第7步恢复完成128；随后最终summary序列化失败，数值结果已保存，不重算。该次退出码unknown，实际时长下界116.960010480s，预算扣304.991010608s，消费不回滚。全部路径运行source详见[run index](outcomes/records/run_index_v44.json)而非最终文档HEAD；SETUP/DATA/GRADIENT ef9f0ddc10b96fdeaf56c659f2c7c1726c963c6a、NN-R 41b6eda61c654d9a9abc658948778a95066ffb41、NN-E恢复 e137607b8f415be34927faf2f57d656621f105e9，后续线性与终测见逐项manifest。

V43最终采样间隔纠正为1.656077245s，旧快照1.548035696s不回写。旧A/B恢复超1e-10的FAIL保留；有限系数误差不代替物理场/功率。所有成本shared-workstation、邻影响INCONCLUSIVE；冷N1/N8/N100和20%必要条件保留上游unknown，不抹去准备与训练成本。

[独立checker](outcomes/records/neural_heldout_checker_v44.json) · [梯度](outcomes/records/neural_gradient_v44.json) · [decoder诊断](outcomes/records/neural_diagnostic_v44.json) · [全费用](outcomes/records/resource_costs_v44.json) · [资源/CPU](outcomes/records/resource_samples_audit_v44.json) · [raw](outcomes/records/raw_evidence_index_v44.json) · [数组/权重](outcomes/records/array_inventory_v44.json) · [测试](outcomes/records/tests_v44.json) · [closed](outcomes/records/closed_window_v44.json)。GitHub视觉NOT_VERIFIED，无CI宣称；清场closed、提交推送后原队列交回，不merge或继续启动新负载。


最终closed与后续低负载结算：有载观测下界1973.161241790s，保守扣费上界2161.192241917s；两者差额188.031000128s来自NN-E监督摘要丢失的保守结算，不是额外训练。原A/AH完成7044次、按上界7046次扣费，新B0。数值及辅助均已退出，closed记录保留原始计费边界；后续文件/文档/Git/队列费用另列实测或unknown。
