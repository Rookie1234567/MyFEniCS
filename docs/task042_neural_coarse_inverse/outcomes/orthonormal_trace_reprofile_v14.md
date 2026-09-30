# V14：直接正交decoder合格，完整头重求仍未取得有限元或神经增量资格

按[Review V11](../review_report_v11.md)完成O0→O1→O2→条件O3→O4，六固定点与s=2、s=4两个新点全部实际执行，无缺项。新decoder与两个制造见证合格；最终原Phi只下降**0.088922%**，散射E／curl只改善**0.094116%／0.094113%**。10个独立审核状态严格通过0个，分类`OBJECTIVE_ONLY_IMPROVEMENT`；无新official R/T/A，无最终0.7 nm／48小时资格。

## 方法与冻结对象

神经隐藏特征先经原Nédélec边／面积分矩，得到合法的有限元trace方向P；这些方向很相关，直接用巨大原始输出系数相消容易损失数值稳定性。本批把它们换成长度归一且互相正交的方向Q，再由原方程决定组合系数c，主正向直接输出t=Qc。它解决输出路径的稳定性，代价是构造、分解和保存大型薄矩阵。相同hidden的P和Q在精确算术下覆盖同一空间，换坐标本身不扩大表示能力；不同hidden的完整头重求才检验空间变化。

新家族为`ORTHONORMAL_NEURAL_FE_BASIS`：网络计算空间特征，QR与原方程LS组成decoder；不是仅保存原MLP参数就能推理的场。本批不求全hidden梯度、不宣称精确VarPro或旧raw头回写通过。

```math
P(\psi)=Q(\psi)R(\psi),\quad t=Qc,\quad
\bar S=K-CH_{hat}^{-1}F,\quad \bar b=b_t-CH_{hat}^{-1}b_p,\quad A=\bar S Q.
```

```math
c=\operatorname{lstsq}(A,\bar b),\quad
\alpha=H_{hat}^{-1}(b_p-Ft),\quad
\Phi=\frac{\lVert b-S[t;\alpha]\rVert_2^2}{2\lVert b\rVert_2^2}.
```

全部40复端口是边界模态幅值，保留top20+bottom20；Hhat为原凝聚端口块，条件数约13284，与未凝聚Hp区分。只用GELSD／cond=1e-12，无正规方程、显式R逆、raw gamma回写、rank扫描或隐藏fallback。内部系数由原局部方程作仿射恢复，包含非零特解；误差恢复使用F(e)-F(0)。

| 身份／measured或frozen | 本批值及证据 |
|---|---|
| 物理与FE | 0.7 nm、真正三维缺口micro、384hex／p3／h0.175 nm／q15；full34050、trace18144、内部13824、slave2082、reduced18184；双Floquet／DtN，40完整端口 |
| 特征／起点 | 3×64 tanh、8载波、FP64、batch8；8576实hidden、1560复组合；V13原物理起点和五个实际保存trial，只取hidden；新点由两个已存hidden定义的射线派生，不猜丢失的小LS系数 |
| 材料 | canonical `input/materials/si_optical_constants_v1.json`，SI_OPTICAL_CONSTANTS_USER_20260929_V1；source 0.699999988显式alias为nominal0.7；Si n=0.999885140474+4.32477054e-6i，epsilon=n*n，air／mu=1；不插值、不换来源 |
| 实际source | 三个正式run均为`87940891c12ccdec35fca39cd453ab9a29eeeda5`；C1 writer `22f5eed7ddc3ecac14511c291fb71c28b60d0d2c`；C3 checker `4efc94aff427bfbc6d77852ddfe4cc55bff9fd34`。文档HEAD不冒充运行source |
| hash／数据边界 | [完整材料／physical／mode／action／数组身份](records/plan_and_input_identity_v14.json)；原action SHA9196edb…、REF7 a0610a…保持。solver不读参考，全部选点／状态冻结后独立VERIFY才读REF7；已消费micro续研，不是fresh终测 |

## Decoder与基底敏感性

共享writer在Task042边界递归处理Mapping、NumPy与复数，整数CPU key保持原JSON语义，禁止default=str和大型数组JSON。参数/c/trace/port/z先原子保存，numeric与physical_identity分开，再写审核和派生汇总。映射与中断小回归通过，历史失败原文未改。

P重建／Q正交缺陷均通过1e-10；P/A在所有点固定阈值下数值秩1560。原点复用P/A前作3列+2组合的真实barS配对；未发生原点A重建。实际残差与thin之差1.03e-12、驻点缺陷1.77e-12＜1e-8；所有点均通过，原点／最终保留Q重算Qc与已存trace差为0。数值满秩不称精确最优。

| 新制造见证；只检验本decoder | 已知z相对差；限1e-6 | 齐次恢复配对；限1e-10 | 原制造残差／decoder |
|---|---:|---:|---|
| ORTHO-M1：seed421401非零c及完整port | 2.31304e-13 | 9.05463e-17 | ≤1e-8，PASS |
| ORTHO-M2：本次物理c与同seed非零port | 3.52074e-13 | 7.85692e-17 | ≤1e-8，PASS |

