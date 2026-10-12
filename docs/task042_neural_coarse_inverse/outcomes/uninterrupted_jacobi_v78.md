# V78：连续Jacobi周期、原方程与成本

**完成连续周期，但未取得合格场；关闭当前PC试错。**

本轮把Jacobi每次只对残差逐项相除的廉价修正保持不变，让求解器在同一个实例内积累完整128个搜索方向。旧32+32中间会丢弃已积累方向，不能代替本对照。代价是更大的向量库，实际内存与原方程残差均单独记录；本批没有神经训练。

| 步数：同0.7nm NOTCH/25576tet/p5/828，measured | 原true | 接口true | port | 累计KSP检查/s |
|---|---:|---:|---:|---:|
| 0 | 1 | 1 | 0.0849805988388 | 65.409 |
| 32 | 0.38882658639 | 0.379105019552 | 0.0525401882174 | 170.438 |
| 64 | 0.316494040594 | 0.315852440263 | 0.018860243072 | 283.986 |
| 96 | 0.295572340788 | 0.295216222243 | 0.0143500399313 | 404.724 |
| 128 | 0.284024612789 | 0.283620383707 | 0.0138676292829 | 533.964 |

实际RIGHT FGMRES/restart128/max256、retained零起点；create/solve/destroy各1。32/64/96检查在同一实例，未使用PROMOTED/BJ32，也未丢弃Arnoldi基。128步rho=0.284024612789，投入门0.10；最终原残差0.284024612789、接口0.283620383707，正式门分别1e-6/1e-11。[完整曲线和配置](records/results_v78.json)

独立新进程q15 PUBLIC_BASIX体/q63全部边界审核与producer原向量差0，阈值1e-10；原true/native/augmented/port各按1e-6验收，恢复/MPC/Schur身份仍按1e-10。代数身份可信与方程未收敛分开，独立direct1e-10目标未因研究效果门放宽。完整1943745 FE系数、828port、原式向量、RHS/尺度/mesh/MPC/κ与source均保存。[增量证据和数组身份](records/evidence_index_v78.json)

六场积分、原240点、物理复振幅/逐级功率、RTA与独立体吸收状态为NOT_RUN_BY_FAIL_FAST_POLICY，official=False。失败时按原true>1e-2政策不花费坏场全积分；端口系数已保存，不能冒称已做完整物理通道评分。未读V70正确场初始化、选PC或造RHS。旧连续空间FAIL、原尺寸2TB48h和NN20均不升级。

| V78当前增量；measured，父成本另列 | 数据 |
|---|---|
| KSP含检查 / 完整失败尝试wrapper | 534.859523 / 875.795297 s |
| PRECHECK+主对照+独立VERIFY prepared链 | 1182.803294 s |
| 当前不重叠命令/归档已知下界 | 1430.087961 s；编辑/Git等未包裹区间unknown |
| 从首次工作至本次结算实时时钟 T_research | 2927.451554 s；包含读取/实现/等待/失败/IO，不与上行相加 |
| 采样整树峰 / 实际最大gap | 11.674725 GiB / 1.224841401 s；0.5s仅配置 |
| 全域作用 / 新矩阵 / 新numeric | 140 / 0 / 0；作用上限400 |
| 257条主向量库derived载荷 | 4.508559 GiB；不是RSS |

ownswap/OOC/GPU=0，MPI/math1；64/80/96GiB规划/警戒/采样停止贯通原监督，现场宿主/邻增长/CPU-SMT门保留。只读取原packet与V76复Jacobi对角，不加载38块、Z/E或旧全局因子；父packet内部LU仍存在，不能称factor-free。V70 packet与S共享准备8766.781321s保留，packet-only冷份额unknown；无同正确性完整冷N=1，因此不给生产加速比。[完整费用与生命周期](records/resource_costs_v78.json)

worktree=/home/fenics/Projects/NN-Lab；分支task42_neural_coarse_inverse；base=ccd357885f7f9be84efe3be07868cc94f13d93fc；Review=c126e154a7196cf427b4511a9e2e596fa5580993，正文SHA匹配。实际科学及VERIFY source=a08d40f9845f481fa79abf6f8d7a48c99b956bcd，最终文档HEAD另列交付收据。新窗首次实钟2026-10-12T08:34:55.233232765UTC、同boot单调1719090.09冻结4h，不刷新旧closed窗口。[权威与时钟](records/authority_identity_v78.json)

最终4项targeted小接线测试、2次合成KSP、相关compile/Ruff与3dat validate通过；未full pytest/CI/旧PDE。两项字符串编辑保护错误均在正式运行前定位修复，原stderr及失败保留，科学重放0；writer/JSON补消费协议未重解。[测试、修复和分流](records/decisions_tests_v78.json)。文档一次15项紧凑合同检查，GitHub视觉NOT_VERIFIED。

唯一下一建议：关闭当前PC试错；新研究须先有同物理方向、误差尺度及成本依据，不自动开下一窗口。 不merge、不通知邻窗口，不自动启动新批。

最终结算：当前不重叠命令及增量归档已知下界1430.087961s；历史已知下界400183.831621s。最终存储快照新增1750646051B、Task去重214759898797B、free2620278730752B。15项文档检查通过；最终15个新数组包81成员的hash-bound清单见增量索引。ledger closed/active null、自有锁释放，无科学后代；精确文档HEAD/远端与实际交付时刻由Git交付收据绑定。
