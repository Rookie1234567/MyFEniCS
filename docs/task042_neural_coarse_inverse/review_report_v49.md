# Review V49：与Task42extra分工，优先取得准确的0.7nm完整三维解

## 0. 裁决与实质交付

**接受V50完整积分、解析FLAT及表示能力的证据；原尺寸0.7nm／2TB／48h仍未完成。授权V51在本分支推进确定性的准确离散：复用已有固定相位有限元数学，接到V50完整物理链，连续完成解析FLAT、真实三维NOTCH的有限精度比较与成本。暂停新NN训练、NN预条件器和旧固定A尾部校正。**

本批消除的blocker是：当前多项式空间即使把其代数方程解到约1e-12，物理场仍不准确。目标是一个可复用的准确有限基准和下一规模所需分辨率，不是又一张接口PASS表。用户要求减少不必要测试，不是取消原方程、场、功率和安全检查；具体减负见§6。

用户追加要求：**与隔壁task42extra最新路径分开，不能两边做同一件事。** 本报告已读取该分支最新Review V29。两路分工及已有成果复用见§1；不因看到“波动／相位”相似字眼混淆“改变物理FE空间”和“在既有FE空间中学习求解系数”。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42_neural_coarse_inverse
worktree               = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-05
reviewed_HEAD          = 2980735e5f0fcf48d54258a4e29b351033cafb69
reviewed_commit_UTC    = 2026-10-05T07:40:45Z
latest_response        = response_v50.md
previous_review        = review_report_v48.md
original_base_SHA      = ccd357885f7f9be84efe3be07868cc94f13d93fc
V50_solve_source       = ba6644fae8ec62ba191a7bac04f2d21006c8264c
V50_verify_source      = e82b713ec9bc86b124ef9f623a981664ffe93ce2
sibling_branch         = task42extra_feinn_5nm
sibling_readonly_HEAD  = 8d617d4d206b08f38279320b67188db1b8ccd301
sibling_latest_review = review_report_v29.md
sibling_campaign      = V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
next_batch            = V51_PHASE_EXPLICIT_FULL3D_ACCURACY
required_response     = response_v51.md
NN_training_this_batch= NOT_AUTHORIZED
merge                 = NOT_APPROVED
```

Review V48已由V50回应，故新增V49。它覆盖V50“不得新相位空间／不得超出旧四空间”的本批限制，不改旧科学结果。本轮授权由用户转交执行；不自动通知、启动或修改隔壁窗口，同一工作树一个执行者。审阅本次核对远端、最新合同／回应、配置与相关源码，未SSH运行工作站、取得实时资源或重演全部科学数组；同SHA治理／task／summary复用已读内容。历史数字为recorded measured/derived，以下为planned/not_run。

最终目标仍是原50×25nm周期、z=−10..130nm、17×25×120nm Si结构、λ0.7nm、任意非可分三维能力；冷N=1端到端≤172800s，约2TB整机保留余量、任务峰≤2e12B、ownswap0。有限532模式准确性不是原尺寸、AUTO32060或连续收敛资格。项目成功不以使用NN为条件；以后宣称NN增量时，原同正确性全成本20%门不降低。

## 1. 与隔壁的边界：两条方法路线，而非两个目录重复计算

| 对象 | 本Task042／V51 | 隔壁Task42extra／V30，仅只读说明 |
|---|---|---|
| 首要问题 | 当前0.7nm物理离散是否足够准确，以及成本如何增长 | 学习新的局部波动函数能否完成既有FE问题的求解 |
| 数学未知 | 周期Nédélec包络的全部FE系数；已知横向相位解析保留在物理基函数 | 局部复指数的方向／幅值及逐步扩充子空间中的组合系数 |
| 是否训练 | 不训练；固定解析κ，不学习方向或波矢 | 真实学习方向／局部幅值，固定字典greedy作控制 |
| 首个完整问题 | V50的0.7nm、80hex、532模式FLAT／NOTCH | 自身M5的5nm／p3完整三维问题，之后有条件缩尺0.7nm |
| 核心验收 | 连续解析FLAT正确、NOTCH有限p/h一致性、完整成本 | 新学习机制的完整数值Gate及同正确性NN净收益 |
| 不做 | M5训练、learned/fixed wave greedy、神经字典／列库／teacher／QR训练 | 本报告不向隔壁发命令或替其安排工作 |

隔壁历史[V20](https://github.com/Rookie1234567/MyFEniCS/blob/8d617d4d206b08f38279320b67188db1b8ccd301/docs/task042extra_feinn_5nm/response_v20.md)已经实现过固定横向相位的gVh空间，不得把本轮写成第一次发明。其8-cell机制配对可作来源；336cell／340端口候选的原坐标恢复FAIL、p6前置失败和准确性UNKNOWN保持。其材料也与V50不完全相同，不能继承旧场为本次参考。隔壁最新[V29合同](https://github.com/Rookie1234567/MyFEniCS/blob/8d617d4d206b08f38279320b67188db1b8ccd301/docs/task042extra_feinn_5nm/review_report_v29.md)已明确回到学习子空间，不续做固定相位FE工程。

**复用而不重复开发：**先检查`src/solvers/fixed_phase_fem.py`的`carrier/physical_rhs/physical_fields`、相关`common_3d_forms.py`的完整curl及`fixed_phase_port_coordinates.py`的等价换元。只迁移本轮所需的小数学闭包／补丁及对应测试，逐文件记donor blob和本地改变。不得直接搬旧`build_model`：它绑定旧材料、旧几何／340通道／FEINN工作流。不得导入另一活跃工作树、整分支merge/cherry-pick、复制旧runner或复跑其V20/V30。所有写入仅本分支，donor读后冻结；不轮询等待隔壁。

这次的新工作是**在V50完整未截断边界和独立解析审核下完成准确性**，不是恢复隔壁旧窗口。公共解析公式和已验证小核可以共享，主case、训练数据和执行队列不得互相借用。若隔壁在本批开始前又变更范围，仅读一次最新合同写明差异，不自行对它排任务；本分支仍不做任何NN／greedy试验。

## 2. V50证据及停止无效续跑的理由

依据：[response_v50](response_v50.md)、[完整结果](outcomes/complete_physics_accuracy_cost_v50.md)、[准确性记录](outcomes/records/complete_accuracy_checks_v50.json)、[最终费用](outcomes/records/resource_costs_final_v50.json)。

| 同0.7nm有限模型；无量纲measured／derived | V50记录 | 本次取舍 |
|---|---|---|
| p4/p5全532边界q47/q63 | 最大相对差约7.73e-14 | 保留算法和未截断规则；新相位泛函只验新依赖 |
| FLAT p5原rho | 5.66631438697e-12 | 代数通过，不等于物理准确 |
| FLAT总E／H误差 | 1.01270192133／1.01269620637 | 准确性FAIL，不再对同空间训练系数 |
| FE R／T vs解析 | 约0.999826／0.000173628 vs0.113433／0.882459 | 能量闭合约3.17e-13不能替代正确散射 |
| X2/p6 | H/curl插值9.50015e-4；derived下界9.37460e-4 | 高于1e-4；不是新gVh空间的下界 |

旧q不足与小项剪枝分别存在。旧p4/p5场代入统一完整边界，rho约0.246451／0.424939；旧同离散记录不回写，也不继续作新方程authority。新路径所有层保持非零项；只改最外层flag而下游继续剪枝不合格。不要再重跑这套旧场归因、四空间筛选、codec或ILU。

新相位路线没有预先成功保证。已知快速横向相位被提取，并不意味着任意缺口的包络都光滑；反向／多向散射、边缘奇异性、法向分辨和高阶模式仍可能主导误差。不能把“方程小残差”和“相位方法已省网格”混称。

## 3. 数学与数据身份：物理场必须留在新空间

令实横向入射波矢κ=(kx,ky,0)，单位nm^-1，沿用exp(−iωt)：

```math
 g(x)=e^{i\kappa\cdot x},\qquad E=g u,\qquad
 C_\kappa u=\nabla\times u+i\kappa\times u,\qquad
 \nabla\times E=g C_\kappa u.