制造rhs由原S.apply已知z生成，完整使用其trace／port常数，物理b未改。它们不同于旧V11-M2；旧1e-8头Gate、V12 FD以及V13全部负结果不变。[decoder raw](records/decoder_checks_v14.json)。

一次逆序行QR恢复canonical行后重新做1560原作用列与LS；未取它替换主结果。两种合法实现Phi差8.9858393e-10、trace差3.1768742e-8、z差3.1484268e-8。比较余量为max(1e-10,100×同点／thin／基底观察差)，实际约8.9858393e-8；标为`BASIS_ROUNDOFF_SENSITIVITY`观察值，不是全误差定理。[敏感性](records/basis_sensitivity_v14.json)。

## 六固定点与两个有界新点

Schur残差检查消去单元内部后的trace+port方程，native在恢复内部后检查原方程；均使用冻结的原RHS归一化。散射场误差是已有准确同mesh/p3参考下的真实场L2和curl误差，不能被小系数范数、驻点或loss替代。

| 固定物理模型／方法与s；measured，无量纲 | 同hidden V13旧raw Phi | V14实际Phi | Schur／native；限1e-6 | 散射E／scaled-curl；限1e-4 | P/A rank／最终资格 |
|---|---:|---:|---|---|---|
| ORIGIN（s=0） | 0.3181799855 | 0.318179987294 | 0.797721740／0.309359507 | 0.734256828／0.734361605 | 1560／1560；FAIL |
| TRIAL_4（s=0.00390625） | 0.318179758 | 0.318179704895 | 0.797721386／0.309359370 | 0.734256077／0.734360854 | 1560／1560；FAIL |
| TRIAL_3（s=0.015625） | 0.3181925773 | 0.318178861532 | 0.797720329／0.309358960 | 0.734254090／0.734358867 | 1560／1560；FAIL |
| TRIAL_2（s=0.0625） | 0.3216867803 | 0.318175490900 | 0.797716104／0.309357322 | 0.734245833／0.734350610 | 1560／1560；FAIL |
| TRIAL_1（s=0.25） | 1.217061893 | 0.318162013392 | 0.797699208／0.309350770 | 0.734212833／0.734317605 | 1560／1560；FAIL |
| TRIAL_0（s=1） | 230.4461445 | 0.318108326981 | 0.797631904／0.309324669 | 0.734081674／0.734186432 | 1560／1560；FAIL |
| NEW_S_2p0（s=2） | — | 0.318037282010 | 0.797542829／0.309290125 | 0.733908024／0.734012762 | 1560／1560；FAIL |
| NEW_S_4p0（s=4） | — | 0.317897054833 | 0.797366986／0.309221932 | 0.733565775／0.733670474 | 1560／1560；FAIL |

较大hidden处V13旧一阶头会严重过冲，完整头重求把trial_0的230.446144降至0.318108327；但正确比较基线是V14原点0.318179987，不是旧的高loss试探。trial_0相对新原点下降2.25219e-4、超过余量，native不高于原点1.05倍且端口/恢复/identity通过，故自动执行s=2；它继续满足条件，再执行s=4。五保存点射线误差≤4.92e-16＜1.85e-13容差；新hidden变化满足1e-3×原点范数界。共两新点，未追加s=8或新方向。[profile及分流](records/profile_points_v14.json)。

## 独立场、通道与功率

所有求解／选择／hash冻结后，一次FE环境处理2历史+8新状态，10个去重状态。原恢复和MPC slave-zero均通过；最终port固定RHS2.3469973e-16、恢复6.08841e-13、identity6.62128e-13，不能替代全方程失败。

| 最终s=4审核；measured，无量纲 | 实际值 | 原限值／判断 |
|---|---:|---|
| Schur／native／增广 | 0.797366986／0.309221932／0.309221932 | 各1e-6，FAIL |
| total原增广／独立DOLFINx native | 0.107299821／0.107299821 | 1e-6，FAIL |
| total E／scaled-curl | 0.0767638614／0.0767762747 | 1e-4，FAIL |
| scattered E／scaled-curl | 0.733565775／0.733670474 | 1e-4，FAIL；研究≤0.5且各25%改善亦FAIL |
| selected复E／H | 0.0854500003／0.0669249701 | 1e-4，FAIL |
| 40复通道差／最大通道功率差 | 0.0493650726／0.0789422564 | 1e-4／1e-6，FAIL |
| R／T／A_balance／A_volume绝对差 | 0.0326695451／0.0789412607／0.111610806／0.000451236 | 各1e-5，FAIL |
| 能量闭合误差 | 0.1120620416 | 1e-5，FAIL |

