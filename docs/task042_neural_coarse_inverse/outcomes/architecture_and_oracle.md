# 原方程、低内存修正与可表达性诊断

粗逆把粗层残差转成修正。原实现先构建全局p4 LU，再回代；本轮候选在原p4方程上用迭代求解，以固定传统B0辅助全部空间，再分别增加线性或神经低维修正。方程、物理复质量、负号、完整DtN通道及最终验算保留。

```math
A_4=P^H A_6P,\qquad C=P A_4^{-1}P^H.
```

单元凝聚先精确消去内部未知量，再求公共边界与端口。p4必须独立凝聚；不能把p6已经凝聚的矩阵投影后叫p4。F1在完整空间验证上式，另以同一个p4的独立单元作用核对Schur矩阵，非零内部/端口RHS验证恢复。BAL_H的粗修正、细层平滑和粗反馈数学未修改；由于F4未通过，本轮没有把研究逆接到BAL_H或p6外层。

| 层次/实现 | 行为及容量 | 实际证据与边界 |
|---|---|---|
| 原A6/A4与传递 | F1完整p6、同网格物理p4，curl+mass后凝聚；共享已有cache/LU/witness | 原A4=PH A6P差3.366065072840215e-15；制造解原p6差2.0935547822786585e-14；不是最终物理解 |
| p4-only后续构建 | F2/F4不重复构建p6；原p4全部mesh/tags/MPC/mode/quadrature和逐行CSR内容必须与F1一致 | 21824×21824、8184464存储NNZ；原operator SHA固定；非减少通道或积分 |
| B0 | 固定不重叠、连续索引512行block Jacobi；43块、无shift/扫描 | patch因子177886464B；cell/port3469728B；最大patch512、port bottom80；无全局因子 |
| oracle | teacher误差streamed POD；Q ranks16/32/64/128；用原native残差像W S4 Q做最佳子空间最小残差 | 独立native作用核验最坏1.5951422754826113e-13；最高rank validation两比.51382457/.33388418，诊断正信号 |
| R-LIN | 先B0，取剩余原native残差的低维投影，用128×128三角R解码，再Q回到全空间 | 同basis/归一化/精度；最小残差线性基线；表示+buffer159186688B，R计入bottom因子 |
| R-NN | 相同B0、Q和native残差投影，FP64实虚256维输入/输出，2hidden×64 residual MLP；线性skip初始化为同R逆 | 103040参数、824320B；离线训练300epochs，validation选51；在线冻结NumPy，不导入Torch或teacher解 |
| 真正的逆返回 | 原p4 Schur上的RIGHT FGMRES32/max256/零初值，随后恢复完整FE+累计port并独立原A4审核 | 三路线各16项，仅零通过；原A4/port未达1e-10就拒绝，无LU fallback |

`W`将凝聚后的残差恢复成原native方程的不平衡量，含端口消元贡献。它不是把投影残差当全系统误差；F1与oracle都用独立原A4作用核对。神经loss包含teacher修正坐标误差和完整native Gram残差（包括子空间之外的正交剩余项）；保留常数项，避免把投影很好误报为全系统通过。oracle的最佳子空间残差是同一Q上可达到的下界，非线性网络不能宣称越过这个下界。

## 严格协议及实际构造

[coarse_inverse_protocol.py](../../../src/solvers/coarse_inverse_protocol.py)保留F0完整复数FE/port、身份、容量和失败返回合同；[learned_coarse_inverse.py](../../../src/solvers/learned_coarse_inverse.py)提供真实有界B0、PETSc内层FGMRES及原方程audit；[learned_reduced_correction.py](../../../src/solvers/learned_reduced_correction.py)实现streamed POD和同表示线性/冻结NN修正。

候选factory为[learned_coarse_runtime.py](../../../src/solvers/learned_coarse_runtime.py)的p4-only原方程构建，没有attach_p4_factor或MUMPS调用。FGMRES使用Python PC；局部dense LU只用于cell、有限patch和小bottom，全部计入512MiB因子预算；basis/映射/buffer另限512MiB且分配前检查。不设置PETSc options来接受隐藏solver覆盖。原矩阵仅借用，audit使用已存在的native/local tensor，不为每个candidate复制CSR。

唯一global p4 LU在`F2-teacher`分支的offline_reference_factor中，MUMPS ICNTL22=0、不OOC；symbolic后预算检查，再numeric。参考8项和384对数据全部原方程审核后factor.destroy、runtime.destroy、worker退出；launcher证实descendants_cleared才允许下一阶段。teacher、oracle、CPU训练及三候选均为独立顺序进程，无factor/训练/candidate共驻留。

`P6CellCondensedAction`仅新增显式`borrowed_p4_witness=True`研究接口，共享调用者已持有p4的材料化tensor、Schur及局部恢复；不取得destroy所有权、不复制矩阵。原p6默认constructor仍拒绝材料化p4，以paired test验证。`RetainedCondensedRuntime.build`仅新增`retain_coarse_schur` opt-in，默认False；没有篡改P4RefinementLedger类型/MatSolve计数，也未改旧production返回路径。

## 冻结身份、历史和停止条件

原physical SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`；完整mode SHA `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb`；p4 Schur CSR SHA `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`。轴坐标、material tags、MPC映射、80通道和curl/mass quadrature15在F1原始operator_identity.json冻结并hash绑定后续构建。h10边界拟合实际为252cells；没有将名义网格步数硬填成cells。

冻结神经历史源`d91652dd2d611d6d6bedd10e677c3f7030c07d4f`仅作只读接口审计，见[原F0审计](records/neural_reference_audit.json)。PARA001/004/005的局部改进、全局成本增长、私有CSR及线性对照教训均保留；没有迁移旧fallback/ILU依赖或旧权重。

预登记oracle最高rank两比<=.90/.99才继续；本轮通过，因此实际完成小训练和F4。F4要求所有非零原A4及port/recovery<=1e-10、zero精确零、finite/slave-zero/恢复成立。三路线到256步仍失败即`COARSE_INVERSE_NOT_QUALIFIED`，不改参数重跑；仅全部合格路线允许三独立进程计时和条件F5。F5原A6<=1e-6、全部场/模态/RTA原门限仍保留，当前全部not_run。

[逐RHS与资源](accuracy_performance_memory.md)、[独立Gate](records/gate_decisions_v2.json)、[真实F1](records/f1_real_components_v2.json)、[teacher](records/teacher_complete_v2.json)、[oracle](records/oracle_complete_v2.json)给出正信号和失败的不同含义。用户共享授权替代仅Task042 heavy/全机锁要求，使用自有非阻塞锁和低开销整树监督；不把原F0等待或用户授权当成正式review通过。


## V3 最新有限诊断（原V2正文保留）

V3只新增显式R-GEO-CELL80-v3与可选逐步observer，复用单元trace/MPC支撑，不复制audit CSR；原连续512行B0不变。252个局部原Schur块含完整80ports，限制canonical坐标、延拓次数平均。全局粗逆未资格化，固定Q下R-LIN精确最小native残差的最优性仍成立；同Q MLP不能胜过该最优解。详细[预登记](bounded_diagnostic_design_v3.md)与[结构实测](records/structure_complete_v3.json)。