```

u在x/y周期，E恢复原Bloch相位；完整三分量、内部矩、两方向传播和非可分材料均保留。κ固定，不学习，不另取材料依赖或单向z相位。物理cfg的kx/ky、mode波矢和入射角不改；只给约束构造传包络周期相位。核对g(x+L)/g(x)与物理Bloch相位，不从slave→master系数表面符号猜测。

新离散为`u_h ∈ periodic Nédélec V_h`、`E_h=g u_h`。不得投回旧多项式Nédélec/DG-p再审核，也不得只给旧系数乘相位或重新编号。真实H为`g Cκu/(i k0 μr)`的code单位，SI再除η0；不能漏κ叉乘项。

实κ、单位模g下，完整体弱式是：

```math
 a_\kappa(u,v)=\int_\Omega \mu_r^{-1}C_\kappa u\cdot\overline{C_\kappa v}
                  -k_0^2\epsilon_r u\cdot\overline v\,dx.
```

UFL内积第二参数取共轭；trial/test均含Cκ。无paraxial、单向或弱散射截断。κ变化使局部tensor／LU／Schur／恢复包全部成为新数学身份；不得复用旧数值因子。首实现直接用完整UFL/FFCx新式，不以另开发准备优化作为求解前提；旧六Gram未含的新交叉项不能遗漏。

物理模式横向波矢仍是κ+Gmn、Gmn=(2πm/Lx,2πn/Ly,0)。包络边界积分中的横向相位减去κ，但beta、偏振、导纳、入射功率和参考面仍按物理波矢计算。C、D、traction、projection分别变换，D不假定为Cᴴ。主未知登记TOTAL_ENVELOPE；真实入射生成RHS，不能用解析答案制造主solve载荷。散射场统一减同一解析层状背景。

首个新p/边界布局作q47与独立q63的全532配对，沿原1e-11相对／1e-10操作门。相同边界依赖在FLAT/NOTCH之间直接复用，不再核对旧q23/25；新p/网格只验新增身份。若高阶积分本身不达门，允许一次有实际相位跨度依据的63/79配对，不无限加q。体积分按完整Cκ多项式次数设置，不能把κ项与旧curl项混作同一自动degree。

端口若使用已知参考面相位的可逆对角换元，先冻结行列变换及原坐标恢复，保存映射；仅在表示范围安全时计算raw范数，另外保留H加权原行残差和物理参考面振幅。不得用raw极端尺度或稳定物理值彼此替代，旧raw恢复FAIL不改判。严禁拟合幅相、删小项、伪逆或按容差置零。

凝聚继续复用V50。若内部端口支撑非零，用现有通用增广凝聚精确纳入；不删内部项或继承旧“边界必无内部浮点项”的拒绝逻辑。确需补接口时，只增加同一消元代数的窄支持；在`[V B; -D H]`约定下必须包含`Hhat=H+Di Vii^-1 Bi`和相应有效载荷，恢复`ui=Vii^-1(fi−Vit ut−Bi a)`。用一个非零内部／端口的小复系统校核，不重建另一套求解器。

## 4. 实际队列：解析正确后连续推进非可分三维

物理沿V50全精度descriptor：s=7/135，x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)。λ0.7nm，grazing1°／azimuth5°／s／幅值1；air1，Si n=0.999885140474+4.32477054e-6i、epsilon=n²、μ1。全532模式m=−9..9、n=−3..3、top/bottom及s/p，不是目标AUTO32060。

FLAT按z=0分空气／基底。NOTCH使用V50的全精度`notch_box_nm`与几何位置，原80hex真实两cell Si改空气、不沿y复制；加密后按同一几何盒重标，不能按旧cell-id移到另一位置。实际resolved_config须写真实p/κ/q/约束，不沿用模板中的旧degree4/q23。

| 路线 | 实际工作 | 自动分流 |
|---|---|---|
| F4 | 新gVh／80hex／p4完整FLAT直接解及解析E/H/532功率 | 必须先取得完整结果，不只提交插值测试 |
| F5 | 仅F4准确性不达时，80hex／p5同FLAT | 先排实现／单位／源错误；依然失败转有限常规保底，不在旧p无限优化 |
| N4、N5 | 至少一个phase-FLAT准确后，80hex NOTCH的p4/p5两个独立零初值完整解 | p4可作粗对照，不要求先是准确NOTCH；新模式／全部内部保留 |
| NH | N4/N5不一致但数学可信时，允许一次160hex／p5方向h细化 | 在x/y/z中只选一轴二等分全部原区间；按下面固定指标选，不改几何或模式 |
| OC | 常规多项式高分辨保底／独立参照，最多一个完整FLAT | 相位链数学／适配未闭合时独立继续；无安全容量则仅报告量化需求，不能冒称已取得解 |

NH方向按N5包络的逐cell梯度能量`sum(h_K,d² * integral(|∂d u|² + |∂d Henv|²))`的最大轴选择，Henv=Cκu/(i k0 μr)，采用固定code单位；并列时x→y→z。此指标只是决定一个有限h对照，不能充误差估计或精度证明。同κ，最后仍比较真实E/H和所有功率；若参考面/实体集合变化，完整保留新身份。

OC不重复V50已失败四空间。仅在无solve的廉价解析投影／插值中检查`普通X4/p6`与`普通X2/p8`两个更高分辨候选；从H/curl插值≤2e-5且容量安全者选最少trace行的一项，实际最多一个FLAT solve。低阶表示下界只用于排除，不当通过证明。两个都不适用即不装配factor、不降低精度、不借更小域过门。这项保底不是替隔壁生成M5 teacher，也不以获得它为phase路线准入条件。

**最多六个新完整solve：F4、条件F5、N4、N5、条件NH、条件OC。** 不重复REGULAR／四q引擎，不新增PC、训练或目标尺寸PDE。普通bug可在同一case恢复；实现接入超过120min仍无可信phase solve入口时，先推进OC已有传统入口和容量结论，剩余实现修复受总预算，不空等另一分支。不得为强行完成solve而绕过真失败。

有限p/h对照可以读取本批已计算场用于上述预登记自适应选择；本批没有训练，不套用“读过对照场就禁止再做任何确定性精度验证”的无关限制。最终验收采用独立原弱式，不能用场对比反调阈值、幅相或材料。

## 5. 真正完成的标准与下一规模

每个返回状态先保存包络完整系数、κ、port和source/input，释放直接factor／无用矩阵后恢复／输出；保留最小恢复包和独立原弱式。保存g u的可再求值表示，不以采样点或旧DG多项式替代完整场。派生保存／审核出错就补审，不重解合法返回向量。

| Gate | 固定要求 |
|---|---|
| 原方程 | 完整未凝聚体弱式＋全部DtN、native／增广／port≤1e-6；直接内部目标≤1e-10，最多两次已有残差精化 |
| 恢复／变换 | 全内部恢复、相位变换恒等式操作尺度≤1e-10，MPC按原规则；不能以native单项替代 |
| FLAT准确性 | 解析total E/H/curl和selected≤1e-4；R/T/A/A_volume绝对差及能量≤1e-5；最大逐mode功率差≤1e-6 |
| NOTCH有限一致性 | 高低两级共同物理积分的total/scattered E/H/curl、selected和参考面复通道≤1e-4；功率沿上行原门 |
| 新积分 | 实际新相位/布局的完整532配对与两级共同积分稳定；未知不得称pass |

近零解析散射／零高阶模式用入射单位场或入射功率的原固定绝对规则，不用近零分母。能量使用独立体吸收，不能归一化R+T+A。新空间独立审核是在相应gVh测试函数上验证原物理弱式，**不能要求新E恰好满足旧多项式离散矩阵**；不同空间通过解析／共同物理积分与模式比较联系。候选凝聚与独立未凝聚原作用必须分开。

FLAT准确且NOTCH至少一对有限增量达标，才记`ACCURACY_ANCHOR_ON_FIXED_532`。不称严格误差上界、连续收敛、模式截断收敛或原尺寸资格；只FLAT通过则明确`FLAT_PASS_NOTCH_NOT_QUALIFIED`。若NOTCH仍差，保存实际误差的方向／区域与成本，关闭本批额度，不能用更多训练掩盖。

同时交一张目标尺度桥接表：沿合格表示记录实际细胞／独立FE／trace／内部／模式、局部tensor与恢复、全局factor/端口/输出时间与同时峰；由实际case和准确性边界推导两个下一尺度的行数／载荷／内存区间，unknown因子fill和迭代数不填0。本批不再运行新尺寸，只提出一个下一完整pilot。目标生产仍须分布式matrix-free原作用、流式DtN与有界可扩展PC；有限直接authority不是全球直接factor生产许可。

## 6. 减少无效测试、归档和“报错就交棒”

**只保留四类必要检查：**新相位curl／弱式与κ=0短退化；新C/D/RHS＋MPC完整532配对；首次完整FLAT解析结果；NOTCH完整物理及有限p/h。普通保存和reader反例复用已有fixture。相同数学source依赖、ABI、配置和数组hash的旧资格直接复用，不因文档／stage别名重新跑FE。

本批不例行全库pytest、不重建全库文本索引、不逐次扫描／重哈希全部历史artifacts、不重复V50旧q／背景归因；这是用户明确的本批测试范围收窄，不修改AGENTS。只运行改动模块的targeted tests、相关Ruff/compile和一次紧凑交付检查。元数据／文档检查目标累计≤20min；超出先简化实现，不降低科学Gate。完整物理审核属主科学工作，不算应砍掉的“杂项测试”。

每个已有核只验证新增依赖；每个新p/材料/几何张量类验证一次并cache同身份结果。不对每cell重复同一个高成本资格，不把监督器用于全历史存储统计；监督只查本actor进程树，磁盘一次准入＋阶段边界。新证据只保存本批增量manifest与父hash，不再层层嵌套上千条旧JSON。

普通API、shape、导入、stage接线、缓存、writer问题同轮定位→最小修复→受影响测试→从最近合法状态继续；**不设第几个bug就停整批的次数门**。同根因两次失败后必须换诊断／采用本合同已授权替代，不第三次盲重放。累计修复含受影响重放≤2h，计入总窗。优化失败保留原正确实现，不取消主物理队列。未触科学／安全阻塞就继续已授权工作，不逐小步等新review。

失去源码／ABI／监督身份，或原方程／端口／恢复实现不可信时，必须先隔离依赖计算，不能把“加快”理解为跳过Gate。普通数值误差不改写成bug，不能改材料、波长、模式数或阈值救场。

## 7. 时间、资源、Git和正式入口

从执行者首项实际准备的UTC／monotonic／boot_id冻结**7h总研发窗**，含实现、测试、修复、等待、求解、验证与交付；最后45min收尾，数值有载累计≤5h。继承旧账但不重开V50 closed窗口。每case含准备通常≤3600s；首case实测较大可在数值总额内预先重新分配剩余case份额，不临近超时无限延长。会话恢复重读真实时钟与ledger，不用摘要中的剩余时间。

继承V50资源上限：规划同时峰≤16GiB、warning20GiB、采样整树hard24GiB、ownswap/OOC0；MPI1、数学/CPU线程1、GPU0、Loader0，现场空闲物理核、避忙SMT。保留系统和邻任务增长余量、原PSI及独立自有锁。与NN-Lab-V2只按各自既有受控共享合同工作，不改其进程、环境、亲和性、锁、watchdog或资源预算，不新增未受控并行actor。

新case先实际拓扑/矩阵/端口/缓存容量规划，不借旧行数。phase主case沿V50全局凝聚行≤35000；OC仅允许最多80000行的受监督稀疏symbolic评估，numeric仍须后端可靠factor/workspace估计×2加全部同时对象≤16GiB，否则不分解。不存在估计或估计不可信不准赌OOM。无全局稠密逆、OOC、盲目换排序或系统BLAS/ABI重装。更大数学空间不自动获得更大RSS许可。

新ignored≤6GiB，Task042去重累计≤38GiB、free≥50GiB；按阶段统计，不为缩档删除旧失败。监控采样如实报告实际最大间隔和采样口径，不声称内核连续hard峰；不得因周期字段0.5s就写始终0.5s。资源压力停止只清自身后代；最多一次≤600s前台冷却并在原安全门复核后恢复，等待计费，不轮询等隔壁。

先读规则／当前合同，核对canonical worktree、分支/HEAD/upstream/origin、活跃run；安全fetch/ff-only，不reset/stash/clean、不覆盖修改。review提交不启动工作站作业。正式数学代码运行前clean commit；历史结果source与文档HEAD分开。旧task/review/response/raw不改；README/summary/两总账只追加短入口，禁止用本报告“未用NN”去改写隔壁状态。

下列为待实现的one-run入口，复用现有run_case和监督／事务writer，不复制大runner，也不自动执行不存在的命令：

```text
input/task042_neural_coarse_inverse/v51_phase_setup.dat
input/task042_neural_coarse_inverse/v51_flat_p4.dat
input/task042_neural_coarse_inverse/v51_flat_p5.dat
input/task042_neural_coarse_inverse/v51_notch_p4.dat
input/task042_neural_coarse_inverse/v51_notch_p5.dat
input/task042_neural_coarse_inverse/v51_notch_hprobe.dat
input/task042_neural_coarse_inverse/v51_ordinary_flat_control.dat
input/task042_neural_coarse_inverse/v51_verify_cost.dat
```

每dat一项明确计算，经`python scripts/run_case.py <dat>`；条件槽只按§4准入，不在一个dat藏多波长／多case campaign。source、input_original.dat、resolved_config.json、run_manifest.json、input/physical/discretization/material/mode/array hash、run_summary及资源齐全。只哈希本次实际依赖和新数组一次；纯文档提交不改变已完成数学资格。

## 8. 一次交付、明确结论

提交`response_v51.md`、`outcomes/phase_explicit_full3d_accuracy_v51.md`，并提供紧凑的分工／最小迁移清单、实际输入／case表、原残差与FLAT/NOTCH E/H/532功率、p/h误差、冷费用与缓存复用、同时峰、修复/未运行原因、下一尺度需求。保留完整场的ignored路径和hash。新报告不以测试条数、归档数量或版本数作进展指标。

科学结果不等网页渲染才保存；本地检查新文档公式和表格，精确GitHub页面不可取就记录NOT_VERIFIED，不触发PDE重跑。代码／数值与网页资格分开，不能伪称CI或视觉通过。

仅推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`。结束后记录精确remote/HEAD/upstream/工作树、closed ledger、active null、后代清场和锁释放；不通知／接管隔壁，不merge master或其他分支。若达到完整有限准确性，下一项应是一个有成本与误差依据的尺度pilot；未达到就报告还差哪个物理量和可核验原因。不得默认跳回NN预条件器或为用NN而新造瓶颈。

### 来源与范围

本报告的数值来源均为本分支V50及冻结extra V20/V29原记录；变换公式直接由E=g u代入curl与弱式得到，不依赖网络或近轴理论。Basix对一般单元间插值要求正确pull-back、push-forward和DOF方向变换，见[官方插值接口](https://docs.fenicsproject.org/basix/v0.10.0.post0/cpp/namespacebasix.html)；这里只是实现接口依据，不授予本case精度。额外历史量与门不因本报告改变。