mu=1且波长固定时，原H_code=curl(E)/(i k0 mu_r)，全域H的相对L2误差与scaled-curl相同；selected复H也独立保存。R00_s/R00_p/R00_total=0.084974088743／1.2727375307e-07／0.084974216016；R_total/T_total/A_balance/A_volume=0.084976274211／0.79810652222／0.11691720357／0.004855161918。这些全部是**未资格化诊断**，无official结果。完整40通道保留原index、m/n、极化、参考面、total/scattered复数；不校相位、不重归一化。[场／功率](records/candidate_comparison_v14.csv)、[通道](records/channel_observables_v14.csv)、[selected复场](records/selected_fields_v14.json)。

现有验证器把候选审核全部写入JSON，当前参考的独立native标量未持久化；不猜填，保留原合格REF7身份和历史qualification。这项记录限制不影响本批候选自身原方程与场明显FAIL，不能从本批重新声明参考Gate通过。未重做LU／teacher／参考或V9区域campaign。

## 成本、资源及停止

| shared-workstation成本；measured，含失败／拒绝 | 墙钟／同时采样树峰／边界 |
|---|---|
| O1直接decoder与逆序对照 | 507.130224s／3052736512B；自身swap0，全后代清场 |
| O2／O3六固定+两个新点 | 1965.470091s／3243409408B；自身swap0，全后代清场 |
| O4独立10状态审核 | 37.672464s／682049536B；自身swap0，全后代清场 |
| 全正式流程 | **2510.272780s**，峰值最大**3243409408B≈3.021GiB**；VRAM0；树峰不把不同stage相加 |
| 操作账 | P/Q/A9套≤10；LS11调用／11RHS≤24／28；S+SH12551≤18000；audit20≤80；新profile2≤2；全场10≤10；修正c次数0 |
| 大对象与存储 | 一套薄矩阵452874240B只是载荷；P/Q/A/U、分解副本和父子进程全纳树峰。规划7.6e9B＜8GiB，只驻留一套分解。原点/最终Q+c保留，其余新可再生P/Q删除前保留state/hash/lifecycle；历史负artifact未删。新持久artifact922132825B，全部Task042 artifact约6.719GB，均低于8／20GiB |
| 环境／硬件 | 正式run各自实时选CPU0（不是永久预约）；MPI1、数学／Torch intra/inter1、Loader0；FE complex128/int64与CPU-only Torch独立activation/cache。自有lock、nice10/I/O idle，只控制本任务后代 |
| 内存监督 | 16GiB hard／12warn、ownswap0，系统10%+邻增长128GiB余量；无cgroup委派，使用独立0.5s采样subreaper，不能称连续内核cap。没有own warning／压力stop；邻负载库存变化、可比阶段速度未知，影响和无争用性能均INCONCLUSIVE |
| 历史／总截止 | V6–V13可核formal下界12160.139323s，本批后14670.412103s；旧辅助未知不补造。start05:38:08UTC，重负载09:23:08、总09:38:08；实际重負載07:10清场。研发/辅助/交付计入总elapsed，与formal wall分列 |

前期整数CPU key边界失败及一项过严浮点测试失败保留；首次C2纯小测试误绑旧CPU0，已结束/清场，重跑从实时audit取CPU16。正式三个run均重新独立选核，未发生正式实现修复重放。最终22 pure测试通过，保留两套Q重算trace差0；checker从原字段重算全部FAIL，`EVIDENCE_CONSISTENT`不等于solver成功。Ruff本环境不可用，未宣称CI/full-repository/MPI2/4测试通过。[测试](test_summary.md)、[资源／嵌套耗时](records/resource_costs_v14.json)、[one-run身份](records/run_index_v14.json)。原action/local p3恢复复用，无候选global p4 LU、全局S/CSR、正规方程或fallback；没有把内存/时间只记为网络参数。

## 收口与未确定问题

稳定坐标通过，有限头重求避免了旧大步的一阶过冲；hidden空间变化只带来0.088922%的Phi和约0.0941%的散射误差改善，原约0.798平台未被突破，rho减半及真实场准入均FAIL。它支持当前受限空间的具体局限，不识别唯一Maxwell困难根因；其它hidden方向、局部表示、最大模型单步/步数/通道存储及独立离散精度仍unknown。micro跨度只有数个波长，不能外推最终48小时。

唯一下一建议，尚未实施：在新review中固定相同micro、1560维容量和40端口，做一次**几何局部、正交Nédélec trace表示**对照，替换当前高相关全局tanh特征，检验表示是否覆盖更有用的原方程方向。当前仅一条hidden射线的数据不支持继续相同大头／QR／切向／缩步循环，也不证明所有神经方法或Full3D迭代都不可行；旧p4逆继续关闭。

本批队列完成并收口，不做新p4参考、最大模型、GPU、P/POD/rank/宽度/学习率扫描、旧FD／切向重复或seed420620。旧task/review/response/raw原样保护。[独立Gate与未运行](records/qualification_and_dispatch_v14.json)、[历史保护](records/protected_history_v14.json)、[实际journal](records/progress_journal_v14.jsonl)。只推送执行分支，等待review，master merge未批准。
